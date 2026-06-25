from typing import List
from openapi_spec_validator import validate_spec
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from app.schemas.validation_schema import (
    Protocol,
    StageResult,
    ValidationErrorDetail,
    ValidationRequest,
    ValidationResponse,
    ValidationStage,
    ValidationStatus,
)
from app.services.api_parser_service import parse_openapi, parse_wsdl


def _build_response(
    protocol: Protocol,
    stage_status: ValidationStatus,
    errors: List[ValidationErrorDetail],
) -> ValidationResponse:
    """Assemble the final response in the format agreed with Member 1."""
    return ValidationResponse(
        overall_status=stage_status,
        stages=[
            StageResult(
                stage=ValidationStage.SPECIFICATION_VALIDATION,
                status=stage_status,
            )
        ],
        errors=errors,
    )


def _validate_rest(request: ValidationRequest) -> ValidationResponse:
    errors: List[ValidationErrorDetail] = []

    # Step 1: parse YAML/JSON
    spec_dict, parse_errors = parse_openapi(request.spec_content)
    errors.extend(parse_errors)

    if spec_dict is None:
        return _build_response(Protocol.REST, ValidationStatus.FAIL, errors)

    # Step 2: validate against OpenAPI standard
    try:
        validate_spec(spec_dict)
    except OpenAPIValidationError as exc:
        errors.append(
            ValidationErrorDetail(
                code="OPENAPI_INVALID_STRUCTURE",
                message=str(exc),
                path=None,
            )
        )
    except Exception as exc:
        errors.append(
            ValidationErrorDetail(
                code="VALIDATION_INTERNAL_ERROR",
                message=str(exc),
                path=None,
            )
        )

    status = ValidationStatus.PASS if not errors else ValidationStatus.FAIL
    return _build_response(Protocol.REST, status, errors)


def _validate_soap(request: ValidationRequest) -> ValidationResponse:
    _, errors = parse_wsdl(request.spec_content)
    status = ValidationStatus.PASS if not errors else ValidationStatus.FAIL
    return _build_response(Protocol.SOAP, status, errors)


def validate_specification(request: ValidationRequest) -> ValidationResponse:
    """
    Main entry point for specification validation.
    Called by the router when Peishuo submits a spec for validation.
    """
    if request.protocol == Protocol.REST:
        return _validate_rest(request)
    elif request.protocol == Protocol.SOAP:
        return _validate_soap(request)
    else:
        return _build_response(
            request.protocol,
            ValidationStatus.FAIL,
            [
                ValidationErrorDetail(
                    code="UNSUPPORTED_PROTOCOL",
                    message=f"Unsupported protocol: {request.protocol}",
                    path=None,
                )
            ],
        )