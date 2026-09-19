import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { DigestPanel } from '../components/DigestPanel';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const preview = {
  generated_at: '2026-09-18T12:00:00Z', cadence: 'daily',
  items: [{
    source: 'Jobicy', external_id: 'ext-1', title: 'Remote Engineer', company: 'Example Co',
    location: 'Remote', source_url: 'https://example.com/jobs/1', published_at: '2026-09-10T00:00:00Z',
    salary: null, workplace_model: null, applicant_region: 'Unknown eligibility',
    remote_arrangement: 'remote', test_data: true, refreshed_at: '2026-09-18T11:00:00Z',
  }],
  skipped_invalid: 1,
  delivery: { enabled: false, reason: 'No delivery provider is configured; previews are in-app only.' },
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ cadence: 'off' });
});

test('cadence saves explicitly and preview shows attribution with delivery disabled', async () => {
  render(<DigestPanel />);
  await screen.findByRole('heading', { name: 'Daily digest' });
  apiMock.mockResolvedValueOnce({ cadence: 'daily' });
  fireEvent.change(screen.getByLabelText('Cadence'), { target: { value: 'daily' } });
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/digest/preferences',
    expect.objectContaining({ method: 'PUT' })));
  const [, putInit] = apiMock.mock.calls.find(([path, callInit]) => String(path) === '/digest/preferences' && (callInit as RequestInit)?.method === 'PUT') as [string, RequestInit];
  expect(JSON.parse(String(putInit.body))).toEqual({ cadence: 'daily', confirm: true });

  apiMock.mockResolvedValueOnce(preview);
  fireEvent.click(screen.getByRole('button', { name: 'Preview digest' }));
  expect(await screen.findByText('Remote Engineer')).toBeTruthy();
  expect(screen.getByText(/Source: Jobicy/)).toBeTruthy();
  expect(screen.getByText(/1 invalid record skipped\./)).toBeTruthy();
  expect(screen.getByText(/Delivery disabled: No delivery provider is configured/)).toBeTruthy();
});
