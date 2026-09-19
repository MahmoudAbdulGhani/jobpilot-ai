import { render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { InsightsView } from '../components/Insights';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));
vi.mock('../components/Shell', () => ({ Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('../lib/auth', () => ({ useAuth: () => ({ user: { email: 'a@b.c' }, loading: false, signOut: async () => {} }) }));
vi.mock('../lib/entitlements', () => ({ EntitlementsProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

const payload = {
  fit_gaps: [{ job_id: 'j1', job_title: 'Backend Engineer', assessment: 'not_evidenced', requirement: 'Kubernetes experience', link: { label: 'Open saved job', href: '/jobs/j1' } }],
  fit_counts: { not_evidenced: 1 },
  applications: [{ job_id: 'j1', job_title: 'Backend Engineer', status: 'Applied', origin: 'manual', link: { label: 'Open saved job', href: '/jobs/j1' } }],
  application_counts: { Applied: 1 },
  replies: [{ reply_id: 'r1', job_id: 'j1', sender_domain: '***@example.com', excerpt: 'Thanks for applying', link: { label: 'Open saved job', href: '/jobs/j1' } }],
  reply_counts: { reply_headers: 1 },
  reminders: [{ application_id: 'a1', job_id: 'j1', job_title: 'Backend Engineer', due_at: null, overdue: false, link: { label: 'Open reminders', href: '/reminders' } }],
  reminder_counts: { overdue: 0, upcoming: 0 },
  interviews: [],
  interview_counts: {},
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue(payload);
});

test('insights renders redacted sections with evidence links', async () => {
  render(<InsightsView />);
  expect(await screen.findByRole('heading', { name: 'Insights' })).toBeTruthy();
  expect(await screen.findByText(/Kubernetes experience/)).toBeTruthy();
  expect(screen.getByText('***@example.com')).toBeTruthy();
  expect(screen.getByText(/Manual record/)).toBeTruthy();
  const links = screen.getAllByRole('link', { name: 'Open saved job' });
  expect(links.length).toBeGreaterThanOrEqual(3);
});
