'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle, Sparkle } from '@phosphor-icons/react';
import { api } from '../lib/api';
import type { CandidateProfile, ExperienceEntry, ProfileChanges, ProfileChangeReview, ProfileSuggestion, ProfileSuggestionSet, Resume } from '../lib/types';

const FIELDS: ProfileSuggestion['field'][] = ['headline', 'location', 'target_roles', 'skills', 'experience', 'education', 'languages', 'remote_preference', 'work_authorization', 'salary_preference'];
const title = (field: string) => field.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
const status = (error: unknown) => (error as { status?: number })?.status;
const message = (error: unknown) => error instanceof Error ? error.message : 'Could not save profile changes.';
const isSuggestion = (item: ProfileSuggestion) => !item.status || item.status === 'suggested';
type GenerationEligibility = { allowed: boolean; kind: 'initial' | 'refresh' | 'unlimited'; remaining_refreshes: number | null; reset_at: string; reason: string | null };

export function ProfileSuggestionsPanel({ resume, enabled }: { resume: Resume; enabled: boolean }) {
  const alive = useRef(true);
  const latest = useRef<ProfileSuggestionSet | null>(null);
  const [set, setSet] = useState<ProfileSuggestionSet | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drafts, setDrafts] = useState<Record<string, any>>({});
  const [editedExperience, setEditedExperience] = useState<Set<string>>(new Set());
  const [extraExperience, setExtraExperience] = useState<ExperienceEntry[]>([]);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [manual, setManual] = useState<Record<string, any>>({});
  const manualDrafts = useRef(manual);
  manualDrafts.current = manual;
  const [pending, setPending] = useState(false);
  const [eligibility, setEligibility] = useState<GenerationEligibility | null>(null);
  const [eligibilityError, setEligibilityError] = useState('');
  const eligibilityRequest = useRef(0);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [review, setReview] = useState<{ result: ProfileChangeReview; changes: ProfileChanges } | null>(null);
  const invalidation = useRef(0);

  const adopt = useCallback((result: ProfileSuggestionSet) => {
    if (!result || result.resume_id !== resume.id) return;
    latest.current = result;
    setSet(result);
    setReview(null);
    const proposed = (result.suggestions || []).filter(isSuggestion);
    const applied = result.status === 'applied' ? result.apply_result?.applied : undefined;
    const accepted = new Map((applied || []).map(item => [item.id, item.value]));
    setSelected(new Set((applied ?? proposed.filter(item => !Object.hasOwn(manualDrafts.current, item.field))).map(item => item.id)));
    setDrafts(Object.fromEntries(proposed.map(item => [item.id, accepted.has(item.id) ? accepted.get(item.id) : item.value])));
    setEditedExperience(new Set());
    setExtraExperience([]);
  }, [resume.id]);

  const loadProfile = useCallback(async () => {
    setLoadError('');
    try {
      const saved = await api<CandidateProfile>('/profile');
      if (alive.current) { setProfile(saved); setLoaded(true); }
    } catch (cause) {
      if (!alive.current) return;
      if (status(cause) === 404) { setProfile(null); setLoaded(true); }
      else setLoadError(message(cause));
    }
  }, []);

  const loadEligibility = useCallback(async () => {
    const request = ++eligibilityRequest.current;
    try {
      const result = await api<GenerationEligibility>(`/profile-suggestions/resumes/${resume.id}/eligibility`);
      if (alive.current && request === eligibilityRequest.current) { setEligibility(result); setEligibilityError(''); }
    } catch {
      if (alive.current && request === eligibilityRequest.current) { setEligibility(null); setEligibilityError('Could not check AI profile allowance. Retry the check.'); }
    }
  }, [resume.id]);

  useEffect(() => {
    alive.current = true;
    if (!enabled) return;
    setEligibility(null);
    setEligibilityError('');
    void loadProfile();
    void loadEligibility();
    let active = true;
    void api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`)
      .then(result => { if (active) adopt(result); })
      .catch(cause => { if (active && status(cause) !== 404) setError(message(cause)); });
    return () => { active = false; alive.current = false; eligibilityRequest.current += 1; };
  }, [adopt, enabled, loadProfile, loadEligibility, resume.id]);

  useEffect(() => {
    const changed = (event: Event) => {
      const saved = (event as CustomEvent<CandidateProfile>).detail;
      if (saved) { setProfile(saved); setLoaded(true); }
      if (latest.current?.status === 'ready') {
        invalidation.current += 1;
        setReview(null);
        setNotice('Your profile changed. Review your changes against the latest saved values.');
      }
    };
    window.addEventListener('jobpilot:profile-updated', changed);
    return () => window.removeEventListener('jobpilot:profile-updated', changed);
  }, []);

  function edit() { invalidation.current += 1; setReview(null); setError(''); setNotice(''); }

  async function generate() {
    if (pending || !eligibility?.allowed) return;
    setPending(true); setError(''); setReview(null); setNotice('');
    const previous = latest.current;
    try {
      let result = await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}`, { method: 'POST' });
      for (let attempt = 0; result.status === 'generating' && attempt < 90; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 1000));
        if (!alive.current) return;
        result = await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`);
        if (!alive.current) return;
      }
      if (result.status === 'generating') throw new Error('Suggestions are still processing.');
      if (result.status === 'failed') {
        if (!previous) adopt(result);
        throw new Error(result.outcome_message || 'Could not refresh suggestions.');
      }
      adopt(result);
    } catch (cause) {
      setError(message(cause));
      if (!previous) try {
        const result = await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`);
        if (result && (result.id !== latest.current?.id || result.status !== latest.current?.status)) adopt(result);
      } catch { /* Keep the original error and the user's drafts. */ }
    } finally { if (alive.current) { setPending(false); void loadEligibility(); } }
  }

  function changes(): ProfileChanges {
    const selections = (set?.suggestions || []).filter(item => isSuggestion(item) && selected.has(item.id))
      .map(item => ({ id: item.id, field: item.field, value: drafts[item.id], evidence: item.evidence }));
    const manualFields = Object.fromEntries(Object.entries(manual).map(([field, value]) => {
      if (field === 'target_roles' || field === 'skills') return [field, value.filter((entry: string) => entry.trim()).map((entry: string) => entry.trim())];
      if (['headline', 'location', 'remote_preference', 'work_authorization'].includes(field)) return [field, value || null];
      return [field, value];
    }));
    const edited = (set?.suggestions || []).filter(item => item.field === 'experience' && editedExperience.has(item.id))
      .map(item => drafts[item.id] as ExperienceEntry);
    return { selections, manual_fields: manualFields, manual_experience_entries: [...edited, ...extraExperience] };
  }

  async function reviewChanges() {
    if (!set || pending) return;
    setPending(true); setError(''); setNotice(''); setReview(null);
    const version = invalidation.current;
    try {
      const input = changes();
      const result = await api<ProfileChangeReview>(`/profile-suggestions/${set.id}/review`, { method: 'POST', body: JSON.stringify(input) });
      if (version === invalidation.current) {
        setProfile(result.current_profile);
        setReview({ result, changes: input });
      }
    } catch (cause) { setError(message(cause)); }
    finally { setPending(false); }
  }

  async function saveChanges() {
    if (!set || !review || pending) return;
    setPending(true); setError('');
    try {
      const applied = await api<ProfileSuggestionSet>(`/profile-suggestions/${set.id}/apply`, {
        method: 'POST', body: JSON.stringify({ ...review.changes, reviewed_profile_revision: review.result.reviewed_profile_revision }),
      });
      adopt(applied);
      setManual({});
      if (applied.profile) {
        setProfile(applied.profile);
        window.dispatchEvent(new CustomEvent<CandidateProfile>('jobpilot:profile-updated', { detail: applied.profile }));
      }
      setNotice('');
    } catch (cause) {
      setError(message(cause));
      if (status(cause) === 409) setReview(null);
    } finally { setPending(false); }
  }

  if (!enabled) return null;
  const ready = set?.status === 'ready';
  const disabled = pending || !loaded || !ready;
  const generationDisabled = pending || !eligibility?.allowed;
  const generationDescription = eligibility?.allowed
    ? eligibility.kind === 'unlimited' ? 'Administrator access: unlimited AI profile generations.'
      : eligibility.kind === 'initial' ? 'This confirmed CV has one initial AI generation available.'
      : `${eligibility.remaining_refreshes} AI profile refresh${eligibility.remaining_refreshes === 1 ? '' : 'es'} left this UTC month.`
    : eligibility?.reason || eligibilityError || 'Checking AI profile allowance…';
  return <section className="ai-suggestions profile-suggestions-panel" aria-label={`Profile suggestions for ${resume.display_name}`}>
    <div className="panel-heading"><div><p className="eyebrow">Profile suggestions</p><h3><Sparkle size={20} />Review profile details</h3></div><span className={`status-badge ${ready ? 'is-confirmed' : ''}`}>{set?.status || 'idle'}</span></div>
    <p className="muted">Provider: {set?.provider || 'OpenAI when configured'}{set?.model ? ` · ${set.model}` : ''}. Your confirmed resume text is shared only when you request suggestions. Review selected suggestions and manual edits together before saving.</p>
    <p className="muted" role="status">{generationDescription}{eligibility?.reset_at && eligibility.kind !== 'unlimited' ? ` Refresh allowance resets ${new Date(eligibility.reset_at).toLocaleDateString(undefined, { timeZone: 'UTC' })} UTC.` : ''} {eligibilityError && <button type="button" className="action-button" onClick={() => void loadEligibility()}>Retry allowance check</button>}</p>
    {loadError && <div role="alert"><p>{loadError}</p><button className="secondary-button" onClick={() => void loadProfile()}>Reload saved profile</button></div>}
    {!set && <button className="secondary-button" aria-label={pending ? 'Generating…' : 'Suggest profile details with AI'} disabled={generationDisabled} onClick={() => void generate()}>{pending ? 'Generating…' : 'Generate suggestions'}</button>}
    {set?.status === 'generating' && <p role="status">Generating suggestions… This page will update automatically.</p>}
    {set?.status === 'failed' && <><p role="alert">{set.outcome_message}{set.failure_field ? ` · ${set.failure_field}` : ''}</p><button className="secondary-button" disabled={generationDisabled} onClick={() => void generate()}>Retry suggestions</button></>}
    {(ready || set?.status === 'applied') && <button className="secondary-button" disabled={generationDisabled} onClick={() => void generate()}>{set?.status === 'applied' ? 'Refresh AI suggestions from this saved CV' : 'Regenerate suggestions'}</button>}
    {(ready || set?.status === 'applied') && FIELDS.map(field => {
      const items = (set?.suggestions || []).filter(item => item.field === field && isSuggestion(item));
      const availability = set?.field_statuses?.[field] || ((set?.suggestions || []).some(item => item.field === field && item.status === 'not_found') ? 'not_found' : 'needs_review');
      const manualOverride = Object.hasOwn(manual, field) || (set?.status === 'applied' && Object.hasOwn(set.apply_result?.manual_fields || {}, field));
      return <div className="suggestion-field-group" key={field}><h4>{title(field)}</h4>
        {items.map(item => <article className="suggestion-card" key={item.id}>
          <label className="suggestion-select"><input type="checkbox" checked={selected.has(item.id) || editedExperience.has(item.id)} disabled={disabled} onChange={() => { edit(); if (!selected.has(item.id) && !editedExperience.has(item.id) && manualOverride) setManual(current => { const next = { ...current }; delete next[field]; return next; }); if (editedExperience.has(item.id)) setEditedExperience(current => { const next = new Set(current); next.delete(item.id); return next; }); if (!selected.has(item.id) && !editedExperience.has(item.id) && field === 'experience') setDrafts(current => ({ ...current, [item.id]: item.value })); setSelected(current => { const next = new Set(current); if (next.has(item.id) || editedExperience.has(item.id)) next.delete(item.id); else next.add(item.id); return next; }); }} />{editedExperience.has(item.id) ? 'Include edited role' : 'Use this AI suggestion'}</label>
          {field === 'experience' && editedExperience.has(item.id) && <><span className="user-provided">User-edited</span><button type="button" className="action-button" disabled={disabled} onClick={() => { edit(); setDrafts(current => ({ ...current, [item.id]: item.value })); setEditedExperience(current => { const next = new Set(current); next.delete(item.id); return next; }); setSelected(current => new Set(current).add(item.id)); }}>Restore AI suggestion</button></>}
          <ValueEditor field={field} value={drafts[item.id]} disabled={disabled} prefix="Proposed" onChange={value => { edit(); setDrafts(current => ({ ...current, [item.id]: value })); if (field === 'experience') { setEditedExperience(current => new Set(current).add(item.id)); setSelected(current => { const next = new Set(current); next.delete(item.id); return next; }); } }} />
          {item.evidence.map((evidence, index) => <blockquote key={index}>“{evidence.quote}”</blockquote>)}
        </article>)}
        {field === 'experience' && items.length > 0 && ready && <div className="manual-field"><p className="muted">Add another role from your CV or your own history. <span className="user-provided">User-provided</span></p>
          <ValueEditor field="experience" value={extraExperience} disabled={disabled} prefix="Added" list onChange={value => { edit(); setExtraExperience(value); }} />
        </div>}
        {field === 'experience' && set?.status === 'applied' && !!profile?.experience?.length && <section aria-label="Saved experience"><h5>Saved experience</h5><ExperienceList entries={profile.experience} /></section>}
        {ready && items.length > 0 && !manualOverride && field !== 'experience' && <button type="button" className="action-button" disabled={disabled} onClick={() => { edit(); setSelected(current => { const next = new Set(current); items.forEach(item => next.delete(item.id)); return next; }); setManual(current => ({ ...current, [field]: profile?.[field] ?? (['target_roles', 'education', 'languages'].includes(field) ? items.map(item => item.value) : items[0].value) })); }}>Enter {title(field)} manually</button>}
        {(!items.length || manualOverride) && <div className="manual-field">
          <p className="muted">{items.length ? (ready ? 'Your manual value is selected. Choose an AI suggestion above to replace it.' : 'Saved as your manual value.') : availability === 'not_found' ? 'Not found in CV — add manually.' : 'No usable AI suggestion — review and add manually.'} <span className="user-provided">User-provided</span></p>
          <ValueEditor field={field} value={Object.hasOwn(manual, field) ? manual[field] : profile?.[field]} prefix="Manual" disabled={disabled} list={['target_roles', 'skills', 'experience', 'education', 'languages'].includes(field)} onChange={value => { edit(); setManual(current => ({ ...current, [field]: value })); }} />
          {field === 'salary_preference' && <button type="button" className="action-button" disabled={disabled} onClick={() => { edit(); setManual(current => ({ ...current, [field]: null })); }}>Clear salary preference</button>}
        </div>}
      </div>;
    })}
    {error && <p className="form-error" role="alert">{error}</p>}
    {notice && <p className="profile-notice" role="status">{notice}</p>}
    {ready && !review && <button className="primary-button" disabled={disabled || (selected.size === 0 && editedExperience.size === 0 && extraExperience.length === 0 && Object.keys(manual).length === 0)} onClick={() => void reviewChanges()}>Review profile changes</button>}
    {ready && review && <section className="profile-save-review" aria-label="Profile change comparison">
      <h4>Review profile changes</h4>
      <p>Selected suggestions and edited manual fields will be saved together. Other saved details stay as shown in your profile.</p>
      {review.result.changed_fields.map(field => <div className="suggestion-card" key={field}><h5>{title(field)}</h5>{field === 'experience' ? <div className="experience-review"><div><h6>Currently saved</h6><ExperienceList entries={review.result.current_profile?.experience} /></div><div><h6>After saving</h6><ExperienceList entries={review.result.proposed_profile.experience} changes={review.changes} /></div></div> : <dl><dt>Currently saved</dt><dd><DisplayValue value={review.result.current_profile?.[field]} /></dd><dt>After saving</dt><dd><DisplayValue value={review.result.proposed_profile[field]} /></dd></dl>}</div>)}
      <div className="dialog-footer"><button className="secondary-button" disabled={pending} onClick={() => setReview(null)}>Back to editing</button><button className="primary-button" disabled={pending} onClick={() => void saveChanges()}>{pending ? 'Saving…' : 'Save profile changes'}</button></div>
    </section>}
    {set?.status === 'applied' && <p className="profile-notice" role="status"><CheckCircle size={18} />Profile changes saved. <a href="/profile">View your profile</a></p>}
  </section>;
}

function ExperienceList({ entries, changes }: { entries: ExperienceEntry[] | null | undefined; changes?: ProfileChanges }) {
  if (!entries?.length) return <p className="muted">No roles saved</p>;
  return <div className="experience-review-list">{entries.map((entry, index) => {
    const suggestion = changes?.selections.find(item => item.field === 'experience' && JSON.stringify(item.value) === JSON.stringify(entry));
    const added = changes?.manual_experience_entries?.some(item => JSON.stringify(item) === JSON.stringify(entry));
    return <article className="experience-review-role" key={`${entry.title}-${entry.organization}-${index}`}>
      <strong>{entry.title} · {entry.organization}</strong>
      {entry.period && <p>{entry.period}</p>}{entry.notes && <p>{entry.notes}</p>}
      {suggestion && <><span className="status-badge is-confirmed">From CV</span>{suggestion.evidence.map((item, evidenceIndex) => <blockquote key={evidenceIndex}>“{item.quote}”</blockquote>)}</>}
      {added && <span className="user-provided">User-provided</span>}
      {!changes && <span className="muted">Already saved</span>}
    </article>;
  })}</div>;
}

function DisplayValue({ value }: { value: any }) {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return <span>Not set</span>;
  if (Array.isArray(value)) return <ul>{value.map((item, index) => <li key={index}><DisplayValue value={item} /></li>)}</ul>;
  if (typeof value === 'object') return <dl>{Object.entries(value).filter(([, item]) => item != null && item !== '').map(([key, item]) => <div key={key}><dt>{title(key)}</dt><dd><DisplayValue value={item} /></dd></div>)}</dl>;
  return <span>{String(value)}</span>;
}

function ValueEditor({ field, value, disabled, prefix, onChange, list = false }: { field: string; value: any; disabled: boolean; prefix: string; onChange: (value: any) => void; list?: boolean }) {
  const structure: Record<string, string[]> = { experience: ['title', 'organization', 'period', 'notes'], education: ['school', 'degree', 'field', 'period'], languages: ['name', 'proficiency'], salary_preference: ['currency', 'min', 'max'] };
  const labels: Record<string, string> = { title: 'Job title', name: 'Language', field: 'Field of study', notes: 'Responsibilities and achievements', min: 'Annual minimum', max: 'Annual maximum' };
  if (list || field === 'skills') {
    const rows = Array.isArray(value) ? value : [];
    return <div aria-label={`${prefix} ${field}`} className="suggestion-skills">{rows.map((entry, index) => <div className="repeatable-row" key={index}>
      {structure[field] ? <ValueEditor field={field} value={entry} disabled={disabled} prefix={`${prefix} ${index + 1}`} onChange={next => onChange(rows.map((item, i) => i === index ? next : item))} /> : <input aria-label={`${prefix} ${field === 'skills' ? 'skill' : 'target role'} ${index + 1}`} disabled={disabled} value={entry} maxLength={field === 'skills' ? 100 : 200} onChange={event => onChange(rows.map((item, i) => i === index ? event.target.value : item))} />}
      {list && <button className="action-button" type="button" disabled={disabled} aria-label={`Remove ${prefix.toLowerCase()} ${field} ${index + 1}`} onClick={() => onChange(rows.filter((_, i) => i !== index))}>Remove</button>}
    </div>)}{list && <button className="action-button" type="button" disabled={disabled} onClick={() => onChange([...rows, field === 'languages' ? { name: '', proficiency: 'professional' } : structure[field] ? {} : ''])}>Add {title(field)}</button>}</div>;
  }
  if (structure[field]) return <div className="suggestion-fields" aria-label={`${prefix} ${field}`}>{structure[field].map(key => {
    const change = (next: any) => onChange({ ...(value || {}), [key]: next });
    const label = `${prefix} ${field} ${key}`;
    return <label key={key}>{labels[key] || title(key)}{key === 'proficiency' ? <select aria-label={label} value={value?.[key] || 'professional'} disabled={disabled} onChange={event => change(event.target.value)}>{['basic', 'conversational', 'professional', 'native'].map(option => <option key={option} value={option}>{title(option)}</option>)}</select> : key === 'notes' ? <textarea aria-label={label} value={value?.[key] || ''} disabled={disabled} maxLength={2000} onChange={event => change(event.target.value || null)} /> : <input aria-label={label} type={key === 'min' || key === 'max' ? 'number' : 'text'} min={key === 'min' || key === 'max' ? 0 : undefined} maxLength={key === 'period' || key === 'name' ? 100 : key === 'currency' ? 12 : 200} value={value?.[key] ?? ''} disabled={disabled} onChange={event => change(key === 'min' || key === 'max' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value || null)} />}</label>;
  })}</div>;
  if (field === 'remote_preference' || field === 'work_authorization') {
    const options = field === 'remote_preference' ? ['office', 'hybrid', 'remote'] : ['citizen', 'permanent_resident', 'work_visa', 'needs_sponsorship', 'other'];
    return <label>{title(field)}<select aria-label={`${prefix} ${field}`} value={value || ''} disabled={disabled} onChange={event => onChange(event.target.value || null)}><option value="">Not set</option>{options.map(option => <option key={option} value={option}>{title(option)}</option>)}</select></label>;
  }
  return <textarea aria-label={`${prefix} ${field}`} value={value || ''} maxLength={field === 'location' ? 300 : 200} disabled={disabled} onChange={event => onChange(event.target.value)} rows={2} />;
}
