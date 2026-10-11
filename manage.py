#!/usr/bin/env python3
import argparse
import json
import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from biology.library import Library
from biology.sources import Client, record_run, discover_papersc, discover_fraft, discover_html, download_catalog


def years(value):
    parts=value.split(':')
    nums=list(range(int(parts[0]),int(parts[1])+1)) if len(parts)==2 else [int(x) for x in value.split(',')]
    if not nums or min(nums)<2016 or max(nums)>2026:
        raise argparse.ArgumentTypeError('年份必须在 2016–2026 范围')
    return nums


def main(argv=None):
    p=argparse.ArgumentParser(description='9700 本地题库：导入、更新、索引与备份')
    p.add_argument('--data',help='数据目录，默认项目 data/')
    sub=p.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import',help='递归批量导入 PDF')
    imp.add_argument('path');imp.add_argument('--source',default='local');imp.add_argument('--source-url',default='')
    idx=sub.add_parser('reindex',help='重建索引（保留人工目录）')
    idx.add_argument('--id',type=int);idx.add_argument('--ocr',action='store_true',help='需要系统已安装 Tesseract + eng 语言包')
    sub.add_parser('coverage',help='输出每年实际覆盖与待处理文件')
    sync=sub.add_parser('sync',help='联网发现并导入；实时校验源码线索接口')
    sync.add_argument('--source',choices=['papersc','fraft'],required=True)
    sync.add_argument('--years',type=years,default=years('2016:2026'))
    sync.add_argument('--discover-only',action='store_true');sync.add_argument('--limit',type=int)
    sync.add_argument('--delay',type=float,default=2);sync.add_argument('--refresh',action='store_true')
    html=sub.add_parser('from-page',help='从公开目录页发现标准命名 PDF，不递归抓取')
    html.add_argument('url');html.add_argument('--source',default='supplement');html.add_argument('--limit',type=int)
    html.add_argument('--delay',type=float,default=2);html.add_argument('--refresh',action='store_true')
    html.add_argument('--discover-only',action='store_true')
    resume=sub.add_parser('resume',help='继续已发现但未导入或下载失败的文件')
    resume.add_argument('--source',required=True);resume.add_argument('--limit',type=int);resume.add_argument('--delay',type=float,default=2)
    probe=sub.add_parser('probe',help='9700 小规模实测查询、raw、PDF、目录和全文搜索')
    probe.add_argument('--source',choices=['papersc','fraft'],required=True)
    backup=sub.add_parser('backup',help='SQLite 一致性快照与 PDF/日志备份')
    backup.add_argument('destination')
    args=p.parse_args(argv)
    lib=Library(args.data)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(),logging.FileHandler(lib.home/'logs'/'import.log',encoding='utf-8')])
    failed=0
    if args.command=='import':
        root=Path(args.path)
        files=[root] if root.is_file() else sorted(f for f in root.rglob('*') if f.suffix.lower()=='.pdf')
        if not files:
            p.error('没有找到 PDF 文件')
        for f in files:
            try:
                logging.info('%s',lib.import_pdf(f,source=args.source,url=args.source_url))
            except Exception as exc:
                failed+=1;logging.error('%s: %s',f.name,exc)
        logging.info('已处理 %d，失败 %d',len(files),failed)
    elif args.command=='reindex':
        with lib.connect() as db:
            ids=[args.id] if args.id else [r[0] for r in db.execute('SELECT id FROM documents')]
        for doc_id in ids:
            try:
                lib.index_document(doc_id,ocr=args.ocr);logging.info('REINDEX %s',doc_id)
            except Exception as exc:
                failed+=1;logging.error('REINDEX %s: %s',doc_id,exc)
    elif args.command=='coverage':
        with lib.connect() as db:
            unfinished=[dict(r) for r in db.execute("SELECT filename,status,error FROM documents WHERE status!='ready'")]
        print(json.dumps({'years':lib.coverage(),'unfinished':unfinished},ensure_ascii=False,indent=2))
    elif args.command in ('sync','from-page','resume'):
        c=Client(lib.home,args.delay,getattr(args,'refresh',False))
        try:
            if args.command=='sync':
                count=(discover_papersc if args.source=='papersc' else discover_fraft)(lib,c,args.years)
                record_run(lib,args.source,'catalog_verified',f'本次列表通过结构校验，共 {count} 条；不代表已下载')
            elif args.command=='from-page':
                count=discover_html(lib,c,args.url,args.source)
                record_run(lib,args.source,'links_discovered',f'{args.url}：{count} 条链接；尚未核实 PDF')
            if not getattr(args,'discover_only',False):
                counts=download_catalog(lib,c,args.source,args.limit)
                failed=counts['failed']
                record_run(lib,args.source,'partial' if failed else 'finished',json.dumps(counts))
        except Exception as exc:
            failed=1;record_run(lib,args.source,'blocked',str(exc));logging.error('%s',exc)
    elif args.command=='probe':
        c=Client(lib.home,refresh=True)
        try:
            if args.source=='papersc':
                from urllib.parse import urlencode
                base='https://paper.sc/search/?'
                data=c.json(base+urlencode({'query':'9700 s23 qp 12','as':'json'}))
                if data.get('response')!='pp' or not isinstance(data.get('list'),list) or not data['list']:
                    raise ValueError('小规模查询没有返回预期试卷列表')
                raw=c.text(base+urlencode({'query':'9700 s23 qp 12','as':'raw','wlinks':'1'}))
                doc=next(d for d in data['list'] if d['type']=='qp' and d['subject']=='9700' and d['time']=='s23' and d['paper']==1 and d['variant']==2)
                docurl=f'https://paper.sc/doc/{doc["_id"]}/'
                directory=c.json(docurl+'?as=dir')
                text_result=c.json(base+urlencode({'query':'9700 mitochondria','as':'json'}))
                if not isinstance(directory,dict) or text_result.get('response')!='text':
                    raise ValueError('目录或全文检索结构不符')
                result=lib.import_pdf(c.pdf(docurl),filename='9700_s23_qp_12.pdf',source='papersc',url=docurl,original_id=doc['_id'])
                evidence={'json':data,'raw':raw,'directory':directory,'text':text_result,'import':result,'page_basis':'remote zero-based; local PDF one-based'}
                (lib.home/'logs'/'papersc-probe.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
                record_run(lib,args.source,'probe_passed','9700 s23 qp12 的查询/raw/PDF/目录/全文结构验证通过；详见日志')
            else:
                count=discover_fraft(lib,c,[2026]);record_run(lib,args.source,'probe_passed',f'2026 列表结构通过，共 {count} 条；不等于已下载')
        except Exception as exc:
            failed=1;record_run(lib,args.source,'blocked',str(exc));logging.error('%s',exc)
    elif args.command=='backup':
        destination=Path(args.destination).resolve()
        if destination.exists():
            p.error('备份目标必须是新的目录，以免覆盖已有资料')
        if lib.home==destination or lib.home in destination.parents:
            p.error('备份不能放在 data 内部')
        destination.mkdir(parents=True)
        with lib.connect() as db, sqlite3.connect(destination/'library.sqlite3') as copy:
            db.backup(copy)
            hashes=[r[0] for r in copy.execute('SELECT sha256 FROM documents')]
        (destination/'pdfs').mkdir()
        for digest in hashes:
            shutil.copy2(lib.home/'pdfs'/f'{digest}.pdf',destination/'pdfs'/f'{digest}.pdf')
        for folder in ('logs','quarantine'):
            shutil.copytree(lib.home/folder,destination/folder,dirs_exist_ok=True)
        logging.info('备份完成：%s，%d PDFs',destination,len(hashes))
    return 1 if failed else 0


if __name__=='__main__':
    sys.exit(main())
