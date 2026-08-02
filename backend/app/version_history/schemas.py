from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProtocolType = Literal["REST", "SOAP", "WEB", "CLI"]
CategoryType = Literal["TRANSFORMATION", "VALIDATION", "COMMUNICATION"]
AuthMethodType = Literal[
    "OAUTH2", "API_KEY", "BASIC", "TOKEN", "BEARER", "MTLS", "NONE", "OTHER"
]
SpecificationType = Literal["OPENAPI", "SWAGGER", "WSDL"]
MappingLifecycleStatus = Literal[
    "DRAFT", "VALIDATING", "ACTIVE", "FAILED", "STALE", "DEPRECATED"
]
VersionEventType = Literal[
    "CREATED",
    "UPDATED",
    "SUBMITTED_FOR_VALIDATION",
    "VALIDATION_PASSED",
    "VALIDATION_FAILED",
    "PUBLISHED",
    "REJECTED",
    "ARCHIVED",
    "RESTORED_AS_DRAFT",
]


class VersionWriteRequest(BaseModel):
    version_number: str = Field(min_length=1, max_length=50)
    change_note: str | None = None
    api_name: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1, max_length=1000)
    protocol_type: ProtocolType = "REST"
    category: CategoryType | None = None
    capability_category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    input_format: str | None = Field(default=None, max_length=100)
    output_format: str | None = Field(default=None, max_length=100)
    auth_method: AuthMethodType
    auth_description: str | None = None
    security_scheme_name: str | None = Field(default=None, max_length=255)
    auth_is_complete: bool = False
    spec_type: SpecificationType
    specification: str


class VersionSummary(BaseModel):
    version_id: int
    version_number: str
    change_note: str | None
    status: str
    is_current: bool
    previous_version_id: int | None
    created_by: int
    api_name: str
    created_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class VersionPage(BaseModel):
    items: list[VersionSummary]
    page: int
    page_size: int
    total: int


class AuthMetadata(BaseModel):
    auth_method: str
    auth_description: str | None
    security_scheme_name: str | None
    is_complete: bool


class SpecificationMetadata(BaseModel):
    specification_id: int
    spec_type: str
    source_type: str
    file_path: str | None
    spec_url: str | None
    checksum: str | None
    uploaded_at: datetime


class ValidationStageResult(BaseModel):
    stage: str
    status: str
    message: str | None
    error_detail: str | None


class ValidationRun(BaseModel):
    validation_run_id: int
    overall_status: str
    started_at: datetime
    completed_at: datetime | None
    results: list[ValidationStageResult]


class VersionDetail(VersionSummary):
    endpoint_url: str
    protocol_type: str
    category: str | None
    capability_category: str | None
    description: str | None
    input_format: str | None
    output_format: str | None
    auth: AuthMetadata | None
    specification: SpecificationMetadata | None
    validation_runs: list[ValidationRun]


class VersionEvent(BaseModel):
    event_id: int
    version_id: int
    api_id: int
    actor_user_id: int | None
    event_type: str
    from_status: str | None
    to_status: str | None
    message: str | None
    created_at: datetime


class EventPage(BaseModel):
    items: list[VersionEvent]
    page: int
    page_size: int
    total: int


class ConnectionImpact(BaseModel):
    mapping_id: int
    role: Literal["SOURCE", "TARGET"]
    api_version_id: int
    counterpart_api_id: int
    counterpart_version_id: int
    lifecycle_status: str
    completeness: str
    latest_validation_run_id: int | None
    latest_validation_run_status: str | None
    updated_at: datetime


class ConnectionImpactPage(BaseModel):
    items: list[ConnectionImpact]
    page: int
    page_size: int
    total: int
