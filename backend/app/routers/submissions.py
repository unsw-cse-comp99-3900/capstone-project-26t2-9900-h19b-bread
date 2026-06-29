import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_connection
from app.core.security import require_role

from app.schemas.submission_schema import (
    DraftSubmissionResponse,
    SubmissionListItem,
    SubmissionRequest,
    SubmissionResponse,
)
from app.schemas.validation_schema import ValidationRequest
from app.services.validation_service import validate_specification

router = APIRouter(prefix="/submissions", tags=["submissions"])


def to_plain_value(value):
    if hasattr(value, "value"):
        return value.value
    return str(value)


def map_protocol(protocol: str) -> str:
    protocol_value = protocol.upper()

    if protocol_value not in {"REST", "SOAP"}:
        raise HTTPException(status_code=400, detail="protocol must be REST or SOAP")

    return protocol_value


def map_spec_type(protocol_type: str) -> str:
    if protocol_type == "REST":
        return "OPENAPI"

    if protocol_type == "SOAP":
        return "WSDL"

    raise HTTPException(status_code=400, detail="unsupported protocol type")


def map_auth_method(auth_method: str) -> str:
    auth_method_value = auth_method.upper()

    allowed_methods = {"OAUTH2", "API_KEY", "BASIC", "MTLS", "OTHER"}

    if auth_method_value not in allowed_methods:
        return "OTHER"

    return auth_method_value


def map_submission_status(overall_status: str) -> str:
    if overall_status == "pass":
        return "DRAFT"

    return "REJECTED"


def map_version_status(overall_status: str) -> str:
    if overall_status == "pass":
        return "DRAFT"

    return "REJECTED"


def map_validation_overall_status(overall_status: str) -> str:
    if overall_status == "pass":
        return "PASSED"

    return "FAILED"


def map_validation_stage(stage_name: str) -> str:
    stage_value = stage_name.lower()

    stage_mapping = {
        "specification_validation": "SPECIFICATION_VALIDATION",
        "domain_compliance_validation": "DOMAIN_COMPLIANCE_VALIDATION",
        "security_validation": "SECURITY_VALIDATION",
    }

    return stage_mapping.get(stage_value, "SPECIFICATION_VALIDATION")


def map_validation_stage_status(stage_status: str) -> str:
    status_value = stage_status.lower()

    if status_value == "pass":
        return "PASSED"

    if status_value == "fail":
        return "FAILED"

    return "NOT_RUN"


@router.post("", response_model=SubmissionResponse)
def create_submission(
    request: SubmissionRequest,
    current_user: dict = Depends(require_role("PUBLISHER", "ADMIN")),
) -> SubmissionResponse:
    validation_request = ValidationRequest(
        protocol=request.protocol,
        spec_content=request.spec_content,
    )

    validation_result = validate_specification(validation_request)

    overall_status_value = to_plain_value(validation_result.overall_status)

    response_submission_status = (
        "validated"
        if overall_status_value == "pass"
        else "rejected"
    )

    protocol_type = map_protocol(request.protocol)
    spec_type = map_spec_type(protocol_type)
    auth_method = map_auth_method(request.auth_method)

    db_submission_status = map_submission_status(overall_status_value)
    db_version_status = map_version_status(overall_status_value)
    db_validation_overall_status = map_validation_overall_status(overall_status_value)

    enterprise_id = current_user["enterprise_id"]
    submitted_by = current_user["user_id"]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO api_submission (
                        enterprise_id,
                        submitted_by,
                        api_name,
                        endpoint_url,
                        protocol_type,
                        input_format,
                        output_format,
                        capability_category,
                        description,
                        status
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING api_id;
                    """,
                    (
                        enterprise_id,
                        submitted_by,
                        request.api_name,
                        request.endpoint_url,
                        protocol_type,
                        request.input_format,
                        request.output_format,
                        request.capability_category,
                        request.description,
                        db_submission_status,
                    ),
                )

                api_row = cursor.fetchone()
                api_id = api_row["api_id"]

                cursor.execute(
                    """
                    INSERT INTO api_version (
                        api_id,
                        created_by,
                        version_number,
                        change_note,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING version_id;
                    """,
                    (
                        api_id,
                        submitted_by,
                        "v1.0",
                        "Initial submission created from Submission API.",
                        db_version_status,
                    ),
                )

                version_row = cursor.fetchone()
                version_id = version_row["version_id"]

                cursor.execute(
                    """
                    INSERT INTO api_specification (
                        version_id,
                        spec_type,
                        source_type,
                        file_path,
                        raw_content
                    )
                    VALUES (%s, %s, 'FILE_UPLOAD', %s, %s);
                    """,
                    (
                        version_id,
                        spec_type,
                        f"inline/submission_{api_id}.txt",
                        request.spec_content,
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO auth_metadata (
                        api_id,
                        auth_method,
                        auth_description,
                        security_scheme_name,
                        is_complete
                    )
                    VALUES (%s, %s, %s, %s, TRUE);
                    """,
                    (
                        api_id,
                        auth_method,
                        f"{auth_method} authentication provided during submission.",
                        auth_method,
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO validation_run (
                        api_id,
                        version_id,
                        overall_status,
                        completed_at
                    )
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING validation_run_id;
                    """,
                    (
                        api_id,
                        version_id,
                        db_validation_overall_status,
                    ),
                )

                validation_run_row = cursor.fetchone()
                validation_run_id = validation_run_row["validation_run_id"]

                for stage in validation_result.stages:
                    stage_name = to_plain_value(stage.stage)
                    stage_status = to_plain_value(stage.status)

                    db_stage = map_validation_stage(stage_name)
                    db_stage_status = map_validation_stage_status(stage_status)

                    error_detail = None
                    if validation_result.errors:
                        error_detail = json.dumps(
                            [
                                error.model_dump()
                                for error in validation_result.errors
                            ],
                            default=str,
                        )

                    cursor.execute(
                        """
                        INSERT INTO validation_result (
                            validation_run_id,
                            stage,
                            status,
                            message,
                            error_detail
                        )
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (
                            validation_run_id,
                            db_stage,
                            db_stage_status,
                            "Validation stage completed.",
                            error_detail,
                        ),
                    )

        return SubmissionResponse(
            submission_id=str(api_id),
            status=response_submission_status,
            validation=validation_result,
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create submission: {exc}",
        )
@router.get("", response_model=List[SubmissionListItem])
def list_submissions(
    current_user: dict = Depends(require_role("PUBLISHER", "ADMIN")),
) -> list[SubmissionListItem]:
    enterprise_id = current_user["enterprise_id"]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        api_id,
                        api_name,
                        endpoint_url,
                        protocol_type,
                        input_format,
                        output_format,
                        capability_category,
                        status,
                        created_at,
                        updated_at
                    FROM api_submission
                    WHERE enterprise_id = %s
                    ORDER BY api_id DESC;
                    """,
                    (enterprise_id,),
                )

                rows = cursor.fetchall()

        return [
            SubmissionListItem(
                api_id=row["api_id"],
                api_name=row["api_name"],
                endpoint_url=row["endpoint_url"],
                protocol_type=row["protocol_type"],
                input_format=row["input_format"],
                output_format=row["output_format"],
                capability_category=row["capability_category"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list submissions: {exc}",
        )
@router.post("/draft", response_model=DraftSubmissionResponse)
def save_draft(
    request: SubmissionRequest,
    current_user: dict = Depends(require_role("PUBLISHER", "ADMIN")),
) -> DraftSubmissionResponse:
    protocol_type = map_protocol(request.protocol)
    spec_type = map_spec_type(protocol_type)
    auth_method = map_auth_method(request.auth_method)

    enterprise_id = current_user["enterprise_id"]
    submitted_by = current_user["user_id"]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO api_submission (
                        enterprise_id,
                        submitted_by,
                        api_name,
                        endpoint_url,
                        protocol_type,
                        input_format,
                        output_format,
                        capability_category,
                        description,
                        status
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, 'DRAFT'
                    )
                    RETURNING api_id;
                    """,
                    (
                        enterprise_id,
                        submitted_by,
                        request.api_name,
                        request.endpoint_url,
                        protocol_type,
                        request.input_format,
                        request.output_format,
                        request.capability_category,
                        request.description,
                    ),
                )

                api_row = cursor.fetchone()
                api_id = api_row["api_id"]

                cursor.execute(
                    """
                    INSERT INTO api_version (
                        api_id,
                        created_by,
                        version_number,
                        change_note,
                        status
                    )
                    VALUES (%s, %s, %s, %s, 'DRAFT')
                    RETURNING version_id;
                    """,
                    (
                        api_id,
                        submitted_by,
                        "v1.0",
                        "Draft created from Save Draft API.",
                    ),
                )

                version_row = cursor.fetchone()
                version_id = version_row["version_id"]

                cursor.execute(
                    """
                    INSERT INTO api_specification (
                        version_id,
                        spec_type,
                        source_type,
                        file_path,
                        raw_content
                    )
                    VALUES (%s, %s, 'FILE_UPLOAD', %s, %s);
                    """,
                    (
                        version_id,
                        spec_type,
                        f"inline/draft_{api_id}.txt",
                        request.spec_content,
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO auth_metadata (
                        api_id,
                        auth_method,
                        auth_description,
                        security_scheme_name,
                        is_complete
                    )
                    VALUES (%s, %s, %s, %s, TRUE);
                    """,
                    (
                        api_id,
                        auth_method,
                        f"{auth_method} authentication provided during draft save.",
                        auth_method,
                    ),
                )

        return DraftSubmissionResponse(
            submission_id=str(api_id),
            status="DRAFT",
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save draft: {exc}",
        )