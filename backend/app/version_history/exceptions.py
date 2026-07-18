class VersionHistoryError(RuntimeError):
    """Base error for version-history operations."""


class VersionNotFoundError(VersionHistoryError):
    def __init__(self, api_id: int, version_id: int | None = None) -> None:
        target = f"API {api_id}" if version_id is None else f"version {version_id} for API {api_id}"
        super().__init__(f"{target} was not found")


class VersionConflictError(VersionHistoryError):
    pass


class HistoryAccessDeniedError(VersionHistoryError):
    pass
