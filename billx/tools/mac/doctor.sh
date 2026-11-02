#!/bin/bash
# Checks the build Mac (section 3.1). Prints pass or fail per item; never prints a secret.
# Exit status is the number of failures (0 = everything passes).
set -u
REPO="${BILLX_REPO:-$HOME/billx}"
DATA="${BILLX_DATA_DIR:-$HOME/billx-data}"
MIRROR="${BILLX_MIRROR_VOLUME:-}"
FAILS=0
pass() { printf 'pass  %s\n' "$1"; }
fail() { printf 'FAIL  %s%s\n' "$1" "${2:+  ($2)}"; FAILS=$((FAILS + 1)); }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$name"; else fail "$name"; fi; }
envval() { grep -E "^$1=" "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed -e "s/^[[:space:]]*//" -e "s/[[:space:]]*$//" -e "s/^\"\(.*\)\"$/\1/" -e "s/^'\(.*\)'$/\1/"; }  # an empty quoted value is not set

echo "== machine"
check "Apple silicon" test "$(uname -m)" = arm64
fdesetup status | grep -q "FileVault is On" && pass "FileVault on" || fail "FileVault on" "System Settings > Privacy & Security > FileVault"
[ "$(pmset -g | awk '$1=="sleep"{print $2}')" = 0 ] && pass "system sleep off" || fail "system sleep off" "System Settings > Energy: prevent automatic sleeping"
[ "$(pmset -g | awk '$1=="autorestart"{print $2}')" = 1 ] && pass "start after power failure" || fail "start after power failure" "System Settings > Energy"

echo "== tools"
PY312="$(python3 -m uv python find 3.12 2>/dev/null)"
[ -n "$PY312" ] && pass "python 3.12" || fail "python 3.12"
check "project venv" test -x "$REPO/.venv/bin/python"
for t in git gh tmux tesseract; do command -v "$t" >/dev/null && pass "$t" || fail "$t" "not installed"; done
{ command -v cloudflared || command -v tailscale; } >/dev/null && pass "cloudflared or tailscale" || fail "cloudflared or tailscale" "not installed"
command -v claude >/dev/null && pass "claude CLI" || fail "claude CLI" "Claude Code command-line tool not on PATH"
if docker info >/dev/null 2>&1; then
  pass "docker running"
  CPUS=$(docker info --format '{{.NCPU}}'); MEM=$(docker info --format '{{.MemTotal}}')
  HALF=$(( $(sysctl -n hw.memsize) / 2 - 1073741824 ))
  [ "$CPUS" -ge 8 ] && pass "docker cpus >= 8" || fail "docker cpus >= 8" "has $CPUS"
  [ "$MEM" -ge "$HALF" ] && pass "docker memory >= half the Mac" || fail "docker memory >= half the Mac" "has $((MEM / 1073741824)) GB"
else
  fail "docker running" "start Docker Desktop"
fi

echo "== folders"
check "repository at $REPO" test -d "$REPO/.git"
for d in golden workspaces hosted; do check "$DATA/$d" test -d "$DATA/$d"; done
case "$(cd "$DATA" && pwd -P)/" in "$(cd "$REPO" && pwd -P)/"*) fail "bill data outside the repository";; *) pass "bill data outside the repository";; esac
check "client identifiers list" test -s "$DATA/client-identifiers.txt"
if [ -n "$MIRROR" ] && [ -d "$MIRROR" ] && [ -w "$MIRROR" ]; then pass "external drive mounted ($MIRROR)"; else fail "external drive mounted" "set BILLX_MIRROR_VOLUME in .env to the drive, e.g. /Volumes/BillxMirror"; fi

echo "== keys (presence only)"
if [ -f "$REPO/.env" ]; then
  [ "$(stat -f %Lp "$REPO/.env")" = 600 ] && pass ".env private (600)" || fail ".env private (600)"
  git -C "$REPO" check-ignore -q .env && pass ".env ignored by git" || fail ".env ignored by git"
  for k in BILLX_OPENAI_API_KEY BILLX_ANTHROPIC_API_KEY OPENAI_BUILD_REVIEW_KEY ESGOS_REGISTRY_KEY CLOUDFLARE_TUNNEL_TOKEN ANTHROPIC_CONSOLE_KEY; do
    [ -n "$(envval "$k")" ] && pass "$k set" || fail "$k set"
  done
else
  fail ".env exists" "$REPO/.env"
fi

echo "== model ids (one one-token call each)"
for pair in "BILLX_MODEL_A:" "BILLX_MODEL_B:" "BILLX_MODEL_REVIEW:OPENAI_BUILD_REVIEW_KEY" "BILLX_MODEL_ASSISTANT:"; do
  var="${pair%%:*}"; keyvar="${pair#*:}"; spec="$(envval "$var")"
  if [ -z "$spec" ]; then fail "$var configured"; continue; fi
  out="$(cd "$REPO" && .venv/bin/python -m billx.reader.providers.ping "$spec" $keyvar 2>/dev/null)"
  [ "${out%% *}" = ok ] && pass "$var $spec" || fail "$var $spec" "${out#*: }"
done

echo "== jobs and checks"
launchctl print "gui/$(id -u)/com.joulewise.billx.mirror" >/dev/null 2>&1 && pass "nightly mirror job active" || fail "nightly mirror job active" "tools/mac/install-jobs.sh"
check "nightly eval job written (inactive until Stage 11)" test -f "$REPO/tools/mac/com.joulewise.billx.eval.plist"
check "Claude Code allow-list" test -f "$REPO/.claude/settings.json"
if [ -f "$REPO/.status/ocr-check.json" ]; then
  for p in macos-arm64 linux-arm64 linux-amd64; do
    grep -q "\"$p\": \"\(paddleocr\|rapidocr\)\"" "$REPO/.status/ocr-check.json" && pass "local OCR reads a synthetic bill on $p" || fail "local OCR reads a synthetic bill on $p"
  done
else
  fail "local OCR check run" "tools/mac/ocr_check.sh"
fi

echo
[ "$FAILS" -eq 0 ] && echo "doctor: all checks pass" || echo "doctor: $FAILS failing"
exit "$FAILS"
