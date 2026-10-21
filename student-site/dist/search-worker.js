import { parseQuery, matchesDocument, matchText, prepareIndex, candidatePages, inScope } from './search-core.mjs';
let manifest, docs, base, byId, latestId = 0;
const indexes = new Map(), pending = new Map();
async function indexFor(source, year, id) {
  const key = source.path + '?v=' + source.sha256.slice(0, 12);
  if (indexes.has(key)) return indexes.get(key);
  if (!pending.has(key)) pending.set(key, (async () => {
    const response = await fetch(new URL(key, base), { cache: 'force-cache' });
    if (!response.ok) throw Error('搜索索引加载失败（' + year + '）');
    const rows = source.path.endsWith('.gz')
      ? await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json()
      : await response.json();
    const index = prepareIndex(rows); indexes.set(key, index); return index;
  })().finally(() => pending.delete(key)));
  const index = await pending.get(key);
  if (id === latestId) postMessage({ type: 'progress', id, text: '正在检索 ' + year + ' 年试卷…' });
  return index;
}
self.onmessage = async event => {
  const data = event.data;
  if (data.type === 'init') {
    ({ manifest, docs, base } = data); docs = docs.filter(inScope); manifest = { ...manifest, years: manifest.years.filter(inScope) }; byId = new Map(docs.map(d => [d.id, d])); return;
  }
  if (data.type !== 'search') return;
  const { id, state } = data; latestId = id;
  try {
    const parsed = parseQuery(state.q, state);
    const documents = docs.filter(d => matchesDocument(d, parsed.filters));
    const selected = new Set(documents.map(d => d.id));
    let results = [];
    if (!parsed.text) {
      results = documents.map(d => ({ doc: d.id, page: 1, score: 0 }));
    } else {
      if (!/[a-z0-9]/i.test(parsed.text)) throw Error('请输入英文关键词、题目原文或试卷编号。');
      const sources = [];
      for (const year of manifest.years) {
        const kinds = new Set(documents.filter(d => d.year === year.year).map(d => d.kind));
        if (!kinds.size) continue;
        if (typeof DecompressionStream !== 'undefined' && year.shards && [...kinds].every(k => year.shards[k])) {
          for (const kind of kinds) sources.push({ year: year.year, source: year.shards[kind] });
        } else sources.push({ year: year.year, source: year });
      }
      for (let i = 0; i < sources.length; i += 3) {
        if (id !== latestId) return;
        const loaded = await Promise.all(sources.slice(i, i + 3).map(s => indexFor(s.source, s.year, id)));
        if (id !== latestId) return;
        for (const index of loaded) for (const [doc, page, text, status] of candidatePages(index, parsed.text)) {
          if (!selected.has(doc)) continue;
          const hit = matchText(text, parsed.text, state.phrase);
          if (hit) results.push({ doc, page, source: status, ...hit });
        }
      }
    }
    if (id !== latestId) return;
    const sign = state.sort === 'oldest' ? 1 : -1;
    results.sort((a, b) => (parsed.text && state.sort === 'relevance' ? b.score - a.score : 0) || sign * (byId.get(a.doc).year - byId.get(b.doc).year) || byId.get(a.doc).filename.localeCompare(byId.get(b.doc).filename) || a.page - b.page);
    const total = results.length;
    postMessage({ type: 'results', id, total, results: results.slice(0, 1000), text: parsed.text, filters: parsed.filters });
  } catch (error) { if (id === latestId) postMessage({ type: 'error', id, message: error.message || '搜索失败，请稍后重试。' }); }
};
