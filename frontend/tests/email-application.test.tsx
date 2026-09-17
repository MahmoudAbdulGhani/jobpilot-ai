import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {EmailApplication} from '../components/EmailApplication';
const {apiMock,downloadMock}=vi.hoisted(()=>({apiMock:vi.fn(),downloadMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock,downloadResume:downloadMock}));
const row={id:'attempt',status:'review',snapshot_hash:'a'.repeat(64),outcome:null,provider_status:null,provider_message_id:null,
  snapshot:{sender:'sender@example.com',recipient:'recruiter@example.com',recipient_source:'Official job posting',subject:'Application',body:'Please review the attached documents.',provider:'google',pack_version:2},
  attachments:[{name:'cv-v2.pdf',size:123,sha256:'a'.repeat(64)},{name:'cover_letter-v2.pdf',size:321,sha256:'b'.repeat(64)}]};
const versions=[{pack_id:'pack',number:2,approved_at:'2026-09-17T12:00:00Z'}];
const mailbox={id:'mailbox',email:'sender@example.com',status:'connected',provider:'google',capabilities:['send']};
function initial(attempt:typeof row|null=row){apiMock.mockImplementation(async(path:string)=>path==='/mailboxes'?{items:[mailbox]}:{versions,items:attempt?[attempt]:[]});}

describe('email application approval',()=>{
  beforeEach(()=>{apiMock.mockReset();downloadMock.mockReset();});
  it('does not send on load and requires explicit confirmation of the immutable snapshot',async()=>{
    initial();render(<EmailApplication job={{id:'job',title:'Backend engineer'}}/>);
    const button=await screen.findByRole('button',{name:'Confirm and send application'});
    expect(button.hasAttribute('disabled')).toBe(true);expect(apiMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Official job posting')).not.toBeNull();expect(screen.getByRole('button',{name:'cv-v2.pdf'})).not.toBeNull();
    fireEvent.click(screen.getByRole('checkbox'));apiMock.mockResolvedValue({...row,status:'sent',application_id:'application',provider_message_id:'gmail-id'});
    fireEvent.click(button);
    expect(await screen.findByText(/Gmail accepted this email/)).not.toBeNull();
    expect(apiMock).toHaveBeenLastCalledWith('/jobs/job/email-applications/attempt/send',{method:'POST',body:JSON.stringify({snapshot_hash:row.snapshot_hash,confirm:true})},false);
    expect(screen.queryByRole('button',{name:'Confirm and send application'})).toBeNull();
  });
  it('cancels approval before editing content and does not guess the recipient',async()=>{
    initial();render(<EmailApplication job={{id:'job',title:'Backend engineer'}}/>);
    fireEvent.click(await screen.findByRole('checkbox'));
    apiMock.mockResolvedValue({...row,status:'cancelled'});
    fireEvent.click(screen.getByRole('button',{name:'Cancel review and edit'}));
    expect(await screen.findByLabelText('Recruitment email')).not.toBeNull();
    expect((screen.getByLabelText('Recruitment email') as HTMLInputElement).value).toBe('');
    expect(apiMock).toHaveBeenLastCalledWith('/jobs/job/email-applications/attempt/cancel',{method:'POST'},false);
    expect(screen.queryByRole('button',{name:'Confirm and send application'})).toBeNull();
  });
  it('never optimistically shows sent and only reads status after a lost response',async()=>{
    initial();render(<EmailApplication job={{id:'job',title:'Backend engineer'}}/>);
    fireEvent.click(await screen.findByRole('checkbox'));
    apiMock.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({...row,status:'unknown'});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and send application'}));
    expect(await screen.findByText(/Delivery is unknown/)).not.toBeNull();
    expect(screen.queryByText(/Gmail accepted this email/)).toBeNull();
    expect(apiMock.mock.calls.filter(([path])=>String(path).endsWith('/send'))).toHaveLength(1);
    expect(screen.queryByRole('button',{name:'Confirm and send application'})).toBeNull();
  });
  it.each(['queued','sending','failed','unknown','simulated'])('shows honest %s state',async status=>{
    initial({...row,status});render(<EmailApplication job={{id:'job',title:'Backend engineer'}}/>);
    await waitFor(()=>expect(screen.getByText(`Email status: ${status}`)).not.toBeNull());
    expect(screen.queryByRole('button',{name:'Confirm and send application'})).toBeNull();
    expect(screen.queryByText(/Gmail accepted this email/)).toBeNull();
  });
});
