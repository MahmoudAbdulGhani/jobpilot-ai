// Isolate the feature widget; entitlement enforcement has dedicated connected tests.
vi.mock('../components/MeteredButton',()=>({MeteredButton:'button'}));
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobFitAnalysis } from '../components/JobFitAnalysis';
import type { Job, JobFitAnalysis as Analysis } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const job: Job = {id:'job-1',owner_id:'user-1',title:'Engineer',company:'Acme',location:null,description:'Python is required',source_url:null,notes:'private',is_archived:false,created_at:'2026-09-14T10:00:00Z',updated_at:'2026-09-14T10:00:00Z'};
const analysis: Analysis = {id:'analysis-1',job_id:job.id,status:'ready',job_snapshot:{description:'Python is required'},profile_facts:[{id:'fact-1',path:'skills[0]',value:'Python'}],result:{requirements:[{id:'req-1',text:'Python',job_quote:'Python is required',importance:'required',assessment:'supported',explanation:'Relevant saved evidence.',candidate_fact_ids:['fact-1']}],strengths:['req-1: Python evidence'],gaps:[],actions:[],summary:'Evidence-backed review.'},counts:{supported:1,total:1},provider:'deterministic-test',model:'synthetic-v1',prompt_version:'job-fit-v1',outcome_message:null,is_outdated:false,created_at:'2026-09-14T10:00:00Z',updated_at:'2026-09-14T10:00:00Z'};

describe('JobFitAnalysis',()=>{
  it('directs a consent error to the selected-job privacy setting',async()=>{
    apiMock.mockImplementation((_path:string,init?:RequestInit)=>init?.method==='POST'
      ? Promise.reject(new Error('AI data-use consent is required. Review Privacy settings before continuing.'))
      : Promise.reject(new Error('not found')));
    render(<JobFitAnalysis job={job}/>);
    fireEvent.click(screen.getByRole('button',{name:/Analyze fit/}));
    const link=await screen.findByRole('link',{name:'Allow selected job AI use in Privacy settings'});
    expect(link.getAttribute('href')).toBe('/settings#privacy');
    expect(screen.queryByRole('link',{name:'Review profile'})).toBeNull();
  });
  it('requires confirmation, saves a claimed skill, and marks fit stale',async()=>{
    const withGap:Analysis={...analysis,result:{...analysis.result!,requirements:[{id:'req-2',text:'Kubernetes',job_quote:'Kubernetes is required',importance:'required',assessment:'not_evidenced',explanation:'No saved profile evidence.',candidate_fact_ids:[],skill_name:'Kubernetes'}],missing_skills:[{skill:'Kubernetes',requirement_id:'req-2',job_quote:'Kubernetes is required',importance:'required'}]}};
    const profile={id:'profile-1',owner_id:'user-1',skills:['Python']};
    apiMock.mockImplementation((path:string,init?:RequestInit)=>{
      if(path==='/profile'&&init?.method==='PATCH')return Promise.resolve({...profile,skills:['Python','Kubernetes']});
      if(path==='/profile')return Promise.resolve(profile);
      return Promise.resolve(path.endsWith('/latest')?withGap:{items:[withGap],total:1,page:1,page_size:10});
    });
    render(<JobFitAnalysis job={job}/>);
    fireEvent.click(await screen.findByRole('button',{name:/I have this skill/}));
    expect(apiMock.mock.calls.some(([path,init])=>path==='/profile'&&init?.method==='PATCH')).toBe(false);
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button',{name:'Add Kubernetes'}));
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/profile',expect.objectContaining({method:'PATCH',body:JSON.stringify({skills:['Python','Kubernetes']})})));
    expect(await screen.findByText(/Added to your profile/)).not.toBeNull();
    expect(screen.getByText(/reanalysis needed/)).not.toBeNull();
  });
  it('shows named evidence gaps without calling them proven absent',async()=>{const withGap:Analysis={...analysis,result:{...analysis.result!,requirements:[...analysis.result!.requirements,{id:'req-2',text:'Kubernetes',job_quote:'Kubernetes is required',importance:'required',assessment:'not_evidenced',explanation:'No saved profile evidence.',candidate_fact_ids:[],skill_name:'Kubernetes'}],missing_skills:[{skill:'Kubernetes',requirement_id:'req-2',job_quote:'Kubernetes is required',importance:'required'}]}};apiMock.mockResolvedValueOnce(withGap).mockResolvedValueOnce({items:[withGap],total:1,page:1,page_size:10});render(<JobFitAnalysis job={job}/>);expect(await screen.findByRole('heading',{name:'Not evidenced in your saved profile'})).not.toBeNull();expect(screen.getAllByText('Kubernetes is required').length).toBeGreaterThan(0);expect(screen.queryByText('You lack Kubernetes')).toBeNull();});
  beforeEach(()=>{ apiMock.mockReset(); });
  it('requires explicit deletion confirmation and keeps the analysis after a failed delete', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') return Promise.reject(new Error('Could not delete saved analysis'));
      return Promise.resolve(path.endsWith('/latest') ? analysis : { items: [analysis] });
    });
    render(<JobFitAnalysis job={job} />);
    await screen.findByText('Evidence-backed review.');
    fireEvent.click(screen.getByText('Previous analyses (1)'));
    fireEvent.click(screen.getByRole('button', { name: /Delete analysis from/ }));
    const dialog = screen.getByRole('alertdialog');
    expect(apiMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete analysis' }));
    expect(await screen.findByText('Could not delete saved analysis')).toBeTruthy();
    expect(screen.getByText('Evidence-backed review.')).toBeTruthy();
  });
  it('shows disclosure and prerequisites without generating',async()=>{apiMock.mockResolvedValueOnce(analysis).mockResolvedValueOnce({items:[analysis],total:1,page:1,page_size:10});render(<JobFitAnalysis job={{...job,description:null}}/>);expect(screen.getByText(/Notes, contact details/)).not.toBeNull();expect(screen.getByText(/Save a job description/)).not.toBeNull();expect(screen.getByRole('button',{name:/Analyze fit/}).hasAttribute('disabled')).toBe(true)});
  it('generates and renders persisted evidence',async()=>{apiMock.mockRejectedValueOnce(new Error('not found')).mockResolvedValueOnce(analysis).mockResolvedValueOnce(analysis).mockResolvedValueOnce({items:[analysis],total:1,page:1,page_size:10});render(<JobFitAnalysis job={job}/>);fireEvent.click(screen.getByRole('button',{name:/Analyze fit/}));expect(await screen.findByText('Evidence-backed review.')).not.toBeNull();expect(screen.getByText((_,element)=>element?.tagName==='BLOCKQUOTE'&&element.textContent?.includes('Python is required')===true)).not.toBeNull();expect(screen.getByRole('heading',{name:'Python'})).not.toBeNull();await waitFor(()=>expect(apiMock).toHaveBeenCalledWith(`/jobs/${job.id}/fit-analyses`,expect.objectContaining({method:'POST'})))});
});
