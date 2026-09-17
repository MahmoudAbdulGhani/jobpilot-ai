import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Discovery, type DiscoveredJob } from '../components/Discovery';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));
vi.mock('../components/Shell', () => ({ Shell: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }));
const job: DiscoveredJob = { source: 'jobtech', external_id: '123', title: 'Backend Engineer', company: 'Demo AB', location: null, salary: null, workplace_model: null, published_at: null, deadline: null, description: '<script>unsafe()</script>', source_url: 'https://arbetsformedlingen.se/platsbanken/annonser/123', existing_job_id: null, test_data: false };
const results = { items: [job], total: 1, offset: 0, next_offset: null };

describe('reviewed discovery', () => {
  beforeEach(() => apiMock.mockReset());
  it('discloses Swedish coverage and approximate remote matching without worldwide eligibility', () => {
    render(<Discovery />);
    expect(screen.getByText(/Primarily Swedish coverage/)).not.toBeNull();
    expect(screen.getByLabelText('Approximate remote matches (source phrase matching)')).not.toBeNull();
    expect(screen.getByText(/does not mean worldwide eligibility/)).not.toBeNull();
    expect(screen.getByText(/residency and work-authorization requirements/)).not.toBeNull();
    expect(apiMock).not.toHaveBeenCalled();
  });
  it('requires search, preview and explicit import and escapes source text', async () => {
    apiMock.mockResolvedValueOnce(results).mockResolvedValueOnce({job, preview_token:'signed',expires_at:'2026-09-17T12:00:00Z'}).mockResolvedValueOnce({job:{id:'saved-1'},already_saved:false});
    const {container} = render(<Discovery />);
    expect(apiMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Keywords'), {target:{value:'Python'}});
    fireEvent.click(screen.getByRole('button',{name:'Search JobTech'}));
    fireEvent.click(await screen.findByRole('button',{name:'Preview job'}));
    expect(await screen.findByText('<script>unsafe()</script>')).not.toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(apiMock).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText(/Not supplied/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button',{name:'Import this job into saved jobs'}));
    expect((await screen.findByRole('link',{name:'Open saved job'})).getAttribute('href')).toBe('/jobs/saved-1');
    expect(apiMock).toHaveBeenLastCalledWith('/discovery/import', {method:'POST',body:JSON.stringify({preview_token:'signed',confirm:true})});
  });
  it('links duplicates instead of overwriting them', async () => {
    apiMock.mockResolvedValueOnce({...results,items:[{...job,existing_job_id:'existing'}]});
    render(<Discovery />);fireEvent.click(screen.getByRole('button',{name:'Search JobTech'}));
    expect((await screen.findByRole('link',{name:/Already saved/})).getAttribute('href')).toBe('/jobs/existing');
    expect(screen.queryByRole('button',{name:'Preview job'})).toBeNull();
  });
  it('shows loading and an empty result', async () => {
    let done!: (value: unknown) => void;
    apiMock.mockReturnValue(new Promise(resolve => {done=resolve;}));
    render(<Discovery />);fireEvent.click(screen.getByRole('button',{name:'Search JobTech'}));
    expect(screen.getByRole('status').textContent).toContain('Searching');
    expect(screen.getByRole('button',{name:'Search JobTech'}).hasAttribute('disabled')).toBe(true);
    done({...results,items:[],total:0});
    expect(await screen.findByText('No matching jobs')).not.toBeNull();
  });
  it.each(['Rate limit reached. Wait before searching again.','JobTech is unavailable. Please try later.','The preview is invalid or expired. Preview the listing again.'])('shows safe failures: %s', async message => {
    apiMock.mockRejectedValueOnce(new Error(message));
    render(<Discovery />);fireEvent.click(screen.getByRole('button',{name:'Search JobTech'}));
    expect((await screen.findByRole('alert')).textContent).toBe(message);
    await waitFor(() => expect(screen.getByRole('button',{name:'Search JobTech'}).hasAttribute('disabled')).toBe(false));
  });
});
