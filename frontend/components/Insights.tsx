'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Shell } from './Shell';
import { QaPanel } from './QaPanel';
import type { Insights } from '../lib/types';
import { PageHeader } from './ui/page-header';
import { LoadingState } from './ui/loading-state';
import { ErrorState } from './ui/error-state';

const sectionCard = 'mt-6 rounded-lg border border-border bg-card p-6';
const sectionHeading = 'font-serif text-2xl leading-snug text-[var(--ink)]';

function Counts({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  return <div className="mt-3">
    <h3 className="text-sm font-semibold text-foreground">{title}</h3>
    {entries.length === 0 && <p className="mt-1 text-sm text-muted-foreground">Nothing recorded yet.</p>}
    {entries.length > 0 && <ul className="mt-2 grid list-disc gap-1.5 gap-x-8 pl-6 text-sm text-muted-foreground sm:grid-cols-2">{entries.map(([name, count]) => <li key={name}>{name}: {count}</li>)}</ul>}
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

  return <Shell><div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
    <PageHeader eyebrow="Private overview" title="Insights"
      subtitle="Your fit gaps, applications, replies, reminders and interview activity in one place. Read-only; previews are excerpted and senders reduced to domains." />
    {error && <div className="mt-6"><ErrorState title="Could not load insights" message={error} onRetry={() => { setData(null); setError(''); }} /></div>}
    {!data && !error && <div className="mt-6"><LoadingState label="Loading insights…" rows={4} /></div>}
    {data && <>
      <section className={sectionCard} aria-label="Fit gaps">
        <h2 className={sectionHeading}>Fit gaps</h2>
        <Counts title="Assessments" counts={data.fit_counts} />
        {data.fit_gaps.length === 0 && <p className="mt-3 text-sm text-muted-foreground">No unevidenced requirements found.</p>}
        <ul className="mt-3 grid list-disc gap-2 pl-6 text-sm text-muted-foreground">{data.fit_gaps.map((gap, index) => <li key={index} className="[overflow-wrap:anywhere]">
          <strong className="font-semibold text-foreground">{gap.job_title}</strong> · {gap.assessment}: {gap.requirement} <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={gap.link.href}>{gap.link.label}</Link>
        </li>)}</ul>
      </section>
      <section className={sectionCard} aria-label="Applications">
        <h2 className={sectionHeading}>Applications</h2>
        <Counts title="By status" counts={data.application_counts} />
        <ul className="mt-3 grid list-disc gap-2 pl-6 text-sm text-muted-foreground">{data.applications.map(item => <li key={`${item.job_id}-${item.status}`} className="[overflow-wrap:anywhere]">
          <strong className="font-semibold text-foreground">{item.job_title}</strong> · {item.status} · {item.origin === 'email_confirmed' ? 'Email-confirmed' : 'Manual record'} <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
      <section className={sectionCard} aria-label="Replies">
        <h2 className={sectionHeading}>Replies</h2>
        <Counts title="By match" counts={data.reply_counts} />
        <ul className="mt-3 grid list-disc gap-2 pl-6 text-sm text-muted-foreground">{data.replies.map(item => <li key={item.reply_id} className="[overflow-wrap:anywhere]">
          <span className="text-foreground">{item.sender_domain}</span> · {item.excerpt || 'No preview text.'} {item.link && <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={item.link.href}>{item.link.label}</Link>}
        </li>)}</ul>
      </section>
      <section className={sectionCard} aria-label="Reminders">
        <h2 className={sectionHeading}>Reminders</h2>
        <p className="mt-3 text-sm text-muted-foreground">Overdue: {data.reminder_counts.overdue} · Upcoming: {data.reminder_counts.upcoming}</p>
        <ul className="mt-3 grid list-disc gap-2 pl-6 text-sm text-muted-foreground">{data.reminders.map(item => <li key={item.application_id} className="[overflow-wrap:anywhere]">
          <strong className="font-semibold text-foreground">{item.job_title}</strong> {item.overdue && '— Due now'}
          {item.due_at && <> · <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString()}</time></>} <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
      <section className={sectionCard} aria-label="Interviews">
        <h2 className={sectionHeading}>Interview activity</h2>
        <Counts title="By status" counts={data.interview_counts} />
        <ul className="mt-3 grid list-disc gap-2 pl-6 text-sm text-muted-foreground">{data.interviews.map(item => <li key={item.session_id}>
          {item.status} <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={item.link.href}>{item.link.label}</Link>
        </li>)}</ul>
      </section>
    </>}
    <div className="mt-6"><QaPanel /></div>
  </div></Shell>;
}