import {fireEvent,render,screen} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {MailboxSettings} from '../components/MailboxSettings';
const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('../components/Shell',()=>({Shell:({children}:{children:React.ReactNode})=><main>{children}</main>}));
const row={id:'one',email:'mailbox@example.test',provider:'google',capabilities:['send'],status:'connected',expires_at:null};
describe('mailbox settings',()=>{
  beforeEach(()=>{apiMock.mockReset();window.history.replaceState(null,'','/settings');});
  it('loads without starting OAuth or reading mail',async()=>{
    apiMock.mockResolvedValue({available:true,test_provider:false,items:[]});render(<MailboxSettings/>);
    expect(await screen.findByRole('button',{name:'Connect Gmail'})).not.toBeNull();
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText('Allow sending applications') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText('Allow reading replies') as HTMLInputElement).checked).toBe(false);
    expect(screen.getAllByText(/whole mailbox/).length).toBe(1);
  });
  it('shows denied consent and removes callback outcome from URL',async()=>{
    window.history.replaceState(null,'','/settings?mailbox=denied');apiMock.mockResolvedValue({available:true,items:[]});render(<MailboxSettings/>);
    expect(await screen.findByText(/Consent was denied/)).not.toBeNull();expect(window.location.search).toBe('');
  });
  it('shows not configured without exposing credentials',async()=>{
    apiMock.mockResolvedValue({available:false,items:[]});render(<MailboxSettings/>);
    expect((await screen.findByRole('button',{name:'Connect Gmail'})).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/not configured on this server/)).not.toBeNull();
  });
  it('requires explicit confirmation for disconnect',async()=>{
    apiMock.mockResolvedValueOnce({available:true,items:[row]}).mockResolvedValueOnce({status:'disconnected'}).mockResolvedValueOnce({available:true,items:[{...row,status:'disconnected',capabilities:[]}]});render(<MailboxSettings/>);
    fireEvent.click(await screen.findByRole('button',{name:'Disconnect'}));
    expect(apiMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Confirm disconnect and revoke'}));
    expect(await screen.findByText('Status: disconnected')).not.toBeNull();
    expect(apiMock).toHaveBeenCalledWith('/mailboxes/one/disconnect',{method:'POST'});
  });
  it.each(['expired','reconnect_required','revoke_failed'])('shows %s state',async status=>{
    apiMock.mockResolvedValue({available:true,items:[{...row,status}]});render(<MailboxSettings/>);
    expect(await screen.findByText('Status: '+status.replaceAll('_',' '))).not.toBeNull();
  });
});
