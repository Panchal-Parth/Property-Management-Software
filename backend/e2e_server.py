"""Isolated browser-test server: never reads/writes the owner's data directory."""
import os
import tempfile
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="havenly-e2e-") as folder:
        os.environ["HAVENLY_DATA_DIR"] = folder
        production = "--production" in sys.argv
        os.environ["HAVENLY_ORIGIN"] = "https://127.0.0.1:8011" if production else "http://127.0.0.1:5174"
        os.environ["HAVENLY_ENV"] = "production" if production else "development"
        tls = {}
        if production:
            if not (Path(__file__).parent.parent / "frontend/dist/index.html").is_file():
                raise SystemExit("Build the frontend before production browser tests.")
            key, cert = Path(folder) / "key.pem", Path(folder) / "cert.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tls = {"ssl_keyfile": str(key), "ssl_certfile": str(cert)}
        from db import migrate, connect
        from security import password_hash
        migrate()
        with connect() as c:
            c.execute("INSERT INTO owners(id,email,name,password_hash) VALUES(1,?,?,?)",
                      ("browser-test@example.test", "Browser Owner", password_hash("test-only-password-123")))
        import uvicorn
        uvicorn.run("main:app", host="127.0.0.1", port=8011, **tls)
