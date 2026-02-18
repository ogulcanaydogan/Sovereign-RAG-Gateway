from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SRG_", case_sensitive=False)

    env: str = "dev"
    api_keys: str = Field(default="dev-key", description="Comma separated API keys")
    default_model: str = "gpt-4o-mini"
    model_catalog: str = "gpt-4o-mini,text-embedding-3-small"
    rag_enabled: bool = True
    rag_default_top_k: int = 3
    rag_allowed_connectors: str = "filesystem"
    rag_filesystem_index_path: Path = Path("artifacts/rag/filesystem_index.jsonl")
    rag_postgres_dsn: str | None = None
    rag_postgres_table: str = "rag_chunks"
    rag_embedding_dim: int = 16
    opa_timeout_ms: int = 150
    opa_mode: str = "enforce"
    opa_url: str | None = None
    opa_simulate_timeout: bool = False
    log_level: str = "INFO"
    redaction_enabled: bool = True
    provider_name: str = "stub"
    audit_log_path: Path = Path("artifacts/audit/events.jsonl")
    contracts_dir: Path = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "v1"

    @property
    def api_key_set(self) -> set[str]:
        return {item.strip() for item in self.api_keys.split(",") if item.strip()}

    @property
    def configured_models(self) -> list[str]:
        return [item.strip() for item in self.model_catalog.split(",") if item.strip()]

    @property
    def rag_allowed_connector_set(self) -> set[str]:
        return {item.strip() for item in self.rag_allowed_connectors.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
