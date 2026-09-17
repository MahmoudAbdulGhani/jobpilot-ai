'use client';
import {useState} from 'react';
import {api, downloadResume, setAccessToken} from '../lib/api';

type Receipt = {id:string;receipt:string;status:string};
type Status = {status:string;failure:string|null;provider_revocation_unconfirmed:boolean};

export function AccountDataSettings() {
  const [password,setPassword]=useState(''),[confirmation,setConfirmation]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [receipt,setReceipt]=useState<Receipt|null>(null),[status,setStatus]=useState<Status|null>(null);
  async function action(kind:'export'|'delete') {
    setBusy(true);setError('');setNotice('');
    try {
      if(kind==='export') {
        const result=await api<{id:string;expires_at:string}>('/account/data/exports',{method:'POST',body:JSON.stringify({password})});
        const blob=await downloadResume(`/account/data/exports/${result.id}`);
        const url=URL.createObjectURL(blob), a=document.createElement('a');a.href=url;a.download='jobpilot-account.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        setNotice('Export download prepared. The server copy expires in ten minutes or less. Store your private archive securely.');
      } else {
        const result=await api<Receipt>('/account/data/deletions',{method:'POST',body:JSON.stringify({password,confirmation})});
        setReceipt(result);setAccessToken(null);
        setNotice('Deletion accepted. Account access is disabled. Cleanup is pending; files and records may still remain until the scheduled cleanup finishes.');
      }
    } catch(e) {setError(e instanceof Error?e.message:'Account operation failed.');}
    finally {setPassword('');setBusy(false);}
  }
  async function check() {
    if(!receipt)return;setBusy(true);setError('');
    try {setStatus(await api<Status>(`/account/data/deletions/${receipt.id}/status`,{method:'POST',body:JSON.stringify({receipt:receipt.receipt})},false));}
    catch(e){setError(e instanceof Error?e.message:'Status unavailable.');}finally{setBusy(false);}
  }
  return <section className="mailbox-card" aria-labelledby="account-data-title">
    <h2 id="account-data-title">Your account data</h2>
    <p>Export your profile, jobs, applications, reminders, interviews, AI results, retained email records and documents. Credentials and security tokens are excluded. Exports are private, size-limited and temporary.</p>
    <p>Deletion disables sign-in immediately and stops new work. Scheduled cleanup removes private files and account records. Previously dispatched emails cannot be recalled. Google revocation may remain unconfirmed. Historical backups expire under the operator’s backup policy; deletion does not erase them immediately.</p>
    {error&&<p role="alert" className="form-error">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!receipt?<>
      <label>Confirm your password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></label>
      <button disabled={busy||!password} onClick={()=>action('export')}>Export my data</button>
      <label>Type DELETE MY ACCOUNT to confirm permanent deletion<input value={confirmation} autoComplete="off" onChange={e=>setConfirmation(e.target.value)} disabled={busy}/></label>
      <button disabled={busy||!password||confirmation!=='DELETE MY ACCOUNT'} onClick={()=>action('delete')}>Permanently delete my account</button>
      <p>The last active account requires a local operator to establish a recovery account first.</p>
    </>:<>
      <button disabled={busy} onClick={check}>Check deletion status</button>
      <p>This page holds a private status receipt only in memory. Keep it open to check progress; if closed, contact the operator. No account access remains.</p>
      {status&&<p role="status">{status.status==='complete'?'Account content and private files removed. A minimal cleanup receipt is retained temporarily.':status.status==='failed'?'Cleanup failed; removal is not complete. The operator must retry cleanup.':'Cleanup pending; removal is not complete.'} {status.provider_revocation_unconfirmed?'Google revocation is unconfirmed. Remove JobPilot access in your Google account connections.':''}</p>}
    </>}
    {busy&&<p role="status">Processing account request…</p>}
  </section>;
}
