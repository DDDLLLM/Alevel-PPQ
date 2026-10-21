export function parseQuery(raw, filters = {}) {
  const next = { ...filters };
  let text = String(raw || '').trim().toLowerCase();
  const filename = text.match(/^9700[_\s-]([mswy])(\d{2})[_\s-](qp|ms|er|gt|ci|ir|in|sp|sm)(?:[_\s-]([1-5][0-9]))?(?:\.pdf)?$/);
  if (filename) {
    next.season = filename[1]; next.year = String(2000 + Number(filename[2])); next.kind = filename[3];
    if (filename[4]) { next.paper = filename[4][0]; next.variant = filename[4][1]; }
    return { text: '', filters: next };
  }
  text = text.replace(/\b9700(?:\/([1-5][0-9]))?\b/g, (_, code) => {
    if (code) { next.paper = code[0]; next.variant = code[1]; }
    return ' ';
  });
  text = text.replace(/\b([mswy])(\d{2})\b/g, (_, season, yy) => { next.year = String(2000 + Number(yy)); next.season = season; return ' '; });
  text = text.replace(/\b(20(?:1[6-9]|2[0-6]))\b/g, (_, year) => { next.year = year; return ' '; });
  text = text.replace(/\bpaper\s*([1-5])\b/g, (_, paper) => { next.paper = paper; return ' '; });
  text = text.replace(/\b(qp|ms|er|gt|ci|ir|in|sp|sm)\b/g, (_, kind) => { next.kind = kind; return ' '; });
  if (/^[1-5][0-9]$/.test(text.trim())) { next.paper = text.trim()[0]; next.variant = text.trim()[1]; text = ''; }
  return { text: text.trim(), filters: next };
}
export function matchesDocument(doc, filters) {
  return ['year', 'season', 'paper', 'kind'].every(k => !filters[k] || String(doc[k]) === String(filters[k])) && (!filters.variant || String(filters.variant).split(',').includes(String(doc.variant)));
}
export function stem(word) {
  if (word.length > 4 && word.endsWith('ies')) return word.slice(0, -3) + 'y';
  if (word.length > 4 && word.endsWith('sses')) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith('s') && !/(ss|us|is)$/.test(word)) return word.slice(0, -1);
  return word;
}
export function matchText(text, query, phrase = false) {
  const queryWords = query.toLowerCase().match(/[a-z0-9]+/g) || [];
  if (!queryWords.length) return null;
  const words = [...text.toLowerCase().matchAll(/[a-z0-9]+/g)];
  let at = -1, score = 0;
  if (phrase) {
    outer: for (let i = 0; i <= words.length - queryWords.length; i++) {
      for (let j = 0; j < queryWords.length; j++) if (words[i + j][0] !== queryWords[j]) continue outer;
      at = words[i].index; score = 10; break;
    }
  } else {
    const needed = new Set(queryWords.map(stem));
    const found = new Set();
    for (const word of words) if (needed.has(stem(word[0]))) {
      found.add(stem(word[0])); if (at === -1) at = word.index; score++;
    }
    if (found.size !== needed.size) return null;
  }
  if (at === -1) return null;
  const start = Math.max(0, at - 90);
  return { score, snippet: (start ? '…' : '') + text.slice(start, at + 280).replace(/\s+/g, ' ').trim() + (at + 280 < text.length ? '…' : '') };
}
