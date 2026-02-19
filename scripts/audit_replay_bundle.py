#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import validate


@dataclass(frozen=True)
class ReplayResult:
    request_id: str
    bundle_path: Path
    sha256_path: Path
    markdown_path: Path
    chain_verified: bool
    signature_path: Path | None = None
    signature_verified: bool | None = None


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_payload(payload: object) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_json_schema(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid schema object: {path}")
    return parsed


def load_audit_events(audit_log_path: Path) -> list[dict[str, Any]]:
    if not audit_log_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for raw_line in audit_log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _event_payload_hash_for_verification(event: dict[str, Any]) -> str:
    copy = dict(event)
    copy.pop("payload_hash", None)
    return _hash_payload(copy)


def _is_event_hash_valid(event: dict[str, Any]) -> bool:
    expected = _event_payload_hash_for_verification(event)
    actual = str(event.get("payload_hash", ""))
    return expected == actual


def _verify_event_link(events: list[dict[str, Any]], index: int) -> bool:
    if index < 0 or index >= len(events):
        return False
    event = events[index]
    if not _is_event_hash_valid(event):
        return False
    expected_prev = "" if index == 0 else str(events[index - 1].get("payload_hash", ""))
    return str(event.get("prev_hash", "")) == expected_prev


def verify_hash_chain(events: list[dict[str, Any]]) -> bool:
    for index in range(len(events)):
        if not _verify_event_link(events, index):
            return False
    return True


def _find_last_event_for_request(
    events: list[dict[str, Any]], request_id: str
) -> tuple[int, dict[str, Any]] | None:
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if str(event.get("request_id", "")) == request_id:
            return index, event
    return None


def build_bundle(
    event: dict[str, Any],
    chain_verified: bool,
    audit_log_path: Path,
) -> dict[str, Any]:
    retrieval_citations_raw = event.get("retrieval_citations", [])
    retrieval_citations: list[dict[str, Any]]
    if isinstance(retrieval_citations_raw, list):
        retrieval_citations = [
            item for item in retrieval_citations_raw if isinstance(item, dict)
        ]
    else:
        retrieval_citations = []

    connector: str | None
    if retrieval_citations:
        connector = str(retrieval_citations[0].get("connector", "")) or None
    else:
        connector = None

    return {
        "bundle_version": "v1",
        "request_id": str(event.get("request_id", "")),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "policy": {
            "decision_id": str(event.get("policy_decision_id", "")),
            "policy_hash": str(event.get("policy_hash", "")),
            "policy_mode": str(event.get("policy_mode", "enforce")),
            "allow": bool(event.get("policy_allow", False)),
            "deny_reason": event.get("deny_reason"),
        },
        "redaction": {
            "count": int(event.get("redaction_count", 0)),
            "request_payload_hash": str(event.get("request_payload_hash", "")),
            "redacted_payload_hash": str(event.get("redacted_payload_hash", "")),
        },
        "retrieval": {
            "enabled": len(retrieval_citations) > 0,
            "connector": connector,
            "citations": retrieval_citations,
        },
        "provider": {
            "provider": str(event.get("provider", "")),
            "selected_model": str(event.get("selected_model", "")),
            "attempts": int(event.get("provider_attempts", 1)),
            "fallback_chain": event.get("fallback_chain", []),
            "provider_request_hash": event.get("provider_request_hash"),
            "provider_response_hash": event.get("provider_response_hash"),
        },
        "usage": {
            "tokens_in": int(event.get("tokens_in", 0)),
            "tokens_out": int(event.get("tokens_out", 0)),
            "cost_usd": float(event.get("cost_usd", 0.0)),
        },
        "integrity": {
            "prev_hash": str(event.get("prev_hash", "")),
            "payload_hash": str(event.get("payload_hash", "")),
            "chain_verified": chain_verified,
        },
        "source": {
            "audit_log_path": str(audit_log_path),
            "event_id": str(event.get("event_id", "")),
        },
    }


def _write_bundle_files(bundle: dict[str, Any], request_id: str, out_dir: Path) -> ReplayResult:
    target_dir = out_dir / request_id
    target_dir.mkdir(parents=True, exist_ok=True)

    bundle_path = target_dir / "bundle.json"
    sha256_path = target_dir / "bundle.sha256"
    markdown_path = target_dir / "bundle.md"

    bundle_text = json.dumps(bundle, indent=2, ensure_ascii=True)
    bundle_path.write_text(bundle_text + "\n", encoding="utf-8")

    bundle_hash = sha256(bundle_text.encode("utf-8")).hexdigest()
    sha256_path.write_text(bundle_hash + "\n", encoding="utf-8")

    markdown_path.write_text(
        "# Evidence Bundle\n\n"
        f"- Request ID: `{bundle['request_id']}`\n"
        f"- Policy decision: `{bundle['policy']['decision_id']}`\n"
        f"- Policy mode: `{bundle['policy']['policy_mode']}`\n"
        f"- Provider: `{bundle['provider']['provider']}`\n"
        f"- Model: `{bundle['provider']['selected_model']}`\n"
        f"- Tokens in/out: `{bundle['usage']['tokens_in']}/{bundle['usage']['tokens_out']}`\n"
        f"- Chain verified: `{bundle['integrity']['chain_verified']}`\n"
        f"- Bundle SHA-256: `{bundle_hash}`\n",
        encoding="utf-8",
    )

    return ReplayResult(
        request_id=request_id,
        bundle_path=bundle_path,
        sha256_path=sha256_path,
        markdown_path=markdown_path,
        chain_verified=bool(bundle["integrity"]["chain_verified"]),
    )


def _run_openssl(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


def sign_bundle(
    bundle_path: Path,
    private_key_path: Path,
    signature_path: Path,
) -> None:
    _run_openssl(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key_path),
            "-out",
            str(signature_path),
            str(bundle_path),
        ]
    )


def verify_bundle_signature(
    bundle_path: Path,
    public_key_path: Path,
    signature_path: Path,
) -> bool:
    try:
        result = _run_openssl(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(public_key_path),
                "-signature",
                str(signature_path),
                str(bundle_path),
            ]
        )
    except subprocess.CalledProcessError:
        return False
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "verified ok" in output


def generate_bundle(
    request_id: str,
    audit_log_path: Path,
    out_dir: Path,
    include_chain_verify: bool,
    sign_private_key: Path | None = None,
    verify_public_key: Path | None = None,
) -> ReplayResult:
    events = load_audit_events(audit_log_path)
    matched = _find_last_event_for_request(events, request_id)
    if matched is None:
        raise LookupError(f"request_id not found in audit log: {request_id}")

    index, event = matched
    if include_chain_verify:
        chain_verified = verify_hash_chain(events)
    else:
        chain_verified = _verify_event_link(events, index)

    bundle = build_bundle(
        event=event,
        chain_verified=chain_verified,
        audit_log_path=audit_log_path,
    )

    schema_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "contracts"
        / "v1"
        / "evidence-bundle.schema.json"
    )
    schema = _load_json_schema(schema_path)
    validate(instance=bundle, schema=schema)

    result = _write_bundle_files(bundle=bundle, request_id=request_id, out_dir=out_dir)
    if sign_private_key is None:
        return result

    signature_path = result.bundle_path.parent / "bundle.sig"
    sign_bundle(
        bundle_path=result.bundle_path,
        private_key_path=sign_private_key,
        signature_path=signature_path,
    )

    signature_verified: bool | None = None
    if verify_public_key is not None:
        signature_verified = verify_bundle_signature(
            bundle_path=result.bundle_path,
            public_key_path=verify_public_key,
            signature_path=signature_path,
        )

    return ReplayResult(
        request_id=result.request_id,
        bundle_path=result.bundle_path,
        sha256_path=result.sha256_path,
        markdown_path=result.markdown_path,
        chain_verified=result.chain_verified,
        signature_path=signature_path,
        signature_verified=signature_verified,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate audit replay evidence bundle")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--audit-log", default="artifacts/audit/events.jsonl")
    parser.add_argument("--out-dir", default="artifacts/evidence")
    parser.add_argument(
        "--include-chain-verify",
        action="store_true",
        help="Verify hash chain integrity for all audit events",
    )
    parser.add_argument(
        "--sign-private-key",
        default=None,
        help="OpenSSL private key path for detached signature output",
    )
    parser.add_argument(
        "--verify-public-key",
        default=None,
        help="Optional OpenSSL public key path to verify generated signature",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    try:
        result = generate_bundle(
            request_id=args.request_id,
            audit_log_path=Path(args.audit_log),
            out_dir=Path(args.out_dir),
            include_chain_verify=bool(args.include_chain_verify),
            sign_private_key=Path(args.sign_private_key) if args.sign_private_key else None,
            verify_public_key=Path(args.verify_public_key) if args.verify_public_key else None,
        )
    except LookupError as exc:
        print(str(exc))
        raise SystemExit(2) from exc

    print(f"bundle: {result.bundle_path}")
    print(f"sha256: {result.sha256_path}")
    print(f"markdown: {result.markdown_path}")
    if result.signature_path is not None:
        print(f"signature: {result.signature_path}")
    if result.signature_verified is not None:
        print(f"signature_verified: {result.signature_verified}")


if __name__ == "__main__":
    main()
