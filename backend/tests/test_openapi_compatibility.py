import json

import pytest

from app.schemas.validation_schema import Protocol, ValidationRequest, ValidationStatus
from app.services.validation_service import validate_specification


def _request(spec: dict) -> ValidationRequest:
    return ValidationRequest(
        protocol=Protocol.REST,
        spec_content=json.dumps(spec),
        auth_method="API Key",
        endpoint_url="https://api.example.com",
        input_format="JSON",
        output_format="JSON",
        capability_category="Invoice Creation",
    )


def _valid_invoice_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Invoice Submission API",
            "version": "1.0.0",
            "description": "Submit UBL invoices for e-invoicing.",
        },
        "servers": [{"url": "https://api.example.com"}],
        "components": {
            "securitySchemes": {
                "ApiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            }
        },
        "paths": {
            "/invoices": {
                "post": {
                    "operationId": "submitInvoice",
                    "security": [{"ApiKey": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "invoiceNumber": {"type": "string"},
                                        "issueDate": {"type": "string"},
                                        "supplier": {"type": "object"},
                                        "buyer": {"type": "object"},
                                        "taxTotal": {"type": "number"},
                                        "totalAmount": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "accepted",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def test_legacy_null_default_is_warning_and_does_not_mutate_raw_spec():
    spec = _valid_invoice_spec()
    operation = spec["paths"]["/invoices"]["post"]
    operation["parameters"] = [
        {
            "name": "issued",
            "in": "query",
            "required": False,
            "schema": {"type": "boolean", "default": None},
        }
    ]

    result = validate_specification(_request(spec))

    assert result.overall_status == ValidationStatus.PASS
    assert any(
        error.code == "OPENAPI_LEGACY_NULL_DEFAULT_IGNORED"
        and error.severity == "warning"
        for error in result.errors
    )
    assert operation["parameters"][0]["schema"]["default"] is None


def test_non_null_structural_error_is_not_ignored():
    spec = _valid_invoice_spec()
    spec["paths"]["/invoices"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["properties"]["totalAmount"]["type"] = "not-a-json-schema-type"

    result = validate_specification(_request(spec))

    assert result.overall_status == ValidationStatus.FAIL
    assert any(error.code == "OPENAPI_INVALID_STRUCTURE" for error in result.errors)


@pytest.mark.parametrize(
    ("schema_type", "invalid_default", "expected_message"),
    [
        ("number", "nulll", "'nulll' is not of type 'number'"),
        ("boolean", "not-a-boolean", "'not-a-boolean' is not of type 'boolean'"),
        ("string", [], "[] is not of type 'string'"),
    ],
)
def test_reports_remaining_default_type_error_after_ignoring_legacy_null_defaults(
    schema_type: str, invalid_default: object, expected_message: str
):
    spec = _valid_invoice_spec()
    schemas = spec["components"].setdefault("schemas", {})
    schemas["LegacyDefaults"] = {"type": "object", "properties": {}}
    properties = schemas["LegacyDefaults"]["properties"]
    properties["optionalItems"] = {"type": "array", "default": "null"}
    properties["invalidDefault"] = {
        "type": schema_type,
        "default": invalid_default,
    }

    result = validate_specification(_request(spec))

    structure_error = next(
        error for error in result.errors if error.code == "OPENAPI_INVALID_STRUCTURE"
    )
    assert result.overall_status == ValidationStatus.FAIL
    assert expected_message in structure_error.message
    assert "'null' is not of type 'array'" not in structure_error.message


def test_reports_remaining_schema_error_after_ignoring_legacy_null_defaults():
    spec = _valid_invoice_spec()
    schemas = spec["components"].setdefault("schemas", {})
    schemas["LegacyDefaults"] = {
        "type": "object",
        "properties": {"optionalItems": {"type": "array", "default": "null"}},
    }
    schemas["InvalidSchema"] = {"type": "not-a-json-schema-type"}

    result = validate_specification(_request(spec))

    structure_error = next(
        error for error in result.errors if error.code == "OPENAPI_INVALID_STRUCTURE"
    )
    assert result.overall_status == ValidationStatus.FAIL
    assert "not-a-json-schema-type" in structure_error.message
    assert "'null' is not of type 'array'" not in structure_error.message
