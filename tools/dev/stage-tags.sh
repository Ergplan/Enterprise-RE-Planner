#!/usr/bin/env bash
# Stage tags (stage-N-start / stage-N-done) live in docs/stage-tags.md because the build workspace
# cannot push tags. `tools/dev/stage-tags.sh record NAME` appends HEAD; `tools/dev/stage-tags.sh apply`
# creates every recorded tag locally (run on the Mac mini, then `git push --tags`).
set -e
cd "$(dirname "$0")/../.."
F=docs/stage-tags.md
[ -f "$F" ] || printf "# Stage tags\n\nRecorded by tools/dev/stage-tags.sh. \`apply\` recreates them as git tags.\n\n| Tag | Commit |\n| --- | --- |\n" > "$F"
case "$1" in
  record) git tag -f "$2" HEAD >/dev/null; sed -i.bak "/^| $2 |/d" "$F" && rm -f "$F.bak"; echo "| $2 | $(git rev-parse HEAD) |" >> "$F"; echo "recorded $2";;
  apply) grep -E '^\| stage-' "$F" | while IFS='|' read -r _ tag sha _; do git tag -f $(echo $tag) $(echo $sha); done; echo "tags applied";;
  *) echo "usage: $0 record NAME | apply"; exit 1;;
esac
