"""Typed domain errors shared by every interface.

The CLI, HTTP and MCP adapters wrap a DomainError in their own transport envelope but
always carry the same `code`, `message`, `field` and `errors` content.
"""

from __future__ import annotations

from typing import Any

INVALID_INPUT = "INVALID_INPUT"
INVALID_GEOMETRY = "INVALID_GEOMETRY"
UNSUPPORTED_FRAME = "UNSUPPORTED_FRAME"
UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
INVALID_PITCH = "INVALID_PITCH"
RESOURCE_LIMIT = "RESOURCE_LIMIT"
REVISION_CONFLICT = "REVISION_CONFLICT"
PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
INVALID_CURSOR = "INVALID_CURSOR"
UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
VERIFICATION_FAILED = "VERIFICATION_FAILED"
INTERNAL_ERROR = "INTERNAL_ERROR"

ALL_CODES = (
    INVALID_INPUT,
    INVALID_GEOMETRY,
    UNSUPPORTED_FRAME,
    UNSUPPORTED_INPUT,
    INVALID_PITCH,
    RESOURCE_LIMIT,
    REVISION_CONFLICT,
    PROJECT_NOT_FOUND,
    RESULT_NOT_FOUND,
    INVALID_CURSOR,
    UNSUPPORTED_OPERATION,
    VERIFICATION_FAILED,
    INTERNAL_ERROR,
)

# HTTP status for each domain code; MCP and the CLI carry the code itself.
HTTP_STATUS = {
    INVALID_INPUT: 422,
    INVALID_GEOMETRY: 422,
    UNSUPPORTED_FRAME: 422,
    UNSUPPORTED_INPUT: 422,
    INVALID_PITCH: 422,
    RESOURCE_LIMIT: 413,
    REVISION_CONFLICT: 409,
    PROJECT_NOT_FOUND: 404,
    RESULT_NOT_FOUND: 404,
    INVALID_CURSOR: 400,
    UNSUPPORTED_OPERATION: 400,
    VERIFICATION_FAILED: 500,
    INTERNAL_ERROR: 500,
}


class FieldError:
    __slots__ = ("code", "field", "message", "details")

    def __init__(self, code: str, field: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.field = field
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "field": self.field, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
        errors: list[FieldError] | None = None,
    ):
        super().__init__(message)
        assert code in ALL_CODES, code
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
        self.errors = errors or []

    @classmethod
    def from_field_errors(cls, errors: list[FieldError]) -> "DomainError":
        first = errors[0]
        message = first.message if len(errors) == 1 else f"{first.message} (and {len(errors) - 1} more)"
        return cls(first.code, message, field=first.field, details=first.details, errors=errors)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field is not None:
            out["field"] = self.field
        if self.details:
            out["details"] = self.details
        if self.errors:
            out["errors"] = [e.to_dict() for e in self.errors]
        return out
