import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sunquote.api.dependencies import AppDependencies
from sunquote.api.errors import register_error_handlers
from sunquote.api.health import router as health_router
from sunquote.api.quotes import router as quotes_router
from sunquote.bootstrap import build_dependencies
from sunquote.config import Settings


def create_app(
    settings: Settings | None = None,
    dependencies: AppDependencies | None = None,
) -> FastAPI:
    """Build the application from its settings and collaborators.

    Tests pass their own settings and fakes. With no `dependencies`, the real adapters are
    built from the settings (data files are read; no network call is made).
    """
    settings = settings or Settings()
    dependencies = dependencies or build_dependencies(settings)

    logging.getLogger("sunquote").setLevel(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        for start in dependencies.startup:
            await start()
        yield
        for close in dependencies.closers:
            await close()

    app = FastAPI(title="sunquote", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.dependencies = dependencies
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(quotes_router)
    return app


app = create_app()
