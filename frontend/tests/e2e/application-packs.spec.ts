import { grantAiConsent } from './helpers';
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, login, logout } from './helpers';
const python = path.resolve(process.cwd(), '..', 'backend', '.venv', 'Scripts', 'python.exe');

function makePdfBuffer(text = 'Connected CV text for application-pack export verification') {
  const stream = `BT /F1 12 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let output = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(output));
    output += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(output);
  output += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  output += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  output += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(output);
}

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) {
    await cleanupUser(request, email);
  }
  createdUsers.length = 0;
});

for (const imported of [false, true]) {
test(`connected ${imported ? 'imported' : 'manual'} application-pack workflow verifies PDF and DOCX exports`, async ({ browser, request }) => {
  const user = await bootstrapUser(request, 'pack-flow');
  await grantAiConsent(request, user, ['ai_application_packs']);
  const token = await accessToken(request, user);
  const auth = { Authorization: `Bearer ${token}` };

  const profile = await request.patch(`${API}/profile`, {
    headers: auth,
    data: {
      headline: 'Backend engineer',
      target_roles: ['Backend Developer'],
      location: 'Beirut, Lebanon',
      remote_preference: 'remote',
      work_authorization: 'citizen',
      skills: ['Python', 'PostgreSQL', 'FastAPI'],
    },
  });
  expect(profile.ok()).toBeTruthy();

  const preview = imported ? await request.get(`${API}/discovery/synthetic-100/preview`, { headers: auth }) : null;
  const createdJob = imported ? await request.post(`${API}/discovery/import`, {
    headers: auth, data: { preview_token: (await preview!.json()).preview_token, confirm: true },
  }) : await request.post(`${API}/jobs`, {
    headers: auth,
    data: {
      title: 'Junior Backend Developer',
      company: 'Cedar Labs',
      location: 'Beirut, Lebanon',
      description: 'Help a small product team build dependable Python APIs.\n\nWhat you will work on\n• Build and maintain FastAPI endpoints\n• Design and query PostgreSQL databases\n\nWhat the team is looking for\n• Comfort with Python, SQL, and Git\n• Clear communication and a willingness to learn',
      source_url: 'https://example.com/jobs/backend',
      notes: 'Review the experience requirement. Prepare API testing examples.',
    },
  });
  expect(createdJob.ok()).toBeTruthy();
  const createdBody = await createdJob.json();
  const job = (imported ? createdBody.job : createdBody) as { id: string };

  const pdfBuffer = makePdfBuffer('Connected CV text for application-pack export verification');
  const resumeUpload = await request.post(`${API}/resumes`, {
    headers: auth,
    multipart: {
      file: {
        name: 'cv_2026_confirmed.pdf',
        mimeType: 'application/pdf',
        buffer: pdfBuffer,
      },
    },
  });
  expect(resumeUpload.ok()).toBeTruthy();
  const resume = await resumeUpload.json() as { id: string };

  const extraction = await request.post(`${API}/resumes/${resume.id}/extract`, {
    headers: auth,
  });
  expect(extraction.ok()).toBeTruthy();
  const extractionBody = await extraction.json() as { status?: string; draft_text?: string };
  expect(extractionBody.status).toBe('succeeded');
  expect(extractionBody.draft_text).toContain('Connected CV text for application-pack export verification');

  const confirm = await request.post(`${API}/resumes/${resume.id}/extraction/confirm`, {
    headers: auth,
  });
  expect(confirm.ok()).toBeTruthy();

  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await login(page, user);
  await page.goto(`/jobs/${job.id}`);
  await page.getByRole('tab', { name: 'Application pack', exact: true }).click();
  await expect(page.getByText('CV & cover letter packs')).toBeVisible();

  await expect(page.getByText('the deterministic test provider', { exact: false })).toBeVisible();
  await page.selectOption('#pack-resume', resume.id);
  await page.getByRole('button', { name: /Generate application pack/ }).click();
  await expect(page.getByText('Both drafts are ready for your review.')).toBeVisible({ timeout: 15000 });

  await expect(page.getByRole('button', { name: /CV PDF/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Cover letter DOCX/ })).toHaveCount(0);
  await page.getByLabel('Tailored CV block 1 text').fill('Connected CV text for application-pack export verification changed by review.');
  await page.getByRole('button', { name: /Save both drafts/ }).click();
  await expect(page.getByText('Both drafts saved. This version needs approval.')).toBeVisible();

  await page.reload();
  await expect(page.getByText(/Unapproved draft · version 2/)).toBeVisible();

  await page.getByRole('button', { name: /Approve version/ }).click();
  await page.getByLabel('I reviewed both documents and confirm their accuracy.').check();
  await page.getByRole('button', { name: 'Confirm approval' }).click();
  await expect(page.getByText(/Approved version/)).toBeVisible();

  const pdfDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /CV PDF/ }).click();
  const pdfDownload = await pdfDownloadPromise;
  expect(pdfDownload.suggestedFilename()).toBe('cv-v2.pdf');
  const pdfPath = await pdfDownload.path();
  expect(existsSync(pdfPath)).toBeTruthy();
  const pdfBytes = readFileSync(pdfPath);
  expect(pdfBytes.length).toBeGreaterThan(0);
  expect(pdfBytes.subarray(0, 5).toString('ascii')).toBe('%PDF-');

  const pdfVerify = execFileSync(python, [
    '-c',
    `from pypdf import PdfReader\nfrom pathlib import Path\nimport sys\npath = Path(sys.argv[1])\nreader = PdfReader(str(path))\ntext = '\\n'.join(page.extract_text() or '' for page in reader.pages)\nprint(text)`,
    pdfPath,
  ], { encoding: 'utf8' });
  expect(pdfVerify).toContain('Connected CV text for application-pack export verification');

  const docxDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Cover letter DOCX/ }).click();
  const docxDownload = await docxDownloadPromise;
  expect(docxDownload.suggestedFilename()).toBe('cover-letter-v2.docx');
  const docxPath = await docxDownload.path();
  expect(existsSync(docxPath)).toBeTruthy();
  const docxBytes = readFileSync(docxPath);
  expect(docxBytes.length).toBeGreaterThan(0);
  expect(docxBytes.subarray(0, 4)).toEqual(Buffer.from([0x50, 0x4b, 0x03, 0x04]));

  const docxVerify = execFileSync(python, [
    '-c',
    `from docx import Document\nfrom pathlib import Path\nimport sys\npath = Path(sys.argv[1])\ndoc = Document(str(path))\ntext = '\\n'.join(paragraph.text for paragraph in doc.paragraphs)\nprint(text)`,
    docxPath,
  ], { encoding: 'utf8' });
  expect(docxVerify).toContain('My background includes:');

  await logout(page);
  expect(pageErrors).toEqual([]);
  await context.close();
});
}
