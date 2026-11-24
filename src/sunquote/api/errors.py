"""Error mapping: every failure becomes an RFC 9457 `application/problem+json` response.

Each problem has a stable `type` URN, so clients can branch on it. To add one, add a
`ProblemType` and register the exception that maps to it in `PROBLEMS_BY_EXCEPTION`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sunquote.domain import rounding
from sunquote.domain.errors import (
    AddressNotFoundError,
    AssistantNotConfiguredError,
    ConversationUnavailableError,
    DomainError,
    LocationNotSupportedError,
    NoCompatibleInverterError,
    NoViableSystemError,
    QuoteNotFoundError,
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
ADDRESS_NOT_FOUND = ProblemType("address-not-found", "Address not found", 422)
QUOTE_NOT_FOUND = ProblemType("quote-not-found", "Quote not found", 404)
UPSTREAM_UNAVAILABLE = ProblemType("upstream-unavailable", "Upstream service unavailable", 503)
# Only ever a tool error of the quote assistant, never an HTTP response.
QUOTE_ALREADY_CREATED = ProblemType("quote-already-created", "A Quote was already created", 409)
ASSISTANT_NOT_CONFIGURED = ProblemType("assistant-not-configured", "Assistant not configured", 503)
ASSISTANT_UNAVAILABLE = ProblemType("assistant-unavailable", "Assistant unavailable", 503)

PROBLEMS_BY_EXCEPTION: dict[type[DomainError], ProblemType] = {
    UnsupportedSubscriberGroupError: UNSUPPORTED_SUBSCRIBER_GROUP,
    NoViableSystemError: NO_VIABLE_SYSTEM,
    NoCompatibleInverterError: NO_COMPATIBLE_INVERTER,
    LocationNotSupportedError: LOCATION_NOT_SUPPORTED,
    AddressNotFoundError: ADDRESS_NOT_FOUND,
    UpstreamUnavailableError: UPSTREAM_UNAVAILABLE,
    QuoteNotFoundError: QUOTE_NOT_FOUND,
    AssistantNotConfiguredError: ASSISTANT_NOT_CONFIGURED,
    ConversationUnavailableError: ASSISTANT_UNAVAILABLE,
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
    # The first element says where the field was read from; the field name is what matters.
    named = location[1:] if location and location[0] in ("body", "path", "query") else location
    parts = [str(part) for part in named]
    return ".".join(parts) if parts else "body"


def field_errors(items: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Pydantic's error items as `{field, message}` entries, in the problem body's format."""
    return [
        {
            "field": _field_path(item["loc"]),
            "message": item["msg"].removeprefix("Value error, "),
        }
        for item in items
    ]


async def _handle_validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    errors = field_errors(error.errors())
    return problem_response(
        VALIDATION_ERROR,
        f"{len(errors)} field(s) failed validation: " + ", ".join(e["field"] for e in errors),
        errors=errors,
    )


def error_detail(error: DomainError) -> str:
    """The error's message, with any figure it carries shown through the rounding policy."""
    if isinstance(error, NoCompatibleInverterError):
        capacity_kwp = rounding.round_capacity_kwp(error.capacity_kwp)
        return (
            f"no compatible inverter: none of the catalog inverters fits a {capacity_kwp} kWp "
            "system within the allowed DC/AC Ratio and the Contracted Power"
        )
    return str(error)


async def _handle_domain_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    problem_type = PROBLEMS_BY_EXCEPTION[type(error)]
    return problem_response(problem_type, error_detail(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    for exception_type in PROBLEMS_BY_EXCEPTION:
        app.add_exception_handler(exception_type, _handle_domain_error)
