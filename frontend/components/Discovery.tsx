'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { Shell } from './Shell';
import { DigestPanel } from './DigestPanel';
import { api } from '../lib/api';
import { PageHeader } from './ui/page-header';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Alert } from './ui/alert';
import { EmptyState } from './ui/empty-state';

export type DiscoveredJob = {
  source: 'jobtech' | 'jobicy'; external_id: string; title: string; company: string;
  location: string | null; description: string | null; source_url: string;
  published_at: string | null; deadline: string | null; salary: string | null;
  applicant_region?: string | null; remote_arrangement?: string; possible_duplicate_ids?: string[]; workplace_model: string | null; existing_job_id: string | null; test_data: boolean;
};
type Results = { items: DiscoveredJob[]; total: number; offset: number; next_offset: number | null };
type Preview = { job: DiscoveredJob; preview_token: string; expires_at: string };
const sourceDate = (date: string | null) => date ? date.replace('T', ' ') : 'Not supplied';
const selectClass = 'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50';

function Details({ job }: { job: DiscoveredJob }) {
  return <dl className="discovery-details">
    <div><dt>Location</dt><dd>{job.location || 'Not supplied'}</dd></div>
    <div><dt>Applicant region (source)</dt><dd>{job.applicant_region || 'Unknown eligibility — check the employer'}</dd></div>
    <div><dt>Salary</dt><dd>{job.salary || 'Not supplied'}</dd></div>
    <div><dt>Workplace model (source)</dt><dd>{job.workplace_model || 'Not supplied — remote work is not confirmed'}</dd></div>
    <div><dt>Published (source date)</dt><dd>{sourceDate(job.published_at)}</dd></div>
    <div><dt>Application deadline (source date)</dt><dd>{sourceDate(job.deadline)}</dd></div>
  </dl>;
}

function PossibleDuplicates({ job }: { job: DiscoveredJob }) {
  if (!job.possible_duplicate_ids?.length) return null;
  return <aside className="my-4 rounded-lg border border-[#e5d9b8] bg-[#faf3e0] p-4 text-sm">
    <p>Possible cross-source match: same title and company. These may be distinct vacancies; compare before importing. Nothing will be merged.</p>
    {job.possible_duplicate_ids.map(id => <Link key={id} className="mt-2 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${id}`}>Compare saved job</Link>)}
  </aside>;
}

export function Discovery() {
  const [source, setSource] = useState('jobtech');
  const [location, setLocation] = useState('');
  const [q, setQ] = useState('');
  const [remote, setRemote] = useState(false);
  const [sort, setSort] = useState('relevance');
  const [results, setResults] = useState<Results | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<{ id: string; duplicate: boolean } | null>(null);
  const [query, setQuery] = useState({ q: '', remote: false, sort: 'relevance', source: 'jobtech', location: '' });
  const previewHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (preview && !saved) previewHeading.current?.focus();
  }, [preview, saved]);

  function fail(error: unknown) {
    setError(error instanceof Error ? error.message : 'Discovery is unavailable. Please try later.');
  }
  async function search(offset = 0, fresh = false) {
    const selection = fresh ? { q, remote: source === 'jobicy' || remote, sort, source, location } : query;
    if (fresh) setQuery(selection);
    setBusy(selection.source === 'jobicy' ? 'Searching Jobicy…' : 'Searching JobTech…'); setError(''); setPreview(null); setSaved(null); setResults(null);
    const params = new URLSearchParams({ source: selection.source, location: selection.location, q: selection.q, remote: String(selection.remote), sort: selection.sort, offset: String(offset) });
    try { setResults(await api<Results>(`/discovery?${params}`)); }
    catch (e) { fail(e); }
    finally { setBusy(''); }
  }
  async function openPreview(id: string, provider: string) {
    setBusy('Loading preview…'); setError(''); setPreview(null); setSaved(null);
    try {
      setPreview(await api<Preview>(`/discovery/${encodeURIComponent(id)}/preview?source=${provider}`));
    } catch (e) { fail(e); }
    finally { setBusy(''); }
  }
  async function importJob() {
    if (!preview) return;
    setBusy('Importing reviewed job…'); setError('');
    try {
      const result = await api<{ job: { id: string }; already_saved: boolean }>('/discovery/import', {
        method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, confirm: true }),
      });
      setSaved({ id: result.job.id, duplicate: result.already_saved });
      setResults(old => old && ({ ...old, items: old.items.map(j => j.source === preview.job.source && j.external_id === preview.job.external_id ? { ...j, existing_job_id: result.job.id } : j) }));
    } catch (e) { fail(e); }
    finally { setBusy(''); }
  }
  return <Shell><div className="app-page">
    <PageHeader eyebrow="Find your next opportunity" title="Discover jobs" subtitle={<>
      <span className="block [overflow-wrap:anywhere]">Listings from Sweden’s public employment service, via <a className="underline underline-offset-4" href="https://jobsearch.api.jobtechdev.se/" target="_blank" rel="noopener noreferrer">JobTech JobSearch</a>. Primarily Swedish coverage; this is not a worldwide job search.</span>
      <span className="mt-2 block [overflow-wrap:anywhere]"><a className="underline underline-offset-4" href="https://jobicy.com/jobs-rss-feed" target="_blank" rel="noopener noreferrer">Jobicy</a> adds international remote listings. Coverage varies; Lebanon-specific availability is not guaranteed. Regional eligibility is source-stated, not a confirmation of your right to work.</span>
      <span className="mt-2 block [overflow-wrap:anywhere]">Review a listing before saving it. Discovery does not run AI or send applications.</span>
    </>} />
    <form className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e: FormEvent) => { e.preventDefault(); void search(0, true); }}>
      <div className="flex flex-col gap-2">
        <Label htmlFor="source">Source</Label>
        <select id="source" className={selectClass} aria-label="Source" value={source} disabled={!!busy} onChange={e => { setSource(e.target.value); setRemote(false); setLocation(''); setResults(null); setPreview(null); setSaved(null); }}>
          <option value="jobtech">JobTech — primarily Sweden</option><option value="jobicy">Jobicy — international remote</option>
        </select>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="region">Applicant region text (Jobicy cache)</Label>
        <Input id="region" value={location} maxLength={100} disabled={!!busy || source !== 'jobicy'} onChange={e => setLocation(e.target.value)} placeholder="e.g. EMEA, Lebanon, UK" />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="keywords">Keywords</Label>
        <Input id="keywords" value={q} maxLength={200} disabled={!!busy} onChange={e => setQ(e.target.value)} placeholder="Job title, skills or employer" />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="sort">Sort</Label>
        <select id="sort" className={selectClass} value={sort} disabled={!!busy} onChange={e => setSort(e.target.value)}>
          <option value="relevance">{source === 'jobicy' ? 'Catalog order' : 'Relevance'}</option><option value="pubdate-desc">Newest published</option>
        </select>
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2 lg:col-span-2">
        <label className="flex items-start gap-2 text-sm text-muted-foreground">
          <input type="checkbox" className="mt-0.5 size-4 rounded border border-input accent-[var(--forest)]"
            checked={source === 'jobicy' || remote} disabled={!!busy || source === 'jobicy'}
            onChange={e => setRemote(e.target.checked)}
            aria-label={source === 'jobicy' ? 'Remote listings (all Jobicy results)' : 'Approximate remote matches (source phrase matching)'} />
          <span>{source === 'jobicy' ? 'Remote listings (all Jobicy results)' : 'Approximate remote matches (source phrase matching)'}</span>
        </label>
        <Button type="submit" disabled={!!busy} className="w-fit">Search {source === 'jobicy' ? 'Jobicy' : 'JobTech'}</Button>
      </div>
    </form>
    <details className="my-6 max-w-3xl text-sm leading-relaxed text-muted-foreground"><summary className="min-h-11 cursor-pointer font-medium text-foreground">Coverage and search limitations</summary><p className="my-6 max-w-3xl text-sm leading-relaxed text-muted-foreground">Remote matching is approximate and does not mean worldwide eligibility. Verify permitted work locations, residency and work-authorization requirements with the employer. Location, salary and workplace details may be missing. Jobicy location filtering matches the source applicant-region text in the latest 100 cached listings; it is not a worksite or eligibility guarantee. Unknown regions do not match location filters. JobTech location filtering remains keyword-based. Salary filtering is not offered.</p></details>
    {busy && <p role="status" className="text-sm text-muted-foreground">{busy}</p>}
    {error && <Alert variant="destructive" className="mt-2">{error}</Alert>}
    {saved && <div role="status" className="my-4 rounded-lg border border-[#cfe0d5] bg-[#eef5f1] p-4 text-sm">
      <p>{saved.duplicate ? 'Already saved. Your edits were preserved.' : 'Job imported. Review and edit it in your saved jobs.'}</p>
      <Link className="mt-2 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${saved.id}`}>Open saved job</Link>
    </div>}
    {preview && !saved && <section className="mt-6 rounded-lg border border-[#c4c8bf] bg-[#f2f5ee] p-6 [overflow-wrap:anywhere]" aria-labelledby="preview-heading">
      <h2 id="preview-heading" tabIndex={-1} ref={previewHeading} className="font-serif text-2xl leading-snug text-[var(--ink)]">Preview: {preview.job.title}</h2>
      <p className="mt-2">{preview.job.company}</p>
      {preview.job.test_data && <p className="mt-2 text-sm text-muted-foreground">Synthetic test listing — not a live result</p>}
      <a className="mt-3 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={preview.job.source_url} target="_blank" rel="noopener noreferrer">View source listing</a>
      <p className="mt-3 whitespace-pre-line">Source: {preview.job.source === 'jobicy' ? 'Jobicy' : 'JobTech JobSearch'}</p>
      <Details job={preview.job} />
      <PossibleDuplicates job={preview.job} />
      <h3 className="mt-4 font-serif text-xl leading-snug text-[var(--ink)]">Description</h3>
      <p className="preserve-lines">{preview.job.description || 'No plain-text description supplied. Check the source before importing.'}</p>
      <p className="mt-3 text-sm text-muted-foreground">This saves the previewed snapshot. It will not refresh automatically or overwrite your edits. Preview expires in 15 minutes. Dates and availability should be checked at the source.</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        {preview.job.existing_job_id ? <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${preview.job.existing_job_id}`}>Already saved — open existing job</Link> : <Button disabled={!!busy} onClick={importJob}>Import this job into saved jobs</Button>}
        <Button variant="ghost" disabled={!!busy} onClick={() => setPreview(null)}>Close preview</Button>
      </div>
    </section>}
    {results && <section aria-label="Discovery results">
      <p className="mt-6 text-sm text-muted-foreground">{results.total} {query.source === 'jobicy' ? 'matches in the latest cached catalog' : 'source matches'}</p>
      {query.source === 'jobicy' && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">Up to 100 recent listings, refreshed at most hourly. Search and pagination filter this cache locally. An empty result does not establish that no vacancy exists. Preview checks availability; saved snapshots do not refresh automatically.</p>}
      {!results.items.length && <div className="mt-6"><EmptyState title="No matching jobs"
        description={query.source === 'jobicy' ? 'Try different keywords or applicant-region text. This searches only the latest cached catalog.' : 'Try different keywords or turn off the remote filter.'} /></div>}
      {results.items.map(job => <article className="my-4 rounded-lg border border-[#c4c8bf] bg-card p-6" key={job.source + job.external_id}>
        <h2 className="font-serif text-2xl leading-snug text-[var(--ink)] [overflow-wrap:anywhere]">{job.title}</h2>
        <p className="mt-1"><strong>{job.company}</strong></p>
        {job.test_data && <p className="mt-2 text-sm text-muted-foreground">Synthetic test listing — not a live result</p>}
        <Details job={job} />
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <a className="text-sm text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={job.source_url} target="_blank" rel="noopener noreferrer">{job.source === 'jobicy' ? 'View on Jobicy' : 'View on Platsbanken'}</a>
          {job.existing_job_id ? <Link className="text-sm text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${job.existing_job_id}`}>Already saved — open existing job</Link> : <Button disabled={!!busy} onClick={() => openPreview(job.external_id, job.source)}>Preview job</Button>}
        </div>
        <PossibleDuplicates job={job} />
      </article>)}
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Button variant="outline" size="sm" disabled={!!busy || results.offset === 0} onClick={() => search(Math.max(0, results.offset - 20))}>Previous results</Button>
        <span className="text-sm text-muted-foreground" aria-live="polite">Page {Math.floor(results.offset / 20) + 1}</span>
        <Button variant="outline" size="sm" disabled={!!busy || results.next_offset === null} onClick={() => search(results.next_offset!)}>Next results</Button>
      </div>
      {results.total > 2000 && <p className="mt-3 text-sm text-muted-foreground">Only the first 2,000 matches are available here. Refine your search.</p>}
    </section>}
    <DigestPanel />
  </div></Shell>;
}
