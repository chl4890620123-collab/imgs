#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import PySide6' >/dev/null 2>&1; then
    "$PYTHON" -m pip install -r studio/requirements.txt
fi
if [ ! -f "saseok_studio_project.json" ]; then
    "$PYTHON" studio/bootstrap.py
fi
exec "$PYTHON" studio/app.py saseok_studio_project.json
