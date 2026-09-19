'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type MatrixRow = {
  domain: string; fields_used: string[]; used_for: string[]; provider: string;
  retention: string; consent_key: string | null; required: boolean; allowed: boolean; managed_by: string;
};

export function PrivacyMatrix() {
  const [rows, setRows] = useState<MatrixRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    try {
      const matrix = await api<{ rows: MatrixRow[] }>('/privacy/matrix');
      setRows(Array.isArray(matrix.rows) ? matrix.rows : []);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => { void load(); }, []);

  async function toggle(row: MatrixRow) {
    if (!row.consent_key) return;
    setBusy(true);
    setError('');
    try {
      await api('/privacy/consents', {
        method: 'PATCH', body: JSON.stringify({ key: row.consent_key, allowed: !row.allowed, confirm: true }),
      });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="privacy-matrix" aria-label="Data use and privacy">
    <div className="section-title"><div>
      <p className="eyebrow">Privacy controls</p>
      <h2>How your data is used</h2>
      <p className="muted">Optional AI uses are denied by default. Advisory features on this page never send data anywhere. Toggling consent only records your posture for that AI use; each AI action still asks you explicitly.</p>
    </div></div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {rows.length === 0 && !error && <p className="notice">Loading data-use matrix…</p>}
    <ul className="matrix-list">
      {rows.map(row => <li key={row.domain} className="mailbox-card">
        <p><strong>{row.domain}</strong> {row.required
          ? <span className="muted">(required for the journal to work)</span>
          : row.consent_key
            ? <span className="muted">(optional, {row.allowed ? 'allowed' : 'denied'})</span>
            : <span className="muted">(managed {row.managed_by === 'connection' ? 'by your mailbox connection in Settings' : `by your explicit ${row.managed_by}`})</span>}</p>
        <p className="muted">Fields: {row.fields_used.join(', ')}</p>
        <p className="muted">Used for: {row.used_for.join('; ')}</p>
        <p className="muted">Provider: {row.provider} · Retention: {row.retention}</p>
        {row.consent_key && <button disabled={busy} onClick={() => void toggle(row)}>{row.allowed ? `Deny ${row.domain} AI use` : `Allow ${row.domain} AI use`}</button>}
      </li>)}
    </ul>
  </section>;
}
