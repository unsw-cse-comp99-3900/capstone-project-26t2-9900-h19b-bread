from app.lifecycle.enums import ApiStatus


class LifecycleError(Exception):
    """Base class for lifecycle domain errors."""


class ApiNotFoundError(LifecycleError):
    def __init__(self, api_id: int) -> None:
        self.api_id = api_id
        super().__init__(f"API submission not found: {api_id}")


class CurrentVersionNotFoundError(LifecycleError):
    def __init__(self, api_id: int) -> None:
        self.api_id = api_id
        super().__init__(f"Current API version not found for API submission: {api_id}")


class ApiPermissionError(LifecycleError):
    def __init__(self) -> None:
        super().__init__("Only the API creator or an administrator may change lifecycle state")


class InvalidStatusTransitionError(LifecycleError):
    def __init__(self, from_status: ApiStatus, to_status: ApiStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid API lifecycle transition: {from_status.value} -> {to_status.value}"
        )
