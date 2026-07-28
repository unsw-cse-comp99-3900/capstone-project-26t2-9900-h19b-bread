"""FR-6 security and authentication metadata validation."""
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


def _local_tag(tag: object) -> str:
    """Return the local name of an ElementTree tag, dropping any '{ns}' prefix."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[-1]
    return tag if isinstance(tag, str) else ""


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

