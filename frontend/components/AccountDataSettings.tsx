'use client';
import {useState} from 'react';
import {api, downloadResume, setAccessToken} from '../lib/api';
import { DownloadSimple, LockKey, Trash } from '@phosphor-icons/react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { FormField } from './ui/form-field';
import '@/app/account.css';

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
  return <section id="account-data" className="account-settings-section" aria-labelledby="account-data-title">
    <div className="account-section-heading"><div className="account-section-symbol"><LockKey size={22} aria-hidden="true"/></div><div><h2 id="account-data-title">Your account data</h2><p>Take a copy of your work, or manage the future of your account.</p></div></div>
    {error&&<p role="alert" className="account-alert account-alert-error">{error}</p>}{notice&&<p className="account-alert account-alert-success" role="status">{notice}</p>}
    {!receipt?<>
      <div className="account-surface account-identity-check"><div><LockKey size={20} aria-hidden="true"/><h3>First, confirm it’s you</h3><p>Enter your current password to export or delete account data. It is cleared after each request.</p></div><FormField label="Confirm your password" htmlFor="account-data-password"><Input id="account-data-password" type="password" placeholder="Your current password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></FormField></div>
      <div className="account-surface account-data-export"><div className="account-data-copy"><DownloadSimple size={23} aria-hidden="true"/><div><h3>Export your workspace</h3><p>Download your profile, jobs, applications, reminders, interviews, AI results, retained email records, and documents. Credentials and security tokens are excluded. Exports are private, size-limited, and temporary.</p></div></div><Button variant="outline" disabled={busy||!password} onClick={()=>action('export')}><DownloadSimple aria-hidden="true"/>Export my data</Button></div>
      <div className="account-surface account-data-danger"><div className="account-data-copy"><Trash size={23} aria-hidden="true"/><div><h3>Delete your account</h3><p>Deletion disables sign-in immediately and stops new work. Scheduled cleanup removes private files and account records. This action is permanent.</p></div></div><details className="account-deletion-details"><summary>What happens to your data?</summary><p>Previously dispatched emails cannot be recalled. Google revocation may remain unconfirmed. Historical backups expire under the operator’s backup policy; deletion does not erase them immediately.</p><p>The last active account requires a local operator to establish a recovery account first.</p></details><div className="account-delete-controls"><FormField label="Type DELETE MY ACCOUNT to confirm permanent deletion" htmlFor="account-delete-confirmation"><Input id="account-delete-confirmation" value={confirmation} placeholder="DELETE MY ACCOUNT" autoComplete="off" onChange={e=>setConfirmation(e.target.value)} disabled={busy}/></FormField><Button variant="destructive" disabled={busy||!password||confirmation!=='DELETE MY ACCOUNT'} onClick={()=>action('delete')}>Permanently delete my account</Button></div></div>
    </>:<>
      <div className="account-surface"><h3>Account deletion progress</h3><p className="account-section-intro">This page holds a private status receipt only in memory. Keep it open to check progress; if closed, contact the operator. No account access remains.</p><Button variant="outline" disabled={busy} onClick={check}>Check deletion status</Button>
      {status&&<p className="account-alert" role="status">{status.status==='complete'?'Account content and private files removed. A minimal cleanup receipt is retained temporarily.':status.status==='failed'?'Cleanup failed; removal is not complete. The operator must retry cleanup.':'Cleanup pending; removal is not complete.'} {status.provider_revocation_unconfirmed?'Google revocation is unconfirmed. Remove JobPilot access in your Google account connections.':''}</p>}</div>
    </>}
    {busy&&<p className="account-inline-status" role="status">Processing account request…</p>}
  </section>;
}
