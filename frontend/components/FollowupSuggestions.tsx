'use client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { FollowupSuggestion, FollowupSuggestionList } from '../lib/types';

export function FollowupSuggestions() {
  const [data, setData] = useState<FollowupSuggestionList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api<FollowupSuggestionList>('/followup-suggestions?state=suggested&page=1&page_size=20'));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function generate() {
    setBusy(true);
    setError('');
    try {
      await api<FollowupSuggestion[]>('/followup-suggestions/generate', { method: 'POST' });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(item: FollowupSuggestion, action: 'approve' | 'reject') {
    setBusy(true);
    setError('');
    try {
      await api(`/followup-suggestions/${item.id}/${action}`, { method: 'POST', body: JSON.stringify({ confirm: true }) });
      await load();
      window.dispatchEvent(new Event('reminders-changed'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="suggestions-panel" aria-label="Follow-up suggestions">
    <div className="section-title">
      <div>
        <p className="eyebrow">Assistance</p>
        <h2>Suggested follow-ups</h2>
        <p className="muted">Drafts from application age and reply state. Nothing is created or sent until you approve. Message drafts are for you to copy and send yourself.</p>
      </div>
      <button className="primary-button" disabled={busy} onClick={() => void generate()}>{busy ? 'Working…' : 'Suggest follow-ups'}</button>
    </div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {data && data.items.length === 0 && <p className="notice empty-state">No open suggestions.</p>}
    {data && data.items.length > 0 && <ul className="suggestion-list">
      {data.items.map(item => <li key={item.id} className="mailbox-card">
        <p><strong>{item.kind === 'reminder' ? 'Reminder suggestion' : 'Follow-up message draft'}</strong>
          {item.job_title && <> for <Link href={`/jobs/${item.job_id}`}>{item.job_title} · {item.company}</Link></>}</p>
        <p className="muted">{item.reason}</p>
        {item.suggested_due_at && <p>Suggested time: <time dateTime={item.suggested_due_at}>{new Date(item.suggested_due_at).toLocaleString()} (UTC)</time></p>}
        {item.draft_message && <p className="preserve-lines">{item.draft_message}</p>}
        <button disabled={busy} onClick={() => void decide(item, 'approve')}>{item.kind === 'reminder' ? 'Approve and create reminder' : 'Approve draft'}</button>
        <button disabled={busy} onClick={() => void decide(item, 'reject')}>Reject suggestion</button>
      </li>)}
    </ul>}
  </section>;
}
