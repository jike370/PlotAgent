"""Validated environment configuration for the control-plane process."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProfileSettings(BaseModel):
    """One fixed server-side deployment exposed as a built-in model profile."""

    model_config = ConfigDict(extra="forbid", strict=True)

    deployment_id: str = Field(min_length=1, max_length=128)
    quota_unit: int = Field(default=1, ge=1, le=1_000_000)


class ControlPlaneSettings(BaseSettings):
    """Settings required to start the service safely.

    ``deployed_model_profiles`` is supplied as a JSON object in the environment, for example
    ``{"builtin-beta":{"deployment_id":"provider-deployment","quota_unit":1}}``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLOTAGENT_CONTROL_PLANE_",
        extra="ignore",
        case_sensitive=False,
    )

    database_path: Path
    secret_pepper: SecretStr = Field(min_length=32)
    deployed_model_profiles: dict[str, ModelProfileSettings] = Field(min_length=1)
    protocol_version: str = Field(default="1", min_length=1, max_length=16)
    provider_timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    idempotency_response_ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    sqlite_busy_timeout_ms: int = Field(default=10_000, ge=100, le=120_000)
    host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    port: int = Field(default=8000, ge=1, le=65_535)
    log_level: str = Field(default="INFO", pattern=r"^(CRITICAL|ERROR|WARNING|INFO|DEBUG)$")

    @model_validator(mode="after")
    def validate_profiles_and_retention(self) -> Self:
        if self.idempotency_response_ttl_seconds <= self.provider_timeout_seconds:
            raise ValueError("idempotency response TTL must exceed provider timeout")
        for profile_id in self.deployed_model_profiles:
            if not profile_id or len(profile_id) > 128:
                raise ValueError("model profile ids must contain 1 to 128 characters")
        if self.database_path.exists() and self.database_path.is_dir():
            raise ValueError("database path must name a file")
        return self


def load_settings() -> ControlPlaneSettings:
    """Load environment settings without echoing environment values on failure."""

    try:
        return ControlPlaneSettings()  # type: ignore[call-arg]
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        joined = ", ".join(fields) if fields else "unknown"
        raise RuntimeError(f"Invalid control-plane environment fields: {joined}") from None
