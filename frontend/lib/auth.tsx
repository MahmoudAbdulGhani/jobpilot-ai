'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import * as client from './api'; import type { User } from './types';
type Context={user:User|null; loading:boolean; signIn:(e:string,p:string)=>Promise<void>; signOut:()=>Promise<boolean>};
const AuthContext=createContext<Context|null>(null);
export function AuthProvider({children}:{children:React.ReactNode}){const [user,setUser]=useState<User|null>(null);const [loading,setLoading]=useState(true);const router=useRouter();const path=usePathname();
 useEffect(()=>{client.restoreSession().then(setUser).catch(()=>setUser(null)).finally(()=>setLoading(false));},[]);
 useEffect(()=>{if(!loading&&!user&&!['/login','/register','/verify-email','/forgot-password','/reset-password'].includes(path))router.replace('/login');if(!loading&&user&&path==='/login')router.replace(user.onboarding_step && user.onboarding_step!=='done'?'/onboarding':'/overview');},[loading,user,path,router]);
 return <AuthContext.Provider value={{user,loading,signIn:async(e,p)=>setUser(await client.login(e,p)),signOut:async()=>{const ok=await client.logout();setUser(null);router.replace('/login');return ok;}}}>{children}</AuthContext.Provider>}
export function useAuth(){const x=useContext(AuthContext);if(!x)throw new Error('Missing AuthProvider');return x}
