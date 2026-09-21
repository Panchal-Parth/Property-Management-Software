# Production deployment: DigitalOcean, Backblaze B2, Brevo

**Status:** templates only. Nothing here provisions a server, domain, email sender,
or backup account. Do not enter real tenant information until the staging gate and
an off-site restore drill have passed on the actual host.

## Accounts and domain (owner actions)

1. Buy a domain at a registrar you control. Enable registrar MFA, domain lock,
   and auto-renew. Choose a hostname (for example, `rentals.yourdomain.com`).
   Keep renewal and recovery email outside this app.
2. Create a DigitalOcean account with MFA and billing. Choose a Basic Droplet in
   New York (NYC1), Debian 13 x64, **at least 2 GB RAM / 1 vCPU / 50 GB disk**.
   Add your SSH public key, enable automatic Droplet backups and improved metrics.
   Set a cloud firewall: 80/443 from anywhere, 22 from your own IP only. Do not
   expose port 8000. Record the Droplet public IP; do not share SSH private keys.
3. Point the chosen hostname's DNS A record to the Droplet public IP. DNS must
   resolve before Caddy can obtain its HTTPS certificate.
4. Create a private Backblaze B2 bucket, preferably in a US region. Enable MFA.
   Create a separate application key limited to that bucket, with the read/write/
   delete permissions needed by restic retention. Record its S3 endpoint and key
   in your password manager. **Do not use a public bucket.**
5. Create a Brevo account. Authenticate the owned domain and verify the sender
   mailbox you will use for signup/recovery. Create an API key for this app.
   Publish the DNS records Brevo requests (including DKIM and DMARC). Keep the
   mailbox usable independently of this server.

Monthly costs include the Droplet, optional Droplet backup, domain, and any B2
storage beyond its free tier. Recheck provider pricing before purchase.

## Server setup

Use a non-root sudo admin over SSH keys; disable password/root SSH logins after
confirming the new login works. Apply OS security updates and enable the
DigitalOcean firewall and disk/CPU/memory alerts. Restrict server users to the
people who actually administer it. For a single-owner app, use one Uvicorn worker
and one persistent SQLite data directory; do not put the database on a network
filesystem or start a second application instance against it.

Install Python 3.13 with venv, Node.js 22 with npm, restic, and Caddy from their
official Debian packages/repositories. Verify versions before continuing. Copy
this repo into `/opt/havenly`, then run these commands as the sudo admin:

```sh
cd /opt/havenly/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd /opt/havenly/frontend
npm ci
npm run build
```

Create the unprivileged `havenly` system account and `/var/lib/havenly` with
owner `havenly:havenly` and mode `0700`. The account must be able to read
`/opt/havenly` but should not own the deployed code. Copy
`deploy/havenly.env.example` to `/etc/havenly.env` and
`deploy/havenly-backup.env.example` to `/etc/havenly-backup.env`, replacing all
example values. Edit with a root-only editor (for example `sudoedit`), not a
command that prints secrets or stores them in shell history. Set both files to
`root:root` and mode `0600`. Create a **unique, long random** restic repository
password in `/etc/havenly-restic-password`; make it `root:havenly`, mode `0640`.
Store a copy in your password manager: without it, backups cannot be restored.
Do not reuse the owner login password. Keep all three files out of Git.

Initialize the encrypted repository once using the same backup environment
variables and restic password file. From a root shell on the server (the private
environment file is readable only by root), run:

```sh
set -a
. /etc/havenly-backup.env
set +a
restic init
restic snapshots
```

Exit the root shell afterward. Do not use `restic init` on an existing
repository. The `RESTIC_REPOSITORY` path must begin with `s3:https://`
and use the exact HTTPS endpoint shown by B2. The backup job uses SQLite's online
backup API, includes private document uploads, encrypts through restic, checks
repository integrity, and keeps 14 daily, 8 weekly, and 12 monthly snapshots.
Allow temporary free disk space for a complete snapshot of the database and
documents while the job runs. Monitor both server and B2 usage.

Replace the placeholder hostname in `deploy/Caddyfile`, matching
`HAVENLY_ORIGIN` exactly. Install the Caddyfile at `/etc/caddy/Caddyfile` and
the three unit files under `/etc/systemd/system/`. Validate the Caddyfile and
systemd units before starting them (see [STAGING.md](STAGING.md)). Start Caddy
and `havenly.service`; only then enable/start `havenly-backup.timer`. Run
`havenly-backup.service` manually once and inspect its exit status. Set alerts for
website health, disk utilization, failed services, and a missing successful daily
backup. A timer that is merely enabled does **not** prove backups are working.

Provision the first owner through verified email signup only after Brevo mail is
working. Alternatively run `manage.py create-owner` on the server as `havenly`
with `HAVENLY_DATA_DIR` set to the live directory. Never seed the production
database with the synthetic/demo data used in tests.

## Launch gate and recovery

Run every check in [STAGING.md](STAGING.md) with **synthetic data first**, on
the real proxy/domain/server. Restore a snapshot downloaded from B2 into a new
directory and verify both a monthly record and a PDF before admitting live data.
Schedule periodic repeat restore drills. Keep a documented administrator who
can reach the registrar, DigitalOcean, B2, Brevo, and the restic password.

For a failed deploy, stop the app, repair or roll back the code, and restart it.
Never point an older app version at a migrated database without checking schema
compatibility. For disaster recovery, download a restic snapshot to a separate
private directory, locate its `snapshot` folder (containing `manifest.json`),
then use `backend/.venv/bin/python backend/manage.py restore SNAPSHOT_FOLDER NEW_DATA_DIRECTORY`
from the deployed repository, with `HAVENLY_DATA_DIR` pointed at a separate
recovery path.
The restore command refuses an existing destination and verifies document hashes
and SQLite integrity. Recovered sessions are revoked. Do not overwrite live data
during a drill.

Never paste API keys, passwords, SSH private keys, restic password, or real tenant
records into an issue, chat, commit, screenshot, or support ticket.
