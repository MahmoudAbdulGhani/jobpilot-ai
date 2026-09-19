import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { FollowupSuggestions } from '../components/FollowupSuggestions';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const suggestion = {
  id: '77777777-7777-7777-7777-777777777777', application_id: 'a1', job_id: 'j1',
  job_title: 'Backend Engineer', company: 'Cedar Labs', kind: 'reminder',
  suggested_due_at: '2026-09-21T12:00:00Z', draft_message: null,
  reason: 'Application is 10 days old.', state: 'suggested', decided_at: null,
  created_at: '', updated_at: '',
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});

test('generate then approve posts explicit confirmation', async () => {
  render(<FollowupSuggestions />);
  await screen.findByText(/No open suggestions\./);
  apiMock.mockResolvedValueOnce([suggestion]);
  apiMock.mockResolvedValueOnce({ items: [suggestion], total: 1, page: 1, page_size: 20 });
  fireEvent.click(screen.getByRole('button', { name: 'Suggest follow-ups' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/followup-suggestions/generate', expect.objectContaining({ method: 'POST' })));
  expect(await screen.findByText(/Application is 10 days old\./)).toBeTruthy();
  apiMock.mockResolvedValueOnce({ ...suggestion, state: 'approved' });
  apiMock.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
  fireEvent.click(screen.getByRole('button', { name: 'Approve and create reminder' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
    `/followup-suggestions/${suggestion.id}/approve`, expect.objectContaining({ method: 'POST' })));
  const [, init] = apiMock.mock.calls.find(([path]) => String(path).endsWith('/approve')) as [string, RequestInit];
  expect(JSON.parse(String(init.body))).toEqual({ confirm: true });
  expect(await screen.findByText(/No open suggestions\./)).toBeTruthy();
});
