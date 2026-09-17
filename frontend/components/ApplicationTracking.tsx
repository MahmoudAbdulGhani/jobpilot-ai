'use client';
import { useCallback, useEffect, useState } from 'react';
import { CheckCircle } from '@phosphor-icons/react';
import { api } from '../lib/api';
import { ReplyTimeline } from './ReplyTimeline';
import type { ApplicationEventList, ApplicationMethod, ApplicationRecord, ApplicationRecordList, ApplicationStatus } from '../lib/types';
import type { ApplicationPack, PackPage, PackVersion, PackVersionList } from '../lib/application-packs';

export function ApplicationTracking({ job }: { job: { id: string } }) {
  const base = `/jobs/${job.id}/applications`;
  const packBase = `/jobs/${job.id}/application-packs`;
  const [record, setRecord] = useState<ApplicationRecord | null>(null);
  const [events, setEvents] = useState<ApplicationEventList | null>(null);
  const [packs, setPacks] = useState<ApplicationPack[]>([]);
  const [packVersions, setPackVersions] = useState<PackVersion[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<ApplicationStatus>('Applied');
  const [method, setMethod] = useState<ApplicationMethod>('email');
  const [notes, setNotes] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [submission, setSubmission] = useState(new Date().toISOString().slice(0, 10));
  const [packId, setPackId] = useState<string | null>(null);
  const [packVersion, setPackVersion] = useState<number | null>(null);

  const resetForm = (item: ApplicationRecord | null) => {
    setRecord(item);
    setStatus(item?.status ?? 'Applied');
    setMethod(item?.method ?? 'email');
    setNotes(item?.notes ?? '');
    setFollowUp(item?.follow_up_date ? item.follow_up_date.slice(0, 10) : '');
    setSubmission(item?.submission_date ? item.submission_date.slice(0, 10) : new Date().toISOString().slice(0, 10));
    setPackId(item?.pack_id ?? null);
    setPackVersion(item?.pack_version ?? null);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, packResult] = await Promise.all([
        api<ApplicationRecordList>(`${base}?page=1&page_size=10`),
        api<PackPage<ApplicationPack>>(`${packBase}?page=1&page_size=50`),
      ]);
      const item = list.items[0] ?? null;
      resetForm(item);
      const readyPacks = (packResult.items ?? []).filter(pack => pack.status === 'ready' && pack.current_version > 0);
      setPacks(readyPacks);
      if (item?.pack_id) {
        const versionList = await api<PackVersionList>(`${packBase}/${item.pack_id}/versions?page=1&page_size=50`);
        setPackVersions(versionList.items.filter(item => item.approved_at !== null));
      } else {
        setPackVersions([]);
      }
      if (item) {
        const eventList = await api<ApplicationEventList>(`${base}/${item.id}/events?page=1&page_size=10`);
        setEvents(eventList);
      } else {
        setEvents(null);
      }
    } catch (e) {
      setRecord(null);
      setEvents(null);
      setPacks([]);
      setPackVersions([]);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [base, packBase]);

  useEffect(() => { void load(); }, [load]);

  const selectedPack = packs.find(pack => pack.id === packId);

  useEffect(() => {
    async function refreshVersions() {
      if (!packId) {
        setPackVersions([]);
        return;
      }
      try {
        const versionList = await api<PackVersionList>(`${packBase}/${packId}/versions?page=1&page_size=50`);
        setPackVersions(versionList.items.filter(version => version.approved_at !== null));
      } catch {
        setPackVersions([]);
      }
    }
    void refreshVersions();
  }, [packId, packBase]);

  async function createOrUpdate(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        submission_date: new Date(submission).toISOString(),
        method,
        notes: notes || null,
        follow_up_date: followUp ? new Date(followUp).toISOString() : null,
        status,
        pack_id: packId ?? null,
        pack_version: packVersion ?? null,
      };
      if (!record) {
        const created = await api<ApplicationRecord>(base, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        resetForm(created);
      } else {
        const updated = await api<ApplicationRecord>(`${base}/${record.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
        resetForm(updated);
      }
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteApplication() {
    if (!record) return;
    setSaving(true);
    try {
      await api(`${base}/${record.id}`, { method: 'DELETE' });
      resetForm(null);
      setEvents(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return <section className="application-tracking">
    <div className="section-title"><h2>Application tracking</h2></div>
    <button type="button" disabled={saving} onClick={()=>void load()}>Refresh saved tracking (replaces unsaved form edits)</button>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    {loading && <p className="notice">Loading application…</p>}
    {!loading && !record && <p className="notice empty-state">No application record yet.</p>}
    <form className="tracking-form" onSubmit={createOrUpdate}>
      <div className="tracking-grid">
        <label><span>Submission date</span><input type="date" value={submission} onChange={e => setSubmission(e.target.value)} required /></label>
        <label><span>Method</span><select value={method} onChange={e => setMethod(e.target.value as ApplicationMethod)}><option value="email">email</option><option value="employer_website">employer website</option><option value="linkedin_manual">LinkedIn manually</option><option value="other">other</option></select></label>
        <label><span>Status</span><select value={status} onChange={e => setStatus(e.target.value as ApplicationStatus)}><option>Applied</option><option>Interview</option><option>Offer</option><option>Rejected</option><option>Withdrawn</option></select></label>
        <label><span>Follow up date</span><input type="date" value={followUp} onChange={e => setFollowUp(e.target.value)} /></label>
      </div>
      <div className="tracking-grid">
        <label><span>Approved pack</span><select value={packId ?? ''} onChange={e => { const id = e.target.value || null; setPackId(id); setPackVersion(null); }}>
          <option value="">None selected</option>
          {packs.map(pack => <option key={pack.id} value={pack.id}>{pack.source_snapshot.resume_name || 'Approved pack'}</option>)}
        </select></label>
        <label><span>Pack version</span><select value={packVersion ?? ''} onChange={e => setPackVersion(e.target.value ? Number(e.target.value) : null)} disabled={!packId || packVersions.length === 0}>
          <option value="">Choose version</option>
          {packVersions.map(version => <option key={version.number} value={version.number}>v{version.number}</option>)}
        </select></label>
      </div>
      <label><span>Notes</span><textarea value={notes} onChange={e => setNotes(e.target.value)} rows={4} placeholder="Optional notes"></textarea></label>
      <div className="tracking-actions">
        <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : (record ? 'Save changes' : 'Record application')}</button>
        {record && <button className="text-button" type="button" disabled={saving} onClick={deleteApplication}>Delete</button>}
      </div>
    </form>
    {record && events && <section className="tracking-events">
      <h3>Status history</h3>
      <ul>{events.items.map(item => <li key={item.id}><span><CheckCircle size={18}/>{item.status}</span><time>{new Date(item.changed_at).toLocaleDateString()}</time></li>)}</ul>
    </section>}
    {selectedPack && !selectedPack.version && <p className="notice">No approved version selected yet.</p>}
    <ReplyTimeline jobId={job.id}/>
  </section>
}
