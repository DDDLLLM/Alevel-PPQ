#!/usr/bin/env python3
"""Discover public historical listings and import actual PDFs, never guessed files."""
import argparse
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biology.library import Library, metadata
from biology.sources import Client, SourceBlocked, discover_fraft, discover_papersc, add_catalog, record_run

UNION_ROOT = 'https://igunioneg.com/past-papers/cambridge/?' + urlencode({'dir': '/AS And A Level/Biology 9700'})


def union_sessions(text, base=UNION_ROOT):
    result = {}
    for a in BeautifulSoup(text, 'html.parser').select('a[href]'):
        url = urljoin(base, a['href'])
        if urlparse(url).hostname != 'igunioneg.com':
            continue
        directory = parse_qs(urlparse(url).query).get('dir', [''])[0]
        if not directory.startswith('/AS And A Level/Biology 9700/'):
            continue
        label = directory.rsplit('/', 1)[-1]
        year = re.search(r'\b(201[6-9]|202[0-3])\b', label)
        if not year:
            continue
        low = label.lower()
        season = 'm' if 'mar' in low else 's' if 'jun' in low else 'w' if 'nov' in low else None
        if season:
            result[(int(year[1]), season)] = url
    return result


def discover_union(lib, client, years):
    sessions = union_sessions(client.text(UNION_ROOT))
    for year in years:
        for season in 'msw':
            url = sessions.get((year, season))
            if not url:
                logging.error('补充来源未列出 %s %s；记录缺失，不构造地址', year, season)
                continue
            html = client.text(url)
            count = 0
            for a in BeautifulSoup(html, 'html.parser').select('a[href]'):
                link = urljoin(url, a['href'])
                if urlparse(link).hostname != 'igunioneg.com':
                    continue
                match = re.search(r'9700_[msw]\d{2}_(?:qp|ms|er|gt|ci|ir|in)(?:_[1-5]\d)?\.pdf', unquote(link) + ' ' + a.get_text(), re.I)
                if not match:
                    continue
                meta = metadata(match[0])
                if meta['year'] != year or meta['season'] != season:
                    raise SourceBlocked('补充目录返回了不匹配的年份或考季')
                add_catalog(lib, 'igunion', link, meta['filename'], link, {'listing_url': url})
                count += 1
            logging.info('补充来源 %s %s：发现 %s 条真实链接', year, season, count)


def report(lib, years, errors):
    output = {'source_errors': errors, 'sessions': [], 'complete': False,
              'note': '仅比较本次来源实际列出的文件；目录完整性和 PDF 下载成功是不同状态。'}
    with lib.connect() as db:
        for year in years:
            for season in 'msw':
                prefix = f'9700_{season}{year % 100:02}_%'
                known = {r[0] for r in db.execute("SELECT filename FROM catalog WHERE source IN ('papersc','fraft','igunion') AND filename LIKE ?", (prefix,))}
                local = {r[0] for r in db.execute('SELECT filename FROM documents WHERE year=? AND season=?', (year, season))}
                unfinished = [r[0] for r in db.execute("SELECT filename FROM documents WHERE year=? AND season=? AND status!='ready'", (year, season))]
                output['sessions'].append({'year': year, 'season': season, 'listed': len(known), 'local_files': len(local),
                                            'missing_from_listings': sorted(known-local), 'unfinished_index': unfinished,
                                            'listing_obtained': bool(known)})
    output['all_discovered_files_present'] = all(s['listing_obtained'] and not s['missing_from_listings'] for s in output['sessions'])
    # Do not label a year universally complete simply because one source has a list.
    (lib.home/'logs'/'2016-2023-sync.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
    for row in output['sessions']:
        print(f"{row['year']} {row['season']}：目录 {row['listed']}，本地 {row['local_files']}，目录内未下载 {len(row['missing_from_listings'])}，未完成索引 {len(row['unfinished_index'])}", flush=True)
    return output


def main():
    p = argparse.ArgumentParser(description='批量补充 9700 2016–2023，不限制为 330 文件')
    p.add_argument('--data')
    p.add_argument('--years', default='2016:2023')
    p.add_argument('--discover-only', action='store_true')
    p.add_argument('--limit', type=int)
    args = p.parse_args()
    bounds = args.years.split(':')
    years = list(range(int(bounds[0]), int(bounds[-1])+1))
    if not years or min(years) < 2016 or max(years) > 2023:
        p.error('仅支持 2016–2023')
    lib = Library(args.data)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(lib.home/'logs'/'range-sync.log', encoding='utf-8')])
    errors = {}
    clients = {}
    for source, discover in [('fraft', discover_fraft), ('papersc', discover_papersc), ('igunion', discover_union)]:
        print(f'检查来源：{source}', flush=True)
        clients[source] = Client(lib.home, delay=2)
        try:
            discover(lib, clients[source], years)
            record_run(lib, source, 'discovered', '2016–2023 目录发现完成；尚需逐文件下载验证')
        except Exception as exc:
            errors[source] = str(exc)
            logging.error('%s 无法完成目录获取：%s', source, exc)
            record_run(lib, source, 'blocked', str(exc))
    if not args.discover_only:
        with lib.connect() as db:
            rows = db.execute("SELECT * FROM catalog WHERE source IN ('papersc','fraft','igunion') ORDER BY filename, CASE source WHEN 'fraft' THEN 0 WHEN 'papersc' THEN 1 ELSE 2 END").fetchall()
        attempted = 0
        blocked = set(errors)
        for row in rows:
            meta = metadata(row['filename'])
            if meta['year'] not in years:
                continue
            with lib.connect() as db:
                existing = db.execute('SELECT * FROM documents WHERE filename=?', (row['filename'],)).fetchone()
            if existing and lib.pdf_path(existing).is_file():
                continue
            source = row['source']
            if source in blocked:
                continue
            if args.limit is not None and attempted >= args.limit:
                break
            attempted += 1
            print(f'下载并索引：{row["filename"]}（{source}）', flush=True)
            try:
                pdf = clients[source].pdf(row['url'])
                lib.import_pdf(pdf, filename=row['filename'], source=source, url=row['url'], original_id=row['original_id'])
                with lib.connect() as db:
                    db.execute("UPDATE catalog SET state='imported',error='' WHERE source=? AND original_id=?", (source,row['original_id']))
            except Exception as exc:
                logging.error('%s：%s', row['filename'], exc)
                with lib.connect() as db:
                    db.execute("UPDATE catalog SET state='failed',error=? WHERE source=? AND original_id=?", (str(exc),source,row['original_id']))
                if isinstance(exc, SourceBlocked):
                    blocked.add(source)
                    errors[source] = str(exc)
    result = report(lib, years, errors)
    print('详细报告：'+str(lib.home/'logs'/'2016-2023-sync.json'), flush=True)
    if not result['all_discovered_files_present']:
        print('本次未补齐全部考季的来源目录和文件。重新执行可继续，未下载文件不计入收录。', flush=True)
        return 1
    print('来源已列出的文件均已在本地；这不证明来源目录绝对完整。', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
