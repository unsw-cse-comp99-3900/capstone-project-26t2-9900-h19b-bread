from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _object_schema(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties.keys()),
    }


def _field(type_name):
    return {"type": type_name}


def test_compare_endpoint_returns_mapping_result():
    source = _object_schema({"invoiceId": _field("string")})
    target = _object_schema({"invoice_id": _field("string")})

    response = client.post(
        "/api/v1/schema-mapping/compare",
        json={
            "source_name": "SourceAPI",
            "target_name": "TargetAPI",
            "source_schema": source,
            "target_schema": target,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "compatible_with_mapping"
    assert body["summary"]["mapping_issues"] == 1


def test_transform_preview_endpoint_is_stateless():
    source = _object_schema(
        {"invoiceId": _field("string"), "amount": _field("string")}
    )
    target = _object_schema(
        {"invoice_id": _field("string"), "amount": _field("number")}
    )

    response = client.post(
        "/api/v1/schema-mapping/transform-preview",
        json={
            "source_name": "SourceAPI",
            "target_name": "TargetAPI",
            "source_schema": source,
            "target_schema": target,
            "data": {"invoiceId": "INV-1", "amount": "99.9"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == {"invoice_id": "INV-1", "amount": 99.9}
    assert body["mapping_status"] == "partial"
    assert body["mapping"]["fields"]


def test_infer_json_schema_endpoint():
    response = client.post(
        "/api/v1/schema-mapping/infer-json-schema",
        json={"data": {"id": 1, "items": [{"name": "A"}]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema"]["properties"]["id"]["type"] == "integer"
    assert body["schema"]["properties"]["items"]["type"] == "array"


def test_infer_xml_schema_endpoint_rejects_invalid_xml():
    response = client.post(
        "/api/v1/schema-mapping/infer-xml-schema",
        json={"xml_content": "<invoice>"},
    )

    assert response.status_code == 422
