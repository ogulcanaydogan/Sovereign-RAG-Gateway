#!/usr/bin/env python3
import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


@dataclass(frozen=True)
class EvalSample:
    sample_id: str
    question: str
    connector: str


def load_samples(path: Path) -> list[EvalSample]:
    rows: list[EvalSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            parsed = json.loads(stripped)
            rows.append(
                EvalSample(
                    sample_id=str(parsed.get("id", f"sample-{len(rows)+1}")),
                    question=str(parsed["question"]),
                    connector=str(parsed.get("connector", "filesystem")),
                )
            )
    if not rows:
        raise ValueError(f"No samples loaded from {path}")
    return rows


def run_eval(samples: list[EvalSample], model: str) -> dict[str, Any]:
    clear_settings_cache()
    client = TestClient(create_app())

    base_headers = {
        "Authorization": "Bearer dev-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "eval-bot",
        "x-srg-classification": "phi",
    }

    observed = []
    citations_present = 0
    grounded_hits = 0

    for sample in samples:
        response = client.post(
            "/v1/chat/completions",
            headers=base_headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": sample.question}],
                "rag": {
                    "enabled": True,
                    "connector": sample.connector,
                    "top_k": 2,
                },
            },
        )

        status_code = response.status_code
        body = response.json()
        citations = []
        if status_code == 200:
            citations = body.get("choices", [{}])[0].get("message", {}).get("citations", [])
        has_citations = bool(citations)
        citations_present += 1 if has_citations else 0

        avg_score = 0.0
        if citations:
            avg_score = sum(float(item.get("score", 0.0)) for item in citations) / len(citations)
        if avg_score > 0:
            grounded_hits += 1

        observed.append(
            {
                "id": sample.sample_id,
                "status_code": status_code,
                "has_citations": has_citations,
                "citation_count": len(citations),
                "avg_citation_score": round(avg_score, 6),
            }
        )

    total = len(samples)
    citation_presence_rate = citations_present / total
    groundedness_score = grounded_hits / total

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "model": model,
        "samples_total": total,
        "citation_presence_rate": round(citation_presence_rate, 6),
        "groundedness_score": round(groundedness_score, 6),
        "results": observed,
    }


def write_markdown(path: Path, summary: dict[str, Any], threshold: float) -> None:
    metrics = [
        f"- Run at: `{summary['run_at']}`",
        f"- Samples: `{summary['samples_total']}`",
        f"- Citation presence rate: `{summary['citation_presence_rate']}`",
        f"- Groundedness score: `{summary['groundedness_score']}`",
        f"- Threshold: `{threshold}`",
    ]
    citation_presence_rate = float(summary["citation_presence_rate"])
    status = "PASS" if citation_presence_rate >= threshold else "FAIL"

    rows = ["| id | status | citations | avg_score |", "|---|---:|---:|---:|"]
    for item in cast(list[dict[str, Any]], summary["results"]):
        row = (
            f"| {item['id']} | {item['status_code']} | "
            f"{item['citation_count']} | {item['avg_citation_score']} |"
        )
        rows.append(row)

    body = "\n".join(
        [
            "# Citation Eval Report",
            "",
            f"Status: **{status}**",
            "",
            *metrics,
            "",
            *rows,
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run citation presence and groundedness eval")
    parser.add_argument("--dataset", default="benchmarks/data/citation_eval.jsonl")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument(
        "--output-json",
        default="artifacts/benchmarks/citation_eval.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="docs/benchmarks/reports/citations-latest.md",
    )
    args = parser.parse_args()

    os.environ.setdefault("SRG_API_KEYS", "dev-key")
    os.environ.setdefault("SRG_OPA_SIMULATE_TIMEOUT", "false")

    samples = load_samples(Path(args.dataset))
    summary = run_eval(samples=samples, model=args.model)

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    write_markdown(Path(args.output_markdown), summary, args.threshold)

    rate = float(summary["citation_presence_rate"])
    groundedness = float(summary["groundedness_score"])
    print(
        f"citation_presence_rate={rate:.3f} groundedness_score={groundedness:.3f}"
    )

    if rate < args.threshold:
        raise SystemExit(
            f"Citation presence rate {rate:.3f} is below threshold {args.threshold:.3f}"
        )


if __name__ == "__main__":
    main()
