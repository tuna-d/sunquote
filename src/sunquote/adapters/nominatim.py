"""Nominatim search restricted to Turkey."""

import asyncio
from decimal import Decimal
from threading import Lock
from time import monotonic

import httpx

from sunquote.domain.errors import AddressNotFoundError, UpstreamUnavailableError
from sunquote.domain.model import Coordinates, GeocodingResult

_SERVICE = "Nominatim"
_request_slot_lock = Lock()
_next_request_at = float("-inf")


async def _wait_for_request_slot() -> None:
    global _next_request_at
    # All adapters in this process share the same clock and lock, even across event loops.
    while True:
        with _request_slot_lock:
            now = monotonic()
            delay = _next_request_at - now
            if delay <= 0:
                _next_request_at = now + 1
                return
        await asyncio.sleep(delay)


class NominatimGeocoder:
    def __init__(self, *, client: httpx.AsyncClient, base_url: str, timeout_seconds: float) -> None:
        self._client = client
        self._endpoint = f"{base_url.rstrip('/')}/search"
        self._timeout_seconds = timeout_seconds

    async def geocode(self, address: str) -> GeocodingResult:
        params = {
            "q": address,
            "format": "jsonv2",
            "countrycodes": "tr",
            "limit": "1",
            "addressdetails": "1",
        }
        await _wait_for_request_slot()
        try:
            response = await self._client.get(
                self._endpoint,
                params=params,
                headers={"User-Agent": "sunquote"},
                timeout=self._timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise UpstreamUnavailableError(_SERVICE, "the request timed out") from None
        except httpx.HTTPStatusError as error:
            raise UpstreamUnavailableError(_SERVICE, f"HTTP {error.response.status_code}") from None
        except httpx.RequestError as error:
            raise UpstreamUnavailableError(_SERVICE, type(error).__name__) from None
        return _parse(response)


def _parse(response: httpx.Response) -> GeocodingResult:
    try:
        matches = response.json(parse_float=Decimal)
        if not isinstance(matches, list):
            raise ValueError("expected a list of matches")
        if not matches:
            raise AddressNotFoundError
        match = matches[0]
        display_name = match["display_name"]
        details = match.get("address", {})
        if not isinstance(display_name, str) or not display_name or not isinstance(details, dict):
            raise ValueError("invalid address details")
        return GeocodingResult(
            display_name=display_name,
            coordinates=Coordinates(
                latitude=Decimal(match["lat"]), longitude=Decimal(match["lon"])
            ),
            district=_first_component(details, "town", "county", "city_district", "suburb"),
            province=_first_component(details, "province", "state"),
        )
    except (ArithmeticError, KeyError, TypeError, ValueError):
        raise UpstreamUnavailableError(_SERVICE, "the response could not be parsed") from None


def _first_component(details: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = details.get(key)
        if isinstance(value, str) and value:
            return value
    return None
