import pytest

from app.config.settings import Settings


def test_api_key_set_parses_values() -> None:
    settings = Settings(api_keys="a, b, c")
    assert settings.api_key_set == {"a", "b", "c"}


def test_rag_allowed_connector_set_parses_values() -> None:
    settings = Settings(rag_allowed_connectors="filesystem, postgres, s3")
    assert settings.rag_allowed_connector_set == {"filesystem", "postgres", "s3"}


def test_postgres_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SRG_RAG_POSTGRES_TABLE", raising=False)
    settings = Settings()
    assert settings.rag_postgres_table == "rag_chunks"
    assert settings.rag_embedding_dim == 16
    assert settings.rag_embedding_source == "hash"
    assert settings.rag_embedding_model == "text-embedding-3-small"


def test_confluence_spaces_parses_values() -> None:
    settings = Settings(rag_confluence_spaces="OPS, ENG,SEC")
    assert settings.rag_confluence_space_set == {"OPS", "ENG", "SEC"}


def test_jira_project_keys_parses_values() -> None:
    settings = Settings(rag_jira_project_keys="OPS, ENG,SEC")
    assert settings.rag_jira_project_key_set == {"OPS", "ENG", "SEC"}


def test_sharepoint_allowed_path_prefixes_parses_values() -> None:
    settings = Settings(
        rag_sharepoint_allowed_path_prefixes=" /drives/a/root:/Ops, /drives/a/root:/Sec "
    )
    assert settings.rag_sharepoint_allowed_path_prefix_set == {
        "/drives/a/root:/Ops",
        "/drives/a/root:/Sec",
    }


def test_budget_tenant_ceiling_map_parses_values() -> None:
    settings = Settings(budget_tenant_ceilings="tenant-a:1000, tenant-b:2500,invalid")
    assert settings.budget_tenant_ceiling_map == {
        "tenant-a": 1000,
        "tenant-b": 2500,
    }


def test_budget_tenant_ceiling_map_ignores_non_positive_values() -> None:
    settings = Settings(
        budget_tenant_ceilings="tenant-a:0, tenant-b:-10, tenant-c:500, :100, tenant-d:notanint"
    )
    assert settings.budget_tenant_ceiling_map == {"tenant-c": 500}


def test_budget_backend_normalized() -> None:
    settings = Settings(budget_backend=" Redis ")
    assert settings.budget_backend_normalized == "redis"


def test_tracing_otlp_header_map_parses_json_and_csv() -> None:
    json_settings = Settings(
        tracing_otlp_headers='{"Authorization":"Bearer x","x-tenant":"tenant-a"}'
    )
    assert json_settings.tracing_otlp_header_map["Authorization"] == "Bearer x"

    csv_settings = Settings(tracing_otlp_headers="Authorization:Bearer x,x-tenant:tenant-a")
    assert csv_settings.tracing_otlp_header_map == {
        "Authorization": "Bearer x",
        "x-tenant": "tenant-a",
    }


def test_webhook_dead_letter_backend_defaults() -> None:
    settings = Settings()
    assert settings.webhook_dead_letter_backend_normalized == "sqlite"
    assert settings.webhook_dead_letter_retention_days == 30
