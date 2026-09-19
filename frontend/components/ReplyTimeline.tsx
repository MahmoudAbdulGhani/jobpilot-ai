'use client';
import Link from 'next/link';
import {useCallback,useEffect,useState} from 'react';
import {api} from '../lib/api';
import {ReplyClassificationPanel} from './ReplyClassification';

type Reply={id:string;job_id:string|null;suggested_job_id:string;match_kind:string;sender:string;subject:string;preview:string;received_at:string;corrected_at:string|null};
type Job={id:string;title:string;company:string};
type Sync={status:string;pending:number;more_pages:boolean;last_sync_at:string|null;retry_after:string|null};
type Listing={items:Reply[];jobs:Job[];attempts:{attempt_id:string;provider:string;send_status:string;sync:Sync|null}[]};
const statusText:Record<string,string>={
  up_to_date_for_thread:'This application thread is up to date for this batch. Other mailbox threads were not scanned.',
  more_pending:'More changes remain. Choose Sync replies again to process the next bounded batch.',
  history_expired:'Google history expired. Sync again to rebuild this application thread only.',
  page_expired:'The page token expired. Sync again to restart the bounded history window; stored replies are deduplicated.',
  rate_limited:'Google rate limit reached. Wait until the displayed retry time; no automatic retry will run.',
  send_remains_unknown:'The exact original was not uniquely verified in Sent mail. Sending remains unknown. Do not resend.',
  send_reconciled_sync_again:'The exact original was found in Sent mail. Submission was reconciled; delivery/read status remains unknown. Refresh tracking, then sync again for replies.',
  reading_permission_required:'Enable reply tracking in Settings. Sending does not need reading permission.',
  credential_revoked:'Google credentials are unavailable or revoked. Reconnect in Settings.',
  reconnect_required:'Reconnect this mailbox in Settings.',
  response_limit:'This thread/history response exceeds the safety limit. Review it directly in Gmail; JobPilot will not scan more broadly.',
  provider_unavailable:'Google could not complete this batch. Saved progress remains; retry only when you choose.',
};

function ReplyCard({reply,jobs,reload}:{reply:Reply;jobs:Job[];reload:()=>Promise<void>}) {
  const [jobId,setJobId]=useState(reply.job_id||reply.suggested_job_id),[busy,setBusy]=useState(false),[error,setError]=useState(''),[discard,setDiscard]=useState(false);
  async function associate(target:string|null){
    setBusy(true);setError('');
    try{await api(`/replies/${reply.id}/association`,{method:'PATCH',body:JSON.stringify({job_id:target,confirm:true})},false);await reload();window.dispatchEvent(new Event('replies-changed'));}
    catch(e){setError(e instanceof Error?e.message:'Correction failed.');}finally{setBusy(false);}
  }
  return <article className="mailbox-card" aria-label={`Reply from ${reply.sender}`}>
    <h4>{reply.job_id?'Reply received':'Uncertain association — confirm before linking'}</h4>
    <p><time dateTime={reply.received_at}>{new Date(reply.received_at).toLocaleString()}</time> · {reply.sender}</p>
    <p><strong>{reply.subject}</strong></p><p className="preserve-lines">{reply.preview||'Text preview unavailable.'}</p>
    <p className="muted">Gmail text preview; may be truncated. No attachments downloaded. Match: {reply.match_kind.replaceAll('_',' ')}. Classification is advisory only and never changes status by itself.</p>
    <label>Associate reply with saved job<select value={jobId} onChange={e=>setJobId(e.target.value)} disabled={busy}>{jobs.map(j=><option key={j.id} value={j.id}>{j.title} — {j.company}</option>)}</select></label>
    <button disabled={busy||!jobId} onClick={()=>void associate(jobId)}>{reply.job_id?'Save association correction':'Confirm association'}</button>
    <button disabled={busy} onClick={()=>setDiscard(true)}>Dismiss and erase preview</button>
    {discard&&<p>Erase this reply preview and prevent it being imported again?<button disabled={busy} onClick={()=>void associate(null)}>Confirm erase preview</button><button onClick={()=>setDiscard(false)}>Cancel</button></p>}
    {error&&<p role="alert">{error}</p>}
    <ReplyClassificationPanel replyId={reply.id} jobId={reply.job_id}/>
  </article>;
}

export function ReplyTimeline({jobId}:{jobId:string}) {
  const [data,setData]=useState<Listing|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState('');
  const load=useCallback(async()=>{try{setData(await api<Listing>(`/jobs/${jobId}/replies`));}catch(e){setError(e instanceof Error?e.message:'Could not load saved replies.');}},[jobId]);
  useEffect(()=>{void load();},[load]);
  async function sync(attemptId:string){
    setBusy(attemptId);setError('');
    try{await api(`/jobs/${jobId}/email-applications/${attemptId}/replies/sync`,{method:'POST',body:JSON.stringify({confirm:true})},false);await load();window.dispatchEvent(new Event('replies-changed'));}
    catch(e){setError(e instanceof Error?e.message:'Sync interrupted. Refresh saved replies before trying another batch.');}
    finally{setBusy('');}
  }
  return <section className="reply-timeline" aria-label="Application reply timeline">
    <h3>Application reply timeline</h3>
    <p><Link href="/settings">Enable reply tracking in Settings</Link> separately from sending. Google grants mailbox-wide reading access. Each Sync replies click reads a bounded batch for this application, never downloads attachments and never sends mail. Connecting alone starts no scanning.</p>
    <button disabled={!!busy} onClick={()=>void load()}>Refresh saved replies</button>
    {!data&&!error&&<p role="status">Loading saved replies…</p>}
    {error&&<p role="alert" className="form-error">{error}</p>}
    {busy&&<p role="status">Synchronizing one bounded batch…</p>}
    {data&&<>
      {!data.attempts.length&&<p>No JobPilot-dispatched application to synchronize for this job.</p>}
      {data.attempts.map(a=><div key={a.attempt_id}>
        <p>{a.provider==='google-test'?'Synthetic reply provider — no live inbox access.':'Gmail reply tracking.'} Send status: {a.send_status}.</p>
        <button disabled={!!busy||!!(a.sync?.retry_after&&new Date(a.sync.retry_after)>new Date())} onClick={()=>void sync(a.attempt_id)}>Sync replies (next bounded batch)</button>
        {a.sync&&<p role="status">{statusText[a.sync.status]||a.sync.status.replaceAll('_',' ')}{a.sync.retry_after&&` Retry after ${new Date(a.sync.retry_after).toLocaleString()}.`}</p>}
      </div>)}
      <h4>Matched responses</h4>
      {!data.items.some(r=>r.job_id===jobId)&&<p>No matched replies saved.</p>}
      {data.items.filter(r=>r.job_id===jobId).map(r=><ReplyCard key={r.id} reply={r} jobs={data.jobs} reload={load}/>)}
      <h4>Uncertain matches</h4><p>Thread membership alone does not confirm an association. Sender or subject similarity never confirms one.</p>
      {data.items.filter(r=>!r.job_id).map(r=><ReplyCard key={r.id} reply={r} jobs={data.jobs} reload={load}/>)}
      <p>Use the application tracking form, or a classified reply with explicit confirmation, to update status. Synchronization never interprets a reply as an interview, rejection or offer.</p>
    </>}
  </section>;
}
