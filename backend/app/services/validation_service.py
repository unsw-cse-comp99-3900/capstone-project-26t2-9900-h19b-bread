import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple
from urllib.parse import urlparse

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
from app.services.validation_domain import _run_domain_stage
from app.services.validation_security import _run_security_stage


def _tag_errors(
    errors: List[ValidationErrorDetail],
    stage: ValidationStage,
) -> List[ValidationErrorDetail]:
    """Attach stage to each error so FR-7 feedback can group by stage."""
    for error in errors:
        if error.stage is None:
            error.stage = stage
    return errors


def _has_blocking(errors: List[ValidationErrorDetail]) -> bool:
    """True if any error is blocking (severity != 'warning'). Warnings don't fail a stage."""
    return any(error.severity != "warning" for error in errors)


def _local_tag(tag: object) -> str:
    """Return the local name of an ElementTree tag, dropping any '{ns}' prefix."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[-1]
    return tag if isinstance(tag, str) else ""


def _build_pipeline_response(
    spec_status: ValidationStatus,
    domain_status: ValidationStatus,
    security_status: ValidationStatus,
    errors: List[ValidationErrorDetail],
) -> ValidationResponse:
    """
    Always return all three stages (FR-7).
    overall_status is pass only when every executed stage passed.
    not_run stages do not count as pass or fail for overall.
    """
    stages = [
        StageResult(
            stage=ValidationStage.SPECIFICATION_VALIDATION,
            status=spec_status,
        ),
        StageResult(
            stage=ValidationStage.DOMAIN_COMPLIANCE_VALIDATION,
            status=domain_status,
        ),
        StageResult(
            stage=ValidationStage.SECURITY_VALIDATION,
            status=security_status,
        ),
    ]

    executed = [
        status
        for status in (spec_status, domain_status, security_status)
        if status != ValidationStatus.NOT_RUN
    ]
    overall = (
        ValidationStatus.PASS
        if executed and all(status == ValidationStatus.PASS for status in executed)
        else ValidationStatus.FAIL
    )

    return ValidationResponse(
        overall_status=overall,
        stages=stages,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Metadata-consistency configuration (FR-3 form metadata vs actual spec).
# ---------------------------------------------------------------------------
# Declared data format -> substring expected in the spec's media types.
_FORMAT_MEDIA_TOKEN = {
    "json": "json",
    "xml": "xml",
    "ubl": "xml",   # UBL is an XML dialect
    "pdf": "pdf",
    "csv": "csv",
    "yaml": "yaml",
    "yml": "yaml",
}

def _format_expected_token(fmt: Optional[str]) -> Optional[str]:
    """Map a declared format string (JSON/XML/UBL/...) to a media-type substring."""
    key = (fmt or "").strip().lower()
    if not key:
        return None
    for name, token in _FORMAT_MEDIA_TOKEN.items():
        if name in key:
            return token
    return None


def _collect_media_types(spec_dict: dict) -> Tuple[set, set]:
    """Return (request_media_types, response_media_types) declared across all paths."""
    request_media: set = set()
    response_media: set = set()

    paths = spec_dict.get("paths") or {}
    if not isinstance(paths, dict):
        return request_media, response_media

    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue

            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                content = request_body.get("content")
                if isinstance(content, dict):
                    request_media.update(content.keys())

            responses = operation.get("responses")
            if isinstance(responses, dict):
                for response in responses.values():
                    if isinstance(response, dict):
                        content = response.get("content")
                        if isinstance(content, dict):
                            response_media.update(content.keys())

    return request_media, response_media


def _check_format_consistency(
    declared_format: Optional[str],
    media_types: set,
    direction: str,
    errors: List[ValidationErrorDetail],
) -> None:
    """Warn if a declared input/output format is absent from the spec's media types."""
    expected = _format_expected_token(declared_format)
    if not expected or not media_types:
        return  # nothing declared, or spec has no content types to verify against

    media_blob = " ".join(media_types).lower()
    if expected not in media_blob:
        errors.append(
            ValidationErrorDetail(
                code=f"METADATA_{direction.upper()}_FORMAT_MISMATCH",
                message=(
                    f"Declared {direction} format '{declared_format}' was not found among "
                    f"the specification media types ({', '.join(sorted(media_types))})."
                ),
                path=f"{direction}_format",
                severity="warning",
                stage=ValidationStage.SPECIFICATION_VALIDATION,
            )
        )


def _check_rest_metadata(
    request: ValidationRequest,
    spec_dict: dict,
) -> List[ValidationErrorDetail]:
    """
    FR-3 metadata consistency for REST: endpoint_url vs servers, and
    input/output_format vs the spec's declared media types.
    Reported under the specification stage. Mismatches are warnings (env/naming
    differences are common); missing structure is surfaced but non-blocking.
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.SPECIFICATION_VALIDATION

    # endpoint_url vs servers
    if request.endpoint_url:
        servers = spec_dict.get("servers") or []
        server_urls = [
            server.get("url")
            for server in servers
            if isinstance(server, dict) and server.get("url")
        ]
        if not server_urls:
            errors.append(
                ValidationErrorDetail(
                    code="METADATA_ENDPOINT_UNVERIFIABLE",
                    message="Specification declares no servers; endpoint_url cannot be verified.",
                    path="endpoint_url",
                    severity="warning",
                    stage=stage,
                )
            )
        else:
            declared_host = urlparse(request.endpoint_url).netloc or request.endpoint_url
            spec_hosts = {
                urlparse(url).netloc for url in server_urls if isinstance(url, str)
            }
            if declared_host and declared_host not in spec_hosts:
                errors.append(
                    ValidationErrorDetail(
                        code="METADATA_ENDPOINT_MISMATCH",
                        message=(
                            f"Declared endpoint_url host '{declared_host}' does not match any "
                            f"server in the specification ({', '.join(sorted(spec_hosts))})."
                        ),
                        path="endpoint_url",
                        severity="warning",
                        stage=stage,
                    )
                )

    # input/output_format vs media types
    request_media, response_media = _collect_media_types(spec_dict)
    _check_format_consistency(request.input_format, request_media, "input", errors)
    _check_format_consistency(request.output_format, response_media, "output", errors)

    return errors


def _check_soap_format(
    declared_format: Optional[str],
    direction: str,
    errors: List[ValidationErrorDetail],
) -> None:
    """SOAP payloads are XML; warn if a declared input/output format is not XML/UBL."""
    expected = _format_expected_token(declared_format)
    if not expected:
        return  # nothing declared or unrecognized token -> nothing to check
    if expected != "xml":
        errors.append(
            ValidationErrorDetail(
                code=f"METADATA_{direction.upper()}_FORMAT_MISMATCH",
                message=(
                    f"Declared {direction} format '{declared_format}' is inconsistent with "
                    f"SOAP: SOAP message payloads are XML (e.g. XML / UBL)."
                ),
                path=f"{direction}_format",
                severity="warning",
                stage=ValidationStage.SPECIFICATION_VALIDATION,
            )
        )


def _check_soap_metadata(
    request: ValidationRequest,
    xml_root: "ET.Element",
) -> List[ValidationErrorDetail]:
    """
    FR-3 metadata consistency for SOAP: endpoint_url vs soap:address locations,
    and input/output_format vs SOAP's inherently-XML payloads.
    Reported under the specification stage; mismatches are warnings (non-blocking).
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.SPECIFICATION_VALIDATION

    # endpoint_url vs <soap:address location="...">
    if request.endpoint_url:
        locations = {
            elem.get("location")
            for elem in xml_root.iter()
            if _local_tag(elem.tag).lower() == "address" and elem.get("location")
        }
        if not locations:
            errors.append(
                ValidationErrorDetail(
                    code="METADATA_ENDPOINT_UNVERIFIABLE",
                    message="WSDL declares no soap:address; endpoint_url cannot be verified.",
                    path="endpoint_url",
                    severity="warning",
                    stage=stage,
                )
            )
        else:
            declared_host = urlparse(request.endpoint_url).netloc or request.endpoint_url
            spec_hosts = {
                urlparse(url).netloc for url in locations if isinstance(url, str)
            }
            if declared_host and declared_host not in spec_hosts:
                errors.append(
                    ValidationErrorDetail(
                        code="METADATA_ENDPOINT_MISMATCH",
                        message=(
                            f"Declared endpoint_url host '{declared_host}' does not match any "
                            f"soap:address in the WSDL ({', '.join(sorted(spec_hosts))})."
                        ),
                        path="endpoint_url",
                        severity="warning",
                        stage=stage,
                    )
                )

    _check_soap_format(request.input_format, "input", errors)
    _check_soap_format(request.output_format, "output", errors)

    return errors


def _validate_wsdl_structure(xml_root: "ET.Element") -> List[ValidationErrorDetail]:
    """
    FR-4 structural completeness for WSDL (the SOAP analogue of validate_spec).

    parse_wsdl only guarantees well-formed XML with a <definitions> root; this
    goes further and requires the essential service contract: at least one
    <portType> declaring at least one <operation>. Missing pieces are blocking.
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.SPECIFICATION_VALIDATION

    local_tags = [_local_tag(elem.tag).lower() for elem in xml_root.iter()]
    tag_set = set(local_tags)

    if "porttype" not in tag_set:
        errors.append(
            ValidationErrorDetail(
                code="WSDL_NO_PORTTYPE",
                message="WSDL must declare at least one <portType> (service interface).",
                path="wsdl:portType",
                stage=stage,
            )
        )
    elif "operation" not in tag_set:
        errors.append(
            ValidationErrorDetail(
                code="WSDL_NO_OPERATION",
                message="WSDL <portType> must declare at least one <operation>.",
                path="wsdl:portType/operation",
                stage=stage,
            )
        )

    return errors


def _run_specification_stage(
    request: ValidationRequest,
) -> Tuple[ValidationStatus, List[ValidationErrorDetail], Optional[object]]:
    """
    FR-4: parse + structural validation, plus FR-3 protocol/endpoint/format
    metadata-consistency checks.
    """
    errors: List[ValidationErrorDetail] = []

    # FR-3: declared protocol must match the actual document type before parsing.
    stripped = request.spec_content.strip()
    looks_like_xml = stripped.startswith("<")
    if request.protocol == Protocol.REST and looks_like_xml:
        errors.append(
            ValidationErrorDetail(
                code="METADATA_PROTOCOL_SPEC_MISMATCH",
                message="Declared protocol is REST but the document looks like XML/WSDL.",
                path="protocol",
                stage=ValidationStage.SPECIFICATION_VALIDATION,
            )
        )
        return ValidationStatus.FAIL, errors, None
    if request.protocol == Protocol.SOAP and not looks_like_xml:
        errors.append(
            ValidationErrorDetail(
                code="METADATA_PROTOCOL_SPEC_MISMATCH",
                message="Declared protocol is SOAP but the document is not XML/WSDL.",
                path="protocol",
                stage=ValidationStage.SPECIFICATION_VALIDATION,
            )
        )
        return ValidationStatus.FAIL, errors, None

    if request.protocol == Protocol.REST:
        spec_dict, parse_errors = parse_openapi(request.spec_content)
        _tag_errors(parse_errors, ValidationStage.SPECIFICATION_VALIDATION)
        errors.extend(parse_errors)

        if spec_dict is None:
            return ValidationStatus.FAIL, errors, None

        try:
            validate_spec(spec_dict)
        except OpenAPIValidationError as exc:
            errors.append(
                ValidationErrorDetail(
                    code="OPENAPI_INVALID_STRUCTURE",
                    message=str(exc),
                    path=None,
                    stage=ValidationStage.SPECIFICATION_VALIDATION,
                )
            )
        except Exception as exc:
            errors.append(
                ValidationErrorDetail(
                    code="VALIDATION_INTERNAL_ERROR",
                    message=str(exc),
                    path=None,
                    stage=ValidationStage.SPECIFICATION_VALIDATION,
                )
            )

        # FR-3 metadata consistency (endpoint / formats) only if structurally sound.
        if not errors:
            errors.extend(_check_rest_metadata(request, spec_dict))

        status = ValidationStatus.FAIL if _has_blocking(errors) else ValidationStatus.PASS
        return status, errors, spec_dict

    if request.protocol == Protocol.SOAP:
        xml_root, parse_errors = parse_wsdl(request.spec_content)
        _tag_errors(parse_errors, ValidationStage.SPECIFICATION_VALIDATION)
        errors.extend(parse_errors)

        # FR-4 structural completeness (portType / operation), analogous to
        # validate_spec for OpenAPI.
        if isinstance(xml_root, ET.Element):
            errors.extend(_validate_wsdl_structure(xml_root))

        # FR-3 metadata consistency (endpoint / formats) only if structurally sound.
        if not _has_blocking(errors) and isinstance(xml_root, ET.Element):
            errors.extend(_check_soap_metadata(request, xml_root))

        status = ValidationStatus.FAIL if _has_blocking(errors) else ValidationStatus.PASS
        return status, errors, xml_root

    errors.append(
        ValidationErrorDetail(
            code="UNSUPPORTED_PROTOCOL",
            message=f"Unsupported protocol: {request.protocol}",
            path=None,
            stage=ValidationStage.SPECIFICATION_VALIDATION,
        )
    )
    return ValidationStatus.FAIL, errors, None


def validate_specification(request: ValidationRequest) -> ValidationResponse:
    """
    Multi-stage validation entry point.
    - Stage 1 (FR-4): implemented
    - Stage 2 (FR-5): implemented
    - Stage 3 (FR-6): implemented
    """
    all_errors: List[ValidationErrorDetail] = []

    # Stage 1: Specification validation
    spec_status, spec_errors, _parsed = _run_specification_stage(request)
    all_errors.extend(spec_errors)

    if spec_status != ValidationStatus.PASS:
        # Later stages depend on a valid spec — mark them not_run (FR-7)
        return _build_pipeline_response(
            spec_status=spec_status,
            domain_status=ValidationStatus.NOT_RUN,
            security_status=ValidationStatus.NOT_RUN,
            errors=all_errors,
        )

    # Stage 2: Domain compliance (FR-5)
    domain_status, domain_errors = _run_domain_stage(request, _parsed)
    all_errors.extend(domain_errors)

    # Stage 3: Security (FR-6)
    security_status, security_errors = _run_security_stage(request, _parsed)
    all_errors.extend(security_errors)

    return _build_pipeline_response(
        spec_status=ValidationStatus.PASS,
        domain_status=domain_status,
        security_status=security_status,
        errors=all_errors,
    )
