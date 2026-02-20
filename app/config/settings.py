import json as json_mod
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
    rag_jira_base_url: str | None = None
    rag_jira_email: str | None = None
    rag_jira_api_token: str | None = None
    rag_jira_project_keys: str = ""
    rag_jira_cache_ttl_seconds: float = 60.0
    rag_sharepoint_base_url: str = "https://graph.microsoft.com/v1.0"
    rag_sharepoint_site_id: str | None = None
    rag_sharepoint_drive_id: str | None = None
    rag_sharepoint_auth_mode: str = "bearer_token"
    rag_sharepoint_bearer_token: str | None = None
    rag_sharepoint_managed_identity_endpoint: str = (
        "http://169.254.169.254/metadata/identity/oauth2/token"
    )
    rag_sharepoint_managed_identity_resource: str = "https://graph.microsoft.com/"
    rag_sharepoint_managed_identity_api_version: str = "2018-02-01"
    rag_sharepoint_managed_identity_client_id: str | None = None
    rag_sharepoint_managed_identity_timeout_s: float = 3.0
    rag_sharepoint_allowed_path_prefixes: str = ""
    rag_sharepoint_cache_ttl_seconds: float = 60.0
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

    # Budget enforcement
    budget_enabled: bool = False
    budget_default_ceiling: int = 100_000
    budget_window_seconds: int = 3600
    budget_tenant_ceilings: str = ""
    budget_backend: str = "memory"
    budget_redis_url: str | None = None
    budget_redis_prefix: str = "srg:budget"
    budget_redis_ttl_seconds: int = 7200

    # Webhook notifications
    webhook_enabled: bool = False
    webhook_endpoints: str = ""
    webhook_timeout_s: float = 5.0
    webhook_max_retries: int = 1
    webhook_backoff_base_s: float = 0.2
    webhook_backoff_max_s: float = 2.0
    webhook_dead_letter_backend: str = "sqlite"
    webhook_dead_letter_path: Path | None = Path("artifacts/audit/webhook_dead_letter.db")
    webhook_dead_letter_retention_days: int = 30

    # Telemetry / tracing
    tracing_enabled: bool = False
    tracing_max_traces: int = 1000
    tracing_otlp_enabled: bool = False
    tracing_otlp_endpoint: str | None = None
    tracing_otlp_timeout_s: float = 2.0
    tracing_otlp_headers: str = ""
    tracing_service_name: str = "sovereign-rag-gateway"

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

    @property
    def rag_jira_project_key_set(self) -> set[str]:
        return {item.strip() for item in self.rag_jira_project_keys.split(",") if item.strip()}

    @property
    def rag_sharepoint_allowed_path_prefix_set(self) -> set[str]:
        return {
            item.strip()
            for item in self.rag_sharepoint_allowed_path_prefixes.split(",")
            if item.strip()
        }

    @property
    def rag_sharepoint_auth_mode_normalized(self) -> str:
        return self.rag_sharepoint_auth_mode.strip().lower()

    @property
    def budget_tenant_ceiling_map(self) -> dict[str, int]:
        """Parse ``tenant:ceiling,tenant:ceiling`` into a dict."""
        result: dict[str, int] = {}
        for item in self.budget_tenant_ceilings.split(","):
            item = item.strip()
            if ":" not in item:
                continue
            tenant, ceiling_str = item.split(":", 1)
            try:
                normalized_tenant = tenant.strip()
                normalized_ceiling = int(ceiling_str.strip())
                if not normalized_tenant or normalized_ceiling <= 0:
                    continue
                result[normalized_tenant] = normalized_ceiling
            except ValueError:
                continue
        return result

    @property
    def budget_backend_normalized(self) -> str:
        return self.budget_backend.strip().lower()

    @property
    def tracing_otlp_header_map(self) -> dict[str, str]:
        raw = self.tracing_otlp_headers.strip()
        if not raw:
            return {}
        if raw.startswith("{"):
            try:
                parsed = json_mod.loads(raw)
            except json_mod.JSONDecodeError:
                return {}
            if not isinstance(parsed, dict):
                return {}
            return {
                str(key).strip(): str(value).strip()
                for key, value in parsed.items()
                if str(key).strip()
            }
        result: dict[str, str] = {}
        for item in raw.split(","):
            item = item.strip()
            if ":" not in item:
                continue
            key, value = item.split(":", 1)
            key = key.strip()
            if not key:
                continue
            result[key] = value.strip()
        return result

    @property
    def webhook_dead_letter_backend_normalized(self) -> str:
        return self.webhook_dead_letter_backend.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
