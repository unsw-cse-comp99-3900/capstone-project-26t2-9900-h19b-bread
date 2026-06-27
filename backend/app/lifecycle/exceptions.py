from app.lifecycle.enums import ApiStatus


class LifecycleError(Exception):
    """Base class for lifecycle domain errors."""


class InvalidStatusTransitionError(LifecycleError):
    def __init__(self, from_status: ApiStatus, to_status: ApiStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid API lifecycle transition: {from_status.value} -> {to_status.value}"
        )
