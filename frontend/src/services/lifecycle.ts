import request from '../utils/request';

export interface WithdrawRequest {
  actor_id: string;
  reason?:  string;
}

export interface WithdrawResponse {
  status:   string;
  message?: string;
}

export interface ApiStatusResponse {
  api_id:           number;
  status:           string;
  current_version?: string;
}

export function withdrawApi(apiId: number | string, data: WithdrawRequest): Promise<WithdrawResponse> {
  return request.post(`/api/apis/${apiId}/withdraw`, data) as unknown as Promise<WithdrawResponse>;
}

export function getApiStatus(apiId: number | string): Promise<ApiStatusResponse> {
  return request.get(`/api/apis/${apiId}/status`) as unknown as Promise<ApiStatusResponse>;
}
