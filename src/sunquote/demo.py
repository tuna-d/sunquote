"""Seed synthetic sample Quotes or remove visitor Quotes from a demo database."""

import argparse
import asyncio
from decimal import Decimal

from sunquote.adapters.postgres.quote_repository import PostgresQuoteRepository, create_engine
from sunquote.bootstrap import build_dependencies
from sunquote.config import Settings
from sunquote.domain.model import (
    Consumption,
    Customer,
    QuoteRequest,
    Roof,
    RoofType,
    Site,
    SubscriberGroup,
)
from sunquote.domain.service import QuoteService


def _sample(name: str, address: str, roof: Roof, consumption: Consumption) -> QuoteRequest:
    return QuoteRequest(
        customer=Customer(name=name),
        site=Site(coordinates=None, address=address, roof=roof),
        consumption=consumption,
        subscriber_group=SubscriberGroup.RESIDENTIAL,
    )


# Synthetic Customers, Roofs and consumption inputs at public locations. The names are stable
# keys for seeding. The Quote service supplies all the figures derived from these inputs.
_SAMPLES = (
    _sample(
        "Demo Ankara A",
        "Çankaya, Ankara",
        Roof(RoofType.PITCHED, Decimal(40), azimuth_deg=Decimal(180), tilt_deg=Decimal(30)),
        Consumption(monthly_consumption_kwh=Decimal(640)),
    ),
    _sample(
        "Demo Ankara B",
        "Çankaya, Ankara",
        Roof(RoofType.FLAT, Decimal(40)),
        Consumption(monthly_bill_try=Decimal(5000)),
    ),
    _sample(
        "Demo İzmir A",
        "Konak, İzmir",
        Roof(RoofType.PITCHED, Decimal(30), azimuth_deg=Decimal(160), tilt_deg=Decimal(25)),
        Consumption(monthly_bill_try=Decimal(6000)),
    ),
    _sample(
        "Demo İzmir B",
        "Konak, İzmir",
        Roof(RoofType.FLAT, Decimal(75)),
        Consumption(monthly_consumption_kwh=Decimal(750)),
    ),
    _sample(
        "Demo Antalya A",
        "Muratpaşa, Antalya",
        Roof(RoofType.PITCHED, Decimal(55), azimuth_deg=Decimal(200), tilt_deg=Decimal(35)),
        Consumption(monthly_consumption_kwh=Decimal(850)),
    ),
    _sample(
        "Demo Antalya B",
        "Muratpaşa, Antalya",
        Roof(RoofType.FLAT, Decimal(48)),
        Consumption(monthly_bill_try=Decimal(7500)),
    ),
)


async def seed(repository: PostgresQuoteRepository, service: QuoteService) -> None:
    """Create the missing sample Quotes through the same service as the API."""
    existing_names = await repository.sample_customer_names()
    for request in _SAMPLES:
        if request.customer.name not in existing_names:
            await service.create_quote(request, is_sample=True)


async def _run(command: str, settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    try:
        repository = PostgresQuoteRepository(engine)
        if command == "reset":
            deleted = await repository.delete_non_sample_quotes()
            print(f"Deleted {deleted} non-sample Quotes.")
            return

        dependencies = build_dependencies(settings, quote_repository=repository)
        try:
            await seed(repository, dependencies.quote_service)
            print("Sample Quotes are ready.")
        finally:
            for close in dependencies.closers:
                await close()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "reset"))
    args = parser.parse_args()
    asyncio.run(_run(args.command, Settings()))


if __name__ == "__main__":
    main()
