"""Tests for `gateway.config` — must preserve the env var contract already
relied on by docker-compose.yml / k8s/configmap.yaml / Dockerfile."""

from gateway.config import Settings, get_settings


def test_defaults_match_the_existing_deployment_contract() -> None:
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.log_file_path == ""
    assert settings.ppe_url == "http://ppe-detection:8000"
    assert settings.fall_url == "http://fall-detection:8000"
    assert settings.event_buffer == 200


def test_env_vars_are_matched_case_insensitively(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PPE_URL", "http://ppe-detection.local:9000")
    monkeypatch.setenv("EVENT_BUFFER", "500")
    settings = Settings(_env_file=None)
    assert settings.log_level == "DEBUG"
    assert settings.ppe_url == "http://ppe-detection.local:9000"
    assert settings.event_buffer == 500


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
