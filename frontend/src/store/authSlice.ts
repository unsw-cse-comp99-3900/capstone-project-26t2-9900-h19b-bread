import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

export interface AuthUser {
  user_id:       string;
  enterprise_id: string;
  email:         string;
  role:          string;
}

interface AuthState {
  token: string | null;
  user:  AuthUser | null;
}

function loadFromStorage(): AuthState {
  return {
    token: localStorage.getItem('token'),
    user:  JSON.parse(localStorage.getItem('user') ?? 'null'),
  };
}

const authSlice = createSlice({
  name: 'auth',
  initialState: loadFromStorage(),
  reducers: {
    setCredentials(state, action: PayloadAction<{ token: string; user: AuthUser }>) {
      state.token = action.payload.token;
      state.user  = action.payload.user;
      localStorage.setItem('token', action.payload.token);
      localStorage.setItem('user',  JSON.stringify(action.payload.user));
    },
    logout(state) {
      state.token = null;
      state.user  = null;
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    },
  },
});

export const { setCredentials, logout } = authSlice.actions;
export default authSlice.reducer;
