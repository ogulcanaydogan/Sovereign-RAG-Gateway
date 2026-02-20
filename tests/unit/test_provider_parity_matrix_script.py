import asyncio

from scripts.provider_parity_matrix import (
    _with_expectation_status,
    evaluate_provider,
    render_markdown,
)


def test_provider_parity_expected_statuses_pass() -> None:
    providers = ["http_openai", "azure_openai", "anthropic"]
    evaluated = [asyncio.run(evaluate_provider(provider)) for provider in providers]
    normalized = [_with_expectation_status(item) for item in evaluated]
    assert all(item.status == "pass" for item in normalized)


def test_provider_parity_markdown_render_contains_table() -> None:
    providers = ["http_openai", "azure_openai", "anthropic"]
    evaluated = [asyncio.run(evaluate_provider(provider)) for provider in providers]
    normalized = [_with_expectation_status(item) for item in evaluated]
    markdown = render_markdown(normalized)
    assert "| Provider | Status | Chat | Embeddings | Streaming |" in markdown
    assert "http_openai" in markdown
    assert "azure_openai" in markdown
    assert "anthropic" in markdown
