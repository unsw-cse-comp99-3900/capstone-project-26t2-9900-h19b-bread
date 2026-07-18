from datetime import datetime

from pydantic import BaseModel, Field

from app.version_history.models import VersionWrite


class VersionWriteRequest(BaseModel):
    version_number: str = Field(min_length=1, max_length=50)
    change_note: str | None = None
    api_name: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1, max_length=1000)
    protocol_type: str
    input_format: str = Field(min_length=1, max_length=100)
    output_format: str = Field(min_length=1, max_length=100)
    capability_category: str = Field(min_length=1, max_length=100)
    description: str | None = None
    auth_method: str
    auth_description: str | None = None
    security_scheme_name: str | None = Field(default=None, max_length=255)
    spec_content: str = Field(min_length=1)

    def to_write(self) -> VersionWrite:
        return VersionWrite(**self.model_dump())


class VersionMutationResponse(BaseModel):
    api_id: int
    version_id: int
    status: str


class VersionListItem(BaseModel):
    version_id: int
    version_number: str
    status: str
    change_note: str | None
    snapshot_origin: str
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    is_current: bool
    is_last_published: bool


class VersionListResponse(BaseModel):
    api_id: int
    total: int
    limit: int
    offset: int
    items: list[VersionListItem]


class VersionAuthResponse(BaseModel):
    auth_method: str
    auth_description: str | None
    security_scheme_name: str | None
    is_complete: bool


class SpecificationMetadataResponse(BaseModel):
    specification_id: int | None
    spec_type: str | None
    source_type: str | None
    file_path: str | None
    spec_url: str | None
    checksum: str | None
    uploaded_at: datetime | None


class ValidationResultResponse(BaseModel):
    result_id: int
    stage: str
    status: str
    message: str | None
    error_detail: str | None
    created_at: datetime


class ValidationRunResponse(BaseModel):
    validation_run_id: int
    overall_status: str
    started_at: datetime
    completed_at: datetime | None
    results: list[ValidationResultResponse]


class VersionDetailResponse(BaseModel):
    version_id: int
    api_id: int
    version_number: str
    change_note: str | None
    status: str
    api_name: str
    endpoint_url: str
    protocol_type: str
    input_format: str
    output_format: str
    capability_category: str
    description: str | None
    snapshot_origin: str
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    is_current: bool
    is_last_published: bool
    authentication: VersionAuthResponse
    specification: SpecificationMetadataResponse
    validation_runs: list[ValidationRunResponse]


class SpecificationContentResponse(BaseModel):
    specification_id: int
    version_id: int
    spec_type: str
    source_type: str
    file_path: str | None
    spec_url: str | None
    raw_content: str | None
    checksum: str | None
    uploaded_at: datetime


class LifecycleEventResponse(BaseModel):
    event_id: int
    api_id: int
    version_id: int
    action: str
    from_status: str | None
    to_status: str
    actor_user_id: int | None
    actor_name: str | None
    validation_run_id: int | None
    reason: str | None
    created_at: datetime


class LifecycleHistoryResponse(BaseModel):
    api_id: int
    total: int
    limit: int
    offset: int
    items: list[LifecycleEventResponse]


class HistoryAccessRequest(BaseModel):
    visibility: str
    allowed_user_ids: list[int] = Field(default_factory=list)


class HistoryAllowedUserResponse(BaseModel):
    user_id: int
    name: str
    email: str
    enterprise_id: int
    granted_by: int
    granted_at: datetime


class HistoryAccessResponse(BaseModel):
    api_id: int
    visibility: str
    allowed_users: list[HistoryAllowedUserResponse]
