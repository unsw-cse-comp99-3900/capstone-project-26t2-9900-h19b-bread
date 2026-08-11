import type { ReactNode } from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { render, screen, waitFor } from '@testing-library/react';
import { Provider } from 'react-redux';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getApiStatus } from '../../services/lifecycle';
import { getSubmissions } from '../../services/submission';
import { getApiHistory, getVersionDetail, getVersions } from '../../services/versionHistory';
import authReducer from '../../store/authSlice';
import authorsReducer from '../../store/authorsSlice';
import ApiDetailPage from './ApiDetailPage';


vi.mock('../../components/PublisherLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('../../components/APIInfoForm', () => ({ default: () => null }));
vi.mock('../../services/submission', () => ({ getSubmissions: vi.fn() }));
vi.mock('../../services/lifecycle', () => ({ getApiStatus: vi.fn(), withdrawApi: vi.fn() }));
vi.mock('../../services/versionHistory', async importOriginal => {
  const actual = await importOriginal<typeof import('../../services/versionHistory')>();
  return {
    ...actual,
    getVersions: vi.fn(),
    getVersionDetail: vi.fn(),
    getApiHistory: vi.fn(),
  };
});

const getVersionsMock = vi.mocked(getVersions);
const getVersionDetailMock = vi.mocked(getVersionDetail);
const getApiHistoryMock = vi.mocked(getApiHistory);
const getSubmissionsMock = vi.mocked(getSubmissions);
const getApiStatusMock = vi.mocked(getApiStatus);

function renderDetail() {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: {
      auth: {
        token: 'jwt-token',
        user: { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' },
      },
      authors: {
        items: [{ user_id: 5, name: 'Current Publisher' }],
        status: 'succeeded' as const,
        error: null,
        fetchedAt: Date.now(),
      },
    },
  });
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={['/apis/7']}>
        <Routes><Route path="/apis/:id" element={<ApiDetailPage />} /></Routes>
      </MemoryRouter>
    </Provider>,
  );
}

describe('API detail workflow', () => {
  beforeEach(() => {
    const summary = {
      version_id: 70,
      version_number: 'v1.0',
      change_note: null,
      status: 'PUBLISHED',
      is_current: true,
      previous_version_id: null,
      created_by: 5,
      api_name: 'Invoice API',
      created_at: '2026-08-01T00:00:00Z',
      published_at: '2026-08-02T00:00:00Z',
      archived_at: null,
    };
    getVersionsMock.mockResolvedValue({ items: [summary], page: 1, page_size: 50, total: 1 });
    getVersionDetailMock.mockResolvedValue({
      ...summary,
      endpoint_url: 'https://api.example.test/invoices',
      protocol_type: 'REST',
      category: 'VALIDATION',
      capability_category: 'Validation',
      description: 'Validates enterprise invoices.',
      input_format: 'JSON',
      output_format: 'JSON',
      auth: {
        auth_method: 'OAUTH2',
        auth_description: 'Client credentials',
        security_scheme_name: 'oauth2',
        is_complete: true,
      },
      specification: null,
      validation_runs: [],
    });
    getApiHistoryMock.mockResolvedValue({
      items: [{
        event_id: 1,
        version_id: 70,
        api_id: 7,
        actor_user_id: 5,
        event_type: 'PUBLISHED',
        from_status: 'DRAFT',
        to_status: 'PUBLISHED',
        message: 'Published v1.0',
        created_at: '2026-08-02T00:00:00Z',
      }],
      page: 1,
      page_size: 50,
      total: 1,
    });
    getSubmissionsMock.mockResolvedValue([{
      api_id: 7,
      api_name: 'Invoice API',
      endpoint_url: 'https://api.example.test/invoices',
      protocol_type: 'REST',
      input_format: 'JSON',
      output_format: 'JSON',
      capability_category: 'Validation',
      status: 'PUBLISHED',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-02T00:00:00Z',
      submitted_by: 5,
      submitted_by_name: 'Current Publisher',
      is_current_user_api: true,
      can_manage: true,
    }]);
    getApiStatusMock.mockResolvedValue({ api_id: 7, status: 'PUBLISHED' });
  });

  it('loads the current version, status, and history for an authorized user', async () => {
    renderDetail();

    expect((await screen.findAllByText('Invoice API')).length).toBeGreaterThan(0);
    expect(screen.getByText('Validates enterprise invoices.')).toBeInTheDocument();
    expect(screen.getByText('Published v1.0')).toBeInTheDocument();
    await waitFor(() => expect(getVersionDetailMock).toHaveBeenCalledWith('7', 70));
    expect(getApiStatusMock).toHaveBeenCalledWith('7');
  });
});
