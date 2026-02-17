from app.config.settings import Settings


def test_api_key_set_parses_values() -> None:
    settings = Settings(api_keys="a, b, c")
    assert settings.api_key_set == {"a", "b", "c"}
