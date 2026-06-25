from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Protocol(str, Enum):
    REST = "REST"
    SOAP = "SOAP"


class ValidationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ValidationStage(str, Enum):
    SPECIFICATION_VALIDATION = "specification_validation"


# Validation Request Schema (Peishuo -> Yiyang)
class ValidationRequest(BaseModel):
  protocol: Protocol
  spec_content: str = Field(..., min_length=1, description="OpenAPI/WSDL file raw content")


# Validation Error Detail Schema
class ValidationErrorDetail(BaseModel):
  code: str
  message: str
  path: Optional[str] = None
  severity: str = "error"


# Validation Stage Result Schema
class StageResult(BaseModel):
  stage: ValidationStage
  status: ValidationStatus


# Validation Response Schema (Yiyang -> Peishuo)
class ValidationResponse(BaseModel):
  overall_status: ValidationStatus
  stages: List[StageResult]
  errors: List[ValidationErrorDetail]