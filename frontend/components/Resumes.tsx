'use client';
import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  CheckCircle,
  DownloadSimple,
  FileDoc,
  FilePdf,
  FileText,
  PencilSimple,
  ShieldCheck,
  Star,
  Sparkle,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react';
import { api, downloadResume } from '../lib/api';
import { ProfileSuggestionsPanel } from './ProfileSuggestionsPanel';
import { Dialog } from './Dialog';
import { PageHeader } from './ui/page-header';
import '../app/resume-profile.css';
import type { Resume, ResumeExtraction, ResumeList } from '../lib/types';

type ReviewedResume = Resume & { extraction?: ResumeExtraction | null };

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
  const [items, setItems] = useState<ReviewedResume[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [busyResume, setBusyResume] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<Resume | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Resume | null>(null);
  const [reviewTarget, setReviewTarget] = useState<Resume | null>(null);
  const confirmedResumeIds = new Set(items.filter(item => item.extraction?.reviewed_at).map(item => item.id));
  const reads = useRef<AbortController | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    reads.current?.abort();
    const controller = new AbortController();
    reads.current = controller;
    setState('loading');
    setLoadError('');
    try {
      const { items: loaded } = await api<ResumeList>('/resumes');
      if (controller.signal.aborted) return;
      setItems(loaded);
      setState('ready');
      // Resume metadata does not include extraction state. Read persisted reviews
      // separately; never start extraction or AI work while opening the library.
      for (const resume of loaded) {
        void Promise.resolve(api<ResumeExtraction>(`/resumes/${resume.id}/extraction`, { signal: controller.signal })).then(result => {
          if (controller.signal.aborted || !result || result.resume_id !== resume.id) return;
          setItems(current => current.map(item => item.id === resume.id ? { ...item, extraction: result } : item));
        }).catch(() => { /* Unextracted documents return 404; review offers explicit recovery. */ });
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not load your resumes.');
      setState('error');
    }
  }

  useEffect(() => { void load(); return () => reads.current?.abort(); }, []);

  async function handleUpload(file: File) {
    if (uploading) return;
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
    setBusyResume(resume.id);
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
    } finally {
      setBusyResume(null);
    }
  }

  async function makePrimary(resume: Resume) {
    setBusyResume(resume.id);
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
    } finally {
      setBusyResume(null);
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
    return <div className="app-page resume-workspace"><PageHeader eyebrow="Your career toolkit" title="Your resumes" subtitle="The right version, ready for your next opportunity." /><div className="rp-loading" role="status"><span className="rp-loading-dot" />Loading resumes…</div></div>;
  }

  if (state === 'error') {
    return (
      <div className="center-state rp-error-state">
        <FileText size={36} />
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
    <div className="app-page resume-workspace">
      <PageHeader eyebrow="Your career toolkit" title="Your resumes" subtitle="The right version, ready for your next opportunity." actions={uploadButton} />
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            aria-label="Upload a PDF or DOCX resume"
            className="hidden-file-input"
            data-testid="resume-file-input"
            onChange={event => {
              const file = event.target.files?.[0];
              if (file) void handleUpload(file);
            }}
          />
      {actionError && <p className="form-error upload-error" role="alert">{actionError}</p>}
      {notice && <p className="notice" role="status"><CheckCircle size={19} />{notice}</p>}
      <div className="resume-workspace-layout">
      <div className="resume-library">
      <section
        className={`resume-dropzone ${dragging ? 'is-dragging' : ''} ${uploading ? 'is-uploading' : ''}`}
        aria-label="Resume upload"
        onDragOver={event => { event.preventDefault(); if (!uploading) setDragging(true); }}
        onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={event => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file && !uploading) void handleUpload(file); }}
      >
        <span className="resume-drop-icon"><UploadSimple size={25} /></span>
        <div><h2>{uploading ? 'Adding your resume…' : 'A new opportunity starts here'}</h2><p>Drag a resume here, or <button type="button" disabled={uploading} onClick={() => fileRef.current?.click()}>browse files</button></p><span className="resume-format-note">PDF or DOCX · Your original file stays intact</span></div>
      </section>
      <div className="resume-library-heading"><h2>Document library <span>{items.length}</span></h2><span>Private to you <ShieldCheck size={15} /></span></div>
      {items.length === 0 ? (
        <div className="empty-state resume-empty">
          <div className="resume-empty-icon"><FileText size={34} weight="duotone" /></div>
          <h2>No resumes yet</h2>
          <p>Keep your career story in one place. Add your first resume to organize versions and prepare your profile.</p>
          <button className="primary-button" disabled={uploading} onClick={() => fileRef.current?.click()}><UploadSimple size={18} />Upload your first resume</button>
        </div>
      ) : (
        <ul className="resume-list">
          {items.map(resume => (
            <li className={`resume-card ${resume.is_primary ? 'resume-card-primary' : ''}`} key={resume.id}>
              <div className="resume-document-row">
              <span className={`resume-icon ${resume.file_extension === 'docx' ? 'is-docx' : ''}`} aria-hidden="true">
                {resume.file_extension === 'docx' ? <FileDoc size={30} weight="duotone" /> : <FilePdf size={30} weight="duotone" />}
              </span>
              <div className="resume-info">
                <div className="resume-name-line">
                  <strong>{resume.display_name}</strong>
                  {resume.is_primary && <span className="primary-badge"><Star size={11} weight="fill" />Primary</span>}
                </div>
                <p className="muted">
                  {resume.original_filename}
                </p>
                <div className="resume-file-facts"><span>{resume.file_extension.toUpperCase()}</span><span>{formatBytes(resume.size_bytes)}</span><span>Added {formatDate(resume.created_at)}</span></div>
              </div>
              </div>
              <div className="resume-card-toolbar">
              <span className={`resume-review-state ${confirmedResumeIds.has(resume.id) ? 'is-reviewed' : ''}`}><span />{confirmedResumeIds.has(resume.id) ? 'Text reviewed' : 'Ready to review'}</span>
              <div className="resume-actions">
                {!resume.is_primary && (
                  <button className="action-button" disabled={busyResume === resume.id} onClick={() => void makePrimary(resume)} title="Make primary resume">
                    <Star size={16} />Make primary
                  </button>
                )}
                <button className="action-button" onClick={() => { setActionError(''); setReviewTarget(resume); }} title="Extract and review text">
                  <FileText size={16} />Extract text
                </button>
                <button className="action-button resume-icon-action" disabled={busyResume === resume.id} onClick={() => void handleDownload(resume)} title="Download" aria-label={`Download ${resume.display_name}`}>
                  <DownloadSimple size={17} /><span>Download</span>
                </button>
                <button className="action-button resume-icon-action" onClick={() => { setActionError(''); setRenameTarget(resume); }} title="Rename" aria-label={`Rename ${resume.display_name}`}>
                  <PencilSimple size={17} /><span>Rename</span>
                </button>
                <button className="action-button danger-action resume-icon-action" onClick={() => { setActionError(''); setDeleteTarget(resume); }} title="Delete" aria-label={`Delete ${resume.display_name}`}>
                  <Trash size={17} /><span>Delete</span>
                </button>
              </div>
              </div>
              <ProfileSuggestionsPanel resume={resume} enabled={confirmedResumeIds.has(resume.id) || Boolean(resume.extraction?.reviewed_at)} />
            </li>
          ))}
        </ul>
      )}
      </div>
      <aside className="resume-guide">
        <div className="resume-guide-heading"><span className="rp-icon-tile"><Sparkle size={21} /></span><p className="eyebrow">A little less admin</p><h2>Let your resume do the groundwork.</h2><p>Turn the experience you already have into a profile you can build on.</p></div>
        <ol className="resume-steps"><li><span>01</span><div><h3>Upload your resume</h3><p>Keep a master copy and versions for different roles.</p></div></li><li><span>02</span><div><h3>Review the text</h3><p>Extract your resume and check every detail before confirming.</p></div></li><li><span>03</span><div><h3>Shape your profile</h3><p>Request AI suggestions, then choose which details to apply.</p></div></li></ol>
        <a href="/profile" className="resume-profile-link">Go to your profile <ArrowRight size={17} /></a>
        <div className="resume-privacy-note"><ShieldCheck size={19} /><p>You stay in control. AI suggestions run only when you request them, with your consent.</p></div>
      </aside>
      </div>
      {renameTarget && (
        <RenameDialog resume={renameTarget} onClose={() => setRenameTarget(null)} onSave={saveRename} />
      )}
      {deleteTarget && (
        <DeleteResumeDialog resume={deleteTarget} onClose={() => setDeleteTarget(null)} onDelete={deleteResume} />
      )}
        {reviewTarget && (
          <ExtractionDialog
            key={reviewTarget.id}
            resume={reviewTarget}
            onClose={() => setReviewTarget(null)}
            onConfirmed={(result) => {
              // Retain the complete server response, including its review provenance.
              setItems(current => current.map(item => item.id === reviewTarget.id
                ? { ...item, extraction: result }
                : item));
            }}
          />
        )}
    </div>
  );
}

function ExtractionDialog({ resume, onClose, onConfirmed }: { resume: Resume; onClose: () => void; onConfirmed: (result: ResumeExtraction) => void }) {
  const [extraction, setExtraction] = useState<ResumeExtraction | null>(null);
  const [draft, setDraft] = useState('');
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function extract(retry = false) {
    setPending(true);
    setState('loading');
    setError('');
    try {
      let result: ResumeExtraction;
      try {
        result = await api<ResumeExtraction>(`/resumes/${resume.id}/${retry ? 'extract' : 'extraction'}`, retry ? { method: 'POST' } : undefined);
      } catch (cause) {
        if (!retry && (cause as { status?: number }).status === 404) result = await api<ResumeExtraction>(`/resumes/${resume.id}/extract`, { method: 'POST' });
        else throw cause;
      }
      setExtraction(result);
      setDraft(result.draft_text || '');
      setState('ready');
      onConfirmed(result);
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
      onConfirmed(result);
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
      onConfirmed(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not confirm the extracted text.');
    } finally {
      setPending(false);
    }
  }


  const savedDraft = extraction?.draft_text || '';
  const hasUnsavedChanges = draft !== savedDraft;
  const isConfirmed = Boolean(extraction?.reviewed_at) && !hasUnsavedChanges;

  return (
    <Dialog title="Review extracted text" description={resume.display_name} onClose={onClose} dirty={hasUnsavedChanges}>
      <div className="extraction-body">
        {state === 'loading' && <div className="extraction-state" role="status">Extracting text locally…</div>}
        {state === 'error' && (
          <div className="extraction-state">
            <p className="form-error" role="alert">{error}</p>
            <button className="secondary-button" disabled={pending} onClick={() => void extract(true)}>Try again</button>
          </div>
        )}
        {state === 'ready' && extraction?.status === 'failed' && (
          <div className="extraction-state">
            <p className="status-badge is-unreviewed">Extraction failed</p>
            <p role="alert">{extraction.failure_message}</p>
            <button className="primary-button" disabled={pending} onClick={() => void extract(true)}>{pending ? 'Retrying…' : 'Retry extraction'}</button>
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
            {extraction.original_text && <details className="extraction-original"><summary>Original extracted text</summary><p className="muted">The initial extraction is kept separately from your editable draft. Your uploaded file stays unchanged.</p><pre className="preserve-lines">{extraction.original_text}</pre></details>}
            <label htmlFor="extracted_text">Extracted resume text</label>
            <p className="muted extraction-help">Check the reading order and correct any parsing mistakes. This does not change your uploaded file or candidate profile.</p>
            <textarea
              id="extracted_text"
              value={draft}
              onChange={event => setDraft(event.target.value)}
              rows={18}
              maxLength={200000}
            />
            {error && <p className="form-error" role="alert">{error}</p>}
          </>
        )}
      </div>
      {state === 'ready' && extraction?.status === 'succeeded' && (
        <footer className="dialog-footer extraction-footer">
          <p className="muted"><CheckCircle size={16} /> Confirmed CV text is sent only when you request suggestions. Review every extracted fact and quote before confirming.</p>
          <button className="secondary-button" data-dialog-dismiss onClick={onClose}>Close</button>
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
