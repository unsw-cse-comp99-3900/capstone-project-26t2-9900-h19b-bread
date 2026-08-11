import { defineConfig, devices } from '@playwright/test';

const useDevServer = process.env.E2E_USE_DEV_SERVER === 'true';
const baseURL = process.env.E2E_BASE_URL ?? (useDevServer ? 'http://127.0.0.1:5173' : 'http://127.0.0.1:8080');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: useDevServer
    ? {
        command: 'npm run dev -- --host 127.0.0.1',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 120_000,
      }
    : undefined,
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
