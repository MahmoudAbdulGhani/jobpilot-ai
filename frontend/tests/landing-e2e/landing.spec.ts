import { expect, test as base, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const evidence = resolve(__dirname, '../../../evidence/landing');

const test = base.extend<{ browserErrors: string[] }>({
  browserErrors: [async ({ page }, use) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    await use(errors);
    expect(errors, 'The page must not emit browser errors').toEqual([]);
  }, { auto: true }],
});

/** This suite never contacts a backend, AI service, email service, or job source. */
async function mockApi(page: Page, authenticated = false) {
  const calls: string[] = [];
  await page.route('**/api/**', async route => {
    const pathname = new URL(route.request().url()).pathname.replace(/^\/api/, '');
    calls.push(`${route.request().method()} ${pathname}`);
    let body: unknown = { items: [], total: 0, page: 1, page_size: 20, next_cursor: null };
    if (pathname === '/auth/refresh') body = { access_token: 'synthetic-landing-session' };
    if (pathname === '/auth/me') body = authenticated ? {
      id: 'landing-browser-test-user', email: 'landing-test@example.invalid',
      is_active: true, onboarding_step: 'done',
    } : null;
    if (pathname === '/account/options') body = { registration: 'public' };
    if (pathname === '/insights') body = {
      application_counts: {}, replies: [], links: [], recommendations: [],
    };
    if (pathname === '/account/usage') body = {
      plan: 'free', base_plan: 'free', admin: false, billing_available: false,
      features: {}, total: { allowance: 20, consumed: 0, remaining: 20 },
      reset_at: '2026-10-01T00:00:00Z', reset_timezone: 'UTC',
      period_start: '2026-09-01T00:00:00Z', beta_expires_at: null,
      beta_revoked_at: null, proposed_monthly_price_usd: '0',
      price_note: 'Synthetic test data', history_note: '',
    };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return calls;
}

async function openLanding(page: Page) {
  const calls = await mockApi(page);
  await page.goto('/');
  await expect(page.locator('.lp-header')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  return calls;
}

async function noHorizontalOverflow(page: Page) {
  const bounds = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(bounds.scroll, `Document width ${bounds.scroll} exceeds viewport ${bounds.viewport}`).toBeLessThanOrEqual(bounds.viewport + 1);
}

async function screenshot(page: Page, name: string, fullPage = false) {
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({ path: resolve(evidence, `${name}.png`), fullPage, animations: 'disabled' });
}

async function scrollWorkflow(page: Page, progress: number, chapter: number) {
  const story = page.locator('#how-it-works');
  const position = await story.locator('.pin-spacer').evaluate((element, fraction) => {
    const pin = element.querySelector<HTMLElement>('.lp-workflow-pin')!;
    const spacerBox = element.getBoundingClientRect();
    const distance = spacerBox.height - pin.getBoundingClientRect().height;
    return spacerBox.top + window.scrollY - 84 + distance * fraction;
  }, progress);
  await page.evaluate(y => window.scrollTo({ top: y, behavior: 'instant' }), position);
  await expect(story).toHaveAttribute('data-active-step', String(chapter));
  await expect(story.locator(`[data-workflow-scene="${chapter}"]`)).toHaveCSS('opacity', '1');
  await expect(story.locator('.lp-workflow-pin')).toHaveCSS('position', 'fixed');
  await noHorizontalOverflow(page);
}

test('public navigation, keyboard FAQ, and sign-in destination work', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(page);
  const nav = page.getByRole('navigation', { name: 'Main navigation', exact: true });
  for (const [name, hash] of [
    ['How it works', '#how-it-works'], ['Features', '#features'],
    ['Product preview', '#product-preview'], ['FAQ', '#faq'],
  ]) {
    await nav.getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${hash}$`));
    await expect(page.locator(hash)).toBeInViewport();
  }
  const question = page.locator('#faq summary').first();
  await question.focus();
  await expect(question).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(question.locator('..')).toHaveAttribute('open', '');
  await page.keyboard.press('Space');
  await expect(question.locator('..')).not.toHaveAttribute('open', '');
  await page.locator('.lp-header').getByRole('link', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
});

test('mobile navigation closes after following a section and restores keyboard focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(page);
  const trigger = page.getByRole('button', { name: 'Open navigation', exact: true });
  await trigger.click();
  const nav = page.getByRole('navigation', { name: 'Mobile navigation', exact: true });
  await expect(nav).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(nav).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await nav.getByRole('link', { name: 'FAQ', exact: true }).click();
  await expect(nav).not.toBeVisible();
  await expect(page).toHaveURL(/#faq$/);
  await expect(page.locator('#faq')).toBeInViewport();
  await noHorizontalOverflow(page);
});

test('sample role preferences update jobs and the application preview is keyboard accessible', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const calls = await openLanding(page);
  const preview = page.locator('#product-preview');
  const roles = preview.getByRole('tablist', { name: 'Sample role preference' });
  await expect(preview.getByRole('heading', { name: 'Senior Product Designer', exact: true })).toBeVisible();
  await roles.getByRole('tab', { name: 'Engineering', exact: true }).click();
  await expect(preview.getByRole('heading', { name: 'Senior Frontend Engineer', exact: true })).toBeVisible();
  await expect(preview.getByRole('heading', { name: 'Senior Product Designer', exact: true })).not.toBeVisible();
  await roles.getByRole('tab', { name: 'Marketing', exact: true }).click();
  await expect(preview.getByRole('heading', { name: 'Content Marketing Lead', exact: true })).toBeVisible();
  await roles.getByRole('tab', { name: 'Product design', exact: true }).click();
  const trigger = preview.getByRole('button', { name: 'Preview application for Senior Product Designer at Northstar Studio', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'A starting point. Make it yours.', exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('tabpanel')).toContainText('Alex Morgan');
  const documents = dialog.getByRole('tablist', { name: 'Application documents' });
  await documents.getByRole('tab', { name: 'CV', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(documents.getByRole('tab', { name: 'Cover letter', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(dialog.getByRole('tabpanel')).toContainText('Dear Northstar Studio team,');
  await page.keyboard.press('ArrowRight');
  await expect(documents.getByRole('tab', { name: 'Email preview', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(dialog.getByRole('tabpanel')).toContainText('Hiring team at Northstar Studio');
  await expect(dialog).toContainText('Sample content only. Nothing is saved or sent.');
  await screenshot(page, 'application-preview');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  expect(calls, 'The illustrative demo must not make API calls').toEqual([]);
});

test('reviewing a sample lets the visitor edit, decline, approve, and reset a change', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const calls = await openLanding(page);
  const review = page.locator('#your-control');
  const headline = review.getByLabel('Suggested headline', { exact: true });
  const selection = review.getByRole('checkbox', { name: 'Include this headline update', exact: true });
  const approve = review.getByRole('button', { name: 'Approve sample change', exact: true });
  await headline.fill('Product designer making complex workflows feel simple');
  await expect(review.locator('.lp-control-summary-proposed')).toContainText('Product designer making complex workflows feel simple');
  await selection.uncheck();
  await expect(approve).toBeDisabled();
  await selection.check();
  await headline.fill('   ');
  await expect(approve).toBeDisabled();
  await headline.fill('Product designer making complex workflows feel simple');
  await approve.click();
  await expect(review.getByRole('status')).toContainText('Approved in this demo.');
  await expect(headline).toBeDisabled();
  await screenshot(page, 'review-approved');
  await review.getByRole('button', { name: 'Edit again', exact: true }).click();
  await expect(headline).toBeEnabled();
  await review.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(review.getByRole('status')).toContainText('Changes canceled. Nothing was applied.');
  await expect(selection).not.toBeChecked();
  await review.getByRole('button', { name: 'Reset demo', exact: true }).click();
  await expect(selection).toBeChecked();
  await expect(headline).toHaveValue('Product designer creating thoughtful digital experiences');
  expect(calls, 'Reviewing a sample must not send or persist any data').toEqual([]);
});

test('application documents remain readable in a narrow mobile dialog', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(page);
  await page.locator('#product-preview').getByRole('button', {
    name: 'Preview application for Senior Product Designer at Northstar Studio', exact: true,
  }).click();
  const dialog = page.getByRole('dialog', { name: 'A starting point. Make it yours.', exact: true });
  await expect(dialog).toBeVisible();
  for (const name of ['CV', 'Cover letter', 'Email preview']) {
    await dialog.getByRole('tab', { name, exact: true }).click();
    await expect(dialog.getByRole('tabpanel')).toBeVisible();
    const bounds = await dialog.evaluate(element => ({
      width: element.scrollWidth, client: element.clientWidth,
      left: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right,
    }));
    expect(bounds.width).toBeLessThanOrEqual(bounds.client + 1);
    expect(bounds.left).toBeGreaterThanOrEqual(0);
    expect(bounds.right).toBeLessThanOrEqual(390);
  }
  await screenshot(page, 'application-preview-mobile');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
});

test('reduced motion leaves all five workflow chapters readable without pinning', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(page);
  const story = page.locator('#how-it-works');
  await expect(story).toHaveAttribute('data-workflow-mode', 'static');
  await expect(story.locator('[data-workflow-scene]')).toHaveCount(5);
  for (let chapter = 0; chapter < 5; chapter += 1) {
    const scene = story.locator(`[data-workflow-scene="${chapter}"]`);
    await scene.scrollIntoViewIfNeeded();
    await expect(scene).toBeInViewport();
    await expect(scene).toHaveCSS('opacity', '1');
    await expect(scene.getByRole('heading', { level: 3 })).toBeVisible();
  }
  await expect(page.locator('.pin-spacer')).toHaveCount(0);
  await expect(story.locator('.lp-workflow-pin')).not.toHaveCSS('position', 'fixed');
  await noHorizontalOverflow(page);
});

test('desktop workflow progresses, reverses, responds to resize, and cleans up on navigation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await openLanding(page);
  const story = page.locator('#how-it-works');
  await expect(story).toHaveAttribute('data-workflow-mode', 'animated');
  await expect(story.locator('.pin-spacer')).toHaveCount(1);
  await expect(page.locator('.lp-review-receipt')).toHaveCSS('opacity', '1');
  await screenshot(page, 'desktop-hero');

  await scrollWorkflow(page, 0.08, 0);
  await screenshot(page, 'workflow-beginning');
  await scrollWorkflow(page, 0.50, 2);
  await expect(story.locator('[data-workflow-scene]:not([inert])')).toHaveCount(1);
  await expect(story.locator('[data-workflow-scene][inert]')).toHaveCount(4);
  await expect(story.locator('[data-workflow-scene="2"]')).not.toHaveAttribute('inert');
  await expect(story.locator('[data-workflow-scene="2"]')).not.toHaveAttribute('aria-hidden', 'true');
  await screenshot(page, 'workflow-middle');
  await scrollWorkflow(page, 0.94, 4);
  await screenshot(page, 'workflow-end');
  await scrollWorkflow(page, 0.30, 1);
  await scrollWorkflow(page, 0.08, 0);
  await page.setViewportSize({ width: 768, height: 1000 });
  await expect(story).toHaveAttribute('data-workflow-mode', 'static');
  await expect(page.locator('.pin-spacer')).toHaveCount(0);
  for (let chapter = 0; chapter < 5; chapter += 1) {
    await expect(story.locator(`[data-workflow-scene="${chapter}"]`)).toHaveCSS('opacity', '1');
  }
  await noHorizontalOverflow(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(story).toHaveAttribute('data-workflow-mode', 'animated');
  await expect(story.locator('.pin-spacer')).toHaveCount(1);
  await scrollWorkflow(page, 0.50, 2);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(story).toHaveAttribute('data-workflow-mode', 'static');
  await expect(page.locator('.pin-spacer')).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(story).toHaveAttribute('data-workflow-mode', 'animated');
  await expect(story.locator('.pin-spacer')).toHaveCount(1);
  await page.locator('.lp-header').getByRole('link', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('.pin-spacer')).toHaveCount(0);
  await expect(page.locator('#how-it-works')).toHaveCount(0);
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
});

test('the review chapter fits its product stage at 1024 by 768', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await openLanding(page);
  const story = page.locator('#how-it-works');
  await expect(story).toHaveAttribute('data-workflow-mode', 'animated');
  await scrollWorkflow(page, 0.72, 3);
  const scene = story.locator('[data-workflow-scene="3"]');
  await expect(scene.getByRole('link', { name: 'Try a sample review', exact: true })).toBeVisible();
  const stage = await story.locator('.lp-workflow-stage').boundingBox();
  expect(stage).not.toBeNull();
  expect(stage!.y).toBeGreaterThanOrEqual(0);
  expect(stage!.y + stage!.height).toBeLessThanOrEqual(769);
  const clipped = await scene.evaluate(element => {
    const viewport = element.closest('.lp-workflow-scenes')!.getBoundingClientRect();
    return Array.from(element.querySelectorAll<HTMLElement>('.lp-workflow-piece')).filter(piece => {
      const bounds = piece.getBoundingClientRect();
      return bounds.left < viewport.left - 1 || bounds.right > viewport.right + 1
        || bounds.top < viewport.top - 1 || bounds.bottom > viewport.bottom + 1
        || piece.scrollWidth > piece.clientWidth + 1;
    }).map(piece => piece.className);
  });
  expect(clipped, 'Review content must fit inside the visible cream product stage').toEqual([]);
  await screenshot(page, 'workflow-review-1024x768');
});

for (const width of [360, 390, 768, 1024, 1440]) {
  test(`landing stays within a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openLanding(page);
    await noHorizontalOverflow(page);
    if (width === 390) await screenshot(page, 'mobile-hero-390');
    for (const id of ['how-it-works', 'features', 'product-preview', 'faq']) {
      await page.locator(`#${id}`).scrollIntoViewIfNeeded();
      await noHorizontalOverflow(page);
    }
    if (width === 390 || width === 1440) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await screenshot(page, width === 390 ? 'mobile-390' : 'desktop-1440', true);
      if (width === 390) {
        await page.locator('.lp-hero-scene').screenshot({
          path: resolve(evidence, 'mobile-product-scene.png'), animations: 'disabled',
          style: '.lp-header { visibility: hidden; }',
        });
      }
    }
  });
}

test('an existing session goes to its workspace and can render empty overview data', async ({ page, context }) => {
  const calls = await mockApi(page, true);
  await context.addCookies([{ name: 'jobpilot_csrf', value: 'synthetic-csrf', url: 'http://localhost:3025' }]);
  await page.goto('/');
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole('heading', { name: 'Your next step, in view.', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Start with one opportunity.', exact: true })).toBeVisible();
  expect(calls).toContain('POST /auth/refresh');
  expect(calls).toContain('GET /auth/me');
  await expect(page.locator('.lp-header')).toHaveCount(0);
});

test('an existing session can still open its applications and empty state', async ({ page, context }) => {
  const calls = await mockApi(page, true);
  await context.addCookies([{ name: 'jobpilot_csrf', value: 'synthetic-csrf', url: 'http://localhost:3025' }]);
  await page.goto('/applications');
  await expect(page).toHaveURL(/\/applications$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Applications', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Your next chapter starts here', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary', exact: true }).getByRole('link', { name: 'Applications', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('link', { name: 'Go to saved jobs', exact: true })).toHaveAttribute('href', '/jobs');
  expect(calls).toContain('GET /applications');
  await expect(page.locator('.lp-header')).toHaveCount(0);
});

for (const route of ['/overview', '/applications']) {
  test(`a logged-out visitor cannot open protected ${route}`, async ({ page }) => {
    await mockApi(page);
    await page.goto(route);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
  });
}

test('server-rendered landing content and FAQ remain usable without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false, viewport: { width: 1440, height: 1000 },
    baseURL: 'http://localhost:3025',
  });
  const page = await context.newPage();
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.locator('#how-it-works')).toBeVisible();
  await expect(page.locator('#product-preview')).toBeVisible();
  await expect(page.locator('[data-workflow-scene]')).toHaveCount(5);
  for (let chapter = 0; chapter < 5; chapter += 1) {
    await expect(page.locator(`[data-workflow-scene="${chapter}"]`)).toHaveCSS('opacity', '1');
  }
  await expect(page.locator('.pin-spacer')).toHaveCount(0);
  const question = page.locator('#faq summary').first();
  await question.click();
  await expect(question.locator('..')).toHaveAttribute('open', '');
  await noHorizontalOverflow(page);
  await context.close();
});
