import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {ReplyTimeline} from '../components/ReplyTimeline';
const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
const reply={id:'reply',job_id:'job',suggested_job_id:'job',match_kind:'reply_headers',sender:'recruiter@example.com',subject:'Response',preview:'<img src=x onerror=alert(1)>',received_at:'2026-09-17T12:00:00Z',corrected_at:null};
const data={items:[],jobs:[{id:'job',title:'Engineer',company:'Example'},{id:'other',title:'Other role',company:'Other'}],attempts:[{attempt_id:'attempt',provider:'google-test',send_status:'simulated',sync:null}]};

describe('reply timeline',()=>{
  beforeEach(()=>{apiMock.mockReset();apiMock.mockImplementation((path:string)=>Promise.resolve(path.includes('/classification')?null:data));});
  it('loads saved data without scanning and requires explicit sync action',async()=>{
    apiMock.mockResolvedValue(data);render(<ReplyTimeline jobId="job"/>);
    const button=await screen.findByRole('button',{name:'Sync replies (next bounded batch)'});
    expect(apiMock).toHaveBeenCalledTimes(1);expect(apiMock).toHaveBeenCalledWith('/jobs/job/replies');
    fireEvent.click(button);
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/jobs/job/email-applications/attempt/replies/sync',{method:'POST',body:'{"confirm":true}'},false));
  });
  it('renders previews as text and separates uncertain matches without changing status',async()=>{
    apiMock.mockResolvedValue({...data,items:[reply,{...reply,id:'uncertain',job_id:null,match_kind:'uncertain_thread'}]});
    const {container}=render(<ReplyTimeline jobId="job"/>);
    expect(await screen.findByText('Reply received')).not.toBeNull();
    expect(screen.getByText('Uncertain association — confirm before linking')).not.toBeNull();
    expect(container.querySelector('img')).toBeNull();expect(apiMock).toHaveBeenCalledTimes(3);
  });
  it('allows an explicit association correction to another owned job',async()=>{
    apiMock.mockResolvedValue({...data,items:[reply]});render(<ReplyTimeline jobId="job"/>);
    fireEvent.change(await screen.findByRole('combobox'),{target:{value:'other'}});
    fireEvent.click(screen.getByRole('button',{name:'Save association correction'}));
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/replies/reply/association',{method:'PATCH',body:'{"job_id":"other","confirm":true}'},false));
  });
  it('requires confirmation before erasing a preview',async()=>{
    apiMock.mockResolvedValue({...data,items:[reply]});render(<ReplyTimeline jobId="job"/>);
    fireEvent.click(await screen.findByRole('button',{name:'Dismiss and erase preview'}));
    expect(apiMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button',{name:'Confirm erase preview'}));
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/replies/reply/association',{method:'PATCH',body:'{"job_id":null,"confirm":true}'},false));
  });
  it('shows a cooldown without automatically retrying',async()=>{
    apiMock.mockResolvedValue({...data,attempts:[{...data.attempts[0],sync:{status:'rate_limited',retry_after:'2099-01-01T00:00:00Z'}}]});
    render(<ReplyTimeline jobId="job"/>);
    expect((await screen.findByRole('button',{name:'Sync replies (next bounded batch)'})).hasAttribute('disabled')).toBe(true);
    expect(apiMock).toHaveBeenCalledTimes(1);
  });
});
