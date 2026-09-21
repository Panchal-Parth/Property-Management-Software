"""Snapshot the live portfolio, then send an encrypted copy to an off-site restic repository.

The database is copied with SQLite's online backup API first; live database files
are never passed directly to restic. Run this only from the private server timer.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from manage import backup


def run_backup():
    repository = os.environ.get("RESTIC_REPOSITORY", "")
    password_file = Path(os.environ.get("RESTIC_PASSWORD_FILE", ""))
    if not repository.startswith(("s3:https://", "b2:", "sftp:", "sftp://", "rest:https://")):
        raise RuntimeError("RESTIC_REPOSITORY must point to an encrypted off-site repository over a secure connection.")
    if not password_file.is_file():
        raise RuntimeError("RESTIC_PASSWORD_FILE must name a readable private file.")
    if not shutil.which("restic"):
        raise RuntimeError("Install restic before enabling the off-site backup timer.")

    with tempfile.TemporaryDirectory(prefix="havenly-offsite-") as temporary:
        snapshot = backup(Path(temporary) / "snapshot")
        subprocess.run(["restic", "backup", "--tag", "havenly-production", str(snapshot)], check=True)
    # No unencrypted snapshot remains on disk after restic exits, including on error.
    subprocess.run(["restic", "check"], check=True)
    subprocess.run(["restic", "forget", "--tag", "havenly-production", "--group-by", "tags",
                    "--keep-daily", "14", "--keep-weekly", "8", "--keep-monthly", "12", "--prune"], check=True)


if __name__ == "__main__":
    run_backup()
    print("Encrypted off-site portfolio backup and repository check completed.")
