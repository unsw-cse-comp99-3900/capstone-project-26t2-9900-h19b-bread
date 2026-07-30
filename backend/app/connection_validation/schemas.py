from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.connection_validation.enums import (
    CompatibilityLevel,
    ConnectionValidationStage,
    ConnectionValidationStageStatus,
    ConnectionValidationTrigger,
    ReasonSeverity,
)


class ConnectionValidationRequest(BaseModel):
    source_api_id: int = Field(..., gt=0)
    source_version_id: int = Field(..., gt=0)
    target_api_id: int = Field(..., gt=0)
    target_version_id: int = Field(..., gt=0)
    sample_data: dict[str, Any] | None = None
    trigger_type: ConnectionValidationTrigger = ConnectionValidationTrigger.MANUAL


class StageResult(BaseModel):
    stage: ConnectionValidationStage
    status: ConnectionValidationStageStatus
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ReasonItem(BaseModel):
    reason_code: str
    stage: ConnectionValidationStage
    severity: ReasonSeverity
    message: str
    source_path: str | None = None
    target_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectionValidationResponse(BaseModel):
    connection_validation_run_id: int
    compatibility_result_id: int
    compatibility_level: CompatibilityLevel
    reason_code: str
    reason: str
    activation_allowed: bool
    source_api_id: int
    source_version_id: int
    target_api_id: int
    target_version_id: int
    source_schema_id: int | None = None
    target_schema_id: int | None = None
    stages: list[StageResult]
    reasons: list[ReasonItem]


@dataclass(frozen=True)
class EndpointVersion:
    api_id: int
    version_id: int
    status: str
    input_formats: list[str]
    output_formats: list[str]


@dataclass(frozen=True)
class PayloadSchema:
    schema_id: int
    direction: str
    format: str
    definition: dict[str, Any]


@dataclass(frozen=True)
class FormatAlias:
    raw_value: str
    normalized_value: str
    family: str
    is_terminal_output: bool = False


@dataclass(frozen=True)
class MappingContext:
    mapping_id: int
    lifecycle_status: str
    completeness: str
    transform: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ConnectionValidationContext:
    source: EndpointVersion
    target: EndpointVersion
    source_schema: PayloadSchema | None
    target_schema: PayloadSchema | None
    aliases: list[FormatAlias]
    mapping: MappingContext | None = None
    sample_data: dict[str, Any] | None = None


@dataclass
class ConnectionValidationDecision:
    compatibility_level: CompatibilityLevel
    reason_code: str
    reason: str
    activation_allowed: bool
    stages: list[StageResult]
    reasons: list[ReasonItem] = field(default_factory=list)
    transformed_data: dict[str, Any] | None = None
