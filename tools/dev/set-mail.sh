#!/usr/bin/env bash
# Set the mailbox that sends sign-in links (Google Workspace or Gmail, with an app password), on the
# server, from /opt/ergplan (VM) or ~/apps/ergplan (mini):
#     sudo bash tools/dev/set-mail.sh venture@aayuda.energy
# The app password is typed here (not shown), checked against Gmail, and only then written to .env.
set -euo pipefail
FROM="${1:?usage: set-mail.sh <sending email address>}"
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "No .env in $(pwd): run this on the server."; exit 1; }
FILES=(--env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml)
[ -f docker/compose.mini.yaml ] && [ "${ERGPLAN_SERVER:-}" = mini ] && FILES+=(-f docker/compose.mini.yaml)
printf 'App password for %s (16 letters; it is not shown): ' "$FROM"
read -r -s PW < /dev/tty; echo
PW="$(printf '%s' "$PW" | tr -d ' ')"
[[ "$PW" =~ ^[A-Za-z]{16}$ ]] || { echo "That is not a 16-letter app password; nothing changed."; exit 1; }
echo "Checking it with Gmail…"
if ! printf '%s\n%s\n' "$FROM" "$PW" | docker compose "${FILES[@]}" exec -T api python -c '
import smtplib, sys
u, p = sys.stdin.read().split()
with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
    s.login(u, p)
'; then
  unset PW
  echo "Could not sign in to Gmail (or the app is not running): nothing changed. Check the address, or create a new app password."
  exit 1
fi
ENC="$(printf '%s' "$FROM" | sed 's/@/%40/')"
tmp="$(mktemp)"
grep -vE '^(ERGPLAN_SMTP_URL|ERGPLAN_MAIL_FROM)=' .env > "$tmp" || true
printf 'ERGPLAN_SMTP_URL=smtps://%s:%s@smtp.gmail.com:465\nERGPLAN_MAIL_FROM="ergPLAN <%s>"\n' "$ENC" "$PW" "$FROM" >> "$tmp"
cat "$tmp" > .env && rm -f "$tmp" && chmod 600 .env
unset PW
docker compose "${FILES[@]}" up -d --force-recreate api worker >/dev/null 2>&1
echo "Saved. Sign-in links are now mailed from $FROM; try 'Send the link' on the sign-in page."
