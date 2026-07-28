"""FR-5 e-invoicing domain compliance (+ capability_category metadata)."""
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from app.schemas.validation_schema import (
    Protocol,
    ValidationErrorDetail,
    ValidationRequest,
    ValidationStage,
    ValidationStatus,
)


def _has_blocking(errors: List[ValidationErrorDetail]) -> bool:
    """True if any error is blocking (severity != 'warning')."""
    return any(error.severity != "warning" for error in errors)


_CAPABILITY_CATEGORIES = {
    "invoice creation": ("creat", "submit", "issue", "generat"),
    "validation": ("validat", "verif", "check", "complian"),
    "transmission": ("transmi", "send", "deliver", "exchange", "dispatch"),
    "archiving": ("archiv", "store", "retention"),
}


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

