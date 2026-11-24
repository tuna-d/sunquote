"""Error mapping: every failure becomes an RFC 9457 `application/problem+json` response.

Each problem has a stable `type` URN, so clients can branch on it. To add one, add a
`ProblemType` and register the exception that maps to it in `PROBLEMS_BY_EXCEPTION`.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sunquote.domain.errors import (
    DomainError,
    LocationNotSupportedError,
    NoCompatibleInverterError,
    NoViableSystemError,
    UnsupportedSubscriberGroupError,
    UpstreamUnavailableError,
)

PROBLEM_JSON = "application/problem+json"


@dataclass(frozen=True)
class ProblemType:
    slug: str
    title: str
    status: int

    @property
    def type_uri(self) -> str:
        return f"urn:sunquote:problem:{self.slug}"


VALIDATION_ERROR = ProblemType("validation-error", "Request validation failed", 422)
UNSUPPORTED_SUBSCRIBER_GROUP = ProblemType(
    "unsupported-subscriber-group", "Unsupported Subscriber Group", 422
)
NO_VIABLE_SYSTEM = ProblemType("no-viable-system", "No viable system", 422)
NO_COMPATIBLE_INVERTER = ProblemType("no-compatible-inverter", "No compatible inverter", 422)
LOCATION_NOT_SUPPORTED = ProblemType("location-not-supported", "Location not supported", 422)
UPSTREAM_UNAVAILABLE = ProblemType("upstream-unavailable", "Upstream service unavailable", 503)

PROBLEMS_BY_EXCEPTION: dict[type[DomainError], ProblemType] = {
    UnsupportedSubscriberGroupError: UNSUPPORTED_SUBSCRIBER_GROUP,
    NoViableSystemError: NO_VIABLE_SYSTEM,
    NoCompatibleInverterError: NO_COMPATIBLE_INVERTER,
    LocationNotSupportedError: LOCATION_NOT_SUPPORTED,
    UpstreamUnavailableError: UPSTREAM_UNAVAILABLE,
}


class FieldError(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    """The body of a problem response, as documented in OpenAPI."""

    type: str
    title: str
    status: int
    detail: str
    errors: list[FieldError] | None = None


def problem_response(problem_type: ProblemType, detail: str, **extra: Any) -> JSONResponse:
    body = {
        "type": problem_type.type_uri,
        "title": problem_type.title,
        "status": problem_type.status,
        "detail": detail,
        **extra,
    }
    return JSONResponse(body, status_code=problem_type.status, media_type=PROBLEM_JSON)


def problem_responses(*problem_types: ProblemType) -> dict[int | str, dict[str, Any]]:
    """The `responses=` entry that documents problem statuses on a route."""
    return {
        status: {
            "model": Problem,
            "description": " / ".join(p.title for p in problem_types if p.status == status),
            "content": {PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in sorted({p.status for p in problem_types})
    }


def _field_path(location: tuple[int | str, ...]) -> str:
    parts = [str(part) for part in location if part != "body"]
    return ".".join(parts) if parts else "body"


async def _handle_validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    errors = [
        {
            "field": _field_path(item["loc"]),
            "message": item["msg"].removeprefix("Value error, "),
        }
        for item in error.errors()
    ]
    return problem_response(
        VALIDATION_ERROR,
        f"{len(errors)} field(s) failed validation: " + ", ".join(e["field"] for e in errors),
        errors=errors,
    )


async def _handle_domain_error(_: Request, error: Exception) -> JSONResponse:
    problem_type = PROBLEMS_BY_EXCEPTION[type(error)]  # type: ignore[index]
    return problem_response(problem_type, str(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    for exception_type in PROBLEMS_BY_EXCEPTION:
        app.add_exception_handler(exception_type, _handle_domain_error)
