class VersionHistoryError(Exception):
    status_code = 400


class ApiNotFoundError(VersionHistoryError):
    status_code = 404

    def __init__(self, api_id: int) -> None:
        super().__init__(f"API {api_id} was not found.")


class VersionNotFoundError(VersionHistoryError):
    status_code = 404

    def __init__(self, api_id: int, version_id: int) -> None:
        super().__init__(f"Version {version_id} was not found for API {api_id}.")


class VersionPermissionError(VersionHistoryError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("Only the API creator or an administrator may change versions.")


class VersionConflictError(VersionHistoryError):
    status_code = 409
