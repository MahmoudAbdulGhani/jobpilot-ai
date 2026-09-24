'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Shell } from '../../components/Shell';
import { api } from '../../lib/api';
import { PageHeader } from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { ErrorState } from '@/components/ui/error-state';
import { LoadingState } from '@/components/ui/loading-state';
import { Alert,AlertDescription,AlertTitle } from '@/components/ui/alert';
import { ArrowRight, Check, FileText, ShieldCheck, Sparkle, Suitcase, UserCircle, WarningCircle } from '@phosphor-icons/react/dist/ssr';
import '@/app/account.css';

type Progress={step:string;ai_enabled:boolean};
const steps=[{id:'profile',name:'Build your profile',href:'/profile',description:'Bring your experience, skills, and career direction together. Add your career facts manually; AI is optional.',icon:UserCircle,action:'Open profile'},{id:'cv',name:'Upload and review a CV',href:'/resumes',description:'Give your experience a home. Upload your document, review the extracted text, and confirm what represents you.',icon:FileText,action:'Open CVs'},{id:'job',name:'Save your first job',href:'/jobs',description:'Start with an opportunity that catches your eye. Save a job manually, or explore the available job sources.',icon:Suitcase,action:'Open saved jobs'}];
export default function Page(){const [progress,setProgress]=useState<Progress|null>(null);const [error,setError]=useState('');const [pending,setPending]=useState(false);const [reload,setReload]=useState(0);
 useEffect(()=>{setProgress(null);setError('');api<Progress>('/account/onboarding').then(setProgress).catch(()=>setError('Unable to load onboarding. Reload to retry.'))},[reload]);
 async function advance(step:string){if(pending)return;setPending(true);setError('');try{setProgress(await api<Progress>('/account/onboarding',{method:'PATCH',body:JSON.stringify({step})},false))}catch{setError('Unable to save progress. Try again.')}finally{setPending(false)}}
 const currentName=progress?steps.find(s=>s.id===progress.step)?.name:undefined;
 const isLastStep=progress?progress.step===steps[steps.length-1].id:false;
 const currentIndex=progress?.step==='done'?3:Math.max(0,steps.findIndex(s=>s.id===progress?.step));
 return <Shell><div className="collection-page account-onboarding">
  <PageHeader eyebrow="Getting started" title="Make space for your next chapter." subtitle="A few thoughtful steps to make this workspace yours. Go at your own pace; your progress is saved along the way."/>
  {error&&<ErrorState message={error} onRetry={()=>setReload(r=>r+1)}/>}
  {!progress&&!error&&<div className="flex flex-col gap-4"><LoadingState label="Loading your progress…" rows={3}/></div>}
  {progress&&<>
   {!progress.ai_enabled&&<Alert variant="warning"><WarningCircle size={18}/><AlertTitle>AI features are unavailable</AlertTitle><AlertDescription>Profiles, CV upload/review and saved jobs remain available.</AlertDescription></Alert>}
   <div className="account-onboarding-layout"><div className="account-steps">
    <div className="account-progress-heading"><div><span className="account-kicker">YOUR STARTING POINT</span><p role="status">{progress.step==='done'?'Onboarding complete. You can revisit any step below.':`Current step: ${currentName??'any remaining step below'}`}</p></div><span className="account-step-count">{progress.step==='done'?<Check size={18} aria-label="Complete"/>:`0${currentIndex+1}`}<span>/ 03</span></span></div>
    <div className="account-step-progress" aria-hidden="true">{steps.map((step,index)=><span className={index<=currentIndex?'is-active':''} key={step.id}/>)}</div>
    {steps.map((step,index)=><article className={`account-step-card ${progress.step===step.id?'is-current':''}`} key={step.id} aria-current={progress.step===step.id?'step':undefined}>
      <div className="account-step-icon"><step.icon size={25} weight="duotone" aria-hidden="true"/></div>
      <div className="account-step-body"><div className="account-step-title"><span className="account-kicker">STEP 0{index+1}</span>{progress.step===step.id&&<span className="account-pill">Your next step</span>}</div><h2>{step.name}</h2><p>{step.description}</p>
      <div className="account-step-actions"><Button asChild variant={progress.step===step.id?'default':'outline'}><Link href={step.href}>{step.action}<ArrowRight aria-hidden="true"/></Link></Button>{step.id==='job'&&<Button asChild variant="ghost"><Link href="/discover">Discover jobs</Link></Button>}</div>
      {progress.step===step.id&&<div className="account-step-completion"><span>Already taken care of this?</span><div><Button variant="ghost" size="sm" disabled={pending} onClick={()=>advance(steps[index+1]?.id||'done')} aria-busy={pending}>{pending?'Saving…':'Mark step done'}<Check aria-hidden="true"/></Button>{!isLastStep&&<Button variant="ghost" size="sm" disabled={pending} onClick={()=>advance(steps[index+1]?.id||'done')} aria-busy={pending}>{pending?'Saving…':'Skip for now'}</Button>}</div></div>}
      </div>
    </article>)}
    {progress.step==='done'&&<Button asChild><Link href="/jobs">Go to saved jobs<ArrowRight aria-hidden="true"/></Link></Button>}
   </div><aside className="account-start-note"><Sparkle size={28} weight="duotone" aria-hidden="true"/><h2>A workspace that follows your lead.</h2><p>All steps are optional. Start with what you have and add the rest when you are ready.</p><div><ShieldCheck size={21} aria-hidden="true"/><p>Gmail and AI access are not required. You decide when to connect a service or use an AI feature.</p></div><Link href="/settings">Explore your privacy settings<ArrowRight size={16} aria-hidden="true"/></Link></aside>
   </div>
  </>}
 </div></Shell>;
}
