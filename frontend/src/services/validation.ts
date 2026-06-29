import request from '../utils/request';

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
  protocol:     'REST' | 'SOAP';
  spec_content: string;
}

export function validateSpec(data: ValidationRequest): Promise<ValidationApiResponse> {
  return request.post('/api/v1/validation/spec', data) as unknown as Promise<ValidationApiResponse>;
}
