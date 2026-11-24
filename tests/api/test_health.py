from fastapi.testclient import TestClient

from sunquote.api.app import create_app


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_serves_swagger_ui(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_factory_builds_app_without_arguments() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
