# sunquote

Prepares a customer-ready rooftop PV quote for a Turkish solar installer from a site's location, roof and electricity consumption.

## Language

### People

**Installer**:
The solar installation company that uses sunquote. There is exactly one.
_Avoid_: firm, tenant, company

**Sales Rep**:
An Installer employee who enters a Site and issues Quotes.
_Avoid_: user, salesperson

**Customer**:
The person a Quote is addressed to, known only by the name and contact details written on the Quote.
_Avoid_: client, lead, account

### Site

**Site**:
The place where the system would be installed: its Address, Coordinates and Roof.
_Avoid_: location, property

**Address**:
The Site's location as the Sales Rep wrote it.

**Coordinates**:
The Site's latitude and longitude, resolved from the Address or given directly.

**Roof**:
A single roof surface available for panels: its Roof Type, usable area, orientation and tilt.
_Avoid_: roof plane, rooftop

**Roof Type**:
Whether the Roof is pitched (panels lie flush, following its tilt and orientation) or flat (panels are raised on racks to a set tilt facing south).

**Usable Area**:
The Roof area left for panels once obstacles such as chimneys and windows are excluded, as entered by the Sales Rep.
_Avoid_: roof area, total area

**Coverage Ratio**:
The share of the Usable Area that panels can actually occupy for a Roof Type, allowing for edges, walkways and row spacing.
_Avoid_: packing factor, ground coverage ratio

**Subscriber Group**:
The grid tariff class of the Site's electricity connection, such as residential or commercial.
_Avoid_: customer type, tariff class

**Contracted Power**:
The maximum power, in kW, of the Site's grid connection agreement, which caps the inverter's AC power.
_Avoid_: connection power, subscribed power

### Consumption

**Monthly Consumption**:
The Customer's average monthly electricity use in kWh, given directly or derived from the Monthly Bill.

**Monthly Bill**:
The Customer's average monthly electricity bill in TRY, taxes and fees included.
_Avoid_: invoice

**Retail Tariff**:
The all-in price per kWh the Customer pays for grid electricity, taxes and fees included.
_Avoid_: electricity price, rate

**Tariff Tier**:
A marginal band of the Retail Tariff. Each month, consumption up to the Subscriber Group's threshold for that month (the daily allowance, 8 kWh, times the month's days in a 365-day year: 248 kWh in January, 224 in February, 240 in April) is priced at the low tier; only the part above it is priced at the high tier. A flat consumption is priced month by month, and a Monthly Bill converts to kWh by inverting that annual cost.
_Avoid_: kademe, step

### System and production

**System Option**:
One candidate PV system in a Quote, with its size, equipment, production, price and financial result.
_Avoid_: proposal, alternative, package

**Sizing Strategy**:
The rule that sets a System Option's size: Consumption-Matched or Roof-Max.

**Consumption-Matched**:
The Sizing Strategy that targets annual production equal to annual consumption, capped by what the Roof fits.

**Roof-Max**:
The Sizing Strategy that fits as many panels as the Roof allows.

**Binding Limit**:
The constraint that actually set a System Option's size: the Roof, the consumption target or the Contracted Power.

**Specific Yield**:
Expected annual production per kWp at the Site for the Roof's orientation and tilt, in kWh/kWp/year.
_Avoid_: yield, irradiation, sun hours

**Monthly Netting**:
The settlement rule for residential Sites: each month's production is offset against that month's consumption, and only the production beyond it is exported.
_Avoid_: net metering, hourly netting

**Netted Energy**:
The part of a month's production that offsets that month's consumption under Monthly Netting.
_Avoid_: self-consumption, self-consumed energy

**Netted Share**:
The share of a System Option's annual production that is Netted Energy. A result of the calculation, not an Assumption.
_Avoid_: Self-Consumption Ratio

**Exported Energy**:
The part of a month's production beyond that month's consumption, sold to the grid.
_Avoid_: surplus, excess

**Export Price**:
The price per kWh paid for Exported Energy.
_Avoid_: feed-in tariff

### Equipment and price

**Catalog**:
The panels and inverters the Installer can install, with their datasheet values and unit prices.
_Avoid_: product list, inventory

**Default Panel**:
The panel model the Installer uses for every System Option.

**DC/AC Ratio**:
The panels' total peak power divided by the inverter's rated AC power.

**Installation Cost**:
What the Installer pays to deliver a System Option: equipment, mounting and cabling, labour and fixed project costs.
_Avoid_: cost price, total cost

**Margin**:
The Installer's markup on the Installation Cost.
_Avoid_: profit, markup rate

**Sale Price**:
The price the Customer pays for a System Option, before VAT.
_Avoid_: price, offer price

**Exchange Rate**:
The rate used to convert foreign-currency Catalog prices into TRY, with the date it applies to.
_Avoid_: currency rate, FX

### Financial result

**Annual Savings**:
The money a System Option saves the Customer in one year: the drop in the grid bill from Netted Energy (which comes off the highest Tariff Tier first) plus Exported Energy at the Export Price.
_Avoid_: profit, return

**Payback Period**:
The number of years until cumulative Annual Savings, net of later costs such as inverter replacement, first exceed the Sale Price including VAT, without discounting.

**Discount Rate**:
The real (inflation-adjusted) yearly rate at which a System Option's future net savings are brought back to today's lira.
_Avoid_: interest rate, hurdle rate

**Net Present Value**:
A System Option's net savings over its lifetime, each discounted at the Discount Rate, minus the Sale Price including VAT.
_Avoid_: profit, lifetime gain

**Internal Rate of Return**:
The real Discount Rate at which a System Option's Net Present Value is zero.
_Avoid_: ROI, yield
_Avoid_: ROI, amortization, break-even

### Quote

**Quote**:
The priced offer for one Site, holding one or more System Options and the Assumptions they were calculated with.
_Avoid_: offer, proposal, estimate

**Quote Number**:
The human-readable sequential identifier shown to the Customer, such as `SQ-2026-000123`.
_Avoid_: quote ID, reference

**Validity Period**:
The number of days a Quote's prices hold, which sets its valid-until date.
_Avoid_: expiry, deadline

**Assumptions**:
Every external input a Quote was calculated with (exchange rate, tariffs, ratios, unit prices, margin, VAT), recorded so the Quote can be reproduced.

**Narrative**:
The prose parts of a Quote's text (greeting, summary, options comparison for two System Options only, next steps), written by an LLM that refers to figures only through Placeholders.
_Avoid_: AI text, cover letter

**Placeholder**:
A `{name}` in the Narrative's prose that stands for a figure or the Customer's name, taken from a closed vocabulary (options are addressed by position, such as `{option_1_total_try}`) and filled from the Quote's displayed values. The LLM writes no digit outside a Placeholder.

**Narrative Context**:
The anonymised description of a Quote that the LLM receives: structure, flags and the available Placeholders, with no figure and no personal data.

**Narrative Draft**:
The prose slots as the LLM wrote them, text with Placeholders still unfilled. It is stored with the Quote only after it passes validation.

**Narrative source**:
Where a Quote's Narrative came from: `llm` (a validated Narrative Draft) or `fallback` (the template's fixed Turkish text, used when there is no key, the LLM fails, times out or is rejected twice).

### Quote assistant

**Assistant**:
The chat endpoint (`POST /assistant/messages`) through which a Sales Rep describes a Customer in Turkish and receives a Quote and a Turkish explanation of it. One request is one turn: the Assistant keeps no state, so the client sends the whole conversation each time.
_Avoid_: chatbot, agent, bot

**Conversation Model**:
The LLM behind the Assistant. In each step it either answers with text or calls one of the Assistant's tools (create the Quote, ask for Missing Fields); the Assistant calls it at most three times per request.
_Avoid_: chat model, agent

**Missing Fields**:
The required values of a Quote that the Sales Rep's conversation does not yet give, named by their `create_quote` field paths such as `roof.tilt_deg`. The Assistant asks for all of them in one Turkish question and lists them in the response.
_Avoid_: gaps, unknowns

**Echoed Digits**:
In a reply without a Quote, a digit sequence that the Sales Rep wrote themselves in their own messages. Only these may appear in such a reply (ADR 0004); a reply after a Quote may show figures only through Placeholders (ADR 0001).
