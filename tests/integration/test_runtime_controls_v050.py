import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_env: dict[str, str] | None = None,
) -> TestClient:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, value)
    clear_settings_cache()
    return TestClient(create_app())


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "user-1",
        "x-srg-classification": "phi",
    }


def test_budget_redis_backend_records_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    redis_mod = pytest.importorskip("redis")
    redis_url = os.getenv("SRG_TEST_REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis_mod.Redis.from_url(redis_url, decode_responses=True)

    try:
        redis_client.ping()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Redis is unavailable for integration test: {exc}")

    key_prefix = f"srg:test:budget:{uuid4().hex[:8]}"
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_BACKEND": "redis",
            "SRG_BUDGET_REDIS_URL": redis_url,
            "SRG_BUDGET_REDIS_PREFIX": key_prefix,
            "SRG_BUDGET_DEFAULT_CEILING": "1000",
        },
    )

    try:
        response = client.post(
            "/v1/chat/completions",
            headers=_auth_headers(),
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hello redis budget"}],
                "max_tokens": 8,
            },
        )
        assert response.status_code == 200
        summary = client.app.state.chat_service._budget_tracker.summary("tenant-a")
        assert int(summary["used"]) > 0
    finally:
        for key in redis_client.scan_iter(f"{key_prefix}:*"):
            redis_client.delete(key)


def test_otlp_exporter_posts_to_http_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _CollectorHandler(BaseHTTPRequestHandler):
        payloads: list[dict[str, object]] = []

        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            if body:
                import json as json_mod

                parsed = json_mod.loads(body)
                if isinstance(parsed, dict):
                    self.__class__.payloads.append(parsed)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            _ = format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), _CollectorHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/traces"

    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_TRACING_ENABLED": "true",
            "SRG_TRACING_OTLP_ENABLED": "true",
            "SRG_TRACING_OTLP_ENDPOINT": endpoint,
            "SRG_TRACING_OTLP_TIMEOUT_S": "1.5",
        },
    )

    try:
        response = client.post(
            "/v1/chat/completions",
            headers=_auth_headers(),
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "trace export check"}],
                "max_tokens": 8,
            },
        )
        assert response.status_code == 200
        assert _CollectorHandler.payloads
        first_payload = _CollectorHandler.payloads[0]
        resource_spans = first_payload.get("resourceSpans")
        assert isinstance(resource_spans, list)
        assert resource_spans
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
