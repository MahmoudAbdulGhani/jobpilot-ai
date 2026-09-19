import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { Applications } from '../components/Applications';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const app = {
  id: '11111111-1111-1111-1111-111111111111', owner_id: '22222222-2222-2222-2222-222222222222',
  job_id: '33333333-3333-3333-3333-333333333333', submission_date: '2026-09-14T12:00:00Z',
  method: 'email', notes: null, status: 'Interview', origin: 'manual' as const,
  follow_up_date: null, reminder_status: null, reminder_timezone: null,
  pack_id: null, pack_version: null, cv_snapshot: null, cover_letter_snapshot: null,
  created_at: '2026-09-14T12:00:00Z', updated_at: '2026-09-14T12:00:00Z',
};

const timeline = {
  application_id: app.id, job_id: app.job_id,
  narrative: 'Interview application via email; 2 recorded events for Backend Engineer.',
  total: 2,
  entries: [
    { at: '2026-09-14T12:00:00Z', kind: 'submitted', title: 'Application recorded via email', detail: 'Initial status: Applied.', evidence: ['Origin: manual', 'Method: email'] },
    { at: '2026-09-16T10:00:00Z', kind: 'reply', title: 'Reply received: Interview invitation', detail: 'Let\u0027s schedule a call', evidence: ['From: recruiter@example.com'] },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path: string) => {
    if (path.startsWith('/applications?')) {
      return Promise.resolve({ items: [app], total: 1, page: 1, page_size: 50 });
    }
    if (String(path).endsWith(`/applications/${app.id}/timeline`)) {
      return Promise.resolve(timeline);
    }
    return Promise.reject(new Error(`unexpected ${path}`));
  });
});

test('expands a read-only timeline for an application', async () => {
  render(<Applications />);
  await screen.findByText('Interview');
  fireEvent.click(screen.getByRole('button', { name: 'Show timeline' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
    `/jobs/${app.job_id}/applications/${app.id}/timeline`));
  expect(await screen.findByText(/Interview application via email/)).toBeTruthy();
  expect(screen.getByText('Application recorded via email')).toBeTruthy();
  expect(screen.getByText('Reply received: Interview invitation')).toBeTruthy();
  expect(screen.getByText('From: recruiter@example.com')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Hide timeline' })).toBeTruthy();
});