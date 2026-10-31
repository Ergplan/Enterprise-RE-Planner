#!/usr/bin/env bash
# Independent stage review: tools/review/run.sh N [base-ref]
set -e
cd "$(dirname "$0")/../.."
PY=apps/api/.venv/bin/python; [ -x "$PY" ] || PY=python3
exec "$PY" tools/review/review.py "$@"
