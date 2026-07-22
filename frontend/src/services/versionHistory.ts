import { apiGet, apiPost, apiPut } from '../utils/request';
import request from '../utils/request';

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
  versionId?: number | string | null,
): Promise<EventPage> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (versionId != null && versionId !== '') {
    params.set('version_id', String(versionId));
  }
  return apiGet<EventPage>(`/api/apis/${apiId}/history?${params.toString()}`);
}

export type ProtocolType = 'REST' | 'SOAP' | 'WEB' | 'CLI';
export type CategoryType = 'TRANSFORMATION' | 'VALIDATION' | 'COMMUNICATION';
export type AuthMethodType =
  | 'OAUTH2'
  | 'API_KEY'
  | 'BASIC'
  | 'TOKEN'
  | 'BEARER'
  | 'MTLS'
  | 'NONE'
  | 'OTHER';
export type SpecificationType = 'OPENAPI' | 'SWAGGER' | 'WSDL';

export interface VersionWriteRequest {
  version_number:        string;
  change_note?:          string | null;
  api_name:              string;
  endpoint_url:          string;
  protocol_type?:        ProtocolType;
  category?:             CategoryType | null;
  capability_category?:  string | null;
  description?:          string | null;
  input_format?:         string | null;
  output_format?:        string | null;
  auth_method:           AuthMethodType;
  auth_description?:     string | null;
  security_scheme_name?: string | null;
  auth_is_complete?:     boolean;
  spec_type:             SpecificationType;
  specification:         string;
}

export function createVersion(
  apiId: number | string,
  data: VersionWriteRequest,
): Promise<VersionDetail> {
  return apiPost<VersionDetail>(`/api/apis/${apiId}/versions`, data);
}

export function updateVersion(
  apiId: number | string,
  versionId: number | string,
  data: VersionWriteRequest,
): Promise<VersionDetail> {
  return apiPut<VersionDetail>(`/api/apis/${apiId}/versions/${versionId}`, data);
}

/** Raw specification body (OpenAPI JSON / WSDL XML). */
export async function getVersionSpecification(
  apiId: number | string,
  versionId: number | string,
): Promise<string> {
  const data = await request.get(
    `/api/apis/${apiId}/versions/${versionId}/specification`,
    {
      responseType: 'text',
      transformResponse: [(body: string) => body],
    },
  ) as unknown as string;
  return typeof data === 'string' ? data : String(data ?? '');
}

const AUTH_TO_BACKEND: Record<string, AuthMethodType> = {
  'OAuth 2.0':            'OAUTH2',
  'Bearer / JWT':         'BEARER',
  'API Key':              'API_KEY',
  'Basic Authentication': 'BASIC',
  mTLS:                   'MTLS',
  OAUTH2:                 'OAUTH2',
  API_KEY:                'API_KEY',
  BASIC:                  'BASIC',
  TOKEN:                  'TOKEN',
  BEARER:                 'BEARER',
  MTLS:                   'MTLS',
  NONE:                   'NONE',
  OTHER:                  'OTHER',
};

const AUTH_FROM_BACKEND: Record<string, string> = {
  OAUTH2: 'OAuth 2.0',
  API_KEY: 'API Key',
  BASIC:  'Basic Authentication',
  TOKEN:  'Bearer / JWT',
  BEARER: 'Bearer / JWT',
  MTLS:   'mTLS',
  NONE:   'API Key',
  OTHER:  'API Key',
};

const CATEGORY_TO_BACKEND: Record<string, CategoryType> = {
  'Invoice Creation': 'COMMUNICATION',
  Validation:         'VALIDATION',
  Transmission:       'TRANSFORMATION',
  Archiving:          'COMMUNICATION',
  TRANSFORMATION:        'TRANSFORMATION',
  VALIDATION:         'VALIDATION',
  COMMUNICATION:      'COMMUNICATION',
};

const CATEGORY_FROM_BACKEND: Record<string, string> = {
  TRANSFORMATION:   'Transmission',
  VALIDATION:    'Validation',
  COMMUNICATION: 'Invoice Creation',
};

export function toBackendAuth(method: string): AuthMethodType {
  return AUTH_TO_BACKEND[method] ?? 'OTHER';
}

export function fromBackendAuth(method: string | null | undefined): string {
  if (!method) return 'API Key';
  return AUTH_FROM_BACKEND[method] ?? AUTH_FROM_BACKEND[method.toUpperCase()] ?? method;
}

export function toBackendCategory(category: string): CategoryType {
  return CATEGORY_TO_BACKEND[category] ?? 'COMMUNICATION';
}

export function fromBackendCategory(
  capability: string | null | undefined,
  category: string | null | undefined,
): string {
  if (capability && (capability in CATEGORY_TO_BACKEND || ['Invoice Creation', 'Validation', 'Transmission', 'Archiving'].includes(capability))) {
    return capability;
  }
  if (category && CATEGORY_FROM_BACKEND[category]) {
    return CATEGORY_FROM_BACKEND[category];
  }
  return capability || category || 'Invoice Creation';
}

export function detectSpecType(protocol: string, specification: string): SpecificationType {
  const trimmed = specification.trim();
  if (protocol.toUpperCase() === 'SOAP' || /<definitions[\s>]|wsdl:/i.test(trimmed)) {
    return 'WSDL';
  }
  try {
    const obj = JSON.parse(trimmed) as { swagger?: string; openapi?: string };
    if (obj.swagger) return 'SWAGGER';
  } catch {
    // not JSON
  }
  return 'OPENAPI';
}

/** Bump patch segment: v1.0 -> v1.1, 2.3 -> 2.4 */
export function bumpVersionNumber(current: string): string {
  const match = current.trim().match(/^(v?)(\d+)(?:\.(\d+))?$/i);
  if (!match) return `${current}-updated`;
  const prefix = match[1] ?? '';
  const major = Number(match[2]);
  const minor = match[3] != null ? Number(match[3]) + 1 : 1;
  return `${prefix}${major}.${minor}`;
}
