import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import APIInfoForm from './APIInfoForm';


describe('API publication wizard import step', () => {
  it('blocks continuation when no specification file is selected', async () => {
    const user = userEvent.setup();
    render(<APIInfoForm open onClose={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Parse & Continue' }));

    expect(await screen.findByText('Please upload a specification file to continue.')).toBeInTheDocument();
  });

  it('validates URL input and allows switching to SOAP', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'fetch').mockRejectedValue(new TypeError('Invalid URL'));
    render(<APIInfoForm open onClose={vi.fn()} />);

    const soap = screen.getByRole('radio', { name: 'SOAP' });
    await user.click(screen.getByText('SOAP'));
    expect(soap).toBeChecked();
    await user.click(screen.getByText('Enter URL'));
    await user.type(screen.getByPlaceholderText('https://api.example.com/openapi.json'), 'not-a-url');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    expect(await screen.findByText(/Could not fetch the URL in the browser/)).toBeInTheDocument();
  });

  it('resets and closes without submitting', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<APIInfoForm open onClose={onClose} />);

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
