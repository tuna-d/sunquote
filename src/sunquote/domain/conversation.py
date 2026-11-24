"""What the quote assistant exchanges with a conversation model.

The assistant is a Sales Rep's chat that ends in a tool call (create a Quote) and an explanation
of its result. These are the plain values that cross the `ConversationModel` port: the chat
messages, the tools the model may call, the calls it made with their results, and what it
answers. They hold no prose of their own and no provider format.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sunquote.domain.narrative import Violation, ViolationKind

# The assistant calls the model at most this often for one request, and for at most this long
# in total (settings can change the time).
MAX_MODEL_CALLS = 3
DEFAULT_ASSISTANT_BUDGET_SECONDS = 30.0
# The longest reply the assistant gives after it created a Quote.
REPLY_MAX_CHARACTERS = 1500


# The two tools the model may call, by name.
CREATE_QUOTE = "create_quote"
ASK_FOR_MISSING_FIELDS = "ask_for_missing_fields"


class MissingField(StrEnum):
    """The `create_quote` field paths the model can say are still missing."""

    CUSTOMER_NAME = "customer.name"
    SITE_ADDRESS = "site.address"
    ROOF_TYPE = "roof.roof_type"
    ROOF_TILT = "roof.tilt_deg"
    ROOF_AZIMUTH = "roof.azimuth_deg"
    ROOF_USABLE_AREA = "roof.usable_area_m2"
    CONSUMPTION = "consumption"
    SUBSCRIBER_GROUP = "subscriber_group"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class ToolDeclaration:
    """A tool the model may call: its name, what it does and its parameters as a JSON Schema
    object."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """The model asked to call the tool `name` with `arguments` (not yet validated).

    `signature` is an opaque token the model attached to the call (Gemini's thought signature)
    that must be sent back with it; the domain never reads it.
    """

    name: str
    arguments: Mapping[str, Any]
    signature: str | None = None


@dataclass(frozen=True, slots=True)
class ToolExchange:
    """A tool call the model made and the result it was given for it."""

    call: ToolCall
    result: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TextReply:
    """The model answered with text instead of a tool call."""

    text: str


@dataclass(frozen=True, slots=True)
class ReplyRejection:
    """A text reply the assistant refused, and why. Sent back to the model for one more try."""

    text: str
    violations: Sequence[Violation]


ModelReply = TextReply | ToolCall

_DIGIT_SEQUENCE = re.compile(r"\d+")


def validate_echoed_digits(
    text: str, *, field: str, messages: Sequence[ChatMessage]
) -> tuple[Violation, ...]:
    """The rule for a reply that gives no Quote figures (a question, the explanation of an
    error, plain text): it may hold digits only as digit sequences that appear in the Sales
    Rep's own (`user`) messages. That echoes their input; any other digit is a figure the model
    made up. A superscript such as the 2 of "m²" is not a digit here."""
    allowed = {
        sequence
        for message in messages
        if message.role is MessageRole.USER
        for sequence in _DIGIT_SEQUENCE.findall(message.content)
    }
    foreign = [
        sequence
        for sequence in dict.fromkeys(_DIGIT_SEQUENCE.findall(text))
        if sequence not in allowed
    ]
    if not foreign:
        return ()
    return (
        Violation(
            ViolationKind.DIGIT_NOT_IN_USER_MESSAGES,
            field,
            f"the figures {', '.join(foreign)} do not appear in the Sales Rep's messages; "
            "write no figure the Sales Rep did not write",
        ),
    )
