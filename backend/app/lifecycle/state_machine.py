from app.lifecycle.enums import ApiStatus
from app.lifecycle.exceptions import InvalidStatusTransitionError


ALLOWED_TRANSITIONS: dict[ApiStatus, set[ApiStatus]] = {
    ApiStatus.DRAFT: {ApiStatus.VALIDATING},
    ApiStatus.VALIDATING: {ApiStatus.PUBLISHED, ApiStatus.REJECTED},
    ApiStatus.REJECTED: {ApiStatus.VALIDATING, ApiStatus.WITHDRAWN},
    ApiStatus.PUBLISHED: {ApiStatus.WITHDRAWN},
    ApiStatus.WITHDRAWN: set(),
}


def can_transition(from_status: ApiStatus, to_status: ApiStatus) -> bool:
    return to_status in ALLOWED_TRANSITIONS[from_status]


def ensure_transition_allowed(
    from_status: ApiStatus,
    to_status: ApiStatus,
) -> None:
    if not can_transition(from_status, to_status):
        raise InvalidStatusTransitionError(from_status, to_status)
