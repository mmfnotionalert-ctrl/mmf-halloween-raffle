// Mae Murray Foundation Halloween Raffle 2026: pumpkin placement.
// This must stay identical to assign() in tools/refresh.py, so a name approved later
// always lands on the same pumpkin the webhook greyed out.
import { createHash } from 'node:crypto';

export const TOTAL = 400;        // pumpkins in the patch
export const LEGACY_TOTAL = 100; // size of the patch when the first buyers were placed; never change
export const SEED = 20261026;    // shuffle seed; never change
export const CAMPAIGN = 'halloween_raffle_2026';

export const shortHash = (s) => createHash('sha256').update(String(s)).digest('hex').slice(0, 16);

// Paid purchases made before the webhook existed. No personal data: hashed session id,
// payment time, number of tickets, pumpkins picked.
export const SEEDS = [{"id": "d95a4bb50c330a60", "t": 1790847139, "q": 1, "p": []}, {"id": "565eab51091dba51", "t": 1790859844, "q": 1, "p": []}, {"id": "17ae56be634224cc", "t": 1790861389, "q": 1, "p": []}, {"id": "f7148ef891cef474", "t": 1790861472, "q": 1, "p": []}, {"id": "4ec80e270a1bb904", "t": 1790866145, "q": 1, "p": [13]}, {"id": "d31b20640f02a243", "t": 1791399882, "q": 1, "p": [107]}];

function legacyOrder() {
  const order = Array.from({ length: LEGACY_TOTAL }, (_, i) => i);
  let s = SEED >>> 0;
  const r = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  for (let j = LEGACY_TOTAL - 1; j > 0; j--) {
    const k = Math.floor(r() * (j + 1));
    [order[j], order[k]] = [order[k], order[j]];
  }
  for (let i = LEGACY_TOTAL; i < TOTAL; i++) order.push(i);
  return order;
}

// records: [{id, t, q, p:[1-based pumpkin numbers], v:void}] in any order.
// Returns a Set of 0-based pumpkin indexes that are taken.
export function assign(records) {
  const byId = new Map();
  for (const r of records) if (r && r.id) byId.set(r.id, { ...(byId.get(r.id) || {}), ...r });
  const list = [...byId.values()].sort((a, b) => (a.t - b.t) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const taken = new Set();
  const legacy = legacyOrder();
  const nearestFree = (i) => {
    for (let d = 0; d < TOTAL; d++) for (const c of [i - d, i + d]) if (c >= 0 && c < TOTAL && !taken.has(c)) return c;
    return null;
  };
  for (const x of list) {
    if (x.v) continue;
    const picks = (x.p || []).filter((n) => n >= 1 && n <= TOTAL).slice(0, x.q).map((n) => n - 1);
    for (let q = 0; q < x.q; q++) {
      let got;
      if (q < picks.length) got = taken.has(picks[q]) ? nearestFree(picks[q]) : picks[q];
      else got = legacy.find((i) => !taken.has(i));
      if (got === null || got === undefined) break;
      taken.add(got);
    }
  }
  return taken;
}

export function recordFromSession(s) {
  const md = s.metadata || {};
  let q = parseInt(md.tickets, 10);
  if (!q) q = Math.round((s.amount_subtotal ?? s.amount_total ?? 0) / 500);
  const p = [...String(s.client_reference_id || '').matchAll(/p(\d+)/g)].map((m) => parseInt(m[1], 10));
  return { id: shortHash(s.id), pi: s.payment_intent ? shortHash(s.payment_intent) : null, t: s.created, q, p, v: false };
}
