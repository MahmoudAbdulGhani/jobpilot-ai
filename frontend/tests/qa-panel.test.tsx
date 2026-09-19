import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { QaPanel } from '../components/QaPanel';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

beforeEach(() => apiMock.mockReset());

test('ask searches one scope and cites sources without writing', async () => {
  apiMock.mockResolvedValue({
    entity: 'jobs', question: 'Python', source: 'structured', answer: 'Search results only.',
    citations: [], limit: 10, total: 1,
    matches: [{ entity: 'jobs', id: 'j1', field: 'description', excerpt: 'Build Python APIs', href: '/jobs/j1' }],
    provider: null, model: null, reason: null,
  });
  render(<QaPanel />);
  fireEvent.change(screen.getByPlaceholderText(/Python applications/), { target: { value: 'Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  const [path] = apiMock.mock.calls[0] as [string];
  expect(path.startsWith('/qa/answer?entity=jobs&q=Python')).toBe(true);
  expect(apiMock.mock.calls.every(([, init]) => init === undefined)).toBe(true);
  expect(await screen.findByText(/1 match in jobs/)).toBeTruthy();
  expect(screen.getByText(/Build Python APIs/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Open source' }).getAttribute('href')).toBe('/jobs/j1');
});

test('renders an AI answer with source, provider and model', async () => {
  apiMock.mockResolvedValue({
    entity: 'jobs', question: 'Python', source: 'ai', answer: 'Cedar Labs needs Python.',
    citations: [], limit: 10, total: 0, matches: [],
    provider: 'deterministic-test', model: 'synthetic-v1', reason: null,
  });
  render(<QaPanel />);
  fireEvent.change(screen.getByPlaceholderText(/Python applications/), { target: { value: 'Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  expect(await screen.findByText(/Cedar Labs needs Python/)).toBeTruthy();
  expect(screen.getByText(/AI answer · deterministic-test · synthetic-v1/)).toBeTruthy();
});

test('renders a structured fallback reason', async () => {
  apiMock.mockResolvedValue({
    entity: 'jobs', question: 'Python', source: 'structured',
    answer: 'Consent for AI answers is not granted.', citations: [], limit: 10, total: 0, matches: [],
    provider: null, model: null, reason: 'Consent for AI answers is not granted',
  });
  render(<QaPanel />);
  fireEvent.change(screen.getByPlaceholderText(/Python applications/), { target: { value: 'Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  expect(await screen.findByText(/Structured search · Consent for AI answers is not granted/)).toBeTruthy();
});