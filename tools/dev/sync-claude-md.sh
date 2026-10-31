#!/usr/bin/env bash
# Regenerates CLAUDE.md from sections 2–5 of docs/MASTER-PROMPT.md. The watcher diff-checks the result.
set -e
cd "$(dirname "$0")/../.."
python3 - <<'PY'
src = open('docs/MASTER-PROMPT.md').read()
start = src.index('## 2. Operating rules'); end = src.index('## 6. Plan')
body = src[start:end].rstrip().rstrip('-').rstrip()
header = open('CLAUDE.md').read().split('\n## 2. Operating rules')[0]
open('CLAUDE.md','w').write(header + '\n' + body + '\n')
PY
echo "CLAUDE.md synced"
