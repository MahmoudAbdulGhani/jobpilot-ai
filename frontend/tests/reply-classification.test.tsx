import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { ReplyClassificationPanel } from '../components/ReplyClassification';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const result = {
  id: '66666666-6666-6666-6666-666666666666', reply_id: 'r1', category: 'interview',
  confidence: 76, evidence_excerpt: 'invite you to an interview', uncertainty: 'Confirm yourself.',
  suggested_status: 'Interview', status_applied: false, applied_status: null,
  created_at: '', updated_at: '',
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue(null);
});

test('classify shows advisory result without changing status', async () => {
  render(<ReplyClassificationPanel replyId="r1" jobId="j1" />);
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/replies/r1/classification'));
  apiMock.mockResolvedValueOnce(result);
  fireEvent.click(screen.getByRole('button', { name: 'Classify reply' }));
  expect(await screen.findByText(/Classification:/)).toBeTruthy();
  expect(screen.getByText(/Nothing changed yet\./)).toBeTruthy();
  expect(screen.queryByText(/Status change applied/)).toBeNull();
});

test('confirm posts explicit confirmation with chosen status', async () => {
  apiMock.mockResolvedValueOnce(null);
  apiMock.mockResolvedValueOnce(result);
  render(<ReplyClassificationPanel replyId="r1" jobId="j1" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Classify reply' }));
  await screen.findByText(/Nothing changed yet\./);
  apiMock.mockResolvedValueOnce({ ...result, status_applied: true, applied_status: 'Offer' });
  fireEvent.change(screen.getByLabelText(/Apply status/), { target: { value: 'Offer' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm status change' }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/replies/r1/classification/confirm',
    expect.objectContaining({ method: 'POST' })));
  const [, init] = apiMock.mock.calls.find(([path]) => String(path).endsWith('/confirm')) as [string, RequestInit];
  expect(JSON.parse(String(init.body))).toEqual({ confirm: true, status: 'Offer' });
  expect(await screen.findByText(/Status change applied: Offer\./)).toBeTruthy();
});

test('no linked job explains confirmation is unavailable', async () => {
  apiMock.mockResolvedValueOnce(result);
  render(<ReplyClassificationPanel replyId="r1" jobId={null} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Classify reply' }));
  expect(await screen.findByText(/Associate the reply with a saved job/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Confirm status change' })).toBeNull();
});
