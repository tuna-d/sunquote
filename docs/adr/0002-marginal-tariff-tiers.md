# Residential Tariff Tiers are marginal bands

The EPDK residential tariff splits consumption at an average of 8 kWh/day (2,920 kWh/year in the placeholder data): energy up to that threshold is billed at the low Retail Tariff and only the part above it at the high Retail Tariff. sunquote models it the same way. A Monthly Bill converts to kWh by inverting this piecewise cost, and self-consumed energy is valued as the drop in the annual grid bill, so it comes off the high tier first.

Spec #1 first described a single tier chosen by annual consumption, with all energy priced at that tier. We dropped it because it does not match how Customers are billed: it makes the bill-to-kWh conversion jump at the threshold (a higher bill could give a lower consumption) and misprices the savings of anyone near the threshold. The marginal model is a little more work in the domain and keeps every figure explainable against a real bill.

## Consequences

- Annual consumption and its split across the two tiers are recorded in the Assumptions, not a single chosen tier.
- Cost as a function of consumption is continuous, so the bill-to-kWh conversion has no edge case at the threshold.
