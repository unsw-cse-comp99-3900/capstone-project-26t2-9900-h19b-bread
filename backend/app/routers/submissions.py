import json
from typing import List
from urllib.parse import urlparse
from urllib.request import urlopen

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.database import get_connection
from app.core.security import require_role
from app.schemas.submission_schema import (
    DraftSubmissionResponse,
    SubmissionListItem,
    SubmissionRequest,
    SubmissionResponse,
    SubmissionUrlImportRequest,
    UserListItem,
)
from app.schemas.validation_schema import ValidationRequest
from app.services.validation_service import validate_specification
from app.services.schema_mapping.spec_schema_extractor import sync_api_schemas_from_spec


router = APIRouter(prefix="/submissions", tags=["submissions"])
MAX_SPEC_SIZE_BYTES = 5 * 1024 * 1024


def read_spec_from_url(spec_url: str) -> str:
    parsed_url = urlparse(spec_url)

    if parsed_url.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=400,
            detail="spec_url must use http or https.",
        )

    try:
        with urlopen(spec_url, timeout=10) as response:
            content = response.read(MAX_SPEC_SIZE_BYTES + 1)

        if len(content) > MAX_SPEC_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Specification file is too large. Maximum size is 5MB.",
            )

        return content.decode("utf-8")

    except HTTPException:
        raise

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Specification content must be valid UTF-8 text.",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to import specification from URL: {exc}",
        )


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
    auth_method_value = auth_method.strip().upper().replace(" ", "_").replace("-", "_")
    auth_method_value = auth_method_value.replace(".", "_")

    if auth_method_value in {"OAUTH_2", "OAUTH2", "OAUTH_2_0"}:
        return "OAUTH2"

    if auth_method_value in {"APIKEY", "API_KEY"}:
        return "API_KEY"

    if auth_method_value in {"BASIC", "BASIC_AUTHENTICATION", "BASIC_AUTH"}:
        return "BASIC"

    if auth_method_value in {"MTLS", "MUTUAL_TLS"}:
        return "MTLS"

    allowed_methods = {
        "OAUTH2",
        "API_KEY",
        "BASIC",
        "TOKEN",
        "BEARER",
        "MTLS",
        "NONE",
        "OTHER",
    }

    if auth_method_value not in allowed_methods:
        return "OTHER"

    return auth_method_value


def map_api_category(capability_category: str) -> str:
    category_value = capability_category.lower()

    if "validation" in category_value or "validate" in category_value:
        return "VALIDATION"

    if (
        "transformation" in category_value
        or "transform" in category_value
        or "mapping" in category_value
    ):
        return "TRANSFORMATION"

    if (
        "communication" in category_value
        or "send" in category_value
        or "transmission" in category_value
    ):
        return "COMMUNICATION"

    return "VALIDATION"


def map_submission_status(overall_status: str) -> str:
    if overall_status == "pass":
        return "PUBLISHED"

    return "REJECTED"


def map_version_status(overall_status: str) -> str:
    if overall_status == "pass":
        return "PUBLISHED"

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


def create_submission_records(
    request: SubmissionRequest,
    current_user: dict,
    submission_status: str,
    version_status: str,
    source_type: str,
    file_path: str | None,
    spec_url: str | None,
    validation_result=None,
) -> int:
    protocol_type = map_protocol(request.protocol)
    spec_type = map_spec_type(protocol_type)
    auth_method = map_auth_method(request.auth_method)
    api_category = map_api_category(request.capability_category)

    enterprise_id = current_user["enterprise_id"]
    submitted_by = current_user["user_id"]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_submission (
                    enterprise_id,
                    submitted_by,
                    api_name,
                    category,
                    status
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING api_id;
                """,
                (
                    enterprise_id,
                    submitted_by,
                    request.api_name,
                    api_category,
                    submission_status,
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
                    status,
                    is_current,
                    api_name,
                    endpoint_url,
                    protocol_type,
                    category,
                    capability_category,
                    description,
                    input_format,
                    output_format,
                    input_formats,
                    output_formats,
                    client_types,
                    published_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    TRUE, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb,
                    CASE WHEN %s = 'PUBLISHED' THEN CURRENT_TIMESTAMP ELSE NULL END
                )
                RETURNING version_id;
                """,
                (
                    api_id,
                    submitted_by,
                    "v1.0",
                    "Initial submission created from Submission API.",
                    version_status,
                    request.api_name,
                    request.endpoint_url,
                    protocol_type,
                    api_category,
                    request.capability_category,
                    request.description,
                    request.input_format,
                    request.output_format,
                    json.dumps([request.input_format]),
                    json.dumps([request.output_format]),
                    json.dumps([protocol_type]),
                    version_status,
                ),
            )

            version_row = cursor.fetchone()
            version_id = version_row["version_id"]

            cursor.execute(
                """
                UPDATE api_submission
                SET current_version_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE api_id = %s;
                """,
                (version_id, api_id),
            )

            cursor.execute(
                """
                INSERT INTO api_specification (
                    version_id,
                    spec_type,
                    source_type,
                    file_path,
                    spec_url,
                    raw_content
                )
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (
                    version_id,
                    spec_type,
                    source_type,
                    file_path,
                    spec_url,
                    request.spec_content,
                ),
            )

            sync_api_schemas_from_spec(
                cursor,
                api_id=api_id,
                version_id=version_id,
                spec_type=spec_type,
                spec_content=request.spec_content,
                input_format=request.input_format,
                output_format=request.output_format,
            )

            cursor.execute(
                """
                INSERT INTO auth_metadata (
                    api_id,
                    version_id,
                    auth_method,
                    auth_method_raw,
                    auth_description,
                    security_scheme_name,
                    is_complete
                )
                VALUES (%s, %s, %s, %s, %s, %s, TRUE);
                """,
                (
                    api_id,
                    version_id,
                    auth_method,
                    request.auth_method,
                    f"{auth_method} authentication provided during submission.",
                    auth_method,
                ),
            )

            if validation_result is not None:
                db_validation_overall_status = map_validation_overall_status(
                    to_plain_value(validation_result.overall_status)
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

    return api_id


@router.post("", response_model=SubmissionResponse)
def create_submission(
    request: SubmissionRequest,
    current_user: dict = Depends(require_role("PUBLISHER", "MANAGER", "ADMIN")),
) -> SubmissionResponse:
    validation_request = ValidationRequest(
        protocol=request.protocol,
        spec_content=request.spec_content,
        auth_method=request.auth_method,
        endpoint_url=request.endpoint_url,
        input_format=request.input_format,
        output_format=request.output_format,
        capability_category=request.capability_category,
    )

    validation_result = validate_specification(validation_request)

    overall_status_value = to_plain_value(validation_result.overall_status)

    response_submission_status = (
        "published"
        if overall_status_value == "pass"
        else "rejected"
    )

    db_submission_status = map_submission_status(overall_status_value)
    db_version_status = map_version_status(overall_status_value)

    try:
        api_id = create_submission_records(
            request=request,
            current_user=current_user,
            submission_status=db_submission_status,
            version_status=db_version_status,
            source_type="FILE_UPLOAD",
            file_path="inline/submission.txt",
            spec_url=None,
            validation_result=validation_result,
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
    current_user: dict = Depends(require_role("PUBLISHER", "VIEWER", "MANAGER", "ADMIN")),
) -> list[SubmissionListItem]:
    enterprise_id = current_user["enterprise_id"]
    current_user_id = current_user["user_id"]
    current_user_role = current_user["role"].upper()

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.api_id,
                        COALESCE(v.api_name, s.api_name) AS api_name,
                        COALESCE(v.endpoint_url, '') AS endpoint_url,
                        COALESCE(v.protocol_type::text, 'REST') AS protocol_type,
                        COALESCE(v.input_format, '') AS input_format,
                        COALESCE(v.output_format, '') AS output_format,
                        COALESCE(v.capability_category, '') AS capability_category,
                        s.status::text AS status,
                        s.created_at,
                        s.updated_at,
                        s.submitted_by,
                        u.name AS submitted_by_name
                    FROM api_submission s
                    LEFT JOIN api_version v
                        ON s.current_version_id = v.version_id
                    LEFT JOIN app_user u
                        ON s.submitted_by = u.user_id
                    WHERE s.enterprise_id = %s
                    ORDER BY s.api_id DESC;
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
                submitted_by=row["submitted_by"],
                submitted_by_name=row["submitted_by_name"],
                is_current_user_api=row["submitted_by"] == current_user_id,
                can_manage=(
                    row["submitted_by"] == current_user_id
                    or current_user_role in {"MANAGER", "ADMIN"}
                ),
            )
            for row in rows
        ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list submissions: {exc}",
        )


@router.get("/authors", response_model=List[UserListItem])
def list_submission_authors(
    current_user: dict = Depends(require_role("PUBLISHER", "VIEWER", "MANAGER", "ADMIN")),
) -> list[UserListItem]:
    enterprise_id = current_user["enterprise_id"]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        user_id,
                        name
                    FROM app_user
                    WHERE enterprise_id = %s
                    ORDER BY name ASC;
                    """,
                    (enterprise_id,),
                )

                rows = cursor.fetchall()

        return [
            UserListItem(
                user_id=row["user_id"],
                name=row["name"],
            )
            for row in rows
        ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list submission authors: {exc}",
        )


@router.post("/draft", response_model=DraftSubmissionResponse)
def save_draft(
    request: SubmissionRequest,
    current_user: dict = Depends(require_role("PUBLISHER", "MANAGER", "ADMIN")),
) -> DraftSubmissionResponse:
    try:
        api_id = create_submission_records(
            request=request,
            current_user=current_user,
            submission_status="DRAFT",
            version_status="DRAFT",
            source_type="FILE_UPLOAD",
            file_path="inline/draft.txt",
            spec_url=None,
            validation_result=None,
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


@router.post("/import-url", response_model=SubmissionResponse)
def import_submission_spec_from_url(
    request: SubmissionUrlImportRequest,
    current_user: dict = Depends(require_role("PUBLISHER", "MANAGER", "ADMIN")),
) -> SubmissionResponse:
    spec_content = read_spec_from_url(str(request.spec_url))

    submission_request = SubmissionRequest(
        api_name=request.api_name,
        endpoint_url=request.endpoint_url,
        protocol=request.protocol,
        input_format=request.input_format,
        output_format=request.output_format,
        auth_method=request.auth_method,
        description=request.description,
        capability_category=request.capability_category,
        spec_content=spec_content,
    )

    validation_request = ValidationRequest(
        protocol=submission_request.protocol,
        spec_content=submission_request.spec_content,
        auth_method=submission_request.auth_method,
        endpoint_url=submission_request.endpoint_url,
        input_format=submission_request.input_format,
        output_format=submission_request.output_format,
        capability_category=submission_request.capability_category,
    )

    validation_result = validate_specification(validation_request)

    overall_status_value = to_plain_value(validation_result.overall_status)

    response_submission_status = (
        "published"
        if overall_status_value == "pass"
        else "rejected"
    )

    db_submission_status = map_submission_status(overall_status_value)
    db_version_status = map_version_status(overall_status_value)

    try:
        api_id = create_submission_records(
            request=submission_request,
            current_user=current_user,
            submission_status=db_submission_status,
            version_status=db_version_status,
            source_type="URL_REFERENCE",
            file_path=None,
            spec_url=str(request.spec_url),
            validation_result=validation_result,
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
            detail=f"Failed to import submission from URL: {exc}",
        )


@router.post("/upload", response_model=SubmissionResponse)
async def upload_submission_spec(
    api_name: str = Form(...),
    endpoint_url: str = Form(...),
    protocol: str = Form(...),
    input_format: str = Form(...),
    output_format: str = Form(...),
    auth_method: str = Form(...),
    capability_category: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("PUBLISHER", "MANAGER", "ADMIN")),
) -> SubmissionResponse:
    file_content = await file.read()

    if len(file_content) > MAX_SPEC_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Specification file is too large. Maximum size is 5MB.",
        )

    try:
        spec_content = file_content.decode("utf-8")

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Specification file must be valid UTF-8 text.",
        )

    request = SubmissionRequest(
        api_name=api_name,
        endpoint_url=endpoint_url,
        protocol=protocol,
        input_format=input_format,
        output_format=output_format,
        auth_method=auth_method,
        description=description,
        capability_category=capability_category,
        spec_content=spec_content,
    )

    validation_request = ValidationRequest(
        protocol=request.protocol,
        spec_content=request.spec_content,
        auth_method=request.auth_method,
        endpoint_url=request.endpoint_url,
        input_format=request.input_format,
        output_format=request.output_format,
        capability_category=request.capability_category,
    )

    validation_result = validate_specification(validation_request)

    overall_status_value = to_plain_value(validation_result.overall_status)

    response_submission_status = (
        "published"
        if overall_status_value == "pass"
        else "rejected"
    )

    db_submission_status = map_submission_status(overall_status_value)
    db_version_status = map_version_status(overall_status_value)

    try:
        api_id = create_submission_records(
            request=request,
            current_user=current_user,
            submission_status=db_submission_status,
            version_status=db_version_status,
            source_type="FILE_UPLOAD",
            file_path=f"upload/{file.filename}",
            spec_url=None,
            validation_result=validation_result,
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
            detail=f"Failed to upload submission specification: {exc}",
        )