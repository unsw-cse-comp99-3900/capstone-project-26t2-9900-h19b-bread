from app.main import app


def test_version_history_routes_match_cloud_backed_contract() -> None:
    paths = app.openapi()["paths"]

    assert "/api/apis/{api_id}/versions" in paths
    assert {"get", "post"} <= set(paths["/api/apis/{api_id}/versions"])
    assert "/api/apis/{api_id}/versions/{version_id}" in paths
    assert {"get", "put"} <= set(paths["/api/apis/{api_id}/versions/{version_id}"])
    assert "/api/apis/{api_id}/versions/{version_id}/specification" in paths
    assert "/api/apis/{api_id}/history" in paths
    assert "/api/apis/{api_id}/connection-impacts" in paths
    assert not any("history-access" in path for path in paths)


def test_all_history_reads_require_authentication() -> None:
    paths = app.openapi()["paths"]
    read_operations = [
        paths["/api/apis/{api_id}/versions"]["get"],
        paths["/api/apis/{api_id}/versions/{version_id}"]["get"],
        paths["/api/apis/{api_id}/versions/{version_id}/specification"]["get"],
        paths["/api/apis/{api_id}/history"]["get"],
        paths["/api/apis/{api_id}/connection-impacts"]["get"],
    ]

    assert all(operation.get("security") == [{"HTTPBearer": []}] for operation in read_operations)


def test_validation_result_callback_requires_authentication() -> None:
    openapi = app.openapi()
    operation = openapi["paths"]["/api/apis/{api_id}/validation-result"]["post"]

    assert operation.get("security") == [{"HTTPBearer": []}]
    assert "validation_run_id" in openapi["components"]["schemas"][
        "ValidationResultRequest"
    ]["required"]
