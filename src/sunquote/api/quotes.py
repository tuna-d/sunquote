from typing import Annotated

from fastapi import APIRouter, Depends

from sunquote.api.dependencies import get_quote_service
from sunquote.api.errors import (
    NO_VIABLE_SYSTEM,
    UNSUPPORTED_SUBSCRIBER_GROUP,
    UPSTREAM_UNAVAILABLE,
    VALIDATION_ERROR,
    problem_responses,
)
from sunquote.api.schemas import QuoteRequestBody, QuoteResponse, quote_response
from sunquote.domain.service import QuoteService

router = APIRouter(tags=["quotes"])


@router.post(
    "/quotes",
    status_code=201,
    summary="Create a Quote",
    responses=problem_responses(
        VALIDATION_ERROR, UNSUPPORTED_SUBSCRIBER_GROUP, NO_VIABLE_SYSTEM, UPSTREAM_UNAVAILABLE
    ),
)
async def create_quote(
    body: QuoteRequestBody,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteResponse:
    """Size a system for the Customer's Site and return the Quote.

    The Quote holds one Consumption-Matched System Option with its first-year production.
    Nothing is priced or stored yet.
    """
    quote = await service.create_quote(body.to_domain())
    return quote_response(quote)
