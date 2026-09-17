// Isolate the feature widget; entitlement enforcement has dedicated connected tests.
vi.mock('../components/MeteredButton',()=>({MeteredButton:'button'}));
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ResumesView } from '../components/Resumes';
import type { Resume, ResumeExtraction } from '../lib/types';

const { apiMock, downloadMock } = vi.hoisted(() => ({ apiMock: vi.fn(), downloadMock: vi.fn() }));
vi.mock('../lib/api', () => ({ api: apiMock, downloadResume: downloadMock }));

const pdfResume: Resume = {
  id: '9d7b17b0-9f0e-4bb8-9c1c-2d2e6a4f4f00',
  owner_id: '3f9c9e0e-0000-0000-0000-000000000001',
  original_filename: 'cv_2026_final.pdf',
  display_name: 'CV 2026',
  file_extension: 'pdf',
  size_bytes: 245760,
  is_primary: true,
  created_at: '2026-09-13T09:00:00Z',
  updated_at: '2026-09-13T09:00:00Z',
};

const docxResume: Resume = {
  id: '7d7b17b0-9f0e-4bb8-9c1c-2d2e6a4f4f11',
  owner_id: '3f9c9e0e-0000-0000-0000-000000000001',
  original_filename: 'draft.docx',
  display_name: 'Draft CV',
  file_extension: 'docx',
  size_bytes: 1536,
  is_primary: false,
  created_at: '2026-09-10T12:00:00Z',
  updated_at: '2026-09-10T12:00:00Z',
};

const notFound = Object.assign(new Error('Request failed (401)'), { status: 401 });

const extraction: ResumeExtraction = {
  id: '6d7b17b0-9f0e-4bb8-9c1c-2d2e6a4f4f22',
  resume_id: pdfResume.id,
  status: 'succeeded',
  original_text: 'Ada Lovelace\nEngineer',
  draft_text: 'Ada Lovelace\nEngineer',
  parser_name: 'pypdf',
  parser_version: '6.18.1',
  failure_code: null,
  failure_message: null,
  reviewed_at: null,
  created_at: '2026-09-13T09:00:00Z',
  updated_at: '2026-09-13T09:00:00Z',
};

describe('ResumesView', () => {
  beforeEach(() => {
    apiMock.mockReset();
    downloadMock.mockReset();
  });

  it('shows a loading state while resumes are being fetched', () => {
    apiMock.mockReturnValue(new Promise(() => undefined));
    render(<ResumesView />);
    expect(screen.getByText('Loading resumes…')).not.toBeNull();
  });

  it('shows an error state with retry for unexpected failures', async () => {
    apiMock.mockRejectedValueOnce(new Error('Server unavailable'));
    render(<ResumesView />);
    expect(await screen.findByText('Resumes unavailable')).not.toBeNull();
    expect(screen.getByText('Server unavailable')).not.toBeNull();

    apiMock.mockResolvedValueOnce({ items: [pdfResume] });
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('CV 2026')).not.toBeNull();
  });

  it('listens for unauthenticated sessions by surfacing the api error', async () => {
    apiMock.mockRejectedValueOnce(notFound);
    render(<ResumesView />);
    expect(await screen.findByText('Resumes unavailable')).not.toBeNull();
    expect(screen.getByText('Request failed (401)')).not.toBeNull();
  });

  it('shows an empty state when there are no resumes yet', async () => {
    apiMock.mockResolvedValueOnce({ items: [] });
    render(<ResumesView />);
    expect(await screen.findByText('No resumes yet')).not.toBeNull();
    expect(screen.getByRole('button', { name: /Upload your first resume/ })).not.toBeNull();
  });

  it('renders each resume with metadata and only one primary badge', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume, docxResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');

    expect(screen.getByText('Draft CV')).not.toBeNull();
    expect(screen.getByText(/cv_2026_final\.pdf/)).not.toBeNull();
    expect(screen.getByText(/draft\.docx/)).not.toBeNull();
    expect(screen.getByText('Primary')).not.toBeNull();
    expect(screen.getAllByText('Primary')).toHaveLength(1);

    const primaryButtons = screen.getAllByRole('button', { name: /Make primary/ });
    expect(primaryButtons).toHaveLength(1);
  });

  it('uploads a selected file through the multipart endpoint and refreshes the list', async () => {
    apiMock.mockResolvedValueOnce({ items: [] });
    render(<ResumesView />);
    await screen.findByText('No resumes yet');

    const file = new File([new Uint8Array([37, 80, 68, 70])], 'new.pdf', { type: 'application/pdf' });
    apiMock.mockResolvedValueOnce({ ...pdfResume, id: 'new-id', display_name: 'new.pdf' });
    apiMock.mockResolvedValueOnce({ items: [{ ...pdfResume, id: 'new-id', display_name: 'new.pdf' }] });

    const input = screen.getByTestId('resume-file-input');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    const [path, init] = apiMock.mock.calls[1];
    expect(path).toBe('/resumes');
    expect(init.method).toBe('POST');
    const body = (init.body as FormData).get('file');
    expect(body).toBe(file);
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Resume uploaded.');
    expect(screen.getByText('new.pdf')).not.toBeNull();
  });

  it('surfaces upload failures from the server inline', async () => {
    apiMock.mockResolvedValueOnce({ items: [] });
    render(<ResumesView />);
    await screen.findByText('No resumes yet');

    const file = new File([new Uint8Array(0)], 'notes.txt', { type: 'text/plain' });
    apiMock.mockRejectedValueOnce(Object.assign(new Error('Unsupported file type. Upload a PDF or DOCX resume.'), { status: 415 }));
    fireEvent.change(screen.getByTestId('resume-file-input'), { target: { files: [file] } });

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Unsupported file type. Upload a PDF or DOCX resume.');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
  });

  it('promotes a resume to primary via PATCH and moves the badge', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume, docxResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');

    apiMock.mockResolvedValueOnce({ ...docxResume, is_primary: true });
    fireEvent.click(screen.getByRole('button', { name: /Make primary/ }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const [path, init] = apiMock.mock.calls[1];
    expect(path).toBe(`/resumes/${docxResume.id}`);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ is_primary: true });
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Primary resume updated.');
    expect(screen.getAllByText('Primary')).toHaveLength(1);
  });

  it('renames a resume through the dialog', async () => {
    apiMock.mockResolvedValueOnce({ items: [docxResume] });
    render(<ResumesView />);
    await screen.findByText('Draft CV');

    apiMock.mockResolvedValueOnce({ ...docxResume, display_name: 'Lead Designer CV' });
    fireEvent.click(screen.getByRole('button', { name: /Rename/ }));
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Lead Designer CV' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save name' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const [path, init] = apiMock.mock.calls[1];
    expect(path).toBe(`/resumes/${docxResume.id}`);
    expect(JSON.parse(init.body as string).display_name).toBe('Lead Designer CV');
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Resume renamed.');
    expect(screen.getByText('Lead Designer CV')).not.toBeNull();
  });

  it('deletes a resume through the confirmation dialog', async () => {
    apiMock.mockResolvedValueOnce({ items: [docxResume] });
    render(<ResumesView />);
    await screen.findByText('Draft CV');

    apiMock.mockResolvedValueOnce(undefined);
    fireEvent.click(screen.getByRole('button', { name: /Delete/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete resume' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const [path, init] = apiMock.mock.calls[1];
    expect(path).toBe(`/resumes/${docxResume.id}`);
    expect(init.method).toBe('DELETE');
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Resume deleted.');
    expect(screen.queryByText('Draft CV')).toBeNull();
    expect(screen.getByText('No resumes yet')).not.toBeNull();
  });

  it('downloads the stored file through the private endpoint', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');

    downloadMock.mockResolvedValueOnce(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
    fireEvent.click(screen.getByRole('button', { name: /Download/ }));

    await waitFor(() => expect(downloadMock).toHaveBeenCalledTimes(1));
    expect(downloadMock).toHaveBeenCalledWith(`/resumes/${pdfResume.id}/download`);
  });

  it('extracts, edits, saves, and explicitly confirms resume text', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');

    apiMock.mockResolvedValueOnce(extraction);
    fireEvent.click(screen.getByRole('button', { name: /Extract text/ }));
    const textarea = await screen.findByLabelText('Extracted resume text');
    expect(screen.getByText('Needs review')).not.toBeNull();

    fireEvent.change(textarea, { target: { value: 'Ada Lovelace\nSenior Engineer' } });
    expect(screen.getByText('Unsaved changes')).not.toBeNull();
    apiMock.mockResolvedValueOnce({
      ...extraction,
      draft_text: 'Ada Lovelace\nSenior Engineer',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    expect(apiMock.mock.calls[2][0]).toBe(`/resumes/${pdfResume.id}/extraction`);

    apiMock.mockResolvedValueOnce({
      ...extraction,
      draft_text: 'Ada Lovelace\nSenior Engineer',
      reviewed_at: '2026-09-13T10:00:00Z',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm text' }));
    await waitFor(() => expect(screen.getAllByText('Confirmed')).toHaveLength(2));
    expect(apiMock.mock.calls[3][0]).toBe(`/resumes/${pdfResume.id}/extraction/confirm`);
  });

  it('shows extraction failures and offers retry', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');
    apiMock.mockResolvedValueOnce({
      ...extraction,
      status: 'failed',
      original_text: null,
      draft_text: null,
      failure_code: 'ocr_required',
      failure_message: 'No extractable text was found. This PDF may be scanned and needs OCR.',
    });
    fireEvent.click(screen.getByRole('button', { name: /Extract text/ }));
    expect(await screen.findByText(/needs OCR/)).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Retry extraction' })).not.toBeNull();
  });

  it('shows the AI disclosure and applies an edited selected suggestion', async () => {
    apiMock.mockResolvedValueOnce({ items: [pdfResume] });
    render(<ResumesView />);
    await screen.findByText('CV 2026');
    apiMock.mockResolvedValueOnce({ ...extraction, reviewed_at: '2026-09-14T10:00:00Z' });
    apiMock.mockRejectedValueOnce(Object.assign(new Error('missing'), { status: 404 }));
    fireEvent.click(screen.getByRole('button', { name: /Extract text/ }));
    expect(await screen.findByText(/confirmed CV text will leave JobPilot/)).not.toBeNull();
    apiMock.mockResolvedValueOnce({
      id: 'set-1', resume_id: pdfResume.id, status: 'ready', provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: null, applied_at: null,
      suggestions: [{ id: 'headline-1', field: 'headline', value: 'Ada Lovelace', evidence: [{ quote: 'Ada Lovelace' }] }],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Suggest profile details with AI' }));
    const proposed = await screen.findByLabelText('Proposed headline');
    fireEvent.change(proposed, { target: { value: 'Computing pioneer' } });
    apiMock.mockResolvedValueOnce({
      id: 'set-1', resume_id: pdfResume.id, status: 'applied', provider: 'deterministic-test', model: 'synthetic-v1', outcome_message: null, applied_at: '2026-09-14T11:00:00Z', suggestions: [],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply selected changes' }));
    expect(await screen.findByText(/Selected profile changes applied/)).not.toBeNull();
  });
});
