# Deploying ergPLAN on the Google Cloud VM (Stage 8)

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
`ERGPLAN_SMTP_URL` (for sign-in mail), `ERGPLAN_MAIL_FROM`. `tools/dev/secrets-check.py` refuses a
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
