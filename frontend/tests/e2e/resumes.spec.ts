import { grantAiConsent } from './helpers';
import { expect, test } from '@playwright/test';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, login, logout } from './helpers';

function textPdf(text: string): Buffer {
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

const pdfBuffer = textPdf('Connected resume text');

const docxBuffer = Buffer.from(
  'UEsDBBQAAAAAADxrLV0CxKfsSwEAAEsBAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbDw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz48VHlwZXMgeG1sbnM9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wYWNrYWdlLzIwMDYvY29udGVudC10eXBlcyI+PERlZmF1bHQgRXh0ZW5zaW9uPSJ4bWwiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi94bWwiLz48T3ZlcnJpZGUgUGFydE5hbWU9Ii93b3JkL2RvY3VtZW50LnhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC53b3JkcHJvY2Vzc2luZ21sLmRvY3VtZW50Lm1haW4reG1sIi8+PC9UeXBlcz5QSwMEFAAAAAAAPGstXe3wzaTSAAAA0gAAABEAAAB3b3JkL2RvY3VtZW50LnhtbDw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz48dzpkb2N1bWVudCB4bWxuczp3PSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvd29yZHByb2Nlc3NpbmdtbC8yMDA2L21haW4iPjx3OmJvZHk+PHc6cD48dzpyPjx3OnQ+UUEgcmVzdW1lPC93OnQ+PC93OnI+PC93OnA+PC93OmJvZHk+PC93OmRvY3VtZW50PlBLAQIUABQAAAAAADxrLV0CxKfsSwEAAEsBAAATAAAAAAAAAAAAAACAAQAAAABbQ29udGVudF9UeXBlc10ueG1sUEsBAhQAFAAAAAAAPGstXe3wzaTSAAAA0gAAABEAAAAAAAAAAAAAAIABfAEAAHdvcmQvZG9jdW1lbnQueG1sUEsFBgAAAAACAAIAgAAAAH0CAAAAAA==',
  'base64'
);

test.afterEach(async ({ request }) => {
  for (const email of createdUsers) {
    await cleanupUser(request, email);
  }
  createdUsers.length = 0;
});

test('connected resume library workflow', async ({ browser, request }) => {
  const user = await bootstrapUser(request, 'resume-main');
  await grantAiConsent(request, user, ['ai_profile_suggestions']);
  const context = await browser.newContext({ viewport: { width: 1488, height: 1058 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await login(page, user);
  await page.goto('/resumes');
  await expect(page.getByRole('heading', { name: 'Your resumes' })).toBeVisible();
  await expect(page.getByText('No resumes yet')).toBeVisible();

  await page.getByTestId('resume-file-input').setInputFiles({
    name: 'cv_2026_final.pdf', mimeType: 'application/pdf', buffer: pdfBuffer,
  });
  await expect(page.getByRole('status')).toContainText('Resume uploaded.');
  const pdfRow = page.locator('.resume-card', { hasText: 'cv_2026_final.pdf' });
  await expect(pdfRow).toBeVisible();

  await page.getByTestId('resume-file-input').setInputFiles({
    name: 'draft.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: docxBuffer,
  });
  await expect(page.getByRole('status')).toContainText('Resume uploaded.');
  const docxRow = page.locator('.resume-card', { hasText: 'draft.docx' });
  await expect(docxRow).toBeVisible();

  await docxRow.getByRole('button', { name: /Rename/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByLabel('Display name').fill('Lead Designer CV');
  await page.getByRole('button', { name: 'Save name' }).click();
  await expect(page.getByRole('status')).toContainText('Resume renamed.');
  await expect(page.getByText('Lead Designer CV')).toBeVisible();

  const docxNamedRow = page.locator('.resume-card', { hasText: 'Lead Designer CV' });
  await docxNamedRow.getByRole('button', { name: /Make primary/ }).click();
  await expect(page.getByRole('status')).toContainText('Primary resume updated.');
  await expect(docxNamedRow.locator('.primary-badge')).toBeVisible();
  await expect(pdfRow.locator('.primary-badge')).toBeHidden();

  await pdfRow.getByRole('button', { name: /Extract text/ }).click();
  await expect(page.getByLabel('Extracted resume text')).toHaveValue(/Connected resume text/);
  await page.getByLabel('Extracted resume text').fill('Connected resume text\nReviewed by the owner');
  await expect(page.getByText('Unsaved changes')).toBeVisible();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('Needs review')).toBeVisible();
  await page.getByRole('button', { name: 'Confirm text' }).click();
  await expect(page.locator('.status-badge', { hasText: 'Confirmed' })).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Suggest profile details with AI' }).click();
  await expect(page.getByLabel('Proposed headline')).toHaveValue('Connected resume text');
  await page.getByLabel('Proposed headline').fill('AI-reviewed connected profile');
  await page.getByRole('button', { name: 'Review profile changes' }).click();
  await expect(page.getByText(/A selected value is invalid or lacks source evidence\./)).toBeVisible();
  await page.getByLabel('Proposed headline').fill('Resume text');
  await page.getByRole('button', { name: 'Review profile changes' }).click();
  await page.getByRole('button', { name: 'Save profile changes' }).click();
  await expect(page.getByRole('link', { name: 'View your profile' })).toBeVisible();
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Resume text', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Resume text', exact: true })).toBeVisible();
  await page.goto('/resumes');

  await page.reload();
  await expect(page.getByText('Lead Designer CV')).toBeVisible();
  await expect(page.locator('.resume-card', { hasText: 'Lead Designer CV' }).locator('.primary-badge')).toBeVisible();
  await page.locator('.resume-card', { hasText: 'cv_2026_final.pdf' }).getByRole('button', { name: /Extract text/ }).click();
  await expect(page.getByLabel('Extracted resume text')).toHaveValue('Connected resume text\nReviewed by the owner');
  await expect(page.locator('.status-badge', { hasText: 'Confirmed' })).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();

  const downloadPromise = page.waitForEvent('download');
  await page.locator('.resume-card', { hasText: 'cv_2026_final.pdf' }).getByRole('button', { name: /Download/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('cv_2026_final.pdf');

  await page.locator('.resume-card', { hasText: 'cv_2026_final.pdf' }).getByRole('button', { name: /Delete/ }).click();
  await page.getByRole('button', { name: 'Delete resume' }).click();
  await expect(page.getByRole('status')).toContainText('Resume deleted.');
  await expect(page.locator('.resume-card', { hasText: 'cv_2026_final.pdf' })).toBeHidden();
  await expect(page.getByText('Lead Designer CV')).toBeVisible();

  await page.getByTestId('resume-file-input').setInputFiles({
    name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('plain text file'),
  });
  await expect(page.locator('.form-error.upload-error')).toContainText('Unsupported file type. Upload a PDF or DOCX resume.');

  await page.screenshot({ path: test.info().outputPath('resumes-desktop.png'), fullPage: true });
  await logout(page);
  expect(pageErrors).toEqual([]);
  await context.close();
});

test('resume ownership and isolation', async ({ request }) => {
  const owner = await bootstrapUser(request, 'resume-owner');
  const intruder = await bootstrapUser(request, 'resume-intruder');
  const ownerToken = await accessToken(request, owner);

  const uploadResponse = await request.post(`${API}/resumes`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    multipart: { file: { name: 'private.pdf', mimeType: 'application/pdf', buffer: pdfBuffer } },
  });
  expect(uploadResponse.ok()).toBeTruthy();
  const resumeId = ((await uploadResponse.json()) as { id: string }).id;

  const intruderToken = await accessToken(request, intruder);
  const deniedDownload = await request.get(`${API}/resumes/${resumeId}/download`, {
    headers: { Authorization: `Bearer ${intruderToken}` },
  });
  expect(deniedDownload.status()).toBe(404);
  const deniedPatch = await request.patch(`${API}/resumes/${resumeId}`, {
    headers: { Authorization: `Bearer ${intruderToken}` },
    data: { display_name: 'stolen' },
  });
  expect(deniedPatch.status()).toBe(404);
  const deniedExtraction = await request.post(`${API}/resumes/${resumeId}/extract`, {
    headers: { Authorization: `Bearer ${intruderToken}` },
  });
  expect(deniedExtraction.status()).toBe(404);
  const deniedDelete = await request.delete(`${API}/resumes/${resumeId}`, {
    headers: { Authorization: `Bearer ${intruderToken}` },
  });
  expect(deniedDelete.status()).toBe(404);

  const intruderList = await request.get(`${API}/resumes`, {
    headers: { Authorization: `Bearer ${intruderToken}` },
  });
  expect((await intruderList.json()) as { items: unknown[] }).toEqual({ items: [] });

  const ownerDelete = await request.delete(`${API}/resumes/${resumeId}`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  expect(ownerDelete.status()).toBe(204);
  const gone = await request.get(`${API}/resumes/${resumeId}/download`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  expect(gone.status()).toBe(404);
});
