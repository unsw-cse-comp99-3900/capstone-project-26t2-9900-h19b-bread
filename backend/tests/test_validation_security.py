"""
Unit tests for FR-6 (security and authentication metadata validation).

Exercises app.services.validation_service._run_security_stage:
- Rule 1: submission auth_method must be present and one of the accepted methods.
- Rule 2: OpenAPI must declare components.securitySchemes.
- Rule 3: auth_method must be consistent with a declared scheme, and the
  document must actually apply security somewhere.
"""

from app.schemas.validation_schema import (
    Protocol,
    ValidationRequest,
    ValidationStage,
    ValidationStatus,
)
from app.services.api_parser_service import parse_wsdl
from app.services.validation_service import _run_security_stage


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _security(parsed_spec, auth_method="OAuth2", protocol=Protocol.REST):
    request = ValidationRequest(
        protocol=protocol,
        spec_content="{}",
        auth_method=auth_method,
    )
    return _run_security_stage(request, parsed_spec)


def _spec(schemes=None, root_security=None, op_security=None) -> dict:
    """Build a parsed OpenAPI dict with optional securitySchemes / security usage."""
    operation = {"operationId": "op", "responses": {"200": {"description": "ok"}}}
    if op_security is not None:
        operation["security"] = op_security

    spec = {
        "openapi": "3.0.3",
        "info": {"title": "API", "version": "1.0.0"},
        "paths": {"/x": {"get": operation}},
    }
    if schemes is not None:
        spec["components"] = {"securitySchemes": schemes}
    if root_security is not None:
        spec["security"] = root_security
    return spec


def _codes(errors):
    return [e.code for e in errors if e.stage == ValidationStage.SECURITY_VALIDATION]


# A fully valid OAuth2 spec used as the "happy path" baseline.
def _valid_oauth2_spec() -> dict:
    return _spec(
        schemes={
            "OAuth2": {
                "type": "oauth2",
                "flows": {
                    "clientCredentials": {
                        "tokenUrl": "https://auth.example.com/token",
                        "scopes": {"invoices:write": "write"},
                    }
                },
            }
        },
        op_security=[{"OAuth2": ["invoices:write"]}],
    )


# --------------------------------------------------------------------------- #
# Rule 1: auth_method presence / legality
# --------------------------------------------------------------------------- #
def test_auth_method_missing_fails():
    status, errors = _security(_valid_oauth2_spec(), auth_method="")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_AUTH_METHOD_MISSING" in _codes(errors)


def test_auth_method_unsupported_fails():
    status, errors = _security(_valid_oauth2_spec(), auth_method="Digest")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_AUTH_METHOD_UNSUPPORTED" in _codes(errors)


def test_auth_method_aliases_are_normalized():
    """'OAuth 2.0' should normalize to OAUTH2 and be accepted."""
    status, errors = _security(_valid_oauth2_spec(), auth_method="OAuth 2.0")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


# --------------------------------------------------------------------------- #
# Rule 2: securitySchemes must be declared
# --------------------------------------------------------------------------- #
def test_missing_security_schemes_fails():
    status, errors = _security(_spec(schemes=None), auth_method="OAuth2")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_SCHEME_MISSING" in _codes(errors)


# --------------------------------------------------------------------------- #
# Rule 3: consistency between auth_method and declared scheme + applied security
# --------------------------------------------------------------------------- #
def test_auth_method_scheme_mismatch_fails():
    """Metadata says OAuth2 but the only scheme is an API key."""
    spec = _spec(
        schemes={"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        op_security=[{"ApiKeyAuth": []}],
    )
    status, errors = _security(spec, auth_method="OAuth2")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_AUTH_METADATA_MISMATCH" in _codes(errors)


def test_scheme_declared_but_security_not_applied_fails():
    spec = _spec(
        schemes={
            "OAuth2": {
                "type": "oauth2",
                "flows": {"clientCredentials": {"tokenUrl": "https://a/t", "scopes": {}}},
            }
        },
        root_security=None,
        op_security=None,
    )
    status, errors = _security(spec, auth_method="OAuth2")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_REQUIREMENT_MISSING" in _codes(errors)


def test_basic_auth_http_scheme_matches():
    spec = _spec(
        schemes={"BasicAuth": {"type": "http", "scheme": "basic"}},
        root_security=[{"BasicAuth": []}],
    )
    status, errors = _security(spec, auth_method="Basic")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_bearer_http_scheme_matches_bearer_metadata():
    spec = _spec(
        schemes={"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
        root_security=[{"BearerAuth": []}],
    )
    status, errors = _security(spec, auth_method="Bearer")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_bearer_http_scheme_matches_jwt_alias():
    spec = _spec(
        schemes={"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
        root_security=[{"BearerAuth": []}],
    )
    status, errors = _security(spec, auth_method="JWT")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_valid_oauth2_spec_passes():
    status, errors = _security(_valid_oauth2_spec(), auth_method="OAuth2")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


# --------------------------------------------------------------------------- #
# REST spec unavailable
# --------------------------------------------------------------------------- #
def test_rest_spec_unavailable_fails():
    status, errors = _security(None, auth_method="OAuth2")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_SPEC_UNAVAILABLE" in _codes(errors)


# --------------------------------------------------------------------------- #
# SOAP / WSDL security
# --------------------------------------------------------------------------- #
def _wsdl_security(policy_body: str = "", location: str = "http://example.com/svc") -> str:
    """Build a minimal WSDL with an optional <wsp:Policy> and a soap:address."""
    policy = f"<wsp:Policy>{policy_body}</wsp:Policy>" if policy_body else ""
    return (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:wsp="http://www.w3.org/ns/ws-policy" '
        'xmlns:sp="http://docs.oasis-open.org/ws-sx/ws-securitypolicy/200702" '
        'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" '
        'targetNamespace="http://example.com/svc">'
        f"{policy}"
        '<service name="S"><port name="P">'
        f'<soap:address location="{location}"/>'
        "</port></service></definitions>"
    )


def _soap_security(wsdl: str, auth_method: str):
    """Parse a WSDL string and run only the security stage against its root."""
    root, _ = parse_wsdl(wsdl)
    request = ValidationRequest(
        protocol=Protocol.SOAP,
        spec_content=wsdl,
        auth_method=auth_method,
    )
    return _run_security_stage(request, root)


def test_soap_no_security_at_all_fails():
    """Decision 1: no policy / token / HTTPS -> hard FAIL."""
    wsdl = _wsdl_security(policy_body="", location="http://example.com/svc")
    status, errors = _soap_security(wsdl, auth_method="Basic")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_REQUIREMENT_MISSING" in _codes(errors)


def test_soap_username_token_matches_basic():
    wsdl = _wsdl_security(policy_body="<sp:UsernameToken/>")
    status, errors = _soap_security(wsdl, auth_method="Basic")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_soap_username_token_mismatch_mtls_fails():
    """Decision: BASIC/MTLS are strongly judged -> mismatch is blocking."""
    wsdl = _wsdl_security(policy_body="<sp:UsernameToken/>")
    status, errors = _soap_security(wsdl, auth_method="mTLS")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_AUTH_METADATA_MISMATCH" in _codes(errors)


def test_soap_https_transport_matches_mtls():
    wsdl = _wsdl_security(policy_body="", location="https://example.com/svc")
    status, errors = _soap_security(wsdl, auth_method="mTLS")
    assert status == ValidationStatus.PASS
    assert _codes(errors) == []


def test_soap_oauth2_unverifiable_warns_but_passes():
    """Decision 2: OAuth2/API Key can't be confirmed from WSDL -> warning, not FAIL."""
    wsdl = _wsdl_security(policy_body="<sp:TransportBinding/>")
    status, errors = _soap_security(wsdl, auth_method="OAuth2")
    assert status == ValidationStatus.PASS
    assert "SECURITY_AUTH_UNVERIFIABLE" in _codes(errors)


def test_soap_missing_auth_fails():
    wsdl = _wsdl_security(policy_body="<sp:UsernameToken/>")
    status, errors = _soap_security(wsdl, auth_method="")
    assert status == ValidationStatus.FAIL
    assert "SECURITY_AUTH_METHOD_MISSING" in _codes(errors)


def test_soap_spec_unavailable_fails():
    status, errors = _security(None, auth_method="OAuth2", protocol=Protocol.SOAP)
    assert status == ValidationStatus.FAIL
    assert "SECURITY_SPEC_UNAVAILABLE" in _codes(errors)
