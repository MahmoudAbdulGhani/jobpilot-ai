'use client';
import {MeteredButton} from './MeteredButton';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowClockwise, CheckCircle, DownloadSimple, FileText, Sparkle, Trash, WarningCircle } from '@phosphor-icons/react';
import { Dialog } from './Dialog';
import { api, downloadResume } from '../lib/api';
import { editableDocument, type ApplicationPack, type PackBlock, type PackDocument, type PackOptions, type PackPage, type PackVersion, type StoredPackDocument } from '../lib/application-packs';
import type { Job, JobFitAnalysis } from '../lib/types';

type Documents = { cv: PackDocument; cover_letter: PackDocument };
type DocumentName = keyof Documents;
const names: Record<DocumentName, string> = { cv: 'Tailored CV', cover_letter: 'Cover letter' };
const messageFor = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed. Please try again.';
const date = (value: string) => new Date(value).toLocaleString();

function DocumentReview({ name, document, original, editable, facts, applicationFacts, onChange }: {
  name: DocumentName;
  document: PackDocument;
  original: StoredPackDocument;
  editable: boolean;
  facts: Map<string, string>;
  applicationFacts: Set<string>;
  onChange: (document: PackDocument) => void;
}) {
  const originals = new Map(original.blocks.map(block => [block.id, block]));
  const firstHeading = document.blocks.findIndex(block => block.kind === 'heading');
  function update(index: number, values: Partial<PackBlock>) {
    onChange({ blocks: document.blocks.map((block, current) => current === index ? { ...block, ...values } : block) });
  }
  function move(index: number, direction: number) {
    const blocks = [...document.blocks];
    [blocks[index], blocks[index + direction]] = [blocks[index + direction], blocks[index]];
    onChange({ blocks });
  }
  return <section className="pack-document" aria-labelledby={`pack-${name}-heading`}>
    <h3 id={`pack-${name}-heading`}><FileText size={21} />{names[name]}</h3>
    <div className={`pack-paper pack-paper-${name}`} aria-label={`${names[name]} preview`}>
      {document.blocks.map((block, index) => block.kind === 'heading'
        ? <h4 className={index === firstHeading ? 'pack-paper-title' : 'pack-paper-section'} key={block.id}>{block.text}</h4>
        : block.kind === 'bullet' ? <p className="pack-bullet" key={block.id}><span aria-hidden="true">•</span>{block.text}</p>
          : <p key={block.id}>{block.text}</p>)}
    </div>
    <details className="pack-edit">
      <summary>{editable ? 'Review evidence and edit' : 'Review saved evidence'}</summary>
      <p className="muted pack-help">Supporting references help you check a claim. They do not prove it is accurate. Check every name, date, qualification and metric before approval.</p>
      {document.blocks.map((block, index) => {
        const source = originals.get(block.id);
        const changed = !source || source.text !== block.text || source.kind !== block.kind;
        const userAuthored = changed || source.origin === 'user';
        return <div className="pack-block" key={block.id}>
          <div className="pack-block-heading"><span>Block {index + 1}</span><span className="pack-origin">{userAuthored ? 'User-authored · check facts' : block.kind === 'heading' ? 'Document heading' : 'AI draft · verify evidence'}</span></div>
          {editable ? <>
            <label className="pack-field">{names[name]} block {index + 1} style<select value={block.kind} onChange={event => update(index, { kind: event.target.value as PackBlock['kind'] })}><option value="heading">Heading</option><option value="paragraph">Paragraph</option><option value="bullet">Bullet</option></select></label>
            <label className="pack-field">{names[name]} block {index + 1} text<textarea value={block.text} rows={block.kind === 'heading' ? 2 : 4} maxLength={2000} onChange={event => update(index, { text: event.target.value })} /></label>
            <div className="pack-block-actions"><button className="text-button" disabled={index === 0} aria-label={`Move ${names[name]} block ${index + 1} up`} onClick={() => move(index, -1)}>Move up</button><button className="text-button" disabled={index === document.blocks.length - 1} aria-label={`Move ${names[name]} block ${index + 1} down`} onClick={() => move(index, 1)}>Move down</button><button className="text-button" disabled={document.blocks.length === 1} aria-label={`Remove ${names[name]} block ${index + 1}`} onClick={() => onChange({ blocks: document.blocks.filter((_, current) => current !== index) })}>Remove</button></div>
          </> : <p className="preserve-lines">{block.text}</p>}
          {userAuthored ? <p className="muted pack-help">This wording is your change. No supporting citation is assigned to it.</p> : source.evidence.length > 0 && <div className="pack-evidence"><strong>Supporting source</strong>{source.evidence.map((evidence, evidenceIndex) => <div key={evidenceIndex}>{evidence.fact_id && <p><span>{applicationFacts.has(evidence.fact_id) ? 'Confirmed for this application:' : 'Saved profile:'}</span> {facts.get(evidence.fact_id) || 'Source fact unavailable'}</p>}{evidence.cv_quote && <blockquote>{evidence.cv_quote}</blockquote>}</div>)}</div>}
        </div>;
      })}
      {editable && <button className="text-button pack-add" disabled={document.blocks.length >= 100} onClick={() => onChange({ blocks: [...document.blocks, { id: crypto.randomUUID(), kind: 'paragraph', text: '' }] })}>Add a paragraph to {names[name]}</button>}
    </details>
  </section>;
}

export function ApplicationPacks({ job }: { job: Job }) {
  const base = `/jobs/${job.id}/application-packs`;
  const [options, setOptions] = useState<PackOptions | null>(null);
  const [fit, setFit] = useState<JobFitAnalysis | null>(null);
  const [jobSkills, setJobSkills] = useState<string[]>([]);
  const [resumeId, setResumeId] = useState('');
  const [history, setHistory] = useState<PackPage<ApplicationPack> | null>(null);
  const [pack, setPack] = useState<ApplicationPack | null>(null);
  const [versions, setVersions] = useState<PackPage<PackVersion> | null>(null);
  const [viewedVersion, setViewedVersion] = useState<PackVersion | null>(null);
  const [documents, setDocuments] = useState<Documents | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [checked, setChecked] = useState(false);
  const [leaveAction, setLeaveAction] = useState<(() => void) | null>(null);
  const mutationKeys = useRef(new Map<string, string>());
  const generationKey = useRef<string | null>(null);
  const loadedJob = useRef('');
  const currentVersion = viewedVersion || pack?.version;
  const saved = useMemo(() => currentVersion ? { cv: editableDocument(currentVersion.cv), cover_letter: editableDocument(currentVersion.cover_letter) } : null, [currentVersion]);
  const dirty = !!documents && JSON.stringify(documents) !== JSON.stringify(saved);
  const facts = useMemo(() => new Map([...(pack?.source_snapshot.profile_facts || []), ...(pack?.source_snapshot.application_skill_facts || [])].map(fact => [fact.id, fact.value])), [pack]);
  const applicationFacts = useMemo(() => new Set(pack?.source_snapshot.application_skill_facts?.map(fact => fact.id) || []), [pack]);
  const readingHistory = !!viewedVersion && viewedVersion.number !== pack?.current_version;
  const canGenerate = !!options?.available && options.has_profile && options.has_description && !!resumeId && fit?.status === 'ready' && !fit.is_outdated;

  const refreshFit = useCallback(async () => {
    try { setFit(await api<JobFitAnalysis>(`/jobs/${job.id}/fit-analyses/latest`)); }
    catch { setFit(null); }
  }, [job.id]);
  const refreshJobSkills = useCallback(async () => {
    try { const response = await api<{ items: { skill: string }[] }>(`/jobs/${job.id}/application-skills`);
      setJobSkills(response.items.map(item => item.skill)); }
    catch { setJobSkills([]); }
  }, [job.id]);
  useEffect(() => {
    void refreshFit(); void refreshJobSkills();
    window.addEventListener('jobpilot:job-fit-updated', refreshFit);
    window.addEventListener('jobpilot:profile-updated', refreshFit);
    window.addEventListener('jobpilot:job-fit-updated', refreshJobSkills);
    window.addEventListener('jobpilot:application-skills-updated', refreshJobSkills);
    return () => { window.removeEventListener('jobpilot:job-fit-updated', refreshFit); window.removeEventListener('jobpilot:profile-updated', refreshFit);
      window.removeEventListener('jobpilot:job-fit-updated', refreshJobSkills); window.removeEventListener('jobpilot:application-skills-updated', refreshJobSkills); };
  }, [refreshFit, refreshJobSkills]);

  const displayPack = useCallback((value: ApplicationPack | null) => {
    setPack(value); setViewedVersion(null); setVersions(null);
    setDocuments(value?.version ? { cv: editableDocument(value.version.cv), cover_letter: editableDocument(value.version.cover_letter) } : null);
  }, []);

  const load = useCallback(async (keepSelection: boolean) => {
    setLoading(true); setError('');
    try {
      const [available, list] = await Promise.all([api<PackOptions>(`${base}/options`), api<PackPage<ApplicationPack>>(`${base}?page=1&page_size=5`)]);
      setOptions(available); setHistory(list);
      setResumeId(previous => available.resumes.some(resume => resume.id === previous) ? previous : available.resumes[0]?.id || '');
      if (!keepSelection) displayPack(list.items[0] || null);
    } catch (caught) { setError(messageFor(caught)); }
    finally { setLoading(false); }
  }, [base, displayPack]);

  useEffect(() => {
    const keepSelection = loadedJob.current === job.id;
    loadedJob.current = job.id;
    void load(keepSelection);
  }, [load, job.id, job.updated_at]);

  useEffect(() => {
    if (!pack || pack.status !== 'generating') return;
    let canceled = false;
    const interval = window.setInterval(() => {
      api<ApplicationPack>(`${base}/${pack.id}`).then(result => {
        if (!canceled) displayPack(result);
      }).catch(caught => { if (!canceled) setError(messageFor(caught)); });
    }, 3000);
    return () => { canceled = true; window.clearInterval(interval); };
  }, [base, pack, displayPack]);

  useEffect(() => {
    if (!dirty) return;
    function warn(event: BeforeUnloadEvent) { event.preventDefault(); event.returnValue = ''; }
    function navigate(event: MouseEvent) {
      const anchor = (event.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.download || anchor.target === '_blank' || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); event.stopPropagation();
      setLeaveAction(() => () => window.location.assign(anchor.href));
    }
    window.addEventListener('beforeunload', warn);
    document.addEventListener('click', navigate, true);
    return () => { window.removeEventListener('beforeunload', warn); document.removeEventListener('click', navigate, true); };
  }, [dirty]);

  function withSavedDraft(action: () => void) { if (dirty) setLeaveAction(() => action); else action(); }
  function operationKey(action: string, body: object) {
    const identity = `${pack?.id}:${action}:${JSON.stringify(body)}`;
    if (!mutationKeys.current.has(identity)) mutationKeys.current.set(identity, crypto.randomUUID());
    return mutationKeys.current.get(identity)!;
  }
  async function refreshActive() {
    if (!pack) { await load(false); return; }
    setBusy('refresh'); setError('');
    try { displayPack(await api<ApplicationPack>(`${base}/${pack.id}`)); await load(true); }
    catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function generate() {
    if (!canGenerate || busy) return;
    setBusy('generate'); setError(''); setNotice('');
    generationKey.current ||= crypto.randomUUID();
    try {
      const result = await api<ApplicationPack>(base, { method: 'POST', body: JSON.stringify({ resume_id: resumeId, idempotency_key: generationKey.current }) });
      generationKey.current = null;
      displayPack(result);
      setNotice(result.status === 'ready' ? 'Both drafts are ready for your review.' : result.status === 'failed' ? 'Generation failed. Your source documents are unchanged; you can retry.' : 'Generation is pending. You can return to this saved pack.');
      await load(true);
    } catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function approve() {
    if (!pack || busy || dirty || !checked) return;
    setBusy('approve'); setError(''); setNotice('');
    const body = { expected_version: pack.current_version };
    try {
      displayPack(await api<ApplicationPack>(`${base}/${pack.id}/approve`, { method: 'POST', body: JSON.stringify({ ...body, idempotency_key: operationKey('approve', body) }) }));
      setApproving(false); setNotice('Version approved. Your PDF and DOCX downloads are ready.'); await load(true);
    } catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function remove() {
    if (!pack || busy) return;
    setBusy('delete'); setError('');
    try { await api(`${base}/${pack.id}`, { method: 'DELETE' }); setDeleting(false); displayPack(null); await load(false); setNotice('Application pack and its versions deleted.'); }
    catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function download(documentName: DocumentName, format: 'pdf' | 'docx') {
    if (!pack || !currentVersion || busy) return;
    setBusy('download'); setError('');
    try {
      const blob = await downloadResume(`${base}/${pack.id}/versions/${currentVersion.number}/download?document=${documentName}&format=${format}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `${documentName === 'cv' ? 'cv' : 'cover-letter'}-v${currentVersion.number}.${format}`;
      document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`${names[documentName]} ${format.toUpperCase()} downloaded from approved version ${currentVersion.number}.`);
    } catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function openPack(id: string) {
    setBusy('history'); setError(''); setNotice('');
    try { displayPack(await api<ApplicationPack>(`${base}/${id}`)); }
    catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function historyPage(page: number) {
    setBusy('history'); setError('');
    try { setHistory(await api<PackPage<ApplicationPack>>(`${base}?page=${page}&page_size=5`)); }
    catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  async function versionsPage(page: number) {
    if (!pack) return;
    setBusy('history'); setError('');
    try { setVersions(await api<PackPage<PackVersion>>(`${base}/${pack.id}/versions?page=${page}&page_size=5`)); }
    catch (caught) { setError(messageFor(caught)); }
    finally { setBusy(''); }
  }
  function showVersion(version: PackVersion) {
    setViewedVersion(version); setDocuments({ cv: editableDocument(version.cv), cover_letter: editableDocument(version.cover_letter) }); setNotice('');
  }

  return <section className="application-packs" aria-labelledby="application-packs-heading" aria-busy={!!busy || loading}>
    <div className="pack-heading"><div><p className="eyebrow">Prepare your application</p><h2 id="application-packs-heading">CV &amp; cover letter packs</h2></div></div>
    <p className="pack-intro">Create a role-specific CV and cover letter from your reviewed CV, saved profile, and skills you confirmed for this application. Check both previews before approval and download.</p>
    <div className="pack-generation">
      <p className="pack-disclosure">When you choose Generate application pack, the saved job description, saved profile, skills confirmed for this application and selected confirmed CV text, including any contact details and projects, are sent to {options ? <strong>{options.provider === 'deterministic-test' ? 'the deterministic test provider' : options.provider} ({options.model})</strong> : 'the configured AI provider'}. Generation creates private drafts. Your profile, original CV and job stay unchanged.</p>
      <p className="muted pack-help">AI can make mistakes. Check facts, dates, skill claims and relevance in both documents before approval.</p>
      {loading && !options && <p role="status">Loading confirmed CVs and saved packs…</p>}
      {options && <>
        {(!options.has_profile || !options.has_description || !options.resumes.length || !options.available) && <div className="pack-prerequisites"><WarningCircle size={21} aria-hidden="true" /><div>{!options.has_description && <p>{job.source_provider ? 'This source listing has no advert text available for a tailored pack. Choose another job with a description.' : 'Save a job description first.'}</p>}{!options.has_profile && <p><Link href="/profile">Save your candidate profile</Link> before generating.</p>}{!options.resumes.length && <p><Link href="/resumes">Upload a CV and confirm its extracted text</Link> to use it here.</p>}{!options.available && <p>{options.reason || 'AI generation is unavailable in this environment.'}</p>}</div></div>}
        <label className="pack-field" htmlFor="pack-resume">Confirmed CV<select id="pack-resume" value={resumeId} disabled={!!busy || !options.resumes.length} onChange={event => { setResumeId(event.target.value); generationKey.current = null; }}><option value="">Choose a confirmed CV</option>{options.resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.display_name}</option>)}</select></label>
      </>}
      {fit?.status !== 'ready' || fit.is_outdated ? <p className="pack-prerequisites" role="status"><WarningCircle size={20} /><span>{fit?.is_outdated ? 'Your profile changed. Reanalyze job fit before generating a new pack.' : 'Analyze job fit before generating an application pack.'} <Link href="#overview">Go to job fit</Link></span></p> : null}
      {fit?.status === 'ready' && !fit.is_outdated && <div className="pack-skill-note"><CheckCircle size={18} /><span>{jobSkills.length ? `Skills confirmed for this application: ${jobSkills.join(', ')}.` : 'No job-specific skills confirmed. The pack will use your reviewed CV and saved profile.'} <Link href="#overview">Review job skills</Link></span></div>}
      <div className="pack-actions"><MeteredButton feature="pack" className="primary-button" disabled={!canGenerate || !!busy || pack?.status === 'generating'} onClick={() => withSavedDraft(() => void generate())}>{busy === 'generate' ? <ArrowClockwise className="spin" size={19} /> : <Sparkle size={19} />}{busy === 'generate' ? 'Generating both drafts…' : pack?.status === 'failed' ? 'Retry generation' : 'Generate application pack'}</MeteredButton><button className="text-button" disabled={!!busy} onClick={() => withSavedDraft(() => void refreshActive())}>Refresh saved state</button></div>
    </div>
    {error && !deleting && !approving && <div className="form-error" role="alert">{error}{error.includes('AI data-use consent is required') && <p><Link href="/settings#privacy">Allow pack drafts AI use in Privacy settings</Link>, then return and generate your pack.</p>}{/conflict|changed|outdated|version/i.test(error) && <p>Refresh saved state after a conflict. Your unsaved text stays here until you choose to replace it.</p>}</div>}
    {notice && <p className="pack-notice" role="status" aria-live="polite">{notice}</p>}
    {pack && <div className="pack-current">
      <div className="pack-state-row"><div><span className={`status-badge ${currentVersion?.approved_at ? 'is-confirmed' : 'is-unreviewed'}`}>{currentVersion?.approved_at ? `Approved version ${currentVersion.number}` : pack.status === 'generating' ? 'Generation pending' : pack.status === 'failed' ? 'Generation failed' : `Unapproved draft · version ${currentVersion?.number}`}</span><p className="muted pack-help">Created {date(pack.created_at)} · {pack.source_snapshot.resume_name || 'Selected CV'}</p></div><button className="icon-button" aria-label="Delete application pack" disabled={!!busy} onClick={() => setDeleting(true)}><Trash size={21} /></button></div>
      {pack.is_outdated && <p className="pack-warning" role="status"><WarningCircle size={20} />Source content changed. This pack is outdated. Generate a new pack before approving. Previously approved downloads remain unchanged.</p>}
      {pack.status === 'generating' && <p className="pack-warning" role="status">The provider is preparing your drafts. This saved record will update when generation finishes.</p>}
      {pack.status === 'failed' && <p className="form-error" role="alert">{pack.outcome_message || 'The provider could not generate valid drafts. Please retry.'}</p>}
      {pack.review_notes.length > 0 && <div className="pack-review-notes"><h3>Check before approval</h3><ul>{pack.review_notes.map((note, index) => <li key={index}>{note}</li>)}</ul></div>}
      {!!pack.source_snapshot.application_skills?.length && <div className="pack-selected-skills"><strong>Confirmed for this application</strong><p>{pack.source_snapshot.application_skills.map(item => item.skill).join(' · ')}</p></div>}
      {currentVersion && documents && <>
        {readingHistory && <p className="pack-warning">Viewing a saved earlier version. <button className="text-button" disabled={!!busy} onClick={() => displayPack(pack)}>Return to current draft</button></p>}
        {currentVersion.approved_at && <p className="pack-help">Approved {date(currentVersion.approved_at)}. Downloads use this exact saved content.</p>}
        <div className="pack-documents">{(['cv', 'cover_letter'] as const).map(name => <DocumentReview key={`${currentVersion.id}-${name}`} name={name} document={documents[name]} original={currentVersion[name]} editable={false} facts={facts} applicationFacts={applicationFacts} onChange={() => {}} />)}</div>
        {!readingHistory && !currentVersion.approved_at && <div className="pack-save-bar"><p role="status">AI drafts ready for your review</p><div className="pack-actions"><button className="primary-button" disabled={!!busy || pack.is_outdated} onClick={() => { setChecked(false); setError(''); setApproving(true); }}><CheckCircle size={20} />Approve version {currentVersion.number}</button></div></div>}
        {currentVersion.approved_at && <div className="pack-downloads"><h3>Download approved version {currentVersion.number}</h3><p className="muted pack-help">Downloads contain your approved document only. Private evidence and review notes are excluded.</p><div className="pack-actions">{(['cv', 'cover_letter'] as const).flatMap(name => (['pdf', 'docx'] as const).map(format => <button className="secondary-button" key={`${name}-${format}`} disabled={!!busy} onClick={() => void download(name, format)}><DownloadSimple size={18} />{name === 'cv' ? 'CV' : 'Cover letter'} {format.toUpperCase()}</button>))}</div>{dirty && <p className="muted pack-help">These downloads use the approved version, excluding your unsaved edits above.</p>}</div>}
      </>}
      <details className="pack-sources"><summary>Review private source details</summary><p className="muted pack-help">These are the source snapshots used for this pack. Evidence and source text never appear in exports.</p><h3>Confirmed CV</h3><p className="preserve-lines">{pack.source_snapshot.cv_text || 'No source text available.'}</p><h3>Saved profile facts</h3><ul>{pack.source_snapshot.profile_facts?.map(fact => <li key={fact.id}>{fact.value}</li>)}</ul><h3>Skills confirmed for this job</h3><ul>{pack.source_snapshot.application_skills?.map(item => <li key={item.id}>{item.skill}</li>)}</ul><h3>Saved job description</h3><p className="preserve-lines">{pack.source_snapshot.job?.description}</p></details>
      {!!pack.current_version && <div className="pack-history"><button className="text-button" disabled={!!busy} onClick={() => void versionsPage(1)}>View version history</button>{versions && <><ul>{versions.items.map(version => <li key={version.id}><button className="text-button" disabled={!!busy} onClick={() => withSavedDraft(() => showVersion(version))}>Version {version.number} · {version.approved_at ? 'Approved' : 'Unapproved draft'} · {date(version.created_at)}</button></li>)}</ul><div className="pack-pagination"><button className="text-button" disabled={!!busy || versions.page <= 1} onClick={() => void versionsPage(versions.page - 1)}>Newer versions</button><span>Page {versions.page} of {Math.max(1, Math.ceil(versions.total / versions.page_size))}</span><button className="text-button" disabled={!!busy || versions.page * versions.page_size >= versions.total} onClick={() => void versionsPage(versions.page + 1)}>Older versions</button></div></>}</div>}
    </div>}
    {history && history.total > 0 && <details className="pack-history"><summary>Application pack history ({history.total})</summary><ul>{history.items.map(item => <li key={item.id}><button className="text-button" disabled={!!busy} aria-current={pack?.id === item.id ? 'true' : undefined} onClick={() => withSavedDraft(() => void openPack(item.id))}>{date(item.created_at)} · {item.status === 'failed' ? 'Failed' : item.status === 'generating' ? 'Pending' : item.version?.approved_at ? 'Approved' : 'Draft'}{item.is_outdated ? ' · Outdated' : ''}</button></li>)}</ul><div className="pack-pagination"><button className="text-button" disabled={!!busy || history.page <= 1} onClick={() => void historyPage(history.page - 1)}>Newer packs</button><span>Page {history.page} of {Math.ceil(history.total / history.page_size)}</span><button className="text-button" disabled={!!busy || history.page * history.page_size >= history.total} onClick={() => void historyPage(history.page + 1)}>Older packs</button></div></details>}
    {deleting && <Dialog title="Delete this application pack?" description="All drafts and approved versions in this pack will be permanently removed." onClose={() => { if (!busy) setDeleting(false); }}><div className="form-body"><p>The original CV, saved profile and job are kept.</p>{dirty && <p className="form-error">Your unsaved changes will also be discarded.</p>}{error && <p className="form-error" role="alert">{error}</p>}</div><footer className="dialog-footer"><button className="secondary-button" autoFocus disabled={!!busy} onClick={() => setDeleting(false)}>Keep pack</button><button className="danger-button" disabled={!!busy} onClick={() => void remove()}>{busy === 'delete' ? 'Deleting…' : 'Delete pack'}</button></footer></Dialog>}
    {approving && currentVersion && <Dialog title={`Approve version ${currentVersion.number}?`} description="Approval freezes the exact saved CV and cover letter shown in the previews." onClose={() => { if (!busy) setApproving(false); }}><div className="form-body"><p>Check the facts, contact details, projects, dates and wording in both documents. Source references do not guarantee accuracy.</p><label className="pack-confirm"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />I reviewed both documents and confirm their accuracy.</label>{error && <p className="form-error" role="alert">{error}</p>}</div><footer className="dialog-footer"><button className="secondary-button" disabled={!!busy} onClick={() => setApproving(false)}>Keep reviewing</button><button className="primary-button" disabled={!!busy || !checked} onClick={() => void approve()}>{busy === 'approve' ? 'Approving…' : 'Confirm approval'}</button></footer></Dialog>}
    {leaveAction && <Dialog title="Discard unsaved changes?" description="Your last saved documents and approved versions will remain available." onClose={() => setLeaveAction(null)}><div className="form-body"><p>Save both drafts first if you want to keep these edits.</p></div><footer className="dialog-footer"><button className="secondary-button" autoFocus onClick={() => setLeaveAction(null)}>Keep editing</button><button className="danger-button" onClick={() => { const action = leaveAction; setLeaveAction(null); setDocuments(saved); action(); }}>Discard changes</button></footer></Dialog>}
  </section>;
}
