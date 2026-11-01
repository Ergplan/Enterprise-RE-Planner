#!/usr/bin/env bash
# docker compose for the Mac mini server: tools/dev/mini.sh <compose args>, e.g.
#   tools/dev/mini.sh up -d --build      tools/dev/mini.sh ps      tools/dev/mini.sh logs -f api
#   tools/dev/mini.sh exec api python -m ergplan.platform.signin someone@company.in
set -euo pipefail
cd "$(dirname "$0")/../.."
exec docker compose --env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml \
  -f docker/compose.mini.yaml "$@"
