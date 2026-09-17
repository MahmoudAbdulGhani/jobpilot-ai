import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {DueReminders,ReminderEditor,Reminders} from '../components/Reminders';
const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
const item={application_id:'a',job_id:'j',title:'Engineer',company:'Example',application_status:'Applied',due_at:null,timezone:'UTC',status:'none',revision:0,overdue:false,reply_received:false};

describe('in-app reminders',()=>{
  beforeEach(()=>apiMock.mockReset());
  it('loads without any provider action and shows empty/error/retry states',async()=>{
    apiMock.mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({items:[],next_cursor:null});
    render(<Reminders/>);expect(screen.getByRole('status').textContent).toContain('Loading');
    expect(await screen.findByRole('alert')).not.toBeNull();fireEvent.click(screen.getByRole('button',{name:'Retry'}));
    expect(await screen.findByText('No reminders in this view.')).not.toBeNull();
    expect(apiMock.mock.calls.every(c=>c[0].startsWith('/reminders?')&&c.length===1)).toBe(true);
  });
  it('sends an explicit timezone and status confirmation with retries disabled',async()=>{
    apiMock.mockResolvedValue({...item,application_status:'Rejected'});render(<ReminderEditor applicationId="a"/>);
    fireEvent.change(await screen.findByLabelText('Reminder date and time'),{target:{value:'2030-01-01T10:00'}});
    fireEvent.change(screen.getByLabelText('Reminder timezone'),{target:{value:'Asia/Beirut'}});
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.submit(screen.getByRole('button',{name:'Create reminder'}).closest('form')!);
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/applications/a/reminder',{method:'POST',body:JSON.stringify({action:'create',revision:0,local_time:'2030-01-01T10:00',timezone:'Asia/Beirut',fold:null,confirm_terminal:true})},false));
  });
  it('shows confirmed reply warning without completing a reminder',async()=>{
    apiMock.mockResolvedValue({...item,status:'active',due_at:'2030-01-01T08:00:00Z',timezone:'Asia/Beirut',reply_received:true});
    render(<ReminderEditor applicationId="a"/>);
    expect(await screen.findByText('Reply received — review before following up')).not.toBeNull();
    expect((screen.getByLabelText('Reminder date and time') as HTMLInputElement).value).toBe('2030-01-01T10:00');
    expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('shows due reminders on app opening without scheduling external notifications',async()=>{
    apiMock.mockResolvedValue({items:[item],next_cursor:null});render(<DueReminders/>);
    expect(await screen.findByRole('link',{name:'You have due follow-up reminders'})).not.toBeNull();
    expect(apiMock).toHaveBeenCalledWith('/reminders?limit=1');
  });
  it('disables mutations while pending and keeps a failed edit visible',async()=>{
    let fail!:(error:Error)=>void;
    apiMock.mockResolvedValueOnce({...item,status:'active'}).mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}));
    render(<ReminderEditor applicationId="a"/>);
    fireEvent.click(await screen.findByRole('button',{name:'Complete reminder'}));
    expect(screen.getByRole('status').textContent).toContain('Saving');
    expect(screen.getByRole('button',{name:'Cancel reminder'}).closest('fieldset')?.disabled).toBe(true);
    fail(new Error('Reminder changed; reload before editing'));
    expect(await screen.findByRole('alert')).not.toBeNull();
  });
});
