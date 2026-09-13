import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export type E2eUser = { email: string; password: string };

export let createdUsers: string[] = [];

export function trackUser(email: string) {
  createdUsers.push(email);
}

export async function bootstrapUser(request: APIRequestContext, tag: string): Promise<E2eUser> {
  const email = `e2e-${tag}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@jobpilot-test.com`;
  const password = 'E2ePass-2026!';
  const response = await request.post(`${API}/e2e/bootstrap`, { data: { email, password } });
  expect(response.ok()).toBeTruthy();
  trackUser(email);
  return { email, password };
}

export async function cleanupUser(request: APIRequestContext, email: string): Promise<void> {
  const response = await request.post(`${API}/e2e/cleanup`, { data: { email } });
  expect(response.ok()).toBeTruthy();
}

export async function login(page: Page, user: E2eUser): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/jobs$/);
}

export async function logout(page: Page): Promise<void> {
  await page.locator('.account-toggle').click();
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
}

export async function accessToken(request: APIRequestContext, user: E2eUser): Promise<string> {
  const response = await request.post(`${API}/auth/login`, {
    data: { email: user.email, password: user.password },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}