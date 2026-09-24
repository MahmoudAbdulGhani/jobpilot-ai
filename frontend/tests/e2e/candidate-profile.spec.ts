import { expect, test } from '@playwright/test';
import { bootstrapUser, cleanupUser, createdUsers, login, logout } from './helpers';

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) {
    await cleanupUser(request, email);
  }
  createdUsers.length = 0;
});

test('connected candidate profile workflow', async ({ browser, request }) => {
  const primary = await bootstrapUser(request, 'profile-primary');
  const secondary = await bootstrapUser(request, 'profile-secondary');
  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await login(page, primary);
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Your profile', exact: true })).toBeVisible();

  const emptyState = page.getByText('Your profile is not set up yet');
  if (await emptyState.isVisible()) {
    await page.getByRole('button', { name: 'Set up profile' }).click();
  } else {
    await page.getByRole('button', { name: 'Edit profile' }).click();
  }

  const headline = `QA profile ${Date.now()}`;
  await page.getByLabel('Headline').fill(headline);
  await page.getByLabel('Location').fill('Beirut, Lebanon');
  await page.getByLabel('Remote preference').selectOption('hybrid');
  await page.getByLabel('Work authorization').selectOption('needs_sponsorship');
  await page.getByLabel('Skills').fill('Python, FastAPI, PostgreSQL');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toContainText('Profile saved');
  await expect(page.getByRole('heading', { name: headline })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('profile-desktop.png'), fullPage: true });

  await page.reload();
  await expect(page.getByRole('heading', { name: headline })).toBeVisible();
  await expect(page.getByText('Python')).toBeVisible();
  await expect(page.locator('.profile-meta').getByText('Hybrid', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Edit profile' }).click();
  await page.getByLabel('Minimum (yearly, optional)').fill('200000');
  await page.getByLabel('Maximum (yearly, optional)').fill('100000');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('The minimum salary must not be higher than the maximum.')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Discard changes', exact: true }).click();
  await expect(page.getByRole('heading', { name: headline })).toBeVisible();

  await logout(page);
  await login(page, secondary);
  await page.goto('/profile');
  await expect(page.getByText('Your profile is not set up yet')).toBeVisible();
  await logout(page);
  expect(pageErrors).toEqual([]);
  await context.close();
});