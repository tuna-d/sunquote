# The LLM never writes figures in customer-facing text

The Quote's customer-facing text combines a Jinja2 template with an LLM-written Narrative. The LLM returns structured output (greeting, summary, recommendation) and may refer to a figure only through a placeholder from a closed list, such as `{capacity_kwp}`. It never writes the figure itself. The template fills every placeholder from the values the domain calculated. Output containing digits outside placeholders, or unknown placeholders, is rejected.

We chose this because a Quote is a commercial offer: an LLM restating 8.4 kWp as 8.2, or rounding a price, would put a wrong figure in front of the Customer, and checking free text against the calculation after the fact is unreliable. Letting the LLM write the whole text reads more naturally but cannot guarantee the numbers; a fixed template guarantees them but reads stiffly. Placeholders keep the guarantee and still let the LLM write the prose.

## Consequences

- The Narrative is optional. Without an LLM key, or when generation fails or is rejected, the template's fixed Turkish text is used and the Quote is still complete.
- The domain stays free of text. Producing the Narrative is an adapter's job.
- The Narrative eval can check the rule mechanically: no stray digits, only known placeholders, every required field present.
