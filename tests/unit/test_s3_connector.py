import json
from io import BytesIO

from app.rag.connectors.s3 import S3Connector


class FakeS3Client:
    def __init__(self, payload: str):
        self._payload = payload

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "demo-bucket"
        assert Key == "rag/index.jsonl"
        return {"Body": BytesIO(self._payload.encode("utf-8"))}


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
