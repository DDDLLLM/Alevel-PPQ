import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { parseQuery, matchesDocument, matchText, prepareIndex, candidatePages } from '../dist/search-core.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const data = path.resolve(process.argv[2] || path.join(root, 'student-publish'));
const read = p => JSON.parse(readFileSync(path.join(data, p), 'utf8'));
const manifest = read('manifest.json'), docs = read('catalog.json');
const allRows = manifest.years.flatMap(y => read(y.path));
let messages = [], fetched = [];
globalThis.self = globalThis;
globalThis.postMessage = m => messages.push(m);
globalThis.fetch = async url => {
  const file = new URL(url).pathname.replace('/data/', '');
  fetched.push(file); return new Response(readFileSync(path.join(data, file)));
};
await import('../dist/search-worker.js');
await self.onmessage({ data: { type: 'init', manifest, docs, base: 'https://library.test/data/' } });
let id = 0;
const result = async state => {
  messages = []; await self.onmessage({ data: { type: 'search', id: ++id, state: { q: '', kind: 'qp', sort: 'relevance', ...state } } });
  const r = messages.find(m => m.type === 'results'); assert.ok(r, JSON.stringify(messages)); return r;
};
const expected = state => {
  const parsed = parseQuery(state.q, { kind: 'qp', ...state });
  const ids = new Set(docs.filter(d => matchesDocument(d, parsed.filters)).map(d => d.id));
  return allRows.filter(([doc, , text, status]) => ids.has(doc) && ['text', 'ocr'].includes(status) && matchText(text || '', parsed.text, state.phrase)).map(r => r[0] + ':' + r[1]).sort();
};
for (const state of [
  { q: 'mitochondria' },
  { q: 'cell membrane' },
  { q: 'cell membrane', phrase: true },
  { q: 'cells', year: '2022', paper: '1', variant: '2' },
  { q: 'mitochondria', kind: 'ms' },
  { q: 'membrane', kind: '', year: '2024' },
  { q: 'zznotabiologytermzz' }
]) {
  const r = await result(state);
  assert.deepEqual(r.results.map(h => h.doc + ':' + h.page).sort(), expected(state));
}
const countBefore = fetched.length;
const warmStart = performance.now();
const warm = await result({ q: 'mitochondria' });
const warmMs = performance.now() - warmStart;
assert.equal(fetched.length, countBefore, 'repeat search must reuse cached indexes');
assert.ok(fetched.every(f => !/2020|2021/.test(f)));
assert.ok(fetched.every(f => f.endsWith('.json.gz')), 'modern browser must fetch compressed shards');
const filesBefore = fetched.length;
assert.equal((await result({ q: '9700_m21_qp_12' })).total, 0);
assert.equal((await result({ q: '', year: '2020' })).total, 0);
assert.equal(fetched.length, filesBefore, 'excluded years must not download indexes');
assert.equal((await result({ q: '9700_s24_qp_22' })).total, 1);
// A stale catalog also cannot re-enable 2020 or 2021.
await self.onmessage({ data: { type: 'init', manifest: { ...manifest, years: [...manifest.years, { year: 2021 }] }, docs: [...docs, { id: -1, year: 2021, kind: 'qp' }], base: 'https://library.test/data/' } });
assert.equal((await result({ q: '', year: '2021' })).total, 0);
const qpRows = allRows.filter(r => docs.some(d => d.id === r[0] && d.kind === 'qp'));
const index = prepareIndex(qpRows);
let t = performance.now();
for (let i = 0; i < 5; i++) for (const row of qpRows) if (['text', 'ocr'].includes(row[3])) matchText(row[2] || '', 'mitochondria');
const scanMs = (performance.now() - t) / 5;
t = performance.now();
for (let i = 0; i < 5; i++) for (const row of candidatePages(index, 'mitochondria')) matchText(row[2] || '', 'mitochondria');
const indexedMs = (performance.now() - t) / 5;
console.log(JSON.stringify({ range: [2022, 2026], files: docs.length, papers: manifest.stats.papers, query: 'mitochondria', hits: warm.total, warm_worker_ms: +warmMs.toFixed(2), prior_scan_cpu_ms: +scanMs.toFixed(2), indexed_cpu_ms: +indexedMs.toFixed(2), default_qp_compressed_bytes: manifest.years.reduce((n, y) => n + y.shards.qp.bytes, 0), equivalence_checks: 'passed' }));
