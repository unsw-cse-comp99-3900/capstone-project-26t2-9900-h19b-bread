import request from '../utils/request';

// ── Request / Response types ───────────────────────────────────────────────

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginUser {
  user_id:       string;
  email:         string;
  role:          string;
  enterprise_id: string;
}

export interface LoginResponse {
  status:  'success' | 'fail';
  token:   string | null;
  user:    LoginUser | null;
  message: string;
}

// ── API call ───────────────────────────────────────────────────────────────

export function login(data: LoginRequest): Promise<LoginResponse> {
  return request.post('/api/v1/auth/login', data) as unknown as Promise<LoginResponse>;
}
