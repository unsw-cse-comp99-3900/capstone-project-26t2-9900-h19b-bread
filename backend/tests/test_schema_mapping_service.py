from app.services.schema_mapping.mapping_engine import FieldMapping, SchemaMapping
from app.services.schema_mapping.repository import PostgresSchemaMappingRepository
from app.services.schema_mapping.service import (
    build_compatibility_matrix,
    compare_schema_pair,
    infer_json_schema_from_sample,
    infer_xml_schema_from_sample,
    transform_preview,
)


class _FakeCursor:
    def __init__(self):
        self.statements = []
        self._row = {"mapping_id": 17}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


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


def test_save_mapping_upserts_by_schema_pair_not_version_pair():
    cursor = _FakeCursor()
    repository = PostgresSchemaMappingRepository(
        connection_factory=lambda: _FakeConnection(cursor)
    )
    mapping = SchemaMapping(
        source="Source",
        target="Target",
        status="partial",
        fields=[
            FieldMapping(
                source_path="invoiceNumber",
                target_path="invoice_id",
                transform="rename",
                source_type="string",
                target_type="string",
                confidence="high",
                note="Rename field.",
            )
        ],
    )

    mapping_id = repository.save_mapping(
        source_schema={
            "api_id": 1,
            "version_id": 10,
            "schema_id": 101,
            "format": "JSON",
        },
        target_schema={
            "api_id": 2,
            "version_id": 20,
            "schema_id": 202,
            "format": "JSON",
        },
        comparison_result_id=99,
        mapping=mapping,
    )

    insert_statement = cursor.statements[0][0]
    assert mapping_id == 17
    assert "ON CONFLICT (source_schema_id, target_schema_id)" in insert_statement
    assert "ON CONFLICT (source_api_id, target_api_id, source_version_id, target_version_id)" not in insert_statement