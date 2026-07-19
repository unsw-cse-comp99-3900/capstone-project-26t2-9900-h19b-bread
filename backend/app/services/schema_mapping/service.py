from typing import Any

from app.services.schema_mapping.compatibility_engine import compare_schemas
from app.services.schema_mapping.data_validator import validate_data
from app.services.schema_mapping.json_schema_extractor import infer_schema
from app.services.schema_mapping.mapping_engine import build_mapping
from app.services.schema_mapping.schema_transformer import (
    build_transformer,
    generate_transform_code,
    transform_to_xml,
)
from app.services.schema_mapping.xml_schema_extractor import extract_schema_from_xml


class SchemaMappingError(ValueError):
    """Raised when a stateless schema mapping request cannot be completed."""


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
