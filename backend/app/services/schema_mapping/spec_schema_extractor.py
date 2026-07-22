from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any

import yaml

from app.services.schema_mapping.compatibility_engine import normalize_schema

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
XSD_NS = "{http://www.w3.org/2001/XMLSchema}"
logger = logging.getLogger(__name__)


def sync_api_schemas_from_spec(
    cursor,
    *,
    api_id: int,
    version_id: int,
    spec_type: str,
    spec_content: str,
    input_format: str | None,
    output_format: str | None,
) -> None:
    """Extract input/output payload schemas from a saved API specification."""
    from psycopg.types.json import Jsonb

    try:
        extracted_schemas = extract_payload_schemas(
            spec_type=spec_type,
            spec_content=spec_content,
            input_format=input_format,
            output_format=output_format,
        )
    except Exception:
        logger.exception(
            "Failed to extract schema mapping payloads for api_id=%s version_id=%s spec_type=%s",
            api_id,
            version_id,
            spec_type,
        )
        return

    for extracted in extracted_schemas:
        raw_schema = extracted["schema"]
        normalized_schema = normalize_schema(raw_schema)
        cursor.execute(
            """
            INSERT INTO api_schema (
                api_id, version_id, direction, format, source_key,
                source_path, source_method, media_type, status_code,
                raw_schema, normalized_schema, schema_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, 1)
            ON CONFLICT (api_id, version_id, direction, schema_version, source_key)
            DO UPDATE SET
                format = EXCLUDED.format,
                source_path = EXCLUDED.source_path,
                source_method = EXCLUDED.source_method,
                media_type = EXCLUDED.media_type,
                status_code = EXCLUDED.status_code,
                raw_schema = EXCLUDED.raw_schema,
                normalized_schema = EXCLUDED.normalized_schema,
                created_at = CURRENT_TIMESTAMP
            RETURNING schema_id
            """,
            (
                api_id,
                version_id,
                extracted["direction"],
                extracted["format"],
                extracted["source_key"],
                extracted.get("source_path"),
                extracted.get("source_method"),
                extracted.get("media_type"),
                extracted.get("status_code"),
                Jsonb(raw_schema),
                Jsonb(normalized_schema),
            ),
        )
        schema_id = cursor.fetchone()["schema_id"]
        cursor.execute("DELETE FROM schema_field WHERE schema_id = %s", (schema_id,))
        for field in flatten_schema_fields(normalized_schema):
            cursor.execute(
                """
                INSERT INTO schema_field (
                    schema_id, field_path, field_name, field_type,
                    is_required, nesting_depth, parent_path
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (schema_id, field_path)
                DO UPDATE SET
                    field_name = EXCLUDED.field_name,
                    field_type = EXCLUDED.field_type,
                    is_required = EXCLUDED.is_required,
                    nesting_depth = EXCLUDED.nesting_depth,
                    parent_path = EXCLUDED.parent_path
                """,
                (
                    schema_id,
                    field["field_path"],
                    field["field_name"],
                    field["field_type"],
                    field["is_required"],
                    field["nesting_depth"],
                    field["parent_path"],
                ),
            )


def extract_payload_schemas(
    *,
    spec_type: str,
    spec_content: str,
    input_format: str | None = None,
    output_format: str | None = None,
) -> list[dict[str, Any]]:
    spec_kind = spec_type.upper()
    if spec_kind in {"OPENAPI", "SWAGGER"}:
        return _extract_openapi_payload_schemas(spec_content, input_format, output_format)
    if spec_kind == "WSDL":
        return _extract_wsdl_payload_schemas(spec_content, input_format, output_format)
    return []


def flatten_schema_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], path: str, required: bool) -> None:
        node_type = node.get("type", "unknown")
        if path:
            parts = path.split("/")
            fields.append(
                {
                    "field_path": path,
                    "field_name": parts[-1].replace("[]", ""),
                    "field_type": node_type,
                    "is_required": required,
                    "nesting_depth": len(parts),
                    "parent_path": "/".join(parts[:-1]) or None,
                }
            )

        if node_type == "object":
            required_keys = set(node.get("required", []))
            for name, child in (node.get("properties") or {}).items():
                child_path = f"{path}/{name}" if path else name
                walk(child, child_path, name in required_keys)
        elif node_type == "array":
            walk(node.get("items", {"type": "unknown"}), f"{path}[]" if path else "[]", required)

    walk(schema, "", True)
    return fields


def _extract_openapi_payload_schemas(
    spec_content: str,
    input_format: str | None,
    output_format: str | None,
) -> list[dict[str, Any]]:
    spec = _parse_json_or_yaml(spec_content)
    schemas: list[dict[str, Any]] = []
    for payload in _openapi_request_payloads(spec):
        schemas.append(
            _extracted_openapi_schema(
                payload,
                direction="INPUT",
                payload_format=_payload_format(input_format, default="JSON"),
                spec=spec,
            )
        )
    for payload in _openapi_response_payloads(spec):
        schemas.append(
            _extracted_openapi_schema(
                payload,
                direction="OUTPUT",
                payload_format=_payload_format(output_format, default="JSON"),
                spec=spec,
            )
        )
    return schemas


def _extract_wsdl_payload_schemas(
    spec_content: str,
    input_format: str | None,
    output_format: str | None,
) -> list[dict[str, Any]]:
    root = ET.fromstring(spec_content)
    complex_types = _wsdl_complex_types(root)
    elements = _wsdl_top_level_elements(root, complex_types)
    input_schema = _pick_named_schema(elements, ("request", "input"))
    output_schema = _pick_named_schema(elements, ("response", "output"))
    schemas: list[dict[str, Any]] = []
    if input_schema is not None:
        schemas.append(
            {
                "direction": "INPUT",
                "format": _payload_format(input_format, default="XML"),
                "source_key": "wsdl:input",
                "source_path": "request",
                "source_method": None,
                "media_type": _payload_format(input_format, default="XML"),
                "status_code": None,
                "schema": input_schema,
            }
        )
    if output_schema is not None:
        schemas.append(
            {
                "direction": "OUTPUT",
                "format": _payload_format(output_format, default="XML"),
                "source_key": "wsdl:output",
                "source_path": "response",
                "source_method": None,
                "media_type": _payload_format(output_format, default="XML"),
                "status_code": None,
                "schema": output_schema,
            }
        )
    return schemas


def _parse_json_or_yaml(content: str) -> dict[str, Any]:
    stripped = content.strip()
    parsed = json.loads(content) if stripped.startswith("{") else yaml.safe_load(content)
    return parsed if isinstance(parsed, dict) else {}


def _openapi_request_payloads(spec: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for operation_ref in _openapi_operations(spec):
        path = operation_ref["path"]
        method = operation_ref["method"]
        operation = operation_ref["operation"]
        request_body = operation.get("requestBody")
        if isinstance(request_body, dict):
            for content_schema in _schemas_from_content(request_body.get("content")):
                payloads.append(
                    {
                        "path": path,
                        "method": method,
                        "media_type": content_schema["media_type"],
                        "schema": content_schema["schema"],
                    }
                )
        schema = _schema_from_swagger_parameters(operation.get("parameters"))
        if schema is not None:
            payloads.append(
                {
                    "path": path,
                    "method": method,
                    "media_type": "parameters",
                    "schema": schema,
                }
            )
    return payloads


def _openapi_response_payloads(spec: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for operation_ref in _openapi_operations(spec):
        path = operation_ref["path"]
        method = operation_ref["method"]
        operation = operation_ref["operation"]
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            continue
        for status_code, response in responses.items():
            if not str(status_code).startswith("2") or not isinstance(response, dict):
                continue
            content_schemas = _schemas_from_content(response.get("content"))
            for content_schema in content_schemas:
                payloads.append(
                    {
                        "path": path,
                        "method": method,
                        "media_type": content_schema["media_type"],
                        "status_code": str(status_code),
                        "schema": content_schema["schema"],
                    }
                )
            if not content_schemas and isinstance(response.get("schema"), dict):
                payloads.append(
                    {
                        "path": path,
                        "method": method,
                        "media_type": "application/json",
                        "status_code": str(status_code),
                        "schema": response["schema"],
                    }
                )
    return payloads


def _openapi_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        return operations
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS and isinstance(operation, dict):
                operations.append(
                    {
                        "path": str(path),
                        "method": method.upper(),
                        "operation": operation,
                    }
                )
    return operations


def _schema_from_content(content: object) -> dict[str, Any] | None:
    schemas = _schemas_from_content(content)
    return schemas[0]["schema"] if schemas else None


def _schemas_from_content(content: object) -> list[dict[str, Any]]:
    if not isinstance(content, dict):
        return []
    schemas: list[dict[str, Any]] = []
    for media_type, media_def in content.items():
        if not isinstance(media_def, dict):
            continue
        schema = media_def.get("schema")
        if schema is not None and isinstance(schema, dict):
            schemas.append({"media_type": str(media_type), "schema": schema})
    return schemas


def _extracted_openapi_schema(
    payload: dict[str, Any],
    *,
    direction: str,
    payload_format: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    source_path = payload["path"]
    source_method = payload["method"]
    media_type = payload.get("media_type") or payload_format
    status_code = payload.get("status_code")
    key_parts = ["openapi", direction.lower(), source_method, source_path, media_type]
    if status_code:
        key_parts.append(str(status_code))
    source_key = "|".join(_source_key_part(part) for part in key_parts)
    return {
        "direction": direction,
        "format": _payload_format(media_type, default=payload_format),
        "source_key": source_key,
        "source_path": source_path,
        "source_method": source_method,
        "media_type": media_type,
        "status_code": status_code,
        "schema": _resolve_schema(payload["schema"], spec),
    }


def _source_key_part(value: object) -> str:
    return str(value).strip().lower().replace("|", "%7c")


def _schema_from_swagger_parameters(parameters: object) -> dict[str, Any] | None:
    if not isinstance(parameters, list):
        return None

    body_schema = None
    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if parameter.get("in") == "body" and isinstance(parameter.get("schema"), dict):
            body_schema = parameter["schema"]
            continue

        name = parameter.get("name")
        if not name:
            continue
        properties[str(name)] = {
            "type": str(parameter.get("type") or "string"),
        }
        if parameter.get("required") is True:
            required.append(str(name))

    if body_schema is not None:
        return body_schema
    if not properties:
        return None
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _resolve_schema(schema: dict[str, Any], spec: dict[str, Any], seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    if "$ref" in schema:
        ref = str(schema["$ref"])
        if ref in seen:
            return {"type": "object", "properties": {}}
        seen.add(ref)
        resolved = _resolve_ref(ref, spec)
        return _resolve_schema(resolved, spec, seen)
    if isinstance(schema.get("allOf"), list):
        return _merge_all_of(schema, spec, seen)
    resolved = deepcopy(schema)
    if "properties" in resolved and isinstance(resolved["properties"], dict):
        resolved["properties"] = {
            name: _resolve_schema(child, spec, seen.copy()) if isinstance(child, dict) else child
            for name, child in resolved["properties"].items()
        }
    if "items" in resolved and isinstance(resolved["items"], dict):
        resolved["items"] = _resolve_schema(resolved["items"], spec, seen.copy())
    return resolved


def _merge_all_of(schema: dict[str, Any], spec: dict[str, Any], seen: set[str]) -> dict[str, Any]:
    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for part in schema.get("allOf") or []:
        if not isinstance(part, dict):
            continue
        resolved = _resolve_schema(part, spec, seen.copy())
        if resolved.get("type") and resolved.get("type") != "object":
            merged["type"] = resolved["type"]
        if isinstance(resolved.get("properties"), dict):
            merged.setdefault("properties", {}).update(resolved["properties"])
        if isinstance(resolved.get("required"), list):
            merged.setdefault("required", []).extend(resolved["required"])
    for key, value in schema.items():
        if key == "allOf":
            continue
        if key == "properties" and isinstance(value, dict):
            merged.setdefault("properties", {}).update(
                {
                    name: _resolve_schema(child, spec, seen.copy()) if isinstance(child, dict) else child
                    for name, child in value.items()
                }
            )
        elif key == "required" and isinstance(value, list):
            merged.setdefault("required", []).extend(value)
        else:
            merged[key] = deepcopy(value)
    merged["required"] = sorted(set(merged.get("required", [])))
    return merged


def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {"type": "object", "properties": {}}
    node: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return {"type": "object", "properties": {}}
        node = node.get(part)
    return deepcopy(node) if isinstance(node, dict) else {"type": "object", "properties": {}}


def _wsdl_complex_types(root: ET.Element) -> dict[str, dict[str, Any]]:
    types: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if _local_name(element.tag) != "complexType":
            continue
        name = element.get("name")
        if not name:
            continue
        types[name] = _schema_from_xsd_complex_type(element, types)
    return types


def _wsdl_top_level_elements(
    root: ET.Element,
    complex_types: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    elements: dict[str, dict[str, Any]] = {}
    for schema_node in root.iter():
        if _local_name(schema_node.tag) != "schema":
            continue
        for child in list(schema_node):
            if _local_name(child.tag) != "element":
                continue
            name = child.get("name")
            if not name:
                continue
            elements[name] = {
                "type": "object",
                "properties": {name: _schema_from_xsd_element(child, complex_types)},
                "required": [name],
            }
    return elements


def _schema_from_xsd_complex_type(
    complex_type: ET.Element,
    complex_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for child in _direct_xsd_child_elements(complex_type):
        name = child.get("name")
        if not name:
            continue
        properties[name] = _schema_from_xsd_element(child, complex_types)
        if child.get("minOccurs", "1") != "0":
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _direct_xsd_child_elements(complex_type: ET.Element) -> list[ET.Element]:
    elements: list[ET.Element] = []
    for container in list(complex_type):
        if _local_name(container.tag) not in {"sequence", "all", "choice"}:
            continue
        elements.extend(
            child for child in list(container) if _local_name(child.tag) == "element"
        )
    return elements


def _schema_from_xsd_element(
    element: ET.Element,
    complex_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    type_name = _local_name(element.get("type", "string"))
    inline_complex = next((child for child in list(element) if _local_name(child.tag) == "complexType"), None)
    if inline_complex is not None:
        schema = _schema_from_xsd_complex_type(inline_complex, complex_types)
    elif type_name in complex_types:
        schema = deepcopy(complex_types[type_name])
    else:
        schema = {"type": _xsd_type_to_json_schema(type_name)}
    if element.get("maxOccurs") in {"unbounded"}:
        return {"type": "array", "items": schema}
    return schema


def _pick_named_schema(schemas: dict[str, dict[str, Any]], needles: tuple[str, ...]) -> dict[str, Any] | None:
    for name, schema in schemas.items():
        lowered = name.lower()
        if any(needle in lowered for needle in needles):
            return schema
    return next(iter(schemas.values()), None) if schemas else None


def _payload_format(value: str | None, *, default: str) -> str:
    text = (value or default).strip().upper()
    if "XML" in text or "UBL" in text:
        return "XML"
    return "JSON"


def _xsd_type_to_json_schema(type_name: str) -> str:
    lowered = type_name.lower()
    if lowered in {"int", "integer", "long", "short", "byte", "nonnegativeinteger"}:
        return "integer"
    if lowered in {"decimal", "double", "float", "number"}:
        return "number"
    if lowered in {"boolean", "bool"}:
        return "boolean"
    return "string"


def _local_name(value: str | None) -> str:
    if not value:
        return ""
    return value.split("}")[-1].split(":")[-1]
