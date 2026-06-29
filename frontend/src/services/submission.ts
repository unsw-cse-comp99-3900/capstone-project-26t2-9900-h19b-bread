import request from '../utils/request';
import type { ValidationApiResponse } from './validation';

export interface SubmissionRequest {
  api_name:            string;
  endpoint_url:        string;
  protocol:            string;
  input_format:        string;
  output_format:       string;
  auth_method:         string;
  description?:        string;
  capability_category: string;
  spec_content:        string;
}

export interface SubmissionApiResponse {
  submission_id: string;
  status:        string;
  validation:    ValidationApiResponse;
}

export function createSubmission(data: SubmissionRequest): Promise<SubmissionApiResponse> {
  return request.post('/api/v1/submissions', data) as unknown as Promise<SubmissionApiResponse>;
}
