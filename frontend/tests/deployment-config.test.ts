import {afterEach,expect,it,vi} from 'vitest';
afterEach(()=>{vi.unstubAllEnvs();vi.resetModules()});
it('production uses a same-origin API rewrite without browser credentials',async()=>{
 vi.stubEnv('JOBPILOT_DEPLOYMENT','production');vi.stubEnv('JOBPILOT_BACKEND_ORIGIN','https://api.example.com');vi.stubEnv('NEXT_PUBLIC_API_URL','/api');
 const config=(await import('../next.config')).default;
 expect(await config.rewrites?.()).toEqual([{source:'/api/:path*',destination:'https://api.example.com/api/:path*'}]);
});
it.each(['http://api.example.com','https://user:password@api.example.com',''])('rejects invalid production backend %s',async origin=>{
 vi.stubEnv('JOBPILOT_DEPLOYMENT','production');vi.stubEnv('JOBPILOT_BACKEND_ORIGIN',origin);vi.stubEnv('NEXT_PUBLIC_API_URL','/api');
 await expect(import('../next.config')).rejects.toThrow('trusted HTTPS backend origin');
});
it('rejects a cross-origin browser API in production',async()=>{
 vi.stubEnv('JOBPILOT_DEPLOYMENT','production');vi.stubEnv('JOBPILOT_BACKEND_ORIGIN','https://api.example.com');vi.stubEnv('NEXT_PUBLIC_API_URL','https://api.example.com/api');
 await expect(import('../next.config')).rejects.toThrow('same-origin');
});
