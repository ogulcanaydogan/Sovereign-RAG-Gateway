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
    rag_s3_bucket: str | None = None
    rag_s3_index_key: str = "rag/index.jsonl"
    rag_s3_region: str | None = None
    rag_s3_endpoint_url: str | None = None
    rag_confluence_base_url: str | None = None
    rag_confluence_email: str | None = None
    rag_confluence_api_token: str | None = None
    rag_confluence_spaces: str = ""
    rag_confluence_cache_ttl_seconds: float = 60.0
    rag_embedding_dim: int = 16
    rag_embedding_source: str = "hash"
    rag_embedding_endpoint: str | None = None
    rag_embedding_model: str = "text-embedding-3-small"
    rag_embedding_api_key: str | None = None
    rag_embedding_tenant_id: str | None = None
    rag_embedding_user_id: str | None = None
    rag_embedding_classification: str | None = None
    opa_timeout_ms: int = 150
    opa_mode: str = "enforce"
    opa_url: str | None = None
    opa_simulate_timeout: bool = False
    log_level: str = "INFO"
    redaction_enabled: bool = True
    provider_name: str = "stub"
    provider_config: str = ""
    provider_fallback_enabled: bool = True
    metrics_enabled: bool = True
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

    @property
    def rag_confluence_space_set(self) -> set[str]:
        return {item.strip() for item in self.rag_confluence_spaces.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
