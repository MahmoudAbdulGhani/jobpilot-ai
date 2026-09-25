import {render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import Detail from '../app/jobs/[id]/page';
import type {Job} from '../lib/types';

const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('next/navigation',()=>({useParams:()=>({id:'saved-1'}),useRouter:()=>({replace:vi.fn()})}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('../components/Shell',()=>({Shell:({children}:{children:React.ReactNode})=><main>{children}</main>}));
vi.mock('../components/Dialog',()=>({DeleteDialog:()=>null,JobEditor:()=>null,NotesEditor:()=>null}));
vi.mock('../components/JobDescription',()=>({JobDescription:({text}:{text:string|null})=><p>{text||'No description'}</p>}));
vi.mock('../components/JobFitAnalysis',()=>({JobFitAnalysis:()=>null}));
vi.mock('../components/ApplicationPacks',()=>({ApplicationPacks:({job}:{job:Job})=><p>Pack source: {job.description||'missing'}</p>}));
vi.mock('../components/AtsReport',()=>({AtsReport:()=>null}));
vi.mock('../components/EmailApplication',()=>({EmailApplication:()=>null}));
vi.mock('../components/ApplicationTracking',()=>({ApplicationTracking:()=>null}));

const job:Job={id:'saved-1',owner_id:'owner',title:'Python Developer',company:'Demo',location:'US',
  description:null,source_url:'https://employer.example/job',notes:null,is_archived:false,
  source_provider:'jobopportunities',source_external_id:'12345678-1234-4234-8234-123456789abc',
  source_snapshot:{source_url:'https://employer.example/job',published_at:null,deadline:null,salary:null,
    workplace_model:null,test_data:false,workplace_country:'US',workplace_city:'Adelphi'},
  created_at:'2026-09-25T12:00:00Z',updated_at:'2026-09-25T12:00:00Z'};

describe('saved source description refresh',()=>{
  beforeEach(()=>apiMock.mockReset());
  it('fills an older imported job before showing its pack',async()=>{
    apiMock.mockImplementation((path:string)=>Promise.resolve(String(path).includes('refresh-description')?
      {...job,description:'Employer requires Python and SQL.'}:job));
    render(<Detail/>);
    expect(await screen.findByText('Employer requires Python and SQL.')).not.toBeNull();
    expect(apiMock).toHaveBeenCalledWith('/discovery/saved/saved-1/refresh-description',{method:'POST'});
    expect(screen.getByText('Pack source: Employer requires Python and SQL.')).not.toBeNull();
    expect(screen.queryByRole('button',{name:'Edit job'})).toBeNull();
    expect((screen.getByText('Imported source details').parentElement as HTMLDetailsElement).open).toBe(true);
  });
  it('does not refresh a description already saved',async()=>{
    apiMock.mockResolvedValue({...job,description:'My saved description'});
    render(<Detail/>);
    expect(await screen.findByText('My saved description')).not.toBeNull();
    expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('explains when the public source has no advert text',async()=>{
    apiMock.mockImplementation((path:string)=>String(path).includes('refresh-description')?
      Promise.reject(new Error('The source does not provide a description for this listing.')):Promise.resolve(job));
    render(<Detail/>);
    expect((await screen.findByRole('alert')).textContent).toContain('The source does not provide a description');
    await waitFor(()=>expect(screen.queryByRole('button',{name:'Create tailored CV and cover letter'})).toBeNull());
  });
});
