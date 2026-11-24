"""What the quote assistant exchanges with a conversation model.

The assistant is a Sales Rep's chat that ends in a tool call (create a Quote) and an explanation
of its result. These are the plain values that cross the `ConversationModel` port: the chat
messages, the tools the model may call, the calls it made with their results, and what it
answers. They hold no prose of their own and no provider format.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sunquote.domain.narrative import Violation

# The assistant calls the model at most this often for one request, and for at most this long
# in total (settings can change the time).
MAX_MODEL_CALLS = 3
DEFAULT_ASSISTANT_BUDGET_SECONDS = 30.0
# The longest reply the assistant gives after it created a Quote.
REPLY_MAX_CHARACTERS = 1500


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
