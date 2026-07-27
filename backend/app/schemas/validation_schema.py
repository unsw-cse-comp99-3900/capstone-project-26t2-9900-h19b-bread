from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Protocol(str, Enum):
    REST = "REST"
    SOAP = "SOAP"


class ValidationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


class ValidationStage(str, Enum):
    SPECIFICATION_VALIDATION = "specification_validation"
    DOMAIN_COMPLIANCE_VALIDATION = "domain_compliance_validation"
    SECURITY_VALIDATION = "security_validation"


# Validation Request Schema (Peishuo -> Yiyang)
class ValidationRequest(BaseModel):
    protocol: Protocol
    spec_content: str = Field(..., min_length=1, description="OpenAPI/WSDL file raw content")
    auth_method: Optional[str] = Field(
        default=None,
        description="Authentication method declared in submission metadata",
    )
    # Business metadata declared in the submission form, used for FR-3/metadata
    # consistency validation against the actual specification content.
    endpoint_url: Optional[str] = Field(
        default=None,
        description="API endpoint URL declared in submission metadata",
    )
    input_format: Optional[str] = Field(
        default=None,
        description="Input data format declared in submission metadata (e.g. JSON, XML, UBL)",
    )
    output_format: Optional[str] = Field(
        default=None,
        description="Output data format declared in submission metadata (e.g. JSON, XML, UBL)",
    )
    capability_category: Optional[str] = Field(
        default=None,
        description="E-invoicing capability category (creation/validation/transmission/archiving)",
    )


# Validation Error Detail Schema
class ValidationErrorDetail(BaseModel):
    code: str
    message: str
    path: Optional[str] = None
    severity: str = "error"
    stage: Optional[ValidationStage] = None


# Validation Stage Result Schema
class StageResult(BaseModel):
    stage: ValidationStage
    status: ValidationStatus


# Validation Response Schema (Yiyang -> Peishuo)
class ValidationResponse(BaseModel):
    overall_status: ValidationStatus
    stages: List[StageResult]
    errors: List[ValidationErrorDetail]