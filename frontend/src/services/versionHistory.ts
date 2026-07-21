import { apiGet, apiPost } from '../utils/request';

export interface VersionSummary {
  version_id:          number;
  version_number:      string;
  change_note:         string | null;
  status:              string;
  is_current:          boolean;
  previous_version_id: number | null;
  created_by:          number;
  api_name:            string;
  created_at:          string;
  published_at:        string | null;
  archived_at:         string | null;
}

export interface VersionPage {
  items:     VersionSummary[];
  page:      number;
  page_size: number;
  total:     number;
}

export interface AuthMetadata {
  auth_method:           string;
  auth_description:      string | null;
  security_scheme_name:  string | null;
  is_complete:           boolean;
}

export interface VersionDetail extends VersionSummary {
  endpoint_url:         string;
  protocol_type:        string;
  category:             string | null;
  capability_category:  string | null;
  description:          string | null;
  input_format:         string | null;
  output_format:        string | null;
  auth:                 AuthMetadata | null;
  specification:        {
    specification_id: number;
    spec_type:        string;
    source_type:      string;
    file_path:        string | null;
    spec_url:         string | null;
    checksum:         string | null;
    uploaded_at:      string;
  } | null;
  validation_runs: Array<{
    validation_run_id: number;
    overall_status:    string;
    started_at:        string;
    completed_at:      string | null;
    results: Array<{
      stage:         string;
      status:        string;
      message:       string | null;
      error_detail:  string | null;
    }>;
  }>;
}

export interface VersionEvent {
  event_id:       number;
  version_id:     number;
  api_id:         number;
  actor_user_id:  number | null;
  event_type:     string;
  from_status:    string | null;
  to_status:      string | null;
  message:        string | null;
  created_at:     string;
}

export interface EventPage {
  items:     VersionEvent[];
  page:      number;
  page_size: number;
  total:     number;
}

export function getVersions(
  apiId: number | string,
  page = 1,
  pageSize = 50,
): Promise<VersionPage> {
  return apiGet<VersionPage>(
    `/api/apis/${apiId}/versions?page=${page}&page_size=${pageSize}`,
  );
}

export function getVersionDetail(
  apiId: number | string,
  versionId: number | string,
): Promise<VersionDetail> {
  return apiGet<VersionDetail>(`/api/apis/${apiId}/versions/${versionId}`);
}

export function getApiHistory(
  apiId: number | string,
  page = 1,
  pageSize = 50,
): Promise<EventPage> {
  return apiGet<EventPage>(
    `/api/apis/${apiId}/history?page=${page}&page_size=${pageSize}`,
  );
}
