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
  Trash,
  UploadSimple,
} from '@phosphor-icons/react';
import { api, downloadResume } from '../lib/api';
import { Dialog } from './Dialog';
import type { Resume, ResumeExtraction, ResumeList } from '../lib/types';

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
        <ExtractionDialog resume={reviewTarget} onClose={() => setReviewTarget(null)} />
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

  async function extract() {
    setPending(true);
    setState('loading');
    setError('');
    try {
      const result = await api<ResumeExtraction>(`/resumes/${resume.id}/extract`, { method: 'POST' });
      setExtraction(result);
      setDraft(result.draft_text || '');
      setState('ready');
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
