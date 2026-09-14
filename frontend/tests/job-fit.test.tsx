import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobFitAnalysis } from '../components/JobFitAnalysis';
import type { Job, JobFitAnalysis as Analysis } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const job: Job = {id:'job-1',owner_id:'user-1',title:'Engineer',company:'Acme',location:null,description:'Python is required',source_url:null,notes:'private',is_archived:false,created_at:'2026-09-14T10:00:00Z',updated_at:'2026-09-14T10:00:00Z'};
const analysis: Analysis = {id:'analysis-1',job_id:job.id,status:'ready',job_snapshot:{description:'Python is required'},profile_facts:[{id:'fact-1',path:'skills[0]',value:'Python'}],result:{requirements:[{id:'req-1',text:'Python',job_quote:'Python is required',importance:'required',assessment:'supported',explanation:'Relevant saved evidence.',candidate_fact_ids:['fact-1']}],strengths:['req-1: Python evidence'],gaps:[],actions:[],summary:'Evidence-backed review.'},counts:{supported:1,total:1},provider:'deterministic-test',model:'synthetic-v1',prompt_version:'job-fit-v1',outcome_message:null,is_outdated:false,created_at:'2026-09-14T10:00:00Z',updated_at:'2026-09-14T10:00:00Z'};

describe('JobFitAnalysis',()=>{
  beforeEach(()=>apiMock.mockReset());
  it('shows disclosure and prerequisites without generating',async()=>{apiMock.mockResolvedValueOnce(analysis).mockResolvedValueOnce({items:[analysis],total:1,page:1,page_size:10});render(<JobFitAnalysis job={{...job,description:null}}/>);expect(screen.getByText(/Notes, contact details/)).not.toBeNull();expect(screen.getByText(/Save a job description/)).not.toBeNull();expect(screen.getByRole('button',{name:/Analyze fit/}).hasAttribute('disabled')).toBe(true)});
  it('generates and renders persisted evidence',async()=>{apiMock.mockRejectedValueOnce(new Error('not found')).mockResolvedValueOnce(analysis).mockResolvedValueOnce(analysis).mockResolvedValueOnce({items:[analysis],total:1,page:1,page_size:10});render(<JobFitAnalysis job={job}/>);fireEvent.click(screen.getByRole('button',{name:/Analyze fit/}));expect(await screen.findByText('Evidence-backed review.')).not.toBeNull();expect(screen.getByText((_,element)=>element?.tagName==='BLOCKQUOTE'&&element.textContent?.includes('Python is required')===true)).not.toBeNull();expect(screen.getByRole('heading',{name:'Python'})).not.toBeNull();await waitFor(()=>expect(apiMock).toHaveBeenCalledWith(`/jobs/${job.id}/fit-analyses`,expect.objectContaining({method:'POST'})))});
});
