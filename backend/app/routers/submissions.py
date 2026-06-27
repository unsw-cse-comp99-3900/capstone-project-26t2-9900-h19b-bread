from fastapi import APIRouter
from app.schemas.submission_schema import SubmissionRequest, SubmissionResponse
from app.schemas.validation_schema import ValidationRequest
from app.services.validation_service import validate_specification

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionResponse)
def create_submission(request: SubmissionRequest) -> SubmissionResponse:
    validation_request = ValidationRequest(
        protocol=request.protocol,
        spec_content=request.spec_content
    )

    validation_result = validate_specification(validation_request)

    overall_status = validation_result.overall_status

    if hasattr(overall_status, "value"):
        overall_status_value = overall_status.value
    else:
        overall_status_value = str(overall_status)

    submission_status = (
        "validated"
        if overall_status_value == "pass"
        else "rejected"
    )

    return SubmissionResponse(
        submission_id="sub_001",
        status=submission_status,
        validation=validation_result
    )