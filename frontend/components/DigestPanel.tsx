'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { FormField } from './ui/form-field';
import { Button } from './ui/button';
import { Alert } from './ui/alert';

type DigestItem = {
  source: string; external_id: string; title: string; company: string; location: string | null;
  source_url: string; published_at: string | null; salary: string | null; workplace_model: string | null;
  applicant_region: string | null; remote_arrangement: string; test_data: boolean; refreshed_at: string | null;
};
type DigestPreview = {
  recipient: string; subject: string; body: string; preview_token: string;
  generated_at: string; cadence: string; items: DigestItem[]; skipped_invalid: number;
  delivery: { enabled: boolean; reason: string };
};
type SendReceipt = {
  sent_at: string; recipient: string; items: number; transport: string;
  delivery: { enabled: boolean; reason: string };
};

const CADENCES = ['off', 'daily', 'weekly'];

export function DigestPanel() {
  const [cadence, setCadence] = useState('off');
  const [preview, setPreview] = useState<DigestPreview | null>(null);
  const [receipt, setReceipt] = useState<SendReceipt | null>(null);
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

  async function sendNow() {
    if (!preview) return;
    setBusy(true);
    setError('');
    setReceipt(null);
    try {
      const data = await api<SendReceipt>('/digest/send', {
        method: 'POST', body: JSON.stringify({ confirm: true, preview_token: preview.preview_token }),
      });
      if (data && data.sent_at) setReceipt(data);
      setPreview(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="mt-6 rounded-lg border border-border bg-card p-6" aria-label="Daily digest">
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold uppercase tracking-[0.04em] text-[var(--forest)]">Digest</p>
      <h2 className="font-serif text-3xl leading-snug text-[var(--ink)]">Daily digest</h2>
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">Fresh Jobicy catalog records with source attribution. Review the exact email before sending. Scheduled delivery is not enabled.</p>
    </div>
    {error && <Alert variant="destructive" className="mt-4">{error}</Alert>}
    <div className="mt-4 flex flex-wrap items-end gap-4">
      <FormField label="Cadence" htmlFor="digest-cadence" className="w-44">
        <select id="digest-cadence" className="h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          value={cadence} disabled={busy} onChange={e => void save(e.target.value)}>
          {CADENCES.map(item => <option key={item} value={item}>{item === 'off' ? 'Off' : item === 'daily' ? 'Daily' : 'Weekly'}</option>)}
        </select>
      </FormField>
      <Button variant="outline" disabled={busy} onClick={() => void loadPreview()}>{busy ? 'Loading…' : 'Preview digest'}</Button>
      <Button disabled={busy || !preview?.delivery.enabled || !preview?.preview_token} onClick={() => void sendNow()}>{busy ? 'Sending…' : 'Approve and send reviewed digest'}</Button>
    </div>
    {preview && <div className="mt-6 space-y-3">
      <p className="text-sm text-muted-foreground">To: {preview.recipient}</p>
      <p className="text-sm text-muted-foreground">Subject: {preview.subject}</p>
      <pre className="digest-body whitespace-pre-wrap rounded-md border border-border bg-[var(--paper)] p-4 [overflow-wrap:anywhere]">{preview.body}</pre>
      <p className="text-sm text-muted-foreground">Generated {new Date(preview.generated_at).toLocaleString()} · cadence {preview.cadence} · {preview.skipped_invalid} invalid {preview.skipped_invalid === 1 ? 'record' : 'records'} skipped.</p>
      <p role="status" className="text-sm text-muted-foreground">Delivery {preview.delivery.enabled ? 'ready' : 'disabled'}: {preview.delivery.reason}</p>
      {preview.items.length === 0 && <p className="text-sm text-muted-foreground">No validated listings cached yet.</p>}
      {preview.items.length > 0 && <ul className="grid list-disc gap-3 pl-6 text-sm text-muted-foreground">
        {preview.items.map(item => <li key={`${item.source}-${item.external_id}`} className="[overflow-wrap:anywhere]">
          <p><strong className="font-semibold text-foreground">{item.title}</strong> · {item.company}</p>
          <p className="mt-1">Source: {item.source} · {item.published_at ? <>published <time dateTime={item.published_at}>{item.published_at}</time></> : 'no published date'} · refreshed {item.refreshed_at ? new Date(item.refreshed_at).toLocaleString() : 'unknown'}</p>
          {item.test_data && <p>Synthetic test listing — not a live result.</p>}
          <a className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={item.source_url} target="_blank" rel="noopener noreferrer">View source listing</a>
        </li>)}
      </ul>}
    </div>}
    {receipt && <p role="status" className="mt-4 text-sm text-muted-foreground">Sent {new Date(receipt.sent_at).toLocaleString()} to {receipt.recipient} ({receipt.items} items via {receipt.transport}).</p>}
  </section>;
}