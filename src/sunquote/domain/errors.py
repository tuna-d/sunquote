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
