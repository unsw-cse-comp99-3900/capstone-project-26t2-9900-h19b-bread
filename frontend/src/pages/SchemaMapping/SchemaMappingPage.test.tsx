import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { validateConnection } from '../../services/connectionValidation';
import { listApiSchemas } from '../../services/schemaMapping';
import SchemaMappingPage from './SchemaMappingPage';


vi.mock('../../components/PublisherLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('../../services/schemaMapping', () => ({
  listApiSchemas: vi.fn(),
  compareApiSchemas: vi.fn(),
  transformApiPreview: vi.fn(),
}));
vi.mock('../../services/connectionValidation', () => ({ validateConnection: vi.fn() }));

const listApiSchemasMock = vi.mocked(listApiSchemas);
const validateConnectionMock = vi.mocked(validateConnection);

const schema = (overrides: Record<string, unknown>) => ({
  schema_id: 10,
  api_id: 1,
  api_name: 'Invoice Source',
  version_id: 100,
  version_number: 'v1.0',
  direction: 'OUTPUT',
  format: 'JSON',
  source_key: 'post:/invoices',
  source_path: '/invoices',
  source_method: 'POST',
  media_type: 'application/json',
  status_code: '200',
  schema_version: 1,
  created_at: '2026-08-01T00:00:00Z',
  schema_definition: { type: 'object' },
  ...overrides,
});

function renderMapping() {
  return render(
    <MemoryRouter initialEntries={['/apis/1/mapping']}>
      <Routes><Route path="/apis/:id/mapping" element={<SchemaMappingPage />} /></Routes>
    </MemoryRouter>,
  );
}

describe('schema connection validation', () => {
  beforeEach(() => {
    listApiSchemasMock.mockResolvedValue([
      schema({}),
      schema({
        schema_id: 20,
        api_id: 2,
        api_name: 'Invoice Target',
        version_id: 200,
        direction: 'INPUT',
        source_key: 'post:/receive',
        source_path: '/receive',
      }),
    ]);
    validateConnectionMock.mockResolvedValue({
      connection_validation_run_id: 77,
      compatibility_result_id: 88,
      transform_run_id: null,
      mapping_id: null,
      lifecycle_status: null,
      is_latest_run: true,
      compatibility_level: 'DIRECTLY_COMPATIBLE',
      reason_code: 'DIRECT_MATCH',
      reason: 'Schemas are directly compatible.',
      activation_allowed: true,
      business_rules_diagnostics: {},
      source_api_id: 1,
      source_version_id: 100,
      target_api_id: 2,
      target_version_id: 200,
      source_schema_id: 10,
      target_schema_id: 20,
      stages: [{ stage: 'FORMAT_CHECK', status: 'PASSED', message: 'Formats match.', payload: {} }],
      reasons: [],
    });
  });

  it('loads persisted schemas and validates the default source-target pair', async () => {
    const user = userEvent.setup();
    renderMapping();

    expect(await screen.findByText('Schema Mapping')).toBeInTheDocument();
    await waitFor(() => expect(listApiSchemasMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'Validate connection' }));

    await waitFor(() => expect(validateConnectionMock).toHaveBeenCalledWith({
      source_api_id: 1,
      source_version_id: 100,
      target_api_id: 2,
      target_version_id: 200,
      source_schema_id: 10,
      target_schema_id: 20,
    }));
    expect(await screen.findByText('Schemas are directly compatible.')).toBeInTheDocument();
    expect(screen.getByText('Connection enabled')).toBeInTheDocument();
  });
});
