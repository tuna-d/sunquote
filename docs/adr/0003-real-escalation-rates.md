# Escalation rates are real, figures are in today's lira

Status: the "NPV is out of scope" consequence is lifted by [ADR 0006](0006-npv-and-irr-with-a-real-discount-rate.md).

The tariff and equipment escalation rates used over the system lifetime are real (inflation-adjusted) rates: placeholder 2%/year for tariffs and 0%/year for equipment. Every lifetime figure in a Quote (yearly cash flow, inverter replacement, lifetime savings, Payback Period) is therefore in today's lira, and the quote document says so.

Turkish inflation expectations of 18-24% a year would make a nominal 25-year TRY cash flow grow 50-80x, which reads as noise to a Customer, and because the Payback Period is undiscounted, nominal escalation would also shorten it artificially. Real rates with no discounting keep the payback honest and the numbers comparable to today's price, at the cost of not matching the lira amounts the Customer will see on future bills.

## Consequences

- The Assumptions record that the escalation rates are real.
- Moving to nominal rates later would require discounting (NPV), which is out of scope for spec #1.
