#!/usr/bin/env python3
import argparse
import json
from hashlib import sha256
from pathlib import Path


def chunk_text(text: str, chunk_size_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    step = max(chunk_size_words - overlap_words, 1)
    while start < len(words):
        end = start + chunk_size_words
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def ingest_directory(
    input_dir: Path,
    output_path: Path,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    supported_extensions = {".txt", ".md"}
    files = sorted(
        path for path in input_dir.rglob("*") if path.suffix.lower() in supported_extensions
    )

    emitted = 0
    with output_path.open("w", encoding="utf-8") as output_file:
        for path in files:
            text = path.read_text(encoding="utf-8")
            pieces = chunk_text(
                text,
                chunk_size_words=chunk_size_words,
                overlap_words=overlap_words,
            )
            if not pieces:
                continue

            source_id = sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
            uri = path.resolve().as_uri()

            for idx, piece in enumerate(pieces):
                payload = {
                    "source_id": source_id,
                    "uri": uri,
                    "chunk_id": f"{source_id}:{idx}",
                    "text": piece,
                    "metadata": {
                        "file_name": path.name,
                        "extension": path.suffix.lower().lstrip("."),
                    },
                }
                output_file.write(json.dumps(payload, ensure_ascii=True) + "\n")
                emitted += 1

    return emitted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest local docs into filesystem connector index"
    )
    parser.add_argument("--input-dir", required=True, help="Directory with .txt/.md source files")
    parser.add_argument(
        "--output",
        default="artifacts/rag/filesystem_index.jsonl",
        help="Output index JSONL path",
    )
    parser.add_argument("--chunk-size-words", type=int, default=120)
    parser.add_argument("--overlap-words", type=int, default=20)
    args = parser.parse_args()

    count = ingest_directory(
        input_dir=Path(args.input_dir),
        output_path=Path(args.output),
        chunk_size_words=args.chunk_size_words,
        overlap_words=args.overlap_words,
    )
    print(f"Wrote {count} chunks to {args.output}")


if __name__ == "__main__":
    main()
