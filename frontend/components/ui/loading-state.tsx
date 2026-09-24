import * as React from 'react';
import {SpinnerGap} from '@phosphor-icons/react/dist/ssr';
import {cn} from '@/lib/utils';
import {Skeleton} from '@/components/ui/skeleton';

interface LoadingStateProps{
  label?:string;
  rows?:number;
  className?:string;
}

function LoadingState({label='Loading…',rows=3,className}:LoadingStateProps){
  return <div data-slot="loading-state" role="status" className={cn('flex flex-col gap-4',className)}>
    <span className="sr-only">{label}</span>
    {Array.from({length:rows},(_,i)=><Skeleton key={i} className="h-16 w-full"/>)}
  </div>;
}

function Spinner({className}:{className?:string}){
  return <SpinnerGap aria-hidden="true" className={cn('animate-spin size-5',className)}/>;
}

export {LoadingState,Spinner};