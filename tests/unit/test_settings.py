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


def test_budget_tenant_ceiling_map_parses_values() -> None:
    settings = Settings(budget_tenant_ceilings="tenant-a:1000, tenant-b:2500,invalid")
    assert settings.budget_tenant_ceiling_map == {
        "tenant-a": 1000,
        "tenant-b": 2500,
    }
