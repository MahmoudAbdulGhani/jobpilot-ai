import { test, expect } from '@playwright/test';
import { API } from './helpers';

test('invitation → verification → resumable onboarding → password reset', async ({page,request})=>{
 const fixture=await request.post(`${API}/e2e/account-fixture`);expect(fixture.ok()).toBeTruthy();
 const {email,ticket,invitation}=await fixture.json();
 let password='Synthetic-onboarding-password-1';
 try{
  await page.goto(`/register#token=${invitation}`);
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByLabel('Confirm password').fill(password);
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('accepted by the transport');
  let message=await request.post(`${API}/e2e/account-message`,{data:{ticket}});
  let text=(await message.json()).text as string;
  await page.goto(text.match(/http[^\s]+/)![0]);
  await page.getByRole('button',{name:'Verify email',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.getByRole('link',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByRole('button',{name:'Skip for now'}).click();
  await expect(page.getByRole('status')).toContainText('Upload and review a CV');
  await page.reload();await expect(page.getByRole('status')).toContainText('Upload and review a CV');
  await page.locator('.account-toggle').click();await page.getByRole('menuitem',{name:'Log out'}).click();
  await page.getByRole('link',{name:'Forgot password?'}).click();await expect(page.getByRole('heading',{name:'Reset your password'})).toBeVisible();await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByRole('button',{name:'Request account email'}).click();await expect(page.getByRole('status')).toContainText('accepted by the transport');
  message=await request.post(`${API}/e2e/account-message`,{data:{ticket}});text=(await message.json()).text;
  await page.goto(text.match(/http[^\s]+/)![0]);
  const newPassword='Synthetic-onboarding-password-2';
  await page.getByLabel('Password',{exact:true}).fill(newPassword);await page.getByLabel('Confirm password').fill(newPassword);
  await page.getByRole('button',{name:'Change password'}).click();await expect(page.getByRole('status')).toContainText('Password changed');password=newPassword;
  await page.getByRole('link',{name:'Sign in',exact:true}).click();await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole('status')).toContainText('Upload and review a CV');
 }finally{const cleanup=await request.post(`${API}/e2e/cleanup`,{data:{email,password}});expect(cleanup.ok()).toBeTruthy();expect((await cleanup.json()).deleted).toBe(true)}
});
