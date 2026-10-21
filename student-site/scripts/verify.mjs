import assert from 'node:assert/strict';
import { readFileSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { parseQuery, matchesDocument, matchText } from '../dist/search-core.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const data = process.argv[2] || path.join(root, 'student-publish');
const read = p => JSON.parse(readFileSync(path.join(data, p), 'utf8'));
const manifest = read('manifest.json'), docs = read('catalog.json'), answers = read('answers.json');
assert.equal(manifest.stats.files, docs.length);
assert.deepEqual(manifest.years.map(y => y.year), [2026, 2025, 2024, 2023, 2022]);
assert.ok(docs.every(d => d.year >= 2022 && d.year <= 2026));
assert.ok(!existsSync(path.join(data, 'index/2020.json')) && !existsSync(path.join(data, 'index/2021.json')));
for (const year of manifest.years) for (const [kind, shard] of Object.entries(year.shards)) {
  const rows = JSON.parse(gunzipSync(readFileSync(path.join(data, shard.path))));
  assert.ok(rows.every(row => docs.some(d => d.id === row[0] && d.year === year.year && d.kind === kind)));
  assert.equal(rows.length, read(year.path).filter(r => r[2] && ['text', 'ocr'].includes(r[3]) && docs.some(d => d.id === r[0] && d.kind === kind)).length);
}
assert.equal(manifest.stats.papers, docs.filter(d => d.kind === 'qp').length);
assert.equal(new Set(docs.map(d => d.filename)).size, docs.length);
for (const doc of docs) {
  assert.ok(/^[a-z0-9_]+\.pdf$/.test(doc.filename));
  assert.equal(statSync(path.join(data, doc.pdf)).size, doc.bytes);
  assert.equal(existsSync(path.join(data, doc.pdf)), true);
  for (const id of doc.related) {
    const related = docs.find(d => d.id === id); assert.ok(related);
    assert.equal(related.year, doc.year); assert.equal(related.season, doc.season);
    if (related.kind === 'ms') { assert.equal(related.paper, doc.paper); assert.equal(related.variant, doc.variant); }
  }
}
const sample = docs.find(d => d.filename === '9700_m22_qp_12.pdf');
const page = read('index/2022.json').find(([doc, page]) => doc === sample.id && page === 3);
assert.ok(matchText(page[2], 'mitochondria'));
assert.ok(matchText(page[2], 'nucleic acids', true));
assert.equal(matchText('cellulose membrane', 'cell'), null);
assert.ok(matchText('Two cells are shown', 'cell'));
assert.equal(matchText('cell wall and plasma membrane', 'cell membrane', true), null);
const parsed = parseQuery('9700_s24_qp_22.pdf', { kind: 'ms' });
assert.equal(parsed.text, '');
assert.deepEqual(docs.filter(d => matchesDocument(d, parsed.filters)).map(d => d.filename), ['9700_s24_qp_22.pdf']);
assert.equal(parseQuery('9700 mitochondria', {}).text, 'mitochondria');
assert.equal(parseQuery('9700/22 cell membrane', {}).filters.variant, '2');
assert.equal(docs.filter(d => matchesDocument(d, parseQuery('9700_m21_qp_12', {}).filters)).length, 0);
const ms = docs.find(d => sample.related.includes(d.id) && d.kind === 'ms');
assert.ok(answers[ms.id]['3']);
assert.ok(answers[ms.id]['3'].page <= ms.page_count);
for (const [id, directory] of Object.entries(answers)) {
  const doc = docs.find(d => d.id === Number(id)); assert.equal(doc.kind, 'ms');
  for (const entry of Object.values(directory)) assert.ok(Number.isInteger(entry.page) && entry.page >= 1 && entry.page <= doc.page_count);
}
console.log(JSON.stringify({ files: docs.length, papers: manifest.stats.papers, sample: sample.filename, sample_page: page[1], search: 'mitochondria', ms: ms.filename, answer_page: answers[ms.id]['3'].page, answer_directories: Object.keys(answers).length, checks: 'passed' }));
