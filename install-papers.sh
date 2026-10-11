#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
echo '开始安装 330 个真实 PDF，约需 1 GB 可用空间（含下载缓存），请保持终端开启。'
.venv/bin/python scripts/install_seed.py "$@"
echo '安装完成。请运行 bash start.sh，然后打开 http://127.0.0.1:9700'
