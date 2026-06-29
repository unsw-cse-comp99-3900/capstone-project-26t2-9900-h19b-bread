import { apiPost } from '../utils/request';
import type { User } from '../types/user';

export interface LoginRequest {
  email:    string;
  password: string;
}

export interface LoginResponse {
  status:  'success' | 'fail';
  token:   string | null;
  user:    User | null;
  message: string;
}

export function login(data: LoginRequest): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/api/v1/auth/login', data);
}
