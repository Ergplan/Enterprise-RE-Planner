#!/usr/bin/env bash
# Deploy ergPLAN to the Google Cloud VM from this Mac (it holds the code bundle, which carries billx,
# the regulation PDFs, the IEX files and the OpenAI key; the VM gets a copy of each):
#     bash ~/Downloads/ergplan-server/vm-push.sh
# Needs the Google Cloud CLI signed in (gcloud auth login) to the project that owns the VM.
#   ERGPLAN_VM (replanner) · ERGPLAN_ZONE (asia-south2-b) · ERGPLAN_PROJECT (gcloud's current project)
#   ERGPLAN_HOST (default <ip-with-dashes>.sslip.io, which needs no DNS)
#   ERGPLAN_ANALYST (venture@aayuda.energy)
# Safe to run again: the VM keeps its settings and database; code, billx and data are refreshed.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
DL="$HOME/Downloads"
VM="${ERGPLAN_VM:-replanner}"
ZONE="${ERGPLAN_ZONE:-asia-south2-b}"
ANALYST="${ERGPLAN_ANALYST:-venture@aayuda.energy}"
say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
ask() { printf '%s [y/N] ' "$1"; read -r a; [ "$a" = y ] || [ "$a" = Y ]; }
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:$HOME/.homebrew/bin:$HOME/google-cloud-sdk/bin"

say "1/6 Google Cloud"
command -v gcloud >/dev/null || die "the Google Cloud CLI is not installed: brew install --cask google-cloud-sdk  (then: gcloud auth login)"
[ -n "$(gcloud config get-value account 2>/dev/null)" ] || die "sign in first: gcloud auth login"
PROJECT="${ERGPLAN_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
[ -n "$PROJECT" ] || die "no project: run again with ERGPLAN_PROJECT=<project id>"
G=(--project "$PROJECT" --zone "$ZONE")
gcloud compute instances describe "$VM" "${G[@]}" --format='value(status)' >/dev/null 2>&1 \
  || die "VM $VM not found in project $PROJECT, zone $ZONE (set ERGPLAN_PROJECT / ERGPLAN_ZONE)"
IP="$(gcloud compute instances describe "$VM" "${G[@]}" --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"
[ -n "$IP" ] || die "the VM has no external IP"
HOST="${ERGPLAN_HOST:-$(echo "$IP" | tr . -).sslip.io}"
echo "project $PROJECT · VM $VM ($IP) · site https://$HOST"
[ -f "$KIT/ergplan.bundle" ] && [ -f "$KIT/vm-install.sh" ] || die "ergplan.bundle and vm-install.sh must be beside this script"

say "2/6 Disk, firewall and address"
DISK="$(gcloud compute instances describe "$VM" "${G[@]}" --format='value(disks[0].source)' | sed 's|.*/||')"
SIZE="$(gcloud compute disks describe "$DISK" "${G[@]}" --format='value(sizeGb)')"
if [ "$SIZE" -lt 40 ]; then
  echo "The boot disk is ${SIZE} GB; the images, database and documents need about 25 GB."
  if ask "Resize it to 50 GB (about US\$4 a month more; a disk cannot be shrunk later)?"; then
    gcloud compute disks resize "$DISK" "${G[@]}" --size 50GB --quiet
    echo "resized (Debian grows the file system on the next boot)"; RESIZED=1
  else
    die "not enough disk for the build"
  fi
fi
gcloud compute instances add-tags "$VM" "${G[@]}" --tags http-server,https-server >/dev/null
for r in "default-allow-http:80:http-server" "default-allow-https:443:https-server"; do
  name="${r%%:*}"; rest="${r#*:}"; port="${rest%%:*}"; tag="${rest#*:}"
  if ! gcloud compute firewall-rules describe "$name" --project "$PROJECT" >/dev/null 2>&1; then
    gcloud compute firewall-rules create "$name" --project "$PROJECT" --network default \
      --allow "tcp:$port" --target-tags "$tag" --source-ranges 0.0.0.0/0 --quiet >/dev/null
    echo "opened port $port"
  fi
done
KIND="$(gcloud compute addresses list --project "$PROJECT" --filter="address=$IP" --format='value(name)' 2>/dev/null || true)"
if [ -z "$KIND" ] && [ -z "${ERGPLAN_HOST:-}" ]; then
  echo "The address $IP is ephemeral: it changes if the VM is stopped, and https://$HOST with it."
  if ask "Keep it permanently (reserve it as a static address; free while the VM runs)?"; then
    gcloud compute addresses create ergplan-ip --project "$PROJECT" --region "${ZONE%-*}" --addresses "$IP" --quiet
  fi
fi
if [ "${RESIZED:-}" = 1 ]; then
  echo "restarting the VM so the larger disk is used"
  gcloud compute instances reset "$VM" "${G[@]}" --quiet >/dev/null
fi
printf 'reaching the VM over SSH'
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if gcloud compute ssh "$VM" "${G[@]}" --quiet --command true >/dev/null 2>&1; then echo " — ok"; OK=1; break; fi
  printf '.'; sleep 10
done
[ "${OK:-}" = 1 ] || die "cannot SSH to the VM (is the default-allow-ssh firewall rule there?)"

say "3/6 Packing code (with billx), regulations, prices and settings"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir "$TMP/p"
cp "$KIT/ergplan.bundle" "$KIT/vm-install.sh" "$TMP/p/"
items=()
for i in "India_DISCOM_Tariff_Orders_Final_2026" "Tariff Orders" "Banking Rule - Uttar Pradesh.pdf"; do
  [ -e "$DL/$i" ] && items+=("$i")
done
[ ${#items[@]} -gt 0 ] && tar -C "$DL" -czf "$TMP/p/corpus.tar.gz" "${items[@]}"
iex=()
for f in "$DL"/DAM_15min_*.xlsx "$DL"/RTM_15min_*.xlsx "$DL"/GDAM_15min_*.xlsx; do [ -e "$f" ] && iex+=("$(basename "$f")"); done
[ ${#iex[@]} -gt 0 ] && tar -C "$DL" -czf "$TMP/p/iex.tar.gz" "${iex[@]}"
key="$(grep -oE 'sk-(proj|svcacct)-[A-Za-z0-9_-]{20,}' "$DL/Keys.rtf" 2>/dev/null | head -1 || true)"
if [ -z "$key" ]; then printf 'Paste the OpenAI API key (not shown): '; read -r -s key; echo; fi
[ -n "$key" ] || die "an OpenAI API key is needed"
touch "$TMP/p/env" && chmod 600 "$TMP/p/env"
cat > "$TMP/p/env" <<ENV
# ergPLAN on the Google Cloud VM — written by tools/dev/vm-push.sh on $(date '+%Y-%m-%d %H:%M'). Never commit.
ERGPLAN_ENV=prod
POSTGRES_USER=ergplan
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=ergplan
BILLX_TOKEN=$(openssl rand -hex 32)
OPENAI_API_KEY=$key
BILLX_OPENAI_API_KEY=$key
ERGPLAN_ANALYST_DOMAIN=joulewise.in
ERGPLAN_ANALYST_EMAILS=$ANALYST
ERGPLAN_WORKER_CONCURRENCY=1
ERGPLAN_SMTP_URL=
ERGPLAN_MAIL_FROM="ergPLAN <no-reply@joulewise.in>"
ENV
unset key
du -sh "$TMP/p" | awk '{print "payload " $1}'

say "4/6 Copying to the VM (the regulations are a few hundred MB)"
gcloud compute ssh "$VM" "${G[@]}" --command "rm -rf /tmp/ergplan-payload" --quiet
gcloud compute scp --recurse "$TMP/p" "$VM:/tmp/ergplan-payload" "${G[@]}" --quiet

say "5/6 Installing on the VM"
gcloud compute ssh "$VM" "${G[@]}" --quiet --command "sudo bash /tmp/ergplan-payload/vm-install.sh '$HOST' '$ANALYST'"

say "6/6 Done"
echo "Open https://$HOST and use the sign-in link printed above."
