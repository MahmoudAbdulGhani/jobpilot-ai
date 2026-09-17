import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {AccountForm} from '../components/AccountForm';
import Onboarding from '../app/onboarding/page';
const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('../components/Shell',()=>({Shell:({children}:{children:React.ReactNode})=><>{children}</>}));
beforeEach(()=>{apiMock.mockReset();window.history.replaceState(null,'','/');});

it('displays delivery failure and does not claim email acceptance',async()=>{
 apiMock.mockRejectedValue(new Error('Account email delivery is unavailable'));
 render(<AccountForm mode="forgot-password"/>);
 fireEvent.change(screen.getByLabelText('Email'),{target:{value:'synthetic@example.com'}});
 fireEvent.click(screen.getByRole('button',{name:'Request account email'}));
 expect((await screen.findByRole('alert')).textContent).toContain('unavailable');
 expect(screen.queryByRole('status')).toBeNull();expect(apiMock).toHaveBeenCalledTimes(1);
 expect(apiMock.mock.calls[0][2]).toBe(false);
});
it('keeps reset tokens in memory and never submits automatically',async()=>{
 window.history.replaceState(null,'','/reset-password#token=synthetic-token-value-123');
 render(<AccountForm mode="reset-password"/>);
 expect(window.location.hash).toBe('');expect(apiMock).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Password',{exact:true}),{target:{value:'Synthetic-password-123'}});
 fireEvent.change(screen.getByLabelText('Confirm password'),{target:{value:'different-password'}});
 fireEvent.click(screen.getByRole('button',{name:'Change password'}));
 expect((await screen.findByRole('alert')).textContent).toContain('match');expect(apiMock).not.toHaveBeenCalled();
});
it('resumes onboarding with disabled AI and saves optional skipping',async()=>{
 apiMock.mockResolvedValueOnce({step:'cv',ai_enabled:false}).mockResolvedValueOnce({step:'job',ai_enabled:false});
 render(<Onboarding/>);
 expect(await screen.findByText(/AI features are unavailable/)).not.toBeNull();
 expect(screen.getByRole('status').textContent).toContain('Upload and review');
 fireEvent.click(screen.getByRole('button',{name:'Skip for now'}));
 await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('Save your first job'));
 expect(apiMock.mock.calls[1]).toEqual(['/account/onboarding',{method:'PATCH',body:'{"step":"job"}'},false]);
});
