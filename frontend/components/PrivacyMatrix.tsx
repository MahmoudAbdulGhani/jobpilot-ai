'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { ShieldCheck } from '@phosphor-icons/react';
import { Button } from './ui/button';
import { LoadingState } from './ui/loading-state';
import '@/app/account.css';

type MatrixRow = {
  domain: string; fields_used: string[]; used_for: string[]; provider: string;
  retention: string; consent_key: string | null; required: boolean; allowed: boolean; managed_by: string;
};

export function PrivacyMatrix() {
  const [rows, setRows] = useState<MatrixRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function load() {
    setError('');
    try {
      const matrix = await api<{ rows: MatrixRow[] }>('/privacy/matrix');
      setRows(Array.isArray(matrix.rows) ? matrix.rows : []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
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

  return <section id="privacy" className="account-settings-section" aria-label="Data use and privacy">
    <div className="account-section-heading"><div className="account-section-symbol"><ShieldCheck size={22} aria-hidden="true"/></div><div>
      <h2>How your data is used</h2>
      <p>Clear permissions. Decisions that stay with you.</p>
    </div></div>
    <p className="account-section-intro">Optional AI uses are denied by default. Toggling consent only records your preference for that AI use; each AI action still asks you explicitly. Advisory features on this page never send data anywhere.</p>
    {error && <div className="account-alert account-alert-error"><p role="alert">{error}</p><Button variant="outline" size="sm" onClick={()=>void load()}>Retry privacy settings</Button></div>}
    {loading && !error && <LoadingState label="Loading data-use matrix…" rows={3}/>}
    {!loading && rows.length===0 && !error && <p className="account-alert">No data-use permissions are available to display.</p>}
    <ul className="account-privacy-list">
      {rows.map(row => <li key={row.domain} className="account-surface account-privacy-row">
        <div className="account-privacy-title"><div><h3>{row.domain}</h3>{row.required
          ? <span className="account-permission-state">(required for the journal to work)</span>
          : row.consent_key
            ? <span className={`account-permission-state ${row.allowed?'is-allowed':''}`}>(optional, {row.allowed ? 'allowed' : 'denied'})</span>
            : <span className="account-permission-state">(managed {row.managed_by === 'connection' ? 'by your mailbox connection in Settings' : `by your explicit ${row.managed_by}`})</span>}</div>
        {row.consent_key?<Button variant="outline" size="sm" disabled={busy} aria-busy={busy} onClick={() => void toggle(row)}>{row.allowed ? `Deny ${row.domain} AI use` : `Allow ${row.domain} AI use`}</Button>:<span className="account-pill account-pill-neutral">{row.required?'Required':'Managed separately'}</span>}</div>
        <dl className="account-privacy-details"><div><dt>Information used</dt><dd>{row.fields_used.join(', ')||'None specified'}</dd></div><div><dt>Purpose</dt><dd>{row.used_for.join('; ')||'None specified'}</dd></div><div><dt>Provider</dt><dd>{row.provider}</dd></div><div><dt>Retention</dt><dd>{row.retention}</dd></div></dl>
      </li>)}
    </ul>
  </section>;
}
