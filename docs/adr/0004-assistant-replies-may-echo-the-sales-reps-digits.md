# Assistant replies without a Quote may echo the Sales Rep's own digits

A reply of the quote assistant that is not about a created Quote (a question for Missing Fields, the explanation of an error, plain text) may contain digit sequences, but only those that appear in the Sales Rep's own (`user`) messages of the same conversation. It may not hold any placeholder syntax, since there is no Quote to fill placeholders from. A reply that breaks either rule is sent back to the model once per kind of reply, and then replaced by a fixed Turkish template. A reply after a Quote was created stays fully under [ADR 0001](0001-llm-never-writes-figures.md): no digit outside a placeholder.

This relaxes ADR 0001 on purpose and only here. ADR 0001 forbids every digit outside a placeholder because the figures of a Quote must come from the calculation. Without a Quote there is nothing to calculate and no placeholder to use, and a question such as "40 m² çatının eğimi kaç derece?" is only useful when it can repeat what the Sales Rep wrote. Forbidding all digits would force vague questions and error explanations; allowing the model's own numbers would let it invent figures (a tilt, an area) that read like facts. Echoing the Sales Rep's digit sequences gives the first without the second: the digits come from the input, not from the model. Digit sequences are compared whole, so "4" does not pass because the Sales Rep wrote "40", and digits in the assistant's own earlier messages do not count as the Sales Rep's.

## Consequences

- The rule is mechanical and lives in the domain (`validate_echoed_digits`), together with the placeholder-syntax check; the eval and the tests can check it without reading the prompt.
- A superscript such as the 2 of "m²" is not a digit under either rule.
- The Sales Rep's own mistakes can be echoed back ("40 m² mi demiştiniz?"); the reply is still not a figure the model produced.
- Echoing says nothing about the figure being right. Nothing in such a reply is stored or priced.
