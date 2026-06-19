from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SMTP_SUBMISSION_PORT = 587
IMAP_SSL_PORT = 993
IMAP_DEFAULT_HOST = "outlook.office365.com"


class Settings(BaseSettings):
    defectdojo_base_url: str = Field(..., alias="DEFECTDOJO_BASE_URL")
    defectdojo_api_token: str = Field(..., alias="DEFECTDOJO_API_TOKEN")
    defectdojo_findings_limit: int = Field(100, alias="DEFECTDOJO_FINDINGS_LIMIT")
    defectdojo_request_timeout_seconds: int = Field(
        30, alias="DEFECTDOJO_REQUEST_TIMEOUT_SECONDS"
    )

    project_email_mapping_json: str | None = Field(
        None, alias="PROJECT_EMAIL_MAPPING_JSON"
    )
    project_email_mapping_file: str | None = Field(
        None, alias="PROJECT_EMAIL_MAPPING_FILE"
    )

    database_url: str = Field(..., alias="DATABASE_URL")

    # This MVP sends alert emails via SMTP. IMAP SSL 993 is documented for
    # future mailbox-reading workflows and is not used by the current sender.
    smtp_host: str = Field(..., alias="SMTP_HOST")
    smtp_port: int = Field(SMTP_SUBMISSION_PORT, alias="SMTP_PORT")
    imap_ssl_port: int = Field(IMAP_SSL_PORT, alias="IMAP_SSL_PORT")
    imap_host: str = Field(IMAP_DEFAULT_HOST, alias="IMAP_HOST")
    imap_username: str | None = Field(None, alias="IMAP_USERNAME")
    imap_password: str | None = Field(None, alias="IMAP_PASSWORD")
    imap_timeout_seconds: int = Field(30, alias="IMAP_TIMEOUT_SECONDS")
    smtp_username: str | None = Field(None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(None, alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(..., alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(True, alias="SMTP_USE_TLS")
    smtp_timeout_seconds: int = Field(30, alias="SMTP_TIMEOUT_SECONDS")
    smtp_pool_size: int = Field(5, alias="SMTP_POOL_SIZE")

    scheduler_interval_seconds: int = Field(300, alias="SCHEDULER_INTERVAL_SECONDS")

    smtp_max_emails_per_minute: int = Field(30, alias="SMTP_MAX_EMAILS_PER_MINUTE")
    smtp_max_emails_per_hour: int = Field(500, alias="SMTP_MAX_EMAILS_PER_HOUR")

    smtp_max_attempts: int = Field(3, alias="SMTP_MAX_ATTEMPTS")
    smtp_retry_delay_seconds: int = Field(60, alias="SMTP_RETRY_DELAY_SECONDS")
    smtp_retry_backoff_multiplier: int = Field(
        2, alias="SMTP_RETRY_BACKOFF_MULTIPLIER"
    )

    manageengine_enabled: bool = Field(False, alias="MANAGEENGINE_ENABLED")
    manageengine_delivery_mode: str = Field(
        "email_fetch", alias="MANAGEENGINE_DELIVERY_MODE"
    )
    manageengine_dry_run: bool = Field(True, alias="MANAGEENGINE_DRY_RUN")
    manageengine_base_url: str | None = Field(None, alias="MANAGEENGINE_BASE_URL")
    manageengine_public_url: str | None = Field(None, alias="MANAGEENGINE_PUBLIC_URL")
    manageengine_auth_token: str | None = Field(None, alias="MANAGEENGINE_AUTH_TOKEN")
    manageengine_request_timeout_seconds: int = Field(
        30, alias="MANAGEENGINE_REQUEST_TIMEOUT_SECONDS"
    )
    manageengine_verify_ssl: bool = Field(True, alias="MANAGEENGINE_VERIFY_SSL")
    manageengine_requester_name: str | None = Field(
        "DevSecOps Automation", alias="MANAGEENGINE_REQUESTER_NAME"
    )
    manageengine_requester_email: str | None = Field(
        None, alias="MANAGEENGINE_REQUESTER_EMAIL"
    )
    manageengine_default_group: str | None = Field(
        None, alias="MANAGEENGINE_DEFAULT_GROUP"
    )
    manageengine_default_category: str | None = Field(
        "Security", alias="MANAGEENGINE_DEFAULT_CATEGORY"
    )
    manageengine_default_subcategory: str | None = Field(
        "Vulnerability", alias="MANAGEENGINE_DEFAULT_SUBCATEGORY"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("defectdojo_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("manageengine_base_url")
    @classmethod
    def strip_manageengine_trailing_slash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.rstrip("/")

    @field_validator("manageengine_public_url")
    @classmethod
    def strip_manageengine_public_trailing_slash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.rstrip("/")

    @field_validator("manageengine_delivery_mode")
    @classmethod
    def validate_manageengine_delivery_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed_modes = {"email_fetch", "api"}
        if normalized not in allowed_modes:
            raise ValueError(
                "MANAGEENGINE_DELIVERY_MODE must be one of: email_fetch, api"
            )
        return normalized

    @field_validator("project_email_mapping_json", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
