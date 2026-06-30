import { apiPost } from '../utils/request';
import type { User } from '../types/user';

export interface RegisterRequest {
  name:          string;
  email:         string;
  password:      string;
  /** Defaults to 1 on the backend if omitted. */
  enterprise_id?: number;
  /** Defaults to "PUBLISHER" on the backend if omitted. */
  role?:         string;
}

export interface RegisterResponse {
  status:  'success' | 'fail';
  token:   string | null;
  user:    User | null;
  message: string;
}

export function registerUser(data: RegisterRequest): Promise<RegisterResponse> {
  return apiPost<RegisterResponse>('/api/v1/auth/register', data);
}
