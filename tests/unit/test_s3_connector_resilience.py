"""Tests for S3 connector cache resilience — verifying last-known-good
cache preservation on transient failures and edge cases."""

import json
from io import BytesIO

from app.rag.connectors.s3 import S3Connector


class _FailAfterNCallsS3Client:
    """S3 client that succeeds for the first N calls then fails."""

    def __init__(self, payload: str, fail_after: int = 1):
        self._payload = payload
        self._call_count = 0
        self._fail_after = fail_after

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        _ = Bucket
        _ = Key
        self._call_count += 1
        if self._call_count > self._fail_after:
            raise RuntimeError("Transient S3 failure")
        return {"Body": BytesIO(self._payload.encode("utf-8"))}


class _MalformedJsonlS3Client:
    """S3 client that returns a mix of valid and invalid JSONL lines."""

    def __init__(self):
        lines = [
            json.dumps({"source_id": "good-1", "chunk_id": "g1", "text": "valid entry", "uri": "s3://b/1"}),
            "not valid json{{{",
            "",
            json.dumps({"source_id": "good-2", "chunk_id": "g2", "text": "another valid", "uri": "s3://b/2"}),
            "also broken",
        ]
        self._payload = "\n".join(lines)

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        _ = Bucket
        _ = Key
        return {"Body": BytesIO(self._payload.encode("utf-8"))}


class _EmptyResponseS3Client:
    """S3 client that returns empty body."""

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        _ = Bucket
        _ = Key
        return {"Body": BytesIO(b"")}


def test_s3_cache_preserved_on_transient_failure() -> None:
    """After a successful load, a transient S3 failure should preserve
    the last-known-good cache rather than replacing it with empty results."""
    payload = json.dumps({
        "source_id": "doc-1",
        "uri": "s3://b/doc-1.txt",
        "chunk_id": "doc-1#0",
        "text": "important medical data",
        "metadata": {},
    })
    s3_client = _FailAfterNCallsS3Client(payload, fail_after=1)
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=s3_client,
        cache_ttl_seconds=0,  # Force refresh every call
    )

    # First call succeeds and populates cache
    results = connector.search("medical", filters={}, k=5)
    assert len(results) == 1

    # Second call: S3 fails, but cached results should be preserved
    results = connector.search("medical", filters={}, k=5)
    assert len(results) == 1, "Cache should be preserved on transient failure"


def test_s3_malformed_jsonl_lines_skipped() -> None:
    """Malformed JSONL lines should be silently skipped, valid ones returned."""
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=_MalformedJsonlS3Client(),
    )
    results = connector.search("valid entry", filters={}, k=10)
    assert len(results) == 2
    source_ids = {r.source_id for r in results}
    assert source_ids == {"good-1", "good-2"}


def test_s3_empty_body_returns_empty_results() -> None:
    """An S3 object with empty body should not crash — just return no results."""
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=_EmptyResponseS3Client(),
    )
    results = connector.search("anything", filters={}, k=5)
    assert results == []


def test_s3_cache_ttl_zero_forces_refresh_every_call() -> None:
    """With cache_ttl=0, every call should re-read from S3."""
    payload = json.dumps({
        "source_id": "doc-1",
        "uri": "s3://b/1",
        "chunk_id": "doc-1#0",
        "text": "test text",
        "metadata": {},
    })
    s3_client = _FailAfterNCallsS3Client(payload, fail_after=999)
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=s3_client,
        cache_ttl_seconds=0,
    )

    connector.search("test", filters={}, k=1)
    connector.search("test", filters={}, k=1)
    connector.search("test", filters={}, k=1)
    assert s3_client._call_count == 3, "cache_ttl=0 should refresh on every call"
