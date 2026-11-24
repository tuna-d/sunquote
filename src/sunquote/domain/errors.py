"""Typed errors the domain and its ports raise. The API layer maps each to a problem response."""


class DomainError(Exception):
    """Base class for every typed error that is part of the domain's contract."""


class NoViableSystemError(DomainError):
    """The Roof fits no panel, so there is nothing to quote."""

    def __init__(self) -> None:
        super().__init__("no viable system: the usable roof area fits no panel")


class UnsupportedSubscriberGroupError(DomainError):
    """The Subscriber Group is not one this version prices."""

    def __init__(self, value: str, supported: tuple[str, ...] = ("residential",)) -> None:
        self.value = value
        super().__init__(
            f"unsupported Subscriber Group: {value!r}; supported: {', '.join(supported)}"
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


class NoCompatibleInverterError(DomainError):
    """No inverter in the Catalog keeps the system's DC/AC Ratio within the configured range."""

    def __init__(self, capacity_kwp: str) -> None:
        self.capacity_kwp = capacity_kwp
        super().__init__(
            f"no compatible inverter: none of the catalog inverters fits a {capacity_kwp} kWp "
            "system within the allowed DC/AC Ratio"
        )


class LocationNotSupportedError(DomainError):
    """The Specific Yield source rejected the Coordinates, for example a point over the sea.

    The message is the source's own explanation, so the Sales Rep can act on it.
    """
