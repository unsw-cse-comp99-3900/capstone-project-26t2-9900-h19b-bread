from pydantic import BaseModel
from typing import Optional
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