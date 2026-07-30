import json
from pathlib import Path

from app.connection_validation import (
    CompatibilityLevel,
    ConnectionValidationContext,
    ConnectionValidationPipeline,
    EndpointVersion,
    FormatAlias,
    MappingContext,
    PayloadSchema,
)
from app.services.schema_mapping.compatibility_engine import (
    compare_schemas,
    normalize_schema,
)
from app.services.schema_mapping.data_validator import validate_data
from app.services.schema_mapping.json_schema_extractor import infer_schema
from app.services.schema_mapping.mapping_engine import build_mapping
from app.services.schema_mapping.schema_transformer import build_transformer
from app.services.schema_mapping.xml_schema_extractor import extract_schema_from_xml


FIXTURES = Path(__file__).parent / "fixtures"
ALIASES = [
    FormatAlias("JSON", "JSON", "JSON"),
    FormatAlias("XML", "XML", "XML"),
]


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _pipeline() -> ConnectionValidationPipeline:
    return ConnectionValidationPipeline(compare_schemas, validate_data)


def _mapping_context(source: dict, target: dict) -> tuple[MappingContext, dict]:
    comparison = compare_schemas(source, target, "Source", "Target")
    mapping = build_mapping(comparison)
    return (
        MappingContext(
            mapping_id=7,
            lifecycle_status="DRAFT",
            completeness="FULL",
            transform=build_transformer(mapping),
        ),
        comparison,
    )


def test_ess_aggregation_json_to_xml_passes_mapping_and_target_acceptance():
    sample = _load_json("ess_aggregation.json")
    source_definition = normalize_schema(infer_schema(sample))
    target_definition = normalize_schema(
        extract_schema_from_xml(
            (FIXTURES / "ess_aggregation.xml").read_text(encoding="utf-8")
        )
    )
    mapping, comparison = _mapping_context(source_definition, target_definition)

    decision = _pipeline().run(
        ConnectionValidationContext(
            source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
            target=EndpointVersion(2, 20, "PUBLISHED", ["XML"], []),
            source_schema=PayloadSchema(
                100, "OUTPUT", "JSON", source_definition, "aggregation"
            ),
            target_schema=PayloadSchema(
                200, "INPUT", "XML", target_definition, "aggregation"
            ),
            aliases=ALIASES,
            mapping=mapping,
            sample_data=sample,
        )
    )

    assert comparison["compatibility"] == "compatible_with_mapping"
    assert {issue["code"] for issue in comparison["issues"]} == {
        "type_conversion_required"
    }
    assert decision.compatibility_level == CompatibilityLevel.COMPATIBLE
    assert decision.reason_code == "COMPATIBLE_WITH_MAPPING"
    assert decision.activation_allowed is True
    assert decision.transform_execution is not None
    assert decision.transform_execution.output_text.startswith("<aggregation>")
    assert "<value>1523847.92</value>" in decision.transform_execution.output_text


def test_ess_validation_version_pair_passes_rename_mapping():
    sample = _load_json("ess_validation1.json")
    source_definition = normalize_schema(infer_schema(sample))
    target_definition = normalize_schema(
        infer_schema(_load_json("ess_validation2.json"))
    )
    mapping, comparison = _mapping_context(source_definition, target_definition)

    decision = _pipeline().run(
        ConnectionValidationContext(
            source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
            target=EndpointVersion(2, 20, "PUBLISHED", ["JSON"], []),
            source_schema=PayloadSchema(100, "OUTPUT", "JSON", source_definition),
            target_schema=PayloadSchema(200, "INPUT", "JSON", target_definition),
            aliases=ALIASES,
            mapping=mapping,
            sample_data=sample,
        )
    )

    mapped_paths = {
        (issue["source_path"], issue["target_path"])
        for issue in comparison["issues"]
        if issue["code"] == "field_mapping_required"
    }
    assert mapped_paths == {("id", "ID"), ("rule", "rules")}
    assert decision.reason_code == "COMPATIBLE_WITH_MAPPING"
    assert decision.activation_allowed is True
    assert decision.transformed_data["ID"] == sample["id"]
    assert decision.transformed_data["rules"] == sample["rule"]


def test_ess_cross_domain_pair_is_rejected_with_structured_schema_issues():
    source_sample = _load_json("ess_aggregation.json")
    source_definition = normalize_schema(infer_schema(source_sample))
    target_definition = normalize_schema(
        infer_schema(_load_json("ess_validation1.json"))
    )

    decision = _pipeline().run(
        ConnectionValidationContext(
            source=EndpointVersion(1, 10, "PUBLISHED", [], ["JSON"]),
            target=EndpointVersion(2, 20, "PUBLISHED", ["JSON"], []),
            source_schema=PayloadSchema(100, "OUTPUT", "JSON", source_definition),
            target_schema=PayloadSchema(200, "INPUT", "JSON", target_definition),
            aliases=ALIASES,
            sample_data=source_sample,
        )
    )

    assert decision.compatibility_level == CompatibilityLevel.INCOMPATIBLE
    assert decision.reason_code == "SCHEMA_INCOMPATIBLE"
    assert decision.activation_allowed is False
    assert decision.reasons
    assert any(reason.target_path == "rule" for reason in decision.reasons)
