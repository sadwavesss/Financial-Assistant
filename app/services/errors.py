"""Business errors. Their messages are shown to the user, so they are written in Russian."""

from typing import Any


class ServiceError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


class NotFoundError(ServiceError):
    status_code = 404
    code = "not_found"


class InvalidDataError(ServiceError):
    status_code = 422
    code = "invalid_data"

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "field": self.field}
