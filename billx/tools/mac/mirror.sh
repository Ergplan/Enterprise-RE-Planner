#!/bin/bash
# Nightly mirror (section 3.1): the sample and golden sets and the hosted volumes to the
# external drive. Never deletes anything on the drive. Logs only paths and counts.
set -uo pipefail
DATA="${BILLX_DATA_DIR:-$HOME/billx-data}"
ENVFILE="${BILLX_REPO:-$HOME/billx}/.env"
MIRROR="${BILLX_MIRROR_VOLUME:-$(grep -E '^BILLX_MIRROR_VOLUME=' "$ENVFILE" 2>/dev/null | cut -d= -f2-)}"
LOG="$DATA/logs/mirror.log"; mkdir -p "$DATA/logs"
stamp() { date -u +%FT%TZ; }
if [ -z "$MIRROR" ] || [ ! -d "$MIRROR" ] || [ ! -w "$MIRROR" ]; then
  echo "$(stamp) FAIL external drive not mounted (BILLX_MIRROR_VOLUME='$MIRROR')" >> "$LOG"; exit 1
fi
DEST="$MIRROR/billx-mirror"; mkdir -p "$DEST"
STATUS=0
for d in golden hosted; do
  [ -d "$DATA/$d" ] || continue
  if rsync -a "$DATA/$d/" "$DEST/$d/"; then
    echo "$(stamp) ok $d ($(find "$DATA/$d" -type f | wc -l | tr -d ' ') files)" >> "$LOG"
  else
    echo "$(stamp) FAIL $d" >> "$LOG"; STATUS=1
  fi
done
exit $STATUS
