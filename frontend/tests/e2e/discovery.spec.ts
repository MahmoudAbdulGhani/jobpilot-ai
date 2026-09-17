import { expect, test } from '@playwright/test';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, login } from './helpers';

test.afterEach(async ({request}) => {
  for (const email of createdUsers) await cleanupUser(request,email);
  createdUsers.length=0;
});

test('search, preview and reviewed import preserves edits and connects to saved-job tools', async ({page,request}) => {
  const user=await bootstrapUser(request,'discovery');
  await login(page,user);
  await page.getByRole('link',{name:'Discover jobs',exact:true}).click();
  await page.getByLabel('Keywords').fill('Python');
  await page.getByRole('button',{name:'Search JobTech'}).click();
  await expect(page.getByRole('heading',{name:'Synthetic Backend Engineer',exact:true})).toBeVisible();
  await expect(page.getByText('Synthetic test listing — not a live result')).toBeVisible();
  await page.screenshot({path:test.info().outputPath('discovery-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path:test.info().outputPath('discovery-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1280,height:720});
  await page.getByRole('button',{name:'Preview job'}).click();
  await expect(page.getByRole('heading',{name:'Preview: Synthetic Backend Engineer'})).toBeFocused();
  const token=await accessToken(request,user), headers={Authorization:`Bearer ${token}`};
  expect((await (await request.get(`${API}/jobs`,{headers})).json()).total).toBe(0);
  await page.getByRole('button',{name:'Import this job into saved jobs'}).click();
  await page.getByRole('link',{name:'Open saved job',exact:true}).click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/);
  const jobId=page.url().split('/').pop();
  await expect(page.getByRole('heading',{name:'Synthetic Backend Engineer',exact:true})).toBeVisible();
  await expect(page.getByText(/Imported from JobTech JobSearch/)).toBeVisible();
  await expect(page.getByText('CV & cover letter packs')).toBeVisible();
  await expect(page.getByRole('button',{name:/Analyze fit/})).toBeVisible();
  // The imported row uses the existing APIs and has no special editing restrictions.
  expect((await request.patch(`${API}/jobs/${jobId}`,{headers,data:{title:'My reviewed title',notes:'Keep my notes'}})).ok()).toBeTruthy();
  expect((await request.patch(`${API}/profile`,{headers,data:{headline:'Backend engineer',skills:['Python','PostgreSQL']}})).ok()).toBeTruthy();
  await page.reload();
  await page.getByRole('button',{name:/Analyze fit/}).click();
  await expect(page.getByText('Synthetic deterministic analysis for application-contract testing.')).toBeVisible({timeout:15000});
  await page.getByRole('link',{name:'Discover jobs',exact:true}).click();
  await page.getByRole('button',{name:'Search JobTech'}).click();
  await page.getByRole('link',{name:'Already saved — open existing job'}).click();
  await expect(page.getByRole('heading',{name:'My reviewed title',exact:true})).toBeVisible();
  const saved=await (await request.get(`${API}/jobs/${jobId}`,{headers})).json();
  expect(saved.notes).toBe('Keep my notes');
  expect(saved.source_snapshot.title).toBe('Synthetic Backend Engineer');
  expect((await (await request.get(`${API}/jobs`,{headers})).json()).total).toBe(1);
  // Recording a synthetic tracking entry is local persistence, not sending an application.
  const tracking=await request.post(`${API}/jobs/${jobId}/applications`,{headers,data:{submission_date:'2026-09-17T09:00:00Z',method:'other',notes:'Synthetic tracking verification only'}});
  expect(tracking.status()).toBe(201);
  await page.reload();
  await expect(page.getByPlaceholder('Optional notes', {exact:true})).toHaveValue('Synthetic tracking verification only');
});
