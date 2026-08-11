import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';


async function login(page: Page) {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  test.skip(!email || !password, 'Set E2E_EMAIL and E2E_PASSWORD to run authenticated workflows.');
  await page.goto('/login');
  await page.getByLabel('Email').fill(email!);
  await page.getByLabel('Password').fill(password!);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).toHaveURL(/\/homepage$/);
}

test('an unauthenticated protected route redirects to login with an expiry notice', async ({ page }) => {
  await page.goto('/homepage');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('Your session has expired. Please sign in again.')).toBeVisible();
});

test('an authenticated publisher can reach the dashboard', async ({ page }) => {
  await login(page);

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Publish New API' })).toBeVisible();
});

test('a secure OpenAPI file can complete the existing publication workflow', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: 'Publish New API' }).click();

  const fixture = path.join(import.meta.dirname, 'fixtures', 'valid-secure-openapi.yaml');
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Parse & Continue' }).click();

  await expect(page.getByLabel('API Name')).toHaveValue('Secure Invoice API');
  await page.getByRole('button', { name: 'Validate & Publish' }).click();

  await expect(page.getByText('API Published Successfully')).toBeVisible({ timeout: 30_000 });
});
