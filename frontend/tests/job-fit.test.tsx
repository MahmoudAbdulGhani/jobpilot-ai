vi.mock('../components/MeteredButton', () => ({ MeteredButton: 'button' }));
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobFitAnalysis } from '../components/JobFitAnalysis';
import type { Job, JobFitAnalysis as Analysis } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const job = { id: 'job-1', owner_id: 'user-1', title: 'Engineer', company: 'Acme', description: 'Python required. Kubernetes required.',
  location: null, source_url: null, notes: null, is_archived: false, created_at: '2026-09-14T10:00:00Z', updated_at: '2026-09-14T10:00:00Z' } as Job;
const gap = { skill: 'Kubernetes', requirement_id: 'req-2', job_quote: 'Kubernetes required.', importance: 'required' };
const analysis = { id: 'analysis-1', job_id: job.id, status: 'ready', job_snapshot: { description: job.description }, profile_facts: [],
  result: { requirements: [], missing_skills: [gap, { ...gap, requirement_id: 'req-3', importance: 'preferred' }],
    summary: 'Do not display this summary', strengths: ['Do not display this strength'], gaps: [], actions: [] },
  counts: { supported: 1, total: 2 }, provider: 'deterministic-test', model: 'synthetic-v1', prompt_version: 'job-fit-v1',
  outcome_message: null, is_outdated: false, created_at: '2026-09-14T10:00:00Z', updated_at: '2026-09-14T10:00:00Z' } as Analysis;

function mockLoad(selected: object[] = []) {
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    if (typeof path !== 'string') return Promise.resolve({ items: [] });
    if (init?.method === 'POST') return Promise.resolve({ id: 'selected-1', analysis_id: analysis.id, ...gap });
    if (init?.method === 'DELETE') return Promise.resolve(undefined);
    if (path.endsWith('/fit-analyses/latest')) return Promise.resolve(analysis);
    if (path.includes('/application-skills')) return Promise.resolve({ items: selected });
    return Promise.resolve({ items: [analysis], total: 1, page: 1, page_size: 10 });
  });
}

describe('JobFitAnalysis', () => {
  beforeEach(() => apiMock.mockReset());

  it('shows grouped missing skills only, with exact job evidence', async () => {
    mockLoad(); render(<JobFitAnalysis job={job} />);
    expect(await screen.findByRole('heading', { name: 'Kubernetes' })).toBeTruthy();
    expect(screen.getAllByText('“Kubernetes required.”')).toHaveLength(1);
    expect(screen.getByText('Required')).toBeTruthy();
    expect(screen.queryByText('Do not display this summary')).toBeNull();
    expect(screen.queryByText('Do not display this strength')).toBeNull();
  });

  it('confirms a job-only skill without changing the profile', async () => {
    mockLoad(); render(<JobFitAnalysis job={job} />);
    fireEvent.click(await screen.findByRole('button', { name: 'I have this skill' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Confirm Kubernetes' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(`/jobs/${job.id}/application-skills`, expect.objectContaining({
      method: 'POST', body: JSON.stringify({ analysis_id: analysis.id, requirement_id: 'req-2', confirmed: true }),
    })));
    expect(apiMock.mock.calls.some(([path]) => path === '/profile')).toBe(false);
  });

  it('hides stale skills until reanalysis', async () => {
    apiMock.mockImplementation((path: string) => Promise.resolve(typeof path === 'string' && path.endsWith('/latest') ? { ...analysis, is_outdated: true } : { items: [] }));
    render(<JobFitAnalysis job={job} />);
    expect(await screen.findByText(/Reanalyze before confirming skills/)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Kubernetes' })).toBeNull();
  });

  it('shows a careful empty state', async () => {
    apiMock.mockImplementation((path: string) => Promise.resolve(typeof path === 'string' && path.endsWith('/latest') ? { ...analysis, result: { ...analysis.result, missing_skills: [] } } : { items: [] }));
    render(<JobFitAnalysis job={job} />);
    expect(await screen.findByText(/No skills need confirmation/)).toBeTruthy();
    expect(screen.getByText(/does not assess every qualification/)).toBeTruthy();
  });
});
