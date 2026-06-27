"""Central configuration.

All settings are read from environment variables (and `.env.local`) via
pydantic-settings. NOTHING is hardcoded — secrets in particular must come from
the environment. See `.env.example` for documentation of every variable.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings.

    Pydantic-settings resolves values in this priority order:
    1. real environment variables
    2. values in `.env.local`
    3. the defaults declared here
    """

    model_config = SettingsConfigDict(
        env_file=(".env.local",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- app ----------------------------------------------------------------
    app_env: Literal["dev", "staging", "prod"] = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ---- structured store (Postgres) ----------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://engram:engram@localhost:5432/engram",
        description="SQLAlchemy URL for Postgres (psycopg v3 driver).",
    )

    # ---- vector store (Qdrant) ----------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "engram_incidents"

    # ---- embeddings (local, open-source) ------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # bge-small-en-v1.5 emits 384-dim vectors. Kept configurable; if you swap
    # the model the embedder reports the true dimension at runtime.
    embedding_dim: int = 384

    # ---- reasoning LLM (provider-swappable via litellm) ---------------------
    llm_provider: str = ""  # anthropic | openai | gemini
    llm_model: str = ""  # e.g. claude-3-5-sonnet-latest / gpt-4o / gemini-1.5-pro
    llm_api_key: str = ""  # the only paid dependency in the whole system

    # ---- tenant bootstrap (seed one tenant + key so things work immediately) -
    engram_bootstrap_api_key: str = ""
    engram_bootstrap_network_id: str = ""

    # ---- device capture (Netmiko SSH creds) ---------------------------------
    device_ssh_username: str = ""
    device_ssh_password: str = ""

    # ---- retrieval weights (documented; tune freely) ------------------------
    retrieval_w_vector: float = 0.6
    retrieval_w_structured: float = 0.4
    # staleness thresholds
    staleness_age_days: int = 180  # incidents older than this are flagged stale

    @property
    def llm_configured(self) -> bool:
        # A key still set to its .env.example placeholder counts as NOT configured,
        # so the user gets a clear "add your key" message instead of a provider
        # auth error — and we never make a doomed paid call.
        key = self.llm_api_key.strip()
        placeholder = (not key) or key.upper().startswith("REPLACE")
        return bool(self.llm_provider and self.llm_model and not placeholder)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor so the whole process shares one Settings instance."""
    return Settings()
