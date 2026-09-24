'use client';
import Link from 'next/link';
import { Bell } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { FollowupSuggestions } from './FollowupSuggestions';
import { ConfirmDialog } from './ui/confirm-dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { PageHeader } from './ui/page-header';

type Reminder = {application_id:string; job_id:string; title:string; company:string; application_status:string; due_at:string|null; timezone:string; status:string; revision:number; overdue:boolean; reply_received:boolean};
type Page = {items:Reminder[]; next_cursor:string|null};
const changed = () => window.dispatchEvent(new Event('reminders-changed'));
function localInput(item:Reminder) {
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:item.timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(item.due_at!));
  const part=(type:string)=>parts.find(p=>p.type===type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
function Due({item}:{item:Reminder}) { return <><p>{item.status} {item.overdue && '— Due now'}{item.due_at && <> · <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString(undefined,{timeZone:item.timezone})}</time> ({item.timezone})</>}</p>{item.reply_received && <p className="text-sm text-muted-foreground">Reply received — review before following up</p>}</>; }
const selectClass = 'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50';
const inputClass = 'h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50';

export function ReminderEditor({applicationId}:{applicationId:string}) {
  const [item,setItem]=useState<Reminder|null>(null), [error,setError]=useState(''), [pending,setPending]=useState(false);
  const [local,setLocal]=useState(''), [zone,setZone]=useState(()=>Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [fold,setFold]=useState(''), [confirm,setConfirm]=useState(false);
  const initialized=useRef(false);
  const load=useCallback(async()=>{try {const result=await api<Reminder>(`/applications/${applicationId}/reminder`);setItem(result);if(!initialized.current){initialized.current=true;if(result.due_at){setLocal(localInput(result));setZone(result.timezone);}}setError('');}catch(e){setError((e as Error).message);}},[applicationId]);
  useEffect(()=>{void load();const refresh=()=>void load();window.addEventListener('replies-changed',refresh);window.addEventListener('focus',refresh);return()=>{window.removeEventListener('replies-changed',refresh);window.removeEventListener('focus',refresh);};},[load]);
  async function save(action:string) {
    if(!item)return; setPending(true);setError('');
    try {const result=await api<Reminder>(`/applications/${applicationId}/reminder`,{method:'POST',body:JSON.stringify({action,revision:item.revision,local_time:local||null,timezone:zone,fold:fold===''?null:Number(fold),confirm_terminal:confirm})},false);setItem(result);setConfirm(false);changed();}
    catch(e){setError((e as Error).message);}finally{setPending(false);}
  }
  return <section className="mailbox-card reminder-editor" aria-labelledby={`reminder-${applicationId}`} aria-busy={pending}>
    <div className="flex flex-col gap-2">
      <h3 id={`reminder-${applicationId}`} className="font-serif text-2xl leading-snug text-[var(--ink)]">Follow-up reminder</h3>
      <p className="text-sm text-muted-foreground">In-app only. Check JobPilot for due reminders; no notifications while the app is closed. Nothing is sent automatically.</p>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-[var(--danger)]">{error} <button className="ml-2 text-[var(--forest)] underline underline-offset-4" onClick={()=>void load()}>Reload reminder</button></p>}
    {!item && !error && <p role="status" className="mt-3 text-sm text-muted-foreground">Loading reminder…</p>}
    {item && <><div className="mt-3"><Due item={item}/></div><form onSubmit={e=>{e.preventDefault();void save(item.status==='none'?'create':'edit');}}>
      <fieldset className="mt-3 grid gap-3" disabled={pending}><legend className="sr-only">{item.status==='none'?'Create reminder':'Edit reminder'}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-2"><Label htmlFor="reminder-date-time">Reminder date and time</Label><input id="reminder-date-time" type="datetime-local" required className={inputClass} value={local} onChange={e=>setLocal(e.target.value)}/></div>
          <div className="flex flex-col gap-2"><Label htmlFor="reminder-timezone">Reminder timezone</Label><input id="reminder-timezone" required className={inputClass} value={zone} onChange={e=>setZone(e.target.value)} placeholder="Asia/Beirut"/></div>
        </div>
        <div className="flex flex-col gap-2"><Label htmlFor="repeated-clock-time">Repeated clock time</Label><select id="repeated-clock-time" className={selectClass} value={fold} onChange={e=>setFold(e.target.value)}><option value="">Ask if ambiguous</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></select></div>
        {['Rejected','Withdrawn','Accepted','Offer'].includes(item.application_status) && <label className="flex items-start gap-2 text-sm text-muted-foreground"><input type="checkbox" className="mt-0.5 size-4 rounded border border-input accent-[var(--forest)]" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>This application is {item.application_status}. I still want to schedule a follow-up.</label>}
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={pending}>{item.status==='none'?'Create reminder':'Save reminder'}</Button>
          {item.status!=='none' && <>
            <Button type="button" variant="outline" disabled={pending} onClick={()=>void save('snooze')}>Snooze to selected time</Button>
            <ConfirmDialog title="Complete reminder" description="Mark this follow-up reminder as completed. You can create a new reminder for this application later if needed." confirmLabel="Complete reminder" busy={pending} onConfirm={()=>void save('complete')} trigger={<Button type="button" variant="outline" disabled={pending}>Complete reminder</Button>} />
            <ConfirmDialog title="Cancel reminder" description="This reminder will be cancelled and will no longer appear as due. You can create a new reminder for this application later if needed." confirmLabel="Cancel reminder" destructive busy={pending} onConfirm={()=>void save('cancel')} trigger={<Button type="button" variant="outline" disabled={pending}>Cancel reminder</Button>} />
          </>}
        </div>
      </fieldset></form>{pending && <p role="status" className="mt-3 text-sm text-muted-foreground">Saving reminder…</p>}</>}
  </section>;
}

export function Reminders() {
  const [view,setView]=useState('overdue'),[data,setData]=useState<Page|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
  const request=useRef(0);
  const load=useCallback(async(cursor?:string)=>{const current=++request.current;setPending(true);setError('');try{const result=await api<Page>(`/reminders?view=${view}${cursor?`&after=${cursor}`:''}`);if(current===request.current)setData(old=>cursor?{...result,items:[...(old?.items||[]),...result.items]}:result);}catch(e){if(current===request.current)setError((e as Error).message);}finally{if(current===request.current)setPending(false);}},[view]);
  useEffect(()=>{setData(null);void load();},[load]);
  return <section className="app-page" aria-label="Follow-up reminders">
    <PageHeader eyebrow="In-app only" title="Follow-up reminders" subtitle="In-app only. Open JobPilot to check due reminders. No email is sent." />
    <div className="mt-6 flex w-full max-w-xs flex-col gap-2"><Label htmlFor="reminder-view">Show reminders</Label><select id="reminder-view" className={selectClass} value={view} onChange={e=>setView(e.target.value)}><option value="overdue">Overdue / due now</option><option value="upcoming">Upcoming</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></div>
    {pending && <p role="status" className="mt-4 text-sm text-muted-foreground">Loading reminders…</p>}
    {error && <p role="alert" className="mt-4 text-sm text-[var(--danger)]">{error} <button className="ml-2 text-[var(--forest)] underline underline-offset-4" onClick={()=>void load()}>Retry</button></p>}
    {data?.items.length===0 && <p className="mt-4 text-sm text-muted-foreground">No reminders in this view.</p>}
    <ul className="mt-4 grid gap-3">
      {data?.items.map(item=><li key={item.application_id} className="rounded-lg border border-border bg-card p-5"><Link className="font-serif text-xl leading-snug text-[var(--ink)] [overflow-wrap:anywhere]" href={`/jobs/${item.job_id}`}>{item.title} · {item.company}</Link><div className="mt-2 text-sm text-muted-foreground"><Due item={item}/></div></li>)}
    </ul>
    {data?.next_cursor && <Button variant="outline" className="mt-4" disabled={pending} onClick={()=>void load(data.next_cursor!)}>Load more reminders</Button>}
    <div className="mt-8"><FollowupSuggestions/></div>
  </section>;
}

export function DueReminders() {
  const [due,setDue]=useState<boolean|null>(null);
  useEffect(()=>{let alive=true;const load=()=>{void api<Page>('/reminders?limit=1').then(p=>{if(alive)setDue(p.items.length>0);}).catch(()=>{if(alive)setDue(null);});};load();window.addEventListener('focus',load);window.addEventListener('reminders-changed',load);const timer=window.setInterval(load,60000);return()=>{alive=false;clearInterval(timer);window.removeEventListener('focus',load);window.removeEventListener('reminders-changed',load);};},[]);
  return <p><Link className="workspace-reminder" aria-label={due ? "You have due follow-up reminders" : "View follow-up reminders"} href="/reminders"><Bell size={20} aria-hidden="true" /><span>{due===true?'You have due follow-up reminders':due===false?'View follow-up reminders':'Check follow-up reminders'}</span></Link></p>;
}
