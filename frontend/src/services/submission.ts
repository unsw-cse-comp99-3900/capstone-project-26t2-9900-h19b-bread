import { apiGet, apiPost } from '../utils/request';
import request from '../utils/request';
import type { Protocol } from '../utils/helper';
import type { ValidationApiResponse } from './validation';

export interface SubmissionRequest {
  api_name:            string;
  endpoint_url:        string;
  protocol:            Protocol;
  input_format:        string;
  output_format:       string;
  auth_method:         string;
  description?:        string;
  capability_category: string;
  spec_content:        string;
}

export interface UrlImportRequest {
  api_name:            string;
  endpoint_url:        string;
  protocol:            Protocol;
  input_format:        string;
  output_format:       string;
  auth_method:         string;
  description?:        string;
  capability_category: string;
  spec_url:            string;
}

export interface SubmissionApiResponse {
  submission_id: string;
  status:        string;
  validation:    ValidationApiResponse;
}

export interface DraftSubmissionResponse {
  submission_id: string;
  status:        string;
}

export interface SubmissionListItem {
  api_id:               number;
  api_name:             string;
  endpoint_url:         string;
  protocol_type:        string;
  input_format:         string;
  output_format:        string;
  capability_category:  string;
  status:               string;
  created_at:           string;
  updated_at:           string;
  submitted_by:         number;
  submitted_by_name:    string | null;
  is_current_user_api:  boolean;
  can_manage:           boolean;
}

export interface AuthorListItem {
  user_id: number;
  name:    string;
}

export function createSubmission(data: SubmissionRequest): Promise<SubmissionApiResponse> {
  return apiPost<SubmissionApiResponse>('/api/v1/submissions', data);
}

export function getSubmissions(): Promise<SubmissionListItem[]> {
  return apiGet<SubmissionListItem[]>('/api/v1/submissions');
}

export function getAuthors(): Promise<AuthorListItem[]> {
  return apiGet<AuthorListItem[]>('/api/v1/submissions/authors');
}

export function saveDraft(data: SubmissionRequest): Promise<DraftSubmissionResponse> {
  return apiPost<DraftSubmissionResponse>('/api/v1/submissions/draft', data);
}

export function importFromUrl(data: UrlImportRequest): Promise<SubmissionApiResponse> {
  return apiPost<SubmissionApiResponse>('/api/v1/submissions/import-url', data);
}

/** Multipart file upload submission (backend Form endpoint). */
export function uploadSubmission(formData: FormData): Promise<SubmissionApiResponse> {
  return request.post(
    '/api/v1/submissions/upload',
    formData,
  ) as unknown as Promise<SubmissionApiResponse>;
}
