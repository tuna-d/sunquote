"""The collaborators the API needs, passed to the app factory so tests can inject fakes."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Request

from sunquote.domain.service import QuoteService


@dataclass(frozen=True)
class AppDependencies:
    """Everything the routes use. Later tickets add the repository, geocoder and so on here.

    `closers` run at shutdown, so a real HTTP client can be closed. Fakes leave it empty.
    """

    quote_service: QuoteService
    closers: tuple[Callable[[], Awaitable[None]], ...] = field(default=())


def get_quote_service(request: Request) -> QuoteService:
    dependencies: AppDependencies = request.app.state.dependencies
    return dependencies.quote_service
