import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, setAccessToken } from '../lib/api';

describe('profile-suggestion API requests', () => {
  afterEach(() => {
    setAccessToken(null);
    vi.unstubAllGlobals();
  });

  it('sends an authenticated POST to the profile-suggestion endpoint', async () => {
    const payload = { id: 'set-1', status: 'ready', suggestions: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('test-access-token');

    await expect(api('/profile-suggestions/resumes/resume-1', { method: 'POST' })).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/profile-suggestions\/resumes\/resume-1$/);
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer test-access-token');
  });

  it.each([
    [403, 'AI data-use consent is required. Review Privacy settings before continuing.'],
    [503, 'The AI provider is currently unavailable. Try again later.'],
  ])('preserves a %i response detail for the UI', async (status, detail) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(api('/profile-suggestions/resumes/resume-1', { method: 'POST' }))
      .rejects.toMatchObject({ message: detail, status });
  });

  it('retains field paths for invalid manual fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [
      { loc: ['body', 'manual_fields', 'salary_preference'], msg: 'minimum salary must not exceed maximum salary' },
    ] }), { status: 422, headers: { 'Content-Type': 'application/json' } })));
    await expect(api('/profile-suggestions/set-1/review', { method: 'POST' })).rejects.toMatchObject({
      status: 422, message: 'manual_fields.salary_preference: minimum salary must not exceed maximum salary',
    });
  });
});
