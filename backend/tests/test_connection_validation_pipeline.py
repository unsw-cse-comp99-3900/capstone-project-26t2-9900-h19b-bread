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
from app.services.schema_mapping.mapping_engine import FieldMapping, SchemaMapping
from app.services.schema_mapping.schema_transformer import build_transformer


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


def _object_definition(properties: dict, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
    }


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


def test_multi_format_pair_uses_non_terminal_compatible_output():
    context = _context(
        source=EndpointVersion(
            1,
            10,
            "PUBLISHED",
            [],
            ["JSON", "Validation Report"],
        ),
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias(
                "Validation Report",
                "VALIDATION_REPORT",
                "REPORT",
                is_terminal_output=True,
            ),
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.COMPATIBLE
    assert decision.reason_code == "DIRECTLY_COMPATIBLE"
    assert decision.stages[1].payload["ignored_terminal_source_formats"] == [
        "Validation Report"
    ]


def test_same_api_different_versions_passes_eligibility():
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
        target=EndpointVersion(1, 20, "PUBLISHED", ["JSON"], []),
    )

    decision = _pipeline().run(context)

    assert decision.activation_allowed is True
    assert decision.stages[0].status == ConnectionValidationStageStatus.PASSED


def test_same_version_is_rejected_during_eligibility():
    context = _context(
        target=EndpointVersion(1, 10, "PUBLISHED", ["JSON"], []),
    )

    decision = _pipeline().run(context)

    assert decision.activation_allowed is False
    assert decision.reason_code == "SOURCE_TARGET_SAME_VERSION"
    assert decision.stages[0].status == ConnectionValidationStageStatus.FAILED


def test_multi_format_pair_ignores_unknown_format_when_known_path_exists():
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["Custom", "JSON"]),
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.COMPATIBLE
    assert decision.reason_code == "DIRECTLY_COMPATIBLE"
    assert decision.stages[1].payload["unknown_source_formats"] == ["Custom"]


def test_unknown_format_blocks_when_no_known_path_exists():
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["Custom"]),
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "FORMAT_ALIAS_MISSING"


def test_empty_source_output_formats_stops_pipeline_as_missing_information():
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], []),
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "SOURCE_OUTPUT_FORMAT_MISSING"
    assert decision.activation_allowed is False
    assert decision.stages[1].status == ConnectionValidationStageStatus.MISSING_INFORMATION
    assert all(
        stage.status == ConnectionValidationStageStatus.NOT_RUN
        for stage in decision.stages[2:5]
    )


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
    schema_issues = decision.stages[2].payload["issues"]
    assert schema_issues
    assert schema_issues[0]["stage"] == "SCHEMA_CHECK"
    assert schema_issues[0]["target_path"] == "invoice_id"


def test_required_target_field_optional_in_source_requires_mapping():
    source = PayloadSchema(
        schema_id=100,
        direction="OUTPUT",
        format="JSON",
        definition={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": [],
        },
    )
    target = _schema(200, "INPUT", {"id": {"type": "string"}})

    decision = _pipeline().run(_context(source_schema=source, target_schema=target))

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "MAPPING_REQUIRED"
    issues = decision.stages[2].payload["issues"]
    assert [issue["reason_code"] for issue in issues] == [
        "REQUIRED_OPTIONAL_CONFLICT"
    ]
    assert issues[0]["source_path"] == "id"
    assert issues[0]["target_path"] == "id"


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


def test_target_validation_failure_keeps_failed_transform_audit():
    target = _schema(200, "INPUT", {"invoice_id": {"type": "string"}})
    mapping = MappingContext(
        mapping_id=7,
        lifecycle_status="DRAFT",
        completeness="FULL",
        transform=lambda data: {"wrong_field": data["id"]},
    )

    decision = _pipeline().run(_context(target_schema=target, mapping=mapping))

    assert decision.reason_code == "TARGET_VALIDATION_FAILED"
    assert decision.transform_execution is not None
    assert decision.transform_execution.success is False
    assert decision.transform_execution.output_data == {"wrong_field": "INV-1"}
    assert decision.transform_execution.error_message


def test_invalid_source_sample_stops_before_mapping_transform():
    target = _schema(200, "INPUT", {"invoice_id": {"type": "string"}})
    transform_calls = []
    mapping = MappingContext(
        mapping_id=7,
        lifecycle_status="DRAFT",
        completeness="FULL",
        transform=lambda data: transform_calls.append(data) or {"invoice_id": "INV-1"},
    )

    decision = _pipeline().run(
        _context(
            target_schema=target,
            mapping=mapping,
            sample_data={"unexpected": "value"},
        )
    )

    assert decision.compatibility_level == CompatibilityLevel.INCOMPATIBLE
    assert decision.reason_code == "SOURCE_VALIDATION_FAILED"
    assert decision.stages[4].payload["validation_scope"] == "SOURCE"
    assert decision.stages[5].status == ConnectionValidationStageStatus.NOT_RUN
    assert transform_calls == []


def test_array_mapping_output_passes_target_validation():
    source_schema = PayloadSchema(
        schema_id=100,
        direction="OUTPUT",
        format="JSON",
        definition=_object_definition(
            {
                "lines": {
                    "type": "array",
                    "items": _object_definition({"id": {"type": "string"}}),
                }
            }
        ),
    )
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="JSON",
        definition=_object_definition(
            {
                "items": {
                    "type": "array",
                    "items": _object_definition(
                        {"identifier": {"type": "string"}}
                    ),
                }
            }
        ),
    )
    mapping = SchemaMapping(
        source="Source",
        target="Target",
        status="full",
        fields=[
            FieldMapping(
                source_path="lines[].id",
                target_path="items[].identifier",
                transform="rename",
                source_type="string",
                target_type="string",
                confidence="high",
                note="Map array item identifier.",
            )
        ],
    )
    context = _context(
        source_schema=source_schema,
        target_schema=target_schema,
        mapping=MappingContext(
            mapping_id=7,
            lifecycle_status="DRAFT",
            completeness="FULL",
            transform=build_transformer(mapping),
        ),
        sample_data={"lines": [{"id": "A"}, {"id": "B"}]},
    )

    decision = _pipeline().run(context)

    assert decision.reason_code == "COMPATIBLE_WITH_MAPPING"
    assert decision.activation_allowed is True
    assert decision.transformed_data == {
        "items": [{"identifier": "A"}, {"identifier": "B"}]
    }
    assert decision.stages[2].payload["requires_mapping_proof"] is True


def test_blocking_schema_conflict_without_mapping_remains_incompatible():
    source_schema = _schema(100, "OUTPUT", {"source_only": {"type": "object"}})
    target_schema = _schema(200, "INPUT", {"required_target": {"type": "array"}})

    decision = _pipeline().run(
        _context(
            source_schema=source_schema,
            target_schema=target_schema,
            sample_data={"source_only": {}},
        )
    )

    assert decision.reason_code == "SCHEMA_INCOMPATIBLE"
    assert decision.activation_allowed is False


def test_blocking_schema_conflict_with_partial_mapping_remains_incompatible():
    source_schema = _schema(100, "OUTPUT", {"source_only": {"type": "object"}})
    target_schema = _schema(200, "INPUT", {"required_target": {"type": "array"}})
    partial_mapping = MappingContext(
        mapping_id=7,
        lifecycle_status="VALIDATING",
        completeness="PARTIAL",
        transform=lambda data: data,
    )

    decision = _pipeline().run(
        _context(
            source_schema=source_schema,
            target_schema=target_schema,
            mapping=partial_mapping,
            sample_data={"source_only": {}},
        )
    )

    assert decision.compatibility_level == CompatibilityLevel.INCOMPATIBLE
    assert decision.reason_code == "SCHEMA_INCOMPATIBLE"
    assert decision.activation_allowed is False


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


def test_supported_bridge_uses_machine_readable_option_from_mixed_formats():
    source_schema = _schema(100, "OUTPUT", {"id": {"type": "string"}})
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="XML",
        definition=source_schema.definition,
    )
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON", "PDF"]),
        target=EndpointVersion(2, 20, "PUBLISHED", ["XML"], []),
        target_schema=target_schema,
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("PDF", "PDF", "DOCUMENT"),
            FormatAlias("XML", "XML", "XML"),
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "MAPPING_REQUIRED"
    assert decision.stages[1].payload["requires_format_transform"] is True


def test_selected_schema_formats_require_transform_despite_version_format_overlap():
    source_schema = PayloadSchema(
        schema_id=100,
        direction="OUTPUT",
        format="XML",
        definition=_object_definition({"id": {"type": "string"}}),
    )
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="JSON",
        definition=source_schema.definition,
    )
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON", "XML"]),
        target=EndpointVersion(2, 20, "PUBLISHED", ["JSON", "XML"], []),
        source_schema=source_schema,
        target_schema=target_schema,
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("XML", "XML", "XML"),
        ],
    )

    decision = _pipeline().run(context)

    assert decision.compatibility_level == CompatibilityLevel.MISSING_INFORMATION
    assert decision.reason_code == "MAPPING_REQUIRED"
    assert decision.stages[1].payload["requires_format_transform"] is True
    assert decision.stages[1].payload["source_schema_format"] == "XML"
    assert decision.stages[1].payload["target_schema_format"] == "JSON"


def test_supported_bridge_materializes_target_xml_output():
    source_schema = _schema(100, "OUTPUT", {"id": {"type": "string"}})
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="XML",
        definition=source_schema.definition,
        root_path="invoice",
    )
    mapping = MappingContext(
        mapping_id=7,
        lifecycle_status="DRAFT",
        completeness="FULL",
        transform=lambda data: data,
    )
    context = _context(
        target=EndpointVersion(2, 20, "PUBLISHED", ["XML"], []),
        target_schema=target_schema,
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("XML", "XML", "XML"),
        ],
        mapping=mapping,
    )

    decision = _pipeline().run(context)

    assert decision.reason_code == "COMPATIBLE_WITH_MAPPING"
    assert decision.transform_execution is not None
    assert decision.transform_execution.success is True
    assert decision.transform_execution.output_format == "XML"
    assert decision.transform_execution.output_data is None
    assert decision.transform_execution.output_text.startswith("<invoice>")
    assert "<id>INV-1</id>" in decision.transform_execution.output_text


def test_xml_materialization_rejects_invalid_element_names():
    source_schema = _schema(100, "OUTPUT", {"bad key": {"type": "string"}})
    target_schema = PayloadSchema(
        schema_id=200,
        direction="INPUT",
        format="XML",
        definition=source_schema.definition,
        root_path="invoice",
    )
    context = _context(
        source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
        target=EndpointVersion(2, 20, "PUBLISHED", ["XML"], []),
        source_schema=source_schema,
        target_schema=target_schema,
        aliases=[
            FormatAlias("JSON", "JSON", "JSON"),
            FormatAlias("XML", "XML", "XML"),
        ],
        mapping=MappingContext(
            mapping_id=7,
            lifecycle_status="DRAFT",
            completeness="FULL",
            transform=lambda data: data,
        ),
        sample_data={"bad key": "value"},
    )

    decision = _pipeline().run(context)

    assert decision.reason_code == "TRANSFORM_FAILED"
    assert decision.transform_execution is not None
    assert decision.transform_execution.success is False
    assert "valid XML element name" in decision.transform_execution.error_message
