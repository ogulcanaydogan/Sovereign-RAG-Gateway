import json
from io import BytesIO

from app.rag.connectors.s3 import S3Connector


class FakeS3Client:
    def __init__(self, payload: str):
        self._payload = payload
        self.get_count = 0

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "demo-bucket"
        assert Key == "rag/index.jsonl"
        self.get_count += 1
        return {"Body": BytesIO(self._payload.encode("utf-8"))}


class PrefixS3Client:
    def __init__(self):
        self._objects = {
            "rag/a.jsonl": json.dumps(
                {
                    "source_id": "doc-a",
                    "uri": "s3://demo-bucket/docs/doc-a.txt",
                    "chunk_id": "doc-a#0",
                    "text": "alpha beta",
                    "metadata": {"tenant": "tenant-a"},
                }
            ),
            "rag/b.jsonl": json.dumps(
                {
                    "source_id": "doc-b",
                    "uri": "s3://demo-bucket/docs/doc-b.txt",
                    "chunk_id": "doc-b#0",
                    "text": "beta gamma",
                    "metadata": {"tenant": "tenant-a"},
                }
            ),
        }

    def list_objects_v2(self, Bucket: str, Prefix: str, ContinuationToken=None):
        assert Bucket == "demo-bucket"
        assert Prefix == "rag/"
        _ = ContinuationToken
        return {
            "IsTruncated": False,
            "Contents": [
                {"Key": "rag/a.jsonl"},
                {"Key": "rag/b.jsonl"},
                {"Key": "rag/README.md"},
            ],
        }

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "demo-bucket"
        payload = self._objects[Key]
        return {"Body": BytesIO(payload.encode("utf-8"))}


class ErrorS3Client:
    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        _ = Bucket
        _ = Key
        raise RuntimeError("not found")


def test_s3_connector_search_and_fetch() -> None:
    payload = "\n".join(
        [
            json.dumps(
                {
                    "source_id": "doc-1",
                    "uri": "s3://demo-bucket/docs/doc-1.txt",
                    "chunk_id": "doc-1#0",
                    "text": "patient has elevated glucose",
                    "metadata": {"tenant": "tenant-a"},
                }
            ),
            json.dumps(
                {
                    "source_id": "doc-1",
                    "uri": "s3://demo-bucket/docs/doc-1.txt",
                    "chunk_id": "doc-1#1",
                    "text": "follow-up in two weeks",
                    "metadata": {"tenant": "tenant-a"},
                }
            ),
        ]
    )
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=FakeS3Client(payload),
    )

    chunks = connector.search("glucose follow-up", filters={"tenant": "tenant-a"}, k=2)
    assert len(chunks) == 2
    assert chunks[0].connector == "s3"
    assert chunks[0].score >= chunks[1].score

    doc = connector.fetch("doc-1")
    assert doc is not None
    assert "elevated glucose" in doc.text
    assert "follow-up in two weeks" in doc.text


def test_s3_connector_missing_index_returns_empty_results() -> None:
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=ErrorS3Client(),
    )
    assert connector.search("hello", filters={}, k=3) == []
    assert connector.fetch("doc-1") is None


def test_s3_connector_cache_reuses_loaded_index() -> None:
    payload = json.dumps(
        {
            "source_id": "doc-1",
            "uri": "s3://demo-bucket/docs/doc-1.txt",
            "chunk_id": "doc-1#0",
            "text": "patient has elevated glucose",
            "metadata": {"tenant": "tenant-a"},
        }
    )
    s3_client = FakeS3Client(payload)
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/index.jsonl",
        s3_client=s3_client,
        cache_ttl_seconds=60,
    )

    assert connector.search("glucose", filters={}, k=1)
    assert connector.search("patient", filters={}, k=1)
    assert s3_client.get_count == 1


def test_s3_connector_prefix_index_loads_multiple_objects() -> None:
    connector = S3Connector(
        bucket="demo-bucket",
        index_key="rag/",
        s3_client=PrefixS3Client(),
    )
    results = connector.search("beta", filters={"tenant": "tenant-a"}, k=5)
    assert len(results) == 2
    assert {item.source_id for item in results} == {"doc-a", "doc-b"}
