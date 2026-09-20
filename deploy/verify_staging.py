"""Read-only public deployment smoke checks; requires valid public HTTPS."""
import argparse
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("origin", help="https://your-staging-domain")
    args = parser.parse_args()
    origin = args.origin.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("Provide an HTTPS origin without a path or query.")

    def get(path):
        try:
            with urlopen(Request(origin + path), timeout=20) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    status, headers, body = get("/")
    assert status == 200 and b'id="root"' in body, "Built frontend is not served"
    assert headers.get("Strict-Transport-Security"), "Missing HSTS"
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""), "Missing production CSP"
    assert headers.get("X-Content-Type-Options") == "nosniff", "Missing nosniff"
    status, headers, body = get("/api/health")
    assert status == 200 and json.loads(body)["status"] == "healthy", "API health failed"
    for path in ("/api/state", "/api/documents/1/download"):
        status, headers, _ = get(path)
        assert status == 401, f"Private route is not protected: {path}"
        assert headers.get("Cache-Control") == "no-store", "Private response caching is enabled"
    for path in ("/docs", "/openapi.json"):
        assert get(path)[0] == 404, f"Development documentation is exposed: {path}"
    print("PASS: HTTPS, frontend, API health, security headers and unauthenticated access checks.")
    print("Still perform authenticated workflows, service restart, timer and restore checks in STAGING.md.")


if __name__ == "__main__":
    main()
