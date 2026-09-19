import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { PrivacyMatrix } from '../components/PrivacyMatrix';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const rows = [
  { domain: 'profile', fields_used: ['headline'], used_for: ['local ranking'], provider: 'local-only', retention: 'until account deletion', consent_key: null, required: true, allowed: true, managed_by: 'always' },
  { domain: 'selected job', fields_used: ['description'], used_for: ['fit analysis (only with consent)'], provider: 'disabled (AI off)', retention: 'until deletion', consent_key: 'ai_job_fit', required: false, allowed: false, managed_by: 'toggle' },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ rows });
});

test('matrix shows least-privilege defaults and toggles consent explicitly', async () => {
  render(<PrivacyMatrix />);
  expect(await screen.findByText(/How your data is used/)).toBeTruthy();
  expect(screen.getByText(/\(optional, denied\)/)).toBeTruthy();
  apiMock.mockResolvedValueOnce({});
  apiMock.mockResolvedValueOnce({ rows: [{ ...rows[1], allowed: true }] });
  fireEvent.click(screen.getByRole('button', { name: 'Allow selected job AI use' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/privacy/consents', expect.objectContaining({ method: 'PATCH' })));
  const [, init] = apiMock.mock.calls.find(([path]) => String(path) === '/privacy/consents') as [string, RequestInit];
  expect(JSON.parse(String(init.body))).toEqual({ key: 'ai_job_fit', allowed: true, confirm: true });
  expect(await screen.findByText(/\(optional, allowed\)/)).toBeTruthy();
});
