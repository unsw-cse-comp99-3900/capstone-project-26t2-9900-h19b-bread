import { configureStore } from '@reduxjs/toolkit';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import authReducer from '../../store/authSlice';
import authorsReducer from '../../store/authorsSlice';
import { login } from '../../services/login';
import Login from './Login';


vi.mock('../../services/login', () => ({ login: vi.fn() }));

const loginMock = vi.mocked(login);

function renderLogin() {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: { auth: { token: null, user: null } },
  });
  return {
    store,
    ...render(
      <Provider store={store}>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/homepage" element={<div>Dashboard destination</div>} />
          </Routes>
        </MemoryRouter>
      </Provider>,
    ),
  };
}

describe('login form', () => {
  beforeEach(() => {
    loginMock.mockReset();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('submits credentials, stores the session, and navigates', async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue({
      status: 'success',
      token: 'jwt-token',
      user: { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' },
      message: 'Login successful.',
    });
    const { store } = renderLogin();

    await user.type(screen.getByLabelText('Email'), 'publisher@example.test');
    await user.type(screen.getByLabelText('Password'), 'correct-password');
    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    await waitFor(() => expect(loginMock).toHaveBeenCalledWith({
      email: 'publisher@example.test',
      password: 'correct-password',
    }));
    expect(await screen.findByText('Dashboard destination')).toBeInTheDocument();
    expect(store.getState().auth.token).toBe('jwt-token');
    expect(localStorage.getItem('token')).toBe('jwt-token');
  });

  it('does not call the service when required fields are empty', async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    expect(await screen.findByText('Please input your email!')).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });
});
