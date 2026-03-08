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


def extract_chart_versions(chart_path: Path) -> tuple[str, str]:
    content = chart_path.read_text(encoding="utf-8")
    version_match = re.search(
        r"^version:\s*([0-9A-Za-z.\-]+)\s*$",
        content,
        flags=re.MULTILINE,
    )
    app_version_match = re.search(
        r'^appVersion:\s*"?([^"\n]+)"?\s*$',
        content,
        flags=re.MULTILINE,
    )
    if not version_match or not app_version_match:
        raise ValueError("Could not find version/appVersion in Chart.yaml")
    return version_match.group(1), app_version_match.group(1)


def extract_terraform_gateway_versions(terraform_vars_path: Path) -> tuple[str, str]:
    content = terraform_vars_path.read_text(encoding="utf-8")

    chart_match = re.search(
        r'variable\s+"gateway_chart_version"\s*{[^}]*?default\s*=\s*"([^"]+)"',
        content,
        flags=re.DOTALL,
    )
    image_match = re.search(
        r'variable\s+"gateway_image_tag"\s*{[^}]*?default\s*=\s*"([^"]+)"',
        content,
        flags=re.DOTALL,
    )
    if not chart_match or not image_match:
        raise ValueError("Could not find gateway chart/image defaults in variables.tf")
    return chart_match.group(1), image_match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify version sync across project files")
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--main", default="app/main.py")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--chart", default="charts/sovereign-rag-gateway/Chart.yaml")
    parser.add_argument("--terraform-vars", default="deploy/terraform/variables.tf")
    args = parser.parse_args()

    pyproject_version = extract_pyproject_version(Path(args.pyproject))
    app_version = extract_app_version(Path(args.main))
    changelog_version = extract_latest_changelog_version(Path(args.changelog))
    chart_version, chart_app_version = extract_chart_versions(Path(args.chart))
    tf_chart_version, tf_image_tag = extract_terraform_gateway_versions(
        Path(args.terraform_vars)
    )

    normalized = {
        "pyproject": normalize_version(pyproject_version),
        "app": normalize_version(app_version),
        "changelog": normalize_version(changelog_version),
        "chart": normalize_version(chart_version),
        "chart_app": normalize_version(chart_app_version),
        "terraform_chart": normalize_version(tf_chart_version),
        "terraform_image_tag": normalize_version(tf_image_tag),
    }

    if len(set(normalized.values())) != 1:
        raise SystemExit(
            "Version mismatch: "
            f"pyproject={pyproject_version}, app={app_version}, changelog={changelog_version}, "
            f"chart={chart_version}, chart_app={chart_app_version}, "
            f"terraform_chart={tf_chart_version}, terraform_image_tag={tf_image_tag}",
        )

    print(f"Version sync OK: {pyproject_version}")


if __name__ == "__main__":
    main()
