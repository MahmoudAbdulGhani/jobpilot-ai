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
  source: 'jobtech' | 'jobicy' | 'jobopportunities'; external_id: string; title: string; company: string;
  location: string | null; description: string | null; source_url: string;
  workplace_country?: string | null; workplace_region?: string | null; workplace_city?: string | null;
  apply_url?: string | null; upstream_source?: string | null; remote_inferred?: boolean;
  published_at: string | null; deadline: string | null; salary: string | null;
  applicant_region?: string | null; remote_arrangement?: string; possible_duplicate_ids?: string[]; workplace_model: string | null; existing_job_id: string | null; test_data: boolean;
};
type Results = { items: DiscoveredJob[]; total: number; offset: number; next_offset: number | null; result_limit?: number | null };
type Preview = { job: DiscoveredJob; preview_token: string; expires_at: string };
type SourceCapability = {label:string;coverage:string;filters:string[];remote_accuracy:string;pagination:string;ai_description:string;application:string;attribution_url:string};
const fallbackSources:Record<string,SourceCapability> = {
  jobtech:{label:'JobTech JobSearch',coverage:'Primarily Sweden.',filters:['country','region','city','remote'],remote_accuracy:'approximate',pagination:'offset',ai_description:'when_supplied',application:'source_link',attribution_url:'https://jobsearch.api.jobtechdev.se/'},
  jobicy:{label:'Jobicy',coverage:'Recent remote catalog only.',filters:['eligibility','remote'],remote_accuracy:'source_remote_catalog',pagination:'cached_offset',ai_description:'when_supplied',application:'source_link',attribution_url:'https://jobicy.com/jobs-rss-feed'},
  jobopportunities:{label:'Job Opportunities API',coverage:'Worldwide first page, up to 50 results per search.',filters:['country','city','us_state','remote'],remote_accuracy:'source_or_inferred',pagination:'single_page',ai_description:'when_supplied',application:'employer_link_when_supplied',attribution_url:'https://jobopportunitiesapi.org/'},
};
const sourceDate = (date: string | null) => date ? date.replace('T', ' ') : 'Not supplied';
const selectClass = 'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50';

function Details({ job }: { job: DiscoveredJob }) {
  return <dl className="discovery-details">
    <div><dt>Workplace</dt><dd>{job.location || [job.workplace_city,job.workplace_region,job.workplace_country].filter(Boolean).join(', ') || 'Not supplied'}</dd></div>
    <div><dt>Applicant eligibility</dt><dd>{job.applicant_region || 'Unknown — check the employer'}</dd></div>
    <div><dt>Salary</dt><dd>{job.salary || 'Not supplied'}</dd></div>
    <div><dt>Workplace model</dt><dd>{job.workplace_model || 'Not supplied — remote work is not confirmed'}{job.remote_inferred ? ' (inferred by source)' : ''}</dd></div>
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
  const [country,setCountry]=useState(''),[region,setRegion]=useState(''),[city,setCity]=useState('');
  const [sources,setSources]=useState<Record<string,SourceCapability>>(fallbackSources);
  const [q, setQ] = useState('');
  const [remote, setRemote] = useState(false);
  const [sort, setSort] = useState('relevance');
  const [results, setResults] = useState<Results | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<{ id: string; duplicate: boolean } | null>(null);
  const [query, setQuery] = useState({ q: '', remote: false, sort: 'relevance', source: 'jobtech', location: '',country:'',region:'',city:'' });
  const previewHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (preview && !saved) previewHeading.current?.focus();
  }, [preview, saved]);
  useEffect(() => {api<{sources:Record<string,SourceCapability>}>('/discovery/sources').then(data=>setSources(data.sources)).catch(()=>{});},[]);

  function fail(error: unknown) {
    setError(error instanceof Error ? error.message : 'Discovery is unavailable. Please try later.');
  }
  async function search(offset = 0, fresh = false) {
    const selection = fresh ? { q, remote: source === 'jobicy' || remote, sort, source, location,country,region,city } : query;
    if (fresh) setQuery(selection);
    setBusy(`Searching ${sources[selection.source]?.label || 'jobs'}…`); setError(''); setPreview(null); setSaved(null); setResults(null);
    const params = new URLSearchParams({ source: selection.source, eligibility: selection.location, country:selection.country,region:selection.region,city:selection.city, q: selection.q, remote: String(selection.remote), sort: selection.sort, offset: String(offset) });
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
      <span className="block [overflow-wrap:anywhere]">Search real listings from public job sources worldwide, remote, or by workplace location. Coverage varies by source.</span>
      <span className="mt-2 block [overflow-wrap:anywhere]">Review a listing before saving it, then prepare an application pack. Discovery itself does not run AI or send applications.</span>
    </>} />
    <form className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e: FormEvent) => { e.preventDefault(); void search(0, true); }}>
      <div className="flex flex-col gap-2">
        <Label htmlFor="source">Source</Label>
        <select id="source" className={selectClass} aria-label="Source" value={source} disabled={!!busy} onChange={e => { setSource(e.target.value); setRemote(false);setSort('relevance'); setLocation('');setCountry('');setRegion('');setCity(''); setResults(null); setPreview(null); setSaved(null); }}>
          <option value="jobtech">JobTech — primarily Sweden</option><option value="jobicy">Jobicy — international remote</option><option value="jobopportunities">Worldwide — Job Opportunities API</option>
        </select>
      </div>
      {source==='jobicy'?<div className="flex flex-col gap-2"><Label htmlFor="eligibility">Applicant eligibility (source text)</Label><Input id="eligibility" value={location} maxLength={100} disabled={!!busy} onChange={e=>setLocation(e.target.value)} placeholder="e.g. EMEA, UK" /></div>:<>
        <div className="flex flex-col gap-2"><Label htmlFor="country">Workplace country</Label><Input id="country" value={country} maxLength={100} disabled={!!busy} onChange={e=>{setCountry(e.target.value);setRegion('');if(source==='jobtech')setCity('');}} placeholder={source==='jobopportunities'?'ISO code, e.g. US, FR':'Country name, e.g. Sweden'} /></div>
        <div className="flex flex-col gap-2"><Label htmlFor="region">Workplace {source==='jobopportunities'?'US state':'region'}</Label><Input id="region" value={region} maxLength={100} disabled={!!busy || (source==='jobopportunities'&&country.toUpperCase()!=='US')} onChange={e=>{setRegion(e.target.value);if(source==='jobtech'){setCountry('');setCity('');}}} placeholder={source==='jobopportunities'?'Two-letter code, e.g. NY':'Exact region name'} /></div>
        <div className="flex flex-col gap-2"><Label htmlFor="city">Workplace {source==='jobtech'?'municipality':'city'}</Label><Input id="city" value={city} maxLength={100} disabled={!!busy} onChange={e=>{setCity(e.target.value);if(source==='jobtech'){setCountry('');setRegion('');}}} placeholder={source==='jobtech'?'Exact municipality name':'City name'} /></div>
      </>}
      <div className="flex flex-col gap-2">
        <Label htmlFor="keywords">Keywords</Label>
        <Input id="keywords" value={q} maxLength={200} disabled={!!busy} onChange={e => setQ(e.target.value)} placeholder={source==='jobopportunities'?'Job title, employer or location':'Job title, skills or employer'} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="sort">Sort</Label>
        <select id="sort" className={selectClass} value={sort} disabled={!!busy} onChange={e => setSort(e.target.value)}>
          <option value="relevance">{source === 'jobicy' ? 'Catalog order' : source==='jobopportunities'?'Newest listings':'Relevance'}</option>{source!=='jobopportunities'&&<option value="pubdate-desc">Newest published</option>}
        </select>
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2 lg:col-span-2">
        <label className="flex items-start gap-2 text-sm text-muted-foreground">
          <input type="checkbox" className="mt-0.5 size-4 rounded border border-input accent-[var(--forest)]"
            checked={source === 'jobicy' || remote} disabled={!!busy || source === 'jobicy'}
            onChange={e => setRemote(e.target.checked)}
            aria-label={source === 'jobicy' ? 'Remote listings (all Jobicy results)' : source==='jobopportunities'?'Source-confirmed remote only':'Approximate remote matches (source phrase matching)'} />
          <span>{source === 'jobicy' ? 'Remote listings (all Jobicy results)' : source==='jobopportunities'?'Source-confirmed remote only':'Approximate remote matches (source phrase matching)'}</span>
        </label>
        <Button type="submit" disabled={!!busy} className="w-fit">Search {sources[source]?.label || 'jobs'}</Button>
      </div>
    </form>
    <details className="my-6 max-w-3xl text-sm leading-relaxed text-muted-foreground"><summary className="min-h-11 cursor-pointer font-medium text-foreground">Coverage and search limitations</summary><p className="my-6 max-w-3xl text-sm leading-relaxed text-muted-foreground">{sources[source]?.coverage} Workplace location does not establish applicant eligibility. Verify eligibility and authorization with the employer. Worldwide public results show only the first 50 matches; refine filters for more. JobTech accepts one geography filter at a time and its remote matches are approximate. Jobicy eligibility matches only its recent cached catalog. There is no JobPilot job-search quota.</p></details>
    {busy && <p role="status" className="text-sm text-muted-foreground">{busy}</p>}
    {error && <Alert variant="destructive" className="mt-2">{error}</Alert>}
    {saved && <div role="status" className="my-4 rounded-lg border border-[#cfe0d5] bg-[#eef5f1] p-4 text-sm">
      <p>{saved.duplicate ? 'Already saved. Your edits were preserved.' : 'Job imported. Review it, then create a tailored CV and cover letter from evidenced skills.'}</p>
      <Link className="mt-2 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${saved.id}`}>Open saved job</Link>
      <Link className="mt-2 ml-4 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${saved.id}#materials`}>Create tailored application pack</Link>
    </div>}
    {preview && !saved && <section className="mt-6 rounded-lg border border-[#c4c8bf] bg-[#f2f5ee] p-6 [overflow-wrap:anywhere]" aria-labelledby="preview-heading">
      <h2 id="preview-heading" tabIndex={-1} ref={previewHeading} className="font-serif text-2xl leading-snug text-[var(--ink)]">Preview: {preview.job.title}</h2>
      <p className="mt-2">{preview.job.company}</p>
      {preview.job.test_data && <p className="mt-2 text-sm text-muted-foreground">Synthetic test listing — not a live result</p>}
      <a className="mt-3 inline-block text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={preview.job.source_url} target="_blank" rel="noopener noreferrer">View source listing</a>
      <p className="mt-3 whitespace-pre-line">Source: {sources[preview.job.source]?.label || preview.job.source}{preview.job.upstream_source?` / ${preview.job.upstream_source}`:''}</p>
      {preview.job.remote_inferred&&<p role="note">Remote status was inferred by the source; confirm the arrangement with the employer.</p>}
      <Details job={preview.job} />
      <PossibleDuplicates job={preview.job} />
      <h3 className="mt-4 font-serif text-xl leading-snug text-[var(--ink)]">Description</h3>
      <p className="preserve-lines">{preview.job.description || 'No plain-text description supplied. Check the source before importing.'}</p>
      {!preview.job.description&&<p role="alert">AI tailoring needs a job description. Add or confirm one in the saved job before generating a pack.</p>}
      <p className="mt-3 text-sm text-muted-foreground">This saves the previewed snapshot. It will not refresh automatically or overwrite your edits. Preview expires in 15 minutes. Dates and availability should be checked at the source.</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        {preview.job.existing_job_id ? <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${preview.job.existing_job_id}`}>Already saved — open existing job</Link> : <Button disabled={!!busy} onClick={importJob}>Import this job into saved jobs</Button>}
        <Button variant="ghost" disabled={!!busy} onClick={() => setPreview(null)}>Close preview</Button>
      </div>
    </section>}
    {results && <section aria-label="Discovery results">
      <p className="mt-6 text-sm text-muted-foreground">{results.total} {query.source === 'jobicy' ? 'matches in the latest cached catalog' : query.source==='jobopportunities'?'shown from the first 50 source matches':'source matches'}</p>
      {query.source==='jobopportunities'&&<p className="mt-2 max-w-3xl text-sm text-muted-foreground">Worldwide public search shows one page of up to 50 real listings. Refine country, city or keywords to explore other matches. Applicant eligibility is unknown unless the employer states it.</p>}
      {query.source === 'jobicy' && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">Up to 100 recent listings, refreshed at most hourly. Search and pagination filter this cache locally. An empty result does not establish that no vacancy exists. Preview checks availability; saved snapshots do not refresh automatically.</p>}
      {!results.items.length && <div className="mt-6"><EmptyState title="No matching jobs"
        description={query.source === 'jobicy' ? 'Try different keywords or applicant eligibility. This searches only the latest cached catalog.' : 'Try different keywords or broader workplace filters.'} /></div>}
      {results.items.map(job => <article className="my-4 rounded-lg border border-[#c4c8bf] bg-card p-6" key={job.source + job.external_id}>
        <h2 className="font-serif text-2xl leading-snug text-[var(--ink)] [overflow-wrap:anywhere]">{job.title}</h2>
        <p className="mt-1"><strong>{job.company}</strong></p>
        <p className="mt-1 text-sm text-muted-foreground">Source: <a href={sources[job.source]?.attribution_url} target="_blank" rel="noopener noreferrer" className="underline">{sources[job.source]?.label||job.source}</a>{job.upstream_source?` / ${job.upstream_source}`:''}. {job.source==='jobopportunities'?'Employer link supplied by the source.':''}</p>
        {job.remote_inferred&&<p className="mt-1 text-sm text-muted-foreground">Remote status inferred by source; verify with employer.</p>}
        {job.test_data && <p className="mt-2 text-sm text-muted-foreground">Synthetic test listing — not a live result</p>}
        <Details job={job} />
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <a className="text-sm text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={job.source_url} target="_blank" rel="noopener noreferrer">{job.source==='jobopportunities'?'View employer posting':job.source === 'jobicy' ? 'View on Jobicy' : 'View on Platsbanken'}</a>
          {job.existing_job_id ? <Link className="text-sm text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={`/jobs/${job.existing_job_id}`}>Already saved — open existing job</Link> : <Button disabled={!!busy} onClick={() => openPreview(job.external_id, job.source)}>Preview job</Button>}
        </div>
        <PossibleDuplicates job={job} />
      </article>)}
      {query.source!=='jobopportunities'&&<div className="mt-6 flex flex-wrap items-center gap-4">
        <Button variant="outline" size="sm" disabled={!!busy || results.offset === 0} onClick={() => search(Math.max(0, results.offset - 20))}>Previous results</Button>
        <span className="text-sm text-muted-foreground" aria-live="polite">Page {Math.floor(results.offset / 20) + 1}</span>
        <Button variant="outline" size="sm" disabled={!!busy || results.next_offset === null} onClick={() => search(results.next_offset!)}>Next results</Button>
      </div>}
      {results.total > 2000 && <p className="mt-3 text-sm text-muted-foreground">Only the first 2,000 matches are available here. Refine your search.</p>}
    </section>}
    <DigestPanel />
  </div></Shell>;
}
