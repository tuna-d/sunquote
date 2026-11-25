# NPV and IRR use a real Discount Rate; the Payback Period stays undiscounted

Every System Option also reports a Net Present Value and an Internal Rate of Return. The cash flow is the one of [ADR 0003](0003-real-escalation-rates.md), in today's lira, so the Discount Rate is a real (inflation-adjusted) rate as well, kept as a sourced placeholder Assumption. The Payback Period stays undiscounted and stays the headline figure in the Quote document; NPV and IRR sit next to it.

A nominal discount rate on a real cash flow (or the reverse) would mix two price levels and make NPV meaningless, so the rate has to match ADR 0003. The undiscounted payback is kept as the headline because it is the figure a Customer can check by hand against their bill, while NPV and IRR answer the question an investor or an interviewer asks: is this better than leaving the money in the bank? A discounted payback was not added, to keep one payback figure in the document.

## Consequences

- This lifts the "NPV is out of scope" consequence of ADR 0003.
- IRR is absent when the cash flow never turns positive within the lifetime, the same case in which the Payback Period is absent.
- The Discount Rate is recorded in the Assumptions, like the escalation rates.
