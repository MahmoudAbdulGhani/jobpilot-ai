import {test,expect} from '@playwright/test';
import {bootstrapUser,cleanupUser,login,API} from './helpers';

test('private export → confirmed deletion → disabled session and pending receipt',async({page,request})=>{
 const user=await bootstrapUser(request,'account-data');
 // Explicit synthetic recovery login keeps this independent of persistent users.
 const recovery=await bootstrapUser(request,'account-data-recovery');
 try{
  await login(page,user);await page.getByRole('link',{name:'Settings',exact:true}).click();
  await page.getByLabel('Confirm your password').fill(user.password);
  const downloaded=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export my data'}).click();
  expect((await downloaded).suggestedFilename()).toBe('jobpilot-account.zip');
  await expect(page.getByText(/Export download prepared/)).toBeVisible();
  await page.getByLabel('Confirm your password').fill(user.password);
  await page.getByLabel(/Type DELETE MY ACCOUNT/).fill('DELETE MY ACCOUNT');
  await page.getByRole('button',{name:'Permanently delete my account'}).click();
  await expect(page.getByText(/Deletion accepted/)).toBeVisible();
  await page.getByRole('button',{name:'Check deletion status'}).click();
  await expect(page.getByText('Cleanup pending; removal is not complete.')).toBeVisible();
  const denied=await request.post(`${API}/auth/login`,{data:user});expect(denied.status()).toBe(401);
 }finally{await cleanupUser(request,user.email);await cleanupUser(request,recovery.email);}
});
