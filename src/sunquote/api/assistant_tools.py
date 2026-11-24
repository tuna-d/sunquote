"""The `create_quote` tool of the quote assistant.

Its parameters are the `POST /quotes` request model's JSON Schema, flattened for a model to read
and without what the model must never supply: Coordinates and an Exchange Rate override. The
Address is required instead, so every Quote the assistant creates is geocoded. Its arguments are
validated by the same request model before the quote-creation service is called.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from sunquote.api.errors import (
    PROBLEMS_BY_EXCEPTION,
    QUOTE_ALREADY_CREATED,
    VALIDATION_ERROR,
    ProblemType,
    error_detail,
    field_errors,
)
from sunquote.api.schemas import QuoteRequestBody
from sunquote.domain.conversation import REPLY_MAX_CHARACTERS, ToolDeclaration
from sunquote.domain.errors import DomainError
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.ports import StoredQuote
from sunquote.domain.service import QuoteService

CREATE_QUOTE = "create_quote"

CREATE_QUOTE_DESCRIPTION = (
    "Create a solar panel Quote for a Customer from the Sales Rep's description. Call it once, "
    "when every required value is known; it geocodes the Address, estimates the production, "
    "prices the system and stores the Quote."
)
_ADDRESS_DESCRIPTION = (
    "The place of the Site exactly as the Sales Rep wrote it (street, district, province). "
    "Never a guess at coordinates."
)
_COORDINATES = ("latitude", "longitude")
_EXCHANGE_RATE_OVERRIDE = "exchange_rate_override"

_Schema = dict[str, Any]


def _inline_references(node: Any, definitions: Mapping[str, Any]) -> Any:
    """`node` with every `$ref` replaced by the definition it points to."""
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_references(definitions[node["$ref"].rsplit("/", 1)[-1]], definitions)
        return {key: _inline_references(value, definitions) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline_references(item, definitions) for item in node]
    return node


def _flatten(node: Any) -> Any:
    """Drop what a model gains nothing from: titles and defaults, `null` alternatives, and the
    decimal-as-string alternative of a number."""
    if isinstance(node, list):
        return [_flatten(item) for item in node]
    if not isinstance(node, dict):
        return node
    flat: _Schema = {
        key: _flatten(value) for key, value in node.items() if key not in ("title", "default")
    }
    alternatives = flat.pop("anyOf", None)
    if alternatives is not None:
        kept = [alt for alt in alternatives if alt.get("type") != "null"]
        if any(alt.get("type") == "number" for alt in kept):
            kept = [alt for alt in kept if alt != {"type": "string"}]
        if len(kept) == 1:
            flat = {**kept[0], **flat}
        else:
            flat["anyOf"] = kept
    return flat


def _request_schema() -> _Schema:
    schema = QuoteRequestBody.model_json_schema()
    flat: _Schema = _flatten(_inline_references(schema, schema.get("$defs", {})))
    flat.pop("$defs", None)
    properties: _Schema = flat["properties"]
    del properties[_EXCHANGE_RATE_OVERRIDE]
    site: _Schema = properties["site"]
    for name in _COORDINATES:
        del site["properties"][name]
    site["properties"]["address"]["description"] = _ADDRESS_DESCRIPTION
    site["required"] = ["address"]
    return flat


def create_quote_declaration() -> ToolDeclaration:
    """The tool as the model sees it."""
    return ToolDeclaration(
        name=CREATE_QUOTE, description=CREATE_QUOTE_DESCRIPTION, parameters=_request_schema()
    )


def create_quote_request(arguments: Mapping[str, Any]) -> QuoteRequestBody:
    """The `POST /quotes` request model for the model's `arguments`.

    Coordinates and an Exchange Rate override are dropped even if the model supplied them, so
    the Site always comes from the Address. Raises pydantic's `ValidationError` with the
    request model's own messages.
    """
    cleaned = {key: value for key, value in arguments.items() if key != _EXCHANGE_RATE_OVERRIDE}
    site = cleaned.get("site")
    if isinstance(site, dict):
        cleaned["site"] = {key: value for key, value in site.items() if key not in _COORDINATES}
    return QuoteRequestBody.model_validate(cleaned)


@dataclass
class ConversationState:
    """What has happened so far in one assistant request. Tools read and update it."""

    created: StoredQuote | None = None


ToolHandler = Callable[[Mapping[str, Any], ConversationState], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class AssistantTool:
    """A tool the model may call: how it is declared and what running it does. The result is
    what the model is told; a failure is a result with an `error` key, never an exception."""

    declaration: ToolDeclaration
    handler: ToolHandler


def tool_error(problem: ProblemType, detail: str, **extra: Any) -> dict[str, Any]:
    """A tool result that says the call failed, with the problem `type` the API would use."""
    return {"error": {"type": problem.type_uri, "detail": detail, **extra}}


def create_quote_tool(service: QuoteService) -> AssistantTool:
    """`create_quote`: runs the same quote creation as `POST /quotes`, once per request.

    On success the model is told which placeholders the Quote can fill, never a figure. A
    validation or domain failure comes back as a tool error carrying the problem type.
    """

    async def run(arguments: Mapping[str, Any], state: ConversationState) -> dict[str, Any]:
        if state.created is not None:
            return tool_error(
                QUOTE_ALREADY_CREATED,
                "A Quote was already created in this request. Do not call the tool again; "
                "explain the Quote to the Sales Rep.",
            )
        try:
            body = create_quote_request(arguments)
            stored = await service.create_quote(body.to_domain())
        except ValidationError as error:
            return tool_error(
                VALIDATION_ERROR,
                "The arguments are invalid.",
                errors=field_errors(error.errors(include_url=False, include_context=False)),
            )
        except DomainError as error:
            problem = PROBLEMS_BY_EXCEPTION.get(type(error))
            if problem is None:
                raise
            return tool_error(problem, error_detail(error))
        state.created = stored
        context = build_narrative_context(stored.quote)
        return {
            "status": "created",
            "option_count": context.option_count,
            "available_placeholders": list(context.available_placeholders),
            "reply_max_characters": REPLY_MAX_CHARACTERS,
        }

    return AssistantTool(declaration=create_quote_declaration(), handler=run)
