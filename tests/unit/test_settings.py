from app.config.settings import Settings


def test_api_key_set_parses_values() -> None:
    settings = Settings(api_keys="a, b, c")
    assert settings.api_key_set == {"a", "b", "c"}


def test_rag_allowed_connector_set_parses_values() -> None:
    settings = Settings(rag_allowed_connectors="filesystem, postgres, s3")
    assert settings.rag_allowed_connector_set == {"filesystem", "postgres", "s3"}
