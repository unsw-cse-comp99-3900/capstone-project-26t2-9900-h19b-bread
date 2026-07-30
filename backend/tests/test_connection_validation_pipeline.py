from app.connection_validation import (
    CompatibilityLevel,
    ConnectionValidationContext,
    ConnectionValidationPipeline,
    ConnectionValidationStageStatus,
    EndpointVersion,
    FormatAlias,
    MappingContext,
    PayloadSchema,
)
from app.services.schema_mapping.compatibility_engine import compare_schemas
from app.services.schema_mapping.data_validator import validate_data


def _schema(schema_id: int, direction: str, properties: dict, required=None):
    return PayloadSchema(
        schema_id=schema_id,
        direction=direction,
        format="JSON",
        definition={
            "type": "object",
            "properties": properties,
            "required": required if required is not None else list(properties),
        },
    )


def _context(**overrides):
    values = {
        "source": EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
        "target": EndpointVersion(2, 20, "PUBLISHED", ["JSON"], []),
        "source_schema": _schema(100, "OUTPUT", {"id": {"type": "string"}}),
        "target_schema": _schema(200, "INPUT", {"id": {"type": "string"}}),
        "aliases": [FormatAlias("JSON", "JSON", "JSON")],
        "sample_data": {"id": "INV-1"},
    }
    values.update(overrides)
    return ConnectionValidationContext(**values)


def _pipeline():
    return ConnectionValidationPipeline(compare_schemas, validate_data)


def test_directly_compatible_pair_passes_all_required_gates():
    decision = _pipeline().run(_context())

    assert decision.compatibility_level == CompatibilityLevel.COMPATIBLE
    assert decision.reason_code == "DIRECTLY_COMPATIBLE"
    assert decision.activation_allowed is True
    assert [stage.status for stage in decision.stages] == [
        ConnectionValidationStageStatus.PASSED,
        ConnectionValidationStageStatus.PASSED,
        ConnectionValidationStageStatus.PASSED,
        ConnectionValidationStageStatus.NOT_RUN,
        ConnectionValidationStageStatus.PASSED,
        ConnectionValidationStageStatus.PASSED,
    ]


def test_terminal_output_fails_and_persists_not_run_shape():
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["Validation Report"]),
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias(
                "Validation Report",
                "VALIDATION_REPORT",
                "REPORT",
                is_terminal_output=True,
            )
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.INCOMPATIBLE
    assert decision.reason_code == "SOURCE_OUTPUT_IS_TERMINAL_REPORT"
    assert decision.activation_allowed is False
    assert len(decision.stages) == 6
    assert decision.stages[2].status == ConnectionValidationStageStatus.NOT_RUN


def test_missing_schema_is_missing_information_not_incompatible():
    decision = _pipeline().run(_context(source_schema=None))

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "SOURCE_OUTPUT_SCHEMA_MISSING"
    assert decision.stages[0].status == ConnectionValidationStageStatus.MISSING_INFORMATION


def test_mapping_compatible_schema_requires_complete_mapping():
    target = _schema(200, "INPUT", {"invoice_id": {"type": "string"}})

    decision = _pipeline().run(_context(target_schema=target))

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "MAPPING_REQUIRED"
    assert decision.activation_allowed is False


def test_complete_mapping_must_also_pass_target_validation():
    target = _schema(200, "INPUT", {"invoice_id": {"type": "string"}})
    mapping = MappingContext(
        mapping_id=7,
        lifecycle_status="DRAFT",
        completeness="FULL",
        transform=lambda data: {"invoice_id": data["id"]},
    )

    decision = _pipeline().run(_context(target_schema=target, mapping=mapping))

    assert decision.compatibility_level == CompatibilityLevel.COMPATIBLE
    assert decision.reason_code == "COMPATIBLE_WITH_MAPPING"
    assert decision.activation_allowed is True
    assert decision.transformed_data == {"invoice_id": "INV-1"}


def test_missing_sample_blocks_activation_after_static_checks():
    decision = _pipeline().run(_context(sample_data=None))

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "SAMPLE_DATA_MISSING"
    assert decision.stages[-1].status == ConnectionValidationStageStatus.NOT_RUN


def test_document_format_is_not_treated_as_json_xml_bridge():
    context = _context(
        target=EndpointVersion(2, 20, "PUBLISHED", ["PDF"], []),
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("PDF", "PDF", "DOCUMENT"),
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.INCOMPATIBLE
    assert decision.reason_code == "FORMAT_MISMATCH"


def test_supported_format_bridge_still_requires_mapping_transform():
    source_schema = _schema(100, "OUTPUT", {"id": {"type": "string"}})
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="XML",
        definition=source_schema.definition,
    )
    context = _context(
        target=EndpointVersion(2, 20, "PUBLISHED", ["XML"], []),
        target_schema=target_schema,
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("XML", "XML", "XML"),
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "MAPPING_REQUIRED"
