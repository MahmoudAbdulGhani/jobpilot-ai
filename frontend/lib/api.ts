const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
let token: string | null = null;
let refreshFlight: Promise<boolean> | null = null;

export const setAccessToken = (value: string | null) => { token = value; };
function csrf() { return document.cookie.split('; ').find(v => v.startsWith('jobpilot_csrf='))?.split('=').slice(1).join('=') || ''; }
async function refresh() {
  if (!refreshFlight) refreshFlight = fetch(`${API}/auth/refresh`, { method:'POST', credentials:'include', headers:{'X-CSRF-Token':csrf()} })
    .then(async r => { if (!r.ok) return false; setAccessToken((await r.json()).access_token); return true; })
    .catch(() => false).finally(() => { refreshFlight = null; });
  return refreshFlight;
}
export async function api<T>(path:string, init:RequestInit = {}, retry=true):Promise<T> {
  const headers = new Headers(init.headers); if (token) headers.set('Authorization', `Bearer ${token}`); if (init.body) headers.set('Content-Type','application/json');
  const response = await fetch(`${API}${path}`, {...init, headers, credentials:'include'});
  if (response.status === 401 && retry && path !== '/auth/login' && await refresh()) return api<T>(path, init, false);
  if (!response.ok) { let message=`Request failed (${response.status})`; try { const b=await response.json(); message=typeof b.detail==='string'?b.detail:(b.detail?.[0]?.msg||message); } catch {} throw new Error(message); }
  return response.status === 204 ? undefined as T : response.json();
}
export async function restoreSession(){ if (!await refresh()) return null; return api<import('./types').User>('/auth/me'); }
export async function login(email:string,password:string){ const x=await api<{access_token:string}>('/auth/login',{method:'POST',body:JSON.stringify({email,password})},false); setAccessToken(x.access_token); return api<import('./types').User>('/auth/me'); }
export async function logout(){ try { if (!token) await refresh(); await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf()}},false); return true; } catch { return false; } finally { setAccessToken(null); } }
