import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { Overview } from '../components/Overview';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));
vi.mock('../components/Shell', () => ({ Shell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

beforeEach(() => { apiMock.mockReset(); });
test('sections survive a ranking failure, retry independently, and never trigger generation', async () => {
  let rankingFailed = true;
  apiMock.mockImplementation((path: string) => {
    if (path.startsWith('/rankings')) return rankingFailed ? Promise.reject(new Error('Ranking unavailable')) : Promise.resolve({ items: [] });
    if (path.startsWith('/jobs')) return Promise.resolve({ items: [{ id: 'j1', title: 'Product engineer', company: 'Northstar', location: 'Remote' }], total: 1 });
    if (path.startsWith('/reminders')) return Promise.resolve({ items: [{ application_id: 'a1', job_id: 'j2', title: 'Follow up with Acme', company: 'Acme', due_at: null }] });
    return Promise.resolve({ application_counts: { Applied: 2 }, replies: [] });
  });
  render(<Overview />);
  expect(await screen.findByText('Product engineer')).toBeTruthy();
  expect(await screen.findByText('Follow up with Acme')).toBeTruthy();
  expect(await screen.findByText('Ranking unavailable')).toBeTruthy();
  const section = screen.getByRole('region', { name: 'Opportunities to consider' });
  rankingFailed = false;
  fireEvent.click(within(section).getByRole('button', { name: /try again/i }));
  await waitFor(() => expect(screen.queryByText('Ranking unavailable')).toBeNull());
  expect(await screen.findByText(/No comparison runs automatically/)).toBeTruthy();
  expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/jobs'))).toHaveLength(1);
  expect(apiMock.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
});
