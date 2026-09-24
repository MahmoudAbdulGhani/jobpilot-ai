import {test,expect} from '@playwright/test';
import {API,bootstrapUser,accessToken,login,cleanupUser,createdUsers} from './helpers';
test.afterEach(async({request})=>{for(const email of createdUsers.splice(0))await cleanupUser(request,email);});

test('guarded usage display and exhausted actions preserve saved data',async({page,request})=>{
  const user=await bootstrapUser(request,'usage'),token=await accessToken(request,user),headers={Authorization:`Bearer ${token}`};
  const response=await request.post(`${API}/jobs`,{headers,data:{title:'Synthetic entitlement job',company:'Synthetic',description:'Python is required.'}});
  expect(response.ok()).toBeTruthy();const job=await response.json();
  await login(page,user);await page.goto('/settings/usage');
  await expect(page.getByRole('heading',{name:'Free access'})).toBeVisible();
  await page.getByText('Billing and future pricing', { exact: true }).click();
  await expect(page.getByText(/Billing is not available/)).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByText(/^Resets .*00:00 UTC/)).toBeVisible();
  const exhausted=await request.post(`${API}/e2e/exhaust-usage`,{headers});
  expect(exhausted.ok()).toBeTruthy();expect((await exhausted.json()).provider_requests_sent).toBe(0);
  await page.getByRole('button',{name:'Refresh usage'}).click();
  await expect(page.locator('.account-allowance-number strong')).toHaveText('0');
  await expect(page.getByText('Allowance exhausted').first()).toBeVisible();
  await page.goto(`/jobs/${job.id}`);
  await expect(page.getByRole('button',{name:'Analyze fit',exact:true})).toBeDisabled();
  await page.getByRole('tab', { name: 'Application pack', exact: true }).click();
  await expect(page.getByRole('button',{name:/Generate application pack/})).toBeDisabled();
  expect((await request.get(`${API}/jobs/${job.id}`,{headers})).ok()).toBeTruthy();
  expect((await request.post(`${API}/account/usage`,{headers,data:{plan:'paid'}})).status()).toBe(405);
  await page.goto('/settings');await expect(page.getByRole('heading',{name:'Your account data'})).toBeVisible();
});
