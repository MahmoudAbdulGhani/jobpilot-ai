'use client';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Archive, ArrowLeft, ArrowSquareOut, CalendarBlank, MapPin, NotePencil, Trash } from '@phosphor-icons/react';
import { Shell } from '../../../components/Shell';
import { DeleteDialog, JobEditor, NotesEditor } from '../../../components/Dialog';
import { JobDescription as Description } from '../../../components/JobDescription';
import { JobFitAnalysis } from '../../../components/JobFitAnalysis';
import { ApplicationPacks } from '../../../components/ApplicationPacks';
import { AtsReport } from '../../../components/AtsReport';
import { EmailApplication } from '../../../components/EmailApplication';
import { ApplicationTracking } from '../../../components/ApplicationTracking';
import { api } from '../../../lib/api';
import type { Job, JobInput } from '../../../lib/types';

export default function Detail() {
  const { id } = useParams<{id:string}>(); const router = useRouter();
  const [job,setJob] = useState<Job|null>(null); const [error,setError] = useState('');
  const [modal,setModal] = useState<'edit'|'notes'|'delete'|null>(null); const [busy,setBusy] = useState(false);
  useEffect(() => { api<Job>(`/jobs/${id}`).then(setJob).catch(error => setError(error.message)) }, [id]);
  async function patch(body:Partial<JobInput>&{is_archived?:boolean}) { const updated=await api<Job>(`/jobs/${id}`,{method:'PATCH',body:JSON.stringify(body)}); setJob(updated); setModal(null) }
  if(error)return <Shell><div className="center-state"><h1>Job not found</h1><p>{error}</p><Link className="text-button" href="/jobs">Back to saved jobs</Link></div></Shell>;
  if(!job)return <Shell><div className="center-state">Loading opportunity…</div></Shell>;
  const safeUrl=job.source_url&&/^https?:\/\//i.test(job.source_url)?job.source_url:null;
  return <Shell><nav className="breadcrumbs"><Link href={job.is_archived?'/archive':'/jobs'}>{job.is_archived?'Archive':'Saved jobs'}</Link><span>/</span><span>{job.company}</span></nav>
    <div className="job-workspace"><article className="job-reading"><header className="job-heading"><div className="heading-row"><p className="eyebrow">{job.is_archived?'Archived opportunity':'Saved opportunity'}</p><button className="icon-button" aria-label="Delete job" onClick={()=>setModal('delete')}><Trash size={21}/></button></div><h1>{job.title}</h1><p className="company-name">{job.company}</p><div className="job-meta">{job.location&&<span><MapPin size={21}/>{job.location}</span>}<span className="meta-dot">·</span><span><CalendarBlank size={21}/>{new Date(job.created_at).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})}</span></div><div className="job-actions"><button className="primary-button" onClick={()=>setModal('edit')}>Edit job</button>{safeUrl&&<a className="source-link" href={safeUrl} target="_blank" rel="noopener noreferrer">Open original posting <ArrowSquareOut size={18}/></a>}</div></header>
      <section className="description-section"><h2>About the role</h2><Description text={job.description}/></section><JobFitAnalysis job={job}/><section className="mailbox-card"><h2>Interview practice</h2><p>Practice privately using reviewed source material. Text only; no hiring predictions.</p><Link className="primary-button" href={`/jobs/${job.id}/interviews`}>Prepare interview practice</Link></section><ApplicationTracking job={job}/><ApplicationPacks job={job}/><AtsReport job={job}/><EmailApplication job={job}/><Link className="back-link" href={job.is_archived?'/archive':'/jobs'}><ArrowLeft size={20}/>Back to {job.is_archived?'archive':'saved jobs'}</Link></article>
      <aside className="job-rail"><section className="notes-section"><h2>My notes</h2><div className="notes-surface preserve-lines">{job.notes||'No personal notes yet.'}</div><button className="text-button edit-notes" onClick={()=>setModal('notes')}><NotePencil size={21}/>Edit notes</button></section><section className="saved-details"><h2>Saved details</h2>{job.source_provider && <p>Imported from {job.source_provider==='jobicy'?'Jobicy':'JobTech JobSearch'} / {job.source_external_id}{job.source_snapshot?.test_data ? " (synthetic test data)" : ""}. Original snapshot retained; edits are yours.</p>}{job.source_snapshot && <details><summary>Imported source details</summary><p>Published: {job.source_snapshot.published_at || "Not supplied"}</p><p>Deadline: {job.source_snapshot.deadline || "Not supplied"}</p><p>Salary: {job.source_snapshot.salary || "Not supplied"}</p><p>Workplace model: {job.source_snapshot.workplace_model || "Not supplied"}</p><p>Applicant region (source): {job.source_snapshot.applicant_region || "Unknown eligibility"}. Remote does not mean worldwide eligibility.</p><a href={job.source_snapshot.source_url} target="_blank" rel="noopener noreferrer">Original source at import</a></details>}<dl><div><dt>Added</dt><dd>{new Date(job.created_at).toLocaleDateString()}</dd></div><div><dt>Visibility</dt><dd>Only you</dd></div></dl></section><div className="archive-action"><button disabled={busy} className="text-button" onClick={async()=>{setBusy(true);try{await patch({is_archived:!job.is_archived})}finally{setBusy(false)}}}><Archive size={22}/>{job.is_archived?'Restore job':'Archive job'}</button></div></aside></div>
    {modal==='edit'&&<JobEditor job={job} onClose={()=>setModal(null)} onSave={patch}/>} {modal==='notes'&&<NotesEditor job={job} onClose={()=>setModal(null)} onSave={notes=>patch({notes})}/>} {modal==='delete'&&<DeleteDialog job={job} onClose={()=>setModal(null)} onDelete={async()=>{await api(`/jobs/${id}`,{method:'DELETE'});router.replace(job.is_archived?'/archive':'/jobs')}}/>}</Shell>
}
