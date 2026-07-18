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

# E-invoicing capability categories (FR-3) -> keywords used both to recognize
# the declared value and to check it against the spec's operations.
_CAPABILITY_CATEGORIES = {
    "invoice creation": ("creat", "submit", "issue", "generat"),
    "validation": ("validat", "verif", "check", "complian"),
    "transmission": ("transmi", "send", "deliver", "exchange", "dispatch"),
    "archiving": ("archiv", "store", "retention"),
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


def _check_capability_category(
    request: ValidationRequest,
    haystack: str,
) -> List[ValidationErrorDetail]:
    """
    FR-3 metadata: capability_category must be one of the recognized e-invoicing
    categories, and (best-effort) be consistent with the spec's operations.
    Reported under the domain stage. Invalid value is blocking; inconsistency is a warning.
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.DOMAIN_COMPLIANCE_VALIDATION

    raw = (request.capability_category or "").strip().lower()
    if not raw:
        return errors  # optional field: only validate when provided

    matched_category = None
    for category, keywords in _CAPABILITY_CATEGORIES.items():
        if category in raw or any(keyword in raw for keyword in keywords):
            matched_category = category
            break

    if matched_category is None:
        errors.append(
            ValidationErrorDetail(
                code="METADATA_CAPABILITY_INVALID",
                message=(
                    f"capability_category '{request.capability_category}' is not recognized. "
                    f"Expected one of: invoice creation, validation, transmission, archiving."
                ),
                path="capability_category",
                stage=stage,
            )
        )
        return errors

    keywords = _CAPABILITY_CATEGORIES[matched_category]
    if not any(keyword in haystack for keyword in keywords):
        errors.append(
            ValidationErrorDetail(
                code="METADATA_CAPABILITY_INCONSISTENT",
                message=(
                    f"Declared capability_category '{request.capability_category}' is not "
                    f"reflected by the API operations (no matching operation names/summaries)."
                ),
                path="capability_category",
                severity="warning",
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
        status = ValidationStatus.PASS if not errors else ValidationStatus.FAIL
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


# FR-5 domain-compliance configuration (aligned with EN 16931 / UBL 2.1 / PEPPOL BIS Billing 3.0 core invoice model).
_DOMAIN_FIELD_CATEGORIES = {
    "invoice_number": ("invoicenumber", "invoiceid", "invoiceno"),
    "invoice_date": ("invoicedate", "issuedate"),
    "invoice_type_code": ("invoicetypecode", "typecode"),
    "currency": ("currency", "currencycode"),
    "seller": ("seller", "supplier", "supplierparty", "accountingsupplier"),
    "buyer": ("buyer", "customer", "customerparty", "accountingcustomer"),
    "totals": (
        "taxexclusiveamount",
        "taxinclusiveamount",
        "payableamount",
        "grandtotal",
        "totalamount",
        "legalmonetarytotal",
    ),
    "tax": ("taxtotal", "taxamount", "vatamount", "taxrate", "vatrate"),
    "line_items": ("invoiceline", "lineitems", "lineextension"),
}

# Weak textual signals.
_DOMAIN_KEYWORDS = (
    "invoice",
    "einvoice",
    "e-invoice",
    "credit note",
    "creditnote",
    "billing",
    "tax",
    "vat",
)

# Strong signals
_DOMAIN_STANDARD_MARKERS = (
    "ubl",
    "peppol",
    "en16931",
    "en 16931",
    "bis billing",
)


def _normalize_field_name(name: str) -> str:
    """Lowercase and strip separators / XML namespace prefixes for matching."""
    text = str(name).strip().lower()
    if ":" in text:
        text = text.split(":")[-1]
    for sep in ("_", "-", " ", "."):
        text = text.replace(sep, "")
    return text


# Keys whose values are sample data, not schema definitions; skip them so we
# do not harvest field names out of example payloads / enum values.
_SCHEMA_SKIP_KEYS = frozenset({"example", "examples", "default", "enum"})


def _collect_property_names(
    node: object,
    names: set,
    depth: int = 0,
) -> None:
    """
    Recursively collect every property name declared anywhere under the node.

    This walks all dict values / list entries (not just schema keywords), so
    it also reaches inline request/response schemas defined directly under
    paths.*.requestBody/responses.*.content.*.schema — not only components.schemas.
    Any key literally named "properties" is treated as a schema property map.
    depth guard prevents runaway recursion on deep specs.
    """
    if depth > 40 or node is None:
        return

    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for prop_name, prop_schema in props.items():
                names.add(prop_name)
                _collect_property_names(prop_schema, names, depth + 1)

        for key, value in node.items():
            if key == "properties" or key in _SCHEMA_SKIP_KEYS:
                continue
            _collect_property_names(value, names, depth + 1)

    elif isinstance(node, list):
        for entry in node:
            _collect_property_names(entry, names, depth + 1)


def _run_domain_stage(
    request: ValidationRequest,
    parsed_spec: Optional[object],
) -> Tuple[ValidationStatus, List[ValidationErrorDetail]]:
    """
    FR-5: E-invoicing domain compliance validation.

    Scoring model (aligned with EN 16931 / UBL 2.1 / PEPPOL BIS Billing 3.0):
        strong   = number of distinct core invoice field categories matched (0..9)
        standard = +2 if the spec references a recognized e-invoicing standard
        keyword  = number of weak textual keywords matched, capped at +2
        score    = strong + standard + min(keyword, 2)

    Hard gate:
        A submission can only PASS if it shows *structural* or *standard* evidence,
        i.e. strong >= 1 OR a recognized standard is referenced. This blocks
        "keyword-only" fakes (invoice/tax words in text but no invoice fields).

    Decision:
        not (strong >= 1 or standard)   -> FAIL (DOMAIN_NOT_EINVOICING)
        eligible and score >= 4         -> PASS
        eligible and 2 <= score < 4     -> PASS + warning (weak but plausible)
        eligible and score < 2          -> FAIL (DOMAIN_NOT_EINVOICING)
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.DOMAIN_COMPLIANCE_VALIDATION

    if request.protocol == Protocol.SOAP:
        # Sprint 2 simplification: WSDL domain parsing is limited; skip deep rules.
        return ValidationStatus.PASS, errors

    if request.protocol != Protocol.REST:
        return ValidationStatus.PASS, errors

    if not isinstance(parsed_spec, dict):
        errors.append(
            ValidationErrorDetail(
                code="DOMAIN_SPEC_UNAVAILABLE",
                message="Parsed OpenAPI document is unavailable for domain validation.",
                path=None,
                stage=stage,
            )
        )
        return ValidationStatus.FAIL, errors

    # --- Signal 1: textual haystack (title/description/tags/paths/operations) ---
    haystack_parts: List[str] = []

    info = parsed_spec.get("info") or {}
    haystack_parts.append(str(info.get("title") or ""))
    haystack_parts.append(str(info.get("description") or ""))

    tags = parsed_spec.get("tags") or []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                haystack_parts.append(str(tag.get("name") or ""))
                haystack_parts.append(str(tag.get("description") or ""))

    paths = parsed_spec.get("paths") or {}
    if isinstance(paths, dict):
        for path_key, path_item in paths.items():
            haystack_parts.append(str(path_key))
            if not isinstance(path_item, dict):
                continue
            for _method, operation in path_item.items():
                if isinstance(operation, dict):
                    haystack_parts.append(str(operation.get("operationId") or ""))
                    haystack_parts.append(str(operation.get("summary") or ""))

    haystack = " ".join(haystack_parts).lower()

    # --- Signal 2: schema property names -> core invoice field categories ---
    # Collect from both reusable components.schemas AND inline request/response
    # schemas declared under paths, so specs that inline their models are covered.
    components = parsed_spec.get("components") or {}
    field_names: set = set()
    _collect_property_names(components.get("schemas"), field_names)
    _collect_property_names(parsed_spec.get("paths"), field_names)

    normalized_fields = {_normalize_field_name(name) for name in field_names}

    matched_categories = set()
    for category, fragments in _DOMAIN_FIELD_CATEGORIES.items():
        for fragment in fragments:
            if any(fragment in field for field in normalized_fields):
                matched_categories.add(category)
                break

    strong_score = len(matched_categories)

    # --- Signal 3: explicit e-invoicing standard reference ---
    standard_matched = any(marker in haystack for marker in _DOMAIN_STANDARD_MARKERS)
    standard_score = 2 if standard_matched else 0

    # --- Signal 4: weak keywords (capped) ---
    keyword_hits = sum(1 for keyword in _DOMAIN_KEYWORDS if keyword in haystack)
    keyword_score = min(keyword_hits, 2)

    score = strong_score + standard_score + keyword_score

    # Hard gate: keyword-only evidence can never pass. Passing requires at least
    # one structural invoice field OR an explicit e-invoicing standard reference.
    eligible_to_pass = strong_score >= 1 or standard_matched

    if eligible_to_pass and score >= 4:
        pass  # strong evidence; no domain-signal error to add
    elif eligible_to_pass and score >= 2:
        # Plausible but weak: surface a warning for FR-7 (non-blocking).
        errors.append(
            ValidationErrorDetail(
                code="DOMAIN_INSUFFICIENT_SIGNALS",
                message=(
                    "API shows weak e-invoicing signals. Consider aligning inputs/outputs "
                    "with EN 16931 / UBL 2.1 (e.g., invoiceNumber, issueDate, supplier, "
                    "buyer, taxTotal, totalAmount)."
                ),
                path=None,
                severity="warning",
                stage=stage,
            )
        )
    else:
        errors.append(
            ValidationErrorDetail(
                code="DOMAIN_NOT_EINVOICING",
                message=(
                    "API does not meet e-invoicing domain rules: it lacks core invoice "
                    "fields (e.g., invoiceNumber, taxTotal, supplier/buyer) and does not "
                    "reference a recognized standard (UBL / PEPPOL / EN 16931). "
                    "Keyword mentions alone are not sufficient."
                ),
                path=None,
                stage=stage,
            )
        )

    # FR-3 metadata: capability_category validity + consistency with operations.
    errors.extend(_check_capability_category(request, haystack))

    status = ValidationStatus.FAIL if _has_blocking(errors) else ValidationStatus.PASS
    return status, errors


def _run_security_stage(
    request: ValidationRequest,
    parsed_spec: Optional[object],
) -> Tuple[ValidationStatus, List[ValidationErrorDetail]]:
    """
    FR-6: Security and authentication metadata validation.
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.SECURITY_VALIDATION

    # Rule 1: Forms must have legal auth_method.
    allowed = {"OAUTH2", "API_KEY", "BASIC", "MTLS"}

    raw_auth = (request.auth_method or "").strip().upper()
    normalized_auth = (
        raw_auth.replace(" ", "_")
        .replace("-", "_")
        .replace("OAUTH_2.0", "OAUTH2")
        .replace("OAUTH2.0", "OAUTH2")
    )

    if not normalized_auth:
        errors.append(
            ValidationErrorDetail(
                code="SECURITY_AUTH_METHOD_MISSING",
                message="Authentication method is required in submission metadata.",
                path="auth_method",
                stage=stage,
            )
        )
    elif normalized_auth not in allowed:
        errors.append(
            ValidationErrorDetail(
                code="SECURITY_AUTH_METHOD_UNSUPPORTED",
                message=(
                    f"Authentication method '{request.auth_method}' is not accepted. "
                    f"Allowed: OAuth2, API Key, Basic, mTLS."
                ),
                path="auth_method",
                stage=stage,
            )
        )

    # Rule 2&3: REST checks ensure that securitySchemes and metadata are consistent.
    if request.protocol == Protocol.REST:
        if not isinstance(parsed_spec, dict):
            errors.append(
                ValidationErrorDetail(
                    code="SECURITY_SPEC_UNAVAILABLE",
                    message="Parsed OpenAPI document is unavailable for security validation.",
                    path=None,
                    stage=stage,
                )
            )
        else:
            components = parsed_spec.get("components") or {}
            schemes = components.get("securitySchemes") or {}

            if not schemes:
                errors.append(
                    ValidationErrorDetail(
                        code="SECURITY_SCHEME_MISSING",
                        message="OpenAPI document must declare components.securitySchemes.",
                        path="components.securitySchemes",
                        stage=stage,
                    )
                )
            else:
                type_to_auth = {
                    "oauth2": "OAUTH2",
                    "apiKey": "API_KEY",
                    "mutualTLS": "MTLS",
                }

                scheme_auths = set()
                for _scheme_name, scheme_body in schemes.items():
                    if not isinstance(scheme_body, dict):
                        continue

                    scheme_type = (scheme_body.get("type") or "").strip()
                    mapped = type_to_auth.get(scheme_type)

                    # OpenAPI Basic Auth is usually type=http + scheme=basic
                    if scheme_type == "http":
                        http_scheme = (scheme_body.get("scheme") or "").strip().lower()
                        if http_scheme == "basic":
                            mapped = "BASIC"

                    if mapped:
                        scheme_auths.add(mapped)

                if normalized_auth and normalized_auth in allowed:
                    if normalized_auth not in scheme_auths:
                        errors.append(
                            ValidationErrorDetail(
                                code="SECURITY_AUTH_METADATA_MISMATCH",
                                message=(
                                    f"Metadata auth_method '{request.auth_method}' does not "
                                    f"match any securitySchemes type in the OpenAPI document."
                                ),
                                path="components.securitySchemes",
                                stage=stage,
                            )
                        )

                # Document should actually apply security somewhere
                root_security = parsed_spec.get("security")
                has_op_security = False
                paths = parsed_spec.get("paths") or {}
                if isinstance(paths, dict):
                    for _path, path_item in paths.items():
                        if not isinstance(path_item, dict):
                            continue
                        for _method, operation in path_item.items():
                            if isinstance(operation, dict) and operation.get("security"):
                                has_op_security = True
                                break
                        if has_op_security:
                            break

                if not root_security and not has_op_security:
                    errors.append(
                        ValidationErrorDetail(
                            code="SECURITY_REQUIREMENT_MISSING",
                            message=(
                                "OpenAPI document declares securitySchemes but does not "
                                "apply security at root or operation level."
                            ),
                            path="security",
                            stage=stage,
                        )
                    )

    elif request.protocol == Protocol.SOAP:
        # Sprint 2 simplification: WSDL security is complex; Rule 1 is enough for now.
        pass

    status = ValidationStatus.PASS if not errors else ValidationStatus.FAIL
    return status, errors


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
