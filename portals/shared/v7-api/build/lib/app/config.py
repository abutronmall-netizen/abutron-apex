from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ABUTRON_",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "recovery_sandbox"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    database_url: str = "postgresql+asyncpg://abutron:change-me@localhost:5432/abutron"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "development-only-change-me-please-32-chars"
    jwt_issuer: str = "abutron-platform"
    access_token_minutes: int = 30

    # New customer signup uses verified email, not reconstructed October identities.
    resend_api_key: str = ""
    verification_from_email: str = ""
    public_base_url: str = ""

    service_token: str = "development-service-token"

    kronos_engine_url: str = "http://127.0.0.1:8090"
    kronos_engine_token: str = "development-engine-token"
    kronos_push_enabled: bool = False

    push_gateway_enabled: bool = False
    push_gateway_url: str = ""
    push_gateway_token: str = "development-push-token"

    billing_webhook_secret: str = "development-billing-webhook-secret-change-me"

    auto_create_schema: bool = False
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_secret", "billing_webhook_secret")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("Security secrets must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def reject_insecure_release_defaults(self) -> "Settings":
        """Refuse production/staging boot with recovery defaults or unsafe origins."""
        if self.env.lower() not in {"production", "prod", "staging"}:
            return self
        bad = []
        db_location = self.database_url.lower()
        if ("change-me@" in db_location or "localhost:5432/abutron" in db_location
                or "abutron_api_sandbox" in db_location
                or "historical" in db_location):
            bad.append("database_url")
        if self.env.lower() in {"production", "prod"}:
            # First public read-only release can only use the reviewed, clean
            # V7 store. Reject legacy, sandbox, staging, restore-probe and
            # attacker-selected database names before the app starts.
            try:
                selected_db = make_url(self.database_url).database
            except (ArgumentError, TypeError, ValueError):
                selected_db = None
            if selected_db != "abutron_v7_release_store":
                bad.append("database_url")
            if self.auto_create_schema:
                bad.append("auto_create_schema")
            if self.api_host not in {"127.0.0.1", "::1"}:
                bad.append("api_host")
            if self.kronos_push_enabled or self.push_gateway_enabled:
                bad.append("unreviewed_trading_or_push")
        # Stage-one public release intentionally accepts NEW customer identities;
        # it must not start with the disposable test/historical customer DB.
        if not self.public_base_url.startswith("https://"):
            bad.append("public_base_url")
        if ("@" not in self.verification_from_email
                or self.verification_from_email.startswith("@")):
            bad.append("verification_from_email")
        if len(self.resend_api_key) < 32 or self.resend_api_key.startswith("development-"):
            bad.append("resend_api_key")
        required = {
            "jwt_secret": self.jwt_secret,
            "service_token": self.service_token,
            "billing_webhook_secret": self.billing_webhook_secret,
        }
        if self.kronos_push_enabled:
            required["kronos_engine_token"] = self.kronos_engine_token
        if self.push_gateway_enabled:
            required["push_gateway_token"] = self.push_gateway_token
        for name, value in required.items():
            if len(value) < 32 or value.startswith("development-") or "change-me" in value:
                bad.append(name)
        if not self.cors_origins or any(
            origin == "*" or not origin.startswith("https://")
            for origin in self.cors_origins
        ):
            bad.append("cors_origins")
        if bad:
            raise ValueError("Unsafe release settings: " + ", ".join(sorted(set(bad))))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
