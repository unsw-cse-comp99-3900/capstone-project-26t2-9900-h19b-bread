import request from '../utils/request';

export interface SchemaCompareResponse {
  source:             string;
  target:             string;
  compatibility:      string;
  summary:            Record<string, unknown>;
  issues:             Array<Record<string, unknown>>;
  normalized_source:  Record<string, unknown>;
  normalized_target:  Record<string, unknown>;
  [key: string]:      unknown;
}

export interface TransformPreviewResponse {
  result:          unknown;
  format:          'json' | 'xml';
  mapping_status:  string;
  mapping:         Record<string, unknown>;
  comparison:      Record<string, unknown>;
  transform_code:  string;
}

export interface MatrixResponse {
  matrix: Array<Array<Record<string, unknown>>>;
}

export interface SchemaInferenceResponse {
  schema: Record<string, unknown>;
}

export interface ApiSchemaSummary {
  schema_id:          number;
  api_id:             number;
  api_name:           string;
  version_id:         number;
  version_number:     string;
  direction:          string;
  format:             string;
  source_key:         string;
  source_path:        string | null;
  source_method:      string | null;
  media_type:         string | null;
  status_code:        string | null;
  schema_version:     number;
  created_at:         string;
  schema_definition:  Record<string, unknown>;
}

export interface ApiSchemaCompareResponse {
  source_schema:          ApiSchemaSummary;
  target_schema:          ApiSchemaSummary;
  comparison_result_id:   number | null;
  mapping_id:             number | null;
  comparison:             SchemaCompareResponse;
  mapping:                Record<string, unknown>;
}

export interface ApiSchemaTransformPreviewResponse extends TransformPreviewResponse {
  transform_run_id:       number | null;
  comparison_result_id:   number | null;
  mapping_id:             number;
}

/** Schema mapping calls can be slower than CRUD. */
function postMapping<T>(url: string, data: unknown): Promise<T> {
  return request.post(url, data, { timeout: 60000 }) as unknown as Promise<T>;
}

export function compareSchemas(payload: {
  source_schema: Record<string, unknown>;
  target_schema: Record<string, unknown>;
  source_name?:  string;
  target_name?:  string;
}): Promise<SchemaCompareResponse> {
  return postMapping('/api/v1/schema-mapping/compare', payload);
}

export function listApiSchemas(): Promise<ApiSchemaSummary[]> {
  return request.get('/api/v1/schema-mapping/api-schemas') as unknown as Promise<ApiSchemaSummary[]>;
}

export function compareApiSchemas(payload: {
  source_schema_id: number;
  target_schema_id: number;
  save_mapping?:    boolean;
}): Promise<ApiSchemaCompareResponse> {
  return postMapping('/api/v1/schema-mapping/compare-api-schemas', {
    save_mapping: true,
    ...payload,
  });
}

export function transformApiPreview(payload: {
  mapping_id: number;
  data:       Record<string, unknown>;
  format?:    'json' | 'xml';
  save_run?:  boolean;
}): Promise<ApiSchemaTransformPreviewResponse> {
  return postMapping('/api/v1/schema-mapping/transform-api-preview', {
    format: 'json',
    save_run: true,
    ...payload,
  });
}

export function buildMatrix(
  schemas: Array<{ name: string; schema: Record<string, unknown> }>,
): Promise<MatrixResponse> {
  return postMapping('/api/v1/schema-mapping/matrix', { schemas });
}

export function transformPreview(payload: {
  source_schema: Record<string, unknown>;
  target_schema: Record<string, unknown>;
  data:          Record<string, unknown>;
  format?:       'json' | 'xml';
  source_name?:  string;
  target_name?:  string;
}): Promise<TransformPreviewResponse> {
  return postMapping('/api/v1/schema-mapping/transform-preview', {
    format: 'json',
    ...payload,
  });
}

export function inferJsonSchema(data: unknown): Promise<SchemaInferenceResponse> {
  return postMapping('/api/v1/schema-mapping/infer-json-schema', { data });
}

export function inferXmlSchema(xml_content: string): Promise<SchemaInferenceResponse> {
  return postMapping('/api/v1/schema-mapping/infer-xml-schema', { xml_content });
}
