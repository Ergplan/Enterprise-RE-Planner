#!/usr/bin/env bash
# Installs or updates ergPLAN on the Google Cloud VM (Debian), as root, from a payload directory
# (tools/dev/vm-push.sh from the Mac, or the builder over SSH from the mini) holding ergplan.bundle and
# optionally corpus.tar.gz, iex.tar.gz and env (first install only). billx comes with the code (billx/):
#   sudo bash /tmp/ergplan-payload/vm-install.sh <hostname> <first analyst email>
# Safe to run again: keeps /opt/ergplan/.env, the database and data/; updates code and billx.
set -euo pipefail
HOST="${1:?hostname}"
ANALYST="${2:?analyst email}"
P="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/ergplan
BILLX="$DEST/billx"  # billx ships inside the repository
say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
cleanup() { rm -rf "$P"; }  # the payload carries a copy of the settings: never leave it behind
trap cleanup EXIT

say "1/9 Swap (4 GB, for image builds on 8 GB of memory)"
if [ -z "$(swapon --show 2>/dev/null)" ] && [ "${SKIP_SWAP:-}" != 1 ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "swap on"
else
  echo "swap present"
fi

say "2/9 Docker and git"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  if ! { apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null; }; then
    echo "Docker's repository failed; using Debian's packages"
    rm -f /etc/apt/sources.list.d/docker.list
    apt-get update -qq && apt-get install -y -qq docker.io docker-compose >/dev/null
  fi
  systemctl enable --now docker
fi
command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git >/dev/null; }
docker compose version

say "3/9 Code → $DEST, billx → $BILLX"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch -q "$P/ergplan.bundle" main
  git -C "$DEST" merge -q --ff-only FETCH_HEAD || die "$DEST has local changes"
else
  git clone -q -b main "$P/ergplan.bundle" "$DEST"
  git -C "$DEST" remote set-url origin https://github.com/Ergplan/Enterprise-RE-Planner.git
fi
echo "ergPLAN at $(git -C "$DEST" log --oneline -1)"
[ -f "$P/billx.tar.gz" ] && echo "billx.tar.gz ignored: billx is built from $BILLX, in the repository"
[ -f "$BILLX/docker/engine.Dockerfile" ] || die "billx is missing at $BILLX"
cd "$DEST"

say "4/9 Settings (.env, root only)"
setkey() {  # setkey NAME VALUE: replace or add a line in .env without printing it
  local tmp; tmp="$(mktemp)"
  grep -v "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
}
if [ ! -f .env ]; then
  [ -f "$P/env" ] || die "no settings in the payload"
  install -m 600 "$P/env" .env
  echo "wrote .env"
else
  echo "kept .env"
fi
chmod 600 .env
setkey ERGPLAN_PUBLIC_URL "https://$HOST"
setkey SITE_ADDRESS "$HOST"
setkey BILLX_REPO "$BILLX"
grep -q '^ERGPLAN_WORKER_CONCURRENCY=' .env || setkey ERGPLAN_WORKER_CONCURRENCY 1
grep -q "^ERGPLAN_ANALYST_EMAILS=" .env || setkey ERGPLAN_ANALYST_EMAILS "$ANALYST"

say "5/9 Regulation PDFs and IEX prices"
mkdir -p data/corpus data/iex
for f in "$P"/corpus.tar*; do [ -f "$f" ] && tar -xf "$f" -C data/corpus && echo "corpus unpacked"; done
for f in "$P"/iex.tar*; do [ -f "$f" ] && tar -xf "$f" -C data/iex && echo "IEX files unpacked"; done
true

say "6/9 Building and starting (the first build takes 15–30 minutes on 2 vCPUs)"
D=(docker compose --env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml)
"${D[@]}" up -d --build
printf 'waiting for the API'
for _ in $(seq 1 120); do
  if "${D[@]}" exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    echo " — up"; break
  fi
  printf '.'; sleep 5
done
"${D[@]}" exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1 \
  || die "the API did not come up: ${D[*]} logs api"

say "7/9 Regulations, rulebooks, prices"
"${D[@]}" exec -T api python -m ergplan.documents.corpus --root /data/corpus/India_DISCOM_Tariff_Orders_Final_2026 | sed -n '1,3p'  # not head: it would close the pipe early
"${D[@]}" exec -T api python -m ergplan.rulebook.cli restore --actor install@ergplan | tail -2
if ls data/iex/*.xlsx >/dev/null 2>&1; then
  "${D[@]}" exec -T api sh -c 'python -m ergplan.intake.iex_loader /data/iex/*.xlsx' || echo "some price files were refused"
fi

say "8/9 Nightly backup at 02:30 (/var/backups/ergplan, 14 days)"
cat > /etc/cron.d/ergplan-backup <<CRON
30 2 * * * root cd $DEST && BACKUP_DIR=/var/backups/ergplan tools/dev/backup.sh >> /var/log/ergplan-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/ergplan-backup && echo scheduled

say "9/9 First sign-in link"
LINK="$("${D[@]}" exec -T api python -m ergplan.platform.signin "$ANALYST" --next /rulebooks)"
cat <<DONE

==============================================================================
ergPLAN is running:  https://$HOST
(the certificate is issued on the first visit; allow a minute)

Sign in as $ANALYST (analyst). This link works once, for 15 minutes:
$LINK

On the VM, from $DEST:
  sudo tools/dev/vm.sh ps · sudo tools/dev/vm.sh logs -f api
  sudo tools/dev/vm.sh exec api python -m ergplan.platform.signin someone@company.in
==============================================================================
DONE
