import { apiPost } from '../utils/request';
import type { Protocol } from '../utils/helper';

export interface ValidationErrorDetail {
  code:      string;
  message:   string;
  path?:     string;
  severity:  string;
}

export interface ValidationStageResult {
  stage:  string;
  status: 'pass' | 'fail';
}

export interface ValidationApiResponse {
  overall_status: 'pass' | 'fail';
  stages:         ValidationStageResult[];
  errors:         ValidationErrorDetail[];
}

export interface ValidationRequest {
  protocol:     Protocol;
  spec_content: string;
}

export function validateSpec(data: ValidationRequest): Promise<ValidationApiResponse> {
  return apiPost<ValidationApiResponse>('/api/v1/validation/spec', data);
}
