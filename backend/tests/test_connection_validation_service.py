import pytest
from datetime import datetime

from app.connection_validation import (
    ConnectionValidationConflictError,
    ConnectionValidationNotFoundError,
    ConnectionValidationPermissionError,
    ConnectionValidationRequest,
    ConnectionValidationService,
    EndpointVersion,
    FormatAlias,
    PayloadSchema,
    PersistedDecision,
)


class FakeRepository:
    def __init__(self):
        self.source = EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"])
        self.target = EndpointVersion(2, 20, "PUBLISHED", ["JSON"], [])
        self.source_schema = PayloadSchema(
            100,
            "OUTPUT",
            "JSON",
            {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        )
        self.target_schema = PayloadSchema(
            200,
            "INPUT",
            "JSON",
            {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        )
        self.saved = None
        self.cancelled = []
        self.connection = {
            "mapping_id": 66,
            "source_api_id": 1,
            "source_version_id": 10,
            "target_api_id": 2,
            "target_version_id": 20,
            "source_schema_id": 100,
            "target_schema_id": 200,
            "compatibility_result_id": 88,
            "lifecycle_status": "ACTIVE",
            "completeness": "FULL",
            "updated_at": datetime(2026, 7, 30),
            "source_enterprise_id": 9,
        }
        self.run = {
            "connection_validation_run_id": 77,
            "source_api_id": 1,
            "source_version_id": 10,
            "target_api_id": 2,
            "target_version_id": 20,
            "compatibility_result_id": 88,
            "status": "PASSED",
            "trigger_type": "MANUAL",
            "created_by": 5,
            "started_at": datetime(2026, 7, 30, 12, 0),
            "completed_at": datetime(2026, 7, 30, 12, 1),
            "source_enterprise_id": 9,
            "stages": [
                {
                    "stage": "ELIGIBILITY",
                    "status": "PASSED",
                    "message": "Eligible.",
                    "payload": {},
                }
            ],
        }
        self.list_runs_args = None

    def get_version(self, api_id, version_id):
        return next(
            (
                endpoint
                for endpoint in (self.source, self.target)
                if endpoint is not None
                and endpoint.api_id == api_id
                and endpoint.version_id == version_id
            ),
            None,
        )

    def assert_actor_can_validate(self, *args):
        return None

    def get_schema(self, api_id, version_id, direction, schema_id=None):
        return self.source_schema if direction == "OUTPUT" else self.target_schema

    def list_format_aliases(self):
        return [FormatAlias("JSON", "JSON", "JSON")]

    def create_run(self, request, created_by):
        return 77

    def save_decision(self, run_id, request, context, decision):
        self.saved = (run_id, decision)
        return PersistedDecision(88, None, None, True, None)

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)

    def get_run(self, run_id):
        return self.run if run_id == 77 else None


def _request():
    return ConnectionValidationRequest(
        source_api_id=1,
        source_version_id=10,
        target_api_id=2,
        target_version_id=20,
        sample_data={"id": "INV-1"},
    )


def test_service_loads_fixed_context_and_persists_decision():
    repository = FakeRepository()
    service = ConnectionValidationService(repository)

    response = service.validate(
        _request(),
        actor_id=5,
        enterprise_id=9,
    )

    assert response.connection_validation_run_id == 77
    assert response.compatibility_result_id == 88
    assert response.transform_run_id is None
    assert response.mapping_id is None
    assert response.lifecycle_status is None
    assert response.reason_code == "DIRECTLY_COMPATIBLE"
    assert response.activation_allowed is True
    assert response.business_rules_diagnostics == {
        "source_business_rules": [],
        "target_business_rules": [],
        "overlapping_rules": [],
        "disjoint_rules": [],
    }
    assert repository.saved[0] == 77


def test_service_rejects_unknown_version_before_creating_run():
    repository = FakeRepository()
    repository.source = None
    service = ConnectionValidationService(repository)

    with pytest.raises(ConnectionValidationNotFoundError) as exc_info:
        service.validate(_request(), actor_id=5, enterprise_id=9)

    assert exc_info.value.reason_code == "SOURCE_VERSION_NOT_FOUND"
    assert repository.saved is None


def test_service_rejects_same_version_pair_before_creating_run():
    repository = FakeRepository()
    repository.target = repository.source
    service = ConnectionValidationService(repository)
    request = ConnectionValidationRequest(
        source_api_id=1,
        source_version_id=10,
        target_api_id=1,
        target_version_id=10,
        sample_data={"id": "INV-1"},
    )

    with pytest.raises(ConnectionValidationConflictError, match="different versions"):
        service.validate(request, actor_id=5, enterprise_id=9)

    assert repository.saved is None


def test_service_allows_same_api_with_different_versions():
    repository = FakeRepository()
    repository.target = EndpointVersion(1, 20, "PUBLISHED", ["JSON"], [])
    service = ConnectionValidationService(repository)
    request = ConnectionValidationRequest(
        source_api_id=1,
        source_version_id=10,
        target_api_id=1,
        target_version_id=20,
        sample_data={"id": "INV-1"},
    )

    response = service.validate(request, actor_id=5, enterprise_id=9)

    assert response.activation_allowed is True
    assert repository.saved is not None


def test_service_cancels_run_when_pipeline_raises():
    class BrokenPipeline:
        def run(self, context):
            raise RuntimeError("engine unavailable")

    repository = FakeRepository()
    service = ConnectionValidationService(
        repository,
        pipeline=BrokenPipeline(),
    )

    with pytest.raises(RuntimeError, match="engine unavailable"):
        service.validate(_request(), actor_id=5, enterprise_id=9)

    assert repository.cancelled == [77]


def test_service_suppresses_activation_for_superseded_run():
    repository = FakeRepository()

    def save_stale(run_id, request, context, decision):
        return PersistedDecision(None, 66, "VALIDATING", False)

    repository.save_decision = save_stale
    service = ConnectionValidationService(repository)

    response = service.validate(_request(), actor_id=5, enterprise_id=9)

    assert response.is_latest_run is False
    assert response.compatibility_result_id is None
    assert response.reason_code == "STALE_VALIDATION_RUN"
    assert response.activation_allowed is False


def test_service_does_not_expose_mapping_lifecycle_from_persistence():
    repository = FakeRepository()

    def save_cancelled(run_id, request, context, decision):
        return PersistedDecision(None, 66, "DEPRECATED", True)

    repository.save_decision = save_cancelled
    service = ConnectionValidationService(repository)

    response = service.validate(_request(), actor_id=5, enterprise_id=9)

    assert response.compatibility_level.value == "DIRECTLY_COMPATIBLE"
    assert response.reason_code == "DIRECTLY_COMPATIBLE"
    assert response.mapping_id is None
    assert response.lifecycle_status is None
    assert response.activation_allowed is True


def test_source_owner_can_read_run_detail():
    repository = FakeRepository()
    service = ConnectionValidationService(repository)

    run = service.get_run(77, enterprise_id=9)

    assert run.stages[0].stage.value == "ELIGIBILITY"


def test_other_enterprise_cannot_read_validation_run():
    repository = FakeRepository()
    service = ConnectionValidationService(repository)

    with pytest.raises(ConnectionValidationPermissionError):
        service.get_run(77, enterprise_id=10)
