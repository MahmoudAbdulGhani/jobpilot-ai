import * as React from 'react';
import {cn} from '@/lib/utils';

interface EmptyStateProps{
  icon?:React.ReactNode;
  title:React.ReactNode;
  description?:React.ReactNode;
  action?:React.ReactNode;
  tone?:'default'|'muted';
  className?:string;
}

function EmptyState({icon,title,description,action,tone='default',className}:EmptyStateProps){
  return <div data-slot="empty-state" className={cn('flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center',tone==='muted'?'border-muted bg-muted/30':'border-border bg-background',className)}>
    {icon?<div className="flex size-12 items-center justify-center rounded-full bg-accent text-[var(--forest)]">{icon}</div>:null}
    <div className="flex flex-col gap-1">
      <p className="font-serif text-2xl leading-snug text-[var(--ink)]">{title}</p>
      {description?<p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>:null}
    </div>
    {action?<div className="mt-1">{action}</div>:null}
  </div>;
}

export {EmptyState};