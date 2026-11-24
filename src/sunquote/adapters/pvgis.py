"""PVGIS `PVcalc` adapter: the Specific Yield for a Site and a fixed-mounted roof."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import httpx

from sunquote.domain.errors import LocationNotSupportedError, UpstreamUnavailableError
from sunquote.domain.ports import SpecificYieldQuery
from sunquote.domain.production import SpecificYield, SpecificYieldInputs

DEFAULT_PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_3"
_SERVICE = "PVGIS"
_COORDINATE_STEP = Decimal("0.001")
_SOUTH_AZIMUTH_DEG = Decimal(180)


def _plain(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class PvgisRequest:
    """The values PVGIS is asked for: after the coordinate rounding and the aspect conversion."""

    latitude: Decimal
    longitude: Decimal
    tilt_deg: Decimal
    aspect_deg: Decimal
    system_loss_percent: Decimal


def pvgis_request(query: SpecificYieldQuery) -> PvgisRequest:
    """What PVGIS receives for `query`. The one definition of its rounding and aspect rules:
    the call and the cache key (`redis_cache`) both read it, so they cannot drift apart.
    """
    return PvgisRequest(
        # Coordinates are rounded to 3 decimals (about 100 m) before the call: finer than the
        # data resolution, and it makes equal sites share one request.
        latitude=query.coordinates.latitude.quantize(_COORDINATE_STEP, rounding=ROUND_HALF_UP),
        longitude=query.coordinates.longitude.quantize(_COORDINATE_STEP, rounding=ROUND_HALF_UP),
        tilt_deg=query.tilt_deg,
        # PVGIS measures the aspect from south (0), west positive; the compass has south at 180.
        aspect_deg=query.azimuth_deg - _SOUTH_AZIMUTH_DEG,
        system_loss_percent=query.system_loss_percent,
    )


class PvgisSpecificYieldProvider:
    """Calls PVGIS for 1 kWp and returns the annual and 12 monthly yields in kWh/kWp.

    The HTTP client is injected so tests can swap the transport. Every call carries its own
    timeout, whatever the client's defaults are.
    """

    def __init__(self, *, client: httpx.AsyncClient, base_url: str, timeout_seconds: float) -> None:
        self._client = client
        self._endpoint = f"{base_url.rstrip('/')}/PVcalc"
        self._timeout_seconds = timeout_seconds

    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        request = pvgis_request(query)
        params = {
            "lat": _plain(request.latitude),
            "lon": _plain(request.longitude),
            "peakpower": "1",
            "loss": _plain(request.system_loss_percent),
            "angle": _plain(request.tilt_deg),
            "aspect": _plain(request.aspect_deg),
            "outputformat": "json",
        }
        response = await self._get(params)
        return self._parse(
            response,
            SpecificYieldInputs(
                source=self._endpoint,
                latitude=request.latitude,
                longitude=request.longitude,
                tilt_deg=request.tilt_deg,
                aspect_deg=request.aspect_deg,
                system_loss_percent=request.system_loss_percent,
            ),
        )

    async def _get(self, params: dict[str, str]) -> httpx.Response:
        try:
            response = await self._client.get(
                self._endpoint, params=params, timeout=self._timeout_seconds
            )
        except httpx.TimeoutException:
            raise UpstreamUnavailableError(_SERVICE, "the request timed out") from None
        except httpx.TransportError as error:
            raise UpstreamUnavailableError(
                _SERVICE, f"could not connect ({type(error).__name__})"
            ) from None
        if response.status_code == 400:
            # PVGIS answers 400 with an explanation when it cannot serve the point, for example
            # "Location over the sea". The request is well-formed, so the Site is the problem.
            raise LocationNotSupportedError(
                _error_message(response) or "PVGIS rejected the location (HTTP 400)"
            )
        if response.status_code != 200:
            raise UpstreamUnavailableError(
                _SERVICE, f"HTTP {response.status_code}: {_error_message(response)}"
            )
        return response

    @staticmethod
    def _parse(response: httpx.Response, inputs: SpecificYieldInputs) -> SpecificYield:
        try:
            body = response.json(parse_float=Decimal)
            annual = body["outputs"]["totals"]["fixed"]["E_y"]
            months = sorted(body["outputs"]["monthly"]["fixed"], key=lambda row: row["month"])
            monthly = tuple(Decimal(row["E_m"]) for row in months)
            return SpecificYield(
                annual_kwh_per_kwp=Decimal(annual), monthly_kwh_per_kwp=monthly, inputs=inputs
            )
        except (ValueError, KeyError, TypeError, ArithmeticError):
            raise UpstreamUnavailableError(_SERVICE, "the response could not be parsed") from None


def _error_message(response: httpx.Response) -> str:
    """PVGIS explains client errors as a JSON `message`; fall back to a short body excerpt."""
    try:
        message = response.json()["message"]
        if isinstance(message, str):
            return message
    except (ValueError, KeyError, TypeError):
        pass
    return response.text[:200]
