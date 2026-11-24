"""One real call to Gemini. Run by hand with `uv run pytest -m integration`.

Skipped without `SUNQUOTE_GEMINI_API_KEY` (in the environment or `.env`). It uses the configured
model, which must be on the free tier, and sends only an anonymised context.
"""

import httpx
import pytest

from sunquote.adapters.gemini import GeminiNarrativeWriter
from sunquote.config import Settings
from tests.adapters.test_gemini import context

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_real_gemini_writes_a_draft_for_an_anonymised_context() -> None:
    settings = Settings()
    if settings.gemini_api_key is None:
        pytest.skip("SUNQUOTE_GEMINI_API_KEY is not set")

    async with httpx.AsyncClient() as client:
        writer = GeminiNarrativeWriter(
            client=client,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=30.0,
        )
        draft = await writer.write(context())

    assert writer.model_name == settings.gemini_model
    assert draft.greeting.strip()
    assert draft.summary.strip()
    assert draft.next_steps.strip()
    assert draft.options_comparison is not None  # the context has two options
