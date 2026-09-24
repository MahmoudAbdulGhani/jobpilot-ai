'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { RankRun, RankRunList } from '../lib/types';
import { Button } from './ui/button';
import { ErrorState } from './ui/error-state';
import { LoadingState } from './ui/loading-state';

export function JobRankings() {
  const [run, setRun] = useState<RankRun | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadLatest() {
    try {
      const list = await api<RankRunList>('/rankings?page=1&page_size=1');
      setTotal(list.total);
      if (list.items.length > 0) {
        const full = await api<RankRun>(`/rankings/${list.items[0].id}`);
        setRun(full);
      } else {
        setRun(null);
      }
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadLatest(); }, []);

  async function rank() {
    setBusy(true);
    setError('');
    try {
      const created = await api<RankRun>('/rankings', { method: 'POST', body: JSON.stringify({}) });
      setRun(created);
      setTotal(value => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="ranking-card" aria-label="Cross-job ranking">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow">Advisory ranking</p>
        <h2 className="mt-2 font-serif text-3xl leading-snug text-[var(--ink)]">Rank saved jobs</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">Deterministic comparison of your saved jobs against your saved profile facts. Advisory only; never a hiring prediction.</p>
      </div>
      <Button disabled={busy} onClick={() => void rank()}>{busy ? 'Ranking…' : run ? 'Rank again' : 'Rank saved jobs'}</Button>
    </div>
    {loading && <div className="mt-4"><LoadingState label="Loading ranking…" rows={2} /></div>}
    {error && <div className="mt-4"><ErrorState title="Could not load the ranking" message={error} onRetry={() => { setLoading(true); void loadLatest(); }} /></div>}
    {!loading && !error && run === null && total === 0 && <p className="ranking-empty">No ranking yet. Add your profile and saved jobs, then run a comparison when you’re ready.</p>}
    {run && run.is_stale && <p className="mt-4 rounded-lg border border-[#e5d9b8] bg-[#faf3e0] p-4 text-sm text-[var(--warning)]" role="status">This ranking is outdated: your profile or a ranked job changed. Rank again for current results.</p>}
    {run && run.items && run.items.length > 0 && <ol className="mt-5 grid gap-4">
      {run.items.map(item => <li className="rounded-lg border border-border bg-[var(--paper)] p-5" key={item.job_id}>
        <div className="flex items-center gap-4">
          <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-[var(--forest)] font-sans text-lg font-bold text-white" aria-label={`Score ${item.score} out of 100`}>{item.score}</span>
          <div className="min-w-0"><strong className="font-sans text-[17px] font-semibold leading-snug text-foreground">{item.title}</strong><p className="mt-0.5 text-sm text-muted-foreground">{item.company}</p></div>
        </div>
        <p className="mt-3 font-semibold text-foreground">{item.recommended_action}</p>
        {item.reasons.length > 0 && <details className="mt-2">
          <summary className="cursor-pointer text-[var(--forest)] hover:underline">Why this score ({item.reasons.length} {item.reasons.length === 1 ? 'reason' : 'reasons'})</summary>
          <ul className="mt-3 grid list-disc gap-3 pl-6">{item.reasons.map((reason, index) => <li key={index}>
            <p>{reason.text}</p>
            <p className="mt-1 text-sm text-muted-foreground">Job says: “{reason.evidence.job_quote}”</p>
            <p className="text-sm text-muted-foreground">Profile says: “{reason.evidence.profile_fact}”</p>
          </li>)}</ul>
        </details>}
        {item.missing_skills.length > 0 && <p className="mt-2 text-sm"><strong className="font-semibold">Missing from profile:</strong> {item.missing_skills.join(', ')}</p>}
        {item.risks.length > 0 && <ul className="mt-2 list-disc pl-6 text-sm text-destructive">{item.risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul>}
      </li>)}
    </ol>}
    {run && (!run.items || run.items.length === 0) && <p className="mt-4 text-sm text-muted-foreground">No ranked jobs in this run.</p>}
    {total > 1 && <p className="mt-4 text-sm text-muted-foreground">{total} ranking runs saved; showing the latest.</p>}
  </section>;
}
