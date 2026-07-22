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

_DOMAIN_VALIDATION_MARKERS = (
    "schematron",
    "validate",
    "validation",
    "validator",
)

_DOMAIN_FILE_PAYLOAD_MARKERS = (
    "file",
    "filename",
    "content",
    "checksum",
    "xmlfile",
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


def _collect_domain_text(
    node: object,
    parts: list,
    depth: int = 0,
) -> None:
    """Collect descriptive OpenAPI text that can carry domain standards."""
    if depth > 40 or node is None:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"title", "description", "summary", "operationId", "name", "default"}:
                parts.append(str(value))
            elif key == "enum" and isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif key not in _SCHEMA_SKIP_KEYS:
                _collect_domain_text(value, parts, depth + 1)

    elif isinstance(node, list):
        for entry in node:
            _collect_domain_text(entry, parts, depth + 1)


def _extract_rest_domain_signals(parsed_spec: dict) -> Tuple[str, set]:
    """
    Extract FR-5 domain signals from a parsed OpenAPI document.

    Returns (haystack, normalized_fields):
      - haystack: lowercased text blob (title/description/tags/paths/operations),
        used for weak-keyword and standard-marker matching.
      - normalized_fields: normalized schema property names collected from both
        components.schemas and inline request/response schemas under paths.

    This is the REST-specific "signal collection" half of the domain stage; the
    scoring/decision half (_evaluate_domain_signals) is protocol-agnostic so SOAP
    can feed the same shape of signals in a later step.
    """
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
                    _collect_domain_text(operation.get("parameters"), haystack_parts)
                    _collect_domain_text(operation.get("requestBody"), haystack_parts)
                    _collect_domain_text(operation.get("responses"), haystack_parts)

    components = parsed_spec.get("components") or {}
    _collect_domain_text(components.get("schemas"), haystack_parts)

    haystack = " ".join(haystack_parts).lower()

    # --- Signal 2: schema property names -> core invoice field categories ---
    # Collect from both reusable components.schemas AND inline request/response
    # schemas declared under paths, so specs that inline their models are covered.
    field_names: set = set()
    _collect_property_names(components.get("schemas"), field_names)
    _collect_property_names(parsed_spec.get("paths"), field_names)

    normalized_fields = {_normalize_field_name(name) for name in field_names}
    return haystack, normalized_fields


def _evaluate_domain_signals(
    haystack: str,
    normalized_fields: set,
    stage: ValidationStage,
) -> List[ValidationErrorDetail]:
    """
    Apply the FR-5 scoring model + hard gate to already-extracted signals.

    Scoring model (aligned with EN 16931 / UBL 2.1 / PEPPOL BIS Billing 3.0):
        strong   = number of distinct core invoice field categories matched (0..9)
        standard = +2 if the spec references a recognized e-invoicing standard
        keyword  = number of weak textual keywords matched, capped at +2
        score    = strong + standard + min(keyword, 2)

    Hard gate:
        A submission can only PASS if it shows *structural* or *standard* evidence,
        i.e. strong >= 1 OR a recognized standard is referenced. This blocks
        "keyword-only" fakes (invoice/tax words in text but no invoice fields).

    Decision (returns the domain-signal errors, empty when strong evidence):
        not (strong >= 1 or standard)   -> DOMAIN_NOT_EINVOICING (blocking)
        eligible and score >= 4         -> no error
        eligible and 2 <= score < 4     -> DOMAIN_INSUFFICIENT_SIGNALS (warning)
        eligible and score < 2          -> DOMAIN_NOT_EINVOICING (blocking)

    Protocol-agnostic: both REST and SOAP feed (haystack, normalized_fields) here.
    """
    errors: List[ValidationErrorDetail] = []

    matched_categories = set()
    for category, fragments in _DOMAIN_FIELD_CATEGORIES.items():
        for fragment in fragments:
            if any(fragment in field for field in normalized_fields):
                matched_categories.add(category)
                break

    strong_score = len(matched_categories)

    standard_matched = any(marker in haystack for marker in _DOMAIN_STANDARD_MARKERS)
    standard_score = 2 if standard_matched else 0
    validation_service_matched = (
        standard_matched
        and any(marker in haystack for marker in _DOMAIN_VALIDATION_MARKERS)
        and any(marker in field for marker in _DOMAIN_FILE_PAYLOAD_MARKERS for field in normalized_fields)
    )

    keyword_hits = sum(1 for keyword in _DOMAIN_KEYWORDS if keyword in haystack)
    keyword_score = min(keyword_hits, 2)

    score = strong_score + standard_score + keyword_score

    # Hard gate: keyword-only evidence can never pass. Passing requires at least
    # one structural invoice field OR an explicit e-invoicing standard reference.
    eligible_to_pass = strong_score >= 1 or standard_matched or validation_service_matched

    if validation_service_matched:
        pass  # e-invoicing validation tools often accept XML/file payloads, not expanded invoice fields.
    elif eligible_to_pass and score >= 4:
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

    return errors


# XSD constructs whose "name" attribute is a real data-field definition.
_SOAP_FIELD_TAGS = frozenset({"element", "attribute", "complexType", "simpleType"})

# WSDL constructs whose "name" attribute is descriptive text (goes to haystack).
_SOAP_TEXT_TAGS = frozenset(
    {"portType", "operation", "message", "service", "port", "binding"}
)


def _local_tag(tag: object) -> str:
    """Return the local name of an ElementTree tag, dropping any '{ns}' prefix."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[-1]
    return tag if isinstance(tag, str) else ""


def _extract_soap_domain_signals(xml_root: "ET.Element") -> Tuple[str, set]:
    """
    Extract FR-5 domain signals from a parsed WSDL document (ElementTree root).

    Returns (haystack, normalized_fields) with the SAME shape as the REST
    extractor, so the shared _evaluate_domain_signals scoring applies unchanged:
      - normalized_fields: names of XSD element/attribute/complexType/simpleType
        declared under <wsdl:types> (the SOAP equivalent of OpenAPI schema props).
      - haystack: portType/operation/service names, <documentation> text, plus
        every XML namespace URI and targetNamespace (this is where UBL / PEPPOL /
        EN 16931 standard markers live in SOAP specs).
    """
    haystack_parts: List[str] = []
    field_names: set = set()
    namespaces: set = set()

    if xml_root is None:
        return "", set()

    root_tns = xml_root.get("targetNamespace")
    if root_tns:
        haystack_parts.append(root_tns)

    for elem in xml_root.iter():
        tag = elem.tag
        # Harvest the namespace URI embedded in the tag ("{uri}local").
        if isinstance(tag, str) and tag.startswith("{"):
            namespaces.add(tag[1:].split("}", 1)[0])
        local = _local_tag(tag)

        name_attr = elem.get("name")
        if name_attr:
            if local in _SOAP_FIELD_TAGS:
                field_names.add(name_attr)
            elif local in _SOAP_TEXT_TAGS:
                haystack_parts.append(name_attr)

        if local == "documentation" and elem.text:
            haystack_parts.append(elem.text)

        nested_tns = elem.get("targetNamespace")
        if nested_tns:
            haystack_parts.append(nested_tns)

    haystack_parts.extend(namespaces)
    haystack = " ".join(haystack_parts).lower()
    normalized_fields = {_normalize_field_name(name) for name in field_names}
    return haystack, normalized_fields


def _run_domain_stage(
    request: ValidationRequest,
    parsed_spec: Optional[object],
) -> Tuple[ValidationStatus, List[ValidationErrorDetail]]:
    """
    FR-5: E-invoicing domain compliance validation.

    Orchestration only: pick the protocol-specific signal extractor, run the
    shared scoring/decision, then add FR-3 capability-category checks.
    Both REST (OpenAPI dict) and SOAP (WSDL ElementTree) produce the same
    (haystack, normalized_fields) shape, so scoring is identical across protocols.
    """
    errors: List[ValidationErrorDetail] = []
    stage = ValidationStage.DOMAIN_COMPLIANCE_VALIDATION

    if request.protocol == Protocol.REST:
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
        haystack, normalized_fields = _extract_rest_domain_signals(parsed_spec)

    elif request.protocol == Protocol.SOAP:
        if not isinstance(parsed_spec, ET.Element):
            errors.append(
                ValidationErrorDetail(
                    code="DOMAIN_SPEC_UNAVAILABLE",
                    message="Parsed WSDL document is unavailable for domain validation.",
                    path=None,
                    stage=stage,
                )
            )
            return ValidationStatus.FAIL, errors
        haystack, normalized_fields = _extract_soap_domain_signals(parsed_spec)

    else:
        return ValidationStatus.PASS, errors

    errors.extend(_evaluate_domain_signals(haystack, normalized_fields, stage))

    # FR-3 metadata: capability_category validity + consistency with operations.
    errors.extend(_check_capability_category(request, haystack))

    status = ValidationStatus.FAIL if _has_blocking(errors) else ValidationStatus.PASS
    return status, errors


def _extract_soap_security_signals(xml_root: "ET.Element") -> Tuple[bool, set]:
    """
    Detect security evidence in a parsed WSDL document (ElementTree root).

    Returns (has_any_security, methods):
      - has_any_security: True if the WSDL shows *any* security intent, i.e. a
        WS-Policy element, a recognized WS-SecurityPolicy token, or an HTTPS
        transport address. Used for the "no security at all" hard gate.
      - methods: the subset of {BASIC, MTLS, OAUTH2} we can positively map from
        the WSDL. API_KEY is intentionally absent: SOAP has no standard place to
        declare it, so it is never positively detectable here.

    Mapping (best-effort, aligned with WS-SecurityPolicy 1.2):
      - UsernameToken                      -> BASIC
      - X509Token / TransportBinding / HTTPS transport -> MTLS (transport/message TLS)
      - IssuedToken / SamlToken            -> OAUTH2 (federated / bearer-style)
    """
    methods: set = set()
    has_policy = False
    https = False

    if xml_root is None:
        return False, methods

    for elem in xml_root.iter():
        local = _local_tag(elem.tag).lower()

        if local == "policy":
            has_policy = True
        elif local == "usernametoken":
            methods.add("BASIC")
        elif local in ("x509token", "transportbinding"):
            methods.add("MTLS")
        elif local in ("issuedtoken", "samltoken"):
            methods.add("OAUTH2")
        elif local == "address":
            location = (elem.get("location") or "").strip().lower()
            if location.startswith("https://"):
                https = True
                methods.add("MTLS")  # transport-level TLS / mTLS evidence

    has_any_security = has_policy or https or bool(methods)
    return has_any_security, methods


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
    allowed = {"OAUTH2", "API_KEY", "BASIC", "MTLS", "TOKEN", "BEARER"}

    raw_auth = (request.auth_method or "").strip().upper()
    normalized_auth = (
        raw_auth.replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("OAUTH_2.0", "OAUTH2")
        .replace("OAUTH2.0", "OAUTH2")
    )
    if normalized_auth in {"JWT", "BEARER_JWT"}:
        normalized_auth = "BEARER"

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
                    f"Allowed: OAuth2, Bearer/JWT, API Key, Basic, mTLS."
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
                        elif http_scheme == "bearer":
                            mapped = "BEARER"

                    if mapped:
                        scheme_auths.add(mapped)
                        if mapped == "BEARER":
                            scheme_auths.add("TOKEN")

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
        if not isinstance(parsed_spec, ET.Element):
            errors.append(
                ValidationErrorDetail(
                    code="SECURITY_SPEC_UNAVAILABLE",
                    message="Parsed WSDL document is unavailable for security validation.",
                    path=None,
                    stage=stage,
                )
            )
        else:
            has_any_security, soap_methods = _extract_soap_security_signals(parsed_spec)

            if not has_any_security:
                # Decision 1: no WS-Policy / token / HTTPS transport at all -> block,
                # mirroring REST's requirement that security be declared in the spec.
                errors.append(
                    ValidationErrorDetail(
                        code="SECURITY_REQUIREMENT_MISSING",
                        message=(
                            "WSDL declares no security: no WS-SecurityPolicy assertions, "
                            "security tokens, or HTTPS transport were found."
                        ),
                        path="wsdl:binding",
                        stage=stage,
                    )
                )
            elif normalized_auth in {"BASIC", "MTLS"}:
                # Strongly detectable in WSDL: require matching evidence (blocking).
                if normalized_auth not in soap_methods:
                    expected = (
                        "UsernameToken"
                        if normalized_auth == "BASIC"
                        else "X509Token / TransportBinding / HTTPS transport"
                    )
                    errors.append(
                        ValidationErrorDetail(
                            code="SECURITY_AUTH_METADATA_MISMATCH",
                            message=(
                                f"Metadata auth_method '{request.auth_method}' is not reflected "
                                f"by the WSDL security policy (expected {expected})."
                            ),
                            path="wsdl:binding",
                            stage=stage,
                        )
                    )
            elif normalized_auth in {"OAUTH2", "API_KEY"}:
                # Decision 2: not reliably declared in WSDL -> warn, don't block.
                if normalized_auth not in soap_methods:
                    errors.append(
                        ValidationErrorDetail(
                            code="SECURITY_AUTH_UNVERIFIABLE",
                            message=(
                                f"Metadata auth_method '{request.auth_method}' cannot be "
                                f"verified from the WSDL: SOAP has no standard place to "
                                f"declare it. Manual confirmation recommended."
                            ),
                            path="wsdl:binding",
                            severity="warning",
                            stage=stage,
                        )
                    )

    status = ValidationStatus.FAIL if _has_blocking(errors) else ValidationStatus.PASS
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
