'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { Shell } from './Shell';
import { DigestPanel } from './DigestPanel';
import { api } from '../lib/api';

export type DiscoveredJob = {
  source: 'jobtech' | 'jobicy'; external_id: string; title: string; company: string;
  location: string | null; description: string | null; source_url: string;
  published_at: string | null; deadline: string | null; salary: string | null;
  applicant_region?: string | null; remote_arrangement?: string; possible_duplicate_ids?: string[]; workplace_model: string | null; existing_job_id: string | null; test_data: boolean;
};
type Results = { items: DiscoveredJob[]; total: number; offset: number; next_offset: number | null };
type Preview = { job: DiscoveredJob; preview_token: string; expires_at: string };
const sourceDate = (date: string | null) => date ? date.replace('T', ' ') : 'Not supplied';

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

function PossibleDuplicates({job}:{job:DiscoveredJob}) {
  if(!job.possible_duplicate_ids?.length)return null;
  return <aside className="notice"><p>Possible cross-source match: same title and company. These may be distinct vacancies; compare before importing. Nothing will be merged.</p>{job.possible_duplicate_ids.map(id=><Link key={id} href={`/jobs/${id}`}>Compare saved job</Link>)}</aside>;
}

export function Discovery() {
  const [source,setSource]=useState('jobtech');
  const [location,setLocation]=useState('');
  const [q, setQ] = useState('');
  const [remote, setRemote] = useState(false);
  const [sort, setSort] = useState('relevance');
  const [results, setResults] = useState<Results | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<{ id: string; duplicate: boolean } | null>(null);
  const [query, setQuery] = useState({ q: '', remote: false, sort: 'relevance', source:'jobtech', location:'' });
  const previewHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (preview && !saved) previewHeading.current?.focus();
  }, [preview, saved]);

  function fail(error: unknown) {
    setError(error instanceof Error ? error.message : 'Discovery is unavailable. Please try later.');
  }
  async function search(offset = 0, fresh = false) {
    const selection = fresh ? { q, remote:source==='jobicy'||remote, sort, source, location } : query;
    if (fresh) setQuery(selection);
    setBusy('Searching JobTech…'); setError(''); setPreview(null); setSaved(null); setResults(null);
    const params = new URLSearchParams({ source:selection.source, location:selection.location, q: selection.q, remote: String(selection.remote), sort: selection.sort, offset: String(offset) });
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
  return <Shell><div className="collection-page discovery-page">
    <header><p className="eyebrow">Find your next opportunity</p><h1>Discover jobs</h1>
      <p>Listings from Sweden’s public employment service, via <a href="https://jobsearch.api.jobtechdev.se/" target="_blank" rel="noopener noreferrer">JobTech JobSearch</a>. Primarily Swedish coverage; this is not a worldwide job search.</p>
      <p><a href="https://jobicy.com/jobs-rss-feed" target="_blank" rel="noopener noreferrer">Jobicy</a> adds international remote listings. Coverage varies; Lebanon-specific availability is not guaranteed. Regional eligibility is source-stated, not a confirmation of your right to work.</p>
      <p>Review a listing before saving it. Discovery does not run AI or send applications.</p>
    </header>
    <form className="discovery-form" onSubmit={(e: FormEvent) => { e.preventDefault(); void search(0, true); }}>
      <label>Source<select aria-label="Source" value={source} disabled={!!busy} onChange={e=>{setSource(e.target.value);setLocation('');setResults(null);setPreview(null);setSaved(null);}}><option value="jobtech">JobTech — primarily Sweden</option><option value="jobicy">Jobicy — international remote</option></select></label>
      <label>Applicant region text (Jobicy cache)<input value={location} maxLength={100} disabled={!!busy||source!=='jobicy'} onChange={e=>setLocation(e.target.value)} placeholder="e.g. EMEA, Lebanon, UK" /></label>
      <label>Keywords<input value={q} maxLength={200} disabled={!!busy} onChange={e => setQ(e.target.value)} placeholder="Job title, skills or employer" /></label>
      <label>Sort<select value={sort} disabled={!!busy} onChange={e => setSort(e.target.value)}><option value="relevance">{source==='jobicy'?'Catalog order':'Relevance'}</option><option value="pubdate-desc">Newest published</option></select></label>
      <label className="discovery-checkbox"><input type="checkbox" checked={source==='jobicy'||remote} disabled={!!busy||source==='jobicy'} onChange={e => setRemote(e.target.checked)} /> {source==='jobicy'?'Remote listings (all Jobicy results)':'Approximate remote matches (source phrase matching)'}</label>
      <button className="primary-button" disabled={!!busy}>Search {source==='jobicy'?'Jobicy':'JobTech'}</button>
    </form>
    <p className="privacy-caption">Remote matching is approximate and does not mean worldwide eligibility. Verify permitted work locations, residency and work-authorization requirements with the employer. Location, salary and workplace details may be missing. Jobicy location filtering matches the source applicant-region text in the latest 100 cached listings; it is not a worksite or eligibility guarantee. Unknown regions do not match location filters. JobTech location filtering remains keyword-based. Salary filtering is not offered.</p>
    {busy && <p role="status">{busy}</p>}
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {saved && <div role="status" className="notice"><p>{saved.duplicate ? 'Already saved. Your edits were preserved.' : 'Job imported. Review and edit it in your saved jobs.'}</p><Link href={`/jobs/${saved.id}`}>Open saved job</Link></div>}
    {preview && !saved && <section className="discovery-preview" aria-labelledby="preview-heading">
      <h2 id="preview-heading" tabIndex={-1} ref={previewHeading}>Preview: {preview.job.title}</h2>
      <p>{preview.job.company}</p>{preview.job.test_data && <p className="notice">Synthetic test listing — not a live result</p>}
      <a href={preview.job.source_url} target="_blank" rel="noopener noreferrer">View source listing</a>
      <p>Source: {preview.job.source==='jobicy'?'Jobicy':'JobTech JobSearch'}</p><Details job={preview.job} /><PossibleDuplicates job={preview.job}/>
      <h3>Description</h3><p className="preserve-lines">{preview.job.description || 'No plain-text description supplied. Check the source before importing.'}</p>
      <p>This saves the previewed snapshot. It will not refresh automatically or overwrite your edits. Preview expires in 15 minutes. Dates and availability should be checked at the source.</p>
      {preview.job.existing_job_id ? <Link href={`/jobs/${preview.job.existing_job_id}`}>Already saved — open existing job</Link> : <button className="primary-button" disabled={!!busy} onClick={importJob}>Import this job into saved jobs</button>}
      <button className="text-button" disabled={!!busy} onClick={() => setPreview(null)}>Close preview</button>
    </section>}
    {results && <section aria-label="Discovery results">
      <p className="results-label">{results.total} {query.source==='jobicy'?'matches in the latest cached catalog':'source matches'}</p>
      {query.source==='jobicy'&&<p>Up to 100 recent listings, refreshed at most hourly. Search and pagination filter this cache locally. An empty result does not establish that no vacancy exists. Preview checks availability; saved snapshots do not refresh automatically.</p>}
      {!results.items.length && <div className="empty-state"><h2>No matching jobs</h2><p>{query.source==='jobicy'?'Try different keywords or applicant-region text. This searches only the latest cached catalog.':'Try different keywords or turn off the remote filter.'}</p></div>}
      {results.items.map(job => <article className="discovery-result" key={job.source+job.external_id}>
        <h2>{job.title}</h2><p><strong>{job.company}</strong></p>
        {job.test_data && <p>Synthetic test listing — not a live result</p>}
        <Details job={job} /><a href={job.source_url} target="_blank" rel="noopener noreferrer">{job.source==='jobicy'?'View on Jobicy':'View on Platsbanken'}</a><PossibleDuplicates job={job}/>
        {job.existing_job_id ? <Link href={`/jobs/${job.existing_job_id}`}>Already saved — open existing job</Link> : <button className="primary-button" disabled={!!busy} onClick={() => openPreview(job.external_id,job.source)}>Preview job</button>}
      </article>)}
      <div className="pagination"><button disabled={!!busy || results.offset === 0} onClick={() => search(Math.max(0, results.offset - 20))}>Previous results</button><span>Page {Math.floor(results.offset / 20) + 1}</span><button disabled={!!busy || results.next_offset === null} onClick={() => search(results.next_offset!)}>Next results</button></div>
      {results.total > 2000 && <p>Only the first 2,000 matches are available here. Refine your search.</p>}
    </section>}
    <DigestPanel/>
  </div></Shell>;
}
