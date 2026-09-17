import type { NextConfig } from 'next';
const backend = process.env.JOBPILOT_BACKEND_ORIGIN;
const deployment = process.env.JOBPILOT_DEPLOYMENT || (process.env.NODE_ENV === 'production' ? 'production' : 'local');
if (!['local', 'test', 'production'].includes(deployment)) throw new Error('Invalid frontend deployment mode');
if (deployment === 'production') {
  let valid = false;
  try { const url = new URL(backend || ''); valid = url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash && url.pathname === '/' && !['localhost','127.0.0.1'].includes(url.hostname); } catch {}
  if (!valid || (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== '/api')) throw new Error('Production requires a trusted HTTPS backend origin and same-origin /api');
}
const nextConfig: NextConfig = {
  reactStrictMode: true, devIndicators: false, poweredByHeader: false,
  async rewrites() { return backend ? [{source:'/api/:path*',destination:`${backend.replace(/\/$/,'')}/api/:path*`}] : []; },
  async headers() { return [{source:'/:path*',headers:[{key:'Referrer-Policy',value:'no-referrer'},{key:'X-Content-Type-Options',value:'nosniff'},{key:'X-Frame-Options',value:'DENY'},...(deployment === 'production' ? [{key:'Strict-Transport-Security',value:'max-age=31536000'}] : [])]}]; },
};
export default nextConfig;
