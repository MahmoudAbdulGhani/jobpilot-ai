'use client';
import { useEffect, useState } from 'react';
import {
  Bank,
  Briefcase,
  CheckCircle,
  GraduationCap,
  MapPin,
  PencilSimple,
  Plus,
  Translate,
  Trash,
  UserCircle,
  Wallet,
} from '@phosphor-icons/react';
import { api } from '../lib/api';
import type {
  CandidateProfile,
  CandidateProfileInput,
  EducationEntry,
  ExperienceEntry,
  LanguageEntry,
  LanguageProficiency,
  RemotePreference,
  WorkAuthorization,
} from '../lib/types';

const MAX_TARGET_ROLES = 10;
const MAX_SKILLS = 50;
const MAX_EXPERIENCE = 20;
const MAX_EDUCATION = 10;
const MAX_LANGUAGES = 15;

const REMOTE_OPTIONS: Array<{ value: RemotePreference; label: string }> = [
  { value: 'office', label: 'On site' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
];

const WORK_AUTH_OPTIONS: Array<{ value: WorkAuthorization; label: string }> = [
  { value: 'citizen', label: 'Citizen' },
  { value: 'permanent_resident', label: 'Permanent resident' },
  { value: 'work_visa', label: 'Work visa holder' },
  { value: 'needs_sponsorship', label: 'Needs sponsorship' },
  { value: 'other', label: 'Other' },
];

const PROFICIENCY_OPTIONS: Array<{ value: LanguageProficiency; label: string }> = [
  { value: 'basic', label: 'Basic' },
  { value: 'conversational', label: 'Conversational' },
  { value: 'professional', label: 'Professional' },
  { value: 'native', label: 'Native' },
];

type Draft = {
  headline: string;
  target_roles: string;
  location: string;
  remote_preference: string;
  work_authorization: string;
  skills: string;
  experience: ExperienceEntry[];
  education: EducationEntry[];
  languages: LanguageEntry[];
  currency: string;
  salary_min: string;
  salary_max: string;
};

type PageState = 'loading' | 'ready' | 'missing' | 'error';

function draftFrom(profile: CandidateProfile | null): Draft {
  return {
    headline: profile?.headline ?? '',
    target_roles: (profile?.target_roles ?? []).join(', '),
    location: profile?.location ?? '',
    remote_preference: profile?.remote_preference ?? '',
    work_authorization: profile?.work_authorization ?? '',
    skills: (profile?.skills ?? []).join(', '),
    experience: profile?.experience ?? [],
    education: profile?.education ?? [],
    languages: profile?.languages ?? [],
    currency: profile?.salary_preference?.currency ?? 'USD',
    salary_min: profile?.salary_preference?.min != null ? String(profile.salary_preference.min) : '',
    salary_max: profile?.salary_preference?.max != null ? String(profile.salary_preference.max) : '',
  };
}

function splitList(value: string): string[] {
  return value.split(',').map(item => item.trim()).filter(Boolean);
}

function statusCode(error: unknown): number | undefined {
  return (error as { status?: number }).status;
}

export function ProfileView() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [state, setState] = useState<PageState>('loading');
  const [loadError, setLoadError] = useState('');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(null));
  const [notice, setNotice] = useState('');
  const [formError, setFormError] = useState('');
  const [pending, setPending] = useState(false);

  async function loadProfile() {
    setState('loading');
    setLoadError('');
    try {
      const loaded = await api<CandidateProfile>('/profile');
      setProfile(loaded);
      setState('ready');
    } catch (error) {
      setProfile(null);
      if (statusCode(error) === 404) {
        setState('missing');
      } else {
        setLoadError(error instanceof Error ? error.message : 'Could not load your profile.');
        setState('error');
      }
    }
  }

  useEffect(() => { void loadProfile(); }, []);

  useEffect(() => {
    const reconcile = (event: Event) => {
      const next = (event as CustomEvent<CandidateProfile>).detail;
      if (!next) return;
      setProfile(next);
      setState('ready');
      setDraft(current => editing ? current : draftFrom(next));
      setNotice('Profile updated from your saved suggestions.');
    };
    window.addEventListener('jobpilot:profile-updated', reconcile);
    return () => window.removeEventListener('jobpilot:profile-updated', reconcile);
  }, [editing]);

  function startEditing() {
    setDraft(draftFrom(profile));
    setFormError('');
    setEditing(true);
  }

  function updateExperience(index: number, patch: Partial<ExperienceEntry>) {
    setDraft(current => {
      const next = [...current.experience];
      next[index] = { ...next[index], ...patch };
      return { ...current, experience: next };
    });
  }

  function updateEducation(index: number, patch: Partial<EducationEntry>) {
    setDraft(current => {
      const next = [...current.education];
      next[index] = { ...next[index], ...patch };
      return { ...current, education: next };
    });
  }

  function updateLanguage(index: number, patch: Partial<LanguageEntry>) {
    setDraft(current => {
      const next = [...current.languages];
      next[index] = { ...next[index], ...patch };
      return { ...current, languages: next };
    });
  }

  function buildInput(d: Draft): CandidateProfileInput {
    const minRaw = d.salary_min.trim();
    const maxRaw = d.salary_max.trim();
    const min = minRaw === '' ? null : Number(minRaw);
    const max = maxRaw === '' ? null : Number(maxRaw);
    const hasSalary = Boolean(d.currency.trim()) || min !== null || max !== null;
    const payload: CandidateProfileInput = {
      headline: d.headline.trim() || null,
      target_roles: splitList(d.target_roles),
      location: d.location.trim() || null,
      remote_preference: (d.remote_preference || null) as RemotePreference | null,
      work_authorization: (d.work_authorization || null) as WorkAuthorization | null,
      skills: splitList(d.skills),
      experience: d.experience.map(entry => ({
        title: entry.title.trim(),
        organization: entry.organization.trim(),
        period: entry.period?.trim() || null,
        notes: entry.notes?.trim() || null,
      })),
      education: d.education.map(entry => ({
        school: entry.school.trim(),
        degree: entry.degree?.trim() || null,
        field: entry.field?.trim() || null,
        period: entry.period?.trim() || null,
      })),
      languages: d.languages.map(entry => ({
        name: entry.name.trim(),
        proficiency: entry.proficiency,
      })),
      salary_preference: hasSalary
        ? { currency: d.currency.trim() || 'USD', min, max }
        : null,
    };
    return payload;
  }

  function buildChangedInput(d: Draft, current: CandidateProfile | null): Partial<CandidateProfileInput> {
    const full = buildInput(d);
    if (!current) return full;
    const changed: Partial<CandidateProfileInput> = {};
    for (const field of Object.keys(full) as Array<keyof CandidateProfileInput>) {
      if (JSON.stringify(full[field]) !== JSON.stringify(current[field])) {
        changed[field] = full[field] as never;
      }
    }
    return changed;
  }

  function validate(d: Draft): string {
    if (d.experience.some(entry => !entry.title.trim() || !entry.organization.trim())) {
      return 'Every experience entry needs a title and an organization.';
    }
    if (d.education.some(entry => !entry.school.trim())) {
      return 'Every education entry needs a school.';
    }
    if (d.languages.some(entry => !entry.name.trim())) {
      return 'Every language needs a name.';
    }
    if (d.target_roles.split(',').filter(item => item.trim()).length > MAX_TARGET_ROLES) {
      return `You can list up to ${MAX_TARGET_ROLES} target roles.`;
    }
    if (d.skills.split(',').filter(item => item.trim()).length > MAX_SKILLS) {
      return `You can list up to ${MAX_SKILLS} skills.`;
    }
    const minRaw = d.salary_min.trim();
    const maxRaw = d.salary_max.trim();
    if ((minRaw && !/^\d+$/.test(minRaw)) || (maxRaw && !/^\d+$/.test(maxRaw))) {
      return 'Salary amounts must be whole numbers.';
    }
    const min = minRaw === '' ? null : Number(minRaw);
    const max = maxRaw === '' ? null : Number(maxRaw);
    if (min !== null && max !== null && min > max) {
      return 'The minimum salary must not be higher than the maximum.';
    }
    return '';
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const error = validate(draft);
    if (error) {
      setFormError(error);
      return;
    }
    setPending(true);
    setFormError('');
    try {
      const saved = await api<CandidateProfile>('/profile', {
        method: 'PATCH',
        body: JSON.stringify(buildChangedInput(draft, profile)),
      });
      setProfile(saved);
      setDraft(draftFrom(saved));
      setState('ready');
      setEditing(false);
      setNotice(saved.headline ? 'Profile saved.' : 'Profile saved. Add your headline to make it stand out.');
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Could not save your profile.');
    } finally {
      setPending(false);
    }
  }

  if (state === 'loading') {
    return <div className="center-state">Loading profile…</div>;
  }

  if (state === 'error') {
    return (
      <div className="center-state">
        <h1>Profile unavailable</h1>
        <p className="muted">{loadError}</p>
        <button className="primary-button" onClick={() => void loadProfile()}>Try again</button>
      </div>
    );
  }

  if (state === 'missing' && !editing) {
    return (
      <div className="collection-page">
        <header className="collection-heading">
          <div>
            <p className="eyebrow">Candidate profile</p>
            <h1>Your profile</h1>
            <p className="collection-subtitle">A private snapshot of your background and preferences.</p>
          </div>
        </header>
        <div className="empty-state">
          <UserCircle size={56} />
          <h2>Your profile is not set up yet</h2>
          <p>Add a headline, target roles, skills, and preferences to get started.</p>
          <button className="primary-button" onClick={startEditing}><Plus size={19} />Set up profile</button>
        </div>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="collection-page">
        <header className="collection-heading">
          <div>
            <p className="eyebrow">Candidate profile</p>
            <h1>{profile ? 'Edit profile' : 'Set up your profile'}</h1>
            <p className="collection-subtitle">Only you can see this private profile.</p>
          </div>
        </header>
        <form className="profile-form" onSubmit={save} noValidate>
          <div className="form-body">
            <label>Headline
              <input
                name="headline"
                value={draft.headline}
                maxLength={200}
                placeholder="e.g. Senior Backend Engineer focused on reliable APIs"
                onChange={event => setDraft(current => ({ ...current, headline: event.target.value }))}
              />
            </label>
            <div className="form-grid">
              <label>Target roles
                <input
                  name="target_roles"
                  value={draft.target_roles}
                  maxLength={600}
                  placeholder="Backend Engineer, Platform Engineer"
                  onChange={event => setDraft(current => ({ ...current, target_roles: event.target.value }))}
                />
              </label>
              <label>Location
                <input
                  name="location"
                  value={draft.location}
                  maxLength={300}
                  placeholder="City, Country or Remote"
                  onChange={event => setDraft(current => ({ ...current, location: event.target.value }))}
                />
              </label>
            </div>
            <div className="form-grid">
              <label>Remote preference
                <select
                  name="remote_preference"
                  value={draft.remote_preference}
                  onChange={event => setDraft(current => ({ ...current, remote_preference: event.target.value }))}
                >
                  <option value="">Not specified</option>
                  {REMOTE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>Work authorization
                <select
                  name="work_authorization"
                  value={draft.work_authorization}
                  onChange={event => setDraft(current => ({ ...current, work_authorization: event.target.value }))}
                >
                  <option value="">Not specified</option>
                  {WORK_AUTH_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
            <label>Skills
              <input
                name="skills"
                value={draft.skills}
                maxLength={1200}
                placeholder="Python, FastAPI, PostgreSQL"
                onChange={event => setDraft(current => ({ ...current, skills: event.target.value }))}
              />
            </label>

            <div className="entry-group">
              <div className="entry-heading"><span><Briefcase size={22} />Experience</span></div>
              {draft.experience.map((entry, index) => (
                <div className="entry-card" key={index}>
                  <div className="form-grid">
                    <label>Title<input
                      value={entry.title}
                      maxLength={200}
                      placeholder="Backend Engineer"
                      onChange={event => {
                        updateExperience(index, { title: event.target.value });
                      }}
                    /></label>
                    <label>Organization<input
                      value={entry.organization}
                      maxLength={200}
                      placeholder="Example Systems"
                      onChange={event => {
                        updateExperience(index, { organization: event.target.value });
                      }}
                    /></label>
                  </div>
                  <div className="form-grid">
                    <label>Period<input
                      value={entry.period ?? ''}
                      maxLength={100}
                      placeholder="2022 — present"
                      onChange={event => {
                        updateExperience(index, { period: event.target.value });
                      }}
                    /></label>
                    <label>Notes<input
                      value={entry.notes ?? ''}
                      maxLength={2000}
                      placeholder="Short summary"
                      onChange={event => {
                        updateExperience(index, { notes: event.target.value });
                      }}
                    /></label>
                  </div>
                  <button type="button" className="entry-remove" aria-label={`Remove experience entry ${index + 1}`} onClick={() => setDraft(current => ({ ...current, experience: current.experience.filter((_, item) => item !== index) }))}>
                    <Trash size={18} />Remove
                  </button>
                </div>
              ))}
              <button type="button" className="text-button" disabled={draft.experience.length >= MAX_EXPERIENCE} onClick={() => setDraft(current => ({ ...current, experience: [...current.experience, { title: '', organization: '', period: null, notes: null }] }))}>
                <Plus size={18} />Add experience
              </button>
            </div>

            <div className="entry-group">
              <div className="entry-heading"><span><GraduationCap size={22} />Education</span></div>
              {draft.education.map((entry, index) => (
                <div className="entry-card" key={index}>
                  <div className="form-grid">
                    <label>School<input
                      value={entry.school}
                      maxLength={200}
                      placeholder="State University"
                      onChange={event => {
                        updateEducation(index, { school: event.target.value });
                      }}
                    /></label>
                    <label>Degree<input
                      value={entry.degree ?? ''}
                      maxLength={200}
                      placeholder="B.Sc."
                      onChange={event => {
                        updateEducation(index, { degree: event.target.value });
                      }}
                    /></label>
                  </div>
                  <div className="form-grid">
                    <label>Field of study<input
                      value={entry.field ?? ''}
                      maxLength={200}
                      placeholder="Computer Science"
                      onChange={event => {
                        updateEducation(index, { field: event.target.value });
                      }}
                    /></label>
                    <label>Period<input
                      value={entry.period ?? ''}
                      maxLength={100}
                      placeholder="2016 — 2020"
                      onChange={event => {
                        updateEducation(index, { period: event.target.value });
                      }}
                    /></label>
                  </div>
                  <button type="button" className="entry-remove" aria-label={`Remove education entry ${index + 1}`} onClick={() => setDraft(current => ({ ...current, education: current.education.filter((_, item) => item !== index) }))}>
                    <Trash size={18} />Remove
                  </button>
                </div>
              ))}
              <button type="button" className="text-button" disabled={draft.education.length >= MAX_EDUCATION} onClick={() => setDraft(current => ({ ...current, education: [...current.education, { school: '', degree: null, field: null, period: null }] }))}>
                <Plus size={18} />Add education
              </button>
            </div>

            <div className="entry-group">
              <div className="entry-heading"><span><Translate size={22} />Languages</span></div>
              {draft.languages.map((entry, index) => (
                <div className="entry-card entry-card-slim" key={index}>
                  <div className="form-grid">
                    <label>Language<input
                      value={entry.name}
                      maxLength={100}
                      placeholder="English"
                      onChange={event => {
                        updateLanguage(index, { name: event.target.value });
                      }}
                    /></label>
                    <label>Proficiency<select
                      value={entry.proficiency}
                      onChange={event => {
                        updateLanguage(index, { proficiency: event.target.value as LanguageProficiency });
                      }}
                    >
                      {PROFICIENCY_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select></label>
                  </div>
                  <button type="button" className="entry-remove" aria-label={`Remove language ${index + 1}`} onClick={() => setDraft(current => ({ ...current, languages: current.languages.filter((_, item) => item !== index) }))}>
                    <Trash size={18} />Remove
                  </button>
                </div>
              ))}
              <button type="button" className="text-button" disabled={draft.languages.length >= MAX_LANGUAGES} onClick={() => setDraft(current => ({ ...current, languages: [...current.languages, { name: '', proficiency: 'professional' }] }))}>
                <Plus size={18} />Add language
              </button>
            </div>

            <div className="entry-group">
              <div className="entry-heading"><span><Wallet size={22} />Salary preference</span></div>
              <div className="form-grid">
                <label>Currency<input
                  name="currency"
                  value={draft.currency}
                  maxLength={12}
                  placeholder="USD"
                  onChange={event => setDraft(current => ({ ...current, currency: event.target.value }))}
                /></label>
                <label>Minimum (yearly, optional)<input
                  name="salary_min"
                  inputMode="numeric"
                  value={draft.salary_min}
                  maxLength={12}
                  placeholder="120000"
                  onChange={event => setDraft(current => ({ ...current, salary_min: event.target.value }))}
                /></label>
                <label>Maximum (yearly, optional)<input
                  name="salary_max"
                  inputMode="numeric"
                  value={draft.salary_max}
                  maxLength={12}
                  placeholder="160000"
                  onChange={event => setDraft(current => ({ ...current, salary_max: event.target.value }))}
                /></label>
              </div>
            </div>

            {formError && <p className="form-error" role="alert">{formError}</p>}
          </div>
          <footer className="dialog-footer">
            <button type="button" className="secondary-button" disabled={pending} onClick={() => setEditing(false)}>Cancel</button>
            <button className="primary-button" disabled={pending}>{pending ? 'Saving…' : 'Save profile'}</button>
          </footer>
        </form>
      </div>
    );
  }

  return (
    <div className="collection-page">
      <header className="collection-heading">
        <div>
          <p className="eyebrow">Candidate profile</p>
          <h1>Your profile</h1>
          <p className="collection-subtitle">A private snapshot of your background and preferences.</p>
        </div>
        <button className="primary-button" onClick={startEditing}><PencilSimple size={19} />Edit profile</button>
      </header>
      {notice && <p className="notice profile-notice" role="status"><CheckCircle size={19} />{notice}</p>}
      <div className="profile-grid">
        <section className="profile-card profile-main">
          <div className="profile-hero">
            <span className="avatar profile-avatar"><UserCircle size={44} weight="duotone" /></span>
            <div>
              <h2>{profile?.headline || 'Your headline'}</h2>
              {(profile?.location || profile?.remote_preference) && (
                <p className="profile-meta">
                  {profile?.location && <span><MapPin size={17} />{profile.location}</span>}
                  {profile?.location && profile?.remote_preference && <span className="meta-dot">·</span>}
                  {profile?.remote_preference && <span>{REMOTE_OPTIONS.find(option => option.value === profile!.remote_preference)?.label}</span>}
                </p>
              )}
            </div>
          </div>
          <section className="profile-section">
            <h3>Target roles</h3>
            {profile?.target_roles?.length ? (
              <ul className="chip-list">{profile.target_roles.map(role => <li key={role} className="chip">{role}</li>)}</ul>
            ) : <p className="muted">Not specified yet.</p>}
          </section>
          <section className="profile-section">
            <h3>Skills</h3>
            {profile?.skills?.length ? (
              <ul className="chip-list">{profile.skills.map(skill => <li key={skill} className="chip">{skill}</li>)}</ul>
            ) : <p className="muted">Not specified yet.</p>}
          </section>
          <section className="profile-section">
            <h3>Experience</h3>
            {profile?.experience?.length ? (
              <ol className="timeline-list">
                {profile.experience.map((entry, index) => (
                  <li key={index}>
                    <strong>{entry.title}</strong>
                    <span className="muted">{entry.organization}{entry.period ? <span> · {entry.period}</span> : null}</span>
                    {entry.notes ? <p className="preserve-lines">{entry.notes}</p> : null}
                  </li>
                ))}
              </ol>
            ) : <p className="muted">No experience entries yet.</p>}
          </section>
          <section className="profile-section">
            <h3>Education</h3>
            {profile?.education?.length ? (
              <ol className="timeline-list">
                {profile.education.map((entry, index) => (
                  <li key={index}>
                    <strong>{entry.degree ? `${entry.degree}${entry.field ? `, ${entry.field}` : ''}` : entry.school}</strong>
                    <span className="muted">{entry.degree ? entry.school : null}{entry.period ? <span> · {entry.period}</span> : null}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="muted">No education entries yet.</p>}
          </section>
        </section>
        <aside className="profile-card profile-side">
          <section className="profile-section">
            <h3><Briefcase size={20} />Work authorization</h3>
            <p>{profile?.work_authorization ? WORK_AUTH_OPTIONS.find(option => option.value === profile.work_authorization)?.label : <span className="muted">Not specified.</span>}</p>
          </section>
          <section className="profile-section">
            <h3><Bank size={20} />Languages</h3>
            {profile?.languages?.length ? (
              <ul className="line-list">
                {profile.languages.map((entry, index) => (
                  <li key={index}><strong>{entry.name}</strong><span className="muted">{PROFICIENCY_OPTIONS.find(option => option.value === entry.proficiency)?.label}</span></li>
                ))}
              </ul>
            ) : <p className="muted">No languages added.</p>}
          </section>
          <section className="profile-section">
            <h3><Wallet size={20} />Salary preference</h3>
            {profile?.salary_preference ? (
              <p>
                {profile.salary_preference.min != null ? `From ${profile.salary_preference.min.toLocaleString()}` : 'Open from'}
                {profile.salary_preference.max != null ? ` to ${profile.salary_preference.max.toLocaleString()} ${profile.salary_preference.currency}` : null}
              </p>
            ) : <p className="muted">Not specified.</p>}
          </section>
        </aside>
      </div>
    </div>
  );
}
