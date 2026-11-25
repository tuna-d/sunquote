"""Per-client rate limits on the write endpoints, as FastAPI dependencies (ADR 0007)."""

import logging

from fastapi import Request

from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.domain.errors import RateLimitedError
from sunquote.domain.rate_limit import RateLimitPolicy

_logger = logging.getLogger(__name__)

HOUR_SECONDS = 3600
# The header Vercel's edge sets to the connecting client's IP. Unlike `x-forwarded-for`, a
# client cannot append to it, so it is trusted only when the app runs behind Vercel.
VERCEL_CLIENT_IP_HEADER = "x-vercel-forwarded-for"
UNKNOWN_CLIENT = "unknown"


def client_ip(request: Request, *, behind_vercel: bool) -> str:
    """The IP the request comes from: Vercel's header when behind Vercel, else the connection."""
    if behind_vercel:
        forwarded = request.headers.get(VERCEL_CLIENT_IP_HEADER, "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else UNKNOWN_CLIENT


async def _enforce(request: Request, policy: RateLimitPolicy) -> None:
    dependencies: AppDependencies = request.app.state.dependencies
    if dependencies.rate_limiter is None:
        return
    settings: Settings = request.app.state.settings
    ip = client_ip(request, behind_vercel=settings.behind_vercel)
    try:
        decision = await dependencies.rate_limiter.check(policy, ip)
    except Exception:
        # Abuse protection must not take the demo down with it: when the counters cannot be
        # reached the call goes through, and the failure is logged.
        _logger.warning("rate limit check failed; letting the call through", exc_info=True)
        return
    if not decision.allowed:
        raise RateLimitedError(
            policy.name, policy.limit, policy.window_seconds, decision.retry_after_seconds
        )


async def limit_quote_creation(request: Request) -> None:
    settings: Settings = request.app.state.settings
    await _enforce(
        request,
        RateLimitPolicy("create-quote", settings.rate_limit_quotes_per_hour, HOUR_SECONDS),
    )


async def limit_assistant_messages(request: Request) -> None:
    settings: Settings = request.app.state.settings
    await _enforce(
        request,
        RateLimitPolicy(
            "assistant-message", settings.rate_limit_assistant_messages_per_hour, HOUR_SECONDS
        ),
    )
