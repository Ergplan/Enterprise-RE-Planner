#!/bin/bash
# Starts builder session N in its own worktree and tmux window, beside the shared
# watcher and log windows (section 3.1). Every window survives a closed terminal.
#
#   tools/mac/session.sh N BRANCH "Run day D, session X of docs/build-prompt.md"
#
# Claude Code runs non-interactively under the allow-list in .claude/settings.json.
# When the Max plan's limit is reached it switches to ANTHROPIC_CONSOLE_KEY if one is
# set in .env, otherwise waits and resumes. Time lost to limits goes in the log.
set -euo pipefail
N="${1:?session number}"; BRANCH="${2:?branch}"; PROMPT="${3:?prompt}"
REPO="${BILLX_REPO:-$HOME/billx}"
WT="$HOME/billx-worktrees/$BRANCH"
LOGS="$HOME/billx-data/logs"; mkdir -p "$LOGS"
command -v tmux >/dev/null || { echo "tmux is not installed" >&2; exit 1; }
command -v claude >/dev/null || { echo "the claude CLI is not on PATH" >&2; exit 1; }

if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "$BRANCH" "$WT" 2>/dev/null || git -C "$REPO" worktree add "$WT" "$BRANCH"
  (cd "$WT" && python3 -m uv venv -q --python 3.12 .venv && python3 -m uv pip install -q --python .venv/bin/python -e '.[dev]')
fi

tmux has-session -t billx 2>/dev/null || {
  tmux new-session -d -s billx -n watcher "cd '$REPO' && .venv/bin/python tools/watch/watch.py"
  tmux new-window -t billx -n logs "tail -F $LOGS/*.log"
}

RUNNER="$LOGS/session-$N.run.sh"
printf '%s' "$PROMPT" > "$LOGS/session-$N.prompt"
cat > "$RUNNER" <<RUN
#!/bin/bash
cd '$WT'
LOG='$LOGS/session-$N.log'
while true; do
  echo "\$(date -u +%FT%TZ) start session $N on $BRANCH" >> "\$LOG"
  caffeinate -dimsu claude -p "\$(cat '$LOGS/session-$N.prompt')" --output-format stream-json --verbose >> "\$LOG" 2>&1 && break
  if tail -n 50 "\$LOG" | grep -qiE 'usage limit|rate limit|limit reached'; then
    KEY=\$(grep -E '^ANTHROPIC_CONSOLE_KEY=' '$REPO/.env' | cut -d= -f2-)
    if [ -n "\$KEY" ] && [ -z "\${ANTHROPIC_API_KEY:-}" ]; then
      echo "\$(date -u +%FT%TZ) plan limit: switching to the Console key" >> "\$LOG"
      export ANTHROPIC_API_KEY="\$KEY"; continue
    fi
    echo "\$(date -u +%FT%TZ) plan limit: waiting 15 minutes" >> "\$LOG"; sleep 900; continue
  fi
  echo "\$(date -u +%FT%TZ) session $N stopped with an error; see above" >> "\$LOG"; break
done
RUN
chmod +x "$RUNNER"
tmux new-window -t billx -n "session-$N" "$RUNNER"
echo "session $N started in tmux window billx:session-$N ($WT); log $LOGS/session-$N.log"
