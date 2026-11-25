"""Application settings loaded from environment and .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Centralized configuration for Insight Agent."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. DashScope (Alibaba Cloud Bailian) OpenAI-compatible LLM & Embedding
    llm_provider: str = Field(default="dashscope")
    dashscope_api_key: str = Field(default="")
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    llm_model: str = Field(default="qwen4-max")
    llm_reasoning_effort_fast: str = Field(default="low")
    llm_reasoning_effort_deep: str = Field(default="high")
    embedding_model: str = Field(default="qwen3.7-text-embedding-flash")
    embedding_dim: int = Field(default=1024)
    no_proxy: str = Field(default="localhost,127.0.0.1,dashscope.aliyuncs.com")

    # 2. Optional OpenAI-compatible endpoint for cross-model eval
    openai_base_url: str = Field(default="")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="")

    # 3. PostgreSQL (3-tier privilege separation: admin DDL, service app state, readonly analyst)
    pg_host: str = Field(default="127.0.0.1")
    pg_port: int = Field(default=5432)
    pg_db: str = Field(default="olist")
    pg_admin_user: str = Field(default="olist_admin")
    pg_admin_password: str = Field(default="replace_with_local_admin_pwd")
    pg_service_user: str = Field(default="agent_service")
    pg_service_password: str = Field(default="insight_local_svc_2026")
    pg_readonly_user: str = Field(default="readonly_analyst")
    pg_readonly_password: str = Field(default="replace_with_local_ro_pwd")

    # 4. Runtime guards & budgets
    max_agent_steps: int = Field(default=12)
    max_node_retries: int = Field(default=3)
    max_tokens_per_run: int = Field(default=60000)
    sandbox_timeout_seconds: int = Field(default=30)

    # 5. Observability
    trace_dir: Path = Field(default=PROJECT_ROOT / "traces")
    otel_exporter_otlp_endpoint: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    @property
    def pg_admin_dsn(self) -> str:
        pwd = quote_plus(self.pg_admin_password)
        return f"postgresql://{self.pg_admin_user}:{pwd}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    @property
    def pg_service_dsn(self) -> str:
        pwd = quote_plus(self.pg_service_password)
        return (
            f"postgresql://{self.pg_service_user}:{pwd}@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def pg_readonly_dsn(self) -> str:
        pwd = quote_plus(self.pg_readonly_password)
        return (
            f"postgresql://{self.pg_readonly_user}:{pwd}@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def glossary_path(self) -> Path:
        return PROJECT_ROOT / "docs" / "03_metrics_glossary.yaml"

    @property
    def few_shots_path(self) -> Path:
        return PROJECT_ROOT / "eval" / "few_shots" / "verified_sqls.yaml"

    @property
    def data_raw_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "raw"

    @property
    def data_extracted_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "extracted"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
