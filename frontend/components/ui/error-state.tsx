import * as React from 'react';
import {ArrowClockwise} from '@phosphor-icons/react/dist/ssr';
import {Alert,AlertDescription,AlertTitle} from '@/components/ui/alert';
import {Button} from '@/components/ui/button';

interface ErrorStateProps{
  title?:React.ReactNode;
  message?:React.ReactNode;
  onRetry?:()=>void;
  retryLabel?:string;
}

function ErrorState({title='Something went wrong',message,onRetry,retryLabel='Try again'}:ErrorStateProps){
  return <Alert variant="destructive" role="alert">
    <AlertTitle>{title}</AlertTitle>
    {message?<AlertDescription>{message}</AlertDescription>:null}
    {onRetry?<Button variant="outline" size="sm" onClick={onRetry} className="mt-1 w-fit"><ArrowClockwise/>{retryLabel}</Button>:null}
  </Alert>;
}

export {ErrorState};