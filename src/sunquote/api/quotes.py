from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from sunquote.api.dependencies import get_quote_repository, get_quote_service
from sunquote.api.document import render_quote_document
from sunquote.api.errors import (
    ADDRESS_NOT_FOUND,
    LOCATION_NOT_SUPPORTED,
    NO_COMPATIBLE_INVERTER,
    NO_VIABLE_SYSTEM,
    QUOTE_NOT_FOUND,
    RATE_LIMITED,
    UNSUPPORTED_SUBSCRIBER_GROUP,
    UPSTREAM_UNAVAILABLE,
    VALIDATION_ERROR,
    problem_responses,
)
from sunquote.api.rate_limit import limit_quote_creation
from sunquote.api.schemas import (
    QuoteListResponse,
    QuoteRequestBody,
    QuoteResponse,
    quote_list_response,
    quote_response,
)
from sunquote.domain.errors import QuoteNotFoundError
from sunquote.domain.ports import QuoteRepository, StoredQuote
from sunquote.domain.service import QuoteService

router = APIRouter(tags=["quotes"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


async def get_stored_quote(
    quote_id: UUID,
    repository: Annotated[QuoteRepository, Depends(get_quote_repository)],
) -> StoredQuote:
    """The stored Quote of the `quote_id` path parameter. Raises `QuoteNotFoundError` (404)."""
    stored = await repository.get(quote_id)
    if stored is None:
        raise QuoteNotFoundError(quote_id)
    return stored


@router.post(
    "/quotes",
    status_code=201,
    summary="Create a Quote",
    dependencies=[Depends(limit_quote_creation)],
    responses=problem_responses(
        VALIDATION_ERROR,
        RATE_LIMITED,
        UNSUPPORTED_SUBSCRIBER_GROUP,
        NO_VIABLE_SYSTEM,
        NO_COMPATIBLE_INVERTER,
        LOCATION_NOT_SUPPORTED,
        ADDRESS_NOT_FOUND,
        UPSTREAM_UNAVAILABLE,
    ),
)
async def create_quote(
    body: QuoteRequestBody,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteResponse:
    """Size a system for the Customer's Site and return the Quote.

    Each client IP may create 10 Quotes an hour (configurable); past that the answer is `429`
    with a `Retry-After` header, whatever the body holds.

    Give the Site Address or both Coordinates. Coordinates take precedence when both are
    given. An Address lookup records the resolved match in the Quote's Assumptions.

    The Quote holds a Consumption-Matched System Option and, when its panel count differs, a
    Roof-Max one after it. Neither is marked as recommended. Both are capped by the Contracted
    Power (given, or the Subscriber Group's default: the cap uses the largest Catalog inverter
    within it) and each has its first-year production, its
    inverter (AC power at most the Contracted Power) and its price in TRY (Installation Cost,
    Sale Price, VAT and total, whole lira). Prices in a foreign currency (USD in the placeholder
    data) are converted with TCMB's forex selling rate of the last business day before today,
    unless `exchange_rate_override` is given.

    Each option also carries its own first-year Annual Savings, Payback Period, lifetime savings
    and yearly cash flow, from the residential tariff (marginal Tariff Tiers, applied per
    month). Escalation rates are real, so all of these are in today's lira.

    The Quote also carries a `narrative`: the prose of its document (greeting, summary, a
    comparison of the two options, next steps) with every figure filled from the Quote. When a
    Narrative writer is configured it writes the text and the source is `llm`; with none, or
    when it fails, times out or breaks the rules, the fixed Turkish text is used and the
    source is `fallback`. The Narrative never makes the request fail.

    The Quote is stored with a Quote Number and a valid-until date and never changes afterwards.
    A failed request stores nothing.
    """
    quote = await service.create_quote(
        body.to_domain(), exchange_rate_override=body.exchange_rate_override_to_domain()
    )
    return quote_response(quote)


@router.get(
    "/quotes/{quote_id}",
    summary="Get a stored Quote",
    responses=problem_responses(QUOTE_NOT_FOUND, VALIDATION_ERROR),
)
async def get_quote(stored: Annotated[StoredQuote, Depends(get_stored_quote)]) -> QuoteResponse:
    """The Quote exactly as it was created."""
    return quote_response(stored)


@router.get(
    "/quotes/{quote_id}/document",
    summary="Get the printable Turkish quote document",
    response_class=HTMLResponse,
    responses=problem_responses(QUOTE_NOT_FOUND, VALIDATION_ERROR),
)
async def get_quote_document(
    stored: Annotated[StoredQuote, Depends(get_stored_quote)],
) -> HTMLResponse:
    """A stored Quote as an A4-printable Turkish HTML page, to send or print to PDF.

    Every figure is the Quote's own displayed value. The prose is the Quote's stored Narrative
    (or the fixed Turkish text) and reads the same every time.
    """
    return HTMLResponse(render_quote_document(stored))


@router.get(
    "/quotes",
    summary="List stored Quotes, newest first",
    responses=problem_responses(VALIDATION_ERROR),
)
async def list_quotes(
    repository: Annotated[QuoteRepository, Depends(get_quote_repository)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> QuoteListResponse:
    """One page of Quotes with the figures of their first System Option."""
    quotes = await repository.list_newest_first(page=page, page_size=page_size)
    return quote_list_response(quotes, page_number=page, page_size=page_size)
