#!/usr/bin/env python3
import csv,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from biology.library import Library,SEASONS

lib=Library()
out=Path(__file__).resolve().parents[1]/'docs';out.mkdir(exist_ok=True)
coverage=lib.coverage()
with lib.connect() as db:
    docs=[dict(r) for r in db.execute('SELECT * FROM documents ORDER BY year,filename')]
    for doc in docs:
        doc['sources']=[dict(r) for r in db.execute('SELECT source,url,original_id,fetched_at FROM sources WHERE doc_id=?',(doc['id'],))]
        doc['pending_pages']=[r[0] for r in db.execute("SELECT page FROM pages WHERE doc_id=? AND status='needs_ocr' ORDER BY page",(doc['id'],))]
    qcount=db.execute('SELECT count(*) FROM units WHERE label IS NOT NULL').fetchone()[0]
    qdocs=db.execute('SELECT count(distinct doc_id) FROM units WHERE label IS NOT NULL').fetchone()[0]
    ocr=[dict(r) for r in db.execute("SELECT d.filename,p.page FROM pages p JOIN documents d ON d.id=p.doc_id WHERE p.status='ocr'")]
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    db.execute("INSERT INTO search_fts(search_fts) VALUES('integrity-check')")
payload={'generated_at':datetime.now(timezone.utc).isoformat(),'coverage':coverage,'documents':docs,'question_units':qcount,'documents_with_questions':qdocs,'ocr_pages':ocr}
(out/'coverage.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'manifest.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['filename','year','season','kind','paper','variant','sha256','page_count','searchable_pages','status','pending_pages','source_urls'])
    for d in docs:w.writerow([d[k] for k in ['filename','year','season','kind','paper','variant','sha256','page_count','searchable_pages','status']]+[','.join(map(str,d['pending_pages'])),' | '.join(s['url'] for s in d['sources'])])
lines=['# 实际覆盖与索引状态','',f'生成时间：{payload["generated_at"]}。仅统计已校验并保存在本地的 PDF。','',
 '| 年份 | 试卷 QP | MS | ER | GT | 全部文件 | 索引完成 | 未完成 | 实际考季（文件数） |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---|']
for y in coverage:
    seasons='、'.join(f'{SEASONS[s["season"]]} ({s["files"]})' for s in y['seasons']) or '未收录'
    lines.append(f'| {y["year"]} | {y["qp"]} | {y["ms"]} | {y["er"]} | {y["gt"]} | {y["files"]} | {y["ready"]} | {y["unfinished"]} | {seasons} |')
lines += ['',f'共 {len(docs)} 文件，其中 {sum(y["qp"] for y in coverage)} 份 QP、{sum(y["searchable_pages"] for y in coverage)} 页可检索文字。{qdocs} 个文件具有题号目录，共 {qcount} 个题目索引单元（包含人工确认项）。',
 '', '数量不代表整年齐全；考试季未导入不等于未发布。图片图表仍需查看原 PDF，全文索引不是图像语义搜索。', '', '## 尚未完成全文索引的文件','']
for d in docs:
    if d['status']!='ready':lines.append(f'- `{d["filename"]}`：{d["status"]}；待处理 PDF 页：{d["pending_pages"]}；错误：{d["error"] or "无运行错误，文字不足以确认索引完整"}')
if all(d['status']=='ready' for d in docs):lines.append('无。')
lines+=['','## 已执行 OCR 的页面','']
for r in ocr:lines.append(f'- `{r["filename"]}` 第 {r["page"]} 页：Tesseract eng，结果仍需核对原图。')
if not ocr:lines.append('尚无 OCR 成功页。')
lines+=['','## 来源与缺失说明','',
 '- 已导入文件来自公开 GitHub 历史仓库，不是 PaperSC API 的下载结果；逐文件来源、提交号和 SHA-256 见 `manifest.csv` / `coverage.json`。',
 '- 2020–2026 暂未导入；其中 2024–2026 按用户最新指示保留后续本地批量导入。',
 '- 2019 未导入 10–11月。2016 年有 3 个同名异内容冲突被隔离；没有覆盖已收录版本。',
 '- PaperSC 网页可见目录到 2023 s23；在线 JSON/raw API 和 Fraft 在执行环境被网络白名单阻止。详见 RESEARCH.md。',
 '- 所有测试生成的 PDF 均位于临时测试目录，没有进入交付题库。']
lines+=['','## 已有 QP 但未导入匹配 MS','']
for d in docs:
    if d['kind']=='qp' and not any(r['kind']=='ms' for r in lib.related(d)):
        lines.append(f'- `{d["filename"]}`')
(out/'COVERAGE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'Report generated: {len(docs)} documents, {qdocs} with question directories; SQLite and FTS integrity OK')
