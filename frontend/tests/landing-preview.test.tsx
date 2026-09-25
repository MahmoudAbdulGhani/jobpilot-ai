import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductPreview } from '../components/landing/ProductPreview';
import { ReviewControl } from '../components/landing/ReviewControl';

afterEach(() => vi.unstubAllGlobals());

function chooseTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

describe('illustrative landing product preview', () => {
  it('updates sample roles locally and previews the selected role in every application panel', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<ProductPreview />);

    expect(screen.getByRole('heading', { name: 'Senior Product Designer' })).toBeTruthy();
    chooseTab('Engineering');
    expect(screen.queryByRole('heading', { name: 'Senior Product Designer' })).toBeNull();
    expect(screen.getByRole('heading', { name: 'Senior Frontend Engineer' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Engineering' }).getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Preview application for Senior Frontend Engineer at Fieldwork' }));

    const dialog = screen.getByRole('dialog', { name: 'A starting point. Make it yours.' });
    expect(within(dialog).getByText('Frontend engineer')).toBeTruthy();
    chooseTab('Cover letter');
    expect(within(dialog).getByText('Dear Fieldwork team,')).toBeTruthy();
    chooseTab('Email preview');
    expect(within(dialog).getByText('Application · Senior Frontend Engineer')).toBeTruthy();
    expect(within(dialog).getByText('Sample content only. Nothing is saved or sent.')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close dialog' }));
    expect(screen.queryByRole('dialog')).toBeNull();

    chooseTab('Marketing');
    expect(screen.getByRole('heading', { name: 'Content Marketing Lead' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Senior Frontend Engineer' })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('updates review values, requires a selected nonempty change, and only approves on confirmation', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<ReviewControl />);

    const headline = screen.getByRole('textbox', { name: 'Suggested headline' });
    const suggestion = screen.getByRole('checkbox', { name: 'Include this headline update' });
    const approve = screen.getByRole('button', { name: 'Approve sample change' });
    expect(screen.queryByText('Approved in this demo.')).toBeNull();

    fireEvent.change(headline, { target: { value: 'Designer focused on accessible experiences' } });
    expect(screen.getByText('Designer focused on accessible experiences')).toBeTruthy();
    fireEvent.click(suggestion);
    expect(approve.hasAttribute('disabled')).toBe(true);
    expect(screen.getByText('No changes')).toBeTruthy();
    fireEvent.click(approve);
    expect(screen.queryByText('Approved in this demo.')).toBeNull();

    fireEvent.click(suggestion);
    fireEvent.change(headline, { target: { value: '   ' } });
    expect(approve.hasAttribute('disabled')).toBe(true);
    fireEvent.change(headline, { target: { value: 'Designer focused on accessible experiences' } });
    expect(approve.hasAttribute('disabled')).toBe(false);
    fireEvent.click(approve);
    expect(screen.getByText('Approved in this demo.')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole('status'));
    expect(headline.hasAttribute('disabled')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Edit again' }));
    expect(headline.hasAttribute('disabled')).toBe(false);
    expect(screen.queryByText('Approved in this demo.')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('cancels a proposal without approving and can reset the local demo', () => {
    render(<ReviewControl />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Suggested headline' }), { target: { value: 'An edited proposal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('status').textContent).toBe('Changes canceled. Nothing was applied.');
    expect(screen.getByRole('checkbox').getAttribute('aria-checked')).toBe('false');
    expect(screen.getByRole('button', { name: 'Approve sample change' }).hasAttribute('disabled')).toBe(true);
    expect(screen.queryByText('Approved in this demo.')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Reset demo' }));
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Product designer creating thoughtful digital experiences');
    expect(screen.getByRole('checkbox').getAttribute('aria-checked')).toBe('true');
    expect(screen.queryByText('Changes canceled. Nothing was applied.')).toBeNull();
  });
});
