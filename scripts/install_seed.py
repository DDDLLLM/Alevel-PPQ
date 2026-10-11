#!/usr/bin/env python3
"""Install verified historical PDFs from immutable public source URLs."""
import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biology.library import Library
from biology.sources import Client, SourceBlocked, record_run


def main():
    parser = argparse.ArgumentParser(description='批量安装已验证的 330 个历史 PDF')
    parser.add_argument('--data')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    lib = Library(args.data)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(lib.home / 'logs' / 'seed.log', encoding='utf-8')])
    files = json.loads(Path(__file__).with_name('seed_manifest.json').read_text())['files']
    if args.limit is not None:
        files = files[:args.limit]
    client = Client(lib.home, delay=2)
    added = skipped = failed = 0
    for number, item in enumerate(files, 1):
        filename = item['filename']
        with lib.connect() as db:
            existing = db.execute('SELECT * FROM documents WHERE filename=?', (filename,)).fetchone()
        if existing and existing['sha256'] == item['sha256'] and lib.pdf_path(existing).is_file():
            skipped += 1
            print(f'[{number}/{len(files)}] 已存在：{filename}', flush=True)
            continue
        print(f'[{number}/{len(files)}] 下载并索引：{filename}', flush=True)
        try:
            pdf = client.pdf(item['url'])
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('下载文件的 SHA-256 与已验证原件不一致，未导入')
            result = lib.import_pdf(pdf, filename=filename, source='github-public-archive',
                                    url=item['url'], original_id=item['original_id'])
            if result['duplicate']:
                skipped += 1
            else:
                added += 1
        except SourceBlocked as exc:
            failed += 1
            logging.error('来源限制，停止下载：%s', exc)
            break
        except Exception as exc:
            failed += 1
            logging.exception('%s 导入失败：%s', filename, exc)
    message = f'新增 {added}，已存在 {skipped}，失败 {failed}；可重新运行继续。仅覆盖 2016–2019 部分考季。'
    record_run(lib, 'seed-archive', 'partial' if failed else 'finished', message)
    print(message, flush=True)
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
