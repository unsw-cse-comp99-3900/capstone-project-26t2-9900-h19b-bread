import { apiPost } from "../utils/request";

export type ConnectionValidationStageStatus =
  | "RUNNING"
  | "PASSED"
  | "FAILED"
  | "NOT_RUN"
  | "MISSING_INFORMATION";

export interface ConnectionValidationStage {
  stage: string;
  status: ConnectionValidationStageStatus;
  message: string;
  payload: Record<string, unknown>;
}

export interface ConnectionValidationReason {
  reason_code: string;
  stage: string;
  severity: "INFO" | "WARNING" | "ERROR";
  message: string;
  source_path: string | null;
  target_path: string | null;
  details: Record<string, unknown>;
}

export interface ConnectionValidationResult {
  connection_validation_run_id: number;
  compatibility_result_id: number | null;
  transform_run_id: number | null;
  mapping_id: number | null;
  lifecycle_status: string | null;
  is_latest_run: boolean;
  compatibility_level:
    | "DIRECTLY_COMPATIBLE"
    | "COMPATIBLE_WITH_MAPPING"
    | "INCOMPATIBLE"
    | "NOT_ASSESSABLE";
  reason_code: string;
  reason: string;
  activation_allowed: boolean;
  business_rules_diagnostics: Record<string, unknown>;
  source_api_id: number;
  source_version_id: number;
  target_api_id: number;
  target_version_id: number;
  source_schema_id: number | null;
  target_schema_id: number | null;
  stages: ConnectionValidationStage[];
  reasons: ConnectionValidationReason[];
}

export function validateConnection(payload: {
  source_api_id: number;
  source_version_id: number;
  target_api_id: number;
  target_version_id: number;
  source_schema_id?: number | null;
  target_schema_id?: number | null;
  sample_data?: Record<string, unknown>;
  trigger_type?: "MANUAL" | "VERSION_CHANGED" | "MAPPING_UPDATED" | "RETRY";
}): Promise<ConnectionValidationResult> {
  return apiPost<ConnectionValidationResult>("/api/v1/connection-validation/runs", {
    trigger_type: "MANUAL",
    ...payload,
  });
}
