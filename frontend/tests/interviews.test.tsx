import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {InterviewHome,InterviewSessionView} from '../components/InterviewPractice';
import type {Interview} from '../lib/interviews';
const {apiMock,push}=vi.hoisted(()=>({apiMock:vi.fn(),push:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('next/navigation',()=>({useRouter:()=>({push})}));
const config={provider:'deterministic-test',model:'synthetic-v1',reasoning:'minimal',max_output_tokens:2000};
const source={job:{title:'Engineer',company:'Example',description:'Build APIs'},source_kind:'reviewed_cv',cv_text:'Reviewed synthetic CV',candidate_profile:{headline:'Engineer'}};
const current={number:1,category:'behavioral',question:{strategy:'behavioral_example',source:'job',quote:'Build APIs'},text:'Describe a real situation.',answer:'Saved answer',feedback:null};
const session:Interview={id:'s',job_id:'j',status:'ready',revision:2,mode:'mixed',question_count:2,configuration:config,source_snapshot:source,turns:[current],guidance:{},actions:{},practice_actions:[],example_structures:{},practice_priorities:[],operations:[]};

describe('interview practice',()=>{
  beforeEach(()=>{apiMock.mockReset();push.mockReset();});
  it('shows loading and empty source states without invoking AI',async()=>{
    apiMock.mockImplementation((path:string)=>Promise.resolve(path.endsWith('/options')?{available:true,configuration:config,max_questions:6,resumes:[],packs:[]}:{items:[],next_cursor:null}));
    render(<InterviewHome jobId="j"/>);expect(screen.getByRole('status')).not.toBeNull();
    expect(await screen.findByText(/No reviewed CV or approved pack/)).not.toBeNull();
    expect(apiMock.mock.calls.every(c=>c.length===1)).toBe(true);
  });
  it('requires a preview and explicit information consent before creating a session',async()=>{
    apiMock.mockImplementation((path:string)=>Promise.resolve(path.endsWith('/options')?{available:true,configuration:config,max_questions:6,resumes:[{id:'r',name:'CV'}],packs:[]}:path.endsWith('/preview')?{source_snapshot:source,configuration:config,preview_hash:'h'.repeat(64)}:{items:[],next_cursor:null,id:'s'}));
    render(<InterviewHome jobId="j"/>);
    fireEvent.change(await screen.findByLabelText('Practice source'),{target:{value:'cv:r'}});
    fireEvent.click(screen.getByRole('button',{name:'Review information to send'}));
    const start=await screen.findByRole('button',{name:'Start interview'});expect(start.hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(start);
    await waitFor(()=>expect(push).toHaveBeenCalledWith('/interviews/s'));
    expect(apiMock.mock.calls.some(c=>c[0].includes('/advance'))).toBe(false);
  });
  it('resumes the saved answer and renders untrusted source text safely',async()=>{
    apiMock.mockResolvedValue({...session,source_snapshot:{...source,cv_text:'<img src=x onerror=alert(1)>'}});
    const {container}=render(<InterviewSessionView id="s"/>);
    expect((await screen.findByLabelText('Your answer') as HTMLTextAreaElement).value).toBe('Saved answer');
    expect(container.querySelector('img')).toBeNull();expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('saves the answer before a provider failure and never retries silently',async()=>{
    apiMock.mockResolvedValueOnce(session).mockResolvedValueOnce({...session,revision:3,turns:[{...current,answer:'New answer'}]}).mockRejectedValueOnce(new Error('Provider unavailable'));
    render(<InterviewSessionView id="s"/>);
    fireEvent.change(await screen.findByLabelText('Your answer'),{target:{value:'New answer'}});
    fireEvent.click(screen.getByRole('button',{name:'Submit answer and continue'}));
    expect(await screen.findByRole('alert')).not.toBeNull();
    expect((screen.getByLabelText('Your answer') as HTMLTextAreaElement).value).toBe('New answer');
    expect(apiMock.mock.calls.map(c=>c[0])).toEqual(['/interviews/s','/interviews/s/answer','/interviews/s/advance']);
    expect(apiMock.mock.calls[1][2]).toBe(false);expect(apiMock.mock.calls[2][2]).toBe(false);
  });
  it('pending and interrupted states do not issue a request on load',async()=>{
    apiMock.mockResolvedValue({...session,status:'generating'});render(<InterviewSessionView id="s"/>);
    expect((await screen.findByRole('button',{name:'Submit answer and continue'})).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('status').textContent).toContain('pending');expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('offers an explicit retry and deletion confirmation while preserving failed answers',async()=>{
    apiMock.mockResolvedValue({...session,status:'interrupted'});render(<InterviewSessionView id="s"/>);
    expect(await screen.findByRole('button',{name:'Retry this step explicitly'})).not.toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Delete session'}));
    expect(screen.getByRole('dialog')).not.toBeNull();expect(apiMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Confirm delete session'}));
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/interviews/s',{method:'DELETE'},false));
  });
});
