import * as React from 'react';
import {Label} from '@/components/ui/label';
import {cn} from '@/lib/utils';

interface FormFieldProps{
  label?:React.ReactNode;
  htmlFor?:string;
  error?:React.ReactNode;
  hint?:React.ReactNode;
  required?:boolean;
  className?:string;
  children:React.ReactNode;
}

function FormField({label,htmlFor,error,hint,className,children}:FormFieldProps){
  const describedBy=error&&htmlFor?`${htmlFor}-error`:undefined;
  return <div data-slot="form-field" className={cn('flex flex-col gap-2',className)}>
    {label?<Label htmlFor={htmlFor}>{label}</Label>:null}
    {React.isValidElement(children)
      ?React.cloneElement(children as React.ReactElement<Record<string,unknown>>,{...error&&htmlFor?{'aria-describedby':describedBy}:null,'aria-invalid':error?'true':undefined})
      :children}
    {error&&htmlFor?<p id={describedBy} className="text-sm text-[var(--danger)]" role="alert">{error}</p>:null}
    {hint&&!error?<p className="text-sm text-muted-foreground">{hint}</p>:null}
  </div>;
}

export {FormField};