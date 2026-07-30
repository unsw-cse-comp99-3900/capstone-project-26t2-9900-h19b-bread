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
        self.prepared = []
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
        return {(1, 10): self.source, (2, 20): self.target}.get((api_id, version_id))

    def assert_actor_can_validate(self, *args):
        return None

    def get_schema(self, api_id, version_id, direction, schema_id=None):
        return self.source_schema if direction == "OUTPUT" else self.target_schema

    def list_format_aliases(self):
        return [FormatAlias("JSON", "JSON", "JSON")]

    def get_mapping_metadata(self, request, source_schema_id, target_schema_id):
        return None

    def prepare_mapping(self, request, source_schema, target_schema):
        self.prepared.append((source_schema.schema_id, target_schema.schema_id))
        return {
            "mapping_id": 66,
            "lifecycle_status": "VALIDATING",
            "completeness": "PARTIAL",
        }

    def create_run(self, request, created_by):
        return 77

    def save_decision(self, run_id, request, context, decision):
        self.saved = (run_id, decision)
        return PersistedDecision(88, 66, "ACTIVE", True, 99)

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)

    def get_connection(self, mapping_id):
        return self.connection if mapping_id == 66 else None

    def get_run(self, run_id):
        return self.run if run_id == 77 else None

    def list_runs(self, *args):
        self.list_runs_args = args
        summary = {
            key: value
            for key, value in self.run.items()
            if key not in {"stages", "source_enterprise_id"}
        }
        return [summary], 1

    def deprecate_connection(self, mapping_id):
        self.connection["lifecycle_status"] = "DEPRECATED"
        return self.connection


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
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    response = service.validate(
        _request(),
        actor_id=5,
        enterprise_id=9,
    )

    assert response.connection_validation_run_id == 77
    assert response.compatibility_result_id == 88
    assert response.transform_run_id == 99
    assert response.mapping_id == 66
    assert response.lifecycle_status == "ACTIVE"
    assert response.reason_code == "DIRECTLY_COMPATIBLE"
    assert response.activation_allowed is True
    assert repository.saved[0] == 77
    assert repository.prepared == [(100, 200)]


def test_service_rejects_unknown_version_before_creating_run():
    repository = FakeRepository()
    repository.source = None
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    with pytest.raises(ConnectionValidationNotFoundError):
        service.validate(_request(), actor_id=5, enterprise_id=9)

    assert repository.saved is None


def test_service_rejects_same_api_pair_before_creating_run():
    repository = FakeRepository()
    repository.target = repository.source
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)
    request = ConnectionValidationRequest(
        source_api_id=1,
        source_version_id=10,
        target_api_id=1,
        target_version_id=10,
        sample_data={"id": "INV-1"},
    )

    with pytest.raises(ConnectionValidationConflictError, match="different APIs"):
        service.validate(request, actor_id=5, enterprise_id=9)

    assert repository.saved is None
    assert repository.prepared == []


def test_service_cancels_run_when_pipeline_raises():
    class BrokenPipeline:
        def run(self, context):
            raise RuntimeError("engine unavailable")

    repository = FakeRepository()
    service = ConnectionValidationService(
        repository,
        mapping_loader=lambda _: None,
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
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    response = service.validate(_request(), actor_id=5, enterprise_id=9)

    assert response.is_latest_run is False
    assert response.compatibility_result_id is None
    assert response.reason_code == "STALE_VALIDATION_RUN"
    assert response.activation_allowed is False


def test_service_reports_deprecated_connection_when_run_was_cancelled():
    repository = FakeRepository()

    def save_cancelled(run_id, request, context, decision):
        return PersistedDecision(None, 66, "DEPRECATED", True)

    repository.save_decision = save_cancelled
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    response = service.validate(_request(), actor_id=5, enterprise_id=9)

    assert response.compatibility_level.value == "MISSING_INFORMATION"
    assert response.reason_code == "CONNECTION_DEPRECATED"
    assert response.activation_allowed is False


def test_source_owner_can_read_and_deprecate_connection():
    repository = FakeRepository()
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    current = service.get_connection(66, enterprise_id=9)
    deprecated = service.deprecate_connection(66, enterprise_id=9)

    assert current.lifecycle_status == "ACTIVE"
    assert deprecated.lifecycle_status == "DEPRECATED"


def test_validating_connection_cannot_be_deprecated():
    repository = FakeRepository()
    repository.connection["lifecycle_status"] = "VALIDATING"
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    with pytest.raises(ValueError, match="cannot be deprecated"):
        service.deprecate_connection(66, enterprise_id=9)


def test_source_owner_can_read_run_detail_and_connection_history():
    repository = FakeRepository()
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    run = service.get_run(77, enterprise_id=9)
    history = service.list_connection_runs(66, 2, 10, enterprise_id=9)

    assert run.stages[0].stage.value == "ELIGIBILITY"
    assert history.total == 1
    assert history.page == 2
    assert repository.list_runs_args == (1, 10, 2, 20, 10, 10)


def test_other_enterprise_cannot_read_validation_run():
    repository = FakeRepository()
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    with pytest.raises(ConnectionValidationPermissionError):
        service.get_run(77, enterprise_id=10)
