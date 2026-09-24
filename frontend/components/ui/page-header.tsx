import * as React from 'react';
import {cn} from '@/lib/utils';

interface PageHeaderProps{
  eyebrow?:string;
  title:React.ReactNode;
  subtitle?:React.ReactNode;
  actions?:React.ReactNode;
  className?:string;
}

function PageHeader({eyebrow,title,subtitle,actions,className}:PageHeaderProps){
  return <header data-slot="page-header" className={cn('flex flex-col gap-4',className)}>
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-2">
        {eyebrow?<p className="text-xs font-semibold uppercase tracking-[0.04em] text-[var(--forest)]">{eyebrow}</p>:null}
        <h1 className="font-serif text-4xl leading-tight tracking-tight text-[var(--ink)] sm:text-5xl">{title}</h1>
        {subtitle?<p className="max-w-2xl text-base leading-relaxed text-muted-foreground">{subtitle}</p>:null}
      </div>
      {actions?<div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>:null}
    </div>
  </header>;
}

export {PageHeader};