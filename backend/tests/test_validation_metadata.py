"""
Unit tests for FR-3 metadata-consistency validation (broad "metadata validation").

These checks verify that submission form metadata is consistent with the actual
specification content. Following the 3-stage architecture, the checks are folded
into existing stages:
  - protocol / endpoint_url / input+output format  -> specification stage (FR-4)
  - capability_category                            -> domain stage (FR-5)
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
    _run_specification_stage,
    validate_specification,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _invoice_spec(**extra) -> dict:
    """A valid e-invoicing OpenAPI doc with servers + JSON media types."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "E-Invoice API", "version": "1.0.0", "description": "Submit UBL invoices"},
        "servers": [{"url": "https://api.einvoice.example.com/v1"}],
        "paths": {
            "/invoices": {
                "post": {
                    "operationId": "submitInvoice",
                    "summary": "Submit a new invoice",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "invoiceNumber": {"type": "string"},
                                        "supplier": {"type": "object"},
                                        "buyer": {"type": "object"},
                                        "taxTotal": {"type": "number"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "ok",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            }
        },
    }
    spec.update(extra)
    return spec


def _req(spec_dict, **meta) -> ValidationRequest:
    return ValidationRequest(
        protocol=meta.pop("protocol", Protocol.REST),
        spec_content=json.dumps(spec_dict) if isinstance(spec_dict, dict) else spec_dict,
        auth_method=meta.pop("auth_method", "OAuth2"),
        **meta,
    )


def _spec_codes(errors):
    return [e.code for e in errors if e.stage == ValidationStage.SPECIFICATION_VALIDATION]


def _domain_codes(errors):
    return [e.code for e in errors if e.stage == ValidationStage.DOMAIN_COMPLIANCE_VALIDATION]


# --------------------------------------------------------------------------- #
# protocol <-> spec type (blocking, specification stage)
# --------------------------------------------------------------------------- #
def test_rest_declared_but_xml_content_fails():
    request = _req("<definitions>...</definitions>", protocol=Protocol.REST)
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.FAIL
    assert "METADATA_PROTOCOL_SPEC_MISMATCH" in _spec_codes(errors)


def test_soap_declared_but_json_content_fails():
    request = _req(_invoice_spec(), protocol=Protocol.SOAP)
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.FAIL
    assert "METADATA_PROTOCOL_SPEC_MISMATCH" in _spec_codes(errors)


# --------------------------------------------------------------------------- #
# endpoint_url <-> servers (warning, non-blocking)
# --------------------------------------------------------------------------- #
def test_endpoint_matches_servers_no_warning():
    request = _req(_invoice_spec(), endpoint_url="https://api.einvoice.example.com/v1/invoices")
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_ENDPOINT_MISMATCH" not in _spec_codes(errors)


def test_endpoint_mismatch_warns_but_passes():
    request = _req(_invoice_spec(), endpoint_url="https://evil.example.org/api")
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS  # warning does not block
    assert "METADATA_ENDPOINT_MISMATCH" in _spec_codes(errors)


def test_endpoint_unverifiable_when_no_servers():
    request = _req(_invoice_spec(servers=[]), endpoint_url="https://api.example.com")
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_ENDPOINT_UNVERIFIABLE" in _spec_codes(errors)


# --------------------------------------------------------------------------- #
# input/output format <-> media types (warning)
# --------------------------------------------------------------------------- #
def test_format_mismatch_warns():
    request = _req(_invoice_spec(), input_format="XML", output_format="XML")
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_INPUT_FORMAT_MISMATCH" in _spec_codes(errors)


def test_format_match_no_warning():
    request = _req(_invoice_spec(), input_format="JSON", output_format="JSON")
    status, errors, _ = _run_specification_stage(request)
    assert "METADATA_INPUT_FORMAT_MISMATCH" not in _spec_codes(errors)
    assert "METADATA_OUTPUT_FORMAT_MISMATCH" not in _spec_codes(errors)


# --------------------------------------------------------------------------- #
# capability_category (domain stage): invalid -> blocking, inconsistent -> warning
# --------------------------------------------------------------------------- #
def test_capability_valid_and_consistent_passes():
    request = _req(_invoice_spec(), capability_category="invoice creation")
    status, errors = _run_domain_stage(request, _invoice_spec())
    assert status == ValidationStatus.PASS
    assert _domain_codes(errors) == []


def test_capability_invalid_fails():
    request = _req(_invoice_spec(), capability_category="weather forecasting")
    status, errors = _run_domain_stage(request, _invoice_spec())
    assert status == ValidationStatus.FAIL
    assert "METADATA_CAPABILITY_INVALID" in _domain_codes(errors)


def test_capability_inconsistent_warns_but_passes():
    """Declared 'archiving' but the only operation is a submit -> warning."""
    request = _req(_invoice_spec(), capability_category="archiving")
    status, errors = _run_domain_stage(request, _invoice_spec())
    assert status == ValidationStatus.PASS
    assert "METADATA_CAPABILITY_INCONSISTENT" in _domain_codes(errors)


# --------------------------------------------------------------------------- #
# SOAP metadata consistency: endpoint_url <-> soap:address, format <-> XML
# --------------------------------------------------------------------------- #
def _soap_invoice_wsdl(location: str = "http://svc.example.com/invoice") -> str:
    return (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" '
        'targetNamespace="http://svc.example.com/invoice">'
        '<types><xsd:schema targetNamespace="http://svc.example.com/invoice">'
        '<xsd:element name="invoiceNumber" type="xsd:string"/>'
        '<xsd:element name="supplier" type="xsd:string"/>'
        '<xsd:element name="buyer" type="xsd:string"/>'
        '<xsd:element name="taxTotal" type="xsd:decimal"/>'
        "</xsd:schema></types>"
        '<portType name="InvoicePort"><operation name="SubmitInvoice"/></portType>'
        '<service name="InvoiceService"><port name="InvoicePortPort">'
        f'<soap:address location="{location}"/>'
        "</port></service></definitions>"
    )


def _soap_wsdl_no_address() -> str:
    return (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="http://svc.example.com/invoice">'
        '<types><xsd:schema>'
        '<xsd:element name="invoiceNumber" type="xsd:string"/>'
        "</xsd:schema></types>"
        '<portType name="P"><operation name="SubmitInvoice"/></portType>'
        "</definitions>"
    )


def test_soap_endpoint_matches_address_no_warning():
    request = _req(
        _soap_invoice_wsdl(),
        protocol=Protocol.SOAP,
        endpoint_url="http://svc.example.com/invoice",
    )
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_ENDPOINT_MISMATCH" not in _spec_codes(errors)


def test_soap_endpoint_mismatch_warns_but_passes():
    request = _req(
        _soap_invoice_wsdl(),
        protocol=Protocol.SOAP,
        endpoint_url="http://evil.example.org/x",
    )
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_ENDPOINT_MISMATCH" in _spec_codes(errors)


def test_soap_endpoint_unverifiable_when_no_address():
    request = _req(
        _soap_wsdl_no_address(),
        protocol=Protocol.SOAP,
        endpoint_url="http://svc.example.com/invoice",
    )
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_ENDPOINT_UNVERIFIABLE" in _spec_codes(errors)


def test_soap_json_format_mismatch_warns():
    """SOAP payloads are XML, so declaring JSON is inconsistent -> warning."""
    request = _req(
        _soap_invoice_wsdl(),
        protocol=Protocol.SOAP,
        input_format="JSON",
        output_format="JSON",
    )
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "METADATA_INPUT_FORMAT_MISMATCH" in _spec_codes(errors)


def test_soap_xml_ubl_format_no_warning():
    request = _req(
        _soap_invoice_wsdl(),
        protocol=Protocol.SOAP,
        input_format="XML",
        output_format="UBL",
    )
    status, errors, _ = _run_specification_stage(request)
    assert "METADATA_INPUT_FORMAT_MISMATCH" not in _spec_codes(errors)
    assert "METADATA_OUTPUT_FORMAT_MISMATCH" not in _spec_codes(errors)


# --------------------------------------------------------------------------- #
# SOAP structural completeness (FR-4): portType / operation required
# --------------------------------------------------------------------------- #
def test_soap_missing_porttype_fails():
    wsdl = (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'targetNamespace="http://svc.example.com/invoice"><types/></definitions>'
    )
    request = _req(wsdl, protocol=Protocol.SOAP)
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.FAIL
    assert "WSDL_NO_PORTTYPE" in _spec_codes(errors)


def test_soap_complete_wsdl_passes_structure():
    request = _req(_soap_invoice_wsdl(), protocol=Protocol.SOAP)
    status, errors, _ = _run_specification_stage(request)
    assert status == ValidationStatus.PASS
    assert "WSDL_NO_PORTTYPE" not in _spec_codes(errors)
    assert "WSDL_NO_OPERATION" not in _spec_codes(errors)


def _soap_full_invoice_wsdl() -> str:
    """A complete + secure e-invoicing WSDL that should pass every stage."""
    return (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" '
        'targetNamespace="http://svc.example.com/invoice">'
        '<types><xsd:schema targetNamespace="http://svc.example.com/invoice">'
        '<xsd:element name="invoiceNumber" type="xsd:string"/>'
        '<xsd:element name="issueDate" type="xsd:date"/>'
        '<xsd:element name="supplier" type="xsd:string"/>'
        '<xsd:element name="buyer" type="xsd:string"/>'
        '<xsd:element name="taxTotal" type="xsd:decimal"/>'
        '<xsd:element name="totalAmount" type="xsd:decimal"/>'
        "</xsd:schema></types>"
        '<portType name="InvoicePort"><operation name="SubmitInvoice"/></portType>'
        '<service name="InvoiceService"><port name="P">'
        '<soap:address location="https://svc.example.com/invoice"/>'
        "</port></service></definitions>"
    )


def test_pipeline_soap_invoice_all_stages_pass():
    """End-to-end SOAP: FR-4 (structure) + FR-5 (domain) + FR-6 (security) all pass."""
    request = _req(_soap_full_invoice_wsdl(), protocol=Protocol.SOAP, auth_method="mTLS")
    resp = validate_specification(request)
    stage_status = {s.stage: s.status for s in resp.stages}
    assert stage_status[ValidationStage.SPECIFICATION_VALIDATION] == ValidationStatus.PASS
    assert stage_status[ValidationStage.DOMAIN_COMPLIANCE_VALIDATION] == ValidationStatus.PASS
    assert stage_status[ValidationStage.SECURITY_VALIDATION] == ValidationStatus.PASS
    assert resp.overall_status == ValidationStatus.PASS


# --------------------------------------------------------------------------- #
# Full pipeline: metadata errors surface end-to-end
# --------------------------------------------------------------------------- #
def test_pipeline_protocol_mismatch_marks_later_stages_not_run():
    request = _req("<definitions></definitions>", protocol=Protocol.REST)
    resp = validate_specification(request)
    stage_status = {s.stage: s.status for s in resp.stages}
    assert stage_status[ValidationStage.SPECIFICATION_VALIDATION] == ValidationStatus.FAIL
    assert stage_status[ValidationStage.DOMAIN_COMPLIANCE_VALIDATION] == ValidationStatus.NOT_RUN
    assert any(e.code == "METADATA_PROTOCOL_SPEC_MISMATCH" for e in resp.errors)


def test_pipeline_valid_invoice_with_full_metadata_passes():
    request = _req(
        _invoice_spec(),
        endpoint_url="https://api.einvoice.example.com/v1",
        input_format="JSON",
        output_format="JSON",
        capability_category="invoice creation",
    )
    resp = validate_specification(request)
    stage_status = {s.stage: s.status for s in resp.stages}
    assert stage_status[ValidationStage.SPECIFICATION_VALIDATION] == ValidationStatus.PASS
    assert stage_status[ValidationStage.DOMAIN_COMPLIANCE_VALIDATION] == ValidationStatus.PASS
