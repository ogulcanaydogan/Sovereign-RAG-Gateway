import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest
from openai import OpenAI


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory):
    root = Path(__file__).resolve().parents[2]
    audit_log = tmp_path_factory.mktemp("audit") / "events.jsonl"

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env["SRG_API_KEYS"] = "test-key"
    env["SRG_AUDIT_LOG_PATH"] = str(audit_log)
    env["SRG_OPA_SIMULATE_TIMEOUT"] = "false"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("Uvicorn server did not start")

    try:
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _extra_headers() -> dict[str, str]:
    return {
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "user-1",
        "x-srg-classification": "phi",
    }


def test_openai_sdk_chat_compat(live_server: str) -> None:
    client = OpenAI(api_key="test-key", base_url=f"{live_server}/v1")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
        extra_headers=_extra_headers(),
    )

    assert response.object == "chat.completion"
    assert response.choices[0].message.content


def test_openai_sdk_embeddings_compat(live_server: str) -> None:
    client = OpenAI(api_key="test-key", base_url=f"{live_server}/v1")
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=["hello", "world"],
        extra_headers=_extra_headers(),
    )

    assert response.object == "list"
    assert len(response.data) == 2
    assert len(response.data[0].embedding) == 16


def test_openai_sdk_models_list_compat(live_server: str) -> None:
    client = OpenAI(api_key="test-key", base_url=f"{live_server}/v1")
    models = client.models.list(extra_headers=_extra_headers())

    assert models.object == "list"
    assert any(item.id == "gpt-4o-mini" for item in models.data)
