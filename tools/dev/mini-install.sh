#!/usr/bin/env bash
# ergPLAN server on this Mac mini (1 Nov 2026). Run it from Terminal:
#     bash ~/Downloads/ergplan-server/install.sh
# Safe to run again: it updates the code from the bundle beside it, keeps .env and the database,
# and only adds what is missing. Nothing it reads or writes leaves this Mac except the OpenAI calls the
# app makes and the Docker image downloads.
#   ERGPLAN_DIR   where the app lives          (default ~/apps/ergplan)
#   BILLX_DIR     your billx checkout          (default ~/billx)
#   ERGPLAN_ANALYST  the first analyst's email (default venture@aayuda.energy)
#   HTTP_PORT     the port the app is served on (default 80)
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
DL="$HOME/Downloads"
DEST="${ERGPLAN_DIR:-$HOME/apps/ergplan}"
BILLX_DIR="${BILLX_DIR:-$HOME/billx}"
ANALYST="${ERGPLAN_ANALYST:-venture@aayuda.energy}"
PORT="${HTTP_PORT:-}"
if [ -z "$PORT" ] && [ -f "$DEST/.env" ]; then PORT="$(grep -E '^HTTP_PORT=' "$DEST/.env" | cut -d= -f2 || true)"; fi
PORT="${PORT:-80}"
say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:$HOME/.homebrew/bin:$HOME/.orbstack/bin"

say "1/8 Checking Docker, git and billx"
command -v git >/dev/null || die "git is missing: run  xcode-select --install  and then this script again."
command -v docker >/dev/null || die "Docker is not installed. Install Docker Desktop for Mac (Apple silicon) or OrbStack, start it, then run this script again."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Open Docker Desktop (or OrbStack), wait until it is running, then run this script again."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing: update Docker Desktop."
[ -f "$BILLX_DIR/docker/engine.Dockerfile" ] || die "billx not found at $BILLX_DIR (run again with BILLX_DIR=/path/to/billx)."
[ -f "$KIT/ergplan.bundle" ] || die "ergplan.bundle is missing beside this script."
if command -v lsof >/dev/null; then
  busy="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1}' | grep -viE '^(com\.docke|docker|vpnkit|orbstack)' | sort -u | tr '\n' ' ' || true)"
  [ -z "$busy" ] || die "port $PORT is already used by: $busy— run again with another port, e.g.  HTTP_PORT=8088 bash $0"
fi

say "2/8 Code → $DEST"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch -q "$KIT/ergplan.bundle" main
  git -C "$DEST" merge -q --ff-only FETCH_HEAD || die "$DEST has local changes that conflict with the update; commit or stash them first."
else
  mkdir -p "$(dirname "$DEST")"
  git clone -q -b main "$KIT/ergplan.bundle" "$DEST"
  git -C "$DEST" remote set-url origin https://github.com/Ergplan/Enterprise-RE-Planner.git
fi
cd "$DEST"
echo "code at $(git log --oneline -1)"

say "3/8 Settings (.env, readable only by you)"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo localhost)"
URL="http://$IP"; [ "$PORT" = 80 ] || URL="$URL:$PORT"
if [ ! -f .env ]; then
  key="$(grep -oE 'sk-(proj|svcacct)-[A-Za-z0-9_-]{20,}' "$DL/Keys.rtf" 2>/dev/null | head -1 || true)"
  if [ -z "$key" ]; then
    printf 'No OpenAI key found in ~/Downloads/Keys.rtf. Paste the OpenAI API key (it is not shown): '
    read -r -s key; echo
  fi
  [ -n "$key" ] || die "an OpenAI API key is needed (voice, explanations, the regulation reader)."
  touch .env && chmod 600 .env  # only you can read it, before anything is written into it
  cat > .env <<ENV
# ergPLAN on the Mac mini — written by tools/dev/mini-install.sh on $(date '+%Y-%m-%d %H:%M'). Never commit.
ERGPLAN_ENV=prod
ERGPLAN_PUBLIC_URL=$URL
SITE_ADDRESS=:80
HTTP_PORT=$PORT
POSTGRES_USER=ergplan
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=ergplan
BILLX_REPO=$BILLX_DIR
BILLX_TOKEN=$(openssl rand -hex 32)
OPENAI_API_KEY=$key
BILLX_OPENAI_API_KEY=$key
ERGPLAN_ANALYST_DOMAIN=joulewise.in
ERGPLAN_ANALYST_EMAILS=$ANALYST
ERGPLAN_WORKER_CONCURRENCY=4
# Sign-in mail: smtps://user:app-password@smtp.example.com:465 ; empty = links are issued by the
# operator (tools/dev/mini.sh exec api python -m ergplan.platform.signin someone@company.in)
ERGPLAN_SMTP_URL=
ERGPLAN_MAIL_FROM="ergPLAN <no-reply@joulewise.in>"
ENV
  unset key
  echo "wrote .env (served at $URL)"
else
  old="$(grep -E '^ERGPLAN_PUBLIC_URL=http://' .env | cut -d= -f2- || true)"
  if [ -n "$old" ] && [ "$old" != "$URL" ]; then
    tmp="$(mktemp)"; sed "s|^ERGPLAN_PUBLIC_URL=.*|ERGPLAN_PUBLIC_URL=$URL|" .env > "$tmp" && cat "$tmp" > .env; rm -f "$tmp"
    echo "the Mac's address changed: $old → $URL"
  else
    echo "kept .env"
  fi
fi

say "4/8 Regulation PDFs and IEX prices from ~/Downloads"
mkdir -p data/corpus data/iex
for item in "India_DISCOM_Tariff_Orders_Final_2026" "Tariff Orders" "Banking Rule - Uttar Pradesh.pdf"; do
  if [ -e "$DL/$item" ]; then rsync -a "$DL/$item" data/corpus/; echo "copied $item"; else echo "not found: ~/Downloads/$item"; fi
done
for f in "$DL"/DAM_15min_*.xlsx "$DL"/RTM_15min_*.xlsx "$DL"/GDAM_15min_*.xlsx; do
  [ -e "$f" ] && cp -n "$f" data/iex/ && echo "copied $(basename "$f")"
done
true

say "5/8 Building and starting (the first time takes 10–20 minutes)"
M=tools/dev/mini.sh
$M up -d --build
printf 'waiting for the API'
for _ in $(seq 1 90); do
  if $M exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    echo " — up"; break
  fi
  printf '.'; sleep 5
done
$M exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1 \
  || die "the API did not come up; see: tools/dev/mini.sh logs api"

say "6/8 Registering the regulations and restoring the approved rulebooks"
$M exec -T api python -m ergplan.documents.corpus --root /data/corpus/India_DISCOM_Tariff_Orders_Final_2026
$M exec -T api python -m ergplan.rulebook.cli restore --actor install@ergplan | tail -3

say "7/8 Loading IEX prices"
if ls data/iex/*.xlsx >/dev/null 2>&1; then
  $M exec -T api sh -c 'python -m ergplan.intake.iex_loader /data/iex/*.xlsx' || echo "some price files were refused (see above)"
else
  echo "no IEX files found; an analyst can upload them in the app (Prices)"
fi

say "8/8 Nightly backup at 02:30 (pg_dump and data/ → ~/ergplan-backups, 14 days)"
PLIST="$HOME/Library/LaunchAgents/in.joulewise.ergplan.backup.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/ergplan-backups"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>in.joulewise.ergplan.backup</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DEST/tools/dev/backup.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:$HOME/.homebrew/bin:$HOME/.orbstack/bin:/usr/bin:/bin</string>
    <key>BACKUP_DIR</key><string>$HOME/ergplan-backups</string>
    <key>ERGPLAN_SERVER</key><string>mini</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$HOME/ergplan-backups/backup.log</string>
  <key>StandardErrorPath</key><string>$HOME/ergplan-backups/backup.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" && echo "scheduled (remove: launchctl unload $PLIST && rm $PLIST)"

LINK="$($M exec -T api python -m ergplan.platform.signin "$ANALYST" --next /rulebooks)"
cat <<DONE

==============================================================================
ergPLAN is running on this Mac:  $URL
(from other machines on the same network; on this Mac also http://localhost$( [ "$PORT" = 80 ] || echo ":$PORT" ))

Sign in as $ANALYST (analyst) — this link works once, for 15 minutes:
$LINK

More sign-in links (no mail server is set up yet):
  cd $DEST && tools/dev/mini.sh exec api python -m ergplan.platform.signin someone@company.in
Status / logs / stop:
  tools/dev/mini.sh ps  ·  tools/dev/mini.sh logs -f api  ·  tools/dev/mini.sh stop
Keep it up: Docker Desktop → Settings → General → "Start Docker Desktop when you sign in",
and System Settings → Energy → "Prevent automatic sleeping when the display is off".
==============================================================================
DONE
