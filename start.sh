#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f "package.json" ] && [ ! -d "node_modules/mupdf" ]; then
  npm install --omit=dev --no-audit --no-fund
fi

if [ -x "../../.venv-image/bin/python" ]; then
  exec ../../.venv-image/bin/python server.py
fi

exec python3 server.py
