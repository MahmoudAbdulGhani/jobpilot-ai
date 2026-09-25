import { expect, test } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, grantAiConsent, login } from './helpers';

function database(input: object) {
  const backend = path.resolve(process.cwd(), '../backend');
  const executable = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
  const result = spawnSync(path.join(backend, executable), ['scripts/profile_review_e2e.py'], {
    cwd: backend, input: JSON.stringify(input), encoding: 'utf8', env: { ...process.env, ENVIRONMENT: 'test' },
  });
  expect(result.status, result.stderr).toBe(0);
  return JSON.parse(result.stdout);
}

function pdf() {
  const stream = 'BT /F1 12 Tf 72 720 Td (Synthetic profile review) Tj ET';
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>', `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let text = '%PDF-1.4\n'; const offsets: number[] = [];
  objects.forEach((obj, i) => { offsets.push(Buffer.byteLength(text)); text += `${i + 1} 0 obj\n${obj}\nendobj\n`; });
  const start = Buffer.byteLength(text);
  text += `xref\n0 6\n0000000000 65535 f \n${offsets.map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`;
  return Buffer.from(text);
}

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) await cleanupUser(request, email);
  createdUsers.length = 0;
});

test('meters two browser refreshes and persists quota across reload', async ({ page, request }) => {
  const user = await bootstrapUser(request, 'profile-review-quota');
  await grantAiConsent(request, user, ['ai_profile_suggestions']);
  const auth = { Authorization: `Bearer ${await accessToken(request, user)}` };
  const uploaded = await request.post(`${API}/resumes`, { headers: auth, multipart: { file: { name: 'quota-cv.pdf', mimeType: 'application/pdf', buffer: pdf() } } });
  expect(uploaded.ok()).toBeTruthy();
  const resume = await uploaded.json();
  expect((await request.post(`${API}/resumes/${resume.id}/extract`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.patch(`${API}/resumes/${resume.id}/extraction`, { headers: auth, data: { draft_text: 'Synthetic profile engineer with SQL experience.' } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/resumes/${resume.id}/extraction/confirm`, { headers: auth })).ok()).toBeTruthy();
  await login(page, user);
  await page.goto('/resumes');
  const panel = page.getByRole('region', { name: /Profile suggestions for/ });
  await expect(panel.getByText(/one initial AI generation available/)).toBeVisible();
  await panel.getByRole('button', { name: 'Suggest profile details with AI' }).click();
  await expect(panel.getByText(/2 AI profile refreshes left/)).toBeVisible();
  await panel.getByRole('button', { name: 'Regenerate suggestions' }).click();
  await expect(panel.getByText(/1 AI profile refresh left/)).toBeVisible();
  await panel.getByRole('button', { name: 'Regenerate suggestions' }).click();
  await expect(panel.getByText(/Two AI profile refreshes used this UTC month/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Regenerate suggestions' })).toBeDisabled();
  expect(database({ action: 'quota', email: user.email })).toEqual({ kinds: ['initial', 'refresh', 'refresh'], reservation_count: 3 });
  await page.reload();
  await expect(panel.getByRole('button', { name: 'Regenerate suggestions' })).toBeDisabled();
  expect((await (await request.get(`${API}/profile-suggestions/resumes/${resume.id}/eligibility`, { headers: auth })).json()).remaining_refreshes).toBe(0);
});

test('refreshes an applied old suggestion set from the saved CV without another upload', async ({ page, request }) => {
  const user = await bootstrapUser(request, 'profile-review-refresh');
  await grantAiConsent(request, user, ['ai_profile_suggestions']);
  const auth = { Authorization: `Bearer ${await accessToken(request, user)}` };
  const uploaded = await request.post(`${API}/resumes`, { headers: auth, multipart: { file: { name: 'saved-cv.pdf', mimeType: 'application/pdf', buffer: pdf() } } });
  expect(uploaded.ok()).toBeTruthy();
  const resume = await uploaded.json();
  expect((await request.post(`${API}/resumes/${resume.id}/extract`, { headers: auth })).ok()).toBeTruthy();
  const source = 'Synthetic developer\nPROFESSIONAL EXPERIENCE\nDeveloper - Cedar Labs June 2022 - July 2024\nBuilt APIs\nEngineer - Pine Works Jan 2020 - May 2022\nBuilt tests\nPROJECT EXPERIENCE\nDemo - Sample App June 2025 - July 2025';
  expect((await request.patch(`${API}/resumes/${resume.id}/extraction`, { headers: auth, data: { draft_text: source } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/resumes/${resume.id}/extraction/confirm`, { headers: auth })).ok()).toBeTruthy();
  database({ action: 'seed', email: user.email, resume_id: resume.id, status: 'applied', prompt_version: 'profile-suggestions-v3', output: { suggestions: [], not_found: ['headline', 'location', 'target_roles', 'skills', 'experience', 'education', 'languages', 'remote_preference', 'work_authorization', 'salary_preference'] } });
  await login(page, user);
  await page.goto('/resumes');
  await expect(page.getByRole('button', { name: 'Refresh AI suggestions from this saved CV' })).toBeVisible();
  const uploads: string[] = [];
  page.on('request', req => { if (req.method() === 'POST' && req.url().endsWith('/resumes')) uploads.push(req.url()); });
  await page.getByRole('button', { name: 'Refresh AI suggestions from this saved CV' }).click();
  await expect(page.getByLabel('Proposed experience title')).toHaveCount(2);
  await expect(page.getByLabel('Proposed experience organization').first()).toHaveValue('Cedar Labs');
  await expect(page.getByLabel('Proposed experience organization').last()).toHaveValue('Pine Works');
  expect(uploads).toHaveLength(0);
  const latest = await (await request.get(`${API}/profile-suggestions/resumes/${resume.id}/latest`, { headers: auth })).json();
  expect(latest.field_statuses.experience).toBe('suggested');
  await page.getByRole('button', { name: 'Review profile changes' }).click();
  const region = page.getByRole('region', { name: 'Profile change comparison' });
  await expect(region.getByText('Developer · Cedar Labs')).toBeVisible();
  await expect(region.getByText('Engineer · Pine Works')).toBeVisible();
  await page.getByRole('button', { name: 'Save profile changes' }).click();
  await expect(page.getByRole('link', { name: 'View your profile' })).toBeVisible();
  const expected = [{ title: 'Developer', organization: 'Cedar Labs', period: 'June 2022 - July 2024', notes: 'Built APIs' }, { title: 'Engineer', organization: 'Pine Works', period: 'Jan 2020 - May 2022', notes: 'Built tests' }];
  expect(database({ action: 'check', email: user.email, set_id: latest.id, status: 'applied', expected: { experience: expected } }).matched).toBe(true);
  expect((await (await request.get(`${API}/profile`, { headers: auth })).json()).experience).toEqual(expected);
  await page.reload();
  await expect(page.getByRole('region', { name: 'Saved experience' }).getByText('Developer · Cedar Labs')).toBeVisible();
  await page.getByRole('link', { name: 'View your profile' }).click();
  await page.reload();
  await expect(page.getByText(/Cedar Labs · June 2022/)).toBeVisible();
  await expect(page.getByText(/Pine Works · Jan 2020/)).toBeVisible();
});

test('review stale AI suggestions and manual edits, commit all values, and reload both pages', async ({ page, request }) => {
  const user = await bootstrapUser(request, 'profile-review');
  const auth = { Authorization: `Bearer ${await accessToken(request, user)}` };
  const uploaded = await request.post(`${API}/resumes`, { headers: auth, multipart: { file: { name: 'profile-review.pdf', mimeType: 'application/pdf', buffer: pdf() } } });
  expect(uploaded.ok()).toBeTruthy();
  const resume = await uploaded.json();
  expect((await request.post(`${API}/resumes/${resume.id}/extract`, { headers: auth })).ok()).toBeTruthy();
  const source = 'Tripoli Python SQL Cedar University BSc Computer Science 2022 Academy AWS 2026 Arabic Native English Professional\nPROFESSIONAL EXPERIENCE\nDeveloper - Cedar Labs June 2022 - July 2024\nBuilt APIs\nPROJECT EXPERIENCE\nDemo project 2025';
  expect((await request.patch(`${API}/resumes/${resume.id}/extraction`, { headers: auth, data: { draft_text: source } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/resumes/${resume.id}/extraction/confirm`, { headers: auth })).ok()).toBeTruthy();
  const values = [
    { field: 'location', value: 'Tripoli' }, { field: 'skills', value: ['Python', 'SQL'] },
    { field: 'education', value: { school: 'Cedar University', degree: 'BSc', field: 'Computer Science', period: '2022' } },
    { field: 'education', value: { school: 'Academy', degree: 'AWS', field: null, period: '2026' } },
    { field: 'languages', value: { name: 'Arabic', proficiency: 'native' } },
    { field: 'languages', value: { name: 'English', proficiency: 'professional' } },
    { field: 'experience', value: { title: 'Developer', organization: 'Cedar Labs', period: 'June 2022 - July 2024', notes: 'Built APIs' } },
  ];
  const seeded = database({ action: 'seed', email: user.email, resume_id: resume.id, output: {
    suggestions: values.map((item, i) => ({ ...item, id: `s-${i}`, evidence: item.field === 'experience' ? [{ quote: 'Developer - Cedar Labs June 2022 - July 2024' }, { quote: 'Built APIs' }] : [{ quote: source }] })),
    not_found: ['target_roles', 'remote_preference', 'work_authorization', 'salary_preference'],
  } });
  // Exactly the reported ordering: manual profile creation makes the ready set stale.
  expect((await request.patch(`${API}/profile`, { headers: auth, data: { target_roles: ['Full-Stack Developer'], remote_preference: 'remote', work_authorization: 'other' } })).ok()).toBeTruthy();
  await login(page, user);
  const apiWrites: string[] = [];
  page.on('request', req => { if (req.method() === 'POST' && req.url().includes('/profile-suggestions/')) apiWrites.push(req.url()); });
  await page.goto('/resumes');
  await expect(page.getByLabel('Manual target role 1')).toHaveValue('Full-Stack Developer');
  await expect(page.getByLabel('Manual remote_preference')).toHaveValue('remote');
  await expect(page.getByLabel('Proposed languages name').first()).toHaveValue('Arabic');
  await page.getByLabel('Manual headline').fill('Full-Stack Engineer');
  await page.getByRole('button', { name: 'Add Experience' }).click();
  await page.getByLabel('Added 1 experience title').fill('Developer');
  await page.getByLabel('Added 1 experience organization').fill('Manual Company');
  await page.getByLabel('Manual salary_preference currency').fill('USD');
  await page.getByLabel('Manual salary_preference min').fill('60000');
  await page.getByLabel('Manual salary_preference max').fill('80000');
  await page.getByRole('button', { name: 'Review profile changes' }).click();
  await expect(page.getByRole('region', { name: 'Profile change comparison' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Profile change comparison' }).getByText('Developer · Cedar Labs')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Profile change comparison' }).getByText('Developer · Manual Company')).toBeVisible();
  expect(database({ action: 'check', email: user.email, set_id: seeded.id, status: 'ready', expected: { headline: null, languages: null, skills: null } }).matched).toBe(true);
  // A second save between review and confirmation must force another review.
  expect((await request.patch(`${API}/profile`, { headers: auth, data: { work_authorization: 'citizen' } })).ok()).toBeTruthy();
  await page.getByRole('button', { name: 'Save profile changes' }).click();
  await expect(page.locator('.profile-suggestions-panel [role="alert"]')).toContainText('The profile changed.');
  await expect(page.getByLabel('Manual headline')).toHaveValue('Full-Stack Engineer');
  await page.getByRole('button', { name: 'Review profile changes' }).click();
  const responsePromise = page.waitForResponse(r => r.url().endsWith(`/profile-suggestions/${seeded.id}/apply`) && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Save profile changes' }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  await expect(page.getByRole('link', { name: 'View your profile' })).toBeVisible();
  const expected = { headline: 'Full-Stack Engineer', target_roles: ['Full-Stack Developer'], location: 'Tripoli', skills: ['Python', 'SQL'], experience: [values[6].value, { title: 'Developer', organization: 'Manual Company', period: null, notes: null }], education: [values[2].value, values[3].value], languages: [values[4].value, values[5].value], remote_preference: 'remote', work_authorization: 'citizen', salary_preference: { currency: 'USD', min: 60000, max: 80000 } };
  expect((await response.json()).profile).toMatchObject(expected);
  expect(database({ action: 'check', email: user.email, set_id: seeded.id, status: 'applied', expected })).toEqual({ matched: true, fields: 10 });
  expect(await (await request.get(`${API}/profile`, { headers: auth })).json()).toMatchObject(expected);
  expect(apiWrites.every(url => url.endsWith('/review') || url.endsWith('/apply'))).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Manual headline')).toHaveValue('Full-Stack Engineer');
  await expect(page.getByLabel('Proposed languages proficiency').first()).toHaveValue('native');
  await expect(page.getByRole('region', { name: 'Saved experience' }).getByText('Developer · Manual Company')).toBeVisible();
  await page.getByRole('link', { name: 'View your profile' }).click();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Full-Stack Engineer', exact: true })).toBeVisible();
  await expect(page.getByText('Arabic', { exact: true })).toBeVisible();
  await expect(page.getByText('English', { exact: true })).toBeVisible();
  await expect(page.getByText(/Cedar Labs · June 2022/)).toBeVisible();
  await expect(page.getByText('Manual Company', { exact: true })).toBeVisible();
  await expect(page.getByText('Cedar University · 2022', { exact: true })).toBeVisible();
  await expect(page.getByText('Academy · 2026', { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('saved-profile.png'), fullPage: true });
});
