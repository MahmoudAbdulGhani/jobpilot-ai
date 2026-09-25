import { defineConfig } from '@playwright/test';

/** Frontend-only checks: every application API request is fulfilled by the spec. */
export default defineConfig({
  testDir: './tests/landing-e2e',
  outputDir: '../evidence/landing/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3025',
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --port 3025',
    url: 'http://localhost:3025',
    reuseExistingServer: true,
    env: {
      JOBPILOT_DEPLOYMENT: 'local',
      NEXT_PUBLIC_API_URL: '/api',
    },
    timeout: 120_000,
  },
});
