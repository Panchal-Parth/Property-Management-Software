# Deployment verification gate

Run against a staging installation using synthetic tenant data first. Local tests
do not prove that a real server's TLS, disk permissions, proxy and timer work.

## Automated local checks

From backend:

```sh
.venv/bin/python -m unittest -v test_app
```

From frontend:

```sh
npm run build
npm run lint
E2E_PRODUCTION=1 PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Omit PLAYWRIGHT_CHANNEL on systems with Playwright Chromium installed.
Production browser tests use the actual frontend/dist, production cookie/CSP
settings, and local TLS. A temporary self-signed certificate is trusted only by
the test browser, not installed in the OS. There is no Vite proxy in this test.
The server runs with temporary credentials and a temporary database.

Backend regressions include concurrent reads/writes, competing deposit refunds,
complete backup manifests, cross-property document links, and rollback of parent
edits that would invalidate document associations.

## Actual staging host

1. Configure your real domain, HAVENLY_ORIGIN, persistent data path, Caddy, and
   systemd services as described in README.md. Provision a staging owner locally.
2. Validate configuration before starting:
   `caddy validate --config /etc/caddy/Caddyfile` and
   `systemd-analyze verify /etc/systemd/system/havenly*.service /etc/systemd/system/havenly-backup.timer`.
3. Run `python3 deploy/verify_staging.py https://YOUR-STAGING-DOMAIN` from your laptop.
   This verifies public TLS with normal certificate validation; never disable it.
4. Sign in via HTTPS. Create a property, unit, tenant, lease, a monthly entry and
   linked PDF. Check profit, document filters, download, and persistence on refresh.
   Confirm the session cookie has Secure, HttpOnly and SameSite=Strict.
5. Restart havenly.service. Reload and verify the same records and PDF download.
   Test parallel browsing from two tabs, then sign out and confirm private requests
   return 401. Test wrong-password rejection.
6. Initialize the private restic repository, then start havenly-backup.service
   once. Inspect its exit status/log and confirm a new encrypted snapshot exists
   in B2 with `restic snapshots`. Confirm havenly-backup.timer is enabled with a
   next scheduled run using `systemctl list-timers havenly-backup.timer`.
   Configure alerts on service failure and a missing successful daily backup.
7. Download that B2 snapshot to a separate private directory and restore its
   `snapshot` folder into a NEW data directory using manage.py restore. Start
   a separate loopback instance against the restored directory. Sign in again
   (backup sessions are revoked). Confirm balances, relationships and PDF bytes.
   Do not switch the live data directory merely to perform a drill.
8. Confirm the off-host retention policy, disk-space monitoring, uptime checks,
   restricted SSH/cloud firewall, and OS update policy. Verify that the restore
   drill did not touch the live data directory.

Do not approve public launch until every host-specific step passes. The repository
contains configuration templates, not proof these services have been installed.
