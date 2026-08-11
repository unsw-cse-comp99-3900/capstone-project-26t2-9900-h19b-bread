import { configureStore } from '@reduxjs/toolkit';
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import authReducer from './store/authSlice';
import authorsReducer from './store/authorsSlice';


vi.mock('./pages/Init/Login', () => ({ default: () => <div>Login page</div> }));
vi.mock('./pages/Init/Register', () => ({ default: () => <div>Register page</div> }));
vi.mock('./pages/Homepage/HomePage', () => ({ default: () => <div>Dashboard page</div> }));
vi.mock('./pages/ApiDetail/ApiDetailPage', () => ({ default: () => <div>API detail page</div> }));
vi.mock('./pages/SchemaMapping/SchemaMappingPage', () => ({ default: () => <div>Mapping page</div> }));


function renderApp(token: string | null) {
  const store = configureStore({
    reducer: { auth: authReducer, authors: authorsReducer },
    preloadedState: {
      auth: {
        token,
        user: token
          ? { user_id: '5', enterprise_id: '7', email: 'publisher@example.test', role: 'PUBLISHER' }
          : null,
      },
    },
  });
  return render(<Provider store={store}><App /></Provider>);
}

describe('route protection', () => {
  beforeEach(() => window.history.replaceState({}, '', '/'));

  it('redirects an unauthenticated protected route to login', async () => {
    window.history.replaceState({}, '', '/homepage');
    renderApp(null);

    expect(await screen.findByText('Login page')).toBeInTheDocument();
  });

  it('allows an authenticated user to open the dashboard', async () => {
    window.history.replaceState({}, '', '/homepage');
    renderApp('jwt-token');

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument();
  });

  it('redirects an authenticated guest route to the dashboard', async () => {
    window.history.replaceState({}, '', '/login');
    renderApp('jwt-token');

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument();
  });
});
