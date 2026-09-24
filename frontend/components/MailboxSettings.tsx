'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Shell } from './Shell';
import { api } from '../lib/api';
import { AccountDataSettings } from './AccountDataSettings';
import { PrivacyMatrix } from './PrivacyMatrix';
import { ArrowRight, ArrowSquareOut, CheckCircle, EnvelopeSimple, GoogleLogo, LockKey, ShieldCheck, SlidersHorizontal } from '@phosphor-icons/react';
import { PageHeader } from './ui/page-header';
import { Button } from './ui/button';
import { LoadingState } from './ui/loading-state';
import '@/app/account.css';

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
  return <fieldset disabled={disabled} className="account-permissions"><legend>Optional capabilities</legend>
    <div className="account-permission-options">{(['send','read_replies'] as Capability[]).map(c => <label key={c} className={value.includes(c)?'is-selected':''}><input type="checkbox" aria-label={c==='send'?'Allow sending applications':'Enable reply tracking'} checked={value.includes(c)} onChange={e=>onChange(e.target.checked?[...value,c]:value.filter(v=>v!==c))}/><span><strong>{c==='send'?'Allow sending applications':'Enable reply tracking'}</strong><small>{c==='send'?'Send only after reviewing and confirming each application.':'Sync replies when you explicitly request an update.'}</small></span></label>)}</div>
    <p className="account-permission-note"><ShieldCheck size={17} aria-hidden="true"/><span>Reading replies requires Google’s read-only access to the whole mailbox, not just application replies. Enabling grants mailbox-wide reading permission. Synchronization runs only when you explicitly choose Sync replies for a JobPilot application; connecting alone never scans.</span></p>
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
  return <article className="account-surface account-connection" aria-label={`Mailbox ${row.email}`}>
    <div className="account-connection-heading"><div className="account-service-icon"><GoogleLogo size={24} aria-hidden="true"/></div><div><h3>{row.email}</h3><p>{row.provider==='google-test'?'Guarded synthetic mailbox':'Gmail'}</p></div><span className={`account-pill ${row.status==='connected'?'':'account-pill-neutral'}`} role="status">Status: {row.status.replaceAll('_',' ')}</span></div>
    <p className="account-enabled"><CheckCircle size={16} aria-hidden="true"/>Enabled capabilities: {row.capabilities.map(c=>c==='send'?'Sending applications':'Reading replies').join(', ')||(['connected','expired'].includes(row.status)?'Identity only':'None')}</p>
    {row.status==='expired'&&<p className="account-alert">Access token expired. Check connection to refresh credentials, or reconnect.</p>}
    {row.status==='reconnect_required'&&<p className="account-alert">Credentials expired or were revoked. Reconnect with Google.</p>}
    {row.status==='revoke_failed'&&<p className="account-alert">Disconnected locally and credentials deleted, but Google revocation could not be confirmed. Remove access in <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">Google account connections</a>.</p>}
    <Permissions value={capabilities} onChange={setCapabilities} disabled={busy||!available}/>
    {error&&<p role="alert" className="account-alert account-alert-error">{error}</p>}
    <div className="account-actions"><Button disabled={busy||!available} onClick={()=>action('reconnect')}>Update permissions / reconnect</Button>
      <Button variant="outline" disabled={busy||!available||['disconnected','revoke_failed','reconnect_required'].includes(row.status)} onClick={()=>action('check')}>Check connection</Button>
      <Button variant="ghost" className="account-danger-text" disabled={busy||row.status==='disconnected'} onClick={()=>setConfirm(true)}>Disconnect</Button></div>
    {confirm&&<div className="account-alert account-confirmation"><strong>Disconnect this mailbox?</strong><p>Disconnect and revoke JobPilot’s Google access? This removes stored credentials and disables both capabilities. Google revocation can affect all grants for this app.</p><div className="account-actions"><Button variant="destructive" disabled={busy} onClick={()=>action('disconnect')}>Confirm disconnect and revoke</Button><Button variant="outline" disabled={busy} onClick={()=>setConfirm(false)}>Cancel</Button></div></div>}
    {busy&&<p className="account-inline-status" role="status">Updating mailbox…</p>}
  </article>;
}

export function MailboxSettings() {
  const [data,setData]=useState<Listing|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [capabilities,setCapabilities]=useState<Capability[]>([]),[busy,setBusy]=useState(false);
  async function load() { setError('');try {setData(await api<Listing>('/mailboxes'));} catch(e) {setError(explain(e));} }
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
  return <Shell><div className="collection-page account-settings">
    <PageHeader eyebrow="YOUR WORKSPACE" title="Settings" subtitle="Make it work for you. Manage your connections, privacy, and account in one place." actions={<Button asChild variant="outline"><Link href="/settings/usage"><SlidersHorizontal size={17} aria-hidden="true"/>Plan and usage<ArrowRight size={16} aria-hidden="true"/></Link></Button>}/>
    <nav className="account-section-nav" aria-label="Settings sections"><a href="#connections"><EnvelopeSimple size={17} aria-hidden="true"/>Connections</a><a href="#privacy"><ShieldCheck size={17} aria-hidden="true"/>Privacy controls</a><a href="#account-data"><LockKey size={17} aria-hidden="true"/>Account data</a></nav>
    {notice&&<p role="status" className="account-alert account-alert-success">{notice}</p>}{error&&<div className="account-alert account-alert-error"><p role="alert">{error}</p><Button variant="outline" size="sm" onClick={()=>void load()}>Try again</Button></div>}
    <section id="connections" className="account-settings-section" aria-labelledby="connections-title">
      <div className="account-section-heading"><div className="account-section-symbol"><EnvelopeSimple size={22} aria-hidden="true"/></div><div><h2 id="connections-title">Mailbox connections</h2><p>Bring your application conversations into your workspace.</p></div></div>
      <div className="account-settings-grid"><div className="account-settings-main">
    {!data&&!error&&<LoadingState label="Loading mailbox settings…" rows={3}/>}
    {data&&<>{!data.available&&<p className="account-alert">Gmail connection is not configured on this server. Existing mailboxes can still be disconnected.</p>}
      {data.test_provider&&<p className="account-alert">Synthetic test provider — no live Google authorization.</p>}
      {data.items.map(row=><Connection key={row.id} row={row} available={data.available} reload={load}/>)}
      <section className="account-surface account-connect"><div className="account-connection-heading"><div className="account-service-icon"><GoogleLogo size={25} aria-hidden="true"/></div><div><h3>Connect a Gmail mailbox</h3><p>{data.items.length?'Add another mailbox to your workspace.':'No mailbox connected yet. Choose what you want to enable.'}</p></div><span className="account-pill account-pill-neutral">Optional</span></div><Permissions value={capabilities} onChange={setCapabilities} disabled={busy||!data.available}/><div className="account-connect-footer"><Button disabled={busy||!data.available} onClick={connect}><GoogleLogo aria-hidden="true"/>{busy?'Opening consent…':'Connect Gmail'}</Button><span>You will continue securely to Google.</span></div></section>
    </>}
    </div><aside className="account-side-note"><ShieldCheck size={25} weight="duotone" aria-hidden="true"/><h3>Connected, on your terms.</h3><p>Connecting never sends messages or scans your inbox. Every application requires a message and attachment review followed by explicit Send confirmation.</p><p>Start with identity only, or select a capability before granting permission. Your Google tokens stay encrypted on the server.</p><details><summary>Managing Google permissions</summary><p>Reply tracking requires separate reading consent and an explicit synchronization action. Unchecking a capability disables it in JobPilot after consent; removing the Google grant requires disconnect and revoke.</p><a href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">Google account connections<ArrowSquareOut size={14} aria-hidden="true"/></a></details></aside></div>
    </section>
    <PrivacyMatrix/>
    <AccountDataSettings />
  </div></Shell>;
}
