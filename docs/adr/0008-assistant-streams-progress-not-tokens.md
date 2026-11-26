# The Assistant streams progress events, not tokens

The Assistant's streaming response sends progress events over Server-Sent Events (looking up the Address, fetching Specific Yield, Quote created, writing the explanation) and then the final, validated reply in one piece. It never streams the model's tokens.

Under [ADR 0001](0001-llm-never-writes-figures.md) and [ADR 0004](0004-assistant-replies-may-echo-the-sales-reps-digits.md), a reply can be judged only once it is complete: a stray digit near the end rejects the whole draft, and the retry or the fixed template replaces it. Streaming tokens would show the Sales Rep text that may then be withdrawn, possibly with a wrong figure in it. Most of a turn's wait is geocoding, PVGIS, TCMB and the Narrative, not the reply itself, so progress events remove most of the perceived latency while every word shown is still one that passed validation.

## Consequences

- The client can render the reply with a typing effect, but only after it has arrived whole.
- The non-streaming `POST /assistant/messages` stays, returning the same final reply.
