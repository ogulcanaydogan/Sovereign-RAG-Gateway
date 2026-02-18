"""Prometheus metrics for the Sovereign RAG Gateway.

Exposes request, policy, provider, cost, and redaction metrics as a /metrics endpoint.
Uses a lightweight custom collector to avoid requiring prometheus_client as a dependency.
Metrics are stored as thread-safe counters and histograms in-process.
"""

import threading
from collections import defaultdict

from fastapi import APIRouter, Response

_lock = threading.Lock()

# Label key type: tuple of (key, value) pairs
LabelKey = tuple[tuple[str, str], ...]

# -- Counters --
_counters: dict[str, dict[LabelKey, float]] = defaultdict(
    lambda: defaultdict(float),
)

# -- Histograms (simple bucket approach) --
_histogram_sums: dict[str, dict[LabelKey, float]] = defaultdict(
    lambda: defaultdict(float),
)
_histogram_counts: dict[str, dict[LabelKey, int]] = defaultdict(
    lambda: defaultdict(int),
)

LATENCY_BUCKETS = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
_histogram_buckets: dict[str, dict[LabelKey, list[int]]] = defaultdict(
    lambda: defaultdict(lambda: [0] * len(LATENCY_BUCKETS)),
)


def inc_counter(name: str, labels: dict[str, str], value: float = 1.0) -> None:
    key: LabelKey = tuple(sorted(labels.items()))
    with _lock:
        _counters[name][key] += value


def observe_histogram(name: str, labels: dict[str, str], value: float) -> None:
    key: LabelKey = tuple(sorted(labels.items()))
    with _lock:
        _histogram_sums[name][key] += value
        _histogram_counts[name][key] += 1
        buckets = _histogram_buckets[name][key]
        for i, bound in enumerate(LATENCY_BUCKETS):
            if value <= bound:
                buckets[i] += 1


def _format_labels(label_pairs: LabelKey) -> str:
    if not label_pairs:
        return ""
    parts = [f'{k}="{v}"' for k, v in label_pairs]
    return "{" + ",".join(parts) + "}"


def render_metrics() -> str:
    lines: list[str] = []
    with _lock:
        for name, label_map in sorted(_counters.items()):
            lines.append(f"# TYPE {name} counter")
            for label_pairs, value in sorted(label_map.items()):
                lbl = _format_labels(label_pairs)
                lines.append(f"{name}{lbl} {value}")

        for name in sorted(_histogram_sums.keys()):
            lines.append(f"# TYPE {name} histogram")
            for label_pairs in sorted(_histogram_sums[name].keys()):
                base_lbl = _format_labels(label_pairs)

                buckets = _histogram_buckets[name][label_pairs]
                cumulative = 0
                for i, bound in enumerate(LATENCY_BUCKETS):
                    cumulative += buckets[i]
                    bucket_labels = dict(label_pairs)
                    bucket_labels["le"] = str(bound)
                    bl: LabelKey = tuple(sorted(bucket_labels.items()))
                    lines.append(f"{name}_bucket{_format_labels(bl)} {cumulative}")

                inf_labels = dict(label_pairs)
                inf_labels["le"] = "+Inf"
                il: LabelKey = tuple(sorted(inf_labels.items()))
                lines.append(
                    f"{name}_bucket{_format_labels(il)} "
                    f"{_histogram_counts[name][label_pairs]}"
                )
                lines.append(
                    f"{name}_sum{base_lbl} "
                    f"{_histogram_sums[name][label_pairs]}"
                )
                lines.append(
                    f"{name}_count{base_lbl} "
                    f"{_histogram_counts[name][label_pairs]}"
                )

    lines.append("")
    return "\n".join(lines)


# -- Convenience helpers for gateway metrics --


def record_request(
    endpoint: str,
    provider: str,
    model: str,
    policy_decision: str,
    status_code: int,
    latency_s: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    redaction_count: int = 0,
    provider_attempts: int = 1,
) -> None:
    """Record all metrics for a completed request."""
    base_labels = {
        "endpoint": endpoint,
        "provider": provider,
        "model": model,
    }

    inc_counter(
        "srg_requests_total",
        {**base_labels, "status": str(status_code)},
    )
    inc_counter(
        "srg_policy_decisions_total",
        {"endpoint": endpoint, "decision": policy_decision},
    )
    observe_histogram("srg_request_duration_seconds", base_labels, latency_s)

    if tokens_in > 0:
        inc_counter(
            "srg_tokens_total",
            {**base_labels, "direction": "input"},
            float(tokens_in),
        )
    if tokens_out > 0:
        inc_counter(
            "srg_tokens_total",
            {**base_labels, "direction": "output"},
            float(tokens_out),
        )
    if cost_usd > 0:
        inc_counter("srg_cost_usd_total", base_labels, cost_usd)
    if redaction_count > 0:
        inc_counter(
            "srg_redactions_total",
            {"endpoint": endpoint},
            float(redaction_count),
        )
    if provider_attempts > 1:
        inc_counter(
            "srg_provider_fallbacks_total",
            {"provider": provider},
            float(provider_attempts - 1),
        )


# -- FastAPI router --


metrics_router = APIRouter()


@metrics_router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(
        content=render_metrics(),
        media_type="text/plain; charset=utf-8",
    )
