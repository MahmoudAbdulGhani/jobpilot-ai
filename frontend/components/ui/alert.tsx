import * as React from 'react';
import {cva,type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/utils';

const alertVariants=cva(
  'relative w-full rounded-lg border px-4 py-3 text-sm grid gap-2 [&>svg]:absolute [&>svg]:top-3.5 [&>svg]:left-4 [&>svg]:text-foreground [&>svg]:size-4',
  {
    variants:{
      variant:{
        default:'bg-card text-card-foreground',
        destructive:'border-destructive/50 bg-destructive/10 text-destructive [&>svg]:text-destructive dark:border-destructive',
        success:'border-transparent bg-[var(--success)]/10 text-[var(--success)] [&>svg]:text-[var(--success)]',
        warning:'border-transparent bg-[var(--warning)]/10 text-[var(--warning)] [&>svg]:text-[var(--warning)]',
      },
    },
    defaultVariants:{variant:'default'},
  }
);

function Alert({className,variant,...props}:React.ComponentProps<'div'>&VariantProps<typeof alertVariants>){
  return <div role="alert" data-slot="alert" data-variant={variant} className={cn(alertVariants({variant}),'pl-12',className)} {...props}/>;
}
function AlertTitle({className,...props}:React.ComponentProps<'div'>){
  return <div data-slot="alert-title" className={cn('font-medium leading-none tracking-tight',className)} {...props}/>;
}
function AlertDescription({className,...props}:React.ComponentProps<'div'>){
  return <div data-slot="alert-description" className={cn('text-sm [&_p]:leading-relaxed',className)} {...props}/>;
}

export {Alert,AlertTitle,AlertDescription};