from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sunquote.api.app import create_app
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An app built by the factory with explicit settings and (fake) dependencies."""
    app = create_app(settings=Settings(), dependencies=AppDependencies())
    with TestClient(app) as test_client:
        yield test_client
