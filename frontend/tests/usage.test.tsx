import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {EntitlementsProvider,type Usage} from '../lib/entitlements';
import {MeteredButton} from '../components/MeteredButton';
import {UsageDetails} from '../components/UsageSettings';
const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
const entry={label:'Application packs',allowance:2,consumed:1,remaining:1,state:'available',unit:'request'} as const;
const usage={plan:'free',base_plan:'free',beta_expires_at:null,beta_revoked_at:null,period_start:'2028-02-01T00:00:00Z',reset_at:'2028-03-01T00:00:00Z',reset_timezone:'UTC',total:{allowance:20,consumed:1,remaining:19},features:{pack:entry,fit:{...entry,label:'Job-fit analysis',state:'unavailable'}},billing_available:false,proposed_monthly_price_usd:'8.00',price_note:'Business hypothesis only; no subscription or checkout is available.',history_note:'Monthly accounting starts with the entitlement rollout.'} as Usage;

describe('server-driven usage and entitlements',()=>{
  beforeEach(()=>apiMock.mockReset());
  it('shows balances, UTC reset, unavailable features and billing hypothesis',async()=>{
    apiMock.mockResolvedValue(usage);render(<EntitlementsProvider><UsageDetails/></EntitlementsProvider>);
    expect(screen.getByRole('status').textContent).toContain('Loading');
    expect(await screen.findByRole('heading',{name:'Free access'})).not.toBeNull();
    expect(screen.getByText(/2028-03-01T00:00:00.000Z/)).not.toBeNull();
    expect(screen.getByText('Provider unavailable or disabled')).not.toBeNull();
    expect(screen.getByText(/Business hypothesis/)).not.toBeNull();
    expect(screen.queryByRole('button',{name:/pay|subscribe|checkout/i})).toBeNull();
  });
  it('blocks loading, exhausted and unavailable actions while leaving data actions usable',async()=>{
    const action=vi.fn();apiMock.mockResolvedValue({...usage,features:{...usage.features,pack:{...entry,state:'exhausted',remaining:0}}});
    render(<EntitlementsProvider><MeteredButton feature="pack" onClick={action}>Generate pack</MeteredButton><button>Export approved documents</button></EntitlementsProvider>);
    expect(screen.getByRole('button',{name:'Generate pack'}).hasAttribute('disabled')).toBe(true);
    await screen.findByText(/Allowance exhausted/);fireEvent.click(screen.getByRole('button',{name:'Generate pack'}));expect(action).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Export approved documents'}).hasAttribute('disabled')).toBe(false);
  });
  it('refreshes after dispatch without offering frontend plan assignments',async()=>{
    const action=vi.fn();apiMock.mockResolvedValueOnce(usage).mockResolvedValue({...usage,features:{...usage.features,pack:{...entry,state:'exhausted',remaining:0}}});
    render(<EntitlementsProvider><MeteredButton feature="pack" onClick={action}>Generate pack</MeteredButton></EntitlementsProvider>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Generate pack'}).hasAttribute('disabled')).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Generate pack'}));expect(action).toHaveBeenCalledTimes(1);
    fireEvent(window,new Event('jobpilot:usage-changed'));await screen.findByText(/Allowance exhausted/);
    expect(apiMock.mock.calls).toEqual([['/account/usage'],['/account/usage']]);
  });
  it('fails closed on usage errors and offers accessible refresh',async()=>{
    apiMock.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(usage);
    render(<EntitlementsProvider><UsageDetails/><MeteredButton feature="pack">Generate pack</MeteredButton></EntitlementsProvider>);
    expect(await screen.findByRole('alert')).not.toBeNull();expect(screen.getByRole('button',{name:'Generate pack'}).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Refresh usage'}));await screen.findByRole('heading',{name:'Free access'});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Generate pack'}).hasAttribute('disabled')).toBe(false));
  });
  it('keeps administrator AI actions enabled and shows unlimited profile access',async()=>{
    apiMock.mockResolvedValue({...usage,admin:true,profile_refreshes:{allowance:null,consumed:0,remaining:null,new_cv_initial_generation:true},features:{...usage.features,pack:{...entry,state:'admin',remaining:999999}}});
    render(<EntitlementsProvider><UsageDetails/><MeteredButton feature="pack">Generate pack</MeteredButton></EntitlementsProvider>);
    await screen.findByText(/AI profile refreshes: unlimited for administrators/);
    expect(screen.getByRole('button',{name:'Generate pack'}).hasAttribute('disabled')).toBe(false);
  });
});
