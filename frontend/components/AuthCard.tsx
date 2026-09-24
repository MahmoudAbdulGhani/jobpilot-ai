import * as React from 'react';
import {ArrowUpRight, Compass, LockKey, Sparkle} from '@phosphor-icons/react';
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
    <aside className="account-auth-story" aria-label="About JobPilot">
      <div className="account-brand"><Compass size={30} weight="duotone" aria-hidden="true"/><span>JobPilot <span className="account-brand-ai">AI</span></span></div>
      <div className="account-story-content">
        <div className="account-story-kicker"><span/>A little direction. A new beginning.</div>
        <h2>Your next chapter,<br/><em>thoughtfully planned.</em></h2>
        <p>A calmer place to bring your experience, opportunities, and next steps together.</p>
        <div className="account-story-path" aria-label="Your career workspace">
          <div><span className="account-path-number">01</span><span><strong>Tell your story</strong><small>Your experience, in your own words.</small></span><ArrowUpRight size={18} aria-hidden="true"/></div>
          <div><span className="account-path-number">02</span><span><strong>Find your direction</strong><small>Keep the right opportunities in sight.</small></span><ArrowUpRight size={18} aria-hidden="true"/></div>
          <div><span className="account-path-number">03</span><span><strong>Take the next step</strong><small>Prepare, review, and apply with intention.</small></span><ArrowUpRight size={18} aria-hidden="true"/></div>
        </div>
      </div>
      <div className="account-story-foot"><LockKey size={16} aria-hidden="true"/><span>Your career. Your data. Your decisions.</span><Sparkle size={19} aria-hidden="true"/></div>
    </aside>
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
