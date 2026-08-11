import { configureStore } from '@reduxjs/toolkit';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { registerUser } from '../../services/register';
import authReducer from '../../store/authSlice';
import authorsReducer from '../../store/authorsSlice';
import Register from './Register';


vi.mock('../../services/register', () => ({ registerUser: vi.fn() }));

const registerMock = vi.mocked(registerUser);

function renderRegister() {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: { auth: { token: null, user: null } },
  });
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/homepage" element={<div>Dashboard destination</div>} />
        </Routes>
      </MemoryRouter>
    </Provider>,
  );
}

describe('registration form', () => {
  beforeEach(() => registerMock.mockReset());

  it('enforces the twelve-character password rule', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText('Name'), 'Publisher');
    await user.type(screen.getByLabelText('Email'), 'publisher@example.test');
    await user.type(screen.getByLabelText('Password'), 'short');
    await user.type(screen.getByLabelText('Confirm Password'), 'short');
    await user.click(screen.getByRole('button', { name: 'Sign Up' }));

    expect(await screen.findByText('Password must be at least 12 characters!')).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('submits no client-controlled enterprise or role fields', async () => {
    const user = userEvent.setup();
    registerMock.mockResolvedValue({
      status: 'success',
      token: 'jwt-token',
      user: { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' },
      message: 'User registered successfully.',
    });
    renderRegister();

    await user.type(screen.getByLabelText('Name'), 'Publisher');
    await user.type(screen.getByLabelText('Email'), 'publisher@example.test');
    await user.type(screen.getByLabelText('Password'), 'a-long-password');
    await user.type(screen.getByLabelText('Confirm Password'), 'a-long-password');
    await user.click(screen.getByRole('button', { name: 'Sign Up' }));

    await waitFor(() => expect(registerMock).toHaveBeenCalledWith({
      name: 'Publisher',
      email: 'publisher@example.test',
      password: 'a-long-password',
    }));
    expect(await screen.findByText('Dashboard destination')).toBeInTheDocument();
  });
});
