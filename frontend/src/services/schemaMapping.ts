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
