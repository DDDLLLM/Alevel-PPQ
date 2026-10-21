import { parseQuery, stem } from './search-core.mjs';
const $ = selector => document.querySelector(selector);
const S = { m: '2–3 月', s: '5–6 月', w: '10–11 月', y: '样卷' };
const K = { qp: '试题', ms: '评分标准', er: '考官报告', gt: '等级分界', ci: '实验说明', ir: '实验说明', in: '附页', sp: '样卷', sm: '样卷评分标准' };
const FILTERS = ['paper', 'variant', 'year', 'season', 'kind'];
const base = new URL(window.LIBRARY_CONFIG.dataBase, location.href).href;
let manifest, docs = [], byId = new Map(), answerMaps, worker, requestId = 0, visible = 0, results = [], queryText = '', readerState, readerSerial = 0, toastTimer;
const params = new URLSearchParams(location.search);
const state = Object.fromEntries(['q', ...FILTERS, 'sort'].map(k => [k, params.get(k) || (k === 'kind' ? 'qp' : k === 'sort' ? 'relevance' : '')]));
state.phrase = params.get('phrase') === '1';
function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
function toast(text) { $('#toast').textContent = text; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 3500); }
function safePDF(doc) { return new URL(doc.pdf, base).href; }
async function getJSON(path) { const r = await fetch(new URL(path, base)); if (!r.ok) throw Error('题库资料暂时无法加载，请稍后重试。'); return r.json(); }
function urlFor(reader) { const p = new URLSearchParams(); for (const k of ['q', ...FILTERS, 'sort']) if (state[k] || k === 'kind') p.set(k, state[k]); if (state.phrase) p.set('phrase', '1'); if (reader) { p.set('doc', reader.doc.id); p.set('page', reader.page || 1); if (reader.answer) p.set('answer', '1'); if (reader.answerLabel) p.set('question', reader.answerLabel); } return location.pathname + (p.size ? '?' + p : ''); }
function updateURL(reader) { history.replaceState(null, '', urlFor(reader)); }
const definitions = () => [
  { key: 'paper', title: 'Paper', options: [['', '全部'], ...[1, 2, 3, 4, 5].map(p => [String(p), 'Paper ' + p])], cls: 'paper-options' },
  { key: 'variant', title: 'Variant', note: '可多选', options: [['', '全部'], ...[1, 2, 3, 4, 5, 6, 7, 8, 9].filter(v => v < 4 || docs.some(d => d.variant === v)).map(v => [String(v), String(v)])] },
  { key: 'year', title: '年份', options: [['', '全部'], ...manifest.years.map(y => [String(y.year), String(y.year)])], cls: 'year-options' },
  { key: 'season', title: '考季', options: [['', '全部'], ...Object.entries(S)] },
  { key: 'kind', title: '资料类型', options: [['', '全部'], ...Object.keys(K).filter(k => docs.some(d => d.kind === k)).map(k => [k, k.toUpperCase() + ' · ' + K[k]])] }
];
function renderFilters() {
  const root = $('#filter-groups'); root.replaceChildren(); const effective = parseQuery(state.q, state).filters;
  for (const def of definitions()) {
    const group = el('section', 'filter-group'), title = el('h3', '', def.title); if (def.note) title.append(el('small', '', def.note));
    const options = el('div', 'filter-options ' + (def.cls || ''));
    for (const [value, label] of def.options) {
      const button = el('button', '', label); button.type = 'button'; button.dataset.filter = def.key; button.dataset.value = value;
      const selected = def.key === 'variant' ? (value ? String(effective.variant || '').split(',').includes(value) : !effective.variant) : String(effective[def.key] || '') === value;
      button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected));
      button.onclick = () => {
        const parsed = parseQuery($('#search').value, state);
        for (const k of FILTERS) state[k] = String(parsed.filters[k] || '');
        $('#search').value = parsed.text;
        if (def.key === 'variant' && value) { const chosen = new Set(state.variant.split(',').filter(Boolean)); chosen.has(value) ? chosen.delete(value) : chosen.add(value); state.variant = [...chosen].sort().join(','); }
        else state[def.key] = value;
        runSearch();
      }; options.append(button);
    } group.append(title, options); root.append(group);
  }
}
function renderChips(filters) {
  const root = $('#active-filters'); root.replaceChildren();
  for (const def of definitions()) if (filters[def.key]) {
    const label = def.key === 'season' ? S[filters.season] : def.key === 'kind' ? K[filters.kind] : filters[def.key].replaceAll(',', '、');
    const button = el('button', '', def.title + ' ' + label); button.append(el('span', '', '×')); button.setAttribute('aria-label', '取消' + def.title + '筛选');
    button.onclick = () => { state[def.key] = ''; const parsed = parseQuery(state.q, state); if (parsed.filters[def.key]) { state.q = parsed.text; for (const k of FILTERS) if (k !== def.key) state[k] = String(parsed.filters[k] || ''); $('#search').value = state.q; } runSearch(); }; root.append(button);
  }
}
function runSearch() {
  if (!worker) return;
  state.q = $('#search').value.trim(); state.phrase = $('#phrase').checked; state.sort = $('#sort').value;
  renderFilters(); updateURL(); const parsed = parseQuery(state.q, state); renderChips(parsed.filters);
  requestId++; $('#load-status').textContent = parsed.text ? '正在搜索题库，首次搜索需要加载索引…' : '正在筛选试卷…'; $('#load-status').setAttribute('aria-busy', 'true');
  $('#results').replaceChildren(); $('#more-results').hidden = true; $('#result-end').hidden = true;
  worker.postMessage({ type: 'search', id: requestId, state: { ...state } });
}
function excerpt(text) {
  const out = el('p', 'result-excerpt');
  const terms = new Set((queryText.toLowerCase().match(/[a-z0-9]+/g) || []).map(stem));
  let last = 0; for (const word of text.matchAll(/[a-z0-9]+/ig)) if (terms.has(stem(word[0].toLowerCase()))) { out.append(document.createTextNode(text.slice(last, word.index)), el('mark', '', word[0])); last = word.index + word[0].length; }
  out.append(document.createTextNode(text.slice(last))); out.lang = 'en'; return out;
}
function fileIcon(kind) { const n = el('div', 'file-icon'); n.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h8l4 4v12H6Z"/><path d="M14 4v5h4M9 13h6M9 16h6"/></svg>'; n.append(el('span', '', kind.toUpperCase())); return n; }
function relatedMS(doc) { return doc.related.map(id => byId.get(id)).find(d => d?.kind === 'ms'); }
function renderMore() {
  const root = $('#results'); const end = Math.min(visible + 24, results.length);
  for (const hit of results.slice(visible, end)) {
    const doc = byId.get(hit.doc); const card = el('article', 'result-card'); card.dataset.doc = doc.id; card.dataset.page = hit.page;
    const content = el('div', 'result-content'), meta = el('p', 'result-meta'); meta.append(el('span', 'result-year', String(doc.year)), el('span', '', S[doc.season]), el('span', 'meta-divider')); if (doc.paper) meta.append(el('span', '', 'Paper ' + doc.paper + ' · Variant ' + doc.variant)); meta.append(el('span', '', K[doc.kind]));
    const heading = el('h3'), link = el('button', '', doc.kind === 'qp' ? `Biology · Paper ${doc.paper} · ${K[doc.kind]}` : `Biology · ${K[doc.kind]}`); link.onclick = () => openReader(doc.id, hit.page); heading.append(link);
    content.append(meta, heading, el('div', 'filename', doc.filename));
    if (hit.snippet) { content.append(el('p', 'result-location', `PDF 第 ${hit.page} 页${hit.source === 'ocr' ? ' · OCR 文字' : ' · 页面匹配'}`), excerpt(hit.snippet)); }
    const tags = el('div', 'result-tags'); tags.append(el('span', '', doc.page_count + ' 页')); if (doc.kind === 'qp') tags.append(el('span', relatedMS(doc) ? 'answer-tag' : '', relatedMS(doc) ? '含对应评分标准' : '评分标准尚未收录')); if (doc.status !== 'ready') tags.append(el('span', '', '部分页面待 OCR')); content.append(tags);
    const open = el('button', 'result-open', '阅读' + (doc.kind === 'qp' ? '试卷' : '资料')); open.append(el('span', '', '↗')); open.onclick = () => openReader(doc.id, hit.page);
    card.append(fileIcon(doc.kind), content, open); root.append(card);
  }
  visible = end; $('#more-results').hidden = visible >= results.length; $('#result-end').hidden = visible < results.length || !results.length;
}
function showEmpty() { const box = el('div', 'empty'); box.innerHTML = '<svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="17" cy="17" r="10"/><path d="m25 25 8 8"/></svg>'; box.append(el('h3', '', '这里暂时没有匹配的内容'), el('p', '', '试试更短的英文关键词，或放宽年份与 Paper 筛选。当前题库实际收录 2020–2026 年资料，部分待 OCR 页面不能全文搜索。')); const reset = el('button', '', '清空搜索与筛选'); reset.onclick = resetAll; box.append(reset); $('#results').append(box); }
function resetAll() { for (const k of ['q', ...FILTERS]) state[k] = k === 'kind' ? 'qp' : ''; $('#search').value = ''; $('#phrase').checked = false; runSearch(); }
function showInfo(title, content) { $('#info-title').textContent = title; $('#info-content').replaceChildren(content); $('#info-dialog').showModal(); }
function showCoverage() {
  if (!manifest) return; const root = el('div'); root.append(el('p', '', `当前共 ${manifest.stats.files} 个文件、${manifest.stats.papers} 份试卷、${manifest.stats.pages.toLocaleString()} 页。部分年份或考季可能未收齐，以实际文件为准。`));
  const table = el('table'), head = el('thead'), hr = el('tr'); for (const name of ['年份', '试题 QP', '答案 MS', '其他资料', '待完善']) hr.append(el('th', '', name)); head.append(hr); table.append(head); const body = el('tbody');
  for (const y of manifest.years) { const row = el('tr'), ds = docs.filter(d => d.year === y.year); const qp = ds.filter(d => d.kind === 'qp').length, ms = ds.filter(d => d.kind === 'ms').length; for (const value of [y.year, qp, ms, ds.length - qp - ms, ds.filter(d => d.status !== 'ready').length]) row.append(el('td', '', String(value))); body.append(row); } table.append(body); root.append(table, el('h3', '', '关于文字搜索'), el('p', '', '搜索使用已提取的原生文字和已有 OCR 文字；图表、手写文字和待 OCR 页面可能无法命中。结果按 PDF 页定位，题号与答案以原卷为准。'), el('p', '', '资料更新：' + new Date(manifest.generated_at).toLocaleDateString('zh-CN'))); showInfo('题库收录情况', root);
}
function showHelp() { const root = el('div'); for (const [title, text] of [ ['搜索题目', '输入 mitochondria、cell membrane 等英文关键词，默认匹配全部关键词。勾选“连续原文匹配”可查找相邻的原文词组。也可以输入 9700_s24_qp_22、9700/22 或 9700 s24。'], ['筛选试卷', '左侧可按 Paper、Variant、年份、考季和资料类型筛选。Variant 可多选。手机上点击“筛选”展开选项。'], ['阅读与答案', '点击结果进入原 PDF 阅读器，搜索结果会跳转到命中的 PDF 页。点击“显示答案”可同时打开同年份、考季、Paper 和 Variant 的评分标准。两栏可以分别翻页和缩放；手机上上下排列。'], ['按题号定位答案', '答案栏打开后可输入 4、4(a) 等题号。已识别到可靠 MS 目录的文件可以自动跳转，无法识别时请手动翻阅原卷。'], ['分享与更新', '“复制链接”保留当前试卷、页码和答案显示状态。题库由老师在本机整理后发布更新；学生无需安装软件或登录。'] ]) root.append(el('h3', '', title), el('p', '', text)); showInfo('使用帮助', root); }

let pdfModule;
async function getPDFModule() { if (!pdfModule) pdfModule = import('./vendor/pdf.mjs').then(m => { m.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.mjs', import.meta.url).href; return m; }); return pdfModule; }
class PDFPanel {
  constructor(root) { this.root = root; this.serial = 0; this.zoom = 1; this.page = 1; this.visiblePages = new Set(); }
  destroy() { this.serial++; this.observer?.disconnect(); this.resizeObserver?.disconnect(); clearTimeout(this.resizeTimer); for (const p of this.pages || []) { p.task?.cancel(); p.textTask?.cancel(); } this.loading?.destroy(); this.pdf?.destroy(); this.pdf = null; this.root.replaceChildren(); }
  async open(doc, initialPage = 1) {
    this.destroy(); const serial = this.serial; this.doc = doc; this.zoom = 1; this.pages = []; this.visiblePages = new Set();
    const toolbar = el('div', 'panel-toolbar'), label = el('span', 'panel-label', K[doc.kind] + ' · ' + String(doc.paper || '').padEnd(1));
    const prev = el('button', '', '‹'), next = el('button', '', '›'), page = el('input'); page.type = 'number'; page.min = 1; page.max = doc.page_count; page.value = initialPage; page.setAttribute('aria-label', K[doc.kind] + ' PDF 页码'); prev.setAttribute('aria-label', K[doc.kind] + ' 上一页'); next.setAttribute('aria-label', K[doc.kind] + ' 下一页');
    const total = el('small', '', '/ ' + doc.page_count), minus = el('button', '', '−'), plus = el('button', '', '+'), zoom = el('span', 'zoom-value', '适宽'), original = el('a', '', '原 PDF ↗'); original.href = safePDF(doc) + '#page=' + initialPage; original.target = '_blank'; original.rel = 'noopener'; minus.setAttribute('aria-label', K[doc.kind] + ' 缩小'); plus.setAttribute('aria-label', K[doc.kind] + ' 放大');
    toolbar.append(label, prev, page, total, next, minus, zoom, plus, original); this.counter = page; this.original = original;
    const scroller = el('div', 'pdf-scroll'), message = el('div', 'panel-message', '正在加载原 PDF…'); scroller.append(message); this.scroller = scroller; this.root.append(toolbar, scroller);
    const navigate = n => { if (Number.isInteger(n) && n >= 1 && n <= doc.page_count) this.go(n); else { page.value = this.page; toast('页码超出范围'); } };
    prev.onclick = () => navigate(this.page - 1); next.onclick = () => navigate(this.page + 1); page.onchange = () => navigate(Number(page.value)); page.onkeydown = e => { if (e.key === 'Enter') page.blur(); };
    const setZoom = z => { const current = this.page; this.zoom = Math.min(2.5, Math.max(.5, z)); zoom.textContent = Math.round(this.zoom * 100) + '%'; this.resize(); this.go(current); minus.disabled = this.zoom <= .5; plus.disabled = this.zoom >= 2.5; };
    minus.onclick = () => setZoom(this.zoom - .25); plus.onclick = () => setZoom(this.zoom + .25);
    try {
      const m = await getPDFModule(); if (serial !== this.serial) return;
      const loading = m.getDocument({ url: safePDF(doc), cMapUrl: new URL('./vendor/cmaps/', import.meta.url).href, cMapPacked: true, standardFontDataUrl: new URL('./vendor/standard_fonts/', import.meta.url).href, wasmUrl: new URL('./vendor/wasm/', import.meta.url).href, isEvalSupported: false }); this.loading = loading;
      loading.onProgress = p => { if (serial === this.serial && message.isConnected) message.textContent = p.total ? '正在加载原 PDF · ' + Math.min(100, Math.round(p.loaded / p.total * 100)) + '%' : '正在加载原 PDF…'; };
      const pdf = await loading.promise; if (serial !== this.serial) { pdf.destroy(); return; } this.pdf = pdf; scroller.replaceChildren();
      const first = await pdf.getPage(1), firstVP = first.getViewport({ scale: 1 });
      for (let n = 1; n <= pdf.numPages; n++) { const sheet = el('div', 'pdf-page'); sheet.dataset.page = n; sheet.setAttribute('aria-label', K[doc.kind] + ' 第 ' + n + ' 页'); sheet.append(el('span', 'page-number', '第 ' + n + ' 页')); scroller.append(sheet); this.pages.push({ n, sheet, width: firstVP.width, height: firstVP.height }); }
      this.observer = new IntersectionObserver(entries => {
        for (const entry of entries) { const p = this.pages[Number(entry.target.dataset.page) - 1]; if (!p) continue; if (entry.isIntersecting) { this.visiblePages.add(p.n); this.render(p, m); } else { this.visiblePages.delete(p.n); if (p.rendered) { p.task?.cancel(); p.textTask?.cancel(); p.sheet.querySelectorAll('canvas,.textLayer').forEach(n => n.remove()); p.sheet.classList.remove('ready'); p.rendered = false; p.scale = null; } } }
      }, { root: scroller, rootMargin: '400px 0px' });
      this.resize(); for (const p of this.pages) this.observer.observe(p.sheet);
      let frame = false; scroller.onscroll = () => { if (frame) return; frame = true; requestAnimationFrame(() => { frame = false; const hit = this.pages.find(p => p.sheet.offsetTop + p.sheet.offsetHeight > scroller.scrollTop + 30) || this.pages.at(-1); if (hit) { this.page = hit.n; page.value = hit.n; original.href = safePDF(doc) + '#page=' + hit.n; if (this === questionPanel && readerState) readerState.page = hit.n; } }); };
      this.resizeObserver = new ResizeObserver(() => { clearTimeout(this.resizeTimer); this.resizeTimer = setTimeout(() => { if (serial !== this.serial) return; const current = this.page; this.resize(); this.go(current); for (const n of this.visiblePages) this.render(this.pages[n - 1], m); }, 100); }); this.resizeObserver.observe(scroller);
      this.go(initialPage);
    } catch (error) {
      if (serial !== this.serial) return;
      scroller.replaceChildren(); const fail = el('div', 'panel-message', 'PDF 暂时无法加载，请检查网络或打开原文件。'); const retry = el('button', '', '重试'); retry.onclick = () => this.open(doc, this.page || initialPage); const link = el('a', '', '在新窗口打开原 PDF ↗'); link.href = safePDF(doc); link.target = '_blank'; link.rel = 'noopener'; fail.append(el('br'), retry, link); scroller.append(fail);
    }
  }
  resize() {
    if (!this.scroller || !this.pages?.length || !this.scroller.clientWidth) return;
    const available = Math.max(100, this.scroller.clientWidth - (matchMedia('(max-width:650px)').matches ? 20 : 32));
    for (const p of this.pages) { const width = available * this.zoom; p.sheet.style.width = width + 'px'; p.sheet.style.height = width * p.height / p.width + 'px'; if (p.rendered && Math.abs((p.scale || 0) - width / p.width) > .01) { p.task?.cancel(); p.textTask?.cancel(); p.sheet.querySelectorAll('canvas,.textLayer').forEach(n => n.remove()); p.rendered = false; } }
  }
  go(number) { const p = this.pages?.[number - 1]; if (!p) return; this.page = number; this.scroller.scrollTop = p.sheet.offsetTop - 16; this.counter.value = number; this.original.href = safePDF(this.doc) + '#page=' + number; if (this === questionPanel && readerState) readerState.page = number; }
  async render(p, m) {
    if (p.rendered || p.busy || !this.pdf) return; p.busy = true; const serial = this.serial;
    try {
      const page = await this.pdf.getPage(p.n); if (serial !== this.serial) return;
      const natural = page.getViewport({ scale: 1 }); p.width = natural.width; p.height = natural.height; this.resize();
      const scale = p.sheet.clientWidth / natural.width, viewport = page.getViewport({ scale }); p.scale = scale;
      const canvas = el('canvas'), ratio = Math.min(devicePixelRatio || 1, 1.5); canvas.width = Math.floor(viewport.width * ratio); canvas.height = Math.floor(viewport.height * ratio); canvas.setAttribute('aria-hidden', 'true'); p.sheet.prepend(canvas); p.sheet.style.setProperty('--scale-factor', scale);
      const task = page.render({ canvasContext: canvas.getContext('2d'), viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] }); p.task = task; await task.promise;
      if (serial !== this.serial || !canvas.isConnected) return;
      const layer = el('div', 'textLayer'); p.sheet.append(layer); const content = await page.getTextContent(); if (serial !== this.serial || !layer.isConnected) return;
      p.textTask = new m.TextLayer({ textContentSource: content, container: layer, viewport }); await p.textTask.render(); p.rendered = true; p.sheet.classList.add('ready');
    } catch (error) { if (serial === this.serial && error.name !== 'RenderingCancelledException' && error.name !== 'AbortException') { p.sheet.querySelector('.page-number').textContent = '本页显示失败，请打开原 PDF'; } }
    finally { p.busy = false; }
  }
}
const questionPanel = new PDFPanel($('#question-panel')), answerPanel = new PDFPanel($('#answer-panel'));
async function openReader(id, page = 1, showAnswer = false, answerLabel = '') {
  const doc = byId.get(Number(id)); if (!doc) { toast('找不到这份试卷'); return; } const serial = ++readerSerial;
  const ms = doc.kind === 'qp' ? relatedMS(doc) : null; page = Math.min(doc.page_count, Math.max(1, Number(page) || 1));
  readerState = { doc, page, ms, answer: false, answerLabel };
  $('#reader-meta').textContent = `${doc.year} · ${S[doc.season]}${doc.paper ? ' · Paper ' + doc.paper + ' / Variant ' + doc.variant : ''}`;
  $('#reader-title').textContent = doc.filename; $('#answer-toggle').hidden = !ms; $('#answer-toggle').textContent = '显示答案'; $('#answer-toggle').setAttribute('aria-pressed', 'false'); $('#answer-panel').hidden = true; $('#answer-form').hidden = true; $('#reader-grid').classList.remove('with-answer'); $('#reader-note').textContent = doc.kind === 'qp' ? ms ? '已关联同套试卷评分标准 · 试题与答案分别翻页' : '本卷评分标准尚未收录' : K[doc.kind] + ' · 原始 PDF'; $('#answer-label').value = answerLabel;
  if (!$('#reader-dialog').open) $('#reader-dialog').showModal(); updateURL(readerState); answerPanel.destroy(); questionPanel.open(doc, page);
  if (showAnswer && ms) await toggleAnswer(true);
  if (answerLabel && serial === readerSerial && readerState?.answer) locateAnswer(answerLabel);
}
async function toggleAnswer(force) {
  if (!readerState?.ms) return;
  const show = force === undefined ? !readerState.answer : force; readerState.answer = show;
  $('#answer-panel').hidden = !show; $('#reader-grid').classList.toggle('with-answer', show); $('#answer-toggle').textContent = show ? '收起答案' : '显示答案'; $('#answer-toggle').setAttribute('aria-pressed', String(show)); $('#answer-form').hidden = !show;
  if (show) { answerPanel.open(readerState.ms, 1); if (!answerMaps) { try { answerMaps = await getJSON('answers.json'); } catch { toast('答案目录暂时无法加载，可手动翻阅评分标准。'); } } }
  else answerPanel.destroy(); updateURL(readerState);
}
async function locateAnswer(value) {
  if (!readerState?.ms) return;
  const label = value.toLowerCase().replace(/\s/g, ''); if (!/^\d{1,2}(?:\([a-z0-9]+\))*$/.test(label)) { toast('请输入题号，例如 4 或 4(a)'); return; }
  try { if (!answerMaps) answerMaps = await getJSON('answers.json'); const entry = answerMaps[readerState.ms.id]?.[label]; if (entry) { if (!answerPanel.pages?.length) await new Promise(resolve => { const start = Date.now(); const t = setInterval(() => { if (answerPanel.pages?.length || Date.now() - start > 15000) { clearInterval(t); resolve(); } }, 100); }); answerPanel.go(entry.page); $('#reader-note').textContent = `自动定位 · 第 ${label} 题 · MS 第 ${entry.page} 页，请核对原卷`; readerState.answerLabel = label; updateURL(readerState); } else { $('#reader-note').textContent = `尚未可靠识别第 ${label} 题的位置，请在评分标准中手动查阅。`; toast('本题尚无可靠答案定位'); } }
  catch { toast('答案目录加载失败，请稍后重试。'); }
}
function closeReader() { readerSerial++; questionPanel.destroy(); answerPanel.destroy(); readerState = null; $('#reader-dialog').close(); updateURL(); }
$('#search-form').onsubmit = e => { e.preventDefault(); runSearch(); };
$('#phrase').onchange = () => runSearch(); $('#sort').onchange = () => runSearch(); $('#reset-filters').onclick = () => { const parsed = parseQuery(state.q, state); for (const k of FILTERS) state[k] = k === 'kind' ? 'qp' : ''; $('#search').value = parsed.text; runSearch(); };
for (const b of document.querySelectorAll('[data-query]')) b.onclick = () => { $('#search').value = b.dataset.query; runSearch(); };
$('#more-results').onclick = renderMore;
$('#mobile-filter-toggle').onclick = e => { const open = $('#filters').classList.toggle('visible'); e.currentTarget.setAttribute('aria-expanded', String(open)); if (open) $('#filters').scrollIntoView({ block: 'start', behavior: 'smooth' }); };
$('#coverage-button').onclick = showCoverage; $('#help-button').onclick = showHelp; $('#close-info').onclick = () => $('#info-dialog').close(); $('#close-reader').onclick = closeReader; $('#reader-dialog').addEventListener('cancel', e => { e.preventDefault(); closeReader(); }); $('#answer-toggle').onclick = () => toggleAnswer(); $('#answer-form').onsubmit = e => { e.preventDefault(); locateAnswer($('#answer-label').value); };
$('#share-reader').onclick = async () => { if (!readerState) return; updateURL(readerState); try { await navigator.clipboard.writeText(location.href); toast('已复制试卷链接'); } catch { toast('请从浏览器地址栏复制当前链接'); } };
document.addEventListener('keydown', e => { if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !$('#reader-dialog').open && !$('#info-dialog').open) { e.preventDefault(); $('#search').focus(); } });
$('#search').value = state.q; $('#phrase').checked = state.phrase; $('#sort').value = state.sort;
async function boot() {
  try {
    [manifest, docs] = await Promise.all([getJSON('manifest.json'), getJSON('catalog.json')]); byId = new Map(docs.map(d => [d.id, d]));
    $('#stat-papers').textContent = manifest.stats.papers; $('#stat-years').textContent = manifest.years.length; $('#sidebar-range').textContent = `${Math.min(...manifest.years.map(y => y.year))}–${Math.max(...manifest.years.map(y => y.year))} · ${manifest.stats.files} 个文件`;
    worker = new Worker(new URL('./search-worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = e => { const m = e.data; if (m.id !== requestId) return; if (m.type === 'progress') { $('#load-status').textContent = m.text; return; } $('#load-status').setAttribute('aria-busy', 'false'); if (m.type === 'error') { $('#load-status').textContent = m.message; return; } if (m.type !== 'results') return; results = m.results; visible = 0; queryText = m.text; $('#results').replaceChildren(); $('#results-title').firstChild.textContent = queryText ? '搜索结果 ' : '浏览试卷 '; $('#result-eyebrow').textContent = queryText ? 'SEARCH THE LIBRARY' : 'THE PAPER LIBRARY'; $('#result-count').textContent = String(m.total); $('#load-status').textContent = m.total > results.length ? `找到 ${m.total} 个页面，显示前 ${results.length} 个结果。可以进一步筛选。` : ''; renderChips(m.filters); renderMore(); if (!m.total) showEmpty(); };
    worker.onerror = () => { $('#load-status').textContent = '搜索程序加载失败，请刷新页面重试。'; };
    worker.postMessage({ type: 'init', manifest, docs, base }); runSearch();
    if (params.get('doc')) openReader(params.get('doc'), params.get('page') || 1, params.get('answer') === '1', params.get('question') || '');
  } catch (error) { const root = $('#load-status'); root.textContent = error.message + ' '; const retry = el('button', '', '重新加载'); retry.onclick = boot; root.append(retry); }
}
boot();
