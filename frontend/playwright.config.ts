import { defineConfig } from '@playwright/test'

const production = process.env.E2E_PRODUCTION === '1'
export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 60000,
  use: { baseURL: production ? 'https://127.0.0.1:8011' : 'http://127.0.0.1:5174', ignoreHTTPSErrors: production, headless: true, trace: 'retain-on-failure', ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) },
  webServer: production ? [
    { command: '../backend/.venv/bin/python ../backend/e2e_server.py --production', url: 'https://127.0.0.1:8011/api/health', ignoreHTTPSErrors: true, reuseExistingServer: false },
  ] : [
    { command: '../backend/.venv/bin/python ../backend/e2e_server.py', url: 'http://127.0.0.1:8011/api/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort', url: 'http://127.0.0.1:5174', env: { HAVENLY_API_TARGET: 'http://127.0.0.1:8011' }, reuseExistingServer: false },
  ],
})
