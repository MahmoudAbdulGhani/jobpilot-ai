'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { AtsCheck, AtsReport } from '../lib/types';

type PackSummary = { id: string; current_version: number; status: string };
type PackList = { items: PackSummary[] };
type PackVersion = { number: number; approved_at: string | null };
type PackVersionList = { items: PackVersion[] };
type ImproveResult = {
  report_id: string; job_id: string; pack_id: string; approved_version: number;
  version_number: number; review_notes: string[];
  preview_checks: AtsCheck[]; preview_readiness: number;
};

export function AtsReport({ job }: { job: { id: string } }) {
  const [packs, setPacks] = useState<PackSummary[]>([]);
  const [packId, setPackId] = useState('');
  const [versions, setVersions] = useState<PackVersion[]>([]);
  const [version, setVersion] = useState<number | null>(null);
  const [report, setReport] = useState<AtsReport | null>(null);
  const [improved, setImproved] = useState<ImproveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadVersions = useCallback((target: string) => {
    let active = true;
    api<PackVersionList>(`/jobs/${job.id}/application-packs/${target}/versions?page=1&page_size=20`)
      .then(list => {
        if (!active) return;
        setVersions(list.items);
        const approved = list.items.filter(item => item.approved_at).map(item => item.number);
        setVersion(approved.length > 0 ? Math.max(...approved) : null);
      })
      .catch(e => { if (active) setError((e as Error).message); });
    return () => { active = false; };
  }, [job.id]);

  useEffect(() => {
    let active = true;
    api<PackList>(`/jobs/${job.id}/application-packs?page=1&page_size=20`)
      .then(list => { if (active) { setPacks(list.items); if (list.items.length > 0) { setPackId(list.items[0].id); loadVersions(list.items[0].id); } } })
      .catch(e => { if (active) setError((e as Error).message); });
    return () => { active = false; };
  }, [job.id, loadVersions]);

  useEffect(() => {
    if (!packId) { setVersions([]); setReport(null); return; }
    let active = true;
    api<AtsReport | null>(`/jobs/${job.id}/packs/${packId}/ats-reports/latest`)
      .then(latest => { if (active) { setReport(latest); if (!latest) setImproved(null); } })
      .catch(() => { if (active) setReport(null); });
    return () => { active = false; };
  }, [job.id, packId]);

  async function check() {
    if (!packId || version === null) return;
    setBusy(true);
    setError('');
    try {
      const created = await api<AtsReport>(`/jobs/${job.id}/packs/${packId}/ats-reports`, {
        method: 'POST', body: JSON.stringify({ pack_version: version }),
      });
      setReport(created);
      setImproved(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function improve() {
    if (!packId || !report) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<ImproveResult>(
        `/jobs/${job.id}/packs/${packId}/ats-reports/${report.id}/improve`, {
          method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
        });
      setImproved(result);
      loadVersions(packId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const approvedVersions = versions.filter(item => item.approved_at);

  return <section className="ats-panel" aria-label="ATS readiness report">
    <div className="section-title">
      <div>
        <p className="eyebrow">Readiness check</p>
        <h2>ATS readiness</h2>
        <p className="muted">Deterministic checks of an approved pack against this job. Explicit findings only. Improvements create a new unapproved draft you review before it can be checked again.</p>
      </div>
    </div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {packs.length === 0 && <p className="notice empty-state">No application packs for this job yet.</p>}
    {packs.length > 0 && <div className="ats-controls">
      <label><span>Approved pack</span><select value={packId} onChange={e => { setPackId(e.target.value); setImproved(null); }}>
        {packs.map(pack => <option key={pack.id} value={pack.id}>{pack.status === 'ready' ? 'Approved pack' : 'Pack'} · v{pack.current_version}</option>)}
      </select></label>
      <label><span>Approved version</span><select value={version ?? ''} onChange={e => setVersion(e.target.value ? Number(e.target.value) : null)}>
        {approvedVersions.length === 0 && <option value="">No approved version</option>}
        {approvedVersions.map(item => <option key={item.number} value={item.number}>Version {item.number}</option>)}
      </select></label>
      <button className="primary-button" disabled={busy || version === null} onClick={() => void check()}>{busy ? 'Checking…' : 'Check readiness'}</button>
      {report && <button className="secondary-button" disabled={busy} onClick={() => void improve()} title="Generate a new draft revision from the findings of this report. The draft stays for your review until you approve it.">{busy ? 'Working…' : 'Improve from this report'}</button>}
    </div>}
    {report && <div className="ats-report">
      <p className="ats-score">Readiness {report.readiness_score} / 100 <span className="muted">· version {report.pack_version} · {report.report_version}</span></p>
      <ul className="ats-checks">
        {report.checks.map(item => <li key={item.id} className={`ats-check is-${item.status}`}>
          <p><strong>{item.label}</strong> <span className={`status-badge is-${item.status === 'pass' ? 'confirmed' : item.status === 'warn' ? 'interview' : 'rejected'}`}>{item.status}</span></p>
          <p>{item.detail}</p>
          <ul>{item.evidence.map((line, index) => <li key={index} className="muted">{line}</li>)}</ul>
        </li>)}
      </ul>
    </div>}
    {improved && <div className="ats-improved" aria-label="Improved draft preview">
      <p className="notice" role="status">Improved draft version {improved.version_number} created from approved version {improved.approved_version}. It is not approved yet: review and approve it, then run Check readiness for a persisted report.</p>
      <h3>Draft preview (not persisted)</h3>
      <p className="ats-score muted">Ready readiness estimate {improved.preview_readiness} / 100</p>
      <ul className="ats-checks">
        {improved.preview_checks.map(item => <li key={item.id} className={`ats-check is-${item.status}`}>
          <p><strong>{item.label}</strong> <span className={`status-badge is-${item.status === 'pass' ? 'confirmed' : item.status === 'warn' ? 'interview' : 'rejected'}`}>{item.status}</span></p>
          <p>{item.detail}</p>
          <ul>{item.evidence.map((line, index) => <li key={index} className="muted">{line}</li>)}</ul>
        </li>)}
      </ul>
      <h3>Review notes</h3>
      <ul>{improved.review_notes.map((note, index) => <li key={index} className="muted">{note}</li>)}</ul>
    </div>}
  </section>;
}
