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
The band of the Retail Tariff that applies, chosen by whether annual consumption is above the Subscriber Group's threshold.
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

**Self-Consumption Ratio**:
The share of annual production the Customer uses directly instead of exporting to the grid.

**Exported Energy**:
Production that is not self-consumed and is sold to the grid.
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
The money a System Option saves the Customer in one year: self-consumed energy at the Retail Tariff plus Exported Energy at the Export Price.
_Avoid_: profit, return

**Payback Period**:
The number of years until cumulative Annual Savings, net of later costs such as inverter replacement, first exceed the Sale Price including VAT, without discounting.
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
The prose parts of a Quote's text (greeting, summary, recommendation), written by an LLM that refers to figures only through placeholders.
_Avoid_: AI text, cover letter
