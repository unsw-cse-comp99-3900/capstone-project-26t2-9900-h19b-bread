"""
Unit tests for FR-5 (e-invoicing domain compliance validation).

Covers the scoring model and the "strong >= 1 OR standard" hard gate in
app.services.validation_service._run_domain_stage, plus its behaviour inside
the full validate_specification pipeline.
"""

import json

from app.schemas.validation_schema import (
    Protocol,
    ValidationRequest,
    ValidationStage,
    ValidationStatus,
)
from app.services.validation_service import (
    _run_domain_stage,
    validate_specification,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _req(spec_content: str = "{}", auth_method: str = "OAuth2") -> ValidationRequest:
    return ValidationRequest(
        protocol=Protocol.REST,
        spec_content=spec_content,
        auth_method=auth_method,
    )


def _domain(parsed_spec, protocol: Protocol = Protocol.REST):
    """Run only the domain stage against an already-parsed spec dict."""
    request = ValidationRequest(
        protocol=protocol,
        spec_content="{}",
        auth_method="OAuth2",
    )
    return _run_domain_stage(request, parsed_spec)


def _spec(title: str, description: str, properties: dict) -> dict:
    """A minimal but structurally valid OpenAPI doc with one inline response schema."""
    return {
        "openapi": "3.0.3",
        "info": {"title": title, "version": "1.0.0", "description": description},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "op",
                    "summary": description,
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": properties,
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def _codes(errors, stage=ValidationStage.DOMAIN_COMPLIANCE_VALIDATION):
    return [e.code for e in errors if e.stage == stage]


# --------------------------------------------------------------------------- #
# Domain stage: PASS cases
# --------------------------------------------------------------------------- #
def test_real_invoice_components_schema_passes():
    spec = _spec(
        "E-Invoice Submission API",
        "Accepts UBL 2.1 electronic invoices",
        {
            "invoiceNumber": {"type": "string"},
            "issueDate": {"type": "string"},
            "supplier": {"type": "object"},
            "buyer": {"type": "object"},
            "taxTotal": {"type": "number"},
            "totalAmount": {"type": "number"},
        },
    )
    status, errors = _domain(spec)
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_inline_invoice_without_components_passes():
    """Fields live only in an inline path schema (no components.schemas)."""
    spec = _spec(
        "Invoice API",
        "submit invoices",
        {
            "invoiceNumber": {"type": "string"},
            "supplier": {"type": "object"},
            "buyer": {"type": "object"},
            "taxTotal": {"type": "number"},
        },
    )
    status, errors = _domain(spec)
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_strong_zero_but_standard_reference_passes_with_warning():
    """No recognizable invoice fields, but the spec references UBL -> eligible."""
    spec = _spec(
        "Document Exchange",
        "Handles UBL 2.1 documents",
        {"docRef": {"type": "string"}},
    )
    status, errors = _domain(spec)
    assert status == ValidationStatus.PASS
    assert "DOMAIN_INSUFFICIENT_SIGNALS" in _codes(errors)


# --------------------------------------------------------------------------- #
# Domain stage: FAIL cases
# --------------------------------------------------------------------------- #
def test_keyword_only_fake_fails():
    """invoice/tax/billing words in text, but fields are unrelated -> hard gate blocks it."""
    spec = _spec(
        "Invoice Tax Billing Manager",
        "manage invoice tax billing vat records",
        {
            "fineId": {"type": "string"},
            "bookId": {"type": "string"},
            "borrower": {"type": "string"},
        },
    )
    status, errors = _domain(spec)
    assert status == ValidationStatus.FAIL
    assert "DOMAIN_NOT_EINVOICING" in _codes(errors)


def test_non_invoice_api_fails():
    spec = _spec(
        "Weather API",
        "current weather",
        {"temperature": {"type": "number"}, "city": {"type": "string"}},
    )
    status, errors = _domain(spec)
    assert status == ValidationStatus.FAIL
    assert "DOMAIN_NOT_EINVOICING" in _codes(errors)


def test_parsed_spec_unavailable_fails():
    status, errors = _domain(None)
    assert status == ValidationStatus.FAIL
    assert "DOMAIN_SPEC_UNAVAILABLE" in _codes(errors)


# --------------------------------------------------------------------------- #
# Domain stage: SOAP is skipped in Sprint 2
# --------------------------------------------------------------------------- #
def test_soap_is_skipped_and_passes():
    status, errors = _domain(object(), protocol=Protocol.SOAP)
    assert status == ValidationStatus.PASS
    assert errors == []


# --------------------------------------------------------------------------- #
# Full pipeline behaviour
# --------------------------------------------------------------------------- #
def test_pipeline_marks_domain_not_run_when_spec_invalid():
    """A structurally invalid spec fails FR-4, so FR-5/FR-6 must be not_run."""
    invalid = json.dumps({"openapi": "3.0.3", "info": {"title": "x"}})  # missing version/paths
    resp = validate_specification(_req(invalid))
    stage_status = {s.stage: s.status for s in resp.stages}
    assert stage_status[ValidationStage.SPECIFICATION_VALIDATION] == ValidationStatus.FAIL
    assert stage_status[ValidationStage.DOMAIN_COMPLIANCE_VALIDATION] == ValidationStatus.NOT_RUN


def test_pipeline_domain_pass_for_valid_invoice():
    spec = json.dumps(
        _spec(
            "E-Invoice API",
            "Submit UBL invoices",
            {
                "invoiceNumber": {"type": "string"},
                "supplier": {"type": "object"},
                "buyer": {"type": "object"},
                "taxTotal": {"type": "number"},
            },
        )
    )
    resp = validate_specification(_req(spec))
    stage_status = {s.stage: s.status for s in resp.stages}
    assert stage_status[ValidationStage.SPECIFICATION_VALIDATION] == ValidationStatus.PASS
    assert stage_status[ValidationStage.DOMAIN_COMPLIANCE_VALIDATION] == ValidationStatus.PASS
