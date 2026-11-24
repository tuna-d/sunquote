import logging

from fastapi import FastAPI

from sunquote.api.dependencies import AppDependencies
from sunquote.api.health import router as health_router
from sunquote.config import Settings


def create_app(
    settings: Settings | None = None,
    dependencies: AppDependencies | None = None,
) -> FastAPI:
    """Build the application from its settings and collaborators.

    Nothing is read from the environment or constructed globally here beyond the defaults
    for omitted arguments, so tests pass their own settings and fakes.
    """
    settings = settings or Settings()
    dependencies = dependencies or AppDependencies()

    logging.getLogger("sunquote").setLevel(settings.log_level)

    app = FastAPI(title="sunquote", version="0.1.0")
    app.state.settings = settings
    app.state.dependencies = dependencies
    app.include_router(health_router)
    return app


app = create_app()
