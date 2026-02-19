#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app
from scripts.audit_replay_bundle import generate_bundle


def generate_release_evidence(
    out_dir: Path,
    private_key: Path,
    public_key: Path,
) -> dict[str, str]:
    evidence_root = out_dir / "release-evidence"
    audit_log = evidence_root / "audit" / "events.jsonl"
    audit_log.parent.mkdir(parents=True, exist_ok=True)

    os.environ["SRG_API_KEYS"] = "release-evidence-key"
    os.environ["SRG_AUDIT_LOG_PATH"] = str(audit_log)
    os.environ["SRG_OPA_SIMULATE_TIMEOUT"] = "false"

    clear_settings_cache()
    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer release-evidence-key",
            "x-srg-tenant-id": "tenant-evidence",
            "x-srg-user-id": "release-bot",
            "x-srg-classification": "phi",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": "patient DOB 01/01/1990: summarize synthetic triage note",
                }
            ],
        },
    )
    if response.status_code != 200:
        raise RuntimeError(f"failed to generate synthetic request: {response.status_code}")

    rows = [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    request_id = str(rows[-1]["request_id"])

    replay_result = generate_bundle(
        request_id=request_id,
        audit_log_path=audit_log,
        out_dir=evidence_root,
        include_chain_verify=True,
        sign_private_key=private_key,
        verify_public_key=public_key,
    )

    metadata = {
        "request_id": request_id,
        "bundle_path": str(replay_result.bundle_path),
        "bundle_sha256_path": str(replay_result.sha256_path),
        "bundle_markdown_path": str(replay_result.markdown_path),
        "bundle_signature_path": str(replay_result.signature_path),
        "signature_verified": str(replay_result.signature_verified),
        "public_key_path": str(public_key),
    }
    metadata_path = evidence_root / "release-evidence-metadata.json"
    metadata_json = json.dumps(metadata, indent=2, ensure_ascii=True) + "\n"
    metadata_path.write_text(metadata_json, encoding="utf-8")

    return metadata


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate release evidence bundle artifacts")
    parser.add_argument("--out-dir", default="artifacts")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-key", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    metadata = generate_release_evidence(
        out_dir=Path(args.out_dir),
        private_key=Path(args.private_key),
        public_key=Path(args.public_key),
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
