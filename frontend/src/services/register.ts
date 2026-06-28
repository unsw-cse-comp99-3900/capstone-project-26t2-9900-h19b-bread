import request from '../utils/request';
import type { LoginUser } from './login';

// ── Request / Response types ───────────────────────────────────────────────

export interface RegisterRequest {
  name:          string;
  email:         string;
  password:      string;
  enterprise_id?: number;
  role?:         string;
}

export interface RegisterResponse {
  status:  'success' | 'fail';
  user:    LoginUser | null;
  message: string;
}

// ── API call ───────────────────────────────────────────────────────────────

export function registerUser(data: RegisterRequest): Promise<RegisterResponse> {
  return request.post('/api/v1/auth/register', data) as unknown as Promise<RegisterResponse>;
}
