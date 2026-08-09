export interface ValidationErrorDetail {
  code: string;
  message: string;
  path?: string;
  severity: string;
  stage?: string;
}

export interface ValidationStageResult {
  stage: string;
  status: "pass" | "fail";
}

export interface ValidationApiResponse {
  overall_status: "pass" | "fail";
  stages: ValidationStageResult[];
  errors: ValidationErrorDetail[];
}
