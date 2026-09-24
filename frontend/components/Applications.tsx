'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowClockwise, ArrowRight, ArrowSquareOut, Briefcase, CalendarBlank, CaretDown, CaretLeft, CaretRight, ClockCounterClockwise, FunnelSimple, LockSimple, Plus } from '@phosphor-icons/react';
import { PageHeader } from './ui/page-header';
import { api } from '../lib/api';
import type { ApplicationRecordList, ApplicationStatus, ApplicationTimeline, Job, TimelineKind } from '../lib/types';
import '../app/workflows.css';

const STATUSES: Array<ApplicationStatus | 'All'> = ['All', 'Applied', 'Interview', 'Offer', 'Accepted', 'Rejected', 'Withdrawn'];
const KIND_LABEL: Record<TimelineKind, string> = { submitted: 'Submitted', status: 'Status change', reply: 'Reply', followup: 'Follow-up', email: 'Email' };
const METHOD_LABEL: Record<string, string> = { email: 'Email', employer_website: 'Employer website', linkedin_manual: 'LinkedIn', other: 'Other' };

export function Applications() {
  const [data, setData] = useState<ApplicationRecordList | null>(null);
  const [status, setStatus] = useState<ApplicationStatus | 'All'>('All');
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const jobCache = useRef<Record<string, Job>>({});
  const [timelines, setTimelines] = useState<Record<string, ApplicationTimeline>>({});
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [timelineErrors, setTimelineErrors] = useState<Record<string, string>>({});
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestId.current;
    setLoading(true); setError('');
    try {
      const query = new URLSearchParams({ page: String(page), page_size: '20' });
      if (status !== 'All') query.set('status', status);
      const list = await api<ApplicationRecordList>(`/applications?${query}`);
      if (request === requestId.current) setData(list);
    } catch (caught) {
      if (request === requestId.current) { setError((caught as Error).message); setData(null); }
    } finally { if (request === requestId.current) setLoading(false); }
  }, [status, page]);

  useEffect(() => { void load(); return () => { requestId.current += 1; }; }, [load]);
  useEffect(() => {
    if (!data) return;
    let active = true;
    const missing = [...new Set(data.items.map(item => item.job_id))].filter(id => !jobCache.current[id]);
    if (!missing.length) return;
    void Promise.allSettled(missing.map(id => api<Job>(`/jobs/${id}`))).then(results => {
      results.forEach(result => { if (result.status === 'fulfilled') jobCache.current[result.value.id] = result.value; });
      if (active) setJobs({ ...jobCache.current });
    });
    return () => { active = false; };
  }, [data]);

  async function loadTimeline(item: { id: string; job_id: string }) {
    setTimelineErrors(previous => ({ ...previous, [item.id]: '' }));
    try {
      const timeline = await api<ApplicationTimeline>(`/jobs/${item.job_id}/applications/${item.id}/timeline`);
      setTimelines(previous => ({ ...previous, [item.id]: timeline }));
    } catch (caught) { setTimelineErrors(previous => ({ ...previous, [item.id]: (caught as Error).message })); }
  }

  function toggleTimeline(item: { id: string; job_id: string }) {
    const isOpen = open.has(item.id);
    setOpen(previous => { const next = new Set(previous); if (isOpen) next.delete(item.id); else next.add(item.id); return next; });
    if (!isOpen && !timelines[item.id]) void loadTimeline(item);
  }

  return <section className="app-page applications-page">
    <PageHeader eyebrow="Your next chapter" title="Applications" subtitle="Every application, conversation, and next step. All in one place." actions={<Link className="primary-button" href="/jobs"><Plus size={17} />Record an application</Link>} />

    <div className="applications-toolbar"><div><h2>Your application activity {data && !loading && <span className="workflow-count">{data.total}</span>}</h2><p>Track progress and keep the next conversation in sight.</p></div><label className="application-filter"><FunnelSimple size={17} aria-hidden="true" /><span className="sr-only">Status filter</span><select value={status} onChange={event => { setStatus(event.target.value as ApplicationStatus | 'All'); setPage(1); }}>{STATUSES.map(item => <option value={item} key={item}>{item === 'All' ? 'All statuses' : item}</option>)}</select></label></div>

    {error && <div className="workflow-error" role="alert"><div><strong>Applications couldn’t load</strong><p>{error}</p></div><button className="secondary-button" onClick={() => void load()}><ArrowClockwise size={16} />Try again</button></div>}
    {loading && <div className="application-list" aria-busy="true"><p className="sr-only" role="status">Loading applications…</p>{[0, 1, 2].map(item => <div className="workflow-skeleton workflow-skeleton-row" key={item} />)}</div>}
    {!loading && !error && (!data || data.total === 0) && <div className="workflow-empty"><span className="workflow-empty-icon"><Briefcase size={28} /></span><h2>{status === 'All' ? 'Your next chapter starts here' : `No ${status.toLowerCase()} applications yet`}</h2><p>{status === 'All' ? 'Open a saved job and record your application. Your progress, replies, and follow-ups will come together here.' : 'Applications with this status will appear here. Choose another status to see more of your activity.'}</p>{status === 'All' ? <Link className="primary-button" href="/jobs">Go to saved jobs <ArrowRight size={17} /></Link> : <button className="secondary-button" onClick={() => { setStatus('All'); setPage(1); }}>Show all applications</button>}</div>}

    {!loading && data && data.total > 0 && <div className="application-list">{data.items.map(item => {
      const job = jobs[item.job_id];
      return <article className="application-row" key={item.id}>
        <div className="application-main">
          <div className="application-row-heading"><span className="application-company-mark" aria-hidden="true">{job ? job.company.slice(0, 2).toUpperCase() : <Briefcase size={22} />}</span><div className="application-role"><h3><Link href={`/jobs/${item.job_id}#tracking`}>{job?.title || 'Saved opportunity'}</Link></h3><p>{job?.company || 'Application record'}{job?.location && <><span aria-hidden="true"> · </span>{job.location}</>}</p></div><span className={`status-badge is-${item.status.toLowerCase()}`}>{item.status}</span></div>
          <div className="application-row-meta"><span><CalendarBlank size={15} />Submitted {new Date(item.submission_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span><span className="method-label">{METHOD_LABEL[item.method] || item.method}</span><span className="origin-label" title={item.origin === 'email_confirmed' ? 'Created from a Gmail message you approved and synchronized' : 'Recorded by hand; no email was sent for this record'}>{item.origin === 'email_confirmed' ? 'Email-confirmed' : 'Manual record'}</span></div>
          {item.notes && <p className="application-notes">{item.notes}</p>}
          {item.follow_up_date && <p className="application-followup"><ClockCounterClockwise size={16} />{item.reminder_status === 'completed' || item.reminder_status === 'cancelled' ? `Reminder ${item.reminder_status}` : `Follow up ${new Date(item.follow_up_date).toLocaleString(undefined, { timeZone: item.reminder_timezone || 'UTC' })} (${item.reminder_timezone || 'UTC'})`}</p>}
          <div className="application-row-links"><Link className="text-button" href={`/jobs/${item.job_id}#tracking`}>Open saved job <ArrowSquareOut size={15} /></Link><button className="text-button" aria-expanded={open.has(item.id)} aria-controls={`timeline-${item.id}`} onClick={() => toggleTimeline(item)}>{open.has(item.id) ? 'Hide timeline' : 'Show timeline'}<CaretDown size={14} className={open.has(item.id) ? 'is-open' : ''} /></button></div>
          {open.has(item.id) && <div id={`timeline-${item.id}`} className="application-timeline" aria-label={`Timeline for application ${item.id}`}>
            {timelineErrors[item.id] ? <div className="workflow-error" role="alert"><p>{timelineErrors[item.id]}</p><button className="text-button" onClick={() => void loadTimeline(item)}>Retry timeline</button></div> : <p className="muted" role={!timelines[item.id] ? 'status' : undefined}>{timelines[item.id]?.narrative || 'Loading timeline…'}</p>}
            {timelines[item.id] && <ol className="timeline-list">{timelines[item.id].entries.map((entry, index) => <li key={`${entry.at}-${index}`} className={`timeline-entry is-${entry.kind}`}><p className="timeline-kind">{KIND_LABEL[entry.kind]}<time dateTime={entry.at}>{new Date(entry.at).toLocaleString()}</time></p><p><strong>{entry.title}</strong></p>{entry.detail && <p className="muted">{entry.detail}</p>}{entry.evidence.length > 0 && <ul className="muted">{entry.evidence.map((line, evidenceIndex) => <li key={evidenceIndex}>{line}</li>)}</ul>}</li>)}</ol>}
          </div>}
        </div>
      </article>;
    })}</div>}

    {!loading && data && data.total > 0 && <footer className="applications-footer"><span><LockSimple size={13} />Your application history is private</span>{data.total > data.page_size && <nav aria-label="Application pages"><button className="icon-button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(previous => previous - 1)}><CaretLeft size={17} /></button><span>Page {page} of {Math.ceil(data.total / data.page_size)}</span><button className="icon-button" aria-label="Next page" disabled={page * data.page_size >= data.total} onClick={() => setPage(previous => previous + 1)}><CaretRight size={17} /></button></nav>}</footer>}
  </section>;
}
