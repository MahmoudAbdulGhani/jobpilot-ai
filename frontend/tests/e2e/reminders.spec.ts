import {test,expect} from '@playwright/test';
import {API,bootstrapUser,accessToken,login,cleanupUser,createdUsers} from './helpers';

test.afterEach(async({request})=>{for(const email of createdUsers.splice(0))await cleanupUser(request,email);});
test('reminder create reload snooze complete',async({page,request})=>{
  const user=await bootstrapUser(request,'reminders');const token=await accessToken(request,user);
  const headers={Authorization:`Bearer ${token}`};
  const jobResponse=await request.post(`${API}/jobs`,{headers,data:{title:'Reminder engineer',company:'Synthetic',description:'Offline reminder scenario'}});
  expect(jobResponse.ok()).toBeTruthy();const job=await jobResponse.json();
  const application=await request.post(`${API}/jobs/${job.id}/applications`,{headers,data:{submission_date:new Date().toISOString(),method:'other',status:'Applied'}});
  expect(application.ok()).toBeTruthy();
  await login(page,user);await page.goto(`/jobs/${job.id}#tracking`);
  await page.getByLabel('Reminder date and time').fill('2020-01-01T10:00');
  await page.getByLabel('Reminder timezone').fill('UTC');
  await page.getByRole('button',{name:'Create reminder',exact:true}).click();
  await expect(page.getByText('active — Due now',{exact:false})).toBeVisible();
  await page.reload();await expect(page.getByText('active — Due now',{exact:false})).toBeVisible();
  await page.getByLabel('Reminder date and time').fill('2035-01-01T10:00');
  await page.getByRole('button',{name:'Snooze to selected time'}).click();
  await expect(page.locator('time[datetime^="2035-01-01"]')).toBeVisible();
  await page.getByRole('button',{name:'Complete reminder',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'Complete reminder',exact:true}).click();
  await expect(page.getByText('completed ·',{exact:false})).toBeVisible();
  await page.goto('/reminders');await page.getByLabel('Show reminders').selectOption('completed');
  await expect(page.getByRole('link',{name:'Reminder engineer · Synthetic'})).toBeVisible();
});
