import pytest

from app.connection_validation import (
    ConnectionValidationNotFoundError,
    ConnectionValidationRequest,
    ConnectionValidationService,
    EndpointVersion,
    FormatAlias,
    PayloadSchema,
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

    def create_run(self, request, created_by):
        return 77

    def save_decision(self, run_id, request, context, decision):
        self.saved = (run_id, decision)
        return 88

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)


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
    assert response.reason_code == "DIRECTLY_COMPATIBLE"
    assert response.activation_allowed is True
    assert repository.saved[0] == 77


def test_service_rejects_unknown_version_before_creating_run():
    repository = FakeRepository()
    repository.source = None
    service = ConnectionValidationService(repository, mapping_loader=lambda _: None)

    with pytest.raises(ConnectionValidationNotFoundError):
        service.validate(_request(), actor_id=5, enterprise_id=9)

    assert repository.saved is None


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
