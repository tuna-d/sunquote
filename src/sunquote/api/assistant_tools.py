"""The tools of the quote assistant: `create_quote` and the control tool `ask_for_missing_fields`.

`create_quote`'s parameters are the `POST /quotes` request model's JSON Schema, simplified for a
model to read and without what the model must never supply: Coordinates and an Exchange Rate
override. The Address is required instead, so every Quote the assistant creates is geocoded. Its
arguments are validated by the same request model before the quote-creation service is called.

`ask_for_missing_fields` ends the turn with a question instead of a Quote. It is a control tool,
not a feature tool: it gives the response's `missing_fields` and the extraction eval a
structured source.

`QuoteAssistantTools` is what the domain's assistant loop calls. This layer validates the
arguments with Pydantic, runs the quote-creation service and turns its failures into tool
results that carry the problem type; the loop's policy (retries, which reply is accepted) is the
domain's.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from sunquote.api.errors import (
    PROBLEMS_BY_EXCEPTION,
    QUOTE_ALREADY_CREATED,
    REPLY_REJECTED,
    UNKNOWN_TOOL,
    VALIDATION_ERROR,
    ProblemType,
    error_detail,
    field_errors,
)
from sunquote.api.schemas import QuoteRequestBody
from sunquote.domain.assistant import AskedQuestion, ToolResult
from sunquote.domain.conversation import (
    ASK_FOR_MISSING_FIELDS,
    CREATE_QUOTE,
    REPLY_MAX_CHARACTERS,
    MissingField,
    ToolCall,
    ToolDeclaration,
)
from sunquote.domain.errors import AddressNotFoundError, DomainError
from sunquote.domain.narrative import Violation
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.ports import StoredQuote
from sunquote.domain.service import QuoteService

CREATE_QUOTE_DESCRIPTION = (
    "Create a solar panel Quote for a Customer from the Sales Rep's description. Call it once, "
    "when every required value is known; it geocodes the Address, estimates the production, "
    "prices the system and stores the Quote."
)
_ADDRESS_DESCRIPTION = (
    "The place of the Site exactly as the Sales Rep wrote it (street, district, province). "
    "Never a guess at coordinates."
)
ADDRESS_FIELD = "site.address"
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


def _simplify_schema(node: Any) -> Any:
    """Drop what a model gains nothing from: titles and defaults, `null` alternatives, and the
    decimal-as-string alternative of a number."""
    if isinstance(node, list):
        return [_simplify_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    simple: _Schema = {
        key: _simplify_schema(value)
        for key, value in node.items()
        if key not in ("title", "default")
    }
    alternatives = simple.pop("anyOf", None)
    if alternatives is not None:
        kept = [alt for alt in alternatives if alt.get("type") != "null"]
        if any(alt.get("type") == "number" for alt in kept):
            kept = [alt for alt in kept if alt != {"type": "string"}]
        if len(kept) == 1:
            simple = {**kept[0], **simple}
        else:
            simple["anyOf"] = kept
    return simple


def _request_schema() -> _Schema:
    schema = QuoteRequestBody.model_json_schema()
    simple: _Schema = _simplify_schema(_inline_references(schema, schema.get("$defs", {})))
    simple.pop("$defs", None)
    properties: _Schema = simple["properties"]
    del properties[_EXCHANGE_RATE_OVERRIDE]
    site: _Schema = properties["site"]
    for name in _COORDINATES:
        del site["properties"][name]
    site["properties"]["address"]["description"] = _ADDRESS_DESCRIPTION
    site["required"] = ["address"]
    return simple


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


ASK_DESCRIPTION = (
    "Ask the Sales Rep for the required values that are still missing, instead of calling "
    f"{CREATE_QUOTE}. List every missing field at once and write one short Turkish question "
    "that asks for all of them. No Quote is created."
)


class AskArguments(BaseModel):
    fields: list[MissingField] = Field(min_length=1)
    question: str = Field(min_length=1)


def ask_for_missing_fields_declaration() -> ToolDeclaration:
    """The control tool as the model sees it."""
    return ToolDeclaration(
        name=ASK_FOR_MISSING_FIELDS,
        description=ASK_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "enum": [item.value for item in MissingField]},
                    "description": (
                        f"Every {CREATE_QUOTE} field that is required, still unknown and not "
                        "stated anywhere in the conversation. `consumption` means the monthly "
                        "kWh or the monthly bill."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": (
                        "The question for the Sales Rep, in Turkish, asking for all the listed "
                        "fields. Write no figure the Sales Rep did not write."
                    ),
                },
            },
            "required": ["fields", "question"],
        },
    )


def tool_error(problem: ProblemType, detail: str, **extra: Any) -> dict[str, Any]:
    """A tool result that says the call failed, with the problem `type` the API would use."""
    return {"error": {"type": problem.type_uri, "detail": detail, **extra}}


def _failure(problem: ProblemType, detail: str, **extra: Any) -> ToolResult:
    return ToolResult(tool_error(problem, detail, **extra), problem=problem.type_uri)


def _invalid_arguments(error: ValidationError) -> ToolResult:
    return _failure(
        VALIDATION_ERROR,
        "The arguments are invalid.",
        errors=field_errors(error.errors(include_url=False, include_context=False)),
    )


class QuoteAssistantTools:
    """The assistant's two tools for one request.

    `create_quote` runs the same quote creation as `POST /quotes`, once per request: on success
    the model is told which placeholders the Quote can fill, never a figure, and a validation or
    domain failure comes back as a failed result carrying the problem type.
    `ask_for_missing_fields` makes its question the reply; no Quote is created. Once a Quote
    exists, every further call is a failed result.
    """

    def __init__(self, service: QuoteService) -> None:
        self._service = service
        self._created: StoredQuote | None = None
        self.declarations: Sequence[ToolDeclaration] = (
            create_quote_declaration(),
            ask_for_missing_fields_declaration(),
        )

    async def run(self, call: ToolCall) -> ToolResult:
        if self._created is not None:
            return _failure(
                QUOTE_ALREADY_CREATED,
                "A Quote was already created in this request. Do not call a tool again; "
                "explain the Quote to the Sales Rep.",
            )
        if call.name == CREATE_QUOTE:
            return await self._create_quote(call.arguments)
        if call.name == ASK_FOR_MISSING_FIELDS:
            return self._ask(call.arguments)
        return _failure(UNKNOWN_TOOL, f"There is no tool named {call.name!r}.")

    def rejection(self, violations: Sequence[Violation]) -> ToolResult:
        return _failure(
            REPLY_REJECTED,
            "The question was rejected. Ask again and fix every violation.",
            violations=[violation.as_dict() for violation in violations],
        )

    async def _create_quote(self, arguments: Mapping[str, Any]) -> ToolResult:
        try:
            body = create_quote_request(arguments)
            stored = await self._service.create_quote(body.to_domain())
        except ValidationError as error:
            return _invalid_arguments(error)
        except DomainError as error:
            problem = PROBLEMS_BY_EXCEPTION.get(type(error))
            if problem is None:
                raise
            extra = (
                {"errors": [{"field": ADDRESS_FIELD, "message": error_detail(error)}]}
                if isinstance(error, AddressNotFoundError)
                else {}
            )
            return _failure(problem, error_detail(error), **extra)
        self._created = stored
        context = build_narrative_context(stored.quote)
        return ToolResult(
            {
                "status": "created",
                "option_count": context.option_count,
                "available_placeholders": list(context.available_placeholders),
                "reply_max_characters": REPLY_MAX_CHARACTERS,
            },
            created=stored,
        )

    def _ask(self, arguments: Mapping[str, Any]) -> ToolResult:
        try:
            asked = AskArguments.model_validate(arguments)
        except ValidationError as error:
            return _invalid_arguments(error)
        question = AskedQuestion(tuple(dict.fromkeys(asked.fields)), asked.question)
        return ToolResult({"status": "asked"}, asked=question)
