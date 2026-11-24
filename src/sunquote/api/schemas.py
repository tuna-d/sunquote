"""Request and response schemas of the quote API, and the mapping to and from the domain.

Rounding for display happens here, through the domain's rounding policy, and nowhere else.
Decimals leave the API as JSON numbers: the displayed figures are already rounded, and the
inputs recorded in the assumptions are short decimals that survive the trip exactly.
"""

from datetime import date
from decimal import Decimal
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
from sunquote.domain.catalog import Panel
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


class QuoteRequestBody(BaseModel):
    customer: CustomerBody
    site: SiteBody
    roof: RoofBody
    consumption: ConsumptionBody
    subscriber_group: str = Field(description="Only `residential` is supported.")

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


class PanelSummary(BaseModel):
    panel_id: str
    manufacturer: str
    model: str
    power_w: int


class PanelDatasheet(PanelSummary):
    length_mm: int
    width_mm: int
    area_m2: JsonNumber
    degradation_rate_per_year: JsonNumber


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


class AssumptionsResponse(BaseModel):
    submitted_request: SubmittedRequest
    pvgis_inputs: PvgisInputs
    roof_type: RoofType
    effective_azimuth_deg: JsonNumber
    effective_tilt_deg: JsonNumber
    coverage_ratio: JsonNumber
    default_panel: PanelDatasheet


class QuoteResponse(BaseModel):
    model_config = ConfigDict(title="Quote")

    customer: SubmittedCustomer
    quote_date: date
    system_options: list[SystemOptionResponse]
    assumptions: AssumptionsResponse


def _panel_summary(panel: Panel) -> PanelSummary:
    return PanelSummary(
        panel_id=panel.panel_id,
        manufacturer=panel.manufacturer,
        model=panel.model,
        power_w=panel.power_w,
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
            ),
        ),
    )
