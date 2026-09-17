'use client';

import Link from 'next/link';
import {useCallback, useEffect, useState} from 'react';
import {api, downloadResume} from '../lib/api';

type Version = {pack_id:string;number:number;approved_at:string};
type Mailbox = {id:string;email:string;status:string;capabilities:string[];provider:string};
type Attempt = {id:string;status:string;outcome:string|null;snapshot_hash:string;provider_status:number|null;
  provider_message_id:string|null;application_id:string|null;
  snapshot:{sender:string;recipient:string;recipient_source:string;subject:string;body:string;provider:string;pack_version:number};
  attachments:{name:string;size:number;sha256:string}[]};
const outcomes:Record<string,string> = {
  review:'Review the exact message and both attachments before approving Send.',
  queued:'Approved and queued. Check status before taking any further action; do not create another submission.',
  sending:'Dispatch is pending. Do not resend. Refresh status to check the recorded result.',
  sent:'Gmail accepted this email. Recipient delivery and reading are not confirmed.',
  simulated:'Synthetic provider accepted the test message. No email was sent and no application was marked submitted.',
  unknown:'Delivery is unknown. The email may have been sent. Do not resend; check Gmail manually. JobPilot will not read your inbox.',
  failed:'This attempt did not receive provider acceptance. Review the result below before preparing any new submission.',
  cancelled:'This review was cancelled. Its approval cannot be used to send.',
};
const message = (error:unknown) => error instanceof Error ? error.message : 'The operation could not be completed.';

export function EmailApplication({job}:{job:{id:string;title:string}}) {
  const base=`/jobs/${job.id}/email-applications`;
  const [versions,setVersions]=useState<Version[]>([]),[mailboxes,setMailboxes]=useState<Mailbox[]>([]);
  const [attempt,setAttempt]=useState<Attempt|null>(null),[editing,setEditing]=useState(false);
  const [version,setVersion]=useState(''),[mailbox,setMailbox]=useState('');
  const [recipient,setRecipient]=useState(''),[confirmRecipient,setConfirmRecipient]=useState('');
  const [source,setSource]=useState(''),[subject,setSubject]=useState(`Application for ${job.title}`),[body,setBody]=useState('');
  const [approved,setApproved]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const load=useCallback(async()=>{
    try {
      const [data,connections]=await Promise.all([api<{versions:Version[];items:Attempt[]}>(base),api<{items:Mailbox[]}>('/mailboxes')]);
      setVersions(data.versions);setMailboxes(connections.items.filter(m=>['connected','expired'].includes(m.status)&&m.capabilities.includes('send')));
      setAttempt(data.items[0]||null);setApproved(false);
    } catch(e) {setError(message(e));} finally {setLoading(false);}
  },[base]);
  useEffect(()=>{void load();},[load]);
  async function prepare(e:React.FormEvent) {
    e.preventDefault();setBusy('Preparing exact PDF attachments');setError('');setApproved(false);
    try {
      const selected=versions.find(v=>`${v.pack_id}:${v.number}`===version);
      if(!selected) throw new Error('Select an approved pack version.');
      const result=await api<Attempt>(base,{method:'POST',body:JSON.stringify({mailbox_id:mailbox,pack_id:selected.pack_id,pack_version:selected.number,
        recipient,confirm_recipient:confirmRecipient,recipient_source:source,subject,body})},false);
      setAttempt(result);setEditing(false);
    } catch(e) {setError(message(e));} finally {setBusy('');}
  }
  async function edit() {
    if(!attempt)return;
    setBusy('Cancelling review');setError('');
    try {if(attempt.status==='review')setAttempt(await api<Attempt>(`${base}/${attempt.id}/cancel`,{method:'POST'},false));setEditing(true);setApproved(false);}
    catch(e){setError(message(e));}finally{setBusy('');}
  }
  async function send() {
    if(!attempt||!approved)return;
    setBusy('Sending approved snapshot; do not resend');setError('');setApproved(false);
    try {setAttempt(await api<Attempt>(`${base}/${attempt.id}/send`,{method:'POST',body:JSON.stringify({snapshot_hash:attempt.snapshot_hash,confirm:true})},false));}
    catch {setError('The send response was not received. Do not resend. Refresh status to check whether the server accepted or dispatched the request.');
      try{setAttempt(await api<Attempt>(`${base}/${attempt.id}`));}catch{/* Keep uncertainty visible; never infer failure or success. */}}
    finally{setBusy('');}
  }
  async function download(index:number) {
    if(!attempt)return;
    try{const blob=await downloadResume(`${base}/${attempt.id}/attachments/${index}`);const url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download=attempt.attachments[index].name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(message(e));}
  }
  return <section className="mailbox-card email-application" aria-labelledby="email-application-heading">
    <h2 id="email-application-heading">Apply by email</h2>
    <p>Select an approved pack, enter the recruitment address yourself and record where you found it. Review the exact PDFs before Send. Sending permission is sufficient; inbox access is not required.</p>
    <p><Link href="/settings">Manage sending mailboxes</Link></p>
    {loading&&<p role="status">Loading email application options…</p>}
    {error&&<p role="alert" className="form-error">{error}</p>}
    {busy&&<p role="status">{busy}…</p>}
    <button type="button" disabled={!!busy} onClick={()=>{setError('');void load();}}>Refresh email status and approved packs</button>
    {attempt&&!editing&&<div className="email-review">
      <p role="status"><strong>Email status: {attempt.status}</strong> — {outcomes[attempt.status]||'Check the recorded result.'}</p>
      {attempt.outcome&&<p>Result: {attempt.outcome.replaceAll('_',' ')}{attempt.provider_status?` (HTTP ${attempt.provider_status})`:''}</p>}
      {attempt.provider_message_id&&<p>Provider message ID: {attempt.provider_message_id}</p>}
      {attempt.status==='sent'&&!attempt.application_id&&<p role="alert">Acceptance was recorded, but tracking needs manual review. Do not resend.</p>}
      {attempt.status==='sent'&&attempt.application_id&&<p><Link href="/applications">View submitted application in tracking</Link></p>}
      <dl><dt>Sending mailbox</dt><dd>{attempt.snapshot.sender} ({attempt.snapshot.provider})</dd><dt>Recruitment recipient</dt><dd>{attempt.snapshot.recipient}</dd>
        <dt>Recipient source</dt><dd>{attempt.snapshot.recipient_source}</dd><dt>Approved pack version</dt><dd>{attempt.snapshot.pack_version}</dd>
        <dt>Subject</dt><dd>{attempt.snapshot.subject}</dd></dl>
      <h3>Message body</h3><p className="preserve-lines">{attempt.snapshot.body}</p>
      <h3>Exact attachments</h3><ul>{attempt.attachments.map((a,i)=><li key={a.name}><button onClick={()=>void download(i)}>{a.name}</button> — {a.size.toLocaleString()} bytes<details><summary>Attachment fingerprint (SHA-256)</summary><code>{a.sha256}</code></details></li>)}</ul>
      {attempt.status==='review'&&<><label className="email-confirm"><input type="checkbox" disabled={!!busy} checked={approved} onChange={e=>setApproved(e.target.checked)}/>I confirm the mailbox, recipient and its source, subject, body and both exact attachments. Send this immutable snapshot.</label>
        <button className="primary-button" disabled={!!busy||!approved} onClick={()=>void send()}>Confirm and send application</button></>}
      {['review','failed','cancelled'].includes(attempt.status)&&<button disabled={!!busy} onClick={()=>void edit()}>{attempt.status==='review'?'Cancel review and edit':'Prepare a new review'}</button>}
    </div>}
    {!loading&&(!attempt||editing)&&<form onSubmit={prepare} className="email-form">
      {!versions.length&&<p>Approve a pack below, then refresh these options.</p>}
      {!mailboxes.length&&<p>Connect a Gmail mailbox with sending permission in Settings.</p>}
      <label>Approved pack version<select required disabled={!!busy} value={version} onChange={e=>setVersion(e.target.value)}><option value="">Select a version</option>{versions.map(v=><option key={`${v.pack_id}:${v.number}`} value={`${v.pack_id}:${v.number}`}>Pack {v.pack_id.slice(0,8)} · version {v.number} · approved {new Date(v.approved_at).toLocaleString()}</option>)}</select></label>
      <label>Sending mailbox<select required disabled={!!busy} value={mailbox} onChange={e=>setMailbox(e.target.value)}><option value="">Select a mailbox</option>{mailboxes.map(m=><option key={m.id} value={m.id}>{m.email}{m.provider==='google-test'?' (synthetic test)':''}</option>)}</select></label>
      <label>Recruitment email<input type="email" required maxLength={254} disabled={!!busy} value={recipient} onChange={e=>{setRecipient(e.target.value);setConfirmRecipient('');}}/></label>
      <label>Confirm recruitment email<input type="email" required maxLength={254} disabled={!!busy} value={confirmRecipient} onChange={e=>setConfirmRecipient(e.target.value)}/></label>
      <label>Where did you find this address?<input required minLength={3} maxLength={1000} disabled={!!busy} value={source} onChange={e=>setSource(e.target.value)} placeholder="Job posting URL or recruiter-provided instructions"/></label>
      <label>Email subject<input required maxLength={200} disabled={!!busy} value={subject} onChange={e=>setSubject(e.target.value)}/></label>
      <label>Email body<textarea required maxLength={20000} rows={8} disabled={!!busy} value={body} onChange={e=>setBody(e.target.value)}/></label>
      <button className="primary-button" disabled={!!busy||!versions.length||!mailboxes.length}>Prepare email review</button>
    </form>}
  </section>;
}
