import axios from 'axios';
import type { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

interface ApiError {
  error?:      string;
  detail?:     string;
  message?:    string;
  statusCode?: number;
}

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

request.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error: AxiosError<ApiError>) => {
    if (error.response) {
      const { status, data } = error.response;

      if (status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        message.error('Session expired. Please sign in again.', 3);
        window.location.href = '/login';
        return Promise.reject(data);
      }

      const errorMessage = data?.detail ?? data?.error ?? data?.message ?? 'An error occurred';
      message.error(errorMessage, 3);
      return Promise.reject(data);
    }

    if (error.request) {
      message.error('Network error. Please check your connection.', 3);
      return Promise.reject<ApiError>({ error: 'Network error' });
    }

    message.error(error.message ?? 'An unexpected error occurred', 3);
    return Promise.reject<ApiError>({ error: error.message ?? 'Unknown error' });
  },
);

/** Typed GET helper — avoids `as unknown as` in every service file. */
export function apiGet<T>(url: string): Promise<T> {
  return request.get(url) as unknown as Promise<T>;
}

/** Typed POST helper — avoids `as unknown as` in every service file. */
export function apiPost<T>(url: string, data?: unknown): Promise<T> {
  return request.post(url, data) as unknown as Promise<T>;
}

/** Typed PUT helper — avoids `as unknown as` in every service file. */
export function apiPut<T>(url: string, data?: unknown): Promise<T> {
  return request.put(url, data) as unknown as Promise<T>;
}

export default request;
