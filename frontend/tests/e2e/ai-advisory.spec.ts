import { expect, test } from '@playwright/test';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, login } from './helpers';

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) {
    await cleanupUser(request, email);
  }
  createdUsers.length = 0;
});

async function apiSetup(request: import('@playwright/test').APIRequestContext, tag: string) {
  const user = await bootstrapUser(request, tag);
  const token = await accessToken(request, user);
  const auth = { Authorization: `Bearer ${token}` };
  const profile = await request.patch(`${API}/profile`, {
    headers: auth,
    data: {
      headline: 'Backend engineer', location: 'Beirut, Lebanon', remote_preference: 'remote',
      skills: ['Python', 'PostgreSQL', 'FastAPI'],
      experience: [
        { title: 'Backend Engineer', organization: 'Acme' },
        { title: 'API Developer', organization: 'Globex' },
        { title: 'Junior Developer', organization: 'Initech' },
      ],
    },
  });
  expect(profile.ok()).toBeTruthy();
  const created = await request.post(`${API}/jobs`, {
    headers: auth,
    data: {
      title: 'Backend Engineer', company: 'Cedar Labs', location: 'Remote',
      description: 'We are hiring a Backend Engineer.\nYou must have strong Python and PostgreSQL experience.\nFastAPI and remote collaboration are required.',
    },
  });
  expect(created.ok()).toBeTruthy();
  const job = await created.json();
  return { user, auth, job };
}

test('ranking runs with evidence and shows on saved jobs', async ({ page, request }) => {
  const { user, job } = await apiSetup(request, 'advisory-ranking');
  await login(page, user);
  const run = await request.post(`${API}/rankings`, {
    headers: { Authorization: `Bearer ${await accessToken(request, user)}` }, data: {},
  });
  expect(run.ok()).toBeTruthy();
  const body = await run.json();
  expect(body.job_count).toBe(1);
  expect(body.items[0].reasons.length).toBeGreaterThan(0);
  expect(body.items[0].reasons[0].evidence.job_quote).toBeTruthy();
  expect(body.items[0].reasons[0].evidence.profile_fact).toBeTruthy();
  await page.goto('/jobs');
  await expect(page.getByRole('heading', { name: 'Rank saved jobs' })).toBeVisible();
  await page.getByRole('button', { name: 'Rank again' }).click();
  await expect(page.getByText(job.title).first()).toBeVisible();
});

test('follow-up suggestions generate, approve and create a reminder', async ({ page, request }) => {
  const { user, auth, job } = await apiSetup(request, 'advisory-followup');
  const app = await request.post(`${API}/jobs/${job.id}/applications`, {
    headers: auth,
    data: { submission_date: '2026-09-04T12:00:00Z', method: 'linkedin_manual', status: 'Applied' },
  });
  expect(app.ok()).toBeTruthy();
  const record = await app.json();
  expect(record.origin).toBe('manual');
  const generated = await request.post(`${API}/followup-suggestions/generate`, { headers: auth });
  expect(generated.ok()).toBeTruthy();
  const items = await generated.json();
  expect(items.length).toBe(1);
  const approved = await request.post(`${API}/followup-suggestions/${items[0].id}/approve`, {
    headers: auth, data: { confirm: true },
  });
  expect(approved.ok()).toBeTruthy();
  const reminder = await request.get(`${API}/applications/${record.id}/reminder`, { headers: auth });
  expect((await reminder.json()).status).toBe('active');
  await login(page, user);
  await page.goto('/reminders');
  await expect(page.getByRole('heading', { name: 'Suggested follow-ups' })).toBeVisible();
});

test('insights, Q&A, privacy and digest answer over owner data', async ({ page, request }) => {
  const { user, auth } = await apiSetup(request, 'advisory-insights');
  const insights = await request.get(`${API}/insights`, { headers: auth });
  expect(insights.ok()).toBeTruthy();
  expect((await insights.json()).application_counts).toEqual({});
  const answer = await request.get(`${API}/qa/ask`, {
    headers: auth, params: { entity: 'jobs', q: 'Python PostgreSQL', limit: 10 },
  });
  expect(answer.ok()).toBeTruthy();
  expect((await answer.json()).total).toBe(1);
  const matrix = await request.get(`${API}/privacy/matrix`, { headers: auth });
  expect(matrix.ok()).toBeTruthy();
  const domains = (await matrix.json()).rows.map((row: { domain: string }) => row.domain);
  expect(domains).toContain('selected job');
  const prefs = await request.put(`${API}/digest/preferences`, {
    headers: auth, data: { cadence: 'daily', confirm: true },
  });
  expect((await prefs.json()).cadence).toBe('daily');
  const preview = await request.get(`${API}/digest/preview`, { headers: auth });
  expect(preview.ok()).toBeTruthy();
  expect((await preview.json()).delivery.enabled).toBe(false);
  await login(page, user);
  await page.goto('/insights');
  await expect(page.getByRole('heading', { name: 'Insights' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ask your journal' })).toBeVisible();
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'How your data is used' })).toBeVisible();
  await page.goto('/discover');
  await expect(page.getByRole('heading', { name: 'Daily digest' })).toBeVisible();
});
