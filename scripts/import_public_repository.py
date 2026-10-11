#!/usr/bin/env python3
"""Import a public repository checkout. No filename guessing or blob modification."""
import argparse
import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from biology.library import Library, metadata
from biology.sources import record_run

p=argparse.ArgumentParser()
p.add_argument('checkout');p.add_argument('--data');p.add_argument('--limit',type=int)
args=p.parse_args()
repo=Path(args.checkout).resolve()
commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
names=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD','--','Biology - 9700'],text=True).splitlines()
lib=Library(args.data)
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(lib.home/'logs'/'public-repository.log',encoding='utf-8')])
done=duplicate=failed=0
for name in names:
    path=repo/name
    if not path.is_file():
        continue
    try:
        metadata(path.name)
    except ValueError:
        continue
    if args.limit is not None and done+duplicate>=args.limit:
        break
    url='https://github.com/vascodegraaff/CIE-A-level-past-papers/blob/'+commit+'/'+quote(name)
    try:
        result=lib.import_pdf(path,source='github-public-archive',url=url,original_id=commit+':'+name)
        if result['duplicate']: duplicate+=1
        else: done+=1
        logging.info('%s %s',path.name,result)
    except Exception as exc:
        failed+=1;logging.error('%s %s',path.name,exc)
record_run(lib,'github-public-archive','partial' if failed else 'finished',f'commit {commit}; 新增 {done}, 已存在 {duplicate}, 失败 {failed}; 仅代表实际导入，不代表整年完整')
print({'new':done,'duplicate':duplicate,'failed':failed})
sys.exit(bool(failed))
