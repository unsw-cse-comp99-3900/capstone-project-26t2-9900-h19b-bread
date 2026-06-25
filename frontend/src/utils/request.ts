import axios from "axios";
import type { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { message } from "antd";

interface ApiError {
  error: string;
  message?: string;
  statusCode?: number;
}

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5005",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

request.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error: AxiosError<ApiError>) => {
    if (error.response) {
      const { data } = error.response;
      const errorMessage = data?.error ?? "An error occurred";
      message.error(errorMessage, 3);
      return Promise.reject(data);
    }

    if (error.request) {
      message.error("Network error. Please check your connection.", 3);
      return Promise.reject<ApiError>({ error: "Network error" });
    }

    message.error(error.message ?? "An unexpected error occurred", 3);
    return Promise.reject<ApiError>({ error: error.message ?? "Unknown error" });
  }
);

export default request;
