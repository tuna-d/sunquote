"""The reference data a Quote is calculated with, bundled so it travels as one argument."""

from dataclasses import dataclass

from sunquote.domain.assumptions import (
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog
from sunquote.domain.money import Currency
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

    def __post_init__(self) -> None:
        _ = self.exchange_rate_currency  # fail fast on prices a Quote cannot convert

    @property
    def exchange_rate_currency(self) -> Currency:
        """The one foreign currency the prices are in, so the Quote needs one Exchange Rate.

        The data files declare each price's currency and this is the single place the Quote's
        rate currency comes from. Raises `ValueError` when no price is in a foreign currency or
        when they are in more than one (a Quote records a single Exchange Rate).
        """
        prices = (
            *(panel.unit_price for panel in self.catalog.panels),
            *(inverter.unit_price for inverter in self.catalog.inverters),
            self.pricing.bos_price_per_kwp,
            self.pricing.labour_price_per_kwp,
            self.pricing.fixed_project_cost,
        )
        foreign = sorted({price.currency for price in prices} - {Currency.TRY})
        if not foreign:
            raise ValueError(
                "no price is in a foreign currency, so the Quote has no Exchange Rate to record"
            )
        if len(foreign) > 1:
            raise ValueError(
                "prices are in more than one foreign currency "
                f"({', '.join(foreign)}); a Quote records one Exchange Rate"
            )
        return foreign[0]
