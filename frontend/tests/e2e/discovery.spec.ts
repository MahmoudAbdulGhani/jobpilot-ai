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
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/,{timeout:15000});
  const jobId=page.url().split('/').pop();
  await expect(page.getByRole('heading',{name:'Synthetic Backend Engineer',exact:true})).toBeVisible();
  await expect(page.getByText(/Imported from JobTech JobSearch/)).toBeVisible();
  await page.getByRole('tab', { name: 'Application pack', exact: true }).click();
  await expect(page.getByText('CV & cover letter packs')).toBeVisible();
  await page.getByRole('tab', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('button',{name:/Analyze fit/})).toBeVisible();
  // The imported row uses the existing APIs and has no special editing restrictions.
  expect((await request.patch(`${API}/jobs/${jobId}`,{headers,data:{title:'My reviewed title',notes:'Keep my notes'}})).ok()).toBeTruthy();
  expect((await request.patch(`${API}/profile`,{headers,data:{headline:'Backend engineer',skills:['Python','PostgreSQL']}})).ok()).toBeTruthy();
  expect((await request.patch(`${API}/privacy/consents`,{headers,data:{key:'ai_job_fit',allowed:true,confirm:true}})).ok()).toBeTruthy();
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
  await page.getByRole('tab', { name: 'Tracking', exact: true }).click();
  await expect(page.getByPlaceholder('Optional notes', {exact:true})).toHaveValue('Synthetic tracking verification only');
});

test('Jobicy remote → region preview → cross-source warning → explicit separate import',async({page,request})=>{
  const user=await bootstrapUser(request,'jobicy');
  const token=await accessToken(request,user),headers={Authorization:`Bearer ${token}`};
  const first=await request.get(`${API}/discovery/synthetic-100/preview`,{headers});expect(first.ok()).toBeTruthy();
  expect((await request.post(`${API}/discovery/import`,{headers,data:{preview_token:(await first.json()).preview_token,confirm:true}})).status()).toBe(201);
  await login(page,user);await page.getByRole('link',{name:'Discover jobs',exact:true}).click();
  await page.getByLabel('Source',{exact:true}).selectOption('jobicy');
  await page.getByLabel('Applicant region text (Jobicy cache)').fill('EMEA');
  await page.getByRole('button',{name:'Search Jobicy'}).click();
  await expect(page.getByText('EMEA',{exact:true})).toBeVisible();
  await expect(page.getByText(/Possible cross-source match/)).toBeVisible();
  await page.getByRole('button',{name:'Preview job'}).click();
  await expect(page.getByRole('heading',{name:'Preview: Synthetic Backend Engineer'})).toBeFocused();
  expect((await (await request.get(`${API}/jobs`,{headers})).json()).total).toBe(1);
  await page.getByRole('button',{name:'Import this job into saved jobs'}).click();
  await page.getByRole('link',{name:'Open saved job',exact:true}).click();
  await expect(page.getByText(/Imported from Jobicy/)).toBeVisible();
  await page.getByText('Imported source details').click();
  await expect(page.getByText(/Applicant region \(source\): EMEA/)).toBeVisible();
  expect((await (await request.get(`${API}/jobs`,{headers})).json()).total).toBe(2);
  const id=page.url().split('/').pop();
  expect((await request.patch(`${API}/jobs/${id}`,{headers,data:{title:'My Jobicy edits',notes:'Preserve'}})).ok()).toBeTruthy();
  const preview=await request.get(`${API}/discovery/123456/preview?source=jobicy`,{headers});
  const duplicate=await request.post(`${API}/discovery/import`,{headers,data:{preview_token:(await preview.json()).preview_token,confirm:true}});
  expect(duplicate.status()).toBe(200);expect((await duplicate.json()).job.notes).toBe('Preserve');
});
