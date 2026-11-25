"""POST /assistant/messages: the Sales Rep's Turkish chat that ends in a stored Quote."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints, field_validator

from sunquote.api.assistant_tools import QuoteAssistantTools
from sunquote.api.assistant_turn import run_assistant_turn
from sunquote.api.dependencies import AppDependencies, get_quote_service
from sunquote.api.errors import (
    ASSISTANT_NOT_CONFIGURED,
    ASSISTANT_UNAVAILABLE,
    RATE_LIMITED,
    VALIDATION_ERROR,
    problem_responses,
)
from sunquote.api.rate_limit import limit_assistant_messages
from sunquote.domain.conversation import ChatMessage, MessageRole, MissingField
from sunquote.domain.errors import AssistantNotConfiguredError
from sunquote.domain.service import QuoteService

router = APIRouter(tags=["assistant"])

MAX_MESSAGES = 20
MAX_MESSAGE_CHARACTERS = 2000


class MessageBody(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)]


class AssistantRequestBody(BaseModel):
    messages: list[MessageBody] = Field(
        min_length=1,
        max_length=MAX_MESSAGES,
        description=(
            "The conversation so far, oldest first. The client keeps it and resends all of it "
            "with every request. The last message must be the Sales Rep's (`user`)."
        ),
    )

    @field_validator("messages")
    @classmethod
    def _last_message_is_from_the_user(cls, messages: list[MessageBody]) -> list[MessageBody]:
        if messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return messages

    def to_domain(self) -> tuple[ChatMessage, ...]:
        return tuple(ChatMessage(MessageRole(m.role), m.content) for m in self.messages)


class QuoteReference(BaseModel):
    id: UUID
    quote_number: str
    document_url: str = Field(description="Link to the printable Turkish quote document.")


class AssistantResponse(BaseModel):
    reply: str = Field(description="Turkish text. Every placeholder is already filled.")
    quote: QuoteReference | None = Field(
        description="The Quote created in this turn, or null when none was."
    )
    missing_fields: list[MissingField] = Field(
        description=(
            "When the turn ends with a question: the `create_quote` field paths still missing "
            "(`customer.name`, `site.address`, `roof.roof_type`, `roof.tilt_deg`, "
            "`roof.azimuth_deg`, `roof.usable_area_m2`, `consumption`, `subscriber_group`) "
            "and `reply` is that question. Otherwise empty."
        )
    )


@router.post(
    "/assistant/messages",
    summary="Create a Quote from a Turkish chat message",
    dependencies=[Depends(limit_assistant_messages)],
    responses=problem_responses(
        VALIDATION_ERROR, RATE_LIMITED, ASSISTANT_NOT_CONFIGURED, ASSISTANT_UNAVAILABLE
    ),
)
async def post_assistant_messages(
    body: AssistantRequestBody,
    request: Request,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> AssistantResponse:
    """Turn the Sales Rep's Turkish message into a Quote and explain it in Turkish.

    Each client IP may send 20 messages an hour (configurable); past that the answer is `429`
    with a `Retry-After` header, whatever the body holds.

    Gemini reads the conversation and calls the `create_quote` tool, which runs the same quote
    creation as `POST /quotes` (Address geocoding, PVGIS, TCMB, Narrative, storage) and stores
    the Quote. The reply explains the Quote; every figure in it is filled from the Quote, never
    written by the model. The response gives the Quote's id, Quote Number and document link.
    The model never sets Coordinates: the Address is always geocoded.

    When something a Quote needs is missing, the assistant asks for all of it in one Turkish
    question (`reply`) and lists the fields in `missing_fields`; answer in a further message and
    the Quote is created once everything is there. When Quote creation fails (Address not found,
    invalid value, no viable system, unsupported Subscriber Group, a service unavailable), the
    reply explains in Turkish what to change. A reply without a Quote may hold digits only as
    the Sales Rep wrote them; if the model breaks that twice, a fixed Turkish reply is used. If
    the three calls or the time budget run out without a Quote, the reply asks to restate the
    information (200, no Quote).

    The server keeps no conversation state: send the whole conversation every time (1 to 20
    messages of at most 2000 characters, the last one from the `user`). At most one Quote is
    created per request, and the model is called at most three times within a total time
    budget, which covers the model calls and the tools together. If the model's reply after the
    Quote breaks the placeholder rules, or the model fails after the Quote was created, the
    reply is a fixed Turkish confirmation with the Quote Number, each option's capacity and
    total price, and the document link.

    **Privacy.** The Sales Rep's messages are sent to Gemini and may include the Customer's name
    and Address. Gemini's free tier may use submitted content for training. Do not send what
    must stay private.

    Without a Gemini key (`SUNQUOTE_GEMINI_API_KEY`) this endpoint answers 503 "assistant not
    configured" and the rest of the API works as usual. When the model is unavailable and no
    Quote exists yet it answers 503 "assistant unavailable".
    """
    dependencies: AppDependencies = request.app.state.dependencies
    model = dependencies.conversation_model
    if model is None:
        raise AssistantNotConfiguredError()

    def document_url(quote_id: UUID) -> str:
        return str(request.url_for("get_quote_document", quote_id=quote_id))

    turn = await run_assistant_turn(
        model=model,
        tools=QuoteAssistantTools(service),
        messages=body.to_domain(),
        document_url=document_url,
        budget_seconds=dependencies.assistant_budget_seconds,
    )
    stored = turn.quote
    return AssistantResponse(
        reply=turn.reply,
        quote=(
            None
            if stored is None
            else QuoteReference(
                id=stored.id,
                quote_number=stored.quote.quote_number,
                document_url=document_url(stored.id),
            )
        ),
        missing_fields=list(turn.missing_fields),
    )
