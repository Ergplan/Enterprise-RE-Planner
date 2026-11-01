#!/usr/bin/env bash
# docker compose for the Google Cloud VM: sudo tools/dev/vm.sh <compose args>, e.g.
#   sudo tools/dev/vm.sh ps     sudo tools/dev/vm.sh logs -f api     sudo tools/dev/vm.sh up -d --build
set -euo pipefail
cd "$(dirname "$0")/../.."
exec docker compose --env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml "$@"
