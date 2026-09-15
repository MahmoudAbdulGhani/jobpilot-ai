import { expect, test, type Page } from '@playwright/test';
import { accessToken, API, bootstrapUser, cleanupUser, createdUsers, login, logout } from './helpers';

async function createJob(page: Page, title: string, company = 'Cedar Labs') {
  await page.getByRole('button', { name: 'Save a job' }).first().click();
  await page.getByLabel('Job title').fill(title);
  await page.getByLabel('Company').fill(company);
  await page.getByLabel('Location').fill('Beirut, Lebanon');
  await page.getByLabel('Original posting URL').fill('https://example.com/jobs/backend');
  await page.getByLabel('Job description').fill('Help a small product team build dependable Python APIs.\n\nWhat you will work on\n• Build and maintain FastAPI endpoints\n• Design and query PostgreSQL databases\n• Test, document, and improve existing APIs\n\nWhat the team is looking for\n• Comfort with Python, SQL, and Git\n• Clear communication and a willingness to learn');
  await page.getByLabel('My notes').fill('Check the experience requirement.\nPrepare an example of API testing.\nReview my PostgreSQL projects.');
  await page.getByRole('button', { name: 'Save job' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
}

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) {
    await cleanupUser(request, email);
  }
  createdUsers.length = 0;
});

test('connected career journal workflow', async ({ browser, request }) => {
  const primary = await bootstrapUser(request, 'journal-primary');
  const secondary = await bootstrapUser(request, 'journal-secondary');
  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await login(page, primary);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Saved jobs' })).toBeVisible();
  await createJob(page, 'Junior Backend Developer');
  await page.reload();
  await page.getByRole('link', { name: /Junior Backend Developer/ }).click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/);
  const jobUrl = page.url();
  await page.screenshot({ path: '../evidence/detail-desktop-initial.png', fullPage: true });

  await page.getByRole('button', { name: 'Edit job' }).click();
  await expect(page.getByLabel('Job title')).toBeFocused();
  await page.getByLabel('Location').fill('');
  await page.getByLabel('Original posting URL').fill('');
  await page.getByRole('button', { name: 'Save job' }).click();
  await expect(page.getByText('Beirut, Lebanon')).toBeHidden();
  await page.getByRole('button', { name: 'Edit notes' }).click();
  await expect(page.getByLabel('Personal notes')).toBeFocused();
  await page.getByLabel('Personal notes').fill('Bring two API reliability stories.');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.getByText('Bring two API reliability stories.')).toBeVisible();

  await page.getByRole('link', { name: 'Back to saved jobs' }).click();
  for (let index = 1; index <= 11; index++) await createJob(page, `Pagination role ${String(index).padStart(2, '0')}`, `Company ${index}`);
  await expect(page.getByText('Page 1 of 2')).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Page 2 of 2')).toBeVisible();
  await page.getByPlaceholder('Search by title or company').fill('Junior Backend');
  await page.getByRole('link', { name: /Junior Backend Developer/ }).click();
  await page.getByRole('button', { name: 'Archive job' }).click();
  await page.getByRole('link', { name: 'Archive' }).first().click();
  await page.getByRole('link', { name: /Junior Backend Developer/ }).click();
  await page.getByRole('button', { name: 'Restore job' }).click();
  await page.getByRole('button', { name: 'Delete job' }).click();
  await page.getByRole('button', { name: 'Keep job' }).click();

  await logout(page);
  await login(page, secondary);
  await page.goto(jobUrl);
  await expect(page.getByRole('heading', { name: 'Job not found' })).toBeVisible();
  await page.goto('/jobs/not-a-real-job-id');
  await expect(page.getByRole('heading', { name: 'Job not found' })).toBeVisible();
  await logout(page);

  await login(page, primary);
  await page.goto(jobUrl);
  await page.getByRole('button', { name: 'Delete job' }).click();
  await page.getByRole('button', { name: 'Delete job' }).last().click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByText('Junior Backend Developer')).toBeHidden();
  await logout(page);
  expect(pageErrors).toEqual([]);
  await context.close();
});

test('connected application tracking record reload edit status history delete flow', async ({ browser, request }) => {
  const user = await bootstrapUser(request, 'tracking-e2e');
  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  await login(page, user);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Saved jobs' })).toBeVisible();

  await createJob(page, 'Application Tracking Job');
  await page.reload();
  await page.getByRole('link', { name: /Application Tracking Job/ }).click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/);

  await page.getByLabel('Submission date').fill('2026-09-14');
  await page.getByLabel('Method').selectOption('email');
  await page.getByLabel('Status').selectOption('Applied');
  await page.getByLabel('Follow up date').fill('2026-09-21');
  await page.getByLabel('Notes').fill('Follow up this week.');
  await page.getByRole('button', { name: 'Record application' }).click();
  await expect(page.getByText('Follow up this week.')).toBeVisible();

  await page.reload();
  await expect(page.getByText('Status history')).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'Applied' })).toBeVisible();

  await page.getByLabel('Status').selectOption('Interview');
  await page.getByLabel('Notes').fill('Follow up this week and keep applying.');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('Follow up this week and keep applying.')).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'Interview' })).toBeVisible();

  await page.getByRole('link', { name: 'Applications' }).click();
  await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible();
  await page.getByLabel('Status filter').selectOption('Interview');
  await page.getByRole('link', { name: /Open saved job/ }).click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/);

  await page.getByRole('button', { name: 'Delete' }).nth(1).click();

  await expect(page.getByRole('button', { name: 'Record application' })).toBeVisible();
  await context.close();
});

test('mobile detail and dialog', async ({ browser, request }) => {
  const user = await bootstrapUser(request, 'journal-mobile');
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await login(page, user);
  await createJob(page, 'Mobile Product Engineer', 'Northstar');
  await page.getByRole('link', { name: /Mobile Product Engineer/ }).click();
  await expect(page.locator('.job-workspace')).toHaveCSS('display', 'flex');
  await page.screenshot({ path: '../evidence/detail-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Edit job' }).click();
  await expect(page.getByLabel('Job title')).toBeFocused();
  await page.screenshot({ path: '../evidence/dialog-mobile.png', fullPage: true });
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveJSProperty('scrollTop', 0);
  await dialog.evaluate(element => element.scrollTop = element.scrollHeight);
  await expect(page.getByRole('button', { name: 'Save job' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Edit job' })).toBeFocused();
  await context.close();
});

test('connected explainable fit analysis persists and becomes outdated', async ({ page, request }) => {
  const user = await bootstrapUser(request, 'job-fit');
  const token = await accessToken(request, user);
  const auth = { Authorization: `Bearer ${token}` };
  expect((await request.patch(`${API}/profile`, { headers: auth, data: { headline: 'Backend engineer', skills: ['Python', 'PostgreSQL'] } })).ok()).toBeTruthy();
  const created = await request.post(`${API}/jobs`, { headers: auth, data: { title:'Backend Engineer', company:'Synthetic Co', description:'Python is required\nClear communication preferred' } });
  expect(created.ok()).toBeTruthy(); const job = await created.json();
  await login(page,user); await page.goto(`/jobs/${job.id}`);
  await page.getByRole('button',{name:'Analyze fit'}).click();
  await expect(page.getByText(/Synthetic deterministic analysis/)).toBeVisible();
  await expect(page.getByRole('heading',{name:'Python is required'})).toBeVisible();
  await page.reload(); await expect(page.getByText(/Synthetic deterministic analysis/)).toBeVisible();
  await page.getByRole('button',{name:'Edit job'}).click();
  await page.getByLabel('Job description').fill('Go is required');
  await page.getByRole('button',{name:'Save job'}).click();
  await expect(page.getByText(/Inputs changed/)).toBeVisible();
  await page.getByRole('button',{name:'Reanalyze fit'}).click();
  await expect(page.getByRole('heading',{name:'Go is required'})).toBeVisible();
});
