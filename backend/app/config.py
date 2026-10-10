"""Application settings loaded exclusively from environment variables / backend/.env.

Secrets (SerpApi and LLM keys) are held only in this object. They are never
returned by the API, written to the database, or included in log messages.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
QUESTIONNAIRE_PATH = REPO_ROOT / "shared" / "questionnaire.json"
FIXTURES_DIR = BACKEND_DIR / "fixtures" / "serpapi"

LLMProvider = Literal["none", "openai", "anthropic", "groq", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    serpapi_api_key: str | None = Field(default=None, repr=False)
    demo_mode: Literal["auto", "true", "false"] = "auto"
    max_serpapi_requests_per_analysis: int = Field(default=12, ge=1, le=60)
    serpapi_cache_ttl_seconds: int = Field(default=86_400, ge=0)
    serpapi_timeout_seconds: float = Field(default=25.0, gt=0, le=120)
    serpapi_max_concurrency: int = Field(default=3, ge=1, le=8)
    serpapi_max_retries: int = Field(default=3, ge=0, le=6)
    serpapi_backoff_base_seconds: float = Field(default=0.75, ge=0)
    fixture_version: str = "v1"

    llm_provider: LLMProvider = "none"
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0
    openai_api_key: str | None = Field(default=None, repr=False)
    anthropic_api_key: str | None = Field(default=None, repr=False)
    groq_api_key: str | None = Field(default=None, repr=False)
    gemini_api_key: str | None = Field(default=None, repr=False)

    database_url: str = "sqlite:///./marketsim.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Run analyses inline (blocking) instead of on the background executor.
    # Used by tests; never needed in normal operation.
    inline_analysis: bool = False
    monte_carlo_iterations: int = Field(default=2000, ge=1000, le=50_000)
    monte_carlo_seed: int = 20251010

    @field_validator("demo_mode", mode="before")
    @classmethod
    def _normalise_demo_mode(cls, value: object) -> object:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "yes", "on"}:
                return "true"
            if lowered in {"0", "no", "off"}:
                return "false"
            return lowered or "auto"
        return value

    @field_validator(
        "serpapi_api_key", "openai_api_key", "anthropic_api_key", "groq_api_key",
        "gemini_api_key", "llm_model", mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # ------------------------------------------------------------------ helpers
    @property
    def has_serpapi_key(self) -> bool:
        return bool(self.serpapi_api_key)

    @property
    def default_data_mode(self) -> Literal["live", "demo"]:
        if self.demo_mode == "true":
            return "demo"
        if self.demo_mode == "false":
            return "live"
        return "live" if self.has_serpapi_key else "demo"

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite paths against backend/ so the CWD does not matter."""
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix) and not url.startswith("sqlite:////"):
            raw = url[len(prefix):]
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                return prefix + str((BACKEND_DIR / raw).resolve()).replace("\\", "/")
        return url

    @property
    def llm_key(self) -> str | None:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "groq": self.groq_api_key,
            "gemini": self.gemini_api_key,
        }.get(self.llm_provider)

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.llm_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
