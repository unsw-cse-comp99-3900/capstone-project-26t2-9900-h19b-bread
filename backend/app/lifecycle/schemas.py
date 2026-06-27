from dataclasses import dataclass
from datetime import datetime

from app.lifecycle.enums import (
    ApiStatus,
    LifecycleAction,
    ValidationStage,
)


@dataclass(frozen=True)
class LifecycleResult:
    api_id: int
    status: ApiStatus
    message: str
    action: LifecycleAction | None = None
    version_id: int | None = None
    validation_run_id: int | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ValidationResultInput:
    passed: bool
    stage: ValidationStage
    message: str | None = None
    error_detail: str | None = None
