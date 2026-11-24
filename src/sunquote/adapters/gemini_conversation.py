"""Gemini adapter: one step of the quote assistant's conversation, with function calling.

It implements the `ConversationModel` port over the same `generateContent` REST endpoint and
HTTP client as the Narrative writer. The tools go in as function declarations; the model answers
with text or a function call. Earlier tool calls are replayed with their results, and a call's
thought signature is sent back with it, which Gemini 3 models require.

Every failure (HTTP error, timeout, network error, blocked or malformed answer) is raised as
`ConversationUnavailableError`. The API key travels in a header, never in the URL, and no error
message or `repr` contains it or the server's response body.
"""

import json
from collections.abc import Sequence
from typing import Any

import httpx

from sunquote.adapters.gemini import DEFAULT_GEMINI_BASE_URL
from sunquote.adapters.gemini_transport import (
    candidate_parts,
    first_candidate,
    generate_content_endpoint,
    post_generate_content,
)
from sunquote.domain.conversation import (
    ChatMessage,
    MessageRole,
    ModelReply,
    ReplyRejection,
    TextReply,
    ToolCall,
    ToolDeclaration,
    ToolExchange,
)
from sunquote.domain.errors import ConversationUnavailableError

_ROLES = {MessageRole.USER: "user", MessageRole.ASSISTANT: "model"}

_REJECTION_FEEDBACK = (
    "Your previous reply was rejected. Write it again in Turkish and fix every violation. "
    "Violations (JSON): "
)


class GeminiConversationModel:
    """Calls `<base_url>/models/<model>:generateContent` with function declarations.

    The HTTP client is injected so tests can swap the transport. Every call carries its own
    timeout, whatever the client's defaults are. The API key is held privately and appears in
    no `repr`, log line or error.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._endpoint = generate_content_endpoint(base_url, model)
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return f"GeminiConversationModel(model={self._model!r})"

    @property
    def model_name(self) -> str:
        return self._model

    async def respond(
        self,
        *,
        system_instruction: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDeclaration],
        exchanges: Sequence[ToolExchange] = (),
        rejected_reply: ReplyRejection | None = None,
    ) -> ModelReply:
        body = _request_body(system_instruction, messages, tools, exchanges, rejected_reply)
        payload = await post_generate_content(
            self._client,
            self._endpoint,
            api_key=self._api_key,
            body=body,
            timeout_seconds=self._timeout_seconds,
            fail=ConversationUnavailableError,
        )
        return _parse_reply(payload)


def _request_body(
    system_instruction: str,
    messages: Sequence[ChatMessage],
    tools: Sequence[ToolDeclaration],
    exchanges: Sequence[ToolExchange],
    rejected_reply: ReplyRejection | None,
) -> dict[str, Any]:
    contents: list[dict[str, Any]] = [
        {"role": _ROLES[message.role], "parts": [{"text": message.content}]} for message in messages
    ]
    for exchange in exchanges:
        contents.append({"role": "model", "parts": [_function_call_part(exchange.call)]})
        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": exchange.call.name,
                            "response": dict(exchange.result),
                        }
                    }
                ],
            }
        )
    if rejected_reply is not None:
        violations = [
            {"kind": violation.kind.value, "field": violation.field, "detail": violation.detail}
            for violation in rejected_reply.violations
        ]
        contents.append({"role": "model", "parts": [{"text": rejected_reply.text}]})
        contents.append(
            {
                "role": "user",
                "parts": [
                    {"text": _REJECTION_FEEDBACK + json.dumps(violations, ensure_ascii=False)}
                ],
            }
        )
    return {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parametersJsonSchema": dict(tool.parameters),
                    }
                    for tool in tools
                ]
            }
        ],
    }


def _function_call_part(call: ToolCall) -> dict[str, Any]:
    part: dict[str, Any] = {"functionCall": {"name": call.name, "args": dict(call.arguments)}}
    if call.signature is not None:
        part["thoughtSignature"] = call.signature
    return part


def _parse_reply(payload: Any) -> ModelReply:
    """The model's text or function call, or `ConversationUnavailableError`."""
    parts = candidate_parts(first_candidate(payload, ConversationUnavailableError))
    for part in parts:
        if "functionCall" in part:
            return _tool_call(part)
    texts = [part["text"] for part in parts if isinstance(part.get("text"), str)]
    if not texts:
        raise ConversationUnavailableError("the candidate has no text")
    return TextReply("".join(texts))


def _tool_call(part: dict[str, Any]) -> ToolCall:
    call = part["functionCall"]
    malformed = ConversationUnavailableError("the function call is malformed")
    if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not call["name"]:
        raise malformed
    arguments = call.get("args", {})
    if not isinstance(arguments, dict):
        raise malformed
    signature = part.get("thoughtSignature")
    return ToolCall(
        name=call["name"],
        arguments=arguments,
        signature=signature if isinstance(signature, str) else None,
    )
