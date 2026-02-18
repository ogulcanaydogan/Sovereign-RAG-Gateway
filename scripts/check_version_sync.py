#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def normalize_version(value: str) -> str:
    return value.strip().lower().lstrip("v").replace("-", "")


def extract_pyproject_version(pyproject_path: Path) -> str:
    match = re.search(
        r'^\s*version\s*=\s*"([^"]+)"\s*$',
        pyproject_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def extract_app_version(main_path: Path) -> str:
    match = re.search(
        r'FastAPI\([^)]*version\s*=\s*"([^"]+)"',
        main_path.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find FastAPI version in app/main.py")
    return match.group(1)


def extract_latest_changelog_version(changelog_path: Path) -> str:
    match = re.search(
        r"^##\s+v([0-9A-Za-z.\-]+)\s+-\s+",
        changelog_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        raise ValueError("Could not find a release heading in CHANGELOG.md")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify version sync across project files")
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--main", default="app/main.py")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    args = parser.parse_args()

    pyproject_version = extract_pyproject_version(Path(args.pyproject))
    app_version = extract_app_version(Path(args.main))
    changelog_version = extract_latest_changelog_version(Path(args.changelog))

    normalized = {
        "pyproject": normalize_version(pyproject_version),
        "app": normalize_version(app_version),
        "changelog": normalize_version(changelog_version),
    }

    if len(set(normalized.values())) != 1:
        raise SystemExit(
            "Version mismatch: "
            f"pyproject={pyproject_version}, app={app_version}, changelog={changelog_version}",
        )

    print(f"Version sync OK: {pyproject_version}")


if __name__ == "__main__":
    main()
