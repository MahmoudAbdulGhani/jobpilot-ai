import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {Discovery, type DiscoveredJob} from '../components/Discovery';

const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('../components/Shell',()=>({Shell:({children}:{children:React.ReactNode})=><main>{children}</main>}));

const capability=(label:string,filters:string[],coverage='Limited source coverage.')=>({label,coverage,filters,remote_accuracy:'approximate',pagination:'offset',ai_description:'when_supplied',application:'source_link',attribution_url:'https://example.test'});
const sources={jobtech:capability('JobTech JobSearch',['country','region','city','remote']),jobicy:capability('Jobicy',['eligibility','remote']),jobopportunities:capability('Job Opportunities API',['country','city','us_state','remote'],'Worldwide first page, up to 50 results per search.')};
const job:DiscoveredJob={source:'jobtech',external_id:'123',title:'Backend Engineer',company:'Demo AB',location:'Stockholm, Sweden',description:'<script>unsafe()</script>',source_url:'https://arbetsformedlingen.se/platsbanken/annonser/123',published_at:null,deadline:null,salary:null,workplace_model:null,existing_job_id:null,test_data:false};

describe('reviewed discovery',()=>{
  let item:DiscoveredJob;
  beforeEach(()=>{
    item=job;apiMock.mockReset();
    apiMock.mockImplementation((path:string)=>{
      if(path==='/discovery/sources')return Promise.resolve({sources});
      if(path==='/digest/preferences')return Promise.resolve({cadence:'off'});
      if(path.startsWith('/digest/'))return Promise.resolve({generated_at:'',cadence:'off',items:[],skipped_invalid:0,delivery:{enabled:false,reason:'test'}});
      if(path.startsWith('/discovery?'))return Promise.resolve({items:[item],total:1,offset:0,next_offset:null});
      if(path.includes('/preview'))return Promise.resolve({job:item,preview_token:'signed',expires_at:'2026-09-17T12:00:00Z'});
      if(path==='/discovery/import')return Promise.resolve({job:{id:'saved-1'},already_saved:false});
      return Promise.reject(new Error('Unexpected route '+path));
    });
  });
  it('exposes source capabilities and separates workplace from eligibility',async()=>{
    render(<Discovery/>);
    expect(await screen.findByText(/Limited source coverage/)).not.toBeNull();
    expect(screen.getByLabelText('Workplace country')).not.toBeNull();
    expect(screen.queryByLabelText('Applicant eligibility (source text)')).toBeNull();
    expect(screen.getByLabelText('Approximate remote matches (source phrase matching)')).not.toBeNull();
    expect(apiMock).toHaveBeenCalledWith('/discovery/sources');
  });
  it('uses one JobTech geography at a time and connects reviewed import to materials',async()=>{
    const {container}=render(<Discovery/>);
    fireEvent.change(screen.getByLabelText('Workplace country'),{target:{value:'Sweden'}});
    fireEvent.change(screen.getByLabelText('Workplace region'),{target:{value:'Stockholms län'}});
    fireEvent.change(screen.getByLabelText('Workplace municipality'),{target:{value:'Stockholm'}});
    fireEvent.click(screen.getByRole('button',{name:'Search JobTech JobSearch'}));
    fireEvent.click(await screen.findByRole('button',{name:'Preview job'}));
    expect(await screen.findByText('<script>unsafe()</script>')).not.toBeNull();
    expect(container.querySelector('script')).toBeNull();
    const url=apiMock.mock.calls.find(call=>String(call[0]).startsWith('/discovery?'))?.[0] as string;
    const params=new URLSearchParams(url.split('?')[1]);
    expect(params.get('country')).toBe('');expect(params.get('region')).toBe('');expect(params.get('city')).toBe('Stockholm');
    fireEvent.click(screen.getByRole('button',{name:'Import this job into saved jobs'}));
    expect((await screen.findByRole('link',{name:'Create tailored application pack'})).getAttribute('href')).toBe('/jobs/saved-1#materials');
  });
  it('keeps Jobicy eligibility separate from workplace location',async()=>{
    item={...job,source:'jobicy',source_url:'https://jobicy.com/jobs/123-role',location:null,applicant_region:'EMEA',remote_arrangement:'remote'};
    render(<Discovery/>);fireEvent.change(screen.getByLabelText('Source'),{target:{value:'jobicy'}});
    expect(screen.queryByLabelText('Workplace country')).toBeNull();
    fireEvent.change(screen.getByLabelText('Applicant eligibility (source text)'),{target:{value:'EMEA'}});
    fireEvent.click(screen.getByRole('button',{name:'Search Jobicy'}));
    expect(await screen.findByText('EMEA')).not.toBeNull();
    const url=apiMock.mock.calls.find(call=>String(call[0]).startsWith('/discovery?'))?.[0] as string;
    expect(new URLSearchParams(url.split('?')[1]).get('eligibility')).toBe('EMEA');
  });
  it('shows worldwide first-page and remote confidence limits',async()=>{
    item={...job,source:'jobopportunities',external_id:'12345678-1234-4234-8234-123456789abc',source_url:'https://employer.example/jobs/1',apply_url:'https://employer.example/jobs/1',upstream_source:'greenhouse',applicant_region:null,remote_inferred:true,description:'Employer requires Python and SQL.'};
    render(<Discovery/>);fireEvent.change(screen.getByLabelText('Source'),{target:{value:'jobopportunities'}});
    fireEvent.change(screen.getByLabelText('Workplace country'),{target:{value:'FR'}});
    expect((screen.getByLabelText('Workplace US state') as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Workplace country'),{target:{value:'US'}});
    fireEvent.change(screen.getByLabelText('Workplace US state'),{target:{value:'NY'}});
    fireEvent.click(screen.getByRole('button',{name:'Search Job Opportunities API'}));
    expect(await screen.findByText(/Worldwide public search shows one page of up to 50/)).not.toBeNull();
    expect(screen.getByText('Employer requires Python and SQL.')).not.toBeNull();
    expect(screen.getByText(/Jobs without advert text are excluded/)).not.toBeNull();
    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0);
    expect(screen.getByRole('link',{name:'View employer posting'}).getAttribute('href')).toBe(item.source_url);
    expect(screen.queryByRole('button',{name:'Next results'})).toBeNull();
  });
  it('surfaces safe errors and restores the search button',async()=>{
    apiMock.mockImplementation((path:string)=>path.startsWith('/discovery?')?Promise.reject(new Error('Source unavailable')):path==='/discovery/sources'?Promise.resolve({sources}):Promise.resolve({cadence:'off'}));
    render(<Discovery/>);fireEvent.click(screen.getByRole('button',{name:'Search JobTech JobSearch'}));
    expect((await screen.findByRole('alert')).textContent).toBe('Source unavailable');
    await waitFor(()=>expect(screen.getByRole('button',{name:'Search JobTech JobSearch'}).hasAttribute('disabled')).toBe(false));
  });
});
