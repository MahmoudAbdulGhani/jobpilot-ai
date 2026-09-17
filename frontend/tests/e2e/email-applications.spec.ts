import {expect,test} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {API,accessToken,bootstrapUser,cleanupUser,createdUsers,login} from './helpers';

function pdf() {
  const stream='BT /F1 12 Tf 72 720 Td (Synthetic candidate builds Python APIs.) Tj ET';
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let result='%PDF-1.4\n';const offsets:number[]=[];
  objects.forEach((object,index)=>{offsets.push(Buffer.byteLength(result));result+=`${index+1} 0 obj\n${object}\nendobj\n`;});
  const xref=Buffer.byteLength(result);
  result+=`xref\n0 6\n0000000000 65535 f \n${offsets.map(n=>`${String(n).padStart(10,'0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(result);
}

test.afterEach(async({request})=>{for(const email of createdUsers)await cleanupUser(request,email);createdUsers.length=0;});

test('approved pack to exact email review and guarded synthetic send',async({page,request})=>{
  const user=await bootstrapUser(request,'email-application');
  const headers={Authorization:`Bearer ${await accessToken(request,user)}`};
  expect((await request.patch(`${API}/profile`,{headers,data:{headline:'Backend engineer',skills:['Python']}})).ok()).toBeTruthy();
  const jobResponse=await request.post(`${API}/jobs`,{headers,data:{title:'Backend engineer',company:'Example Systems',description:'Build Python APIs.'}});
  expect(jobResponse.ok()).toBeTruthy();const job=await jobResponse.json();
  const upload=await request.post(`${API}/resumes`,{headers,multipart:{file:{name:'synthetic.pdf',mimeType:'application/pdf',buffer:pdf()}}});
  expect(upload.ok()).toBeTruthy();const resume=await upload.json();
  expect((await request.post(`${API}/resumes/${resume.id}/extract`,{headers})).ok()).toBeTruthy();
  expect((await request.post(`${API}/resumes/${resume.id}/extraction/confirm`,{headers})).ok()).toBeTruthy();
  const generated=await request.post(`${API}/jobs/${job.id}/application-packs`,{headers,data:{resume_id:resume.id,idempotency_key:crypto.randomUUID()}});
  expect(generated.ok()).toBeTruthy();const pack=await generated.json();
  expect(pack.provider).toBe('deterministic-test');
  const approved=await request.post(`${API}/jobs/${job.id}/application-packs/${pack.id}/approve`,{headers,data:{expected_version:pack.current_version,idempotency_key:crypto.randomUUID()}});
  expect(approved.ok()).toBeTruthy();
  await login(page,user);await page.goto('/settings');
  await page.getByLabel('Allow sending applications').check();
  await page.getByRole('button',{name:'Connect Gmail',exact:true}).click();
  await expect(page.getByText('Enabled capabilities: Sending applications')).toBeVisible();
  await page.goto(`/jobs/${job.id}`);
  const panel=page.locator('section.email-application');
  await expect(panel.getByRole('heading',{name:'Apply by email',exact:true})).toBeVisible();
  await panel.getByRole('combobox',{name:'Approved pack version',exact:true}).selectOption(`${pack.id}:${pack.current_version}`);
  const boxes=await (await request.get(`${API}/mailboxes`,{headers})).json();
  await panel.getByRole('combobox',{name:'Sending mailbox',exact:true}).selectOption(boxes.items[0].id);
  await panel.getByLabel('Recruitment email',{exact:true}).fill('recruiter@example.com');
  await panel.getByLabel('Confirm recruitment email',{exact:true}).fill('recruiter@example.com');
  await panel.getByLabel('Where did you find this address?').fill('Synthetic job posting https://example.com/job');
  await panel.getByLabel('Email body',{exact:true}).fill('Please review my CV and cover letter for the advertised role.');
  await panel.getByRole('button',{name:'Prepare email review'}).click();
  await expect(panel.getByText('Email status: review')).toBeVisible();
  const send=panel.getByRole('button',{name:'Confirm and send application'});
  await expect(send).toBeDisabled();
  const attempts=await (await request.get(`${API}/jobs/${job.id}/email-applications`,{headers})).json();
  const attempt=attempts.items[0];expect(attempt.approved_at).toBeNull();
  for(const attachment of attempt.attachments){
    const downloaded=page.waitForEvent('download');
    await panel.getByRole('button',{name:attachment.name,exact:true}).click();
    const file=await downloaded;const bytes=readFileSync((await file.path())!);
    expect(bytes.subarray(0,5).toString()).toBe('%PDF-');
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(attachment.sha256);
  }
  await panel.getByRole('checkbox').check();await send.click();
  await expect(panel.getByText('Email status: simulated')).toBeVisible();
  await expect(panel.getByText(/No email was sent and no application was marked submitted/)).toBeVisible();
  await expect(send).toHaveCount(0);
  const repeated=await request.post(`${API}/jobs/${job.id}/email-applications/${attempt.id}/send`,{headers,data:{confirm:true,snapshot_hash:attempt.snapshot_hash}});
  expect((await repeated.json()).status).toBe('simulated');
  const applications=await (await request.get(`${API}/jobs/${job.id}/applications`,{headers})).json();
  expect(applications.total).toBe(0);
  await page.reload();await expect(panel.getByText('Email status: simulated')).toBeVisible();
});
