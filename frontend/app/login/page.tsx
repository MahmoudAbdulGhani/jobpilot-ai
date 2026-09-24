'use client';
import Link from 'next/link';
import {FormEvent,useState} from 'react';
import {useAuth} from '@/lib/auth';
import {AuthCard} from '@/components/AuthCard';
import {Button} from '@/components/ui/button';
import {FormField} from '@/components/ui/form-field';
import {Input} from '@/components/ui/input';
import {ArrowRight, CircleNotch, Eye, EyeSlash} from '@phosphor-icons/react';

export default function Login(){
  const{signIn,loading}=useAuth();
  const[pending,setPending]=useState(false);
  const[error,setError]=useState('');
  const[showPassword,setShowPassword]=useState(false);
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();if(pending)return;const d=new FormData(e.currentTarget);setPending(true);setError('');try{await signIn(String(d.get('email')),String(d.get('password')))}catch(x){setError(x instanceof Error?x.message:'Unable to sign in');setPending(false)}}
  if(loading)return <main className="center-state" role="status"><CircleNotch size={24} className="animate-spin" aria-hidden="true"/>Restoring your session…</main>;
  return <AuthCard eyebrow="YOUR CAREER WORKSPACE" title="Welcome back." subtitle="A fresh perspective on your next move. Sign in to pick up where you left off."
    footer={<><p>New to JobPilot? <Link href="/register">Create an account <ArrowRight size={14} aria-hidden="true"/></Link></p><Link className="account-subtle-link" href="/verify-email">Need to verify your email?</Link></>}>
    <form onSubmit={submit} aria-busy={pending} className="account-form">
      <FormField label="Email" htmlFor="login-email">
        <Input id="login-email" name="email" type="email" placeholder="you@example.com" autoComplete="username" required/>
      </FormField>
      <div className="account-password-field">
        <div className="account-field-label"><label htmlFor="login-password">Password</label><Link href="/forgot-password">Forgot password?</Link></div>
        <div className="account-password-input"><Input id="login-password" name="password" type={showPassword?'text':'password'} placeholder="Enter your password" autoComplete="current-password" required/><button type="button" aria-label={showPassword?'Hide password':'Show password'} aria-pressed={showPassword} onClick={()=>setShowPassword(!showPassword)}>{showPassword?<EyeSlash size={18}/>:<Eye size={18}/>}</button></div>
      </div>
      {error&&<p className="account-alert account-alert-error" role="alert">{error}</p>}
      <Button type="submit" disabled={pending} className="account-submit">{pending?<><CircleNotch className="animate-spin" aria-hidden="true"/>Signing in…</>:<>Sign in<ArrowRight aria-hidden="true"/></>}</Button>
    </form>
  </AuthCard>;
}
