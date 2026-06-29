from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.validation_schema import ValidationResponse


class SubmissionRequest(BaseModel):
    api_name: str
    endpoint_url: str
    protocol: str
    input_format: str
    output_format: str
    auth_method: str
    description: Optional[str] = None
    capability_category: str
    spec_content: str


class SubmissionResponse(BaseModel):
    submission_id: str
    status: str
    validation: ValidationResponse


class SubmissionListItem(BaseModel):
    api_id: int
    api_name: str
    endpoint_url: str
    protocol_type: str
    input_format: str
    output_format: str
    capability_category: str
    status: str
    created_at: datetime
    updated_at: datetime