#!/usr/bin/env bash
# Stage 7 browser end-to-end on real bills, isolated from the dev stack: billx stub (stored readings),
# an API and a worker on the ergplan_e2e database, a second Next dev server, then the Playwright test.
#   tools/dev/e2e-journey.sh            (needs Postgres, the real bills and their stored billx readings)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API="$ROOT/apps/api"
LOG="${E2E_LOG_DIR:-$(mktemp -d)}"
DB="postgresql+psycopg://ergplan:ergplan@localhost:5432/ergplan_e2e"
export DATABASE_URL="$DB"
pids=()
killtree() { local c; for c in $(pgrep -P "$1" 2>/dev/null); do killtree "$c"; done; kill "$1" 2>/dev/null || true; }
cleanup() { for p in "${pids[@]}"; do killtree "$p"; done; }
trap cleanup EXIT
(cd "$API" && .venv/bin/alembic upgrade head >/dev/null)
"$API/.venv/bin/python" - <<'PY'
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ["DATABASE_URL"])
with e.begin() as c:
    names = [r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"))]
    c.execute(text("truncate " + ", ".join(names) + " cascade"))
PY
"$API/.venv/bin/uvicorn" --app-dir "$ROOT/tools/dev" billx_stub:app --port 8091 >"$LOG/billx.log" 2>&1 & pids+=($!)
(cd "$API" && BILLX_URL=http://localhost:8091 BILLX_TOKEN=stub ERGPLAN_WEB_INTERNAL_URL=http://localhost:3010 \
  ERGPLAN_PUBLIC_URL=http://localhost:3010 .venv/bin/uvicorn ergplan.platform.app:app --port 8010 >"$LOG/api.log" 2>&1) & pids+=($!)
(cd "$API" && .venv/bin/python -m ergplan.platform.worker >"$LOG/worker.log" 2>&1) & pids+=($!)
(cd "$ROOT/apps/web" && API_URL=http://localhost:8010 NEXT_DIST_DIR=.next-e2e npx next dev -p 3010 >"$LOG/web.log" 2>&1) & pids+=($!)
for url in http://localhost:8091/v1/health http://localhost:8010/health http://localhost:3010/; do
  for _ in $(seq 1 90); do curl -sf -o /dev/null "$url" && break; sleep 2; done
done
(cd "$API" && E2E_WEB_URL=http://localhost:3010 E2E_API_URL=http://localhost:8010 \
  .venv/bin/pytest -o addopts="" -m slow -q tests/e2e/test_stage7_journey.py "$@")
echo "logs: $LOG"
