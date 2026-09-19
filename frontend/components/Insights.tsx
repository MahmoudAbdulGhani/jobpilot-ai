'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Shell } from './Shell';
import { QaPanel } from './QaPanel';
import type { Insights } from '../lib/types';

function Counts({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  return <div>
    <h3>{title}</h3>
    {entries.length === 0 && <p className="muted">Nothing recorded yet.</p>}
    {entries.length > 0 && <ul>{entries.map(([name, count]) => <li key={name}>{name}: {count}</li>)}</ul>}
  </div>;
}

export function InsightsView() {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api<Insights>('/insights')
      .then(result => { if (active) setData(result); })
      .catch(e => { if (active) setError((e as Error).message); });
    return () => { active = false; };
  }, []);

  return <Shell><div className="collection-page insights-page">
    <div className="collection-heading"><div>
      <p className="eyebrow">Private overview</p>
      <h1>Insights</h1>
      <p className="collection-subtitle">Your fit gaps, applications, replies, reminders and interview activity in one place. Read-only; previews are excerpted and senders reduced to domains.</p>
    </div></div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {!data && !error && <p className="notice">Loading insights…</p>}
    {data && <>
      <section aria-label="Fit gaps">
        <h2>Fit gaps</h2>
        <Counts title="Assessments" counts={data.fit_counts} />
        {data.fit_gaps.length === 0 && <p className="muted">No unevidenced requirements found.</p>}
        <ul>{data.fit_gaps.map((gap, index) => <li key={index}>
          <strong>{gap.job_title}</strong> · {gap.assessment}: {gap.requirement} <Link href={gap.link.href}>{gap.link.label}</Link>
        </li>)}</ul>
      </section>
      <section aria-label="Applications">
        <h2>Applications</h2>
        <Counts title="By status" counts={data.application_counts} />
        <ul>{data.applications.map(item => <li key={`${item.job_id}-${item.status}`}>
          <strong>{item.job_title}</strong> · {item.status} · {item.origin === 'email_confirmed' ? 'Email-confirmed' : 'Manual record'} <Link href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
      <section aria-label="Replies">
        <h2>Replies</h2>
        <Counts title="By match" counts={data.reply_counts} />
        <ul>{data.replies.map(item => <li key={item.reply_id}>
          <span className="muted">{item.sender_domain}</span> · {item.excerpt || 'No preview text.'} {item.link && <Link href={item.link.href}>{item.link.label}</Link>}
        </li>)}</ul>
      </section>
      <section aria-label="Reminders">
        <h2>Reminders</h2>
        <p>Overdue: {data.reminder_counts.overdue} · Upcoming: {data.reminder_counts.upcoming}</p>
        <ul>{data.reminders.map(item => <li key={item.application_id}>
          <strong>{item.job_title}</strong> {item.overdue && '— Due now'}
          {item.due_at && <> · <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString()}</time></>} <Link href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
      <section aria-label="Interviews">
        <h2>Interview activity</h2>
        <Counts title="By status" counts={data.interview_counts} />
        <ul>{data.interviews.map(item => <li key={item.session_id}>
          {item.status} <Link href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
      <QaPanel/>
    </>}
  </div></Shell>;
}
