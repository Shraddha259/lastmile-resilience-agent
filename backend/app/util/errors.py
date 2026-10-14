"""Application errors rendered in the PRD §11.1 error shape."""

from typing import Any


class AppError(Exception):
    """Base error with an HTTP status and a PRD error code."""

    status_code = 500
    code = "INTERNAL"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class Unauthorized(AppError):
    status_code, code = 401, "UNAUTHORIZED"


class NotFound(AppError):
    status_code, code = 404, "NOT_FOUND"


class ValidationFailed(AppError):
    status_code, code = 422, "VALIDATION_ERROR"


class InvalidTransition(AppError):
    status_code, code = 409, "INVALID_TRANSITION"


class VersionConflict(AppError):
    status_code, code = 409, "VERSION_CONFLICT"


class IncidentNotActive(AppError):
    status_code, code = 409, "INCIDENT_NOT_ACTIVE"


class ActiveIncidentExists(AppError):
    status_code, code = 409, "ACTIVE_INCIDENT_EXISTS"


class UpstreamModelError(AppError):
    status_code, code = 502, "UPSTREAM_MODEL_ERROR"
