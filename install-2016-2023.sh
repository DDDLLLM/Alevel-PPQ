#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
echo '同步 9700 的 2016–2023 年全部考季目录并下载；完成情况以实际报告为准。'
.venv/bin/python scripts/install_range.py "$@"
