"""Additive reader storage. Original PDF, page text, FTS and corrections are untouched."""
import json
import math
import re
import sqlite3
from datetime import datetime, timezone

import fitz

LAYOUT_VERSION = 1
DIRECTORY_VERSION = 2
LABEL = re.compile(r'\d{1,2}(?:\([a-z0-9]+\))*')


def label(value):
    value = re.sub(r'\s+', '', str(value)).lower()
    if not LABEL.fullmatch(value) or not 1 <= int(re.match(r'\d+', value)[0]) <= 99:
        raise ValueError('请输入题号，例如 4、4(a) 或 4(a)(iii)')
    return value


def migrate(path):
    """An SQLite online backup precedes the first additive v2 migration."""
    with sqlite3.connect(path, timeout=60) as db:
        old = db.execute('PRAGMA user_version').fetchone()[0]
        if old >= 2:
            return
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='documents'").fetchone():
            folder = path.parent / 'backups'
            folder.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            with sqlite3.connect(folder / f'before-reader-v2-{stamp}.sqlite3') as target:
                db.backup(target)
        db.executescript('''BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS page_layouts(
          doc_id INTEGER NOT NULL, page INTEGER NOT NULL, version INTEGER NOT NULL,
          data_json TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(doc_id,page));
        CREATE TABLE IF NOT EXISTS answer_directories(
          doc_id INTEGER PRIMARY KEY, version INTEGER NOT NULL, data_json TEXT NOT NULL,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS answer_links(
          qp_doc_id INTEGER NOT NULL, label TEXT NOT NULL, ms_doc_id INTEGER NOT NULL,
          ranges_json TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(qp_doc_id,label));
        PRAGMA user_version=2;
        COMMIT;''')


def bbox(rect, page):
    return [round(v, 3) for v in fitz.Rect(rect) * page.rotation_matrix]


def text_in(layout, box):
    """Visual reading order, not PDF object order (important for rotated MS tables)."""
    x0, y0, x1, y1 = box
    words = [w for w in layout['words'] if x0 <= (w['box'][0]+w['box'][2])/2 <= x1
             and y0 <= (w['box'][1]+w['box'][3])/2 < y1]
    rows = []
    for w in sorted(words, key=lambda w: (w['box'][1], w['box'][0])):
        y = (w['box'][1] + w['box'][3]) / 2
        row = next((r for r in rows[-3:] if abs(r[0]-y) < 3), None)
        if row is None:
            row = [y, []]
            rows.append(row)
        row[1].append(w)
    return '\n'.join(' '.join(w['text'] for w in sorted(r[1], key=lambda w:w['box'][0])) for r in rows)


class Reader:
    def __init__(self, library):
        self.lib = library

    def layout(self, doc_id, number, repair=False):
        doc = self.lib.document(doc_id)
        if not 1 <= number <= doc['page_count']:
            raise ValueError('PDF 页码超出范围')
        with self.lib.connect() as db:
            cached = db.execute('SELECT * FROM page_layouts WHERE doc_id=? AND page=?', (doc_id, number)).fetchone()
            saved = db.execute('SELECT text,status FROM pages WHERE doc_id=? AND page=?', (doc_id, number)).fetchone()
        if cached and cached['version'] == LAYOUT_VERSION:
            data = json.loads(cached['data_json'])
            if not (repair and data['needs_coordinates']):
                # Reindexing can change OCR status without changing immutable PDF bytes.
                if not (saved and saved['status']=='ocr' and data['source']=='native'):
                    return data
        with fitz.open(self.lib.pdf_path(doc)) as pdf:
            page = pdf[number-1]
            source = 'native'
            needs = bool(saved and saved['status'] in ('ocr', 'needs_ocr'))
            tp = None
            if needs and repair:
                try:
                    tp = page.get_textpage_ocr(language='eng', dpi=200, full=True)
                except Exception as exc:
                    raise ValueError('此页文字坐标识别失败。请检查 Tesseract 和 eng 语言包；已有 OCR 与索引仍保留。' + str(exc)) from exc
                source, needs = 'ocr', False
            elif needs:
                source = 'ocr_pending'
            words = []
            for w in page.get_text('words', textpage=tp):
                if w[4].strip():
                    words.append({'text':w[4], 'box':bbox(w[:4], page)})
            # A native fragment does not count as a complete OCR overlay.
            if needs:
                words = []
            raw = page.get_text('dict', textpage=tp)
            lines = []
            for b in raw['blocks']:
                for ln in b.get('lines', []):
                    t = ''.join(s['text'] for s in ln['spans']).strip()
                    if t:
                        lines.append({'text': t, 'box': bbox(ln['bbox'], page)})
            lines.sort(key=lambda l: (l['box'][1], l['box'][0]))
            # Thin rectangles are table rules in many Cambridge MS PDFs.
            rules = []
            for drawing in page.get_drawings():
                r = fitz.Rect(drawing['rect']) * page.rotation_matrix
                if r.width > page.rect.width * .65 and r.height < 3:
                    rules.append(round((r.y0+r.y1)/2, 3))
            data = dict(page=number, width=page.rect.width, height=page.rect.height,
                        source=source, needs_coordinates=needs, words=words, lines=lines,
                        rules=sorted(set(rules)), text=saved['text'] if saved else '')
            if source=='ocr' and not words:
                raise ValueError('此页未识别到可定位文字，保留已有 OCR 文字；可查看原卷核对。')
        with self.lib.connect() as db:
            db.execute('INSERT INTO page_layouts(doc_id,page,version,data_json) VALUES(?,?,?,?) '
                       'ON CONFLICT(doc_id,page) DO UPDATE SET version=excluded.version,data_json=excluded.data_json,updated_at=CURRENT_TIMESTAMP',
                       (doc_id, number, LAYOUT_VERSION, json.dumps(data, ensure_ascii=False)))
            if repair:
                db.execute('DELETE FROM answer_directories WHERE doc_id=?', (doc_id,))
        return data

    def _segment(self, number, layout, box):
        return dict(page=number, box=box, width=layout['width'], height=layout['height'],
                    text=text_in(layout, box), source=layout['source'])

    def directory(self, ms_id, refresh=False):
        doc = self.lib.document(ms_id)
        if doc['kind'] != 'ms':
            raise ValueError('该文件不是评分标准')
        with self.lib.connect() as db:
            cached = db.execute('SELECT * FROM answer_directories WHERE doc_id=?', (ms_id,)).fetchone()
        if cached and cached['version']==DIRECTORY_VERSION and not refresh:
            return json.loads(cached['data_json'])
        layouts = {n:self.layout(ms_id,n) for n in range(1,doc['page_count']+1)}
        entries = {}
        if doc['paper']==1:
            pairs = []
            for n, p in layouts.items():
                # Native text only for automatic matching. OCR remains manually locatable.
                if p['source']!='native' or not re.search(r'Question',p['text'], re.I):
                    continue
                for w in p['words']:
                    if not re.fullmatch(r'\d{1,2}', w['text']):
                        continue
                    x0,y0,x1,y1 = w['box']
                    if not 70 < y0 < p['height']-60:
                        continue
                    answers = [a for a in p['words'] if re.fullmatch('[ABCD]',a['text'])
                               and 5 < a['box'][0]-x1 < p['width']*.18 and abs(a['box'][1]-y0)<3]
                    if len(answers)==1:
                        a=answers[0]
                        pairs.append((w['text'],self._segment(n,p,[x0-3,y0-2,a['box'][2]+3,max(y1,a['box'][3])+2])))
            # Require the entire forty-question answer key, including uniqueness.
            if sorted(int(k) for k,_ in pairs)==list(range(1,41)):
                entries={k:dict(label=k,segments=[s],complete=True) for k,s in pairs}
        else:
            records=[]
            blocked=False
            for n,p in layouts.items():
                if p['source']!='native':
                    continue
                header = next((l for l in p['lines'] if l['text'].strip().lower()=='question'
                               and l['box'][0]<p['width']*.25), None)
                if not header or not any(l['text'].lower()=='answer' for l in p['lines']) or not any(l['text'].lower()=='marks' for l in p['lines']):
                    continue  # old, unruled prose MS: honest manual fallback
                hx0,hy0,hx1,hy1=header['box']
                candidates=[]
                for ln in p['lines']:
                    t=re.sub(r'\s+','',ln['text']).lower()
                    if LABEL.fullmatch(t) and 0<int(re.match(r'\d+',t)[0])<=40 and hx0-8<=ln['box'][0]<=hx1 and ln['box'][2]<p['width']*.23 and hy1<ln['box'][1]<p['height']-50:
                        candidates.append((t,ln['box'][1]))
                # Unknown labels in the question column invalidate this page, not silently merged.
                suspicious=[ln for ln in p['lines'] if hx0-8<=ln['box'][0]<=hx1 and ln['box'][2]<p['width']*.23 and hy1+4<ln['box'][1]<p['height']-50 and ln['text'].lower()!='question' and not LABEL.fullmatch(re.sub(r'\s+','',ln['text']).lower())]
                if not candidates or suspicious:
                    blocked=True
                    continue
                for i,(k,y) in enumerate(candidates):
                    end=candidates[i+1][1]-2 if i+1<len(candidates) else p['height']-45
                    repeated_headers=[ln['box'][1]-2 for ln in p['lines'] if ln['text'].lower()=='question' and y<ln['box'][1]<end]
                    if repeated_headers:end=min(repeated_headers)
                    separators=[v for v in p['rules'] if y+2<v<=end]
                    if separators:
                        end=max(separators)
                    start=max(hy1+2,y-2)
                    # Borderless layouts still locate the start, but copying is disabled.
                    complete=bool(separators)
                    records.append((k,self._segment(n,p,[hx0-3,start,p['width']-55,end]),complete))
            # Repeated labels may continue on the next page, never reappear later out of order.
            order=[]
            for k,s,complete in records:
                if k in entries and (not order or order[-1]!=k):
                    blocked=True
                    continue
                order.append(k)
                entry=entries.setdefault(k,dict(label=k,segments=[],complete=True))
                entry['segments'].append(s)
                entry['complete'] &= complete
            if blocked:
                # Starts remain useful; uncertain boundaries cannot enable whole-answer copy.
                for e in entries.values():e['complete']=False
            # Parent/main question ranges consist only of recognized child rows.
            original=dict(entries)
            parents=set()
            for k in original:
                ancestors=re.findall(r'^\d+|\([a-z0-9]+\)',k)
                parents.update(''.join(ancestors[:i]) for i in range(1,len(ancestors)))
            for parent in parents:
                children=[v for name,v in original.items() if name==parent or name.startswith(parent+'(')]
                segs=[s for v in children for s in v['segments']]
                segs.sort(key=lambda s:(s['page'],s['box'][1]))
                entries[parent]=dict(label=parent,segments=segs,complete=bool(children) and all(v['complete'] for v in children))
        result=dict(entries=entries,reason='' if entries else '未找到可靠的表格题号目录，请用卷内搜索或人工定位。',
                    pending_pages=[n for n,p in layouts.items() if p['needs_coordinates']])
        with self.lib.connect() as db:
            db.execute('INSERT INTO answer_directories(doc_id,version,data_json) VALUES(?,?,?) '
                       'ON CONFLICT(doc_id) DO UPDATE SET version=excluded.version,data_json=excluded.data_json,updated_at=CURRENT_TIMESTAMP',
                       (ms_id,DIRECTORY_VERSION,json.dumps(result,ensure_ascii=False)))
        return result

    def question(self, doc_id, value):
        k=label(value)
        with self.lib.connect() as db:
            row=db.execute('SELECT * FROM units WHERE doc_id=? AND label=?',(doc_id,k)).fetchone()
        if row:
            return dict(label=k,text=row['text'],complete=True,confidence=row['confidence'],
                        page=row['page_start'],page_end=row['page_end'])
        # Derive subparts only inside an already verified main-question directory.
        # Cambridge uses separate gutters for (a) and (i). Reject gaps/repetitions.
        root=re.match(r'\d+',k)[0]
        with self.lib.connect() as db:
            parent=db.execute('SELECT * FROM units WHERE doc_id=? AND label=?',(doc_id,root)).fetchone()
        if parent and '(' in k:
            layouts={n:self.layout(doc_id,n) for n in range(parent['page_start'],parent['page_end']+1)}
            if all(p['source']=='native' for p in layouts.values()):
                events=[];letter='';last_letter=0;roman_index=0;valid=True
                romans=['i','ii','iii','iv','v','vi','vii','viii','ix','x']
                bounds={}
                for n,p in layouts.items():
                    start,end=55,p['height']-65
                    mains=[ln for ln in p['lines'] if 40<=ln['box'][0]<=56 and 55<ln['box'][1]<end and re.fullmatch(r'\d{1,2}',ln['text'])]
                    if n==parent['page_start']:
                        anchor=next((ln for ln in mains if ln['text']==root),None)
                        if anchor:start=anchor['box'][1]-1
                    for ln in mains:
                        if int(ln['text'])>int(root):end=min(end,ln['box'][1]-1)
                    bounds[n]=(start,end)
                    for ln in p['lines']:
                        x,y,_,_=ln['box']
                        m=re.match(r'^\(([a-z]+)\)(?:\s|$)',ln['text'])
                        if not m or not start<=y<end:continue
                        part=m[1]
                        if 65<=x<=86 and len(part)==1:
                            if ord(part)-96!=last_letter+1:valid=False;break
                            letter=part;last_letter+=1;roman_index=0
                            events.append((root+'('+part+')',n,y))
                        elif 88<=x<=113 and part in romans and letter:
                            if romans.index(part)!=roman_index:valid=False;break
                            roman_index+=1
                            events.append((root+'('+letter+')('+part+')',n,y))
                found=next((i for i,e in enumerate(events) if e[0]==k),None)
                if valid and found is not None:
                    _,sp,sy=events[found]
                    stop=next((e for e in events[found+1:] if not e[0].startswith(k+'(')),None)
                    ep,ey=(stop[1],stop[2]-1) if stop else (parent['page_end'],bounds[parent['page_end']][1])
                    segments=[]
                    for n in range(sp,ep+1):
                        p=layouts[n];y0=sy-1 if n==sp else bounds[n][0];y1=ey if n==ep else bounds[n][1]
                        if y1>y0 and 'BLANK PAGE' not in p['text'].upper():
                            segment=self._segment(n,p,[40,y0,p['width']-40,y1])
                            if segment['text'].strip():segments.append(segment)
                    if not segments:return dict(label=k,text='',complete=False,confidence='unlocated')
                    return dict(label=k,text=k+'\n'+'\n\n'.join(s['text'] for s in segments),complete=True,
                                confidence='automatic',page=segments[0]['page'],page_end=segments[-1]['page'],segments=segments)
        return dict(label=k,text='',complete=False,confidence='unlocated')

    def resolve(self, qp_id, value=''):
        qp=self.lib.document(qp_id)
        if qp['kind']!='qp':
            raise ValueError('请从试题文件查找对应答案')
        ms=next((r for r in self.lib.related(qp) if r['kind']=='ms'),None)
        out=dict(ms=ms,label=value,status='unlocated',segments=[],complete=False,text='',
                 message='评分标准尚未导入' if not ms else '已关联本卷 MS；尚未定位到具体答案。')
        if not value or not ms:return out
        k=label(value);out['label']=k
        with self.lib.connect() as db:
            manual=db.execute('SELECT * FROM answer_links WHERE qp_doc_id=? AND label=?',(qp_id,k)).fetchone()
            old=db.execute('SELECT ms_doc_id,ms_page FROM units WHERE doc_id=? AND label=?',(qp_id,k)).fetchone()
        if manual and manual['ms_doc_id']==ms['id']:
            segments=json.loads(manual['ranges_json'])
            # A saved range is durable; newly available coordinates can improve its text.
            segments=[self._segment(s['page'],self.layout(ms['id'],s['page']),s['box']) for s in segments]
            out.update(status='manual',segments=segments,complete=all(s.get('text') for s in segments),
                       text='\n\n'.join(s['text'] for s in segments),message='已人工确认答案范围')
            return out
        directory=self.directory(ms['id'])
        found=directory['entries'].get(k)
        # Honour old page-only corrections. Do not quietly replace a confirmed page with an auto page.
        if old and old['ms_doc_id']==ms['id'] and old['ms_page']:
            out.update(status='manual',page=old['ms_page'],message='已人工确认 MS 页码；答案范围尚未确认，不能复制整题答案。')
            return out
        if found:
            out.update(status='automatic',segments=found['segments'],complete=found['complete'],
                       text='\n\n'.join(s['text'] for s in found['segments']) if found['complete'] else '',
                       message='自动定位：已识别 MS 表格题号，请核对原卷。'+('' if found['complete'] else ' 内容终点待确认，暂不复制整题答案。'))
        else:
            out['message']='尚未定位到 '+k+' 的答案。已关联正确 MS，可卷内搜索或人工修正。'
        return out

    def save_link(self, qp_id, payload):
        qp=self.lib.document(qp_id);ms=self.lib.document(int(payload['ms_doc_id']));k=label(payload['label'])
        if qp['kind']!='qp' or ms['kind']!='ms' or any(qp[f]!=ms[f] for f in ('year','season','paper','variant')):
            raise ValueError('QP 与 MS 必须属于相同年份、考季和完整组件编号')
        ranges=payload.get('ranges')
        if not isinstance(ranges,list) or not 1<=len(ranges)<=100:
            raise ValueError('请提供已核对的答案范围')
        clean=[];previous=None
        for r in ranges:
            n=int(r['page']);p=self.layout(ms['id'],n)
            box=[float(v) for v in r['box']]
            if len(box)!=4 or not all(math.isfinite(v) for v in box) or not(0<=box[0]<box[2]<=p['width'] and 0<=box[1]<box[3]<=p['height']):
                raise ValueError('答案范围超出页面')
            if previous and (n,box[1])<(previous[0],previous[1]):
                raise ValueError('范围必须按页码顺序排列且不能重叠')
            clean.append(self._segment(n,p,box));previous=(n,box[3])
        with self.lib.connect() as db:
            db.execute('INSERT INTO answer_links(qp_doc_id,label,ms_doc_id,ranges_json) VALUES(?,?,?,?) '
                       'ON CONFLICT(qp_doc_id,label) DO UPDATE SET ms_doc_id=excluded.ms_doc_id,ranges_json=excluded.ranges_json,updated_at=CURRENT_TIMESTAMP',
                       (qp_id,k,ms['id'],json.dumps(clean,ensure_ascii=False)))
        return self.resolve(qp_id,k)

    def find(self, doc_id, query):
        self.lib.document(doc_id)
        query=query.strip()
        if not query or len(query)>200:raise ValueError('请输入不超过 200 字符的卷内搜索内容')
        tokens=re.findall(r'[A-Za-z0-9]+',query.lower())
        if not tokens:raise ValueError('请输入英文关键词或题号')
        result=[]
        with self.lib.connect() as db:
            for r in db.execute('SELECT page,text,status FROM pages WHERE doc_id=? ORDER BY page',(doc_id,)):
                if all(re.search(r'\b'+re.escape(t)+r'\b',r['text'],re.I) for t in tokens):
                    at=re.search(r'\b'+re.escape(tokens[0])+r'\b',r['text'],re.I).start()
                    result.append(dict(page=r['page'],text=r['text'][max(0,at-60):at+260],source=r['status']))
        return result
