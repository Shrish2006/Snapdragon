"""Tests for `gateway.main` — the app factory must preserve `/health`,
the one endpoint every deployment healthcheck/probe already depends on."""

from fastapi.testclient import TestClient
from gateway.config import Settings
from gateway.main import create_app


def test_health_endpoint_matches_the_existing_contract() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_wires_settings_onto_app_state() -> None:
    settings = Settings(_env_file=None, log_level="DEBUG")
    app = create_app(settings)
    assert app.state.settings is settings
