import { beforeEach, describe, expect, it, vi } from 'vitest';

import { validateConnection } from './connectionValidation';
import { getApiStatus, submitApi, withdrawApi } from './lifecycle';
import { login } from './login';
import { registerUser } from './register';
import { compareApiSchemas, listApiSchemas, transformApiPreview } from './schemaMapping';
import { createSubmission, getAuthors, getSubmissions, importFromUrl, saveDraft } from './submission';
import { apiGet, apiPost } from '../utils/request';
import request from '../utils/request';


vi.mock('../utils/request', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);
const requestPostMock = vi.mocked(request.post);
const requestGetMock = vi.mocked(request.get);

describe('typed API client routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGetMock.mockResolvedValue({});
    apiPostMock.mockResolvedValue({});
    requestGetMock.mockResolvedValue({});
    requestPostMock.mockResolvedValue({});
  });

  it('uses the authentication endpoints', () => {
    const credentials = { email: 'publisher@example.test', password: 'a-long-password' };
    login(credentials);
    registerUser({ name: 'Publisher', ...credentials });

    expect(apiPostMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/login', credentials);
    expect(apiPostMock).toHaveBeenNthCalledWith(2, '/api/v1/auth/register', { name: 'Publisher', ...credentials });
  });

  it('uses submission and lifecycle endpoints', () => {
    const submission = {
      api_name: 'Invoice API', endpoint_url: 'https://example.test', protocol: 'REST' as const,
      input_format: 'JSON', output_format: 'JSON', auth_method: 'OAUTH2',
      capability_category: 'validation', spec_content: '{}',
    };
    createSubmission(submission);
    saveDraft(submission);
    importFromUrl({ ...submission, spec_url: 'https://example.test/openapi.json' });
    getSubmissions();
    getAuthors();
    withdrawApi(7, { actor_id: 5 });
    getApiStatus(7);
    submitApi(7);

    expect(apiPostMock).toHaveBeenCalledWith('/api/v1/submissions', submission);
    expect(apiPostMock).toHaveBeenCalledWith('/api/v1/submissions/draft', submission);
    expect(apiGetMock).toHaveBeenCalledWith('/api/v1/submissions');
    expect(apiGetMock).toHaveBeenCalledWith('/api/v1/submissions/authors');
    expect(apiPostMock).toHaveBeenCalledWith('/api/apis/7/withdraw', { actor_id: 5 });
    expect(apiGetMock).toHaveBeenCalledWith('/api/apis/7/status');
    expect(apiPostMock).toHaveBeenCalledWith('/api/apis/7/submit', {});
  });

  it('uses schema mapping and connection validation endpoints with safe defaults', () => {
    listApiSchemas();
    compareApiSchemas({ source_schema_id: 10, target_schema_id: 20 });
    transformApiPreview({ mapping_id: 30, data: { id: 'INV-1' } });
    validateConnection({
      source_api_id: 1,
      source_version_id: 100,
      target_api_id: 2,
      target_version_id: 200,
    });

    expect(requestGetMock).toHaveBeenCalledWith('/api/v1/schema-mapping/api-schemas');
    expect(requestPostMock).toHaveBeenCalledWith(
      '/api/v1/schema-mapping/compare-api-schemas',
      { save_mapping: true, source_schema_id: 10, target_schema_id: 20 },
      { timeout: 60000 },
    );
    expect(requestPostMock).toHaveBeenCalledWith(
      '/api/v1/schema-mapping/transform-api-preview',
      { format: 'json', save_run: true, mapping_id: 30, data: { id: 'INV-1' } },
      { timeout: 60000 },
    );
    expect(apiPostMock).toHaveBeenCalledWith('/api/v1/connection-validation/runs', {
      trigger_type: 'MANUAL',
      source_api_id: 1,
      source_version_id: 100,
      target_api_id: 2,
      target_version_id: 200,
    });
  });
});
