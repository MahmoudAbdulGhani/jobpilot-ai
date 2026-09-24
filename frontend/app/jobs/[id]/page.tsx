'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState, type KeyboardEvent } from 'react';
import { Archive, ArrowLeft, ArrowRight, ArrowSquareOut, CalendarBlank, CaretRight, CheckSquare, FileText, LockSimple, MapPin, Microphone, NotePencil, PaperPlaneTilt, PencilSimple, Sparkle, Trash } from '@phosphor-icons/react';
import { Shell } from '../../../components/Shell';
import { DeleteDialog, JobEditor, NotesEditor } from '../../../components/Dialog';
import { JobDescription as Description } from '../../../components/JobDescription';
import { JobFitAnalysis } from '../../../components/JobFitAnalysis';
import { ApplicationPacks } from '../../../components/ApplicationPacks';
import { AtsReport } from '../../../components/AtsReport';
import { EmailApplication } from '../../../components/EmailApplication';
import { ApplicationTracking } from '../../../components/ApplicationTracking';
import { api } from '../../../lib/api';
import type { Job, JobInput } from '../../../lib/types';
import '../../workflows.css';

const TABS = [
  { id: 'overview', label: 'Overview', icon: FileText },
  { id: 'materials', label: 'Application pack', icon: Sparkle },
  { id: 'email', label: 'Apply by email', icon: PaperPlaneTilt },
  { id: 'tracking', label: 'Tracking', icon: CheckSquare },
] as const;
type Tab = typeof TABS[number]['id'];

export default function Detail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [tab, setTab] = useState<Tab>('overview');
  const [modal, setModal] = useState<'edit' | 'notes' | 'delete' | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setJob(null); setError(''); setActionError('');
    api<Job>(`/jobs/${id}`).then(value => { if (active) setJob(value); }).catch(caught => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    const showHash = () => {
      const requested = window.location.hash.slice(1);
      if (TABS.some(item => item.id === requested)) setTab(requested as Tab);
    };
    showHash();
    window.addEventListener('hashchange', showHash);
    return () => window.removeEventListener('hashchange', showHash);
  }, []);

  function changeTab(next: Tab) {
    setTab(next);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${next}`);
  }

  function tabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === 'ArrowRight' ? (index + 1) % TABS.length : event.key === 'ArrowLeft' ? (index + TABS.length - 1) % TABS.length : event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    changeTab(TABS[next].id);
    document.getElementById(`job-tab-${TABS[next].id}`)?.focus();
  }

  async function patch(body: Partial<JobInput> & { is_archived?: boolean }, closeModal = true) {
    const updated = await api<Job>(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    setJob(updated);
    if (closeModal) setModal(null);
  }

  if (error) return <Shell><section className="app-page workflow-empty" role="alert"><span className="workflow-empty-icon"><FileText size={28} /></span><h1>We couldn’t open this job</h1><p>{error}</p><Link className="secondary-button" href="/jobs"><ArrowLeft size={17} />Back to saved jobs</Link></section></Shell>;
  if (!job) return <Shell><section className="app-page job-detail-page" aria-busy="true" aria-label="Loading opportunity"><div className="workflow-skeleton workflow-skeleton-title" /><div className="workflow-skeleton workflow-skeleton-subtitle" /><div className="workflow-skeleton workflow-skeleton-panel" /><p className="sr-only" role="status">Loading opportunity…</p></section></Shell>;

  const safeUrl = job.source_url && /^https?:\/\//i.test(job.source_url) ? job.source_url : null;
  const snapshotUrl = job.source_snapshot?.source_url && /^https?:\/\//i.test(job.source_snapshot.source_url) ? job.source_snapshot.source_url : null;
  const backPath = job.is_archived ? '/archive' : '/jobs';
  const initials = job.company.split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();

  return <Shell><div className="app-page job-detail-page">
    <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href={backPath}>{job.is_archived ? 'Archive' : 'Saved jobs'}</Link><CaretRight size={13} aria-hidden="true" /><span aria-current="page">{job.company}</span></nav>
    <header className="job-heading">
      <div className="job-heading-main"><span className="job-company-mark" aria-hidden="true">{initials}</span><div><p className="eyebrow">{job.is_archived ? 'Archived opportunity' : 'Your opportunity workspace'}</p><h1>{job.title}</h1><p className="company-name">{job.company}</p></div></div>
      <div className="job-heading-bottom"><div className="job-meta">{job.location && <span><MapPin size={16} />{job.location}</span>}<span><CalendarBlank size={16} />Saved {new Date(job.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span><span className="job-private"><LockSimple size={14} />Only you</span></div><div className="job-actions"><button className="secondary-button" onClick={() => setModal('edit')}><PencilSimple size={16} />Edit job</button>{safeUrl && <a className="primary-button" href={safeUrl} target="_blank" rel="noopener noreferrer">Original posting <ArrowSquareOut size={16} /></a>}</div></div>
    </header>

    <div className="job-workspace">
      <div className="job-reading">
        <div className="job-tabs" role="tablist" aria-label="Job workspace">{TABS.map(({ id: key, label, icon: Icon }, index) => <button key={key} id={`job-tab-${key}`} role="tab" type="button" aria-selected={tab === key} aria-controls={`job-panel-${key}`} tabIndex={tab === key ? 0 : -1} onClick={() => changeTab(key)} onKeyDown={event => tabKey(event, index)}><Icon size={17} aria-hidden="true" />{label}</button>)}</div>
        <div className="job-tab-panel" id="job-panel-overview" role="tabpanel" aria-labelledby="job-tab-overview" hidden={tab !== 'overview'} tabIndex={0}>
          <section className="description-section workflow-card"><div className="workflow-section-heading"><div><p className="eyebrow">The opportunity</p><h2>About the role</h2></div><FileText size={21} aria-hidden="true" /></div><Description text={job.description} /></section>
          <JobFitAnalysis job={job} />
        </div>
        <div className="job-tab-panel" id="job-panel-materials" role="tabpanel" aria-labelledby="job-tab-materials" hidden={tab !== 'materials'} tabIndex={0}><ApplicationPacks job={job} /><AtsReport job={job} /></div>
        <div className="job-tab-panel" id="job-panel-email" role="tabpanel" aria-labelledby="job-tab-email" hidden={tab !== 'email'} tabIndex={0}><EmailApplication job={job} /></div>
        <div className="job-tab-panel" id="job-panel-tracking" role="tabpanel" aria-labelledby="job-tab-tracking" hidden={tab !== 'tracking'} tabIndex={0}><ApplicationTracking job={job} /></div>
      </div>

      <aside className="job-rail" aria-label="Your notes and job details">
        <section className="notes-section workflow-card"><div className="workflow-section-heading"><h2>My notes</h2><NotePencil size={19} aria-hidden="true" /></div><div className={`notes-surface preserve-lines ${!job.notes ? 'is-empty' : ''}`}>{job.notes || 'A place for your thoughts, questions, and things to remember.'}</div><button className="text-button edit-notes" onClick={() => setModal('notes')}><PencilSimple size={15} />{job.notes ? 'Edit notes' : 'Add a note'}</button></section>
        <section className="interview-prompt workflow-card"><span className="workflow-small-icon"><Microphone size={21} /></span><h2>Make your next conversation count.</h2><p>Practice interview questions using your reviewed CV and this role.</p><Link className="text-button" href={`/jobs/${job.id}/interviews`}>Prepare interview practice <ArrowRight size={16} /></Link></section>
        <section className="saved-details workflow-card"><h2>Saved details</h2><dl><div><dt>Added</dt><dd>{new Date(job.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</dd></div><div><dt>Last updated</dt><dd>{new Date(job.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</dd></div><div><dt>Visibility</dt><dd><LockSimple size={13} />Only you</dd></div></dl>
          {job.source_provider && <p className="source-provenance">Imported from {job.source_provider === 'jobicy' ? 'Jobicy' : 'JobTech JobSearch'} / {job.source_external_id}{job.source_snapshot?.test_data ? ' (synthetic test data)' : ''}. Original snapshot retained; edits are yours.</p>}
          {job.source_snapshot && <details className="source-details"><summary>Imported source details</summary><p>Published: {job.source_snapshot.published_at || 'Not supplied'}</p><p>Deadline: {job.source_snapshot.deadline || 'Not supplied'}</p><p>Salary: {job.source_snapshot.salary || 'Not supplied'}</p><p>Workplace model: {job.source_snapshot.workplace_model || 'Not supplied'}</p><p>Applicant region (source): {job.source_snapshot.applicant_region || 'Unknown eligibility'}. Remote does not mean worldwide eligibility.</p>{snapshotUrl && <a className="text-button" href={snapshotUrl} target="_blank" rel="noopener noreferrer">Original source at import <ArrowSquareOut size={14} /></a>}</details>}
        </section>
        <div className="archive-action"><button disabled={busy} className="text-button" onClick={async () => { setBusy(true); setActionError(''); try { await patch({ is_archived: !job.is_archived }, false); } catch (caught) { setActionError(caught instanceof Error ? caught.message : 'Could not update this job. Try again.'); } finally { setBusy(false); } }}><Archive size={17} />{busy ? 'Updating…' : job.is_archived ? 'Restore job' : 'Archive job'}</button><button className="text-button workflow-delete" aria-label="Delete job" onClick={() => setModal('delete')}><Trash size={16} />Delete</button></div>
        {actionError && <p className="form-error" role="alert">{actionError}</p>}
      </aside>
    </div>
    {modal === 'edit' && <JobEditor job={job} onClose={() => setModal(null)} onSave={patch} />}
    {modal === 'notes' && <NotesEditor job={job} onClose={() => setModal(null)} onSave={notes => patch({ notes })} />}
    {modal === 'delete' && <DeleteDialog job={job} onClose={() => setModal(null)} onDelete={async () => { await api(`/jobs/${id}`, { method: 'DELETE' }); router.replace(backPath); }} />}
  </div></Shell>;
}
