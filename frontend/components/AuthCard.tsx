import * as React from 'react';
import {Compass, LockKey} from '@phosphor-icons/react';
import {cn} from '@/lib/utils';
import '@/app/account.css';

interface AuthCardProps{
  eyebrow?:string;
  title:string;
  subtitle?:React.ReactNode;
  footer?:React.ReactNode;
  maxWidth?:string;
  className?:string;
  children:React.ReactNode;
}

function AuthCard({eyebrow,title,subtitle,footer,maxWidth='max-w-md',className,children}:AuthCardProps){
  return <main className="account-auth">
    <div className="account-auth-form-side">
      <div className="account-mobile-brand"><Compass size={28} weight="duotone" aria-hidden="true"/>JobPilot AI</div>
      <section className={cn('account-auth-card',maxWidth,className)}>
        <div className="account-auth-heading">
          {eyebrow?<p className="eyebrow">{eyebrow}</p>:null}
          <h1>{title}</h1>
          {subtitle?<p className="account-subtitle">{subtitle}</p>:null}
        </div>
        {children}
        {footer?<div className="account-auth-footer">{footer}</div>:null}
      </section>
      <p className="account-auth-note"><LockKey size={14} aria-hidden="true"/>A private workspace for your next move.</p>
    </div>
  </main>;
}

export {AuthCard};
