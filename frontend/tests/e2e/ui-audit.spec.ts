import { test, expect } from '@playwright/test';
import { API, bootstrapUser, cleanupUser, accessToken, grantAiConsent } from './helpers';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

test('workspace route and responsive visual audit', async ({ page, request, browser }, testInfo) => {
  test.setTimeout(480_000);
  const user = await bootstrapUser(request, 'visual');
  try {
    await grantAiConsent(request, user, ['ai_interview']);
    const token = await accessToken(request, user);
    const headers = { Authorization: `Bearer ${token}` };
    const response = await request.post(`${API}/jobs`, { headers, data: { title: 'Senior product engineer', company: 'Northstar Studio', location: 'Beirut · Hybrid', description: 'Build thoughtful tools for people.\n\nResponsibilities\nDesign accessible interfaces and reliable services. Work with a small multidisciplinary team.', notes: 'Review the role and prepare examples of recent work.' } });
    expect(response.ok()).toBeTruthy();
    const job = await response.json();
    expect((await request.patch(`${API}/profile`, { headers, data: { headline: 'Product engineer', location: 'Beirut, Lebanon', skills: ['TypeScript', 'Python', 'Accessible interfaces'], experience: [{ title: 'Software Engineer', organization: 'Northstar Studio', period: '2022–present', notes: 'Built reliable tools with a small product team.' }] } })).ok()).toBeTruthy();
    const buffer = execFileSync(path.resolve('../backend/.venv/Scripts/python.exe'), ['-c', "from docx import Document; from io import BytesIO; import sys; d=Document(); d.add_paragraph('Synthetic product engineer with TypeScript and Python experience.'); b=BytesIO(); d.save(b); sys.stdout.buffer.write(b.getvalue())"]);
    const upload = await request.post(`${API}/resumes`, { headers, multipart: { file: { name: 'Product engineer.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer } } });
    expect(upload.ok()).toBeTruthy();
    const resume = await upload.json();
    expect((await request.post(`${API}/resumes/${resume.id}/extract`, { headers })).ok()).toBeTruthy();
    expect((await request.post(`${API}/resumes/${resume.id}/extraction/confirm`, { headers })).ok()).toBeTruthy();
    const selection = { resume_id: resume.id, mode: 'mixed', question_count: 2 };
    const preview = await request.post(`${API}/jobs/${job.id}/interviews/preview`, { headers, data: selection });
    expect(preview.ok()).toBeTruthy();
    const started = await request.post(`${API}/jobs/${job.id}/interviews`, { headers, data: { ...selection, preview_hash: (await preview.json()).preview_hash, request_key: crypto.randomUUID(), confirm: true } });
    expect(started.ok()).toBeTruthy();
    const interview = await started.json();
    expect((await request.post(`${API}/jobs/${job.id}/applications`, { headers, data: { submission_date: '2026-09-24T09:00:00Z', method: 'employer_website', status: 'Applied', notes: 'Portfolio submitted; review follow-up timing.' } })).ok()).toBeTruthy();
    await page.goto('/login');
    await page.getByLabel('Email', { exact: true }).fill(user.email);
    await page.getByLabel('Password', { exact: true }).fill(user.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).not.toHaveURL(/\/login$/);
    const routes = ['overview', 'jobs', `jobs/${job.id}`, `jobs/${job.id}/interviews`, `interviews/${interview.id}`, 'applications', 'discover', 'reminders', 'insights', 'resumes', 'profile', 'settings', 'settings/usage', 'archive', 'onboarding'];
    for (const route of routes) {
      if (process.env.UI_AUDIT_STAGE === 'before' && route === 'overview') continue;
      await page.goto(`/${route}`);
      await expect(page.locator('main h1').first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.getByText(/^Loading|^Opening your journal/).first()).toBeHidden({ timeout: 15_000 });
      for (const width of [1488, 390, 320, 375, 768, 1024, 1280, 1440]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1058 });
        await page.evaluate(() => new Promise(requestAnimationFrame));
        if (width === 1488 || width === 390) await page.screenshot({ path: testInfo.outputPath(`${process.env.UI_AUDIT_STAGE || 'after'}-${route.replaceAll('/', '-')}-${width}.png`), fullPage: true });
        const overflow = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth, elements: Array.from(document.querySelectorAll('main *')).filter(element => element.getBoundingClientRect().right > innerWidth + 1).slice(0, 12).map(element => `${element.tagName}.${element.className}`) }));
        expect(overflow.width <= overflow.viewport, `${route} at ${width}px: ${JSON.stringify(overflow)}`).toBeTruthy();
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/jobs');
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused();
    await page.getByRole('button', { name: 'Save a job', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByLabel('Job title')).toBeFocused();
    await dialog.getByLabel('Job title').fill('Unsaved example');
    await page.keyboard.press('Escape');
    await expect(dialog.getByText('You have unsaved changes. Discard them?')).toBeVisible();
    await dialog.getByRole('button', { name: 'Keep editing' }).click();
    await expect(dialog.getByLabel('Job title')).toHaveValue('Unsaved example');
    for (let index = 0; index < 15; index += 1) {
      await page.keyboard.press('Tab');
      expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    }
    await page.screenshot({ path: testInfo.outputPath('after-job-editor-390.png') });
    await page.keyboard.press('Escape');
    await dialog.getByRole('button', { name: 'Discard changes' }).click();
    await expect(page.getByRole('button', { name: 'Save a job', exact: true })).toBeFocused();
    // A 1488px desktop at 200% has a 744px CSS viewport. Scale screenshots
    // back to physical pixels while exercising that reflow and authenticated state.
    const zoomContext = await browser.newContext({ viewport: { width: 744, height: 529 }, deviceScaleFactor: 2, storageState: await page.context().storageState() });
    try {
      const zoomPage = await zoomContext.newPage();
      for (const route of ['overview', 'settings', `jobs/${job.id}`]) {
        await zoomPage.goto(`http://localhost:3010/${route}`);
        await expect(zoomPage.locator('main h1').first()).toBeVisible();
        expect(await zoomPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `200% equivalent reflow: ${route}`).toBe(true);
      }
      await zoomPage.screenshot({ path: testInfo.outputPath('after-job-detail-200-percent-equivalent.png'), fullPage: true });
    } finally { await zoomContext.close(); }
  } finally { await cleanupUser(request, user.email); }
});

test('authentication screens reflow without horizontal overflow', async ({ page }, testInfo) => {
  for (const width of [1488, 390, 320]) {
    await page.setViewportSize({ width, height: width === 1488 ? 1058 : 844 });
    for (const route of ['login', 'register', 'verify-email', 'forgot-password', 'reset-password']) {
      await page.goto(`/${route}`);
      await expect(page.locator('h1')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      if (width !== 320) await page.screenshot({ path: testInfo.outputPath(`after-${route}-${width}.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    }
  }
});
