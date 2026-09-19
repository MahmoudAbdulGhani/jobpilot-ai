'use client';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { FollowupSuggestions } from './FollowupSuggestions';

type Reminder = {application_id:string; job_id:string; title:string; company:string; application_status:string; due_at:string|null; timezone:string; status:string; revision:number; overdue:boolean; reply_received:boolean};
type Page = {items:Reminder[]; next_cursor:string|null};
const changed = () => window.dispatchEvent(new Event('reminders-changed'));
function localInput(item:Reminder) {
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:item.timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(item.due_at!));
  const part=(type:string)=>parts.find(p=>p.type===type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
function Due({item}:{item:Reminder}) { return <><p>{item.status} {item.overdue && '— Due now'}{item.due_at && <> · <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString(undefined,{timeZone:item.timezone})}</time> ({item.timezone})</>}</p>{item.reply_received && <p className="notice">Reply received — review before following up</p>}</>; }

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
    <h3 id={`reminder-${applicationId}`}>Follow-up reminder</h3>
    <p>In-app only. Check JobPilot for due reminders; no notifications while the app is closed. Nothing is sent automatically.</p>
    {error && <p role="alert" className="form-error">{error} <button onClick={()=>void load()}>Reload reminder</button></p>}
    {!item && !error && <p role="status">Loading reminder…</p>}
    {item && <><Due item={item}/><form onSubmit={e=>{e.preventDefault();void save(item.status==='none'?'create':'edit');}}>
      <fieldset disabled={pending}><legend>{item.status==='none'?'Create reminder':'Edit reminder'}</legend>
        <label>Reminder date and time<input type="datetime-local" required value={local} onChange={e=>setLocal(e.target.value)}/></label>
        <label>Reminder timezone<input required value={zone} onChange={e=>setZone(e.target.value)} placeholder="Asia/Beirut"/></label>
        <label>Repeated clock time<select value={fold} onChange={e=>setFold(e.target.value)}><option value="">Ask if ambiguous</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></select></label>
        {['Rejected','Withdrawn','Accepted','Offer'].includes(item.application_status) && <label><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>This application is {item.application_status}. I still want to schedule a follow-up.</label>}
        <button className="primary-button">{item.status==='none'?'Create reminder':'Save reminder'}</button>
        {item.status!=='none' && <><button type="button" onClick={()=>void save('snooze')}>Snooze to selected time</button><button type="button" onClick={()=>void save('complete')}>Complete reminder</button><button type="button" onClick={()=>void save('cancel')}>Cancel reminder</button></>}
      </fieldset></form>{pending && <p role="status">Saving reminder…</p>}</>}
  </section>;
}

export function Reminders() {
  const [view,setView]=useState('overdue'),[data,setData]=useState<Page|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
  const request=useRef(0);
  const load=useCallback(async(cursor?:string)=>{const current=++request.current;setPending(true);setError('');try{const result=await api<Page>(`/reminders?view=${view}${cursor?`&after=${cursor}`:''}`);if(current===request.current)setData(old=>cursor?{...result,items:[...(old?.items||[]),...result.items]}:result);}catch(e){if(current===request.current)setError((e as Error).message);}finally{if(current===request.current)setPending(false);}},[view]);
  useEffect(()=>{setData(null);void load();},[load]);
  return <section className="reminders-page"><h1>Follow-up reminders</h1><p>In-app only. Open JobPilot to check due reminders. No email is sent.</p><label>Show reminders<select value={view} onChange={e=>setView(e.target.value)}><option value="overdue">Overdue / due now</option><option value="upcoming">Upcoming</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label>
    {pending && <p role="status">Loading reminders…</p>}{error && <p role="alert">{error}<button onClick={()=>void load()}>Retry</button></p>}
    {data?.items.length===0 && <p>No reminders in this view.</p>}
    {data?.items.map(item=><article className="mailbox-card" key={item.application_id}><Link href={`/jobs/${item.job_id}`}>{item.title} · {item.company}</Link><Due item={item}/></article>)}
    {data?.next_cursor && <button disabled={pending} onClick={()=>void load(data.next_cursor!)}>Load more reminders</button>}
    <FollowupSuggestions/>
  </section>;
}

export function DueReminders() {
  const [due,setDue]=useState<boolean|null>(null);
  useEffect(()=>{let alive=true;const load=()=>{void api<Page>('/reminders?limit=1').then(p=>{if(alive)setDue(p.items.length>0);}).catch(()=>{if(alive)setDue(null);});};load();window.addEventListener('focus',load);window.addEventListener('reminders-changed',load);const timer=window.setInterval(load,60000);return()=>{alive=false;clearInterval(timer);window.removeEventListener('focus',load);window.removeEventListener('reminders-changed',load);};},[]);
  return <p className="notice"><Link href="/reminders">{due===true?'You have due follow-up reminders':due===false?'View follow-up reminders':'Check follow-up reminders'}</Link></p>;
}
