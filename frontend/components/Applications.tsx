'use client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { CalendarBlank, ArrowSquareOut } from '@phosphor-icons/react';
import { api } from '../lib/api';
import type { ApplicationRecordList, ApplicationStatus, ApplicationTimeline, TimelineKind } from '../lib/types';

const STATUSES: Array<ApplicationStatus | 'All'> = ['All', 'Applied', 'Interview', 'Offer', 'Accepted', 'Rejected', 'Withdrawn'];

const KIND_LABEL: Record<TimelineKind, string> = {
  submitted: 'Submitted', status: 'Status change', reply: 'Reply', followup: 'Follow-up', email: 'Email',
};

export function Applications() {
  const [data, setData] = useState<ApplicationRecordList | null>(null);
  const [status, setStatus] = useState<ApplicationStatus | 'All'>('All');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [timelines, setTimelines] = useState<Record<string, ApplicationTimeline>>({});
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [timelineError, setTimelineError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const query = new URLSearchParams({ page: '1', page_size: '50' });
      if (status !== 'All') query.set('status', status);
      const list = await api<ApplicationRecordList>(`/applications?${query}`);
      setData(list);
    } catch (e) {
      setError((e as Error).message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  const toggleTimeline = useCallback(async (item: { id: string; job_id: string }) => {
    const key = item.id;
    const next = new Set(open);
    if (next.has(key)) {
      next.delete(key);
      setOpen(next);
      return;
    }
    setTimelineError('');
    setOpen(new Set(next).add(key));
    if (!timelines[key]) {
      try {
        const timeline = await api<ApplicationTimeline>(`/jobs/${item.job_id}/applications/${key}/timeline`);
        setTimelines(prev => ({ ...prev, [key]: timeline }));
      } catch (e) {
        setTimelineError((e as Error).message);
      }
    }
  }, [open, timelines]);

  return <section className="applications-page">
    <div className="section-title">
      <div>
        <p className="eyebrow">Private applications</p>
        <h1>Applications</h1>
      </div>
      <div className="filter-row">
        <label><span className="sr-only">Status filter</span><select value={status} onChange={e => setStatus(e.target.value as ApplicationStatus | 'All')}>
          {STATUSES.map(item => <option value={item} key={item}>{item === 'All' ? 'All statuses' : item}</option>)}
        </select></label>
      </div>
    </div>

    {error && <p className="notice form-error" role="alert">{error}</p>}
    {loading && <p className="notice">Loading applications…</p>}
    {!loading && !error && (!data || data.total === 0) && <p className="notice empty-state">No applications yet.</p>}

    {data && data.total > 0 && <div className="application-list">
      {data.items.map((item) => <article className="application-row" key={item.id}>
        <div className="application-main">
          <div className="application-row-top">
            <span className={`status-badge is-${item.status.toLowerCase()}`}>{item.status}</span>
            <span className="method-label">{item.method}</span>
            <span className="origin-label" title={item.origin === 'email_confirmed' ? 'Created from a Gmail message you approved and synchronized' : 'Recorded by hand; no email was sent for this record'}>{item.origin === 'email_confirmed' ? 'Email-confirmed' : 'Manual record'}</span>
            {item.follow_up_date && <span className="followup-label"><CalendarBlank size={16}/>{item.reminder_status === 'completed' || item.reminder_status === 'cancelled' ? `Reminder ${item.reminder_status}` : `Follow up ${new Date(item.follow_up_date).toLocaleString(undefined, {timeZone:item.reminder_timezone || 'UTC'})} (${item.reminder_timezone || 'UTC'})`}</span>}
          </div>
          <div className="application-row-meta">
            <span><strong>Submitted:</strong> {new Date(item.submission_date).toLocaleDateString()}</span>
            <span><strong>Notes:</strong> {item.notes || '—'}</span>
          </div>
          <div className="application-row-links">
            <Link className="text-button" href={`/jobs/${item.job_id}`}>Open saved job <ArrowSquareOut size={16}/></Link>
            <button className="text-button" onClick={() => void toggleTimeline(item)}>{open.has(item.id) ? 'Hide timeline' : 'Show timeline'}</button>
          </div>
          {timelineError && open.has(item.id) && <p className="notice form-error" role="alert">{timelineError}</p>}
          {open.has(item.id) && <div className="application-timeline" aria-label={`Timeline for application ${item.id}`}>
            <p className="muted">{timelines[item.id]?.narrative || 'Loading timeline…'}</p>
            {timelines[item.id] && <ol className="timeline-list">
              {timelines[item.id].entries.map((entry, index) => <li key={`${entry.at}-${index}`} className={`timeline-entry is-${entry.kind}`}>
                <p className="timeline-kind">{KIND_LABEL[entry.kind]} <span className="muted">· {new Date(entry.at).toLocaleString()}</span></p>
                <p><strong>{entry.title}</strong></p>
                {entry.detail && <p className="muted">{entry.detail}</p>}
                {entry.evidence.length > 0 && <ul className="muted">{entry.evidence.map((line, i) => <li key={i}>{line}</li>)}</ul>}
              </li>)}
            </ol>}
          </div>}
        </div>
      </article>)}
    </div>}
  </section>;
}
