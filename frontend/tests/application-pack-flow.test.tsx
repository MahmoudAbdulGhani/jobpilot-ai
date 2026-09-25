vi.mock('../components/MeteredButton', () => ({ MeteredButton: 'button' }));
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApplicationPacks } from '../components/ApplicationPacks';
import type { Job } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock, downloadResume: vi.fn() }));

const job = { id: 'job-1', title: 'Engineer', company: 'Demo', description: 'Python required', updated_at: '2026-09-25T00:00:00Z' } as Job;
const options = { provider: 'deterministic-test', model: 'synthetic-v1', available: true, reason: null,
  resumes: [{ id: 'resume-1', display_name: 'Confirmed CV', reviewed_at: '2026-09-25T00:00:00Z' }],
  has_profile: true, has_description: true };

beforeEach(() => { apiMock.mockReset(); });

it('requires current job fit before generating an AI pack', async () => {
  let currentFit: object | null = null;
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return currentFit ? Promise.resolve(currentFit) : Promise.reject(new Error('No fit'));
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  expect(await screen.findByText(/Analyze job fit before generating/)).not.toBeNull();
  expect(screen.getByRole('button', { name: /Generate application pack/ }).hasAttribute('disabled')).toBe(true);
  currentFit = { status: 'ready', is_outdated: false };
  fireEvent(window, new Event('jobpilot:job-fit-updated'));
  await waitFor(() => expect(screen.getByRole('button', { name: /Generate application pack/ }).hasAttribute('disabled')).toBe(false));
  currentFit = { status: 'ready', is_outdated: true };
  fireEvent(window, new Event('jobpilot:profile-updated'));
  await waitFor(() => expect(screen.getByRole('button', { name: /Generate application pack/ }).hasAttribute('disabled')).toBe(true));
});

it('shows generated documents for review without edit controls', async () => {
  const block = { id: 'one', kind: 'paragraph', text: 'Python', origin: 'ai', evidence: [{ fact_id: 'fact-1', cv_quote: null }] };
  const heading = { id: 'title', kind: 'heading', text: 'Curriculum vitae', origin: 'ai', evidence: [] };
  const pack = { id: 'pack-1', job_id: job.id, resume_id: 'resume-1', status: 'ready', current_version: 1,
    version: { id: 'version-1', number: 1, cv: { blocks: [heading, block] }, cover_letter: { blocks: [{ ...heading, text: 'Cover letter' }, block] }, approved_at: null, created_at: '2026-09-25T00:00:00Z' },
    review_notes: [], source_snapshot: { cv_text: 'Python', profile_facts: [{ id: 'fact-1', path: 'skills[0]', value: 'Python' }], job: { description: job.description } },
    is_outdated: false, provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: null, created_at: '2026-09-25T00:00:00Z' };
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return Promise.resolve({ status: 'ready', is_outdated: false });
    return Promise.resolve({ items: [pack], total: 1, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  expect(await screen.findByRole('button', { name: /Approve version 1/ })).not.toBeNull();
  expect(screen.getByRole('heading', { name: 'Curriculum vitae' }).classList.contains('pack-paper-title')).toBe(true);
  expect(screen.queryByRole('textbox', { name: /block 1 text/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /Save both drafts/ })).toBeNull();
});
