"""Typed errors the domain and its ports raise. The API layer maps each to a problem response."""

from decimal import Decimal


class DomainError(Exception):
    """Base class for every typed error that is part of the domain's contract."""


class AddressNotFoundError(DomainError):
    """The Geocoder found no match for the Address in Turkey."""

    def __init__(self) -> None:
        super().__init__("No match for the address in Turkey.")


class NoViableSystemError(DomainError):
    """The Roof fits no panel, so there is nothing to quote."""

    def __init__(self, reason: str = "the usable roof area fits no panel") -> None:
        super().__init__(f"no viable system: {reason}")


class QuoteNotFoundError(DomainError):
    """No stored Quote has the requested id."""

    def __init__(self, quote_id: object) -> None:
        self.quote_id = quote_id
        super().__init__(f"no quote with id {quote_id}")


class UnsupportedSubscriberGroupError(DomainError):
    """The Subscriber Group is not one this version prices."""

    def __init__(self, value: str, supported: tuple[str, ...] = ("residential",)) -> None:
        self.value = value
        super().__init__(
            f"unsupported Subscriber Group: {value!r}; supported: {', '.join(supported)}"
        )


class NarrativeUnavailableError(DomainError):
    """A `NarrativeWriter` could not give a draft: it timed out, was rate limited, could not be
    reached or answered with something unusable.

    Quote creation catches it and falls back to the template's fixed text, so no request ever
    fails with it and it has no problem mapping.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"the Narrative writer is unavailable: {reason}")


class ConversationUnavailableError(DomainError):
    """A `ConversationModel` could not answer: it timed out, was rate limited, could not be
    reached, blocked the prompt or answered with something unusable.

    Mapped to a 503 when no Quote exists yet. Once the assistant has created a Quote it falls
    back to a fixed confirmation instead.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"the conversation model is unavailable: {reason}")


class AssistantNotConfiguredError(DomainError):
    """The quote assistant has no conversation model, because no Gemini key is set."""

    def __init__(self) -> None:
        super().__init__("the assistant needs a Gemini API key (SUNQUOTE_GEMINI_API_KEY)")


class GeminiBudgetExhaustedError(DomainError):
    """The day's global Gemini request budget is spent, or could not be checked (ADR 0007).

    No request went out. The budget fails closed: when the counter store cannot be reached the
    count is unknown, so the request is refused too (`counter_unavailable`). Quote creation
    catches it and records a `fallback` Narrative with the reason. The quote assistant lets it
    through when no Quote exists yet, and the API answers 503.
    """

    def __init__(self, daily_limit: int, *, counter_unavailable: bool = False) -> None:
        self.daily_limit = daily_limit
        self.counter_unavailable = counter_unavailable
        if counter_unavailable:
            super().__init__(
                f"the daily Gemini budget of {daily_limit} requests could not be checked "
                "(counter store unavailable), so the request was refused"
            )
        else:
            super().__init__(
                f"the daily Gemini budget of {daily_limit} requests is spent; "
                "it resets at 00:00 Europe/Istanbul"
            )


class UpstreamUnavailableError(DomainError):
    """An external service (PVGIS, ...) could not be reached or gave no usable answer.

    Raised by the adapters that implement the domain's ports.
    """

    def __init__(self, service: str, reason: str) -> None:
        self.service = service
        self.reason = reason
        super().__init__(f"{service} is unavailable: {reason}")


class CurrencyMismatchError(DomainError):
    """Money of different currencies was combined, or converted with the wrong Exchange Rate.

    This is a programming or data error (for example a catalog price in a currency no Exchange
    Rate was fetched for), not something a request can cause, so it has no problem mapping.
    """

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"currency mismatch: expected {expected}, got {actual}")


class MissingExchangeRateError(DomainError):
    """A price is in a currency the Quote's Exchange Rate does not convert.

    A data error (the Catalog and pricing data name the currencies they are priced in, and the
    service fetches the rate for them), not something a request can cause.
    """

    def __init__(self, currency: str, rate_base: str) -> None:
        self.currency = currency
        self.rate_base = rate_base
        super().__init__(
            f"no Exchange Rate for {currency}: the Quote's rate converts {rate_base} to TRY only"
        )


class NoCompatibleInverterError(DomainError):
    """No inverter in the Catalog keeps the system's DC/AC Ratio within the configured range."""

    def __init__(self, capacity_kwp: Decimal) -> None:
        # The unrounded number: the API shows it through the rounding policy.
        self.capacity_kwp = capacity_kwp
        super().__init__(
            "no compatible inverter: none of the catalog inverters fits the system within the "
            "allowed DC/AC Ratio and the Contracted Power"
        )


class LocationNotSupportedError(DomainError):
    """The Specific Yield source rejected the Coordinates, for example a point over the sea.

    The message is the source's own explanation, so the Sales Rep can act on it.
    """


class RateLimitedError(DomainError):
    """A client used up its calls for the current window of a rate limit."""

    def __init__(self, policy_name: str, limit: int, window_seconds: int, retry_after_seconds: int):
        self.policy_name = policy_name
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"rate limit reached for {policy_name}: at most {limit} calls per "
            f"{window_seconds} seconds per client; try again in {retry_after_seconds} seconds"
        )
