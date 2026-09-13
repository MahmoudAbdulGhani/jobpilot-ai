import { expect, test } from '@playwright/test';
import { API, accessToken, bootstrapUser, cleanupUser, createdUsers, login, logout } from './helpers';

const pdfBuffer = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
%%EOF
`
);

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

  await page.reload();
  await expect(page.getByText('Lead Designer CV')).toBeVisible();
  await expect(page.locator('.resume-card', { hasText: 'Lead Designer CV' }).locator('.primary-badge')).toBeVisible();

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

  await page.screenshot({ path: '../evidence/resumes-desktop.png', fullPage: true });
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