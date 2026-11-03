#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Install dependencies explicitly during setup; startup must also work offline.
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python server.py
fi
if [ -x "../../.venv-image/bin/python" ]; then
  exec ../../.venv-image/bin/python server.py
fi
exec python3 server.py
