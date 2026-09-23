import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfileView } from '../components/Profile';
import type { CandidateProfile } from '../lib/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock }));

const sampleProfile: CandidateProfile = {
  id: '9d7b17b0-9f0e-4bb8-9c1c-2d2e6a4f4f00',
  owner_id: '3f9c9e0e-0000-0000-0000-000000000001',
  headline: 'Senior Backend Engineer focused on reliable APIs',
  target_roles: ['Backend Engineer', 'Platform Engineer'],
  location: 'Beirut, Lebanon',
  remote_preference: 'hybrid',
  work_authorization: 'needs_sponsorship',
  skills: ['Python', 'FastAPI', 'PostgreSQL'],
  experience: [
    {
      title: 'Backend Engineer',
      organization: 'Example Systems',
      period: '2022 — present',
      notes: 'Built and maintained public APIs.',
    },
  ],
  education: [
    { school: 'State University', degree: 'B.Sc.', field: 'Computer Science', period: '2016 — 2020' },
  ],
  languages: [{ name: 'English', proficiency: 'professional' }],
  salary_preference: { currency: 'USD', min: 120000, max: 160000 },
  created_at: '2026-09-12T10:00:00Z',
  updated_at: '2026-09-12T10:00:00Z',
};

const notFound = Object.assign(new Error('Profile not found'), { status: 404 });

describe('ProfileView', () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it('shows a loading state while the profile is being fetched', () => {
    apiMock.mockReturnValue(new Promise(() => undefined));
    render(<ProfileView />);
    expect(screen.getByText('Loading profile…')).not.toBeNull();
  });

  it('shows an error state with retry for unexpected failures', async () => {
    apiMock.mockRejectedValueOnce(new Error('Server unavailable'));
    render(<ProfileView />);
    expect(await screen.findByText('Profile unavailable')).not.toBeNull();
    expect(screen.getByText('Server unavailable')).not.toBeNull();

    apiMock.mockResolvedValueOnce(sampleProfile);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your profile' })).not.toBeNull();
  });

  it('shows an empty state when no profile exists yet and opens the editor', async () => {
    apiMock.mockRejectedValueOnce(notFound);
    render(<ProfileView />);
    expect(await screen.findByText('Your profile is not set up yet')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Set up profile/ }));
    expect(screen.getByRole('heading', { name: 'Set up your profile' })).not.toBeNull();
    expect(screen.getByLabelText('Headline')).not.toBeNull();
  });

  it('renders a saved profile in the read view', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    expect(
      await screen.findByRole('heading', { name: 'Senior Backend Engineer focused on reliable APIs' })
    ).not.toBeNull();
    expect(screen.getByText('Python')).not.toBeNull();
    expect(screen.getByText('FastAPI')).not.toBeNull();
    expect(screen.getByText('Example Systems')).not.toBeNull();
    expect(screen.getByText('English')).not.toBeNull();
    expect(screen.getByRole('button', { name: /Edit profile/ })).not.toBeNull();
  });

  it('reconciles an applied suggestion profile snapshot without a manual refresh', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('heading', { name: 'Senior Backend Engineer focused on reliable APIs' });
    const updated = {
      ...sampleProfile,
      headline: 'Remote',
      target_roles: ['Full Stack Developer'],
      skills: ['Python'],
      experience: [{ title: 'Engineer', organization: 'Cedar Labs', period: '2020-2024', notes: null }],
      education: [{ school: 'State University', degree: 'BSc', field: 'Computer Science', period: '2020' }],
      remote_preference: 'remote' as const,
    };
    window.dispatchEvent(new CustomEvent('jobpilot:profile-updated', { detail: updated }));
    expect(await screen.findByRole('heading', { name: 'Remote' })).not.toBeNull();
    expect(screen.getByText('Full Stack Developer')).not.toBeNull();
    expect(screen.getByText('Python')).not.toBeNull();
    expect(screen.getByText('Cedar Labs')).not.toBeNull();
  });

  it('persists edited values through the PATCH endpoint and shows the success state', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });

    apiMock.mockResolvedValueOnce({ ...sampleProfile, headline: 'Staff Engineer' });
    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Staff Engineer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const [path, init] = apiMock.mock.calls[1];
    expect(path).toBe('/profile');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string).headline).toBe('Staff Engineer');
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Profile saved');
    expect(screen.getByRole('heading', { name: 'Staff Engineer' })).not.toBeNull();
  });

  it('serializes target roles, experience, and work authorization with their exact profile keys', async () => {
    const base = { ...sampleProfile, target_roles: [], experience: [], work_authorization: null };
    apiMock.mockResolvedValueOnce(base);
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });
    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText('Target roles'), { target: { value: 'Product Engineer, Platform Engineer' } });
    fireEvent.change(screen.getByLabelText('Work authorization'), { target: { value: 'citizen' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add experience' }));
    const titles = screen.getAllByLabelText('Title');
    const organizations = screen.getAllByLabelText('Organization');
    fireEvent.change(titles.at(-1)!, { target: { value: 'Product Engineer' } });
    fireEvent.change(organizations.at(-1)!, { target: { value: 'Cedar Labs' } });
    const saved = { ...base, target_roles: ['Product Engineer', 'Platform Engineer'], work_authorization: 'citizen' as const, experience: [{ title: 'Product Engineer', organization: 'Cedar Labs', period: null, notes: null }] };
    apiMock.mockResolvedValueOnce(saved);
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse((apiMock.mock.calls[1][1] as RequestInit).body as string);
    expect(body.target_roles).toEqual(['Product Engineer', 'Platform Engineer']);
    expect(body.experience).toEqual([{ title: 'Product Engineer', organization: 'Cedar Labs', period: null, notes: null }]);
    expect(body.work_authorization).toBe('citizen');
    expect(body.headline).toBe(base.headline);
    expect(body.location).toBe(base.location);
  });

  it('renders headline and location separately and uses the save response immediately', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('heading', { name: 'Senior Backend Engineer focused on reliable APIs' });
    expect(screen.getByText('Beirut, Lebanon')).not.toBeNull();
    apiMock.mockResolvedValueOnce({ ...sampleProfile, headline: 'Remote', location: 'Tripoli, Lebanon' });
    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Remote' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Tripoli, Lebanon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByRole('heading', { name: 'Remote' })).not.toBeNull();
    expect(screen.getByText('Tripoli, Lebanon')).not.toBeNull();
  });

  it('does not optimistically replace profile values when the save fails', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });
    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Unsaved headline' } });
    apiMock.mockRejectedValueOnce(new Error('Validation failed'));
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Validation failed');
    expect(screen.getByRole('heading', { name: 'Edit profile' })).not.toBeNull();
  });

  it('rejects a salary range where the minimum exceeds the maximum', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });

    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText(/Minimum \(yearly, optional\)/), { target: { value: '200000' } });
    fireEvent.change(screen.getByLabelText(/Maximum \(yearly, optional\)/), { target: { value: '100000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('The minimum salary must not be higher than the maximum.');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  });

  it('validates that experience entries have a title and organization', async () => {
    apiMock.mockResolvedValueOnce({ ...sampleProfile, experience: [] });
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });

    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add experience' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Every experience entry needs a title and an organization.');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  });

  it('clears fields with a null value when saved', async () => {
    apiMock.mockResolvedValueOnce(sampleProfile);
    render(<ProfileView />);
    await screen.findByRole('button', { name: /Edit profile/ });

    apiMock.mockResolvedValueOnce({ ...sampleProfile, headline: null });
    fireEvent.click(screen.getByRole('button', { name: /Edit profile/ }));
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse((apiMock.mock.calls[1][1] as RequestInit).body as string);
    expect(body.headline).toBeNull();
  });
});
