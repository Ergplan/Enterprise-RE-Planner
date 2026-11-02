#!/bin/bash
# Nightly evaluation, active from Stage 11 (section 12.2). `billx eval` arrives in Stage 1.7.
set -euo pipefail
REPO="${BILLX_REPO:-$HOME/billx}"
"$REPO/tools/mac/mirror.sh"
cd "$REPO"
DAY=$(date +%F); BRANCH="accuracy-$DAY"
git fetch -q origin main && git worktree add -q -B "$BRANCH" "$HOME/billx-worktrees/$BRANCH" origin/main
cd "$HOME/billx-worktrees/$BRANCH"
"$REPO/.venv/bin/billx" eval --set golden --report "docs/accuracy/$DAY.md"
git add "docs/accuracy/$DAY.md" && git commit -qm "Nightly accuracy report $DAY" && git push -q -u origin "$BRANCH"
gh pr create --fill --base main --head "$BRANCH"
