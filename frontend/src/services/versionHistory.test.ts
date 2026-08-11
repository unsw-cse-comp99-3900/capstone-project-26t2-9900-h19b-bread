import { describe, expect, it } from 'vitest';

import {
  bumpVersionNumber,
  detectSpecType,
  fromBackendAuth,
  fromBackendCategory,
  nextVersionNumber,
  toBackendAuth,
  toBackendCategory,
  type VersionSummary,
} from './versionHistory';


const version = (version_number: string): VersionSummary => ({
  version_id: 1,
  version_number,
  change_note: null,
  status: 'PUBLISHED',
  is_current: true,
  previous_version_id: null,
  created_by: 5,
  api_name: 'Invoice API',
  created_at: '2026-08-01T00:00:00Z',
  published_at: null,
  archived_at: null,
});

describe('version form conversions', () => {
  it('normalizes authentication and category values', () => {
    expect(toBackendAuth('OAuth 2.0')).toBe('OAUTH2');
    expect(toBackendAuth('unknown')).toBe('OTHER');
    expect(fromBackendAuth('API_KEY')).toBe('API Key');
    expect(fromBackendAuth(null)).toBe('API Key');
    expect(toBackendCategory('Validation')).toBe('VALIDATION');
    expect(fromBackendCategory(null, 'COMMUNICATION')).toBe('Invoice Creation');
  });

  it('detects OpenAPI, Swagger, and WSDL specifications', () => {
    expect(detectSpecType('REST', '{"openapi":"3.0.3"}')).toBe('OPENAPI');
    expect(detectSpecType('REST', 'swagger: "2.0"')).toBe('SWAGGER');
    expect(detectSpecType('SOAP', '<definitions/>')).toBe('WSDL');
  });

  it('increments version numbers safely', () => {
    expect(bumpVersionNumber('v1.9')).toBe('v1.10');
    expect(bumpVersionNumber('release')).toBe('release-updated');
    expect(nextVersionNumber([version('v1.2'), version('v2.4')])).toBe('v2.5');
    expect(nextVersionNumber([version('release')])).toBe('v1.0');
  });
});
