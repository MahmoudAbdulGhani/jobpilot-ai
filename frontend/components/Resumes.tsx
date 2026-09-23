'use client';
import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle,
  DownloadSimple,
  FileDoc,
  FilePdf,
  FileText,
  PencilSimple,
  Star,
  Sparkle,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react';
import { api, downloadResume } from '../lib/api';
import { Dialog } from './Dialog';
import type { ProfileSuggestionSet, Resume, ResumeExtraction, ResumeList } from '../lib/types';

type PageState = 'loading' | 'ready' | 'error';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function ResumesView() {
  const [items, setItems] = useState<Resume[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [uploading, setUploading] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Resume | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Resume | null>(null);
  const [reviewTarget, setReviewTarget] = useState<Resume | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setState('loading');
    setLoadError('');
    try {
      const { items: loaded } = await api<ResumeList>('/resumes');
      setItems(loaded);
      setState('ready');
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not load your resumes.');
      setState('error');
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleUpload(file: File) {
    setUploading(true);
    setActionError('');
    setNotice('');
    const body = new FormData();
    body.append('file', file);
    try {
      await api<Resume>('/resumes', { method: 'POST', body });
      await load();
      setNotice('Resume uploaded.');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not upload the resume.');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDownload(resume: Resume) {
    setActionError('');
    try {
      const blob = await downloadResume(`/resumes/${resume.id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = resume.original_filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch {
      setActionError('Could not download the resume.');
    }
  }

  async function makePrimary(resume: Resume) {
    setActionError('');
    try {
      const updated = await api<Resume>(`/resumes/${resume.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_primary: true }),
      });
      setItems(current => current.map(item => (item.id === updated.id ? updated : { ...item, is_primary: false })));
      setNotice('Primary resume updated.');
    } catch {
      setActionError('Could not update the primary resume.');
    }
  }

  async function saveRename(displayName: string) {
    if (!renameTarget) return;
    setActionError('');
    const updated = await api<Resume>(`/resumes/${renameTarget.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName }),
    });
    setItems(current => current.map(item => (item.id === updated.id ? updated : item)));
    setRenameTarget(null);
    setNotice('Resume renamed.');
  }

  async function deleteResume() {
    if (!deleteTarget) return;
    setActionError('');
    await api(`/resumes/${deleteTarget.id}`, { method: 'DELETE' });
    setItems(current => current.filter(item => item.id !== deleteTarget.id));
    setDeleteTarget(null);
    setNotice('Resume deleted.');
  }

  if (state === 'loading') {
    return <div className="center-state">Loading resumes…</div>;
  }

  if (state === 'error') {
    return (
      <div className="center-state">
        <h1>Resumes unavailable</h1>
        <p className="muted">{loadError}</p>
        <button className="primary-button" onClick={() => void load()}>Try again</button>
      </div>
    );
  }

  const uploadButton = (
    <button className="primary-button" disabled={uploading} onClick={() => fileRef.current?.click()}>
      <UploadSimple size={19} />{uploading ? 'Uploading…' : 'Upload resume'}
    </button>
  );

  return (
    <div className="collection-page">
      <header className="collection-heading">
        <div>
          <p className="eyebrow">Resume library</p>
          <h1>Your resumes</h1>
          <p className="collection-subtitle">Keep your recent CVs here. Only you can view or download them.</p>
        </div>
        <div className="resume-upload-wrap">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden-file-input"
            data-testid="resume-file-input"
            onChange={event => {
              const file = event.target.files?.[0];
              if (file) void handleUpload(file);
            }}
          />
          {uploadButton}
          {actionError && <p className="form-error upload-error" role="alert">{actionError}</p>}
        </div>
      </header>
      {notice && <p className="notice" role="status"><CheckCircle size={19} />{notice}</p>}
      {items.length === 0 ? (
        <div className="empty-state">
          <FilePdf size={56} />
          <h2>No resumes yet</h2>
          <p>Upload a PDF or DOCX resume. Each file is stored privately and only you can download it.</p>
          <button className="primary-button" onClick={() => fileRef.current?.click()}><UploadSimple size={19} />Upload your first resume</button>
        </div>
      ) : (
        <ul className="resume-list">
          {items.map(resume => (
            <li className="resume-card" key={resume.id}>
              <span className={`resume-icon ${resume.file_extension === 'docx' ? 'is-docx' : ''}`} aria-hidden="true">
                {resume.file_extension === 'docx' ? <FileDoc size={30} weight="duotone" /> : <FilePdf size={30} weight="duotone" />}
              </span>
              <div className="resume-info">
                <div className="resume-name-line">
                  <strong>{resume.display_name}</strong>
                  {resume.is_primary && <span className="primary-badge">Primary</span>}
                </div>
                <p className="muted">
                  {resume.original_filename} · {formatBytes(resume.size_bytes)} · {formatDate(resume.created_at)}
                </p>
              </div>
              <div className="resume-actions">
                {!resume.is_primary && (
                  <button className="action-button" onClick={() => void makePrimary(resume)} title="Make primary resume">
                    <Star size={20} />Make primary
                  </button>
                )}
                <button className="action-button" onClick={() => { setActionError(''); setReviewTarget(resume); }} title="Extract and review text">
                  <FileText size={20} />Extract text
                </button>
                <button className="action-button" onClick={() => void handleDownload(resume)} title="Download">
                  <DownloadSimple size={20} />Download
                </button>
                <button className="action-button" onClick={() => { setActionError(''); setRenameTarget(resume); }} title="Rename">
                  <PencilSimple size={20} />Rename
                </button>
                <button className="action-button danger-action" onClick={() => { setActionError(''); setDeleteTarget(resume); }} title="Delete">
                  <Trash size={20} />Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {renameTarget && (
        <RenameDialog resume={renameTarget} onClose={() => setRenameTarget(null)} onSave={saveRename} />
      )}
      {deleteTarget && (
        <DeleteResumeDialog resume={deleteTarget} onClose={() => setDeleteTarget(null)} onDelete={deleteResume} />
      )}
      {reviewTarget && (
        <ExtractionDialog key={reviewTarget.id} resume={reviewTarget} onClose={() => setReviewTarget(null)} />
      )}
    </div>
  );
}

function ExtractionDialog({ resume, onClose }: { resume: Resume; onClose: () => void }) {
  const [extraction, setExtraction] = useState<ResumeExtraction | null>(null);
  const [draft, setDraft] = useState('');
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [suggestionSet, setSuggestionSet] = useState<ProfileSuggestionSet | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [suggestionDrafts, setSuggestionDrafts] = useState<Record<string, string>>({});
  const [aiError, setAiError] = useState('');

function adoptSuggestions(result: ProfileSuggestionSet) {
    if (result.resume_id !== resume.id) return;
    setSuggestionSet(result);
    const suggestions = result.suggestions || [];
    const proposed = suggestions.filter(item => item.status !== 'not_found');
    setSelected(new Set(proposed.map(item => item.id)));
    setSuggestionDrafts(Object.fromEntries(proposed.map(item => [
      item.id,
      typeof item.value === 'string' ? item.value : JSON.stringify(item.value, null, 2),
    ])));
  }

  async function refreshLatest() {
    try {
      adoptSuggestions(await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`));
    } catch {
      // Keep whatever is already displayed; the reported error stays primary.
    }
  }

  async function loadLatest() {
    try {
      adoptSuggestions(await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`));
    } catch (cause) {
      if ((cause as { status?: number }).status !== 404) setAiError(cause instanceof Error ? cause.message : 'Could not load suggestions.');
    }
  }

  async function extract() {
    setPending(true);
    setState('loading');
    setError('');
    try {
      const result = await api<ResumeExtraction>(`/resumes/${resume.id}/extract`, { method: 'POST' });
      setExtraction(result);
      setDraft(result.draft_text || '');
      setState('ready');
      if (result.reviewed_at) await loadLatest();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not extract this resume.');
      setState('error');
    } finally {
      setPending(false);
    }
  }

  useEffect(() => { void extract(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (!draft.trim()) {
      setError('Extracted text cannot be empty.');
      return;
    }
    setPending(true);
    setError('');
    try {
      const result = await api<ResumeExtraction>(`/resumes/${resume.id}/extraction`, {
        method: 'PATCH',
        body: JSON.stringify({ draft_text: draft }),
      });
      setExtraction(result);
      setDraft(result.draft_text || '');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the extracted text.');
    } finally {
      setPending(false);
    }
  }

  async function confirm() {
    setPending(true);
    setError('');
    try {
      const result = await api<ResumeExtraction>(`/resumes/${resume.id}/extraction/confirm`, { method: 'POST' });
      setExtraction(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not confirm the extracted text.');
    } finally {
      setPending(false);
    }
  }

  async function generateSuggestions() {
    if (pending) return;
    setPending(true);
    setAiError('');
    try {
      let result = await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}`, { method: 'POST' });
      adoptSuggestions(result);
      for (let attempt = 0; result.status === 'generating' && attempt < 90; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 1000));
        result = await api<ProfileSuggestionSet>(`/profile-suggestions/resumes/${resume.id}/latest`);
        adoptSuggestions(result);
      }
      if (result.status === 'generating') throw new Error('Profile suggestions are still processing.');
    } catch (cause) {
      setAiError(cause instanceof Error ? cause.message : 'Could not generate profile suggestions.');
      await refreshLatest();
    } finally {
      setPending(false);
    }
  }

  async function applySuggestions() {
    if (!suggestionSet) return;
    setPending(true);
    setAiError('');
    try {
      const stringFields = new Set(['headline', 'location', 'target_roles', 'remote_preference', 'work_authorization']);
      const selections = (suggestionSet.suggestions || []).filter(item => item.status !== 'not_found' && selected.has(item.id)).map(item => ({
        ...item,
        value: stringFields.has(item.field)
          ? suggestionDrafts[item.id]
          : JSON.parse(suggestionDrafts[item.id]),
      }));
      adoptSuggestions(await api<ProfileSuggestionSet>(`/profile-suggestions/${suggestionSet.id}/apply`, {
        method: 'POST', body: JSON.stringify({ selections }),
      }));
    } catch (cause) {
      setAiError(cause instanceof Error ? cause.message : 'Could not apply the selected changes.');
    } finally {
      setPending(false);
    }
  }

  const savedDraft = extraction?.draft_text || '';
  const hasUnsavedChanges = draft !== savedDraft;
  const isConfirmed = Boolean(extraction?.reviewed_at) && !hasUnsavedChanges;

  return (
    <Dialog title="Review extracted text" description={resume.display_name} onClose={onClose}>
      <div className="extraction-body">
        {state === 'loading' && <div className="extraction-state" role="status">Extracting text locally…</div>}
        {state === 'error' && (
          <div className="extraction-state">
            <p className="form-error" role="alert">{error}</p>
            <button className="secondary-button" disabled={pending} onClick={() => void extract()}>Try again</button>
          </div>
        )}
        {state === 'ready' && extraction?.status === 'failed' && (
          <div className="extraction-state">
            <p className="status-badge is-unreviewed">Extraction failed</p>
            <p role="alert">{extraction.failure_message}</p>
            <button className="primary-button" disabled={pending} onClick={() => void extract()}>{pending ? 'Retrying…' : 'Retry extraction'}</button>
          </div>
        )}
        {state === 'ready' && extraction?.status === 'succeeded' && (
          <>
            <div className="extraction-summary">
              <span className={`status-badge ${isConfirmed ? 'is-confirmed' : 'is-unreviewed'}`}>
                {isConfirmed ? 'Confirmed' : hasUnsavedChanges ? 'Unsaved changes' : 'Needs review'}
              </span>
              <span className="muted">{extraction.parser_name} {extraction.parser_version}</span>
            </div>
            <label htmlFor="extracted_text">Extracted resume text</label>
            <p className="muted extraction-help">Check the reading order and correct any parsing mistakes. This does not change your uploaded file or candidate profile.</p>
            <textarea
              id="extracted_text"
              value={draft}
              onChange={event => setDraft(event.target.value)}
              rows={18}
              maxLength={200000}
            />
            {isConfirmed && (
              <section className="ai-suggestions">
                <h3><Sparkle size={20} />AI profile suggestions</h3>
                <p className="muted">Provider: OpenAI when configured. Your confirmed CV text will leave JobPilot only when you request generation. Review every fact and quote before applying.</p>
                {!suggestionSet && <button type="button" className="secondary-button" disabled={pending} aria-busy={pending} onClick={() => void generateSuggestions()}><Sparkle size={18} />{pending ? 'Generating…' : 'Suggest profile details with AI'}</button>}
                {suggestionSet?.status === 'failed' && <button type="button" className="secondary-button" disabled={pending} aria-busy={pending} onClick={() => void generateSuggestions()}>{pending ? 'Generating…' : 'Retry suggestions'}</button>}
                {suggestionSet?.suggestions?.map(item => item.status === 'not_found' ? (
                  <article className="suggestion-card" key={item.id}>
                    <strong>{item.field.replaceAll('_', ' ')}</strong>
                    <p className="muted">Not found in the confirmed CV.</p>
                  </article>
                ) : (
                  <article className="suggestion-card" key={item.id}>
                    <label className="suggestion-select"><input type="checkbox" checked={selected.has(item.id)} disabled={suggestionSet.status === 'applied'} onChange={() => setSelected(current => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next; })} />Use {item.field.replaceAll('_', ' ')}</label>
                    <textarea aria-label={`Proposed ${item.field}`} value={suggestionDrafts[item.id] || ''} disabled={suggestionSet.status === 'applied'} onChange={event => setSuggestionDrafts(current => ({ ...current, [item.id]: event.target.value }))} rows={3} />
                    {item.evidence.map((evidence, index) => <blockquote key={index}>&ldquo;{evidence.quote}&rdquo;</blockquote>)}
                  </article>
                ))}
                {suggestionSet?.outcome_message && <p className="muted">{suggestionSet.outcome_message}{suggestionSet.failure_field ? ` · ${suggestionSet.failure_field}` : ''}</p>}
                {suggestionSet?.status === 'ready' && <button className="primary-button" disabled={pending || selected.size === 0} onClick={() => void applySuggestions()}>{pending ? 'Applying…' : 'Apply selected changes'}</button>}
                {suggestionSet?.status === 'applied' && <p className="profile-notice" role="status"><CheckCircle size={18} />Selected profile changes applied.</p>}
                {aiError && <p className="form-error" role="alert">{aiError}</p>}
              </section>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
          </>
        )}
      </div>
      {state === 'ready' && extraction?.status === 'succeeded' && (
        <footer className="dialog-footer extraction-footer">
          <button className="secondary-button" onClick={onClose}>Close</button>
          <button className="secondary-button" disabled={pending || !hasUnsavedChanges || !draft.trim()} onClick={() => void save()}>
            {pending ? 'Saving…' : 'Save changes'}
          </button>
          <button className="primary-button" disabled={pending || hasUnsavedChanges || isConfirmed} onClick={() => void confirm()}>
            <CheckCircle size={19} />{isConfirmed ? 'Confirmed' : 'Confirm text'}
          </button>
        </footer>
      )}
    </Dialog>
  );
}

function RenameDialog({ resume, onClose, onSave }: { resume: Resume; onClose: () => void; onSave: (displayName: string) => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  return (
    <Dialog title="Rename resume" description={resume.display_name} onClose={onClose}>
      <form onSubmit={async (event) => {
        event.preventDefault();
        if (pending) return;
        const value = String(new FormData(event.currentTarget).get('display_name') || '').trim();
        if (!value) {
          setError('Give the resume a name.');
          return;
        }
        setPending(true);
        setError('');
        try {
          await onSave(value);
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Could not rename the resume.');
          setPending(false);
        }
      }}>
        <div className="form-body">
          <label htmlFor="display_name">Display name</label>
          <input id="display_name" name="display_name" defaultValue={resume.display_name} maxLength={255} autoFocus />
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
        <footer className="dialog-footer">
          <button type="button" className="secondary-button" onClick={onClose}>Cancel</button>
          <button className="primary-button" disabled={pending}>{pending ? 'Saving…' : 'Save name'}</button>
        </footer>
      </form>
    </Dialog>
  );
}

function DeleteResumeDialog({ resume, onClose, onDelete }: { resume: Resume; onClose: () => void; onDelete: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  return (
    <Dialog title="Delete this resume?" description={resume.display_name} onClose={onClose}>
      <div className="form-body">
        <p>&ldquo;{resume.display_name}&rdquo; and its stored file will be permanently removed.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
      <footer className="dialog-footer">
        <button autoFocus className="secondary-button" onClick={onClose}>Keep resume</button>
        <button disabled={pending} className="danger-button" onClick={async () => {
          setPending(true);
          try {
            await onDelete();
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not delete resume');
            setPending(false);
          }
        }}><Trash size={19} />{pending ? 'Deleting…' : 'Delete resume'}</button>
      </footer>
    </Dialog>
  );
}
