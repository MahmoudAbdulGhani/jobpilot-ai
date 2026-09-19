'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Shell } from './Shell';
import { api } from '../lib/api';
import { AccountDataSettings } from './AccountDataSettings';
import { PrivacyMatrix } from './PrivacyMatrix';

type Capability = 'send' | 'read_replies';
type Mailbox = {id:string;email:string;provider:string;capabilities:Capability[];status:string;expires_at:string|null};
type Listing = {available:boolean;test_provider:boolean;items:Mailbox[]};
const messages: Record<string,string> = {
  connected:'Mailbox connected. No messages were sent or read.',
  already_connected:'This mailbox is already listed. Existing permissions were preserved; use its reconnect control to update them.',
  partial:'Connected with only the permissions you granted. Review the enabled capabilities below.',
  denied:'Consent was denied. Existing mailbox permissions were not changed.',
  invalid_state:'This connection attempt expired, was already used, or came from another browser. Start again.',
  account_unavailable:'This Google account cannot be connected here. No other account details are disclosed.',
  account_mismatch:'Choose the same Google account when reconnecting this mailbox.',
  reconnect_required:'Google credentials expired or were revoked. Reconnect to authorize again.',
  not_configured:'Gmail connection is not configured on this server.',
  offline_consent_required:'Google did not issue offline access. Reconnect and grant consent.',
  provider_unavailable:'Google is unavailable. Please try again later.',
  credential_unavailable:'Stored credentials cannot be opened. Reconnect or disconnect this mailbox.',
};
function explain(error:unknown) { return error instanceof Error ? messages[error.message] || 'Mailbox operation failed. Please try again.' : 'Mailbox operation failed.'; }

function Permissions({value,onChange,disabled}:{value:Capability[];onChange:(v:Capability[])=>void;disabled:boolean}) {
  return <fieldset disabled={disabled} className="mailbox-permissions"><legend>Optional capabilities</legend>
    {(['send','read_replies'] as Capability[]).map(c => <label key={c}><input type="checkbox" checked={value.includes(c)} onChange={e=>onChange(e.target.checked?[...value,c]:value.filter(v=>v!==c))}/>{c==='send'?'Allow sending applications':'Enable reply tracking'}</label>)}
    <p>Reading replies requires Google’s read-only access to the whole mailbox, not just application replies. Enabling grants mailbox-wide reading permission. Synchronization runs only when you explicitly choose Sync replies for a JobPilot application; connecting alone never scans.</p>
  </fieldset>;
}

function Connection({row,available,reload}:{row:Mailbox;available:boolean;reload:()=>Promise<void>}) {
  const [capabilities,setCapabilities]=useState<Capability[]>(row.capabilities);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirm,setConfirm]=useState(false);
  useEffect(()=>setCapabilities(row.capabilities),[row.capabilities]);
  async function action(kind:'check'|'disconnect'|'reconnect') {
    setBusy(true);setError('');
    try {
      if(kind==='reconnect') {
        const result=await api<{authorization_url:string}>('/mailboxes/oauth/start',{method:'POST',body:JSON.stringify({connection_id:row.id,capabilities})});
        window.location.assign(result.authorization_url);
      } else { await api(`/mailboxes/${row.id}/${kind}`,{method:'POST'});setConfirm(false);await reload(); }
    } catch(e) {setError(explain(e));await reload();}
    finally {setBusy(false);}
  }
  return <article className="mailbox-card" aria-label={`Mailbox ${row.email}`}>
    <h2>{row.email}</h2><p>{row.provider==='google-test'?'Guarded synthetic mailbox':'Gmail'}</p>
    <p role="status">Status: {row.status.replaceAll('_',' ')}</p>
    <p>Enabled capabilities: {row.capabilities.map(c=>c==='send'?'Sending applications':'Reading replies').join(', ')||(['connected','expired'].includes(row.status)?'Identity only':'None')}</p>
    {row.status==='expired'&&<p>Access token expired. Check connection to refresh credentials, or reconnect.</p>}
    {row.status==='reconnect_required'&&<p>Credentials expired or were revoked. Reconnect with Google.</p>}
    {row.status==='revoke_failed'&&<p>Disconnected locally and credentials deleted, but Google revocation could not be confirmed. Remove access in <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">Google account connections</a>.</p>}
    <Permissions value={capabilities} onChange={setCapabilities} disabled={busy||!available}/>
    {error&&<p role="alert" className="form-error">{error}</p>}
    <div className="mailbox-actions"><button className="primary-button" disabled={busy||!available} onClick={()=>action('reconnect')}>Update permissions / reconnect</button>
      <button disabled={busy||!available||['disconnected','revoke_failed','reconnect_required'].includes(row.status)} onClick={()=>action('check')}>Check connection</button>
      <button disabled={busy||row.status==='disconnected'} onClick={()=>setConfirm(true)}>Disconnect</button></div>
    {confirm&&<div className="notice"><p>Disconnect and revoke JobPilot’s Google access? This removes stored credentials and disables both capabilities. Google revocation can affect all grants for this app.</p><button disabled={busy} onClick={()=>action('disconnect')}>Confirm disconnect and revoke</button><button disabled={busy} onClick={()=>setConfirm(false)}>Cancel</button></div>}
    {busy&&<p role="status">Updating mailbox…</p>}
  </article>;
}

export function MailboxSettings() {
  const [data,setData]=useState<Listing|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [capabilities,setCapabilities]=useState<Capability[]>([]),[busy,setBusy]=useState(false);
  async function load() { try {setData(await api<Listing>('/mailboxes'));} catch(e) {setError(explain(e));} }
  useEffect(()=>{
    const outcome=new URLSearchParams(window.location.search).get('mailbox');
    if(outcome) {setNotice(messages[outcome]||'The connection could not be completed. Start again.');window.history.replaceState(null,'','/settings');}
    void load();
  },[]);
  async function connect() {
    setBusy(true);setError('');
    try {const result=await api<{authorization_url:string}>('/mailboxes/oauth/start',{method:'POST',body:JSON.stringify({capabilities})});window.location.assign(result.authorization_url);}
    catch(e) {setError(explain(e));setBusy(false);}
  }
  return <Shell><div className="collection-page mailbox-settings"><p className="eyebrow">Account settings</p><h1>Mailboxes</h1><p><Link href="/settings/usage">Plan and usage</Link></p>
    <p>Connect Gmail for user-approved email applications from saved jobs. Connecting never sends messages or scans your inbox. Every application requires a separate message and attachment review followed by explicit Send confirmation. Reply tracking is optional and requires separate reading consent plus an explicit synchronization action.</p>
    <p>Start with identity only, or select a capability before granting permission. Your Google tokens stay encrypted on the server. You can disconnect and revoke access at any time.</p>
    <p>You can also remove grants directly in <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">Google account connections</a>. Unchecking a capability disables it in JobPilot after consent; removing the Google grant requires disconnect and revoke.</p>
    {notice&&<p role="status" className="notice">{notice}</p>}{error&&<p role="alert" className="form-error">{error}</p>}
    {!data&&!error&&<p role="status">Loading mailbox settings…</p>}
    {data&&<>{!data.available&&<p className="notice">Gmail connection is not configured on this server. Existing mailboxes can still be disconnected.</p>}
      {data.test_provider&&<p className="notice">Synthetic test provider — no live Google authorization.</p>}
      {data.items.map(row=><Connection key={row.id} row={row} available={data.available} reload={load}/>)}
      <section className="mailbox-card"><h2>Connect a Gmail mailbox</h2><Permissions value={capabilities} onChange={setCapabilities} disabled={busy||!data.available}/><button className="primary-button" disabled={busy||!data.available} onClick={connect}>{busy?'Opening consent…':'Connect Gmail'}</button></section>
    </>}
    <AccountDataSettings />
    <PrivacyMatrix/>
  </div></Shell>;
}
