import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SEASONS = {'m': '2–3月', 's': '5–6月', 'w': '10–11月', 'y': '样卷'}
TYPES = {'qp': '试题', 'ms': '评分标准', 'er': '考官报告', 'gt': '等级分界', 'ci': '实验说明', 'ir': '实验说明（旧格式）', 'in': '附页', 'sp': '样卷', 'sm': '样卷评分标准'}
STATUSES = {'ready': '文字已索引', 'partial': '部分页面待 OCR', 'needs_ocr': '待 OCR', 'error': '解析失败', 'pending': '待索引'}


def metadata(name):
    name = Path(name).name.lower()
    # Official convention and the historical PaperSC download convention.
    m = re.fullmatch(r'9700_([mswy])(\d{2})_(qp|ms|er|gt|ci|ir|in|sp|sm)(?:_([1-5][0-9]))?\.pdf', name)
    if not m:
        old = re.fullmatch(r'9700_([mswy])(\d{2})_([0-5][0-9])_(qp|ms|er|gt|ci|ir|in|sp|sm)\.pdf', name)
        if old:
            s, y, pv, typ = old.groups()
            name = f'9700_{s}{y}_{typ}' + (f'_{pv}' if pv != '00' else '') + '.pdf'
            return metadata(name)
        raise ValueError('文件名不符合 9700_s24_qp_12.pdf 或 9700_s24_er.pdf 格式')
    season, yy, typ, pv = m.groups()
    year = 2000 + int(yy)
    if not 2016 <= year <= 2026:
        raise ValueError('仅收录 2016–2026 年的 9700 文件')
    if typ in ('qp', 'ms', 'sp', 'sm', 'ci', 'ir', 'in') and not pv:
        raise ValueError('该文件类型需要 Paper 和 Variant 编号')
    return dict(filename=name, year=year, season=season, kind=typ,
                paper=int(pv[0]) if pv else 0, variant=int(pv[1]) if pv else 0)


class Library:
    def __init__(self, directory=None):
        self.home = Path(directory or os.environ.get('BIOLOGY_DATA', ROOT / 'data')).resolve()
        for folder in ('pdfs', 'cache', 'logs', 'quarantine'):
            (self.home / folder).mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / 'library.sqlite3'
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents(
              id INTEGER PRIMARY KEY, filename TEXT UNIQUE NOT NULL, sha256 TEXT UNIQUE NOT NULL,
              year INTEGER NOT NULL CHECK(year BETWEEN 2016 AND 2026), season TEXT NOT NULL,
              kind TEXT NOT NULL, paper INTEGER NOT NULL, variant INTEGER NOT NULL,
              page_count INTEGER DEFAULT 0, searchable_pages INTEGER DEFAULT 0,
              status TEXT DEFAULT 'pending', error TEXT DEFAULT '',
              added_at TEXT DEFAULT CURRENT_TIMESTAMP, indexed_at TEXT);
            CREATE TABLE IF NOT EXISTS sources(
              id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id), source TEXT NOT NULL,
              url TEXT NOT NULL, original_id TEXT DEFAULT '', original_name TEXT DEFAULT '',
              fetched_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(doc_id,source,url));
            CREATE TABLE IF NOT EXISTS pages(
              doc_id INTEGER REFERENCES documents(id), page INTEGER, text TEXT,
              lines_json TEXT, status TEXT, PRIMARY KEY(doc_id,page));
            CREATE TABLE IF NOT EXISTS units(
              id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id), label TEXT,
              confidence TEXT, page_start INTEGER, page_end INTEGER, text TEXT,
              parts_json TEXT, ms_doc_id INTEGER, ms_page INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(text, content='units', content_rowid='id', tokenize='porter unicode61');
            CREATE TRIGGER IF NOT EXISTS units_ai AFTER INSERT ON units BEGIN
              INSERT INTO search_fts(rowid,text) VALUES(new.id,new.text); END;
            CREATE TRIGGER IF NOT EXISTS units_ad AFTER DELETE ON units BEGIN
              INSERT INTO search_fts(search_fts,rowid,text) VALUES('delete',old.id,old.text); END;
            CREATE TABLE IF NOT EXISTS corrections(doc_id INTEGER PRIMARY KEY REFERENCES documents(id),
              spans_json TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS catalog(source TEXT, original_id TEXT, filename TEXT,
              url TEXT, metadata_json TEXT, state TEXT DEFAULT 'discovered', error TEXT DEFAULT '',
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(source,original_id));
            CREATE TABLE IF NOT EXISTS source_runs(id INTEGER PRIMARY KEY, source TEXT, state TEXT,
              details TEXT, checked_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS doc_filters ON documents(year,season,paper,variant,kind);
            CREATE INDEX IF NOT EXISTS unit_doc ON units(doc_id);
            PRAGMA user_version=1;
            ''')

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=60)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def pdf_path(self, doc):
        return self.home / 'pdfs' / f"{doc['sha256']}.pdf"

    def document(self, doc_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
        if row is None:
            raise ValueError('文件不存在')
        return dict(row)

    def import_pdf(self, path, filename=None, source='local', url='', original_id=''):
        path = Path(path)
        meta = metadata(filename or path.name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with fitz.open(path) as pdf:
            if not pdf.is_pdf or pdf.needs_pass or not 0 < len(pdf) <= 1000:
                raise ValueError('PDF 无效、加密或页数超限')
            first = pdf[0].get_text()
            codes = re.findall(r'\b(\d{4})\s*/\s*\d{1,2}\b', first)
            if codes and '9700' not in codes:
                raise ValueError('PDF 内部科目编号与 9700 不符')
            component = re.search(r'\b9700\s*/\s*([1-5][0-9])\b', first)
            if component and meta['paper'] and component[1] != f"{meta['paper']}{meta['variant']}":
                raise ValueError('PDF 内部 Paper/Variant 与文件名不符')
            date = re.search(r'(February\s*/\s*March|May\s*/\s*June|October\s*/\s*November|March|June|November)\s+(20\d{2})', first, re.I)
            if date and meta['season'] != 'y':
                month = date[1].lower()
                season = 'm' if 'march' in month else ('s' if 'june' in month else 'w')
                if season != meta['season'] or int(date[2]) != meta['year']:
                    raise ValueError('PDF 内部年份或考季与文件名不符')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM documents WHERE sha256=? OR filename=?', (digest, meta['filename'])).fetchall()
            if old:
                old = old[0]
                if old['sha256'] != digest or old['filename'] != meta['filename']:
                    target = self.home / 'quarantine' / f'{digest}_{meta["filename"]}'
                    if not target.exists():
                        shutil.copyfile(path, target)
                    raise ValueError('同名异内容或同内容异元数据：已放入 quarantine，未覆盖原记录')
                doc_id = old['id']
                duplicate = True
            else:
                target = self.home / 'pdfs' / f'{digest}.pdf'
                if not target.exists():
                    fd, temp = tempfile.mkstemp(dir=target.parent, suffix='.part')
                    os.close(fd)
                    try:
                        shutil.copyfile(path, temp)
                        os.replace(temp, target)
                    finally:
                        Path(temp).unlink(missing_ok=True)
                doc_id = db.execute('INSERT INTO documents(filename,sha256,year,season,kind,paper,variant) VALUES(?,?,?,?,?,?,?)',
                    (meta['filename'], digest, meta['year'], meta['season'], meta['kind'], meta['paper'], meta['variant'])).lastrowid
                duplicate = False
            db.execute('INSERT OR IGNORE INTO sources(doc_id,source,url,original_id,original_name) VALUES(?,?,?,?,?)',
                       (doc_id, source, url or 'local:' + (filename or path.name), str(original_id), filename or path.name))
        if not duplicate or self.document(doc_id)['status'] in ('pending', 'error'):
            self.index_document(doc_id)
        return {'id': doc_id, 'filename': meta['filename'], 'duplicate': duplicate, 'status': self.document(doc_id)['status']}

    def index_document(self, doc_id, ocr=False):
        doc = self.document(doc_id)
        with self.connect() as db:
            prior_ocr = {r['page']: dict(r) for r in db.execute("SELECT * FROM pages WHERE doc_id=? AND status='ocr'", (doc_id,))}
        try:
            pages = []
            with fitz.open(self.pdf_path(doc)) as pdf:
                for number, page in enumerate(pdf, 1):
                    raw = page.get_text('dict', sort=True)
                    lines = []
                    for block in raw['blocks']:
                        for line in block.get('lines', []):
                            txt = ''.join(s['text'] for s in line['spans']).strip()
                            if txt:
                                lines.append({'text': txt, 'x': round(line['bbox'][0], 1), 'y': round(line['bbox'][1], 1),
                                              'bold': any(s['flags'] & 16 for s in line['spans'])})
                    body = [l for l in lines if 55 < l['y'] < page.rect.height - 65 and not re.fullmatch(r'\d+', l['text'])]
                    meaningful = sum(len(re.findall('[A-Za-z]', l['text'])) for l in body)
                    text = '\n'.join(l['text'] for l in lines)
                    body_text='\n'.join(l['text'] for l in body)
                    remainder=re.sub(r'Question\s+\d+\s+(?:starts|continues) on page\s+\d+','',body_text,flags=re.I)
                    # Empty answer space / turn-over notices do not need OCR. A scan
                    # remains pending because its page contains an image.
                    blank = 'BLANK PAGE' in text.upper() or (not page.get_images() and not re.search('[A-Za-z]',remainder))
                    answer_table = doc['kind']=='ms' and doc['paper']==1 and 'Question' in text and 'Answer' in text and len(re.findall(r'\b[ABCD]\b',body_text)) >= 5
                    status = 'blank' if blank else ('text' if meaningful >= 45 or answer_table else 'needs_ocr')
                    if status == 'needs_ocr' and not ocr and number in prior_ocr:
                        previous = prior_ocr[number]
                        text = previous['text']
                        lines = json.loads(previous['lines_json'])
                        status = 'ocr'
                    if status == 'needs_ocr' and ocr:
                        tp = page.get_textpage_ocr(language='eng', dpi=200, full=True)
                        text = page.get_text(textpage=tp, sort=True)
                        lines = [{'text': s, 'x': 0, 'y': 0, 'bold': False} for s in text.splitlines() if s.strip()]
                        status = 'ocr' if len(re.findall('[A-Za-z]', text)) >= 45 else 'needs_ocr'
                    pages.append({'page': number, 'text': text, 'lines': lines, 'status': status})
            searchable = sum(p['status'] in ('text', 'ocr') for p in pages)
            missing = sum(p['status'] == 'needs_ocr' for p in pages)
            status = ('partial' if searchable else 'needs_ocr') if missing else 'ready'
            with self.connect() as db:
                db.execute('DELETE FROM pages WHERE doc_id=?', (doc_id,))
                db.executemany('INSERT INTO pages VALUES(?,?,?,?,?)', [(doc_id, p['page'], p['text'], json.dumps(p['lines']), p['status']) for p in pages])
                db.execute('UPDATE documents SET page_count=?,searchable_pages=?,status=?,error=?,indexed_at=CURRENT_TIMESTAMP WHERE id=?',
                           (len(pages), searchable, status, '', doc_id))
                self._build_units(db, doc, pages)
        except Exception as exc:
            # Keep earlier text when a requested OCR backend fails, but never claim success.
            with self.connect() as db:
                db.execute('UPDATE documents SET status=\'error\',error=? WHERE id=?', (str(exc), doc_id))
            raise

    def _auto_spans(self, doc, pages):
        if doc['kind'] != 'qp':
            return []
        candidates = []
        for p in pages:
            if p['page'] == 1 or p['status'] != 'text':
                continue
            for idx, line in enumerate(p['lines'], 1):
                # Cambridge main question numbers in the left gutter; omit page numbers and footer codes.
                m = re.match(r'^(\d{1,2})(?:\s+([A-Za-z(].*)|\s*)$', line['text'])
                # Many older Cambridge embedded fonts omit the PDF bold flag. Require
                # a gutter number paired with question text at the same baseline instead.
                paired = bool(m and m[2]) or any(65 <= other['x'] <= 100 and abs(other['y']-line['y']) < 2
                    and re.match(r'[A-Za-z(]',other['text']) for other in p['lines'])
                if m and 40 <= line['x'] <= 56 and 55 < line['y'] < 780 and paired:
                    candidates.append((int(m[1]), p['page'], idx))
        nums = [c[0] for c in candidates]
        # Any gap, repeated number or unexpected count rejects the entire automatic directory.
        if nums != list(range(1, len(nums) + 1)) or len(nums) < 2 or (doc['paper'] == 1 and len(nums) != 40) or (doc['paper'] != 1 and len(nums) > 20):
            return []
        spans = []
        for i, (n, p, line) in enumerate(candidates):
            if i + 1 < len(candidates):
                _, ep, el = candidates[i + 1]
                el -= 1
                if el == 0:
                    ep -= 1
                    el = len(pages[ep-1]['lines'])
            else:
                ep = max(x['page'] for x in pages if x['status'] != 'blank')
                el = len(pages[ep-1]['lines'])
            spans.append(dict(label=str(n), page_start=p, line_start=line, page_end=ep, line_end=el, confidence='automatic'))
        return spans

    def _build_units(self, db, doc, pages):
        row = db.execute('SELECT spans_json FROM corrections WHERE doc_id=?', (doc['id'],)).fetchone()
        spans = json.loads(row[0]) if row else self._auto_spans(doc, pages)
        db.execute('DELETE FROM units WHERE doc_id=?', (doc['id'],))
        covered = set()
        def add(label, confidence, parts, ms_id=None, ms_page=None):
            if not parts:
                return
            text = '\n'.join(p['text'] for p in parts)
            if not re.search('[A-Za-z]', text):
                return
            db.execute('INSERT INTO units(doc_id,label,confidence,page_start,page_end,text,parts_json,ms_doc_id,ms_page) VALUES(?,?,?,?,?,?,?,?,?)',
                       (doc['id'], label, confidence, parts[0]['page'], parts[-1]['page'], text, json.dumps(parts), ms_id, ms_page))
        for span in spans:
            parts = []
            for p in pages:
                if not span['page_start'] <= p['page'] <= span['page_end'] or p['status'] not in ('text', 'ocr'):
                    continue
                start = span.get('line_start', 1) if p['page'] == span['page_start'] else 1
                end = span.get('line_end', len(p['lines'])) if p['page'] == span['page_end'] else len(p['lines'])
                text = '\n'.join(l['text'] for l in p['lines'][start-1:end])
                covered.update((p['page'], n) for n in range(start, end+1))
                parts.append({'page': p['page'], 'text': text})
            add(span['label'], span.get('confidence', 'manual'), parts, span.get('ms_doc_id'), span.get('ms_page'))
        for p in pages:
            if p['status'] not in ('text', 'ocr'):
                continue
            text = '\n'.join(l['text'] for n, l in enumerate(p['lines'], 1) if (p['page'], n) not in covered)
            add(None, 'page', [{'page': p['page'], 'text': text}])

    def correct(self, doc_id, spans):
        doc = self.document(doc_id)
        if not isinstance(spans, list) or len(spans) > 200:
            raise ValueError('修正目录应为不超过 200 项的 JSON 数组')
        with self.connect() as db:
            pages = [dict(r) for r in db.execute('SELECT * FROM pages WHERE doc_id=? ORDER BY page', (doc_id,))]
            for p in pages:
                p['lines'] = json.loads(p['lines_json'])
            previous = (0, 0)
            labels = set()
            cleaned = []
            for s in spans:
                label = str(s['label']).strip()
                if not re.fullmatch(r'\d{1,2}(?:\([a-zivx0-9]+\))*', label) or label in labels:
                    raise ValueError('题号无效或重复，例如 1、1(a)、1(a)(ii)')
                ps, pe = int(s['page_start']), int(s['page_end'])
                if not 1 <= ps <= pe <= len(pages):
                    raise ValueError('PDF 页码超出范围')
                ls, le = int(s.get('line_start', 1)), int(s.get('line_end', len(pages[pe-1]['lines'])))
                if not 1 <= ls <= len(pages[ps-1]['lines']) or not 1 <= le <= len(pages[pe-1]['lines']) or (ps,ls) > (pe,le) or (ps,ls) <= previous:
                    raise ValueError('行号超界、范围重叠或目录顺序错误')
                out = dict(label=label,page_start=ps,page_end=pe,line_start=ls,line_end=le,confidence='manual')
                if s.get('ms_doc_id') or s.get('ms_page'):
                    ms = self.document(int(s['ms_doc_id']))
                    if ms['kind'] != 'ms' or any(ms[k] != doc[k] for k in ('year','season','paper','variant')) or not 1 <= int(s['ms_page']) <= ms['page_count']:
                        raise ValueError('评分标准不属于同一套卷，或页码超界')
                    out.update(ms_doc_id=ms['id'], ms_page=int(s['ms_page']))
                cleaned.append(out)
                labels.add(label)
                previous = (pe,le)
            db.execute('INSERT INTO corrections(doc_id,spans_json) VALUES(?,?) ON CONFLICT(doc_id) DO UPDATE SET spans_json=excluded.spans_json,updated_at=CURRENT_TIMESTAMP', (doc_id,json.dumps(cleaned)))
            self._build_units(db, doc, pages)

    def related(self, doc):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT * FROM documents WHERE year=? AND season=? AND id!=?
               AND ((paper=? AND variant=?) OR (paper=0 AND kind IN ('er','gt')))
               ORDER BY kind''', (doc['year'],doc['season'],doc['id'],doc['paper'],doc['variant']))]

    def coverage(self):
        with self.connect() as db:
            result = []
            for year in range(2016,2027):
                row = dict(db.execute('''SELECT count(*) files, sum(kind='qp' AND season!='y') qp,
                  sum(kind='ms') ms,sum(kind='er') er,sum(kind='gt') gt,
                  sum(status='ready') ready, sum(status!='ready') unfinished,
                  coalesce(sum(searchable_pages),0) searchable_pages FROM documents WHERE year=?''',(year,)).fetchone())
                row = {k: v or 0 for k,v in row.items()}
                row['year'] = year
                row['seasons'] = [dict(r) for r in db.execute('SELECT season,count(*) files,sum(kind=\'qp\') qp FROM documents WHERE year=? GROUP BY season',(year,))]
                result.append(row)
            return result

    def search(self, query='', filters=None, page=1, size=15, phrase=False):
        filters = filters or {}
        page = max(1, int(page))
        size = max(1, min(50, int(size)))
        where, args = [], []
        for k in ('year','season','paper','variant','kind','status'):
            if filters.get(k) not in (None, ''):
                where.append('d.' + k + '=?')
                args.append(filters[k])
        query = query.strip()
        tokens = re.findall(r"[A-Za-z0-9]+", query)
        if query and not tokens:
            return {'items': [], 'total': 0, 'page': page, 'pages': 0, 'size': size}
        if len(tokens) > 160 or len(query) > 3000:
            raise ValueError('搜索内容过长，请选择不超过 160 个词的一段文字')
        with self.connect() as db:
            if query:
                match = '"' + ' '.join(tokens) + '"' if phrase else ' AND '.join('"'+t+'"' for t in tokens)
                where.insert(0, 'search_fts MATCH ?')
                args.insert(0, match)
                base = ' FROM search_fts JOIN units u ON u.id=search_fts.rowid JOIN documents d ON d.id=u.doc_id'
                fields = 'd.*,u.id unit_id,u.label,u.confidence,u.page_start,u.page_end,u.parts_json,u.ms_doc_id,u.ms_page, snippet(search_fts,0,\'[[H]]\',\'[[/H]]\',\' … \',48) snippet'
                order = 'bm25(search_fts),d.year DESC,u.id'
            else:
                base = ' FROM documents d'
                fields = 'd.*'
                order = "d.year DESC,CASE d.season WHEN 'w' THEN 3 WHEN 's' THEN 2 WHEN 'm' THEN 1 ELSE 0 END DESC,d.paper,d.variant,d.kind"
            clause = (' WHERE ' + ' AND '.join(where)) if where else ''
            total = db.execute('SELECT count(*)'+base+clause,args).fetchone()[0]
            rows = db.execute('SELECT '+fields+base+clause+' ORDER BY '+order+' LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            if query:
                d['snippet_html'] = html.escape(d.pop('snippet')).replace('[[H]]','<mark>').replace('[[/H]]','</mark>')
                parts = json.loads(d.pop('parts_json'))
                # Physical PDF page, one-based. Prefer a page containing the actual matched words.
                d['hit_page'] = next((p['page'] for p in parts if all(t.lower() in p['text'].lower() for t in tokens)),
                    next((p['page'] for p in parts if any(t.lower() in p['text'].lower() for t in tokens)), d['page_start']))
            else:
                d['hit_page'] = 1
            d['related'] = self.related(d)
            items.append(d)
        return {'items':items,'total':total,'page':page,'pages':(total+size-1)//size,'size':size}
