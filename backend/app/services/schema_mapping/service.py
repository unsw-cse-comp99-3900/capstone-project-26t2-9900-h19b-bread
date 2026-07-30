import re
from typing import Any

from app.services.schema_mapping.compatibility_engine import compare_schemas
from app.services.schema_mapping.data_validator import validate_data
from app.services.schema_mapping.json_schema_extractor import infer_schema
from app.services.schema_mapping.mapping_engine import FieldMapping, build_mapping
from app.services.schema_mapping.repository import PostgresSchemaMappingRepository
from app.services.schema_mapping.schema_transformer import (
    build_transformer,
    generate_transform_code,
    transform_to_xml,
)
from app.services.schema_mapping.xml_schema_extractor import extract_schema_from_xml


class SchemaMappingError(ValueError):
    """Raised when a stateless schema mapping request cannot be completed."""


class SchemaMappingPermissionError(SchemaMappingError):
    """Raised when an actor cannot manage the source side of a mapping."""


repository = PostgresSchemaMappingRepository()


def compare_schema_pair(
    source_schema: dict[str, Any],
    target_schema: dict[str, Any],
    source_name: str = "Source",
    target_name: str = "Target",
) -> dict[str, Any]:
    return compare_schemas(
        source_schema=source_schema,
        target_schema=target_schema,
        source_name=source_name,
        target_name=target_name,
    )


def build_compatibility_matrix(
    schemas: list[dict[str, Any]],
) -> dict[str, Any]:
    if not schemas:
        raise SchemaMappingError("schemas must contain at least one schema.")

    matrix: list[list[dict[str, Any]]] = []
    for source in schemas:
        row: list[dict[str, Any]] = []
        for target in schemas:
            source_name = source["name"]
            target_name = target["name"]
            if source_name == target_name:
                row.append(
                    {
                        "source": source_name,
                        "target": target_name,
                        "compatibility": "same_schema",
                        "summary": {"compatibility_label": "Same schema"},
                    }
                )
            else:
                row.append(
                    compare_schema_pair(
                        source_schema=source["schema"],
                        target_schema=target["schema"],
                        source_name=source_name,
                        target_name=target_name,
                    )
                )
        matrix.append(row)

    return {"matrix": matrix}


def transform_preview(
    source_schema: dict[str, Any],
    target_schema: dict[str, Any],
    data: dict[str, Any],
    output_format: str = "json",
    source_name: str = "Source",
    target_name: str = "Target",
) -> dict[str, Any]:
    output_format = output_format.lower()
    if output_format not in {"json", "xml"}:
        raise SchemaMappingError("format must be json or xml.")

    is_valid, validation_error = validate_data(data, source_schema)
    if not is_valid:
        raise SchemaMappingError(validation_error or "Source data failed validation.")

    comparison = compare_schema_pair(
        source_schema=source_schema,
        target_schema=target_schema,
        source_name=source_name,
        target_name=target_name,
    )
    mapping = build_mapping(comparison)
    transformer = build_transformer(mapping)
    transformed_json = transformer(data)

    return {
        "result": (
            transform_to_xml(lambda _: transformed_json, {}, root_tag="record")
            if output_format == "xml"
            else transformed_json
        ),
        "format": output_format,
        "mapping_status": mapping.status,
        "mapping": mapping.to_dict(),
        "comparison": comparison,
        "transform_code": generate_transform_code(mapping),
    }


def infer_json_schema_from_sample(data: Any) -> dict[str, Any]:
    return infer_schema(data)


def infer_xml_schema_from_sample(xml_content: str) -> dict[str, Any]:
    try:
        return extract_schema_from_xml(xml_content)
    except Exception as exc:
        raise SchemaMappingError(f"Could not parse XML content: {exc}") from exc


def list_database_api_schemas() -> list[dict[str, Any]]:
    return repository.list_api_schemas()


def compare_database_api_schemas(
    source_schema_id: int,
    target_schema_id: int,
    *,
    save_mapping: bool = True,
    enterprise_id: int | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    source_schema = repository.get_api_schema(source_schema_id)
    target_schema = repository.get_api_schema(target_schema_id)
    if source_schema is None:
        raise SchemaMappingError(f"Source schema {source_schema_id} was not found.")
    if target_schema is None:
        raise SchemaMappingError(f"Target schema {target_schema_id} was not found.")
    if (
        source_schema.get("api_status") != "PUBLISHED"
        or source_schema.get("version_status") != "PUBLISHED"
        or target_schema.get("api_status") != "PUBLISHED"
        or target_schema.get("version_status") != "PUBLISHED"
    ):
        raise SchemaMappingError("Schema mapping is only available for published APIs.")
    if source_schema["api_id"] == target_schema["api_id"]:
        raise SchemaMappingError("Source and target schemas must belong to different APIs.")
    if source_schema["direction"] != "OUTPUT":
        raise SchemaMappingError("Source schema must have OUTPUT direction.")
    if target_schema["direction"] != "INPUT":
        raise SchemaMappingError("Target schema must have INPUT direction.")
    _ensure_source_owner(source_schema["api_id"], enterprise_id, is_admin)

    comparison = compare_schema_pair(
        source_schema=source_schema["schema_definition"],
        target_schema=target_schema["schema_definition"],
        source_name=source_schema["api_name"],
        target_name=target_schema["api_name"],
    )
    mapping = build_mapping(comparison)

    comparison_result_id = None
    mapping_id = None
    if save_mapping:
        mapping_id = repository.save_mapping(
            source_schema=source_schema,
            target_schema=target_schema,
            comparison_result_id=comparison_result_id,
            mapping=mapping,
        )

    return {
        "source_schema": source_schema,
        "target_schema": target_schema,
        "comparison_result_id": comparison_result_id,
        "mapping_id": mapping_id,
        "comparison": comparison,
        "mapping": mapping.to_dict(),
    }


def transform_database_mapping_preview(
    mapping_id: int,
    data: dict[str, Any],
    output_format: str = "json",
    *,
    save_run: bool = True,
    enterprise_id: int | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    output_format = output_format.lower()
    if output_format not in {"json", "xml"}:
        raise SchemaMappingError("format must be json or xml.")

    mapping_detail = repository.get_mapping(mapping_id)
    if mapping_detail is None:
        raise SchemaMappingError(f"Mapping {mapping_id} was not found.")
    _ensure_source_owner(
        mapping_detail["row"]["source_api_id"],
        enterprise_id,
        is_admin,
    )
    source_schema = mapping_detail["source_schema"]
    if source_schema is None:
        raise SchemaMappingError("Mapping has no source schema.")

    is_valid, validation_error = validate_data(data, source_schema["schema_definition"])
    if not is_valid:
        raise SchemaMappingError(validation_error or "Source data failed validation.")

    mapping = mapping_detail["mapping"]
    transformer = build_transformer(mapping)
    transformed_json = transformer(data)
    target_schema = mapping_detail["target_schema"]
    if target_schema is None:
        raise SchemaMappingError("Mapping has no target schema.")
    target_valid, target_error = validate_data(
        transformed_json,
        target_schema["schema_definition"],
    )
    result = (
        transform_to_xml(lambda _: transformed_json, {}, root_tag="record")
        if output_format == "xml"
        else transformed_json
    )
    transform_run_id = None
    if save_run:
        transform_run_id = repository.save_transform_run(
            mapping_row=mapping_detail["row"],
            input_data=data,
            output_data=result,
            output_format=output_format,
            mapping_status=mapping.status,
            success=target_valid,
            error_message=target_error,
        )

    if not target_valid:
        raise SchemaMappingError(
            target_error or "Transformed output failed target input validation."
        )

    return {
        "result": result,
        "format": output_format,
        "mapping_status": mapping.status,
        "mapping": mapping.to_dict(),
        "comparison": mapping_detail["comparison"] or {},
        "transform_code": generate_transform_code(mapping),
        "transform_run_id": transform_run_id,
        "comparison_result_id": mapping_detail["row"]["compatibility_result_id"],
        "mapping_id": mapping_id,
        "target_validation_passed": True,
    }


def update_database_mapping_rules(
    mapping_id: int,
    rules: list[dict[str, Any]],
    *,
    enterprise_id: int | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    mapping_detail = repository.get_mapping(mapping_id)
    if mapping_detail is None:
        raise SchemaMappingError(f"Mapping {mapping_id} was not found.")
    row = mapping_detail["row"]
    _ensure_source_owner(row["source_api_id"], enterprise_id, is_admin)
    if row["lifecycle_status"] in {"VALIDATING", "DEPRECATED"}:
        raise SchemaMappingError(
            f"Mapping rules cannot be edited while lifecycle status is {row['lifecycle_status']}."
        )

    target_schema = mapping_detail["target_schema"]
    required_paths = _required_leaf_paths(target_schema["schema_definition"])
    declared_targets = [_canonical_path(rule["target_path"]) for rule in rules]
    if len(declared_targets) != len(set(declared_targets)):
        raise SchemaMappingError("Each target path may appear in at most one mapping rule.")
    target_paths = {
        _canonical_path(rule["target_path"])
        for rule in rules
        if rule["transform"] not in {"drop", "missing"}
    }
    completeness = "FULL" if required_paths <= target_paths else "PARTIAL"
    fields = [
        FieldMapping(
            source_path=rule.get("source_path"),
            target_path=rule["target_path"],
            transform=rule["transform"],
            source_type=rule.get("source_type"),
            target_type=rule.get("target_type"),
            confidence=rule.get("confidence", "high"),
            note=rule.get("note", ""),
        )
        for rule in rules
    ]
    updated = repository.replace_mapping_rules(mapping_id, fields, completeness)
    return {
        **updated,
        "revalidation_required": True,
        "missing_required_targets": sorted(required_paths - target_paths),
    }


def _ensure_source_owner(
    source_api_id: int,
    enterprise_id: int | None,
    is_admin: bool,
) -> None:
    if enterprise_id is None or is_admin:
        return
    if repository.get_api_owner_enterprise(source_api_id) != enterprise_id:
        raise SchemaMappingPermissionError(
            "Only the source API owner or an administrator may manage this mapping."
        )


def _required_leaf_paths(schema: dict[str, Any], prefix: str = "") -> set[str]:
    if schema.get("type") == "array":
        item_path = f"{prefix}[]" if prefix else "[]"
        nested = _required_leaf_paths(schema.get("items") or {}, item_path)
        return nested or {item_path}
    if schema.get("type") != "object":
        return {prefix} if prefix else set()
    paths: set[str] = set()
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        child = properties.get(name, {})
        path = f"{prefix}.{name}" if prefix else name
        nested = _required_leaf_paths(child, path)
        paths.update(nested or {path})
    return paths


def _canonical_path(path: str) -> str:
    cleaned = path.strip().lstrip("$./")
    return ".".join(part for part in re.split(r"[/.]+", cleaned) if part)
