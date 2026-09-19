'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { ReplyClassification } from '../lib/types';

const STATUSES = ['Applied', 'Interview', 'Offer', 'Accepted', 'Rejected', 'Withdrawn'];

export function ReplyClassificationPanel({ replyId, jobId }: { replyId: string; jobId: string | null }) {
  const [result, setResult] = useState<ReplyClassification | null>(null);
  const [status, setStatus] = useState('Interview');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api<ReplyClassification | null>(`/replies/${replyId}/classification`)
      .then(value => { if (active) { setResult(value); if (value?.suggested_status) setStatus(value.suggested_status); } })
      .catch(() => { if (active) setResult(null); });
    return () => { active = false; };
  }, [replyId]);

  async function classify() {
    setBusy(true);
    setError('');
    try {
      const created = await api<ReplyClassification>(`/replies/${replyId}/classification`, { method: 'POST' });
      setResult(created);
      if (created.suggested_status) setStatus(created.suggested_status);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    setError('');
    try {
      const updated = await api<ReplyClassification>(`/replies/${replyId}/classification/confirm`, {
        method: 'POST', body: JSON.stringify({ confirm: true, status }),
      });
      setResult(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="reply-classification">
    <button disabled={busy} onClick={() => void classify()}>Classify reply</button>
    {error && <p role="alert">{error}</p>}
    {result && <div>
      <p><strong>Classification:</strong> {result.category} <span className="muted">(confidence {result.confidence}/100)</span></p>
      <p className="muted">Evidence: “{result.evidence_excerpt || 'none'}”</p>
      <p className="muted">{result.uncertainty}</p>
      {result.suggested_status && !result.status_applied && <p>Suggested status: {result.suggested_status}. Nothing changed yet.</p>}
      {result.status_applied && <p role="status">Status change applied: {result.applied_status}.</p>}
      {!result.status_applied && (jobId
        ? <label>Apply status to the linked application
          <select value={status} onChange={e => setStatus(e.target.value)}>
            {STATUSES.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        : <p className="muted">Associate the reply with a saved job that has an application record before confirming a status change.</p>)}
      {!result.status_applied && jobId && <button disabled={busy} onClick={() => void confirm()}>Confirm status change</button>}
    </div>}
  </div>;
}
