'use client';
import {createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import {api} from './api';
export type Feature='profile'|'fit'|'pack'|'interview'|'transcription'|'speech';
export type FeatureUsage={label:string;allowance:number;consumed:number;remaining:number;state:'available'|'unavailable'|'not_in_plan'|'exhausted';unit:string};
export type Usage={plan:string;base_plan:string;beta_expires_at:string|null;beta_revoked_at:string|null;period_start:string;reset_at:string;reset_timezone:string;total:{allowance:number;consumed:number;remaining:number};features:Record<Feature,FeatureUsage>;admin:boolean;billing_available:false;proposed_monthly_price_usd:string;price_note:string;history_note:string};
type State={data:Usage|null;loading:boolean;error:string;refresh:()=>Promise<void>};
const Context=createContext<State|null>(null);
export function EntitlementsProvider({children}:{children:React.ReactNode}){
  const [data,setData]=useState<Usage|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const sequence=useRef(0);
  const refresh=useCallback(async()=>{const ticket=++sequence.current;setLoading(true);setError('');
    try{const value=await api<Usage>('/account/usage');if(ticket===sequence.current)setData(value);}
    catch{if(ticket===sequence.current)setError('Usage is unavailable. AI actions are paused; your saved data remains accessible.');}
    finally{if(ticket===sequence.current)setLoading(false);}
  },[]);
  useEffect(()=>{const requests=sequence;void refresh();const changed=()=>void refresh();window.addEventListener('jobpilot:usage-changed',changed);
    return()=>{requests.current++;window.removeEventListener('jobpilot:usage-changed',changed);};},[refresh]);
  return <Context.Provider value={{data,loading,error,refresh}}>{children}</Context.Provider>;
}
export const useEntitlements=()=>useContext(Context);
export function stateLabel(state:FeatureUsage['state']){
  return {available:'Available',unavailable:'Provider unavailable or disabled',not_in_plan:'Not included in this plan',exhausted:'Allowance exhausted',admin:'Admin access (unlimited)'}[state];
}
