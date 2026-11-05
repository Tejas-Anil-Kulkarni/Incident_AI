import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_settings_loads_required_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HINDSIGHT_BANK_ID", raising=False)
    monkeypatch.setenv("HINDSIGHT_API_KEY", "hindsight-test-key")
    monkeypatch.setenv("HINDSIGHT_BASE_URL", "https://example.hindsight.test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-oss-120b")

    settings = Settings()

    assert str(settings.hindsight_base_url) == "https://example.hindsight.test/"
    assert settings.model_name == "openai/gpt-oss-120b"
    assert settings.hindsight_api_key.get_secret_value() == "hindsight-test-key"
    assert settings.hindsight_bank_id == "incidentmind"


def test_settings_accepts_a_dedicated_hindsight_bank_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINDSIGHT_API_KEY", "hindsight-test-key")
    monkeypatch.setenv("HINDSIGHT_BASE_URL", "https://example.hindsight.test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-oss-120b")
    monkeypatch.setenv("HINDSIGHT_BANK_ID", "incidentmind-demo")
    assert Settings().hindsight_bank_id == "incidentmind-demo"


def test_settings_fails_clearly_when_required_values_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL", "GROQ_API_KEY", "MODEL_NAME"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert missing_fields == {"HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL", "GROQ_API_KEY", "MODEL_NAME"}

