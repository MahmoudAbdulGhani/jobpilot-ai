import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { QaPanel } from '../components/QaPanel';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

beforeEach(() => apiMock.mockReset());

test('ask searches one scope and cites sources without writing', async () => {
  apiMock.mockResolvedValue({
    entity: 'jobs', question: 'Python', limit: 10, total: 1,
    matches: [{ entity: 'jobs', id: 'j1', field: 'description', excerpt: 'Build Python APIs', href: '/jobs/j1' }],
  });
  render(<QaPanel />);
  fireEvent.change(screen.getByPlaceholderText(/Python applications/), { target: { value: 'Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  const [path] = apiMock.mock.calls[0] as [string];
  expect(path.startsWith('/qa/ask?entity=jobs&q=Python')).toBe(true);
  expect(apiMock.mock.calls.every(([, init]) => init === undefined)).toBe(true);
  expect(await screen.findByText(/1 match in jobs/)).toBeTruthy();
  expect(screen.getByText(/Build Python APIs/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Open source' }).getAttribute('href')).toBe('/jobs/j1');
});
