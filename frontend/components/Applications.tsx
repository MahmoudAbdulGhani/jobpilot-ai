'use client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { CalendarBlank, ArrowSquareOut } from '@phosphor-icons/react';
import { api } from '../lib/api';
import type { ApplicationRecordList, ApplicationStatus } from '../lib/types';

const STATUSES: Array<ApplicationStatus | 'All'> = ['All', 'Applied', 'Interview', 'Offer', 'Rejected', 'Withdrawn'];

export function Applications() {
  const [data, setData] = useState<ApplicationRecordList | null>(null);
  const [status, setStatus] = useState<ApplicationStatus | 'All'>('All');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

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
            <span className="status-badge status-${item.status}">{item.status}</span>
            <span className="method-label">{item.method}</span>
            {item.follow_up_date && <span className="followup-label"><CalendarBlank size={16}/>Follow up {new Date(item.follow_up_date).toLocaleDateString()}</span>}
          </div>
          <div className="application-row-meta">
            <span><strong>Submitted:</strong> {new Date(item.submission_date).toLocaleDateString()}</span>
            <span><strong>Notes:</strong> {item.notes || '—'}</span>
          </div>
          <div className="application-row-links">
            <Link className="text-button" href={`/jobs/${item.job_id}`}>Open saved job <ArrowSquareOut size={16}/></Link>
          </div>
        </div>
      </article>)}
    </div>}
  </section>;
}
