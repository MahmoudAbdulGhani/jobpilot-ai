import { expect, test, type Page } from '@playwright/test';

const password = 'QaPass-2026!';
const primary = 'qa-one@example.com';
const secondary = 'qa-two@example.com';

async function login(page: Page, email = primary) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/jobs$/);
}

async function logout(page: Page) {
  await page.locator('.account-toggle').click();
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test('connected candidate profile workflow', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await login(page);
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
  await page.screenshot({ path: '../evidence/profile-desktop.png', fullPage: true });

  await page.reload();
  await expect(page.getByRole('heading', { name: headline })).toBeVisible();
  await expect(page.getByText('Python')).toBeVisible();
  await expect(page.getByText('Hybrid')).toBeVisible();

  await page.getByRole('button', { name: 'Edit profile' }).click();
  await page.getByLabel('Minimum (yearly, optional)').fill('200000');
  await page.getByLabel('Maximum (yearly, optional)').fill('100000');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('The minimum salary must not be higher than the maximum.')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('heading', { name: headline })).toBeVisible();

  await logout(page);
  await login(page, secondary);
  await page.goto('/profile');
  await expect(page.getByText('Your profile is not set up yet')).toBeVisible();
  await logout(page);
  expect(pageErrors).toEqual([]);
  await context.close();
});