import { defineConfig } from '@playwright/test';
import { randomBytes } from 'node:crypto';

export default defineConfig({
  testDir: './tests/e2e',
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  use: {
    baseURL: 'http://localhost:3010',
    browserName: 'chromium',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: '.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host localhost --port 8010',
      cwd: '../backend',
      url: 'http://localhost:8010/api/health',
      reuseExistingServer: false,
      env: {
        ...process.env,
        POSTGRES_DB: process.env.POSTGRES_TEST_DB || 'jobpilot_test',
        E2E_TEST_MODE: 'true',
        JOBPILOT_AI_ENABLED: 'true',
        JOBPILOT_AI_TEST_PROVIDER: 'true',
        JOBPILOT_DISCOVERY_TEST_PROVIDER: 'true',
        JOBPILOT_MAILBOX_TEST_PROVIDER: 'true',
        JOBPILOT_MAILBOX_ENCRYPTION_KEY: randomBytes(32).toString('base64'),
        JOBPILOT_GOOGLE_REDIRECT_URI: 'http://localhost:8010/api/mailboxes/oauth/callback',
        JOBPILOT_MAILBOX_SETTINGS_URL: 'http://localhost:3010/settings',
        CORS_ORIGINS: 'http://localhost:3010',
      },
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --port 3010',
      url: 'http://localhost:3010',
      reuseExistingServer: false,
      env: {
        NEXT_PUBLIC_API_URL: 'http://localhost:8010/api',
      },
      timeout: 120_000,
    },
  ],
});
