import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { AtsReport } from '../components/AtsReport';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const job = { id: '33333333-3333-3333-3333-333333333333' };
const report = {
  id: '44444444-4444-4444-4444-444444444444', job_id: job.id,
  pack_id: '55555555-5555-5555-5555-555555555555', pack_version: 1,
  checks: [{ id: 'contact_fields', label: 'Contact fields', status: 'pass', detail: 'Email present; phone present.', evidence: ['email:found'] }],
  readiness_score: 92, report_version: 'ats-v1', created_at: '', updated_at: '',
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/application-packs?page=1&page_size=20')) {
      return Promise.resolve({ items: [{ id: report.pack_id, current_version: 1, status: 'ready' }] });
    }
    if (path.includes('/versions?')) {
      return Promise.resolve({ items: [{ number: 1, approved_at: '2026-09-14T12:00:00Z' }] });
    }
    if (path.endsWith('/ats-reports/latest')) {
      return Promise.resolve(null);
    }
    return Promise.reject(new Error(`unexpected ${path}`));
  });
});

test('readiness check posts the approved version and shows checks', async () => {
  apiMock.mockImplementationOnce(() => Promise.resolve({ items: [{ id: report.pack_id, current_version: 1, status: 'ready' }] }));
  render(<AtsReport job={job} />);
  await screen.findByRole('option', { name: 'Version 1' });
  const button = await screen.findByRole('button', { name: 'Check readiness' });
  apiMock.mockResolvedValueOnce(report);
  fireEvent.click(button);
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
    `/jobs/${job.id}/packs/${report.pack_id}/ats-reports`,
    expect.objectContaining({ method: 'POST' })));
  expect(await screen.findByText(/Readiness 92 \/ 100/)).toBeTruthy();
  expect(screen.getByText('Contact fields')).toBeTruthy();
});

test('improve posts the report and shows the new draft preview', async () => {
  apiMock.mockResolvedValueOnce({ items: [{ id: report.pack_id, current_version: 1, status: 'ready' }] });
  apiMock.mockResolvedValueOnce({ items: [{ number: 1, approved_at: '2026-09-14T12:00:00Z' }] });
  apiMock.mockResolvedValueOnce(report);
  render(<AtsReport job={job} />);
  const button = await screen.findByRole('button', { name: 'Improve from this report' });
  apiMock.mockImplementation((path: string) => {
    if (String(path).includes('/improve')) {
      return Promise.resolve({
        report_id: report.id, job_id: job.id, pack_id: report.pack_id,
        approved_version: 1, version_number: 2,
        review_notes: ['Human review is required.'],
        preview_checks: [{ id: 'contact_fields', label: 'Contact fields', status: 'pass', detail: 'Email present; phone present.', evidence: ['email:found'] }],
        preview_readiness: 92,
      });
    }
    if (String(path).includes('/versions?')) {
      return Promise.resolve({ items: [{ number: 1, approved_at: '2026-09-14T12:00:00Z' }, { number: 2, approved_at: null }] });
    }
    return Promise.reject(new Error(`unexpected ${path}`));
  });
  fireEvent.click(button);
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
    `/jobs/${job.id}/packs/${report.pack_id}/ats-reports/${report.id}/improve`,
    expect.objectContaining({ method: 'POST' })));
  expect(await screen.findByText(/Improved draft version 2 created from approved version 1/)).toBeTruthy();
  expect(screen.getByText('Draft preview (not persisted)')).toBeTruthy();
  expect(screen.getByText('Human review is required.')).toBeTruthy();
});
