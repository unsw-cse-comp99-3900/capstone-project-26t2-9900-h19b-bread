import { apiGet, apiPost } from '../utils/request';

export interface WithdrawRequest {
  /** Must be a numeric string matching the user_id integer on the backend. */
  actor_id: number;
  reason?:  string;
}

export interface WithdrawResponse {
  status:     string;
  api_id?:    number;
  action?:    string;
  message?:   string;
  updated_at?: string;
}

export interface ApiStatusResponse {
  api_id:      number;
  status:      string;
  updated_at?: string;
}

export function withdrawApi(apiId: number | string, data: WithdrawRequest): Promise<WithdrawResponse> {
  return apiPost<WithdrawResponse>(`/api/apis/${apiId}/withdraw`, data);
}

export function getApiStatus(apiId: number | string): Promise<ApiStatusResponse> {
  return apiGet<ApiStatusResponse>(`/api/apis/${apiId}/status`);
}

export interface SubmitApiRequest {
  protocol?:     string;
  spec_content?: string;
}

export interface SubmitApiResponse {
  api_id:             number;
  status:             string;
  message:            string;
  updated_at?:        string;
  action?:            string;
  version_id?:        number;
  validation_run_id?: number;
}

export function submitApi(
  apiId: number | string,
  data: SubmitApiRequest = {},
): Promise<SubmitApiResponse> {
  return apiPost<SubmitApiResponse>(`/api/apis/${apiId}/submit`, data);
}
