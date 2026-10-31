#!/usr/bin/env bash
# Re-copies ergOS Harmony from a checkout of Ergplan/designsystem (default ../designsystem or $DS_REPO).
set -e
cd "$(dirname "$0")/../.."
SRC="${DS_REPO:-../designsystem}/design-system"
[ -d "$SRC" ] || { echo "Clone github.com/Ergplan/designsystem next to this repo or set DS_REPO"; exit 1; }
cp "$SRC/tokens/tokens.css" "$SRC/harmony.css" "$SRC/harmony.js" "$SRC/harmony.d.ts" apps/web/public/vendor/harmony/
cp "$SRC/assets/logo/joulewise-dark.svg" "$SRC/assets/logo/joulewise-light.svg" "$SRC/assets/logo/joulewise-mark.svg" apps/web/public/brand/
echo "Vendored from github.com/Ergplan/designsystem @ $(git -C "$SRC/.." rev-parse --short HEAD)" > apps/web/public/vendor/harmony/ORIGIN.txt
echo "Harmony synced"
