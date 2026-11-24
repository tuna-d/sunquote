"""The reference data a Quote is calculated with, bundled so it travels as one argument."""

from dataclasses import dataclass

from sunquote.domain.assumptions import (
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog
from sunquote.domain.tariff import ResidentialTariff


@dataclass(frozen=True, slots=True)
class ReferenceData:
    """Everything a Quote reads besides the request, the Specific Yield and the Exchange Rate.

    It comes from the data files at startup and never changes while the service runs.
    """

    catalog: Catalog
    engineering: EngineeringAssumptions
    pricing: PricingAssumptions
    tariff: ResidentialTariff
    financial: FinancialAssumptions
