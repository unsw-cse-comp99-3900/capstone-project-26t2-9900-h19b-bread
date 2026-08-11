import { configureStore } from '@reduxjs/toolkit';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getAuthors } from '../services/submission';
import authReducer from '../store/authSlice';
import authorsReducer from '../store/authorsSlice';
import PublisherLayout from './PublisherLayout';


vi.mock('../services/submission', () => ({ getAuthors: vi.fn() }));

const getAuthorsMock = vi.mocked(getAuthors);

function renderLayout() {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: {
      auth: {
        token: 'jwt-token',
        user: { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' },
      },
    },
  });
  return {
    store,
    ...render(
      <Provider store={store}>
        <MemoryRouter initialEntries={['/homepage']}>
          <Routes>
            <Route path="/homepage" element={<PublisherLayout><div>Page content</div></PublisherLayout>} />
            <Route path="/schema-mapping" element={<div>Mapping destination</div>} />
            <Route path="/login" element={<div>Login destination</div>} />
          </Routes>
        </MemoryRouter>
      </Provider>,
    ),
  };
}

describe('publisher application shell', () => {
  beforeEach(() => getAuthorsMock.mockResolvedValue([{ user_id: 5, name: 'Current Publisher' }]));

  it('loads shared authors and navigates to schema mapping', async () => {
    const user = userEvent.setup();
    renderLayout();

    expect(screen.getByText('Page content')).toBeInTheDocument();
    await waitFor(() => expect(getAuthorsMock).toHaveBeenCalledOnce());
    await user.click(screen.getByText('Schema Mapping'));

    expect(await screen.findByText('Mapping destination')).toBeInTheDocument();
  });

  it('clears authentication and navigates to login', async () => {
    const user = userEvent.setup();
    const { store } = renderLayout();

    await user.click(screen.getByRole('button', { name: /Log out/ }));

    expect(await screen.findByText('Login destination')).toBeInTheDocument();
    expect(store.getState().auth).toEqual({ token: null, user: null });
  });
});
