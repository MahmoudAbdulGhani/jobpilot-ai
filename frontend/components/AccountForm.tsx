'use client';
import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { AuthCard } from './AuthCard';
import { Button } from './ui/button';
import { FormField } from './ui/form-field';
import { Input } from './ui/input';
import { ArrowRight, CircleNotch } from '@phosphor-icons/react';

type Mode = 'register' | 'verify-email' | 'forgot-password' | 'reset-password';
export function AccountForm({mode}:{mode:Mode}) {
 const [token,setToken]=useState(''); const [pending,setPending]=useState(false);
 const [error,setError]=useState(''); const [message,setMessage]=useState('');
 const [registration,setRegistration]=useState<string>('loading');
 const tokenLoaded=useRef(false);
 useEffect(()=>{if(!tokenLoaded.current){setToken(new URLSearchParams(window.location.hash.slice(1)).get('token')||''); window.history.replaceState(null,'',window.location.pathname);tokenLoaded.current=true;}
   if(mode==='register')api<{registration:string}>('/account/options',{},false).then(x=>setRegistration(x.registration)).catch(()=>setRegistration('unavailable'));
 },[mode]);
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();if(pending)return;setPending(true);setError('');setMessage('');
 const data=new FormData(e.currentTarget);const email=String(data.get('email')||'');const password=String(data.get('password')||'');
 if((mode==='register'||mode==='reset-password')&&password!==data.get('confirm')){setError('Passwords must match');setPending(false);return}
 const path=mode==='register'?'register':mode==='verify-email'?(token?'verify':'request/verify'):mode==='forgot-password'?'request/reset':'reset';
 const body=mode==='register'?{email,password,invitation:token||null}:mode==='reset-password'?{token,password}:mode==='verify-email'&&token?{token}:{email};
 try{const result=await api<{message:string}>('/account/'+path,{method:'POST',body:JSON.stringify(body)},false);setMessage(result.message)}catch(x){setError(x instanceof Error?x.message:'Account request failed')}finally{setPending(false)}
 }
 const title={'register':'Create your account','verify-email':'Verify your email','forgot-password':'Reset your password','reset-password':'Choose a new password'}[mode];
 const blocked=mode==='register'&&['closed','loading','unavailable'].includes(registration);
 const subtitle=mode==='register'?(registration==='invite-only'?'Use your email invitation to create a private career workspace.':registration==='public'?'Make room for your next chapter. Verify your email before signing in.':registration==='closed'?'Registration is currently closed. Existing members can still sign in.':registration==='loading'?'Loading registration options…':'Registration options unavailable. Reload to retry.'):mode==='forgot-password'?'Enter the email for your account and request a secure reset link.':mode==='verify-email'?(token?'Confirm your email address to finish setting up your workspace.':'Request a new verification link for your account email.'): 'Create a strong password to securely return to your workspace.';
 const submitLabel=pending?'Processing…':mode==='verify-email'&&token?'Verify email':mode==='reset-password'?'Change password':mode==='register'?'Create account':'Request account email';
 const footer=<><p>Already have an account? {mode==='reset-password'&&message?<a href="/login">Sign in <ArrowRight size={14} aria-hidden="true"/></a>:<Link href="/login">Sign in <ArrowRight size={14} aria-hidden="true"/></Link>}</p>{mode!=='verify-email'&&<Link className="account-subtle-link" href="/verify-email">Request verification email</Link>}</>;
 return <AuthCard eyebrow="JobPilot account" title={title} subtitle={subtitle} footer={footer}>
  <form onSubmit={submit} aria-busy={pending} className="account-form">
  {(mode==='register'||mode==='forgot-password'||(mode==='verify-email'&&!token))&&<FormField label="Email" htmlFor="email"><Input id="email" name="email" type="email" placeholder="you@example.com" autoComplete="email" required maxLength={255}/></FormField>}
  {mode==='register'&&registration==='invite-only'&&<FormField label="Invitation token" htmlFor="invitation" hint="You'll find this in your invitation email."><Input id="invitation" value={token} onChange={e=>setToken(e.target.value)} required maxLength={100} autoComplete="off"/></FormField>}
  {mode==='reset-password'&&!token&&<p className="account-alert" role="alert">Open the reset link from your account email.</p>}
  {(mode==='register'||mode==='reset-password')&&<><FormField label="Password" htmlFor="password" hint="Use 12–128 characters for your new password."><Input id="password" name="password" type="password" placeholder="Create a strong password" autoComplete="new-password" minLength={12} maxLength={128} required/></FormField><FormField label="Confirm password" htmlFor="confirm"><Input id="confirm" name="confirm" type="password" placeholder="Re-enter your password" autoComplete="new-password" minLength={12} maxLength={128} required/></FormField></>}
  {error&&<p role="alert" className="account-alert account-alert-error">{error}</p>}
  {message&&<p role="status" className="account-alert account-alert-success">{message}</p>}
  <Button type="submit" disabled={pending||blocked||(mode==='reset-password'&&!token)} className="account-submit">{pending&&<CircleNotch className="animate-spin" aria-hidden="true"/>}{submitLabel}{!pending&&<ArrowRight aria-hidden="true"/>}</Button>
  </form>
 </AuthCard>;
}
