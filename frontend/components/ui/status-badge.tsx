import * as React from 'react';
import {Badge} from '@/components/ui/badge';
import {cn} from '@/lib/utils';

const STATUS_VARIANT:Record<string,'success'|'warning'|'destructive'|'info'|'secondary'|'default'|'outline'>={
  applied:'success',
  interview:'info',
  offer:'default',
  accepted:'success',
  rejected:'destructive',
  withdrawn:'secondary',
  confirmed:'success',
  unreviewed:'warning',
  draft:'secondary',
  generating:'secondary',
  ready:'success',
  failed:'destructive',
  pass:'success',
  warn:'warning',
  synced:'success',
  pending:'warning',
  disconnected:'destructive',
  aiGenerated:'info',
  userProvided:'secondary',
};

interface StatusBadgeProps{
  status:string;
  label?:string;
  className?:string;
}

function normalize(status:string):string{
  switch(status){
    case 'ai-generated':return 'aiGenerated';
    case 'user-provided':return 'userProvided';
    default:return status;
  }
}

function StatusBadge({status,label,className}:StatusBadgeProps){
  const key=normalize(status);
  return <Badge variant={STATUS_VARIANT[key]??'outline'} className={cn('capitalize',className)}>
    {label??status.replace(/[_-]/g,' ')}
  </Badge>;
}

export {StatusBadge,STATUS_VARIANT};