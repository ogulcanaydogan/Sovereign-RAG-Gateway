#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.rag.connectors.postgres import PostgresPgvectorConnector


@dataclass(frozen=True)
class RankingSample:
    sample_id: str
    query: str
    expected_file_name: str
    filters: dict[str, str]


def load_samples(path: Path) -> list[RankingSample]:
    rows: list[RankingSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            filters = payload.get("filters", {})
            parsed_filters: dict[str, str] = {}
            if isinstance(filters, dict):
                parsed_filters = {str(key): str(value) for key, value in filters.items()}
            rows.append(
                RankingSample(
                    sample_id=str(payload.get("id", f"sample-{len(rows)+1}")),
                    query=str(payload["query"]),
                    expected_file_name=str(payload["expected_file_name"]),
                    filters=parsed_filters,
                )
            )
    if not rows:
        raise ValueError(f"No samples loaded from {path}")
    return rows


def evaluate(
    connector: PostgresPgvectorConnector, samples: list[RankingSample], top_k: int
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    hits = 0
    reciprocal_rank_sum = 0.0

    for sample in samples:
        chunks = connector.search(query=sample.query, filters=sample.filters, k=top_k)
        matched_rank = 0
        for idx, chunk in enumerate(chunks, start=1):
            if chunk.metadata.get("file_name") == sample.expected_file_name:
                matched_rank = idx
                break

        hit = matched_rank > 0
        if hit:
            hits += 1
            reciprocal_rank_sum += 1.0 / matched_rank

        results.append(
            {
                "id": sample.sample_id,
                "query": sample.query,
                "expected_file_name": sample.expected_file_name,
                "hit": hit,
                "matched_rank": matched_rank,
                "top_sources": [chunk.metadata.get("file_name", "") for chunk in chunks],
            }
        )

    total = len(samples)
    recall_at_k = hits / total
    mrr = reciprocal_rank_sum / total
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "samples_total": total,
        "top_k": top_k,
        "recall_at_k": round(recall_at_k, 6),
        "mrr": round(mrr, 6),
        "results": results,
    }


def write_markdown(path: Path, summary: dict[str, Any], threshold: float) -> None:
    recall = float(summary["recall_at_k"])
    status = "PASS" if recall >= threshold else "FAIL"
    rows = ["| id | hit | rank | expected | top_sources |", "|---|---:|---:|---|---|"]
    for result in summary["results"]:
        top_sources = ",".join(result["top_sources"])
        rows.append(
            "| {id} | {hit} | {rank} | {expected} | {sources} |".format(
                id=result["id"],
                hit="yes" if result["hit"] else "no",
                rank=result["matched_rank"] or "-",
                expected=result["expected_file_name"],
                sources=top_sources,
            )
        )

    body = "\n".join(
        [
            "# PGVector Ranking Eval Report",
            "",
            f"Status: **{status}**",
            "",
            f"- Run at: `{summary['run_at']}`",
            f"- Samples: `{summary['samples_total']}`",
            f"- Recall@{summary['top_k']}: `{summary['recall_at_k']}`",
            f"- MRR: `{summary['mrr']}`",
            f"- Threshold: `{threshold}`",
            "",
            *rows,
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate pgvector retrieval ranking quality")
    parser.add_argument("--dataset", default="benchmarks/data/pgvector_ranking_eval.jsonl")
    parser.add_argument("--postgres-dsn", required=True)
    parser.add_argument("--postgres-table", default="rag_chunks")
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument(
        "--output-json", default="artifacts/benchmarks/pgvector_ranking_eval.json"
    )
    parser.add_argument(
        "--output-markdown",
        default="docs/benchmarks/reports/pgvector-ranking-latest.md",
    )
    args = parser.parse_args()

    samples = load_samples(Path(args.dataset))
    connector = PostgresPgvectorConnector(
        dsn=args.postgres_dsn,
        table=args.postgres_table,
        embedding_dim=args.embedding_dim,
    )
    summary = evaluate(connector=connector, samples=samples, top_k=args.top_k)

    output_json_path = Path(args.output_json)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(Path(args.output_markdown), summary, args.threshold)

    recall = float(summary["recall_at_k"])
    print(f"recall_at_{args.top_k}={recall:.3f} mrr={float(summary['mrr']):.3f}")
    if recall < args.threshold:
        raise SystemExit(f"Recall@{args.top_k} {recall:.3f} below threshold {args.threshold:.3f}")


if __name__ == "__main__":
    main()
