#!/bin/bash
# Activates the nightly mirror job (the evaluation job stays inactive until Stage 11).
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/com.joulewise.billx.mirror.plist"
DEST="$HOME/Library/LaunchAgents/com.joulewise.billx.mirror.plist"
cp "$SRC" "$DEST"
launchctl bootout "gui/$(id -u)/com.joulewise.billx.mirror" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "nightly mirror active (01:30 daily); log: ~/billx-data/logs/mirror.log"
