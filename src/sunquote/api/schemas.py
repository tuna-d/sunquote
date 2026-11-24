"""Request and response schemas of the quote API, and the mapping to and from the domain.

Rounding for display happens here, through the domain's rounding policy, and nowhere else.
Decimals leave the API as JSON numbers: the displayed figures are already rounded, and the
inputs recorded in the assumptions are short decimals that survive the trip exactly.
"""

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from sunquote.domain import rounding
from sunquote.domain.assumptions import DcAcRatioRange, PricingAssumptions
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
from sunquote.domain.pricing import SystemPrice
from sunquote.domain.production import SpecificYieldInputs
from sunquote.domain.quote import Quote, SystemOption
from sunquote.domain.sizing import BindingLimit, SizingStrategy

JsonNumber = Annotated[
    Decimal, PlainSerializer(lambda value: float(value), return_type=float, when_used="json")
]


# --- Request -------------------------------------------------------------------------------


class CustomerBody(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    email: EmailStr | None = None


class SiteBody(BaseModel):
    latitude: Annotated[Decimal, Field(ge=-90, le=90)]
    longitude: Annotated[Decimal, Field(ge=-180, le=180)]


class RoofBody(BaseModel):
    roof_type: RoofType
    usable_area_m2: Annotated[Decimal, Field(gt=0)]
    azimuth_deg: Annotated[Decimal, Field(ge=0, lt=360)] | None = Field(
        default=None,
        validate_default=True,
        description="Compass bearing (180 = south). Required for pitched roofs, ignored for flat.",
    )
    tilt_deg: Annotated[Decimal, Field(ge=0, le=90)] | None = Field(
        default=None,
        validate_default=True,
        description="Required for pitched roofs, ignored for flat roofs.",
    )

    @field_validator("azimuth_deg", "tilt_deg", mode="before")
    @classmethod
    def _orientation_for_roof_type(cls, value: object, info: ValidationInfo) -> object:
        roof_type = info.data.get("roof_type")
        if roof_type is RoofType.FLAT:
            return None
        if roof_type is RoofType.PITCHED and value is None:
            raise ValueError("required for a pitched roof")
        return value


class ConsumptionBody(BaseModel):
    monthly_consumption_kwh: Annotated[Decimal, Field(gt=0)]


class ExchangeRateOverrideBody(BaseModel):
    rate: Annotated[Decimal, Field(gt=0)] = Field(description="TRY per 1 USD.")
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
            "USD/TRY rate to price with instead of TCMB's. When given, TCMB is not called "
            "and the Quote records that the rate was overridden."
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
                coordinates=Coordinates(latitude=self.site.latitude, longitude=self.site.longitude),
                roof=Roof(
                    roof_type=self.roof.roof_type,
                    usable_area_m2=self.roof.usable_area_m2,
                    azimuth_deg=self.roof.azimuth_deg,
                    tilt_deg=self.roof.tilt_deg,
                ),
            ),
            consumption=Consumption(
                monthly_consumption_kwh=self.consumption.monthly_consumption_kwh
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
    latitude: JsonNumber
    longitude: JsonNumber


class SubmittedRoof(BaseModel):
    roof_type: RoofType
    usable_area_m2: JsonNumber
    azimuth_deg: JsonNumber | None
    tilt_deg: JsonNumber | None


class SubmittedConsumption(BaseModel):
    monthly_consumption_kwh: JsonNumber


class SubmittedRequest(BaseModel):
    """The submitted inputs at full precision. Flat Roof angles are ignored."""

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
    """An amount at full precision with its currency, for unit prices and rates."""

    amount: JsonNumber
    currency: Currency


class PanelDatasheet(PanelSummary):
    length_mm: int
    width_mm: int
    area_m2: JsonNumber
    degradation_rate_per_year: JsonNumber
    unit_price: MoneyResponse


class InverterSummary(BaseModel):
    inverter_id: str
    manufacturer: str
    model: str
    ac_power_kw: JsonNumber


class InverterDatasheet(InverterSummary):
    unit_price: MoneyResponse


class ExchangeRateResponse(BaseModel):
    """1 `base_currency` buys `rate` `quote_currency` on `date`."""

    base_currency: Currency
    quote_currency: Currency
    rate: JsonNumber
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
    bos_price_per_kwp: MoneyResponse
    labour_price_per_kwp: MoneyResponse
    fixed_project_cost: MoneyResponse
    margin: JsonNumber
    vat_rate: JsonNumber


class DcAcRatioRangeResponse(BaseModel):
    minimum: JsonNumber
    maximum: JsonNumber


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


class SystemOptionResponse(BaseModel):
    strategy: SizingStrategy
    panel: PanelSummary
    panel_count: int
    capacity_kwp: JsonNumber
    binding_limit: BindingLimit
    annual_production_kwh: int
    monthly_production_kwh: list[MonthlyProduction]
    inverter: InverterSummary
    price: PriceResponse


class AssumptionsResponse(BaseModel):
    submitted_request: SubmittedRequest
    pvgis_inputs: PvgisInputs
    roof_type: RoofType
    effective_azimuth_deg: JsonNumber
    effective_tilt_deg: JsonNumber
    coverage_ratio: JsonNumber
    default_panel: PanelDatasheet
    inverters: list[InverterDatasheet]
    dc_ac_ratio_range: DcAcRatioRangeResponse
    contracted_power: ContractedPowerResponse
    pricing: PricingResponse
    exchange_rate: ExchangeRateResponse


class QuoteResponse(BaseModel):
    model_config = ConfigDict(title="Quote")

    customer: SubmittedCustomer
    quote_date: dt.date
    system_options: list[SystemOptionResponse]
    assumptions: AssumptionsResponse


def _panel_summary(panel: Panel) -> PanelSummary:
    return PanelSummary(
        panel_id=panel.panel_id,
        manufacturer=panel.manufacturer,
        model=panel.model,
        power_w=panel.power_w,
    )


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
        installation_cost_try=rounding.round_try(price.installation_cost.amount),
        sale_price_try=rounding.round_try(price.sale_price.amount),
        vat_try=rounding.round_try(price.vat.amount),
        total_try=rounding.round_try(price.total.amount),
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
        inverter=_inverter_summary(option.inverter),
        price=_price_response(option.price),
    )


def _submitted_request(request: QuoteRequest) -> SubmittedRequest:
    roof = request.site.roof
    return SubmittedRequest(
        customer=SubmittedCustomer(
            name=request.customer.name, phone=request.customer.phone, email=request.customer.email
        ),
        site=SubmittedSite(
            latitude=request.site.coordinates.latitude,
            longitude=request.site.coordinates.longitude,
        ),
        roof=SubmittedRoof(
            roof_type=roof.roof_type,
            usable_area_m2=roof.usable_area_m2,
            azimuth_deg=roof.azimuth_deg,
            tilt_deg=roof.tilt_deg,
        ),
        consumption=SubmittedConsumption(
            monthly_consumption_kwh=request.consumption.monthly_consumption_kwh
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


def quote_response(quote: Quote) -> QuoteResponse:
    recorded = quote.assumptions
    panel = recorded.default_panel
    return QuoteResponse(
        customer=SubmittedCustomer(
            name=quote.customer.name, phone=quote.customer.phone, email=quote.customer.email
        ),
        quote_date=quote.quote_date,
        system_options=[_option_response(option) for option in quote.system_options],
        assumptions=AssumptionsResponse(
            submitted_request=_submitted_request(recorded.submitted_request),
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
        ),
    )
