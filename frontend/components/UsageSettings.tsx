'use client';
import Link from 'next/link';
import {Shell} from './Shell';
import {useEntitlements,stateLabel} from '../lib/entitlements';

export function UsageDetails(){
  const usage=useEntitlements(),data=usage?.data;
  return <section className="collection-page"><Link href="/settings">Back to settings</Link><h1>Plan and usage</h1>
    <p>Billing is not available. There is no active checkout or payment collection.</p>
    <p>Allowances apply only to new AI and speech requests. You can always access your saved data, review/edit documents, export approved packs and request account deletion.</p>
    {usage?.loading&&<p role="status">Loading current allowance…</p>}
    {usage?.error&&<p role="alert">{usage.error}</p>}
    <button className="secondary-button" disabled={usage?.loading} onClick={()=>void usage?.refresh()}>Refresh usage</button>
    {data&&<>
      <h2>{({free:'Free access',legacy:'Existing-user continuity',invited_beta:'Invited beta'} as Record<string,string>)[data.plan]||'Access plan'}</h2>
      {data.plan==='legacy'&&<p>Your continuity access has no automatic expiry. The migration preserved existing access.</p>}
      {data.beta_expires_at&&<p>Beta grant expiry: {new Date(data.beta_expires_at).toLocaleString()}. {data.beta_revoked_at?'This grant was revoked.':data.plan!=='invited_beta'?'This grant is inactive; base-plan allowances apply.':'On expiry, access returns to your base plan; saved data remains available.'}</p>}
      <p>Current period: {new Date(data.period_start).toISOString()} · Resets {new Date(data.reset_at).toISOString()} at 00:00 UTC.</p>
      <p><strong>Shared monthly allowance:</strong> {data.total.consumed} reserved / {data.total.allowance} · {data.total.remaining} remaining.</p>
      <div className="usage-table"><table><caption>AI and speech request allowances</caption><thead><tr><th scope="col">Feature</th><th scope="col">Allowance</th><th scope="col">Reserved</th><th scope="col">Remaining</th><th scope="col">Availability</th></tr></thead><tbody>
        {Object.entries(data.features).map(([key,row])=><tr key={key}><th scope="row">{row.label}</th><td>{row.allowance}</td><td>{row.consumed}</td><td>{row.remaining}</td><td>{stateLabel(row.state)}</td></tr>)}
      </tbody></table></div>
      <p>One unit is one bounded provider-request reservation. A pack request creates both documents; each interview question/assessment request costs one unit. Each transcription or spoken question also costs one unit. Feature balances share the monthly total and are not additive.</p>
      <p>Failures, timeouts and interrupted or unknown outcomes remain reserved because dispatch may have incurred usage. Invalid inputs rejected before reservation are not charged. These counts are not provider billing or payment records. Deleting results does not refund quota.</p>
      <p>{data.history_note}</p><p>Proposed future price: USD {data.proposed_monthly_price_usd}/month. {data.price_note}</p>
    </>}
  </section>;
}
export function UsageSettings(){return <Shell><UsageDetails/></Shell>;}
