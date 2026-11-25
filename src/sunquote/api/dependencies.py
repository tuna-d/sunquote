"""The collaborators the API needs, passed to the app factory so tests can inject fakes."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Request

from sunquote.domain.conversation import DEFAULT_ASSISTANT_BUDGET_SECONDS
from sunquote.domain.ports import ConversationModel, QuoteRepository
from sunquote.domain.rate_limit import FixedWindowRateLimiter
from sunquote.domain.service import QuoteService


@dataclass(frozen=True)
class AppDependencies:
    """Everything the routes use. Later tickets add the repository, geocoder and so on here.

    `startup` hooks run before the app serves (the real wiring applies the database
    migrations there) and `closers` run at shutdown, so a real HTTP client or connection pool
    can be closed. Fakes leave both empty. `quote_repository` is the one the service saves to;
    the read endpoints use it directly. `conversation_model` is the quote assistant's LLM; with
    none the assistant answers 503 and the rest of the API is unaffected. `rate_limiter` limits the
    write endpoints per client; with none nothing is limited.
    """

    quote_service: QuoteService
    quote_repository: QuoteRepository
    conversation_model: ConversationModel | None = None
    assistant_budget_seconds: float = DEFAULT_ASSISTANT_BUDGET_SECONDS
    rate_limiter: FixedWindowRateLimiter | None = None
    startup: tuple[Callable[[], Awaitable[None]], ...] = field(default=())
    closers: tuple[Callable[[], Awaitable[None]], ...] = field(default=())


def get_quote_repository(request: Request) -> QuoteRepository:
    dependencies: AppDependencies = request.app.state.dependencies
    return dependencies.quote_repository


def get_quote_service(request: Request) -> QuoteService:
    dependencies: AppDependencies = request.app.state.dependencies
    return dependencies.quote_service
