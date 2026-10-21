#!/usr/bin/env python3
"""Export a read-only student library without modifying the teacher database."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    path.write_bytes(payload)
    return {'path': path.name, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}


def export(data, output, directories=True):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='biology-student-export-') as temp:
        snapshot = Path(temp) / 'library.sqlite3'
        with sqlite3.connect(f'file:{data / "library.sqlite3"}?mode=ro', uri=True) as source:
            with sqlite3.connect(snapshot) as target:
                source.backup(target)
        db = sqlite3.connect(snapshot)
        db.row_factory = sqlite3.Row
        columns = 'id,filename,sha256,year,season,kind,paper,variant,page_count,searchable_pages,status'
        docs = [dict(r) for r in db.execute(f'SELECT {columns} FROM documents ORDER BY year DESC,season,paper,variant,kind')]
        for doc in docs:
            src = data / 'pdfs' / (doc['sha256'] + '.pdf')
            if not src.is_file():
                raise RuntimeError(f'Missing original PDF: {doc["filename"]}')
            if hashlib.sha256(src.read_bytes()).hexdigest() != doc['sha256']:
                raise RuntimeError(f'PDF hash mismatch: {doc["filename"]}')
            destination = output / 'pdfs' / doc['filename']
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists() or destination.stat().st_size != src.stat().st_size or hashlib.sha256(destination.read_bytes()).hexdigest() != doc['sha256']:
                shutil.copyfile(src, destination)
            doc['pdf'] = 'pdfs/' + doc['filename']
            doc['bytes'] = src.stat().st_size
            doc.pop('sha256')
            doc['related'] = [d['id'] for d in docs if d['id'] != doc['id'] and d['year'] == doc['year'] and d['season'] == doc['season'] and ((d['paper'] == doc['paper'] and d['variant'] == doc['variant']) or (d['paper'] == 0 and d['kind'] in ('er', 'gt')))]
        years = []
        for year in sorted({d['year'] for d in docs}, reverse=True):
            rows = [[r['doc_id'], r['page'], r['text'], r['status']] for r in db.execute('SELECT p.doc_id,p.page,p.text,p.status FROM pages p JOIN documents d ON d.id=p.doc_id WHERE d.year=? ORDER BY p.doc_id,p.page', (year,))]
            info = write_json(output / 'index' / f'{year}.json', rows)
            info['path'] = 'index/' + info['path']
            info.update(year=year, files=sum(d['year'] == year for d in docs), papers=sum(d['year'] == year and d['kind'] == 'qp' for d in docs), pages=len(rows))
            years.append(info)
        # Reuse the existing conservative MS recognizer on a temporary database only.
        answer_map = {}
        if directories:
            from biology.library import Library
            from biology.reader import Reader
            lib = Library(temp)
            lib.pdf_path = lambda d: data / 'pdfs' / (d['sha256'] + '.pdf')
            reader = Reader(lib)
            marks = [d for d in docs if d['kind'] == 'ms']
            for i, doc in enumerate(marks, 1):
                result = reader.directory(doc['id'])
                entries = {}
                for key, entry in result.get('entries', {}).items():
                    if entry.get('segments'):
                        entries[key] = {'page': entry['segments'][0]['page'], 'complete': entry.get('complete', False), 'text': '\n'.join(s.get('text', '') for s in entry['segments']) if entry.get('complete') else ''}
                if entries:
                    answer_map[str(doc['id'])] = entries
                if i % 30 == 0:
                    print(f'MS directories: {i}/{len(marks)}', flush=True)
        write_json(output / 'answers.json', answer_map)
        write_json(output / 'catalog.json', docs)
        stats = dict(files=len(docs), papers=sum(d['kind'] == 'qp' for d in docs), pages=sum(d['page_count'] for d in docs), partial=sum(d['status'] != 'ready' for d in docs), pdf_bytes=sum(d['bytes'] for d in docs), answer_directories=len(answer_map))
        manifest = dict(schema=1, subject='9700', title='Cambridge International AS & A Level Biology', generated_at=datetime.now(timezone.utc).isoformat(), years=years, stats=stats)
        write_json(output / 'manifest.json', manifest)
        (output / '.nojekyll').touch()
        (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>9700 Biology library data</title><p>9700 Biology · student library files</p>', encoding='utf-8')
        print(json.dumps(stats, ensure_ascii=False), flush=True)
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, default=ROOT / 'student-publish')
    parser.add_argument('--skip-directories', action='store_true')
    args = parser.parse_args()
    export(args.data.resolve(), args.output.resolve(), not args.skip_directories)
