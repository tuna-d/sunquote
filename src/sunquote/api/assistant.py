"""POST /assistant/messages: the Sales Rep's Turkish chat that ends in a stored Quote."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints, field_validator

from sunquote.api.assistant_loop import Assistant
from sunquote.api.assistant_tools import create_quote_tool
from sunquote.api.dependencies import AppDependencies, get_quote_service
from sunquote.api.errors import (
    ASSISTANT_NOT_CONFIGURED,
    ASSISTANT_UNAVAILABLE,
    VALIDATION_ERROR,
    problem_responses,
)
from sunquote.domain.conversation import ChatMessage, MessageRole
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
    missing_fields: list[str] = Field(
        description="Required fields the assistant still needs. Always empty for now."
    )


@router.post(
    "/assistant/messages",
    summary="Create a Quote from a Turkish chat message",
    responses=problem_responses(VALIDATION_ERROR, ASSISTANT_NOT_CONFIGURED, ASSISTANT_UNAVAILABLE),
)
async def post_assistant_messages(
    body: AssistantRequestBody,
    request: Request,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> AssistantResponse:
    """Turn the Sales Rep's Turkish message into a Quote and explain it in Turkish.

    Gemini reads the conversation and calls the `create_quote` tool, which runs the same quote
    creation as `POST /quotes` (Address geocoding, PVGIS, TCMB, Narrative, storage) and stores
    the Quote. The reply explains the Quote; every figure in it is filled from the Quote, never
    written by the model. The response gives the Quote's id, Quote Number and document link.
    The model never sets Coordinates: the Address is always geocoded.

    The server keeps no conversation state: send the whole conversation every time (1 to 20
    messages of at most 2000 characters, the last one from the `user`). At most one Quote is
    created per request, and the model is called at most three times within a total time
    budget. If the model's reply after the Quote breaks the placeholder rules, or the model
    fails after the Quote was created, the reply is a fixed Turkish confirmation with the Quote
    Number, each option's capacity and total price, and the document link.

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

    assistant = Assistant(
        model=model,
        tools=[create_quote_tool(service)],
        document_url=document_url,
        budget_seconds=dependencies.assistant_budget_seconds,
    )
    outcome = await assistant.run(body.to_domain())
    stored = outcome.quote
    return AssistantResponse(
        reply=outcome.reply,
        quote=(
            None
            if stored is None
            else QuoteReference(
                id=stored.id,
                quote_number=stored.quote.quote_number,
                document_url=document_url(stored.id),
            )
        ),
        missing_fields=[],
    )
