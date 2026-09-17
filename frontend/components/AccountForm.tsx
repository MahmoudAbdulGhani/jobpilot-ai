'use client';
import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';

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
 return <main className="login-page"><section className="login-card"><p className="eyebrow">JobPilot account</p><h1>{title}</h1>
 {mode==='register'&&<p>{registration==='invite-only'?'An email-bound invitation is required. New accounts have access only to their own data.':registration==='public'?'Registration is open. Verify your email before signing in.':registration==='closed'?'Registration is closed.':registration==='loading'?'Loading registration options…':'Registration options unavailable. Reload to retry.'}</p>}
 <form onSubmit={submit}>
 {(mode==='register'||mode==='forgot-password'||(mode==='verify-email'&&!token))&&<label>Email<input name="email" type="email" autoComplete="email" required maxLength={255}/></label>}
 {mode==='register'&&registration==='invite-only'&&<label>Invitation token<input value={token} onChange={e=>setToken(e.target.value)} required maxLength={100} autoComplete="off"/></label>}
 {mode==='reset-password'&&!token&&<p role="alert">Open the reset link from your account email.</p>}
 {(mode==='register'||mode==='reset-password')&&<><label>Password<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label><label>Confirm password<input name="confirm" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label></>}
 {error&&<p role="alert" className="form-error">{error}</p>}{message&&<p role="status" className="notice">{message}</p>}
 <button className="primary-button" disabled={pending||blocked||(mode==='reset-password'&&!token)}>{pending?'Processing…':mode==='verify-email'&&token?'Verify email':mode==='reset-password'?'Change password':mode==='register'?'Create account':'Request account email'}</button>
 </form><p>{mode==='reset-password'&&message?<a href="/login">Sign in</a>:<Link href="/login">Sign in</Link>} · <Link href="/verify-email">Request verification email</Link></p></section></main>
}
