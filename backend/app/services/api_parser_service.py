import json
from typing import Any, Tuple, List
import yaml
from app.schemas.validation_schema import ValidationErrorDetail
import xml.etree.ElementTree as ET


def parse_openapi(spec_content: str) -> Tuple[Any, List[ValidationErrorDetail]]:
    """
    Parse OpenAPI YAML or JSON string into a Python dict.
    Return a tuple of (parsed_dict, errors).
    """
    errors: List[ValidationErrorDetail] = []
    stripped = spec_content.strip()

    try:
        if stripped.startswith("{"):
            data = json.loads(spec_content)
        else:
            data = yaml.safe_load(spec_content)
    except json.JSONDecodeError as exc:
        return None, [
            ValidationErrorDetail(
                code="PARSE_ERROR",
                message=f"Invalid JSON: {exc}",
                path=None,
            )
        ]
    except yaml.YAMLError as exc:
        return None, [
            ValidationErrorDetail(
                code="PARSE_ERROR",
                message=f"Invalid YAML: {exc}",
                path=None,
            )
        ]

    if not isinstance(data, dict):
        return None, [
            ValidationErrorDetail(
                code="PARSE_ERROR",
                message="OpenAPI spec must be a YAML/JSON object.",
                path=None,
            )
        ]

    return data, errors


def parse_wsdl(spec_content: str) -> Tuple[Any, List[ValidationErrorDetail]]:
    """
    Parse WSDL XML string.
    Return a tuple of (xml_root, errors).
    """
    try:
        root = ET.fromstring(spec_content)
    except ET.ParseError as exc:
        return None, [
            ValidationErrorDetail(
                code="WSDL_MALFORMED_XML",
                message=f"Invalid XML: {exc}",
                path=None,
            )
        ]

    # Strip XML namespace to get local tag name
    tag = root.tag.split("}")[-1]
    if tag != "definitions":
        return None, [
            ValidationErrorDetail(
                code="WSDL_INVALID_STRUCTURE",
                message="SOAP spec root element must be <definitions>.",
                path="root",
            )
        ]

    return root, []