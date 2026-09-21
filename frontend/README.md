# Havenly frontend

React, TypeScript, and Vite client for the single-owner rental management app.
For backend setup, email configuration, data privacy, backups, and deployment,
see the [project README](../README.md).

From this directory:

```sh
npm ci
npm run dev
```

Open http://localhost:5173. The development server proxies `/api` to
`http://127.0.0.1:8000` by default. Set `HAVENLY_API_TARGET` before `npm run dev`
if your backend uses another address. Start the backend separately from its own
directory with `uvicorn main:app --reload --host 127.0.0.1 --port 8000`.

Checks:

```sh
npm run build
npm run lint
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

The browser tests create a temporary, fictional portfolio and use separate local
test servers; they do not touch the real owner database. The Chrome channel is
useful on macOS 13 where the bundled Playwright Chromium may be unavailable.
