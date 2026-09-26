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
    review_notes: [], source_snapshot: { cv_text: 'Python', profile_facts: [{ id: 'fact-1', path: 'skills[0]', value: 'Python' }],
      application_skill_facts: [{ id: 'fact-2', path: 'application_skills[0]', value: 'Kubernetes' }],
      application_skills: [{ id: 'selected-1', analysis_id: 'analysis-1', skill: 'Kubernetes', importance: 'required', job_quote: 'Kubernetes required' }],
      job: { description: job.description } },
    is_outdated: false, provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: null, created_at: '2026-09-25T00:00:00Z' };
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return Promise.resolve({ status: 'ready', is_outdated: false });
    return Promise.resolve({ items: [pack], total: 1, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  expect(await screen.findByRole('button', { name: /Approve version 1/ })).not.toBeNull();
  expect(screen.getByRole('heading', { name: 'Curriculum vitae' }).classList.contains('pack-paper-title')).toBe(true);
  expect(screen.getByText('Confirmed for this application')).toBeTruthy();
  expect(screen.getAllByText('Kubernetes').length).toBeGreaterThan(0);
  expect(screen.queryByRole('textbox', { name: /block 1 text/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /Save both drafts/ })).toBeNull();
});

it('shows separate PDF downloads after approval and keeps DOCX secondary', async () => {
  const block = { id: 'one', kind: 'paragraph', text: 'Python', origin: 'ai', evidence: [] };
  const pack = { id: 'pack-2', job_id: job.id, resume_id: 'resume-1', status: 'ready', current_version: 1,
    version: { id: 'version-2', number: 1, cv: { blocks: [block] }, cover_letter: { blocks: [block] }, approved_at: '2026-09-25T01:00:00Z', created_at: '2026-09-25T00:00:00Z' },
    review_notes: [], source_snapshot: { cv_text: 'Python', profile_facts: [], application_skill_facts: [], application_skills: [], job: { description: job.description } },
    is_outdated: false, provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: null, created_at: '2026-09-25T00:00:00Z' };
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return Promise.resolve({ status: 'ready', is_outdated: false });
    return Promise.resolve({ items: [pack], total: 1, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  expect(await screen.findByRole('button', { name: 'CV PDF' })).not.toBeNull();
  expect(screen.getByRole('button', { name: 'Cover letter PDF' })).not.toBeNull();
  expect(screen.queryByRole('button', { name: 'Approve version 1' })).toBeNull();
  fireEvent.click(screen.getByText('Need editable files? Download DOCX'));
  expect(screen.getByRole('button', { name: 'CV DOCX' })).not.toBeNull();
  expect(screen.getByRole('button', { name: 'Cover letter DOCX' })).not.toBeNull();
});

it('explains that failed source details are inputs, not generated files', async () => {
  const pack = { id: 'pack-3', job_id: job.id, resume_id: 'resume-1', status: 'failed', current_version: 0,
    version: null, review_notes: [], source_snapshot: { cv_text: 'Python', profile_facts: [], application_skill_facts: [], application_skills: [], job: { description: job.description } },
    is_outdated: false, provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: 'Not enough supported CV content.', created_at: '2026-09-25T00:00:00Z' };
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return Promise.resolve({ status: 'ready', is_outdated: false });
    return Promise.resolve({ items: [pack], total: 1, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  expect(await screen.findByText(/No CV or cover letter draft was saved/)).not.toBeNull();
  expect(screen.queryByRole('button', { name: 'CV PDF' })).toBeNull();
  fireEvent.click(screen.getByText('Review private source details'));
  expect(screen.getByText(/input snapshots captured before generation/)).not.toBeNull();
});

it('shows the saved failure reason immediately after Generate', async () => {
  const failed = { id: 'pack-4', job_id: job.id, resume_id: 'resume-1', status: 'failed', current_version: 0,
    version: null, review_notes: [], source_snapshot: { cv_text: 'Python', profile_facts: [], application_skill_facts: [], application_skills: [], job: { description: job.description } },
    is_outdated: false, provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: 'The cover letter did not retain enough supported content.', created_at: '2026-09-25T00:00:00Z' };
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    if (path.endsWith('/options')) return Promise.resolve(options);
    if (path.includes('/fit-analyses/latest')) return Promise.resolve({ status: 'ready', is_outdated: false });
    if (init?.method === 'POST') return Promise.resolve(failed);
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 5 });
  });
  render(<ApplicationPacks job={job} />);
  const generate = await screen.findByRole('button', { name: 'Generate application pack' });
  await waitFor(() => expect(generate.hasAttribute('disabled')).toBe(false));
  fireEvent.click(generate);
  expect(await screen.findByText(/Generation failed: The cover letter did not retain enough supported content/)).not.toBeNull();
});
