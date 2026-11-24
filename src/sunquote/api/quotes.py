from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sunquote.api.dependencies import get_quote_repository, get_quote_service
from sunquote.api.errors import (
    LOCATION_NOT_SUPPORTED,
    NO_COMPATIBLE_INVERTER,
    NO_VIABLE_SYSTEM,
    QUOTE_NOT_FOUND,
    UNSUPPORTED_SUBSCRIBER_GROUP,
    UPSTREAM_UNAVAILABLE,
    VALIDATION_ERROR,
    problem_responses,
)
from sunquote.api.schemas import (
    QuoteListResponse,
    QuoteRequestBody,
    QuoteResponse,
    quote_list_response,
    quote_response,
)
from sunquote.domain.errors import QuoteNotFoundError
from sunquote.domain.ports import QuoteRepository
from sunquote.domain.service import QuoteService

router = APIRouter(tags=["quotes"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.post(
    "/quotes",
    status_code=201,
    summary="Create a Quote",
    responses=problem_responses(
        VALIDATION_ERROR,
        UNSUPPORTED_SUBSCRIBER_GROUP,
        NO_VIABLE_SYSTEM,
        NO_COMPATIBLE_INVERTER,
        LOCATION_NOT_SUPPORTED,
        UPSTREAM_UNAVAILABLE,
    ),
)
async def create_quote(
    body: QuoteRequestBody,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteResponse:
    """Size a system for the Customer's Site and return the Quote.

    The Quote holds one Consumption-Matched System Option with its first-year production, its
    inverter and its price in TRY (Installation Cost, Sale Price, VAT and total, whole lira).
    Equipment prices are converted with TCMB's USD forex selling rate of the last business day
    before today, unless `exchange_rate_override` is given. The Quote is stored, with a Quote
    Number and a valid-until date, and never changes afterwards. A failed request stores nothing.
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
async def get_quote(
    quote_id: UUID,
    repository: Annotated[QuoteRepository, Depends(get_quote_repository)],
) -> QuoteResponse:
    """The Quote exactly as it was created."""
    stored = await repository.get(quote_id)
    if stored is None:
        raise QuoteNotFoundError(quote_id)
    return quote_response(stored)


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
