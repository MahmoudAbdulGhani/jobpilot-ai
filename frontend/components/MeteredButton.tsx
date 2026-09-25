'use client';
import type {ButtonHTMLAttributes} from 'react';
import {useEntitlements,stateLabel,type Feature} from '../lib/entitlements';

export function MeteredButton({feature,disabled,children,...props}:ButtonHTMLAttributes<HTMLButtonElement>&{feature:Feature}){
  const usage=useEntitlements(),entry=usage?.data?.features?.[feature];
  const allowed=!!usage&&!usage.loading&&!usage.error&&(entry?.state==='available'||entry?.state==='admin');
  const explanation=!usage||usage.loading?'Checking allowance…':usage.error?'Usage unavailable':entry?stateLabel(entry.state):'Usage unavailable';
  return <><button {...props} disabled={disabled||!allowed} title={!allowed?explanation:props.title}>{children}</button>
    {!allowed&&<span className="muted" role="status"> {explanation}. <a href="/settings/usage">View usage</a></span>}</>;
}
