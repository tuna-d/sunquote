"""Request and response schemas of the quote API, and the mapping to and from the domain.

Rounding for display happens here, through the domain's rounding policy, and nowhere else.
Displayed figures (whole lira, rounded kWp, kWh and Payback Period) and plain measurements
(coordinates, areas, angles, kW) are JSON numbers. Money, rates, ratios and tariff prices are
recorded at full precision as decimal strings, which Pydantic writes for `Decimal`: a JSON
number would round-trip through `float`. Monthly Bills and their derived Monthly Consumption
are decimal strings too.
"""

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from sunquote.api.narrative_text import stored_narrative
from sunquote.api.option_views import option_views
from sunquote.domain import rounding
from sunquote.domain.assumptions import DcAcRatioRange, FinancialAssumptions, PricingAssumptions
from sunquote.domain.catalog import Inverter, Panel
from sunquote.domain.model import (
    Consumption,
    Coordinates,
    Customer,
    QuoteRequest,
    Roof,
    RoofType,
    Site,
    SubscriberGroup,
)
from sunquote.domain.money import Currency, ExchangeRate, ExchangeRateOverride, Money
from sunquote.domain.narrative import FallbackReason, NarrativeSource
from sunquote.domain.ports import QuotePage, StoredQuote
from sunquote.domain.pricing import SystemPrice
from sunquote.domain.production import SpecificYieldInputs
from sunquote.domain.quote import SystemOption
from sunquote.domain.savings import SavingsAnalysis, YearlyCashFlow
from sunquote.domain.sizing import BindingLimit, SizingStrategy
from sunquote.domain.tariff import ResidentialTariff

# A rounded display figure or a plain measurement, as a JSON number. Anything that must keep its
# precision is a plain `Decimal` field instead, which serialises as a decimal string.
JsonNumber = Annotated[
    Decimal, PlainSerializer(lambda value: float(value), return_type=float, when_used="json")
]


# --- Request -------------------------------------------------------------------------------


class CustomerBody(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    email: EmailStr | None = None


class SiteBody(BaseModel):
    latitude: Annotated[Decimal, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[Decimal, Field(ge=-180, le=180)] | None = None
    address: str | None = Field(
        default=None,
        description="Required without coordinates. A complete coordinate pair takes precedence.",
    )

    @model_validator(mode="after")
    def _require_address_or_coordinates(self) -> Self:
        if self.latitude is None and self.longitude is not None:
            field, message = "latitude", "required when longitude is given"
        elif self.longitude is None and self.latitude is not None:
            field, message = "longitude", "required when latitude is given"
        elif self.latitude is None and (self.address is None or not self.address.strip()):
            field, message = "address", "required when coordinates are absent"
        else:
            return self
        raise ValidationError.from_exception_data(
            type(self).__name__,
            [
                InitErrorDetails(
                    type=PydanticCustomError("site_input", message),
                    loc=(field,),
                    input=getattr(self, field),
                )
            ],
        )

    def coordinates(self) -> Coordinates | None:
        if self.latitude is None or self.longitude is None:
            return None
        return Coordinates(latitude=self.latitude, longitude=self.longitude)


class RoofBody(BaseModel):
    roof_type: RoofType
    usable_area_m2: Annotated[Decimal, Field(gt=0)]
    azimuth_deg: Annotated[Decimal, Field(ge=0, lt=360)] | None = Field(
        default=None,
        validate_default=True,
        description=(
            "Compass bearing (180 = south). Required for pitched roofs. A flat roof does not "
            "need it and does not use it (panels face south); a value given is recorded as "
            "submitted."
        ),
    )
    tilt_deg: Annotated[Decimal, Field(ge=0, le=90)] | None = Field(
        default=None,
        validate_default=True,
        description=(
            "Required for pitched roofs. A flat roof does not need it and does not use it "
            "(panels sit at the Installer's tilt); a value given is recorded as submitted."
        ),
    )

    @field_validator("azimuth_deg", "tilt_deg", mode="before")
    @classmethod
    def _require_for_pitched(cls, value: object, info: ValidationInfo) -> object:
        """Request-shape check only: what a flat roof does with the angles is the domain's."""
        if value is None and info.data.get("roof_type") is RoofType.PITCHED:
            raise ValueError("required for a pitched roof")
        return value


class ConsumptionBody(BaseModel):
    monthly_bill_try: Annotated[Decimal, Field(gt=0)] | None = Field(
        default=None, description="Average Monthly Bill in TRY, used when kWh is missing."
    )
    monthly_consumption_kwh: Annotated[Decimal, Field(gt=0)] | None = Field(
        default=None,
        validate_default=True,
        description="Average Monthly Consumption in kWh. Takes precedence over the bill.",
    )

    @field_validator("monthly_consumption_kwh")
    @classmethod
    def _require_consumption_or_bill(
        cls, value: Decimal | None, info: ValidationInfo
    ) -> Decimal | None:
        # If the bill failed validation, it already has a field error of its own.
        if (
            value is None
            and "monthly_bill_try" in info.data
            and info.data["monthly_bill_try"] is None
        ):
            raise ValueError("monthly_consumption_kwh or monthly_bill_try is required")
        return value


class ExchangeRateOverrideBody(BaseModel):
    rate: Annotated[Decimal, Field(gt=0)] = Field(
        description=(
            "TRY per 1 unit of the currency the Catalog and pricing data are priced in "
            "(USD in the placeholder data)."
        )
    )
    date: dt.date = Field(description="The date the rate applies to.")


class QuoteRequestBody(BaseModel):
    customer: CustomerBody
    site: SiteBody
    roof: RoofBody
    consumption: ConsumptionBody
    subscriber_group: str = Field(description="Only `residential` is supported.")
    contracted_power_kw: Annotated[Decimal, Field(gt=0)] | None = Field(
        default=None,
        description=(
            "The Site's Contracted Power in kW. It caps every System Option's panel count and "
            "inverter AC power. When absent, the Subscriber Group's default is used and the "
            "Quote records that it was defaulted."
        ),
    )
    exchange_rate_override: ExchangeRateOverrideBody | None = Field(
        default=None,
        description=(
            "Rate to price with instead of TCMB's, for the currency the Catalog and pricing data "
            "are priced in (USD in the placeholder data). When given, TCMB is not called and the "
            "Quote records that the rate was overridden."
        ),
    )

    def exchange_rate_override_to_domain(self) -> ExchangeRateOverride | None:
        if self.exchange_rate_override is None:
            return None
        return ExchangeRateOverride(
            rate=self.exchange_rate_override.rate, rate_date=self.exchange_rate_override.date
        )

    def to_domain(self) -> QuoteRequest:
        """Raises `UnsupportedSubscriberGroupError` for any group but residential."""
        return QuoteRequest(
            customer=Customer(
                name=self.customer.name, phone=self.customer.phone, email=self.customer.email
            ),
            site=Site(
                coordinates=self.site.coordinates(),
                roof=Roof(
                    roof_type=self.roof.roof_type,
                    usable_area_m2=self.roof.usable_area_m2,
                    azimuth_deg=self.roof.azimuth_deg,
                    tilt_deg=self.roof.tilt_deg,
                ),
                address=self.site.address,
            ),
            consumption=Consumption(
                monthly_consumption_kwh=self.consumption.monthly_consumption_kwh,
                monthly_bill_try=self.consumption.monthly_bill_try,
            ),
            subscriber_group=SubscriberGroup.parse(self.subscriber_group),
            contracted_power_kw=self.contracted_power_kw,
        )


# --- Response ------------------------------------------------------------------------------


class SubmittedCustomer(BaseModel):
    name: str
    phone: str | None
    email: str | None


class SubmittedSite(BaseModel):
    latitude: JsonNumber | None
    longitude: JsonNumber | None
    address: str | None = Field(default=None, exclude_if=lambda address: address is None)


class GeocodingResultResponse(BaseModel):
    display_name: str
    latitude: JsonNumber
    longitude: JsonNumber


class SubmittedRoof(BaseModel):
    roof_type: RoofType
    usable_area_m2: JsonNumber
    azimuth_deg: JsonNumber | None
    tilt_deg: JsonNumber | None


class SubmittedConsumption(BaseModel):
    monthly_consumption_kwh: JsonNumber | None
    monthly_bill_try: Decimal | None = Field(default=None, exclude_if=lambda bill: bill is None)


class SubmittedRequest(BaseModel):
    """The submitted inputs at full precision, exactly as given."""

    customer: SubmittedCustomer
    site: SubmittedSite
    roof: SubmittedRoof
    consumption: SubmittedConsumption
    subscriber_group: SubscriberGroup
    contracted_power_kw: JsonNumber | None


class PanelSummary(BaseModel):
    panel_id: str
    manufacturer: str
    model: str
    power_w: int


class MoneyResponse(BaseModel):
    """An amount with its currency, for unit prices. `amount` is a decimal string at full
    precision."""

    amount: Decimal
    currency: Currency


class PanelDatasheet(PanelSummary):
    length_mm: int
    width_mm: int
    area_m2: JsonNumber
    degradation_rate_per_year: Decimal
    unit_price: MoneyResponse


class InverterSummary(BaseModel):
    inverter_id: str
    manufacturer: str
    model: str
    ac_power_kw: JsonNumber


class InverterDatasheet(InverterSummary):
    unit_price: MoneyResponse


class ExchangeRateResponse(BaseModel):
    """1 `base_currency` buys `rate` `quote_currency` on `date`. `rate` is a decimal string."""

    base_currency: Currency
    quote_currency: Currency
    rate: Decimal
    date: dt.date
    overridden: bool


class ContractedPowerSource(StrEnum):
    GIVEN = "given"
    DEFAULTED = "defaulted"


class ContractedPowerResponse(BaseModel):
    """The Contracted Power every System Option was sized against, and where it came from."""

    kw: JsonNumber
    source: ContractedPowerSource


class PricingResponse(BaseModel):
    """The prices the Installation Cost was built from. `margin` and `vat_rate` are shares as
    decimal strings (0.25 is 25%)."""

    bos_price_per_kwp: MoneyResponse
    labour_price_per_kwp: MoneyResponse
    fixed_project_cost: MoneyResponse
    margin: Decimal
    vat_rate: Decimal
    validity_period_days: int


class DcAcRatioRangeResponse(BaseModel):
    """The allowed DC/AC Ratio, as decimal strings."""

    minimum: Decimal
    maximum: Decimal


class PriceResponse(BaseModel):
    """What the Customer pays for a System Option, in whole lira."""

    installation_cost_try: int
    sale_price_try: int
    vat_try: int
    total_try: int


class PvgisInputs(BaseModel):
    """What PVGIS was actually asked. `aspect_deg` is PVGIS's: 0 = south, 90 = west."""

    source: str
    latitude: JsonNumber
    longitude: JsonNumber
    tilt_deg: JsonNumber
    aspect_deg: JsonNumber
    system_loss_percent: JsonNumber


class MonthlyProduction(BaseModel):
    month: int = Field(ge=1, le=12)
    production_kwh: int


class CashFlowRow(BaseModel):
    """One year of the cash flow, in today's lira (escalation rates are real, ADR 0003)."""

    year: int = Field(ge=1)
    production_kwh: int
    netted_kwh: int
    exported_kwh: int
    netting_savings_try: int
    export_income_try: int
    annual_savings_try: int
    inverter_replacement_try: int
    net_savings_try: int
    cumulative_net_savings_try: int


class SavingsResponse(BaseModel):
    """What a System Option saves the Customer, in today's lira.

    `payback_period_years` is null, with `payback_beyond_lifetime` true, when the total price
    including VAT is not recovered within the lifetime.
    """

    first_year_annual_savings_try: int
    payback_period_years: JsonNumber | None
    payback_beyond_lifetime: bool
    lifetime_savings_try: int = Field(
        description="Total net savings, after the inverter replacement."
    )
    cash_flow: list[CashFlowRow]


class SystemOptionResponse(BaseModel):
    strategy: SizingStrategy
    panel: PanelSummary
    panel_count: int
    capacity_kwp: JsonNumber
    binding_limit: BindingLimit
    annual_production_kwh: int
    monthly_production_kwh: list[MonthlyProduction]
    netted_share: JsonNumber = Field(
        description=(
            "Share of year 1's production that offsets the bill month by month (Monthly "
            "Netting); the rest is exported. A decimal between 0 and 1."
        )
    )
    inverter: InverterSummary
    price: PriceResponse
    savings: SavingsResponse


class TariffResponse(BaseModel):
    """The residential Retail Tariff the savings were calculated with (ADR 0002, ADR 0005): the
    Tariff Tiers are applied per month, a month's threshold being `tier_threshold_kwh_per_day`
    times the month's days. Every figure is a decimal string at full precision."""

    tier_threshold_kwh_per_day: Decimal
    low_tariff_try_per_kwh: Decimal
    high_tariff_try_per_kwh: Decimal
    export_price_try_per_kwh: Decimal
    valid_from: dt.date
    source: str


class FinancialResponse(BaseModel):
    """Both escalation rates are real (inflation-adjusted): all figures are in today's lira.
    The rates are decimal strings (0.02 is 2%)."""

    tariff_escalation_rate_real: Decimal
    equipment_escalation_rate_real: Decimal
    lifetime_years: int
    inverter_replacement_year: int


class AssumptionsResponse(BaseModel):
    """Everything the Quote was calculated with, at full precision. Money, rates, ratios and
    tariff prices are decimal strings; measurements (coordinates, areas, angles, kW, kWh) are
    JSON numbers."""

    submitted_request: SubmittedRequest
    geocoding_result: GeocodingResultResponse | None
    pvgis_inputs: PvgisInputs
    roof_type: RoofType
    effective_azimuth_deg: JsonNumber
    effective_tilt_deg: JsonNumber
    coverage_ratio: Decimal
    default_panel: PanelDatasheet
    inverters: list[InverterDatasheet]
    dc_ac_ratio_range: DcAcRatioRangeResponse
    contracted_power: ContractedPowerResponse
    pricing: PricingResponse
    exchange_rate: ExchangeRateResponse
    consumption_derived_from_bill: bool
    derived_monthly_consumption_kwh: Decimal | None
    annual_consumption_kwh: JsonNumber
    low_tier_consumption_kwh: JsonNumber
    high_tier_consumption_kwh: JsonNumber
    tariff: TariffResponse
    financial: FinancialResponse


class NarrativeResponse(BaseModel):
    """The prose of the Quote document, with every placeholder filled from the Quote."""

    model_config = ConfigDict(title="Narrative")

    greeting: str
    summary: str
    options_comparison: str | None = Field(
        description="Only for a Quote with two System Options; otherwise null."
    )
    next_steps: str
    source: NarrativeSource = Field(
        description="`llm` when a writer's validated text is shown, `fallback` for the fixed text."
    )
    model: str | None = Field(description="The model that wrote the text; null for `fallback`.")
    fallback_reason: FallbackReason | None = Field(
        description=(
            "Why the fixed text is shown, when the cause is recorded: `budget_spent` when the "
            "day's Gemini budget was spent. Null for `llm` and for other causes."
        )
    )
    generated_at: dt.datetime | None = Field(
        description="When the Narrative step ran; null for Quotes stored before it existed."
    )


class QuoteResponse(BaseModel):
    model_config = ConfigDict(title="Quote")

    id: UUID
    quote_number: str = Field(description="Readable identifier, `SQ-<year>-<6-digit sequence>`.")
    created_at: dt.datetime
    is_sample: bool = Field(description="Whether this is a synthetic sample Quote.")
    customer: SubmittedCustomer
    quote_date: dt.date
    valid_until: dt.date = Field(description="The last day the quoted price holds.")
    system_options: list[SystemOptionResponse]
    narrative: NarrativeResponse
    assumptions: AssumptionsResponse


def _panel_summary(panel: Panel) -> PanelSummary:
    return PanelSummary(
        panel_id=panel.panel_id,
        manufacturer=panel.manufacturer,
        model=panel.model,
        power_w=panel.power_w,
    )


def _whole_lira(money: Money) -> int:
    """A TRY amount in whole lira, by the rounding policy."""
    return rounding.round_try(money.amount)


def _money(money: Money) -> MoneyResponse:
    return MoneyResponse(amount=money.amount, currency=money.currency)


def _inverter_summary(inverter: Inverter) -> InverterSummary:
    return InverterSummary(
        inverter_id=inverter.inverter_id,
        manufacturer=inverter.manufacturer,
        model=inverter.model,
        ac_power_kw=inverter.ac_power_kw,
    )


def _price_response(price: SystemPrice) -> PriceResponse:
    return PriceResponse(
        installation_cost_try=_whole_lira(price.installation_cost),
        sale_price_try=_whole_lira(price.sale_price),
        vat_try=_whole_lira(price.vat),
        total_try=_whole_lira(price.total),
    )


def _cash_flow_row(row: YearlyCashFlow) -> CashFlowRow:
    return CashFlowRow(
        year=row.year,
        production_kwh=rounding.round_kwh(row.production_kwh),
        netted_kwh=rounding.round_kwh(row.netted_kwh),
        exported_kwh=rounding.round_kwh(row.exported_kwh),
        netting_savings_try=_whole_lira(row.netting_savings),
        export_income_try=_whole_lira(row.export_income),
        annual_savings_try=_whole_lira(row.annual_savings),
        inverter_replacement_try=_whole_lira(row.inverter_replacement),
        net_savings_try=_whole_lira(row.net_savings),
        cumulative_net_savings_try=_whole_lira(row.cumulative_net_savings),
    )


def _savings_response(savings: SavingsAnalysis) -> SavingsResponse:
    payback = savings.payback_years
    return SavingsResponse(
        first_year_annual_savings_try=_whole_lira(savings.first_year_annual_savings),
        payback_period_years=None if payback is None else rounding.round_payback_years(payback),
        payback_beyond_lifetime=savings.payback_beyond_lifetime,
        lifetime_savings_try=_whole_lira(savings.lifetime_savings),
        cash_flow=[_cash_flow_row(row) for row in savings.cash_flow],
    )


def _tariff_response(tariff: ResidentialTariff) -> TariffResponse:
    return TariffResponse(
        tier_threshold_kwh_per_day=tariff.tier_threshold_kwh_per_day,
        low_tariff_try_per_kwh=tariff.low_tariff_try_per_kwh,
        high_tariff_try_per_kwh=tariff.high_tariff_try_per_kwh,
        export_price_try_per_kwh=tariff.export_price_try_per_kwh,
        valid_from=tariff.valid_from,
        source=tariff.source,
    )


def _financial_response(financial: FinancialAssumptions) -> FinancialResponse:
    return FinancialResponse(
        tariff_escalation_rate_real=financial.tariff_escalation_rate_real,
        equipment_escalation_rate_real=financial.equipment_escalation_rate_real,
        lifetime_years=financial.lifetime_years,
        inverter_replacement_year=financial.inverter_replacement_year,
    )


def _option_response(option: SystemOption) -> SystemOptionResponse:
    return SystemOptionResponse(
        strategy=option.strategy,
        panel=_panel_summary(option.panel),
        panel_count=option.panel_count,
        capacity_kwp=rounding.round_capacity_kwp(option.capacity_kwp),
        binding_limit=option.binding_limit,
        annual_production_kwh=rounding.round_kwh(option.annual_production_kwh),
        monthly_production_kwh=[
            MonthlyProduction(month=month, production_kwh=rounding.round_kwh(kwh))
            for month, kwh in enumerate(option.monthly_production_kwh, start=1)
        ],
        netted_share=rounding.round_share(option.savings.netted_share),
        inverter=_inverter_summary(option.inverter),
        price=_price_response(option.price),
        savings=_savings_response(option.savings),
    )


def _submitted_request(request: QuoteRequest) -> SubmittedRequest:
    roof = request.site.roof
    coordinates = request.site.coordinates
    return SubmittedRequest(
        customer=SubmittedCustomer(
            name=request.customer.name, phone=request.customer.phone, email=request.customer.email
        ),
        site=SubmittedSite(
            latitude=coordinates.latitude if coordinates else None,
            longitude=coordinates.longitude if coordinates else None,
            address=request.site.address,
        ),
        roof=SubmittedRoof(
            roof_type=roof.roof_type,
            usable_area_m2=roof.usable_area_m2,
            azimuth_deg=roof.azimuth_deg,
            tilt_deg=roof.tilt_deg,
        ),
        consumption=SubmittedConsumption(
            monthly_consumption_kwh=request.consumption.monthly_consumption_kwh,
            monthly_bill_try=request.consumption.monthly_bill_try,
        ),
        subscriber_group=request.subscriber_group,
        contracted_power_kw=request.contracted_power_kw,
    )


def _pvgis_inputs(inputs: SpecificYieldInputs) -> PvgisInputs:
    return PvgisInputs(
        source=inputs.source,
        latitude=inputs.latitude,
        longitude=inputs.longitude,
        tilt_deg=inputs.tilt_deg,
        aspect_deg=inputs.aspect_deg,
        system_loss_percent=inputs.system_loss_percent,
    )


def _pricing_response(pricing: PricingAssumptions) -> PricingResponse:
    return PricingResponse(
        bos_price_per_kwp=_money(pricing.bos_price_per_kwp),
        labour_price_per_kwp=_money(pricing.labour_price_per_kwp),
        fixed_project_cost=_money(pricing.fixed_project_cost),
        margin=pricing.margin,
        vat_rate=pricing.vat_rate,
        validity_period_days=pricing.validity_period_days,
    )


def _exchange_rate_response(rate: ExchangeRate) -> ExchangeRateResponse:
    return ExchangeRateResponse(
        base_currency=rate.base,
        quote_currency=rate.quote,
        rate=rate.rate,
        date=rate.rate_date,
        overridden=rate.overridden,
    )


def _dc_ac_range_response(ratio_range: DcAcRatioRange) -> DcAcRatioRangeResponse:
    return DcAcRatioRangeResponse(minimum=ratio_range.minimum, maximum=ratio_range.maximum)


def _narrative_response(stored: StoredQuote) -> NarrativeResponse:
    filled = stored_narrative(stored, option_views(stored))
    record = stored.quote.narrative
    return NarrativeResponse(
        greeting=filled.greeting,
        summary=filled.summary,
        options_comparison=filled.options_comparison,
        next_steps=filled.next_steps,
        source=record.source,
        model=record.model,
        fallback_reason=record.fallback_reason,
        generated_at=record.generated_at,
    )


def quote_response(stored: StoredQuote) -> QuoteResponse:
    quote = stored.quote
    recorded = quote.assumptions
    panel = recorded.default_panel
    match = recorded.geocoding_result
    return QuoteResponse(
        id=stored.id,
        quote_number=quote.quote_number,
        created_at=stored.created_at,
        is_sample=stored.is_sample,
        customer=SubmittedCustomer(
            name=quote.customer.name, phone=quote.customer.phone, email=quote.customer.email
        ),
        quote_date=quote.quote_date,
        valid_until=quote.valid_until,
        system_options=[_option_response(option) for option in quote.system_options],
        narrative=_narrative_response(stored),
        assumptions=AssumptionsResponse(
            submitted_request=_submitted_request(recorded.submitted_request),
            geocoding_result=(
                GeocodingResultResponse(
                    display_name=match.display_name,
                    latitude=match.coordinates.latitude,
                    longitude=match.coordinates.longitude,
                )
                if match
                else None
            ),
            pvgis_inputs=_pvgis_inputs(recorded.pvgis_inputs),
            roof_type=recorded.roof_type,
            effective_azimuth_deg=recorded.effective_azimuth_deg,
            effective_tilt_deg=recorded.effective_tilt_deg,
            coverage_ratio=recorded.coverage_ratio,
            default_panel=PanelDatasheet(
                panel_id=panel.panel_id,
                manufacturer=panel.manufacturer,
                model=panel.model,
                power_w=panel.power_w,
                length_mm=panel.length_mm,
                width_mm=panel.width_mm,
                area_m2=panel.area_m2,
                degradation_rate_per_year=panel.degradation_rate_per_year,
                unit_price=_money(panel.unit_price),
            ),
            inverters=[
                InverterDatasheet(
                    **_inverter_summary(inverter).model_dump(),
                    unit_price=_money(inverter.unit_price),
                )
                for inverter in recorded.inverters
            ],
            dc_ac_ratio_range=_dc_ac_range_response(recorded.dc_ac_ratio_range),
            contracted_power=ContractedPowerResponse(
                kw=recorded.contracted_power.kw,
                source=(
                    ContractedPowerSource.GIVEN
                    if recorded.contracted_power.given
                    else ContractedPowerSource.DEFAULTED
                ),
            ),
            pricing=_pricing_response(recorded.pricing),
            exchange_rate=_exchange_rate_response(recorded.exchange_rate),
            consumption_derived_from_bill=recorded.consumption_derived_from_bill,
            derived_monthly_consumption_kwh=recorded.derived_monthly_consumption_kwh,
            annual_consumption_kwh=recorded.annual_consumption_kwh,
            low_tier_consumption_kwh=recorded.low_tier_consumption_kwh,
            high_tier_consumption_kwh=recorded.high_tier_consumption_kwh,
            tariff=_tariff_response(recorded.tariff),
            financial=_financial_response(recorded.financial),
        ),
    )


# --- Quote list -----------------------------------------------------------------------------


class QuoteListItem(BaseModel):
    """What the Sales Rep needs to recognise a Quote without opening it."""

    id: UUID
    quote_number: str
    created_at: dt.datetime
    is_sample: bool = Field(description="Whether this is a synthetic sample Quote.")
    customer_name: str
    district: str | None = Field(description="Null until address geocoding exists.")
    province: str | None = Field(description="Null until address geocoding exists.")
    system_option_count: int
    capacity_kwp: JsonNumber = Field(description="Of the first System Option.")
    total_try: int = Field(description="Total price including VAT of the first System Option.")


class QuoteListResponse(BaseModel):
    items: list[QuoteListItem]
    page: int
    page_size: int
    total: int = Field(description="The number of stored Quotes, across all pages.")


def _list_item(stored: StoredQuote) -> QuoteListItem:
    quote = stored.quote
    first = quote.system_options[0]
    return QuoteListItem(
        id=stored.id,
        quote_number=quote.quote_number,
        created_at=stored.created_at,
        is_sample=stored.is_sample,
        customer_name=quote.customer.name,
        district=stored.district,
        province=stored.province,
        system_option_count=len(quote.system_options),
        capacity_kwp=rounding.round_capacity_kwp(first.capacity_kwp),
        total_try=_whole_lira(first.price.total),
    )


def quote_list_response(page: QuotePage, *, page_number: int, page_size: int) -> QuoteListResponse:
    return QuoteListResponse(
        items=[_list_item(stored) for stored in page.items],
        page=page_number,
        page_size=page_size,
        total=page.total,
    )
