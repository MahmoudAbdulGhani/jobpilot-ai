import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { JobRankings } from '../components/JobRankings';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const item = {
  job_id: '11111111-1111-1111-1111-111111111111', title: 'Backend Engineer', company: 'Cedar Labs', score: 82,
  reasons: [{ text: 'Profile covers 3 terms.', evidence: { job_quote: 'Must know Python.', profile_fact: 'Python' } }],
  missing_skills: ['kubernetes'], risks: ['Senior wording with few entries.'], recommended_action: 'Strong fit.',
};
const run = {
  id: '22222222-2222-2222-2222-222222222222', job_count: 1, top_score: 82, profile_hash: 'abc',
  engine_version: 'rank-v1', is_stale: false, items: [item], created_at: '', updated_at: '',
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 1 });
});

test('ranking runs on explicit action and shows evidence', async () => {
  apiMock.mockResolvedValueOnce(run);
  render(<JobRankings />);
  fireEvent.click(await screen.findByRole('button', { name: 'Rank saved jobs' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/rankings', expect.objectContaining({ method: 'POST' })));
  expect(await screen.findByText('Backend Engineer')).toBeTruthy();
  expect(screen.getByText(/Strong fit\./)).toBeTruthy();
  expect(screen.getByText(/Missing from profile:/)).toBeTruthy();
  expect(screen.getByText(/Senior wording/)).toBeTruthy();
  fireEvent.click(screen.getByText(/Why this score/));
  expect(screen.getByText(/Must know Python\./)).toBeTruthy();
});

test('stale runs show an outdated notice', async () => {
  apiMock.mockReset();
  apiMock.mockResolvedValueOnce({ items: [{ ...run, items: null }], total: 1, page: 1, page_size: 1 });
  apiMock.mockResolvedValueOnce({ ...run, is_stale: true });
  render(<JobRankings />);
  expect(await screen.findByText(/outdated/)).toBeTruthy();
});
