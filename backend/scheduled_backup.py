import sys
from datetime import datetime, timezone
from pathlib import Path
from manage import backup

if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    print(backup(root / ("havenly-" + stamp)))
