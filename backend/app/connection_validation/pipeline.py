from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.connection_validation.enums import (
    CompatibilityLevel,
    ConnectionValidationStage,
    ConnectionValidationStageStatus,
    ReasonSeverity,
)
from app.connection_validation.schemas import (
    ConnectionValidationContext,
    ConnectionValidationDecision,
    FormatAlias,
    ReasonItem,
    StageResult,
)


SchemaComparator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
TargetValidator = Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str | None]]

STAGE_ORDER = list(ConnectionValidationStage)
SUPPORTED_SCHEMA_FORMATS = {"JSON", "XML"}
MACHINE_READABLE_FORMAT_FAMILIES = {"JSON", "XML", "UBL"}


class ConnectionValidationPipeline:
    def __init__(
        self,
        compare_schemas: SchemaComparator,
        validate_target: TargetValidator,
    ) -> None:
        self.compare_schemas = compare_schemas
        self.validate_target = validate_target

    def run(self, context: ConnectionValidationContext) -> ConnectionValidationDecision:
        stages: list[StageResult] = []
        reasons: list[ReasonItem] = []

        eligibility = self._eligibility(context)
        stages.append(eligibility)
        if eligibility.status != ConnectionValidationStageStatus.PASSED:
            return self._halt(context, stages, reasons, eligibility)

        format_result = self._format_check(context)
        stages.append(format_result)
        if format_result.status != ConnectionValidationStageStatus.PASSED:
            return self._halt(context, stages, reasons, format_result)

        comparison = self.compare_schemas(
            context.source_schema.definition,
            context.target_schema.definition,
        )
        schema_result, schema_reasons, schema_mapping_required = self._schema_check(comparison)
        stages.append(schema_result)
        reasons.extend(schema_reasons)
        if schema_result.status != ConnectionValidationStageStatus.PASSED:
            return self._halt(context, stages, reasons, schema_result)

        mapping_required = bool(
            schema_mapping_required
            or format_result.payload.get("requires_format_transform")
        )

        mapping_result = self._mapping_check(context, mapping_required)
        stages.append(mapping_result)
        if mapping_result.status not in {
            ConnectionValidationStageStatus.PASSED,
            ConnectionValidationStageStatus.NOT_RUN,
        }:
            return self._halt(context, stages, reasons, mapping_result)

        target_result, transformed_data = self._target_validation(
            context,
            mapping_required,
        )
        stages.append(target_result)
        if target_result.status != ConnectionValidationStageStatus.PASSED:
            return self._halt(context, stages, reasons, target_result)

        reason_code = "COMPATIBLE_WITH_MAPPING" if mapping_required else "DIRECTLY_COMPATIBLE"
        reason = (
            "Source output can be accepted by the target after applying the complete mapping."
            if mapping_required
            else "Source output directly satisfies the target input contract."
        )
        stages.append(
            StageResult(
                stage=ConnectionValidationStage.ACTIVATION_GATE,
                status=ConnectionValidationStageStatus.PASSED,
                message="All required connection validation gates passed.",
            )
        )
        return ConnectionValidationDecision(
            compatibility_level=CompatibilityLevel.COMPATIBLE,
            reason_code=reason_code,
            reason=reason,
            activation_allowed=True,
            stages=stages,
            reasons=reasons,
            transformed_data=transformed_data,
        )

    def _eligibility(self, context: ConnectionValidationContext) -> StageResult:
        if context.source.api_id == context.target.api_id:
            return self._stage_failure(
                ConnectionValidationStage.ELIGIBILITY,
                "SOURCE_TARGET_SAME_API",
                "Source and target must be different APIs.",
            )
        if context.source.status != "PUBLISHED":
            return self._stage_failure(
                ConnectionValidationStage.ELIGIBILITY,
                "SOURCE_NOT_PUBLISHED",
                "Source version is not published.",
            )
        if context.target.status != "PUBLISHED":
            return self._stage_failure(
                ConnectionValidationStage.ELIGIBILITY,
                "TARGET_NOT_PUBLISHED",
                "Target version is not published.",
            )
        if context.source_schema is None:
            return self._stage_missing(
                ConnectionValidationStage.ELIGIBILITY,
                "SOURCE_OUTPUT_SCHEMA_MISSING",
                "Source version has no OUTPUT schema.",
            )
        if context.target_schema is None:
            return self._stage_missing(
                ConnectionValidationStage.ELIGIBILITY,
                "TARGET_INPUT_SCHEMA_MISSING",
                "Target version has no INPUT schema.",
            )
        if context.source_schema.direction != "OUTPUT":
            return self._stage_failure(
                ConnectionValidationStage.ELIGIBILITY,
                "INVALID_SOURCE_SCHEMA_DIRECTION",
                "Source schema must have OUTPUT direction.",
            )
        if context.target_schema.direction != "INPUT":
            return self._stage_failure(
                ConnectionValidationStage.ELIGIBILITY,
                "INVALID_TARGET_SCHEMA_DIRECTION",
                "Target schema must have INPUT direction.",
            )
        return StageResult(
            stage=ConnectionValidationStage.ELIGIBILITY,
            status=ConnectionValidationStageStatus.PASSED,
            message="The selected published versions satisfy OUTPUT to INPUT eligibility.",
        )

    def _format_check(self, context: ConnectionValidationContext) -> StageResult:
        if not context.source.output_formats:
            return self._stage_missing(
                ConnectionValidationStage.FORMAT_CHECK,
                "SOURCE_OUTPUT_FORMAT_MISSING",
                "Source version does not declare an output format.",
            )
        if not context.target.input_formats:
            return self._stage_missing(
                ConnectionValidationStage.FORMAT_CHECK,
                "TARGET_INPUT_FORMAT_MISSING",
                "Target version does not declare an input format.",
            )

        alias_index = {alias.raw_value.strip().casefold(): alias for alias in context.aliases}
        source_aliases, source_unknown = self._resolve_aliases(
            context.source.output_formats,
            alias_index,
        )
        target_aliases, target_unknown = self._resolve_aliases(
            context.target.input_formats,
            alias_index,
        )

        usable_source_aliases = [
            alias for alias in source_aliases if not alias.is_terminal_output
        ]
        terminal = sorted(
            alias.raw_value for alias in source_aliases if alias.is_terminal_output
        )
        source_tokens = {alias.normalized_value for alias in usable_source_aliases}
        target_tokens = {alias.normalized_value for alias in target_aliases}
        source_families = {alias.family for alias in usable_source_aliases}
        target_families = {alias.family for alias in target_aliases}
        diagnostics = {
            "ignored_terminal_source_formats": terminal,
            "unknown_source_formats": source_unknown,
            "unknown_target_formats": target_unknown,
        }
        if source_tokens & target_tokens or source_families & target_families:
            return StageResult(
                stage=ConnectionValidationStage.FORMAT_CHECK,
                status=ConnectionValidationStageStatus.PASSED,
                message="Source and target formats overlap after normalization.",
                payload={"requires_format_transform": False, **diagnostics},
            )

        source_schema_format = context.source_schema.format.upper()
        target_schema_format = context.target_schema.format.upper()
        has_machine_readable_path = all(
            any(
                alias.family in MACHINE_READABLE_FORMAT_FAMILIES
                for alias in aliases
            )
            for aliases in (usable_source_aliases, target_aliases)
        )
        if (
            usable_source_aliases
            and target_aliases
            and has_machine_readable_path
            and {source_schema_format, target_schema_format} <= SUPPORTED_SCHEMA_FORMATS
        ):
            return StageResult(
                stage=ConnectionValidationStage.FORMAT_CHECK,
                status=ConnectionValidationStageStatus.PASSED,
                message="Formats differ but the schema mapping engine supports this JSON/XML bridge.",
                payload={"requires_format_transform": True, **diagnostics},
            )
        if source_unknown or target_unknown:
            return self._stage_missing(
                ConnectionValidationStage.FORMAT_CHECK,
                "FORMAT_ALIAS_MISSING",
                "No known compatible path exists and one or more formats have no normalization rule.",
                diagnostics,
            )
        if terminal and not usable_source_aliases:
            return self._stage_failure(
                ConnectionValidationStage.FORMAT_CHECK,
                "SOURCE_OUTPUT_IS_TERMINAL_REPORT",
                "Source output is a terminal document or report and cannot feed another API.",
                {"terminal_formats": terminal},
            )
        return self._stage_failure(
            ConnectionValidationStage.FORMAT_CHECK,
            "FORMAT_MISMATCH",
            "Source output format cannot be consumed or transformed for the target input.",
            {
                "source_formats": sorted(source_tokens),
                "target_formats": sorted(target_tokens),
            },
        )

    def _schema_check(
        self,
        comparison: dict[str, Any],
    ) -> tuple[StageResult, list[ReasonItem], bool]:
        compatibility = comparison.get("compatibility")
        raw_issues = comparison.get("issues") or []
        reasons = [self._schema_reason(issue) for issue in raw_issues]
        payload = {
            "schema_compatibility": compatibility,
            "summary": comparison.get("summary") or {},
            "issues": [reason.model_dump(mode="json") for reason in reasons],
        }
        if compatibility == "directly_compatible":
            return (
                StageResult(
                    stage=ConnectionValidationStage.SCHEMA_CHECK,
                    status=ConnectionValidationStageStatus.PASSED,
                    message="Source schema directly satisfies the target schema.",
                    payload=payload,
                ),
                reasons,
                False,
            )
        if compatibility == "compatible_with_mapping":
            return (
                StageResult(
                    stage=ConnectionValidationStage.SCHEMA_CHECK,
                    status=ConnectionValidationStageStatus.PASSED,
                    message="Schema differences are potentially resolvable through mapping.",
                    payload=payload,
                ),
                reasons,
                True,
            )
        return (
            self._stage_failure(
                ConnectionValidationStage.SCHEMA_CHECK,
                "SCHEMA_INCOMPATIBLE",
                "Source schema has blocking conflicts with the target schema.",
                payload,
            ),
            reasons,
            False,
        )

    def _mapping_check(
        self,
        context: ConnectionValidationContext,
        mapping_required: bool,
    ) -> StageResult:
        if not mapping_required:
            return StageResult(
                stage=ConnectionValidationStage.MAPPING_CHECK,
                status=ConnectionValidationStageStatus.NOT_RUN,
                message="No mapping is required for directly compatible schemas.",
            )
        if context.mapping is None:
            return self._stage_missing(
                ConnectionValidationStage.MAPPING_CHECK,
                "MAPPING_REQUIRED",
                "A complete mapping is required before this pair can be activated.",
            )
        if context.mapping.completeness != "FULL":
            return self._stage_missing(
                ConnectionValidationStage.MAPPING_CHECK,
                "MAPPING_INCOMPLETE",
                "The selected mapping does not cover every required target field.",
                {"mapping_id": context.mapping.mapping_id},
            )
        if context.mapping.lifecycle_status in {"FAILED", "STALE", "DEPRECATED"}:
            return self._stage_failure(
                ConnectionValidationStage.MAPPING_CHECK,
                "MAPPING_NOT_USABLE",
                "The selected mapping lifecycle state does not permit validation.",
                {
                    "mapping_id": context.mapping.mapping_id,
                    "lifecycle_status": context.mapping.lifecycle_status,
                },
            )
        return StageResult(
            stage=ConnectionValidationStage.MAPPING_CHECK,
            status=ConnectionValidationStageStatus.PASSED,
            message="A complete mapping is available for the selected version pair.",
            payload={"mapping_id": context.mapping.mapping_id},
        )

    def _target_validation(
        self,
        context: ConnectionValidationContext,
        mapping_required: bool,
    ) -> tuple[StageResult, dict[str, Any] | None]:
        if context.sample_data is None:
            return (
                self._stage_missing(
                    ConnectionValidationStage.TARGET_VALIDATION,
                    "SAMPLE_DATA_MISSING",
                    "Sample source output is required for target acceptance validation.",
                ),
                None,
            )
        source_valid, source_error = self.validate_target(
            context.sample_data,
            context.source_schema.definition,
        )
        if not source_valid:
            return (
                self._stage_failure(
                    ConnectionValidationStage.TARGET_VALIDATION,
                    "SOURCE_VALIDATION_FAILED",
                    source_error
                    or "Sample output does not satisfy the source output schema.",
                    {"validation_scope": "SOURCE"},
                ),
                None,
            )
        transformed = context.sample_data
        if mapping_required:
            try:
                transformed = context.mapping.transform(context.sample_data)
            except Exception as exc:
                return (
                    self._stage_failure(
                        ConnectionValidationStage.TARGET_VALIDATION,
                        "TRANSFORM_FAILED",
                        "The mapping could not transform the sample source output.",
                        {"error": str(exc)},
                    ),
                    None,
                )
        valid, error = self.validate_target(transformed, context.target_schema.definition)
        if not valid:
            return (
                self._stage_failure(
                    ConnectionValidationStage.TARGET_VALIDATION,
                    "TARGET_VALIDATION_FAILED",
                    error or "Transformed output does not satisfy the target input schema.",
                ),
                transformed,
            )
        return (
            StageResult(
                stage=ConnectionValidationStage.TARGET_VALIDATION,
                status=ConnectionValidationStageStatus.PASSED,
                message="The resulting payload satisfies the target input schema.",
                payload={"validation_scope": "SOURCE_AND_TARGET"},
            ),
            transformed,
        )

    def _halt(
        self,
        context: ConnectionValidationContext,
        stages: list[StageResult],
        reasons: list[ReasonItem],
        blocker: StageResult,
    ) -> ConnectionValidationDecision:
        completed = {result.stage for result in stages}
        for stage in STAGE_ORDER:
            if stage not in completed:
                stages.append(
                    StageResult(
                        stage=stage,
                        status=ConnectionValidationStageStatus.NOT_RUN,
                        message="Skipped because an earlier validation gate did not pass.",
                    )
                )
        severity = (
            ReasonSeverity.WARNING
            if blocker.status == ConnectionValidationStageStatus.MISSING_INFORMATION
            else ReasonSeverity.ERROR
        )
        reasons.append(
            ReasonItem(
                reason_code=blocker.payload["reason_code"],
                stage=blocker.stage,
                severity=severity,
                message=blocker.message,
                details={
                    key: value
                    for key, value in blocker.payload.items()
                    if key != "reason_code"
                },
            )
        )
        level = (
            CompatibilityLevel.MISSING_INFORMATION
            if blocker.status == ConnectionValidationStageStatus.MISSING_INFORMATION
            else CompatibilityLevel.INCOMPATIBLE
        )
        return ConnectionValidationDecision(
            compatibility_level=level,
            reason_code=blocker.payload["reason_code"],
            reason=blocker.message,
            activation_allowed=False,
            stages=stages,
            reasons=reasons,
        )

    @staticmethod
    def _resolve_aliases(
        values: list[str],
        alias_index: dict[str, FormatAlias],
    ) -> tuple[list[FormatAlias], list[str]]:
        resolved: list[FormatAlias] = []
        unknown: list[str] = []
        for value in values:
            alias = alias_index.get(value.strip().casefold())
            if alias is None:
                unknown.append(value)
            else:
                resolved.append(alias)
        return resolved, unknown

    @staticmethod
    def _schema_reason(issue: dict[str, Any]) -> ReasonItem:
        code = re.sub(r"[^A-Z0-9]+", "_", str(issue.get("code", "SCHEMA_ISSUE")).upper()).strip("_")
        severity = {
            "error": ReasonSeverity.ERROR,
            "warning": ReasonSeverity.WARNING,
        }.get(str(issue.get("severity", "")).lower(), ReasonSeverity.INFO)
        return ReasonItem(
            reason_code=code or "SCHEMA_ISSUE",
            stage=ConnectionValidationStage.SCHEMA_CHECK,
            severity=severity,
            source_path=issue.get("source_path"),
            target_path=issue.get("target_path"),
            message=issue.get("message") or "Schema compatibility issue.",
            details={"kind": issue.get("kind"), "suggestion": issue.get("suggestion")},
        )

    @staticmethod
    def _stage_failure(
        stage: ConnectionValidationStage,
        reason_code: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> StageResult:
        return StageResult(
            stage=stage,
            status=ConnectionValidationStageStatus.FAILED,
            message=message,
            payload={"reason_code": reason_code, **(payload or {})},
        )

    @staticmethod
    def _stage_missing(
        stage: ConnectionValidationStage,
        reason_code: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> StageResult:
        return StageResult(
            stage=stage,
            status=ConnectionValidationStageStatus.MISSING_INFORMATION,
            message=message,
            payload={"reason_code": reason_code, **(payload or {})},
        )
