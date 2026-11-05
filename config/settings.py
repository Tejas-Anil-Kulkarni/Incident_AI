"""Environment-backed application settings for IncidentMind AI."""

from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Required configuration for integrations used by later phases.

    Construction intentionally fails with a Pydantic validation error when a
    required secret or endpoint is missing. The Phase 0 health endpoint does
    not instantiate this model, so local liveness checks remain dependency-free.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hindsight_api_key: SecretStr = Field(validation_alias="HINDSIGHT_API_KEY")
    hindsight_base_url: HttpUrl = Field(validation_alias="HINDSIGHT_BASE_URL")
    groq_api_key: SecretStr = Field(validation_alias="GROQ_API_KEY")
    model_name: str = Field(validation_alias="MODEL_NAME", min_length=1)
    chaos_dojo_enabled: bool = Field(default=False, validation_alias="CHAOS_DOJO_ENABLED")
    staleness_enabled: bool = Field(default=False, validation_alias="STALENESS_ENABLED")
    deploy_risk_enabled: bool = Field(default=False, validation_alias="DEPLOY_RISK_ENABLED")


class FeatureFlags(BaseSettings):
    """Phase 7 flags can be inspected without requiring integration secrets."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    chaos_dojo_enabled: bool = Field(default=False, validation_alias="CHAOS_DOJO_ENABLED")
    staleness_enabled: bool = Field(default=False, validation_alias="STALENESS_ENABLED")
    deploy_risk_enabled: bool = Field(default=False, validation_alias="DEPLOY_RISK_ENABLED")


@lru_cache
def get_settings() -> Settings:
    """Return process-cached validated settings for integration code."""

    return Settings()


@lru_cache
def get_feature_flags() -> FeatureFlags:
    """Load default-off experimental feature flags independently of secrets."""

    return FeatureFlags()

