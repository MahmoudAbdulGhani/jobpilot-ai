'use client';
import Link from 'next/link';
import {Shell} from './Shell';
import {useEntitlements,stateLabel} from '../lib/entitlements';
import {ArrowClockwise, ArrowLeft, CalendarBlank, ChartBar, Sparkle} from '@phosphor-icons/react';
import {PageHeader} from './ui/page-header';
import {Button} from './ui/button';
import {LoadingState} from './ui/loading-state';
import '@/app/account.css';

export function UsageDetails(){
  const usage=useEntitlements(),data=usage?.data;
  const percent=data?.total.allowance?Math.min(100,Math.max(0,data.total.consumed/data.total.allowance*100)):0;
  const dateLabel=(value:string)=>new Date(value).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});
  return <section className="collection-page account-usage">
    <Link className="account-back-link" href="/settings"><ArrowLeft size={16} aria-hidden="true"/>Back to settings</Link>
    <PageHeader eyebrow="ACCOUNT" title="Plan and usage" subtitle="A clear view of your access and monthly AI allowance." actions={<Button variant="outline" disabled={usage?.loading} onClick={()=>void usage?.refresh()}><ArrowClockwise size={16} className={usage?.loading?'animate-spin':''} aria-hidden="true"/>Refresh usage</Button>}/>
    {usage?.loading&&<LoadingState label="Loading current allowance…" rows={2}/>}
    {usage?.error&&<p className="account-alert account-alert-error" role="alert">{usage.error}</p>}
    {data&&<>
      <div className="account-usage-overview"><div className="account-surface account-plan-card"><span className="account-kicker"><Sparkle size={17} aria-hidden="true"/>YOUR CURRENT PLAN</span><h2>{({free:'Free access',legacy:'Existing-user continuity',invited_beta:'Invited beta'} as Record<string,string>)[data.plan]||'Access plan'}</h2><p>Room to prepare your next move.</p><span className="account-pill">{data.admin?'Administrator access':'Current access'}</span></div><div className="account-surface account-allowance-card"><div className="account-allowance-heading"><span className="account-kicker"><ChartBar size={17} aria-hidden="true"/>SHARED MONTHLY ALLOWANCE</span><span>{data.total.consumed} / {data.total.allowance} reserved</span></div><div className="account-allowance-number"><strong>{data.total.remaining}</strong><span>requests remaining</span></div><div className="account-usage-meter" role="progressbar" aria-label="Monthly allowance reserved" aria-valuenow={data.total.consumed} aria-valuemin={0} aria-valuemax={Math.max(data.total.allowance,data.total.consumed)}><span style={{width:`${percent}%`}}/></div><p><CalendarBlank size={16} aria-hidden="true"/>Resets {dateLabel(data.reset_at)} at 00:00 UTC</p></div></div>
      {data.admin&&<p className="account-alert account-alert-success">Administrator — quotas bypassed for this account.</p>}
      {data.profile_refreshes&&<p className="account-alert">AI profile refreshes: {data.admin ? 'unlimited for administrators' : `${data.profile_refreshes.remaining} of ${data.profile_refreshes.allowance} remaining this UTC month`}. Each different confirmed CV also gets one initial generation. Deleting and reuploading the same CV does not reset its allowance.</p>}
      {data.plan==='legacy'&&<p className="account-alert">Your continuity access has no automatic expiry. The migration preserved existing access.</p>}
      {data.beta_expires_at&&<p className="account-alert">Beta grant expiry: {new Date(data.beta_expires_at).toLocaleString()}. {data.beta_revoked_at?'This grant was revoked.':data.plan!=='invited_beta'?'This grant is inactive; base-plan allowances apply.':'On expiry, access returns to your base plan; saved data remains available.'}</p>}
      <section className="account-surface account-feature-usage"><div className="account-table-heading"><h2>Feature allowances</h2><p>Feature balances share the monthly total and are not additive.</p></div><div className="account-usage-table" tabIndex={0} role="region" aria-label="Feature allowance table"><table><caption className="sr-only">AI and speech request allowances</caption><thead><tr><th scope="col">Feature</th><th scope="col">Allowance</th><th scope="col">Reserved</th><th scope="col">Remaining</th><th scope="col">Availability</th></tr></thead><tbody>
        {Object.entries(data.features).map(([key,row])=><tr key={key}><th scope="row">{row.label}</th><td>{row.allowance}</td><td>{row.consumed}</td><td><strong>{row.remaining}</strong></td><td><span className={`account-availability ${row.state==='available'?'is-available':''}`}>{stateLabel(row.state)}</span></td></tr>)}
      </tbody></table></div></section>
      <div className="account-surface account-usage-explainer"><h2>Good to know</h2><p>Allowances apply only to new AI and speech requests. Your saved data, document editing, approved pack exports, and account deletion remain available.</p><details><summary>How requests are counted</summary><p>One unit is one bounded provider-request reservation. A pack request creates both documents; each interview question/assessment request costs one unit. Each transcription or spoken question also costs one unit.</p><p>Failures, timeouts and interrupted or unknown outcomes remain reserved because dispatch may have incurred usage. Invalid inputs rejected before reservation are not charged. These counts are not provider billing or payment records. Deleting results does not refund quota.</p><p>{data.history_note}</p></details><details><summary>Current accounting period</summary><p>Current period: {new Date(data.period_start).toISOString()} · Resets {new Date(data.reset_at).toISOString()} at 00:00 UTC.</p></details><details><summary>Billing and future pricing</summary><p>Billing is not available. There is no active checkout or payment collection.</p><p>Proposed future price: USD {data.proposed_monthly_price_usd}/month. {data.price_note}</p></details></div>
    </>}
    {!data&&!usage?.loading&&!usage?.error&&<p className="account-alert">Your usage information is unavailable. Refresh usage to try again.</p>}
  </section>;
}
export function UsageSettings(){return <Shell><UsageDetails/></Shell>;}
