from app.services.schema_mapping.service import (
    build_compatibility_matrix,
    compare_schema_pair,
    infer_json_schema_from_sample,
    infer_xml_schema_from_sample,
    transform_preview,
)


def _object_schema(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties.keys()),
    }


def _field(type_name):
    return {"type": type_name}


def test_compare_schema_pair_detects_rename_mapping():
    source = _object_schema({"userId": _field("integer")})
    target = _object_schema({"user_id": _field("integer")})

    result = compare_schema_pair(source, target, "SourceAPI", "TargetAPI")

    assert result["compatibility"] == "compatible_with_mapping"
    assert result["summary"]["mapping_issues"] == 1
    assert result["issues"][0]["source_path"] == "userId"
    assert result["issues"][0]["target_path"] == "user_id"


def test_transform_preview_casts_and_renames_without_database():
    source = _object_schema(
        {
            "userId": _field("integer"),
            "amount": _field("string"),
        }
    )
    target = _object_schema(
        {
            "user_id": _field("integer"),
            "amount": _field("number"),
        }
    )

    result = transform_preview(
        source_schema=source,
        target_schema=target,
        data={"userId": 7, "amount": "12.5"},
        source_name="SourceAPI",
        target_name="TargetAPI",
    )

    assert result["format"] == "json"
    assert result["mapping_status"] == "partial"
    assert result["result"] == {"user_id": 7, "amount": 12.5}
    assert "transform_sourceapi_to_targetapi" in result["transform_code"]


def test_build_compatibility_matrix_returns_same_schema_diagonal():
    schema = _object_schema({"id": _field("integer")})

    result = build_compatibility_matrix(
        [
            {"name": "A", "schema": schema},
            {"name": "B", "schema": schema},
        ]
    )

    assert result["matrix"][0][0]["compatibility"] == "same_schema"
    assert result["matrix"][0][1]["compatibility"] == "directly_compatible"


def test_infer_json_schema_from_sample():
    schema = infer_json_schema_from_sample(
        {"invoiceNumber": "INV-1", "total": 19.5, "paid": False}
    )

    assert schema["type"] == "object"
    assert schema["properties"]["invoiceNumber"]["type"] == "string"
    assert schema["properties"]["total"]["type"] == "number"
    assert schema["properties"]["paid"]["type"] == "boolean"


def test_infer_xml_schema_from_sample():
    schema = infer_xml_schema_from_sample(
        "<invoice><id>123</id><total>42.5</total></invoice>"
    )

    assert schema["root"] == "invoice"
    assert schema["schema"]["properties"]["id"]["type"] == "integer"
    assert schema["schema"]["properties"]["total"]["type"] == "number"
