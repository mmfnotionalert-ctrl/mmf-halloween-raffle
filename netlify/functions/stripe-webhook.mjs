// Stripe calls this the moment a raffle payment goes through. It records which pumpkins
// are now taken so the patch greys them out straight away. It stores no names, emails
// or phone numbers: only a hashed reference, the time, the ticket count and the picks.
import { createHmac, timingSafeEqual } from 'node:crypto';
import { getStore } from '@netlify/blobs';
import { CAMPAIGN, recordFromSession, shortHash } from '../lib/patch.mjs';

export const config = { path: '/api/stripe-webhook' };

const TOLERANCE = 300; // seconds

function verify(body, header, secret) {
  if (!header) return false;
  const parts = Object.create(null);
  const v1 = [];
  for (const kv of header.split(',')) {
    const i = kv.indexOf('=');
    if (i < 0) continue;
    const k = kv.slice(0, i).trim(), v = kv.slice(i + 1).trim();
    if (k === 'v1') v1.push(v); else parts[k] = v;
  }
  const t = parseInt(parts.t, 10);
  if (!t || Math.abs(Date.now() / 1000 - t) > TOLERANCE) return false;
  const expected = Buffer.from(createHmac('sha256', secret).update(`${t}.${body}`).digest('hex'));
  return v1.some((sig) => {
    const b = Buffer.from(sig);
    return b.length === expected.length && timingSafeEqual(b, expected);
  });
}

async function update(store, change) {
  for (let attempt = 0; attempt < 12; attempt++) {
    const cur = await store.getWithMetadata('index', { type: 'json', consistency: 'strong' });
    const records = (cur && cur.data && cur.data.records) || [];
    const next = change(records);
    if (!next) return 'unchanged';
    const opts = cur ? { onlyIfMatch: cur.etag } : { onlyIfNew: true };
    const res = await store.setJSON('index', { records: next }, opts);
    if (res.modified) return 'saved';
    await new Promise((r) => setTimeout(r, 50 + Math.random() * 150));
  }
  throw new Error('could not save after retries');
}

export default async (req) => {
  if (req.method !== 'POST') return new Response('Method not allowed', { status: 405 });
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!secret) return new Response('Not configured', { status: 500 });
  const body = await req.text();
  if (!verify(body, req.headers.get('stripe-signature'), secret)) return new Response('Bad signature', { status: 400 });

  let event;
  try { event = JSON.parse(body); } catch { return new Response('Bad JSON', { status: 400 }); }
  const obj = (event.data && event.data.object) || {};
  const store = getStore({ name: 'halloween-raffle', consistency: 'strong' });

  if (event.type === 'checkout.session.completed' || event.type === 'checkout.session.async_payment_succeeded') {
    if (obj.payment_status !== 'paid' || (obj.metadata || {}).campaign !== CAMPAIGN) return new Response('Ignored', { status: 200 });
    const rec = recordFromSession(obj);
    const result = await update(store, (records) => (records.some((r) => r.id === rec.id) ? null : [...records, rec]));
    return new Response(result, { status: 200 });
  }

  if (event.type === 'charge.refunded' && obj.refunded && obj.payment_intent) {
    const pi = shortHash(obj.payment_intent);
    const result = await update(store, (records) => {
      if (!records.some((r) => r.pi === pi && !r.v)) return null;
      return records.map((r) => (r.pi === pi ? { ...r, v: true } : r));
    });
    return new Response(result, { status: 200 });
  }

  return new Response('Ignored', { status: 200 });
};
