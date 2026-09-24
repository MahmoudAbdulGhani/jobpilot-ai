'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, Archive, BookmarkSimple, Compass, FileText, LockSimple, MagnifyingGlass, MapPin, Plus, UserCircle } from '@phosphor-icons/react';
import { Shell } from './Shell';
import { JobEditor } from './Dialog';
import { JobRankings } from './JobRankings';
import { api } from '../lib/api';
import type { JobInput, JobList } from '../lib/types';
import { PageHeader } from './ui/page-header';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { LoadingState } from './ui/loading-state';
import { ErrorState } from './ui/error-state';
import { EmptyState } from './ui/empty-state';
import { Pagination } from './ui/pagination';

export function Collection({ archived = false }: { archived?: boolean }) {
  const [data, setData] = useState<JobList | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [create, setCreate] = useState(false);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      setError('');
      api<JobList>(`/jobs?archived=${archived}&search=${encodeURIComponent(search)}&page=${page}&page_size=10`, { signal: controller.signal })
        .then(result => { setData(result); const last = Math.max(1, Math.ceil(result.total / 10)); if (page > last) setPage(last); })
        .catch(e => { if (e.name !== 'AbortError') setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [archived, search, page, version]);
  return <Shell><div className="app-page saved-jobs-page">
    <PageHeader eyebrow={archived ? 'Room for what’s next' : 'Your career, considered'} title={archived ? 'Archive' : 'Saved jobs'} subtitle={archived ? 'A home for opportunities you’ve set aside. Return to them whenever you’re ready.' : 'Keep the possibilities together. Find the next step that feels right.'} actions={!archived ? <Button onClick={() => setCreate(true)}><Plus size={18} aria-hidden="true" />Save a job</Button> : undefined} />
    {!archived && <div className="collection-intro"><span className="intro-icon"><BookmarkSimple size={25} weight="duotone" aria-hidden="true" /></span><div><strong>A shortlist with a little more intention.</strong><p>Save opportunities, add your thoughts, and move forward at your own pace.</p></div><Link href="/discover">Find opportunities <ArrowUpRight size={17} aria-hidden="true" /></Link></div>}
    <div className={`collection-layout${archived ? ' is-archive' : ''}`}>
      <section className="collection-surface" aria-label={archived ? 'Archived opportunities' : 'Saved opportunities'}>
        <div className="collection-surface-heading"><h2>{archived ? 'Archived opportunities' : 'Your shortlist'}</h2>{data && <span className="count-pill">{data.total}</span>}<span className="sort-note"><ArrowDown size={13} aria-hidden="true" />Newest first</span></div>
        <div className="collection-search"><label className="collection-search-field"><span className="sr-only">Search jobs</span><MagnifyingGlass size={18} aria-hidden="true" /><Input value={search} maxLength={200} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search by title or company" /></label></div>
        {error && <div className="collection-state"><ErrorState title="Could not load your jobs" message={error} onRetry={() => setVersion(x => x + 1)} /></div>}
        {loading && <div className="collection-state"><LoadingState label="Loading jobs…" rows={3} /></div>}
        {!loading && !error && data && <><p className="sr-only" role="status">{data.total} {data.total === 1 ? 'opportunity' : 'opportunities'}</p>
          {data.items.length ? <ul className="opportunity-list">{data.items.map((job, index) => <li key={job.id}><Link href={`/jobs/${job.id}`} className="opportunity-row"><span className={`company-monogram tone-${index % 4}`} aria-hidden="true">{job.company.trim().slice(0, 2).toUpperCase()}</span><span className="opportunity-copy"><h3>{job.title}</h3><span className="opportunity-company">{job.company}</span><span className="opportunity-meta">{job.location && <span><MapPin size={13} aria-hidden="true" />{job.location}</span>}<time dateTime={job.created_at}>Saved {new Date(job.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time></span></span><span className="opportunity-arrow"><ArrowRight size={18} aria-hidden="true" /></span></Link></li>)}</ul> : <div className="collection-state"><EmptyState icon={archived ? <Archive size={26} aria-hidden="true" /> : <BookmarkSimple size={26} aria-hidden="true" />} title={search ? 'Nothing found' : archived ? 'Your archive is empty' : 'Save your first opportunity'} description={search ? 'Try a different title or company, or clear your search to see everything.' : archived ? 'Jobs you archive will appear here, ready whenever you are.' : 'Found a role that caught your eye? Keep its details and your private notes in one place.'} action={search ? <Button variant="outline" onClick={() => setSearch('')}>Clear search</Button> : !archived ? <Button onClick={() => setCreate(true)}><Plus size={17} aria-hidden="true" />Save a job</Button> : undefined} /></div>}
          <footer className="collection-pagination"><Pagination page={page} total={data.total} pageSize={10} onPageChange={setPage} ariaLabel="Saved jobs pagination" /><span><LockSimple size={12} aria-hidden="true" />Only visible to you</span></footer>
        </>}
      </section>
      {!archived && <aside className="collection-aside" aria-label="Career tools"><JobRankings /><section className="next-step-card"><p className="eyebrow">A strong foundation</p><h2>Ready for your next move?</h2><p>The little things you prepare today make your next application easier.</p><Link href="/profile"><span className="tool-link-icon"><UserCircle size={21} aria-hidden="true" /></span><span><strong>Refine your profile</strong><small>Keep your experience up to date</small></span><ArrowUpRight size={17} aria-hidden="true" /></Link><Link href="/resumes"><span className="tool-link-icon"><FileText size={21} aria-hidden="true" /></span><span><strong>Organize your resumes</strong><small>Put your best version forward</small></span><ArrowUpRight size={17} aria-hidden="true" /></Link></section><p className="collection-aside-note"><Compass size={16} aria-hidden="true" />Small steps. Meaningful progress.</p></aside>}
    </div>
    {create && <JobEditor onClose={() => setCreate(false)} onSave={async (values: JobInput) => { await api('/jobs', { method: 'POST', body: JSON.stringify(values) }); setCreate(false); setVersion(x => x + 1); }} />}
  </div></Shell>;
}
