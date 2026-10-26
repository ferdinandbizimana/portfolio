# Putting the site online

This guide takes the application from this repository to a live site with
HTTPS, backups and monitoring. Day-to-day tasks are in
[`operations.md`](operations.md).

## What you need

- A server (VPS) with Ubuntu 24.04, **at least 4 GB of memory** (8 GB
  comfortable for very large SAP exports), 2 CPUs and 40 GB of disk.
- A domain name, for example `ferdinand.rw`, and access to its DNS settings.
- An e-mail account for sending (Gmail with an app password works; see
  "Contact form e-mail" in `operations.md`).
- A place for the backups, away from the server: an S3-compatible bucket
  (Backblaze B2 is inexpensive) or another server.

## 1. Prepare the server

```bash
# as root on the new server
apt update && apt upgrade -y
adduser deploy && usermod -aG sudo deploy
# Docker (official instructions: https://docs.docker.com/engine/install/ubuntu/)
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
# Firewall: only SSH and the web
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable
```

Use SSH keys and turn off password login for SSH
(`PasswordAuthentication no` in `/etc/ssh/sshd_config`, then
`systemctl restart ssh`). Turn on automatic security updates:
`apt install unattended-upgrades`.

## 2. Point the domain at the server

At your DNS provider, create an `A` record for the domain (and `www` if you
want it) with the server's IP address. Wait until `ping your-domain` answers
from that address.

## 3. Get the application and set the secrets

```bash
# as the deploy user
git clone https://github.com/ferdinandbizimana/portfolio.git
cd portfolio
cp .env.example .env
chmod 600 .env
nano .env
```

In `.env`, set at least:

| Setting | Value |
|---|---|
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.prod.yml` (remove the `#`) |
| `COMPOSE_PROFILES` | `backup` (remove the `#`) |
| `ENVIRONMENT` | `production` |
| `POSTGRES_PASSWORD` | a long random value: `openssl rand -hex 24` |
| `SITE_ADDRESS` | your domain, e.g. `ferdinand.rw` |
| `SITE_URL` | `https://` + your domain |
| `CORS_ORIGINS` | `https://` + your domain |
| `COOKIE_SECURE` | `true` |
| `SMTP_*`, `MAIL_FROM`, `CONTACT_TO_EMAIL` | your sending account and your address |
| `VARIANCE_BCC` | your address: a copy of every stock variance e-mail |
| `EXPIRY_MAIL_TO` | the sales pharmacist: the monthly expiry follow-up (last day of the month) |
| `EXPIRY_MAIL_CC` | the managers to copy, comma-separated (and your address if you want it in Cc) |
| `EXPIRY_MAIL_BCC` | your address: a hidden copy of the monthly expiry follow-up |
| `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `AWS_*` | the backup bucket and its keys; the password from `openssl rand -hex 32` |
| `INBOX_HOST_DIR` | the shared folder with SAP exports, if you use one |

Write `RESTIC_PASSWORD` down somewhere safe **outside the server** (a
password manager). Without it, the backups cannot be read.

## 4. Start

```bash
docker compose up -d --build --wait
docker compose exec backend python -m app.cli create-admin --email you@example.com
```

Caddy obtains the HTTPS certificate on the first visit. Open
`https://your-domain`, then `https://your-domain/admin` and sign in.
In Admin → Settings, send a test e-mail.

## 5. Check the backups

```bash
docker compose run --rm backup backup.sh      # one backup now
docker compose run --rm backup restic snapshots
```

Admin → Overview then shows "Backups: OK". Backups run every night at
`BACKUP_TIME` (default 02:30, Kigali time). Each run keeps 7 daily, 4 weekly
and 12 monthly copies and checks a sample of the stored data.

Do a restore test once on a spare server (see "Restoring from a backup" in
`operations.md`). The automated tests already do this on every change
(`scripts/test-backup-restore.sh`).

## 6. Monitoring

- **Uptime**: create a free check at an uptime service (for example
  UptimeRobot or Better Stack) for `https://your-domain/api/health`. It
  answers 200 when the site, the database and the job queue work, 503
  otherwise, and the service e-mails you when it fails.
- **Backups**: create a free check at healthchecks.io with a daily period,
  and put its ping URL in `BACKUP_PING_URL`. You are e-mailed if a night's
  backup does not report.
- **Inside the app**: Admin → Overview shows the worker, the scheduler, the
  last backup and free disk space.
- **Error log**: `docker compose logs --since 24h backend worker scheduler | grep '"ERROR"'`.
  Logs are rotated automatically (5 × 10 MB per service).

## 7. Updating

```bash
cd ~/portfolio && scripts/update.sh
```

It backs up, gets the latest version from GitHub, rebuilds, restarts (database
changes are applied automatically) and checks that the API answers.
