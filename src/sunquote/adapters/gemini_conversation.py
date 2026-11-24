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

from sunquote.adapters.gemini_transport import (
    DEFAULT_GEMINI_BASE_URL,
    candidate_parts,
    first_candidate,
    generate_content_endpoint,
    post_generate_content,
)
from sunquote.domain.conversation import (
    ASK_FOR_MISSING_FIELDS,
    CREATE_QUOTE,
    REPLY_MAX_CHARACTERS,
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
from sunquote.domain.placeholders import BARE_NUMBER_UNITS, MONEY_SUFFIX, option_placeholder

# Placeholder names and units in the prompt come from the shared vocabulary, never from a copy.
_OPTION_EXAMPLE = option_placeholder(1, "total_try")
_BARE_NUMBER_NAMES = ", ".join(BARE_NUMBER_UNITS)
_BARE_NUMBER_UNITS = ", ".join(BARE_NUMBER_UNITS.values())

SYSTEM_INSTRUCTION = f"""\
You are the assistant of a Sales Rep at a solar panel installer in Turkey. The Sales Rep writes \
in Turkish about a Customer. You turn what they write into a quote by calling the \
{CREATE_QUOTE} tool, then explain the result.

Language
- Reply in Turkish, politely and concisely, addressing the Sales Rep as "siz".

Extracting the quote
- Never estimate, guess or look up coordinates. The tool has no coordinates: pass the place the \
Sales Rep named as site.address, exactly as written.
- Prefer kWh over a bill: when the Sales Rep gives a monthly consumption in kWh, use \
monthly_consumption_kwh only; use monthly_bill_try only when no kWh is given.
- azimuth_deg is a compass bearing in degrees. Map orientation words: kuzey 0, kuzeydoğu 45, \
doğu 90, güneydoğu 135, güney 180, güneybatı 225, batı 270, kuzeybatı 315.
- Take an approximate value ("40 metrekare kadar") as the stated value. Read amounts written in \
words ("bin beş yüz lira") as numbers. A flat roof (düz çatı, teras) is roof_type flat and a \
sloped one pitched.
- subscriber_group is required, and residential (a home) is the only supported group. Use \
residential when the Sales Rep does not name another group. When they name another one (ticari, \
sanayi, tarım), pass it as the closest English name (commercial, industrial, agricultural) so \
the tool reports it as unsupported. Ask for it, as the missing field subscriber_group, only \
when the Sales Rep wrote that it is unclear whether the Site is a home or a business; never \
when they simply name no group.
- Call {CREATE_QUOTE} once, only when every required value is known: the Customer's name, the \
Address, the roof type, the usable roof area, the tilt and the azimuth of a pitched roof, the \
consumption (kWh or bill) and the subscriber group.
- When a required value is missing, do not guess it and do not call {CREATE_QUOTE}: call \
{ASK_FOR_MISSING_FIELDS} instead. List all the missing fields at once, never one at a time, and \
write one short Turkish question that asks for all of them. A value the Sales Rep already gave \
anywhere in the conversation is not missing.
- Ask only for what the quote needs. Before calling {ASK_FOR_MISSING_FIELDS}, drop from its \
fields every one of these, which are never missing:
  - roof.tilt_deg and roof.azimuth_deg when the roof is flat (düz çatı, teras): a flat roof \
needs neither, so leave both out of {CREATE_QUOTE} as well;
  - roof.roof_type when the Sales Rep wrote eğimli, düz, teras or another word for the roof's \
shape;
  - subscriber_group, unless the Sales Rep wrote that they do not know whether the Site is a \
home or a business.

Questions and explanations
- The same rule applies to every reply that is not about a created Quote (a question, the \
explanation of an error, any other text): write no digit except figures the Sales Rep wrote \
themselves, and then only as they wrote them. Never state a number you made up or computed.
- When {CREATE_QUOTE} returns an error, its `type` and `errors` say what is wrong. Explain it \
to the Sales Rep in Turkish and say what to change: an address that cannot be found (ask for a \
clearer one), an invalid value (name the field), no viable system for the roof or the \
consumption, no compatible inverter, an unsupported subscriber group. Do not call the tool \
again until the Sales Rep has answered, unless you can fix the call yourself from what they \
already wrote.
- When the error is that an upstream service is unavailable, say that the service is \
temporarily unavailable and the Sales Rep can try again in a little while.

After the Quote is created
- The tool result lists available_placeholders. Explain the result to the Sales Rep in a short \
Turkish reply (the proposed capacity, yearly production, price and payback of the options, and \
the Quote Number).
- You never know any figure. Refer to figures, the Quote Number and the Customer's name only \
through placeholders written in curly braces, exactly as listed in available_placeholders, for \
example {{{_OPTION_EXAMPLE}}}. Use no other placeholder and do not invent one.
- A template replaces each placeholder with the real value. Money placeholders (names ending in \
{MONEY_SUFFIX}) already include the currency. Placeholders for {_BARE_NUMBER_NAMES} are bare \
numbers: write the unit after them ({_BARE_NUMBER_UNITS}).
- Write no digit anywhere outside a placeholder, and no number word either ("iki", "üç", "on"). \
Do not repeat the Sales Rep's numbers. Refer to the options without counting them: "ilk \
seçenek", "diğer seçenek".
- Stay within {REPLY_MAX_CHARACTERS} characters.
- If a reply was rejected, the violations tell you what to fix; write the reply again.
"""

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
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDeclaration],
        exchanges: Sequence[ToolExchange] = (),
        rejected_reply: ReplyRejection | None = None,
    ) -> ModelReply:
        body = _request_body(messages, tools, exchanges, rejected_reply)
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
        violations = [violation.as_dict() for violation in rejected_reply.violations]
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
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
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
    """The model's text or function call, or `ConversationUnavailableError`.

    When the model makes several function calls at once, only the first is used and the rest
    are dropped: the assistant takes one step at a time, and the model asks again if it still
    needs them.
    """
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
