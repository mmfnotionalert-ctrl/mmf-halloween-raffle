// Tells the patch page which pumpkins are taken. Public, and contains no personal data:
// just pumpkin numbers. Names are added separately, once approved, through data.json.
import { getStore } from '@netlify/blobs';
import { SEEDS, TOTAL, assign } from '../lib/patch.mjs';

export const config = { path: '/api/reserved' };

export default async () => {
  let records = [];
  try {
    const store = getStore('halloween-raffle');
    const idx = await store.get('index', { type: 'json' });
    records = (idx && idx.records) || [];
  } catch (e) {
    // fall back to the seeds only; the page still shows everything approved in data.json
  }
  const taken = [...assign([...SEEDS, ...records])].sort((a, b) => a - b);
  return new Response(JSON.stringify({ total: TOTAL, reserved: taken, webhook: Boolean(process.env.STRIPE_WEBHOOK_SECRET) }), {
    headers: {
      'content-type': 'application/json',
      'cache-control': 'public, max-age=0, must-revalidate',
      'netlify-cdn-cache-control': 'public, s-maxage=15, stale-while-revalidate=60',
      'access-control-allow-origin': '*',
    },
  });
};
