import type { ReactNode } from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getSubmissions } from '../../services/submission';
import authReducer from '../../store/authSlice';
import authorsReducer from '../../store/authorsSlice';
import HomePage from './HomePage';


vi.mock('../../components/PublisherLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('../../components/APIInfoForm', () => ({ default: () => null }));
vi.mock('../../services/submission', () => ({
  getSubmissions: vi.fn(),
  getAuthors: vi.fn(),
}));
vi.mock('../../services/lifecycle', () => ({ withdrawApi: vi.fn() }));

const getSubmissionsMock = vi.mocked(getSubmissions);

const submissions = [
  {
    api_id: 1,
    api_name: 'Invoice Alpha',
    endpoint_url: 'https://alpha.example.test',
    protocol_type: 'REST',
    input_format: 'JSON',
    output_format: 'JSON',
    capability_category: 'validation',
    status: 'PUBLISHED',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
    submitted_by: 5,
    submitted_by_name: 'Current Publisher',
    is_current_user_api: true,
    can_manage: true,
  },
  {
    api_id: 2,
    api_name: 'Archive Beta',
    endpoint_url: 'https://beta.example.test',
    protocol_type: 'SOAP',
    input_format: 'XML',
    output_format: 'XML',
    capability_category: 'archiving',
    status: 'DRAFT',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
    submitted_by: 6,
    submitted_by_name: 'Other Publisher',
    is_current_user_api: false,
    can_manage: false,
  },
];

function renderHome() {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: {
      auth: {
        token: 'jwt-token',
        user: { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' },
      },
      authors: {
        items: [{ user_id: 5, name: 'Current Publisher' }, { user_id: 6, name: 'Other Publisher' }],
        status: 'succeeded' as const,
        error: null,
        fetchedAt: Date.now(),
      },
    },
  });
  return render(<Provider store={store}><MemoryRouter><HomePage /></MemoryRouter></Provider>);
}

describe('dashboard list behaviour', () => {
  beforeEach(() => getSubmissionsMock.mockResolvedValue(submissions));

  it('renders backend submissions and filters them by search text', async () => {
    const user = userEvent.setup();
    renderHome();

    expect(await screen.findByText('Invoice Alpha')).toBeInTheDocument();
    expect(screen.getByText('Archive Beta')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/Search by name/), 'Alpha');

    expect(screen.getByText('Invoice Alpha')).toBeInTheDocument();
    expect(screen.queryByText('Archive Beta')).not.toBeInTheDocument();
  });

  it('shows only the current user records on the My APIs tab', async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByText('Archive Beta');

    await user.click(screen.getByRole('tab', { name: 'My APIs' }));

    expect(screen.getByText('Invoice Alpha')).toBeInTheDocument();
    expect(screen.queryByText('Archive Beta')).not.toBeInTheDocument();
  });
});
