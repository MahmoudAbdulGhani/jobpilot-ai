'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { RankRun, RankRunList } from '../lib/types';

export function JobRankings() {
  const [run, setRun] = useState<RankRun | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
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
    } catch (e) {
      setError((e as Error).message);
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

  return <section className="ranking-panel" aria-label="Cross-job ranking">
    <div className="section-title">
      <div>
        <p className="eyebrow">Advisory ranking</p>
        <h2>Rank saved jobs</h2>
        <p className="muted">Deterministic comparison of your saved jobs against your saved profile facts. Advisory only; never a hiring prediction.</p>
      </div>
      <button className="primary-button" disabled={busy} onClick={() => void rank()}>{busy ? 'Ranking…' : run ? 'Rank again' : 'Rank saved jobs'}</button>
    </div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {run && run.is_stale && <p className="notice" role="status">This ranking is outdated: your profile or a ranked job changed. Rank again for current results.</p>}
    {run && run.items && run.items.length > 0 && <ol className="ranking-list">
      {run.items.map(item => <li className="ranking-row" key={item.job_id}>
        <div className="ranking-row-top">
          <span className="ranking-score" aria-label={`Score ${item.score} out of 100`}>{item.score}</span>
          <div><strong>{item.title}</strong><p className="muted">{item.company}</p></div>
        </div>
        <p className="ranking-action">{item.recommended_action}</p>
        {item.reasons.length > 0 && <details className="ranking-evidence">
          <summary>Why this score ({item.reasons.length} {item.reasons.length === 1 ? 'reason' : 'reasons'})</summary>
          <ul>{item.reasons.map((reason, index) => <li key={index}>
            <p>{reason.text}</p>
            <p className="muted">Job says: “{reason.evidence.job_quote}”</p>
            <p className="muted">Profile says: “{reason.evidence.profile_fact}”</p>
          </li>)}</ul>
        </details>}
        {item.missing_skills.length > 0 && <p className="ranking-missing"><strong>Missing from profile:</strong> {item.missing_skills.join(', ')}</p>}
        {item.risks.length > 0 && <ul className="ranking-risks">{item.risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul>}
      </li>)}
    </ol>}
    {run && (!run.items || run.items.length === 0) && <p className="notice empty-state">No ranked jobs in this run.</p>}
    {total > 1 && <p className="muted">{total} ranking runs saved; showing the latest.</p>}
  </section>;
}
