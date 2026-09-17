import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {AccountDataSettings} from '../components/AccountDataSettings';
import {api,setAccessToken} from '../lib/api';
vi.mock('../lib/api',()=>({api:vi.fn(),downloadResume:vi.fn(),setAccessToken:vi.fn()}));
const request=vi.mocked(api);
beforeEach(()=>vi.clearAllMocks());
describe('account data',()=>{
 it('requires password and exact explicit confirmation',()=>{
  render(<AccountDataSettings/>);
  const remove=screen.getByRole('button',{name:'Permanently delete my account'});
  expect(remove.hasAttribute('disabled')).toBe(true);
  fireEvent.change(screen.getByLabelText('Confirm your password'),{target:{value:'synthetic'}});
  fireEvent.change(screen.getByLabelText(/Type DELETE/),{target:{value:'DELETE MY ACCOUNT'}});
  expect(remove.hasAttribute('disabled')).toBe(false);
  expect(request).not.toHaveBeenCalled();
 });
 it('shows pending deletion and failed cleanup honestly with a limited receipt',async()=>{
  request.mockResolvedValueOnce({id:'one',receipt:'private-receipt',status:'pending'}).mockResolvedValueOnce({status:'failed',failure:'local_cleanup_unconfirmed',provider_revocation_unconfirmed:true});
  render(<AccountDataSettings/>);
  fireEvent.change(screen.getByLabelText('Confirm your password'),{target:{value:'synthetic'}});
  fireEvent.change(screen.getByLabelText(/Type DELETE/),{target:{value:'DELETE MY ACCOUNT'}});
  fireEvent.click(screen.getByRole('button',{name:'Permanently delete my account'}));
  expect(await screen.findByText(/Deletion accepted/)).not.toBeNull();
  expect(setAccessToken).toHaveBeenCalledWith(null);
  fireEvent.click(screen.getByRole('button',{name:'Check deletion status'}));
  expect(await screen.findByText(/Cleanup failed; removal is not complete/)).not.toBeNull();
  expect(request).toHaveBeenLastCalledWith('/account/data/deletions/one/status',{method:'POST',body:JSON.stringify({receipt:'private-receipt'})},false);
 });
 it('shows server errors and clears the password',async()=>{
  request.mockRejectedValue(new Error('Reauthentication failed'));
  render(<AccountDataSettings/>);
  fireEvent.change(screen.getByLabelText('Confirm your password'),{target:{value:'wrong'}});
  fireEvent.click(screen.getByRole('button',{name:'Export my data'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent','Reauthentication failed');
  await waitFor(()=>expect((screen.getByLabelText('Confirm your password') as HTMLInputElement).value).toBe(''));
 });
});
