import { parseQuery, matchesDocument, matchText } from './search-core.mjs';
let manifest, docs, base;
const indexes = new Map(), pending = new Map();
async function indexFor(year, id) {
  if (indexes.has(year.year)) return indexes.get(year.year);
  if (!pending.has(year.year)) pending.set(year.year, (async () => {
    const response = await fetch(new URL(year.path + '?v=' + year.sha256.slice(0, 12), base));
    if (!response.ok) throw Error('搜索索引加载失败（' + year.year + '）');
    const data = await response.json(); indexes.set(year.year, data); return data;
  })().finally(() => pending.delete(year.year)));
  const data = await pending.get(year.year);
  postMessage({ type: 'progress', id, text: '正在检索 ' + year.year + ' 年试卷…' });
  return data;
}
self.onmessage = async event => {
  const data = event.data;
  if (data.type === 'init') { ({ manifest, docs, base } = data); return; }
  if (data.type !== 'search') return;
  const { id, state } = data;
  try {
    const parsed = parseQuery(state.q, state), byId = new Map(docs.map(d => [d.id, d]));
    const documents = docs.filter(d => matchesDocument(d, parsed.filters));
    const selected = new Set(documents.map(d => d.id));
    let results = [];
    if (!parsed.text) {
      results = documents.map(d => ({ doc: d.id, page: 1, score: 0 }));
    } else {
      if (!/[a-z0-9]/i.test(parsed.text)) throw Error('请输入英文关键词、题目原文或试卷编号。');
      const years = manifest.years.filter(y => documents.some(d => d.year === y.year));
      // Bound parallel requests, keeping mobile startup small.
      for (let i = 0; i < years.length; i += 3) {
        const loaded = await Promise.all(years.slice(i, i + 3).map(y => indexFor(y, id)));
        for (const rows of loaded) for (const [doc, page, text, status] of rows) {
          if (!selected.has(doc) || !text || !['text', 'ocr'].includes(status)) continue;
          const hit = matchText(text, parsed.text, state.phrase);
          if (hit) results.push({ doc, page, source: status, ...hit });
        }
      }
    }
    const sign = state.sort === 'oldest' ? 1 : -1;
    results.sort((a, b) => (parsed.text && state.sort === 'relevance' ? b.score - a.score : 0) || sign * (byId.get(a.doc).year - byId.get(b.doc).year) || byId.get(a.doc).filename.localeCompare(byId.get(b.doc).filename) || a.page - b.page);
    const total = results.length;
    postMessage({ type: 'results', id, total, results: results.slice(0, 1000), text: parsed.text, filters: parsed.filters });
  } catch (error) { postMessage({ type: 'error', id, message: error.message || '搜索失败，请稍后重试。' }); }
};
