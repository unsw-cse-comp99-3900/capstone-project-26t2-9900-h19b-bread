from fastapi.testclient import TestClient

from app.connection_validation import (
    CompatibilityLevel,
    ConnectionValidationResponse,
    ConnectionValidationStage,
    ConnectionValidationStageStatus,
)
from app.connection_validation.schemas import StageResult
from app.main import app
from app.routers.connection_validation import (
    get_connection_validation_actor,
    get_connection_validation_service,
)


class FakeService:
    def validate(self, request, *, actor_id, enterprise_id, is_admin=False):
        assert actor_id == 5
        assert enterprise_id == 9
        return ConnectionValidationResponse(
            connection_validation_run_id=77,
            compatibility_result_id=88,
            compatibility_level=CompatibilityLevel.COMPATIBLE,
            reason_code="DIRECTLY_COMPATIBLE",
            reason="Compatible.",
            activation_allowed=True,
            source_api_id=request.source_api_id,
            source_version_id=request.source_version_id,
            target_api_id=request.target_api_id,
            target_version_id=request.target_version_id,
            source_schema_id=100,
            target_schema_id=200,
            stages=[
                StageResult(
                    stage=ConnectionValidationStage.ELIGIBILITY,
                    status=ConnectionValidationStageStatus.PASSED,
                    message="Eligible.",
                )
            ],
            reasons=[],
        )

    def get_connection(self, mapping_id, *, enterprise_id, is_admin=False):
        return {
            "mapping_id": mapping_id,
            "source_api_id": 1,
            "source_version_id": 10,
            "target_api_id": 2,
            "target_version_id": 20,
            "source_schema_id": 100,
            "target_schema_id": 200,
            "compatibility_result_id": 88,
            "lifecycle_status": "ACTIVE",
            "completeness": "FULL",
            "updated_at": "2026-07-30T12:00:00",
        }

    def deprecate_connection(self, mapping_id, *, enterprise_id, is_admin=False):
        result = self.get_connection(
            mapping_id,
            enterprise_id=enterprise_id,
            is_admin=is_admin,
        )
        result["lifecycle_status"] = "DEPRECATED"
        return result


def test_connection_validation_endpoint_uses_authenticated_actor():
    app.dependency_overrides[get_connection_validation_service] = lambda: FakeService()
    app.dependency_overrides[get_connection_validation_actor] = lambda: {
        "user_id": 5,
        "enterprise_id": 9,
        "role": "PUBLISHER",
    }
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/connection-validation/runs",
            json={
                "source_api_id": 1,
                "source_version_id": 10,
                "target_api_id": 2,
                "target_version_id": 20,
                "sample_data": {"id": "INV-1"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["connection_validation_run_id"] == 77
    assert response.json()["activation_allowed"] is True


def test_connection_lifecycle_endpoints_return_current_state():
    app.dependency_overrides[get_connection_validation_service] = lambda: FakeService()
    app.dependency_overrides[get_connection_validation_actor] = lambda: {
        "user_id": 5,
        "enterprise_id": 9,
        "role": "PUBLISHER",
    }
    client = TestClient(app)

    try:
        current = client.get("/api/v1/connection-validation/connections/66")
        deprecated = client.post(
            "/api/v1/connection-validation/connections/66/deprecate"
        )
    finally:
        app.dependency_overrides.clear()

    assert current.status_code == 200
    assert current.json()["lifecycle_status"] == "ACTIVE"
    assert deprecated.status_code == 200
    assert deprecated.json()["lifecycle_status"] == "DEPRECATED"
