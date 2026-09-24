'use client';
import * as React from 'react';
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog';
import {Button} from '@/components/ui/button';

interface ConfirmDialogProps{
  trigger:React.ReactNode;
  title:React.ReactNode;
  description?:React.ReactNode;
  confirmLabel?:string;
  cancelLabel?:string;
  destructive?:boolean;
  busy?:boolean;
  onConfirm:()=>void;
  onOpenChange?:(open:boolean)=>void;
}

function ConfirmDialog({trigger,title,description,confirmLabel='Confirm',cancelLabel='Cancel',destructive=false,busy=false,onConfirm,onOpenChange}:ConfirmDialogProps){
  return <AlertDialogPrimitive.Root onOpenChange={onOpenChange}>
    <AlertDialogPrimitive.Trigger asChild>{trigger}</AlertDialogPrimitive.Trigger>
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50"/>
      <AlertDialogPrimitive.Content className="fixed top-[50%] left-[50%] z-50 grid max-h-[calc(100dvh-2rem)] overflow-y-auto w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border border-border bg-card p-6 shadow-lg duration-200 sm:max-w-lg">
        <div className="flex flex-col gap-2 text-center sm:text-left">
          <AlertDialogPrimitive.Title className="text-lg font-semibold text-foreground">{title}</AlertDialogPrimitive.Title>
          {description?<AlertDialogPrimitive.Description className="text-sm text-muted-foreground">{description}</AlertDialogPrimitive.Description>:null}
        </div>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <AlertDialogPrimitive.Cancel asChild>
            <Button variant="outline" disabled={busy}>{cancelLabel}</Button>
          </AlertDialogPrimitive.Cancel>
          <AlertDialogPrimitive.Action asChild>
            <Button variant={destructive?'destructive':'default'} disabled={busy} onClick={onConfirm}>
              {busy?'Working…':confirmLabel}
            </Button>
          </AlertDialogPrimitive.Action>
        </div>
      </AlertDialogPrimitive.Content>
    </AlertDialogPrimitive.Portal>
  </AlertDialogPrimitive.Root>;
}

export {ConfirmDialog};
