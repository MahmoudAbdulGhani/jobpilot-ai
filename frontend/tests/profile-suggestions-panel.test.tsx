/* eslint-disable @typescript-eslint/no-explicit-any */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfileSuggestionsPanel } from '../components/ProfileSuggestionsPanel';
import type { CandidateProfile, ProfileChanges, ProfileSuggestionSet, Resume } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));
const resume = { id: 'resume-1', display_name: 'Test CV' } as Resume;
const empty = { id: 'profile-1', owner_id: 'owner', headline: null, location: null, target_roles: null, skills: null, experience: null, education: null, languages: null, remote_preference: null, work_authorization: null, salary_preference: null, created_at: '2026-09-24T10:00:00Z', updated_at: '2026-09-24T10:00:00Z' } as CandidateProfile;
const values: Record<string, any> = { headline: 'Engineer', location: 'Tripoli', target_roles: 'Developer', skills: ['Python', 'SQL'], experience: { title: 'Engineer', organization: 'Cedar', period: '2020', notes: 'APIs' }, education: { school: 'University', degree: 'BSc', field: 'CS', period: '2024' }, languages: { name: 'Arabic', proficiency: 'native' }, remote_preference: 'remote', work_authorization: 'other', salary_preference: { currency: 'USD', min: 50000, max: 70000 } };
let record: ProfileSuggestionSet;
let saved: CandidateProfile;
let reviewMock: ReturnType<typeof vi.fn>;
let applyMock: ReturnType<typeof vi.fn>;
let generationMock: ReturnType<typeof vi.fn>;

function view() { return render(<ProfileSuggestionsPanel resume={resume} enabled />); }
async function ready() { await screen.findByLabelText('Proposed headline'); await waitFor(() => expect(screen.getByRole('button', { name: 'Review profile changes' }).hasAttribute('disabled')).toBe(false)); }
function input(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
function calls(path: string) { return apiMock.mock.calls.filter(([url]) => url.endsWith(path)); }

describe('combined profile review and save', () => {
  beforeEach(() => {
    saved = structuredClone(empty);
    record = { id: 'set-1', resume_id: resume.id, status: 'ready', provider: 'test', model: 'test', outcome_message: null, failure_field: null, applied_at: null, suggestions: Object.entries(values).map(([field, value], index) => ({ id: `s-${index}`, field: field as any, value: structuredClone(value), evidence: [{ quote: field === 'languages' ? '• Arabic: Native' : field }] })) };
    reviewMock = vi.fn(async (changes: ProfileChanges) => {
      const proposed: any = structuredClone(saved);
      for (const item of changes.selections) proposed[item.field] = ['target_roles', 'experience', 'education', 'languages'].includes(item.field) ? [item.value] : item.value;
      if (changes.manual_experience_entries?.length) proposed.experience = [...(proposed.experience || []), ...changes.manual_experience_entries];
      Object.assign(proposed, changes.manual_fields);
      return { current_profile: saved, proposed_profile: proposed, reviewed_profile_revision: 'revision-2', changed_fields: [...new Set([...changes.selections.map(item => item.field), ...Object.keys(changes.manual_fields || {}), ...(changes.manual_experience_entries?.length ? ['experience'] : [])])] };
    });
    applyMock = vi.fn(async (changes: ProfileChanges) => ({ ...record, status: 'applied', apply_result: { applied: changes.selections, profile_id: saved.id, manual_fields: changes.manual_fields }, profile: { ...saved, ...(await reviewMock(changes)).proposed_profile } }));
    generationMock = vi.fn(async () => record);
    apiMock.mockReset().mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === '/profile') return saved;
      if (path.endsWith('/latest')) return record;
      if (path.endsWith('/review')) return reviewMock(JSON.parse(String(init?.body)));
      if (path.endsWith('/apply')) return applyMock(JSON.parse(String(init?.body)));
      return generationMock();
    });
  });

  it('reviews edited values for all ten fields before any save and restores accepted values on reopening', async () => {
    record.suggestions!.push({ id: 'english', field: 'languages', value: { name: 'English', proficiency: 'professional' }, evidence: [{ quote: 'English professional' }] });
    const rendered = view(); await ready();
    const changes = { ...structuredClone(values), headline: 'Senior Engineer', location: 'Beirut', target_roles: 'Full-Stack Developer', skills: ['TypeScript', 'SQL'], experience: { ...values.experience, notes: 'Built APIs' }, education: { ...values.education, degree: 'MSc' }, languages: { name: 'Arabic', proficiency: 'native' }, remote_preference: 'hybrid', work_authorization: 'citizen', salary_preference: { currency: 'EUR', min: 60000, max: 80000 } };
    for (const field of ['headline', 'location', 'target_roles', 'remote_preference', 'work_authorization']) input(`Proposed ${field}`, changes[field as keyof typeof changes] as string);
    input('Proposed skill 1', 'TypeScript'); input('Proposed experience notes', 'Built APIs'); input('Proposed education degree', 'MSc');
    input('Proposed salary_preference currency', 'EUR'); input('Proposed salary_preference min', '60000'); input('Proposed salary_preference max', '80000');
    const englishCard = screen.getByText('“English professional”').closest('article')!;
    fireEvent.click(within(englishCard).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('region', { name: 'Profile change comparison' });
    expect(calls('/apply')).toHaveLength(0); expect(generationMock).not.toHaveBeenCalled();
    const payload = reviewMock.mock.calls[0][0];
    expect(Object.fromEntries(payload.selections.map((item: any) => [item.field, item.value]))).toEqual(Object.fromEntries(Object.entries(changes).filter(([field]) => field !== 'experience')));
    expect(payload.manual_experience_entries).toEqual([changes.experience]);
    expect(payload.manual_fields).toEqual({});
    expect(screen.getAllByText('Currently saved')).toHaveLength(10);
    fireEvent.click(screen.getByRole('button', { name: 'Save profile changes' }));
    await screen.findByRole('link', { name: 'View your profile' });
    expect(applyMock.mock.calls[0][0].reviewed_profile_revision).toBe('revision-2');
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Senior Engineer');
    record = await applyMock.mock.results[0].value; saved = record.profile!;
    rendered.unmount(); view();
    await screen.findByRole('link', { name: 'View your profile' });
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Senior Engineer');
    expect((screen.getByText('“English professional”').closest('article')!.querySelector('input[type=checkbox]') as HTMLInputElement).checked).toBe(false);
  });

  it('shows all missing categories, hydrates manual values, and submits only edited manual fields together', async () => {
    record.suggestions = record.suggestions!.filter(item => ['location', 'skills', 'education', 'languages'].includes(item.field));
    saved = { ...saved, target_roles: ['Existing role'], remote_preference: 'remote', work_authorization: 'other' };
    view(); await screen.findByLabelText('Manual headline');
    expect((screen.getByLabelText('Manual target role 1') as HTMLInputElement).value).toBe('Existing role');
    expect((screen.getByLabelText('Manual remote_preference') as HTMLSelectElement).value).toBe('remote');
    expect(screen.getByRole('button', { name: 'Add Experience' })).toBeTruthy();
    input('Manual headline', 'My headline'); input('Manual target role 1', 'New role');
    input('Manual salary_preference currency', 'USD'); input('Manual salary_preference min', '1000');
    fireEvent.click(screen.getByRole('button', { name: 'Add Experience' }));
    input('Manual 1 experience title', 'Developer'); input('Manual 1 experience organization', 'Cedar');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    expect(reviewMock.mock.calls[0][0].manual_fields).toEqual({ headline: 'My headline', target_roles: ['New role'], salary_preference: { currency: 'USD', min: 1000 }, experience: [{ title: 'Developer', organization: 'Cedar' }] });
    expect(calls('/profile').every(([, init]) => !init)).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Save profile changes' }));
    await screen.findByRole('link', { name: 'View your profile' });
    expect((screen.getByLabelText('Manual headline') as HTMLTextAreaElement).value).toBe('My headline');
  });

  it('keeps a CV role and a user-added role distinct through review', async () => {
    view(); await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Add Experience' }));
    input('Added 1 experience title', 'Mentor');
    input('Added 1 experience organization', 'Community Lab');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    const region = await screen.findByRole('region', { name: 'Profile change comparison' });
    const payload = reviewMock.mock.calls[0][0];
    expect(payload.selections.some((item: any) => item.field === 'experience' && item.value.organization === 'Cedar')).toBe(true);
    expect(payload.manual_experience_entries).toEqual([{ title: 'Mentor', organization: 'Community Lab' }]);
    expect(within(region).getByText('Engineer · Cedar')).toBeTruthy();
    expect(within(region).getByText('Mentor · Community Lab')).toBeTruthy();
  });

  it('refreshes an applied set on click and chooses manual entry for a suggested field', async () => {
    record.status = 'applied';
    record.apply_result = { applied: [], profile_id: saved.id, manual_fields: {} };
    const refreshed = { ...record, id: 'fresh-set', status: 'ready' as const, apply_result: null };
    generationMock.mockResolvedValueOnce(refreshed);
    view();
    const refresh = await screen.findByRole('button', { name: 'Refresh AI suggestions from this saved CV' });
    expect(generationMock).not.toHaveBeenCalled();
    fireEvent.click(refresh);
    await screen.findByRole('button', { name: 'Regenerate suggestions' });
    expect(generationMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Enter Location manually' }));
    input('Manual location', 'Beirut');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    const payload = reviewMock.mock.calls[0][0];
    expect(payload.manual_fields.location).toBe('Beirut');
    expect(payload.selections.some((item: any) => item.field === 'location')).toBe(false);
  });

  it('supports a manual-only save and explicit clearing without resubmitting untouched values', async () => {
    record.suggestions = [];
    saved = { ...saved, headline: 'Clear', location: 'Keep', salary_preference: { currency: 'USD', min: 1, max: 2 } };
    view(); await screen.findByLabelText('Manual headline');
    input('Manual headline', '');
    fireEvent.click(screen.getByRole('button', { name: 'Clear salary preference' }));
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    expect(reviewMock.mock.calls[0][0]).toEqual({ selections: [], manual_fields: { headline: null, salary_preference: null }, manual_experience_entries: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile changes' }));
    await screen.findByRole('link', { name: 'View your profile' });
    expect((screen.getByLabelText('Manual location') as HTMLTextAreaElement).value).toBe('Keep');
  });

  it('re-reviews after a save conflict without regeneration or losing edits', async () => {
    applyMock.mockRejectedValueOnce(Object.assign(new Error('The profile changed. Review again.'), { status: 409 }));
    view(); await ready(); input('Proposed headline', 'Retained');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save profile changes' }));
    await screen.findByText('The profile changed. Review again.');
    expect(screen.queryByRole('button', { name: 'Save profile changes' })).toBeNull();
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Retained');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save profile changes' }));
    await screen.findByRole('link', { name: 'View your profile' });
    expect(generationMock).not.toHaveBeenCalled();
  });

  it('invalidates the preview after local edits or an external profile save', async () => {
    view(); await ready(); fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    input('Proposed headline', 'Updated');
    expect(screen.queryByRole('button', { name: 'Save profile changes' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    act(() => window.dispatchEvent(new CustomEvent('jobpilot:profile-updated', { detail: saved })));
    expect(screen.queryByRole('button', { name: 'Save profile changes' })).toBeNull();
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Updated');
  });

  it.each([422, 503])('preserves the form and makes no save when review fails with %i', async code => {
    reviewMock.mockRejectedValueOnce(Object.assign(new Error('skills: Cannot review these values.'), { status: code }));
    view(); await ready(); input('Proposed headline', 'Retain');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByText('skills: Cannot review these values.');
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Retain');
    expect(applyMock).not.toHaveBeenCalled();
  });

  it('preserves edits and unchecked items when regeneration fails', async () => {
    generationMock.mockRejectedValueOnce(Object.assign(new Error('Quota reached'), { status: 429 }));
    view(); await ready(); input('Proposed headline', 'Keep edits');
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate suggestions' }));
    await screen.findByText('Quota reached');
    expect((screen.getByLabelText('Proposed headline') as HTMLTextAreaElement).value).toBe('Keep edits');
    expect((screen.getAllByRole('checkbox')[0] as HTMLInputElement).checked).toBe(false);
  });

  it('keeps manual edits visible and selected when new suggestions cover the same field', async () => {
    const complete = structuredClone(record);
    record.suggestions = record.suggestions!.filter(item => item.field !== 'headline');
    view(); await screen.findByLabelText('Manual headline');
    input('Manual headline', 'My manual headline');
    generationMock.mockResolvedValueOnce({ ...complete, id: 'new-set' });
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate suggestions' }));
    await screen.findByLabelText('Proposed headline');
    expect((screen.getByLabelText('Manual headline') as HTMLTextAreaElement).value).toBe('My manual headline');
    fireEvent.click(screen.getByRole('button', { name: 'Review profile changes' }));
    await screen.findByRole('button', { name: 'Save profile changes' });
    expect(reviewMock.mock.calls[0][0].manual_fields).toEqual({ headline: 'My manual headline' });
    expect(reviewMock.mock.calls[0][0].selections.some((item: any) => item.field === 'headline')).toBe(false);
  });

  it('generates only on an explicit click and shows provider errors and retry', async () => {
    apiMock.mockImplementation(async path => {
      if (path === '/profile') return saved;
      if (path.endsWith('/latest')) throw Object.assign(new Error('Not found'), { status: 404 });
      return generationMock();
    });
    generationMock.mockRejectedValueOnce(new Error('AI consent required'));
    view();
    expect(generationMock).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest profile details with AI' }));
    await screen.findByText('AI consent required');
    fireEvent.click(screen.getByRole('button', { name: 'Suggest profile details with AI' }));
    await screen.findByLabelText('Proposed headline');
    expect(generationMock).toHaveBeenCalledTimes(2);
  });

  it('ignores a set belonging to another resume and shows failed provider diagnostics', async () => {
    record = { ...record, resume_id: 'someone-else' };
    const rendered = view();
    await screen.findByRole('button', { name: 'Suggest profile details with AI' });
    expect(screen.queryByLabelText('Proposed headline')).toBeNull();
    rendered.unmount(); record = { ...record, resume_id: resume.id, status: 'failed', outcome_message: 'invalid_field_value', failure_field: 'experience' };
    view(); await screen.findByText('invalid_field_value · experience');
    expect(screen.getByRole('button', { name: 'Retry suggestions' })).toBeTruthy();
  });
});
