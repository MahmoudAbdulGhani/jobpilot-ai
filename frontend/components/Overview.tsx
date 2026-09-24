'use client';
import Link from 'next/link';
import { ArrowRight } from '@phosphor-icons/react';
import type { Insights, JobList, RankRun, RankRunList } from '../lib/types';
import { useResource } from '../lib/use-resource';
import { Shell } from './Shell';
import { PageHeader } from './ui/page-header';
import { Button } from './ui/button';
import { ErrorState } from './ui/error-state';
import { LoadingState } from './ui/loading-state';

type ReminderPage = { items: { application_id: string; job_id: string; title: string; company: string; due_at: string | null }[] };
function More({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link className="overview-link" href={href}>{children}<ArrowRight aria-hidden="true" /></Link>;
}
function Section<T>({ title, resource, children }: { title: string; resource: ReturnType<typeof useResource<T>>; children: (data: T) => React.ReactNode }) {
  return <section className="overview-section" aria-label={title}><h2>{title}</h2>
    {resource.error ? <ErrorState title={`Could not load ${title.toLowerCase()}`} message={resource.error} onRetry={resource.retry} /> : resource.data === null ? <LoadingState label={`Loading ${title.toLowerCase()}…`} rows={2} /> : children(resource.data)}
  </section>;
}
function Ranking({ id }: { id: string }) {
  const resource = useResource<RankRun>(`/rankings/${id}`);
  if (resource.error) return <ErrorState message={resource.error} onRetry={resource.retry} />;
  if (!resource.data) return <LoadingState label="Loading ranked opportunities…" rows={2} />;
  const run = resource.data;
  return <><p className="overview-caption">Advisory comparison · {new Date(run.created_at).toLocaleDateString()}{run.is_stale && ' · Your data has changed; review or rerun this comparison.'}</p>
    <ul className="overview-list">{(run.items || []).slice(0, 3).map(item => <li key={item.job_id}><Link href={`/jobs/${item.job_id}`}><span><strong>{item.title}</strong><small>{item.company}</small><small>{item.recommended_action}</small></span><ArrowRight aria-hidden="true" /></Link></li>)}</ul>
    {!run.items?.length && <p>No opportunities in this comparison.</p>}<More href="/jobs">Review saved jobs and rankings</More></>;
}
export function Overview() {
  const reminders = useResource<ReminderPage>('/reminders?view=overdue&limit=5');
  const insights = useResource<Insights>('/insights');
  const jobs = useResource<JobList>('/jobs?archived=false&page=1&page_size=5');
  const rankings = useResource<RankRunList>('/rankings?page=1&page_size=1');
  return <Shell><div className="app-page overview-page">
    <PageHeader eyebrow="Your workspace" title="Your next step, in view." subtitle="Review what needs attention, return to an opportunity, and keep your applications moving." actions={<Button asChild><Link href="/jobs">Open saved jobs<ArrowRight aria-hidden="true" /></Link></Button>} />
    <div className="overview-grid"><div>
      <Section title="Needs your attention" resource={reminders}>{data => <>
        {data.items.length ? <ul className="overview-list">{data.items.map(item => <li key={item.application_id}><Link href={`/jobs/${item.job_id}`}><span><strong>{item.title}</strong><small>{item.company}{item.due_at && <> · Due <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString()}</time></>}</small></span><span className="overview-due">Due now</span></Link></li>)}</ul> : <div className="overview-empty"><h3>You’re up to date.</h3><p>No follow-up reminders are due. Check upcoming reminders to plan ahead.</p></div>}<More href="/reminders">View reminders</More>
      </>}</Section>
      <Section title="Recently saved" resource={jobs}>{data => <>
        {data.items.length ? <ul className="overview-list">{data.items.map(job => <li key={job.id}><Link href={`/jobs/${job.id}`}><span><strong>{job.title}</strong><small>{job.company}{job.location ? ` · ${job.location}` : ''}</small></span><ArrowRight aria-hidden="true" /></Link></li>)}</ul> : <div className="overview-empty"><h3>Start with one opportunity.</h3><p>Save a role and keep its description, notes, and application progress together.</p></div>}<More href="/jobs">View saved jobs</More>
      </>}</Section>
    </div><div>
      <Section title="Application pipeline" resource={insights}>{data => <>
        {Object.keys(data.application_counts).length ? <dl className="overview-pipeline">{Object.entries(data.application_counts).map(([status, count]) => <div key={status}><dt>{status}</dt><dd>{count}</dd></div>)}</dl> : <p className="overview-empty">No applications recorded yet. Track an application from a saved job.</p>}<More href="/applications">View applications</More>
        {data.replies.length > 0 && <div className="overview-activity"><h3>Replies to review</h3><ul className="overview-list">{data.replies.slice(0, 3).map(reply => <li key={reply.reply_id}><p><strong>{reply.sender_domain}</strong></p><p>{reply.excerpt || 'No preview available.'}</p>{reply.link && <More href={reply.link.href}>{reply.link.label}</More>}</li>)}</ul></div>}<More href="/insights">Explore detailed insights</More>
      </>}</Section>
      <Section title="Opportunities to consider" resource={rankings}>{data => data.items[0] ? <Ranking id={data.items[0].id} /> : <div className="overview-empty"><p>Compare saved jobs against your profile when you’re ready. No comparison runs automatically.</p><More href="/jobs">Review and rank saved jobs</More></div>}</Section>
      <nav className="overview-toolkit" aria-label="Prepare your next application"><h2>Your application toolkit</h2><More href="/profile">Update your profile</More><More href="/resumes">Review your resumes</More><More href="/discover">Discover opportunities</More></nav>
    </div></div>
  </div></Shell>;
}
