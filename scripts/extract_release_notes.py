#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def extract_release_notes(changelog: str, tag: str) -> str:
    pattern = re.compile(r"^##\s+" + re.escape(tag) + r"\b.*$", re.MULTILINE)
    match = pattern.search(changelog)
    if not match:
        raise ValueError(f"No changelog section found for tag {tag}")

    start = match.start()
    next_match = re.search(r"^##\s+", changelog[match.end() :], re.MULTILINE)
    if next_match:
        end = match.end() + next_match.start()
    else:
        end = len(changelog)

    section = changelog[start:end].strip()
    return section + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract changelog section for a release tag")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--output", default="artifacts/release-notes.md")
    args = parser.parse_args()

    changelog_path = Path(args.changelog)
    if not changelog_path.exists():
        raise SystemExit(f"Changelog not found: {changelog_path}")

    changelog = changelog_path.read_text(encoding="utf-8")
    notes = extract_release_notes(changelog, args.tag)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(notes, encoding="utf-8")
    print(f"wrote release notes to {output_path}")


if __name__ == "__main__":
    main()
