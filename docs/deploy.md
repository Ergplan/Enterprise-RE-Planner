# Deploying ergPLAN

## The Mac mini (the server, from 1 Nov 2026)

Prerequisites on the mini: Docker Desktop (or OrbStack) running, git, the billx checkout at `~/billx`,
and in `~/Downloads`: `ergplan-server/` (this kit), `Keys.rtf` (the OpenAI key is read from it, never
printed), `India_DISCOM_Tariff_Orders_Final_2026/`, `Tariff Orders/`, `Banking Rule - Uttar Pradesh.pdf`,
and the IEX `DAM_15min_*.xlsx` / `RTM_15min_*.xlsx` files.

```bash
bash ~/Downloads/ergplan-server/install.sh
```

It installs the code at `~/apps/ergplan` and writes `.env` (mode 600), builds and starts the stack
(first time 10–20 minutes), registers the regulations, restores the approved rulebooks, loads the IEX
prices, schedules the nightly backup and prints the address (`http://<the mini's address>`) with a
one-time sign-in link for the first analyst. Running it again updates the code from a newer kit and keeps
`.env` and the database.

Day to day, from `~/apps/ergplan`:

| What | Command |
| --- | --- |
| Status, logs | `tools/dev/mini.sh ps` · `tools/dev/mini.sh logs -f api` |
| A sign-in link for someone (no mail server yet) | `tools/dev/mini.sh exec api python -m ergplan.platform.signin someone@company.in` |
| Stop, start | `tools/dev/mini.sh stop` · `tools/dev/mini.sh up -d` |
| Update from GitHub instead of a kit | `git pull && tools/dev/mini.sh up -d --build` |
| Backup now | `ERGPLAN_SERVER=mini BACKUP_DIR=~/ergplan-backups tools/dev/backup.sh` |

Keep it up: Docker Desktop → Settings → General → "Start Docker Desktop when you sign in"; System
Settings → Energy → prevent automatic sleeping. Sign-in mail: set `ERGPLAN_SMTP_URL`
(`smtps://user:app-password@smtp.example.com:465`) in `.env`, then `tools/dev/mini.sh up -d`.
To reach it from outside the office, put a hostname in front (Cloudflare Tunnel, or a router port
forward with `SITE_ADDRESS=<hostname>`, `ERGPLAN_PUBLIC_URL=https://<hostname>` and port 443 published),
so Caddy serves https.

# The Google Cloud VM `replanner` (asia-south2-b, from 1 Nov 2026)

How code reaches it: the builder commits and pushes to GitHub, then updates the VM over SSH from the
Mac mini (the build workspace cannot open SSH; the mini can). Each update copies a git bundle of `main`
and runs `tools/dev/vm-install.sh`, which fast-forwards `/opt/ergplan`, rebuilds and restarts the stack
and keeps `.env`, the database and `data/`. The first install also carries billx (from `~/billx`), the
regulation PDFs, the IEX files and the settings (the OpenAI key read on the mini from `Keys.rtf`, never
printed; the payload is deleted from the VM after the install).

Once, in the Console: the project-wide SSH key `ergplan` (Compute Engine → Metadata → SSH keys), a
firewall rule for TCP 80 and 443, a 50 GB boot disk, and (recommended) the external address reserved as
static. The site is `https://<ip-with-dashes>.sslip.io` (no DNS needed; Caddy obtains the certificate)
until a jouleWise hostname is pointed at the address.

On the VM, from `/opt/ergplan`: `sudo tools/dev/vm.sh ps`, `sudo tools/dev/vm.sh logs -f api`,
`sudo tools/dev/vm.sh exec api python -m ergplan.platform.signin someone@company.in`. Backups: root's
cron at 02:30 into `/var/backups/ergplan` (14 days). From a Mac with the Google Cloud CLI signed in,
`tools/dev/vm-push.sh` does the same install without the builder.

# The Google Cloud VM, by hand (Stage 8 runbook)

The stack is the same Compose file as on the laptop, with `docker/compose.prod.yaml` on top: only Caddy is
reachable from outside (80/443, automatic TLS for the jouleWise hostname); the API runs with
`ERGPLAN_ENV=prod` (sign-in by email link, development headers ignored, ownership enforced).

## 1. The VM (once)

```bash
gcloud compute instances create ergplan \
  --project=<project> --zone=asia-south2-a \
  --machine-type=e2-standard-4 --boot-disk-size=100GB \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --tags=http-server,https-server
gcloud compute firewall-rules create ergplan-web --allow=tcp:80,tcp:443 --target-tags=http-server,https-server
```

Point the hostname (for example `plan.joulewise.in`) at the VM's external IP (an A record) before the
first start, so Caddy can obtain the certificate.

## 2. Software and code

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
sudo mkdir -p /opt/ergplan && sudo chown $USER /opt/ergplan
git clone https://github.com/Ergplan/Enterprise-RE-Planner /opt/ergplan
git clone <billx repository> /opt/billx      # BILLX_REPO=../../billx relative to docker/
cd /opt/ergplan && cp .env.example .env      # fill in: see the Stage 8 block
```

Required in `.env`: `SITE_ADDRESS`, `ERGPLAN_ENV=prod`, `ERGPLAN_PUBLIC_URL=https://<hostname>`,
`POSTGRES_PASSWORD`, `OPENAI_API_KEY`, `BILLX_TOKEN`, `BILLX_OPENAI_API_KEY`,
`ERGPLAN_SMTP_URL` (mandatory: without it production refuses to issue sign-in links), `ERGPLAN_MAIL_FROM`. `tools/dev/secrets-check.py` refuses a
committed `.env`.

## 3. Data

Copy the regulation PDFs, IEX files and (optionally) bills into `data/` (git-ignored), then register the
corpus and restore the approved rulebooks:

```bash
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d --build
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml exec api python -m ergplan.rulebook.cli restore
```

## 4. Backups

```bash
sudo crontab -e   # 30 2 * * * cd /opt/ergplan && BACKUP_BUCKET=gs://<bucket> tools/dev/backup.sh >> /var/log/ergplan-backup.log 2>&1
```

Nightly at 02:30: `pg_dump` (custom format) and `data/` as a tarball, with SHA-256 sums, kept 14 days
locally and copied to the bucket. Restore: `pg_restore -c -d ergplan db-<stamp>.dump` inside the
postgres container; untar `data-<stamp>.tar.gz` at the repository root.

## 5. Check

`https://<hostname>/api/health` shows the migration head; sign in with a `@joulewise.in` address (analyst);
open a shared plan from a private window (it opens without sign-in).
