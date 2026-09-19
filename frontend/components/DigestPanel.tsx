'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type DigestItem = {
  source: string; external_id: string; title: string; company: string; location: string | null;
  source_url: string; published_at: string | null; salary: string | null; workplace_model: string | null;
  applicant_region: string | null; remote_arrangement: string; test_data: boolean; refreshed_at: string | null;
};
type DigestPreview = {
  generated_at: string; cadence: string; items: DigestItem[]; skipped_invalid: number;
  delivery: { enabled: boolean; reason: string };
};

const CADENCES = ['off', 'daily', 'weekly'];

export function DigestPanel() {
  const [cadence, setCadence] = useState('off');
  const [preview, setPreview] = useState<DigestPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api<{ cadence: string }>('/digest/preferences')
      .then(prefs => { if (active && typeof prefs?.cadence === 'string') setCadence(prefs.cadence); })
      .catch(() => { if (active) setCadence('off'); });
    return () => { active = false; };
  }, []);

  async function save(next: string) {
    setBusy(true);
    setError('');
    try {
      const updated = await api<{ cadence: string }>('/digest/preferences', {
        method: 'PUT', body: JSON.stringify({ cadence: next, confirm: true }),
      });
      setCadence(updated.cadence);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    setBusy(true);
    setError('');
    try {
      const data = await api<DigestPreview>('/digest/preview');
      if (data && Array.isArray(data.items) && data.delivery) setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="digest-panel" aria-label="Daily digest">
    <div className="section-title"><div>
      <p className="eyebrow">Digest</p>
      <h2>Daily digest</h2>
      <p className="muted">Validated JobTech and Jobicy records with source attribution and timestamps. Delivery is disabled: no delivery provider is configured, so digests are previews you read here.</p>
    </div></div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    <div className="digest-controls">
      <label><span>Cadence</span><select value={cadence} disabled={busy} onChange={e => void save(e.target.value)}>
        {CADENCES.map(item => <option key={item} value={item}>{item === 'off' ? 'Off' : item === 'daily' ? 'Daily' : 'Weekly'}</option>)}
      </select></label>
      <button className="primary-button" disabled={busy} onClick={() => void loadPreview()}>{busy ? 'Loading…' : 'Preview digest'}</button>
    </div>
    {preview && <>
      <p className="muted">Generated {new Date(preview.generated_at).toLocaleString()} · cadence {preview.cadence} · {preview.skipped_invalid} invalid {preview.skipped_invalid === 1 ? 'record' : 'records'} skipped.</p>
      <p className="notice" role="status">Delivery disabled: {preview.delivery.reason}</p>
      {preview.items.length === 0 && <p className="notice empty-state">No validated listings cached yet.</p>}
      <ul className="digest-list">
        {preview.items.map(item => <li key={`${item.source}-${item.external_id}`}>
          <p><strong>{item.title}</strong> · {item.company}</p>
          <p className="muted">Source: {item.source} · {item.published_at ? <>published <time dateTime={item.published_at}>{item.published_at}</time></> : 'no published date'} · refreshed {item.refreshed_at ? new Date(item.refreshed_at).toLocaleString() : 'unknown'}</p>
          {item.test_data && <p className="muted">Synthetic test listing — not a live result.</p>}
          <p><a href={item.source_url} target="_blank" rel="noopener noreferrer">View source listing</a></p>
        </li>)}
      </ul>
    </>}
  </section>;
}
