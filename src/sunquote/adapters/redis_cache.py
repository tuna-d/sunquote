"""Best-effort Redis caching for the external lookup ports."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import partial

from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from sunquote.domain.model import GeocodingResult
from sunquote.domain.money import Currency, ExchangeRate
from sunquote.domain.ports import (
    ExchangeRateProvider,
    Geocoder,
    SpecificYieldProvider,
    SpecificYieldQuery,
)
from sunquote.domain.production import SpecificYield

_logger = logging.getLogger(__name__)
_KEY_PREFIX = "sunquote:v1"
_THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60
_GEOCODING_JSON = TypeAdapter(GeocodingResult)
_SPECIFIC_YIELD_JSON = TypeAdapter(SpecificYield)
_EXCHANGE_RATE_JSON = TypeAdapter(ExchangeRate)
_TURKISH_I = str.maketrans({"İ": "i", "I": "ı"})
_COORDINATE_STEP = Decimal("0.001")
_SOUTH_AZIMUTH_DEG = Decimal(180)


async def _get_or_fetch[T](
    redis: Redis,
    key: str,
    codec: TypeAdapter[T],
    fetch: Callable[[], Awaitable[T]],
    *,
    ttl: int | None,
) -> T:
    try:
        payload = await redis.get(key)
    except (OSError, RedisError) as error:
        _logger.warning("Redis cache read failed (%s)", type(error).__name__)
        return await fetch()

    if payload is not None:
        try:
            return codec.validate_json(payload)
        except ValidationError:
            _logger.warning("Redis cache entry could not be decoded")

    value = await fetch()
    try:
        await redis.set(key, codec.dump_json(value), ex=ttl)
    except (OSError, RedisError, PydanticSerializationError) as error:
        _logger.warning("Redis cache write failed (%s)", type(error).__name__)
    return value


class CachedGeocoder:
    def __init__(self, provider: Geocoder, redis: Redis) -> None:
        self._provider = provider
        self._redis = redis

    async def geocode(self, address: str) -> GeocodingResult:
        normalised_address = " ".join(address.split()).translate(_TURKISH_I).lower()
        return await _get_or_fetch(
            self._redis,
            f"{_KEY_PREFIX}:geocoding:{normalised_address}",
            _GEOCODING_JSON,
            partial(self._provider.geocode, address),
            ttl=_THIRTY_DAYS_SECONDS,
        )


class CachedSpecificYieldProvider:
    def __init__(self, provider: SpecificYieldProvider, redis: Redis) -> None:
        self._provider = provider
        self._redis = redis

    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        # Match PVGIS's coordinate rounding and aspect convention.
        latitude = _coordinate_key(query.coordinates.latitude)
        longitude = _coordinate_key(query.coordinates.longitude)
        tilt = _decimal_key(query.tilt_deg)
        aspect = _decimal_key(query.azimuth_deg - _SOUTH_AZIMUTH_DEG)
        loss = _decimal_key(query.system_loss_percent)
        return await _get_or_fetch(
            self._redis,
            f"{_KEY_PREFIX}:specific-yield:{latitude}:{longitude}:{tilt}:{aspect}:{loss}",
            _SPECIFIC_YIELD_JSON,
            partial(self._provider.fetch, query),
            ttl=_THIRTY_DAYS_SECONDS,
        )


class CachedExchangeRateProvider:
    def __init__(self, provider: ExchangeRateProvider, redis: Redis) -> None:
        self._provider = provider
        self._redis = redis

    async def fetch(self, currency: Currency, quote_date: date) -> ExchangeRate:
        return await _get_or_fetch(
            self._redis,
            f"{_KEY_PREFIX}:exchange-rate:{quote_date}:{currency}",
            _EXCHANGE_RATE_JSON,
            partial(self._provider.fetch, currency, quote_date),
            ttl=None,
        )


def _coordinate_key(value: Decimal) -> str:
    rounded = value.quantize(_COORDINATE_STEP, rounding=ROUND_HALF_UP)
    return format(rounded, "z.3f")


def _decimal_key(value: Decimal) -> str:
    text = format(value, "zf")
    return text.rstrip("0").rstrip(".") if "." in text else text
