from pathlib import Path

from scripts.check_version_sync import (
    extract_app_version,
    extract_chart_versions,
    extract_latest_changelog_version,
    extract_pyproject_version,
    extract_terraform_gateway_versions,
    normalize_version,
)


def test_normalize_version() -> None:
    assert normalize_version("v0.3.0-rc1") == "0.3.0rc1"


def test_extract_versions(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.3.0rc1"\n', encoding="utf-8")

    app_main = tmp_path / "main.py"
    app_main.write_text(
        'app = FastAPI(title="X", version="0.3.0-rc1")\n',
        encoding="utf-8",
    )

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## v0.3.0-rc1 - 2026-02-18\n", encoding="utf-8")

    chart = tmp_path / "Chart.yaml"
    chart.write_text(
        "version: 0.3.0-rc1\nappVersion: \"0.3.0-rc1\"\n",
        encoding="utf-8",
    )

    terraform_vars = tmp_path / "variables.tf"
    terraform_vars.write_text(
        'variable "gateway_chart_version" { default = "0.3.0-rc1" }\n'
        'variable "gateway_image_tag" { default = "v0.3.0-rc1" }\n',
        encoding="utf-8",
    )

    assert extract_pyproject_version(pyproject) == "0.3.0rc1"
    assert extract_app_version(app_main) == "0.3.0-rc1"
    assert extract_latest_changelog_version(changelog) == "0.3.0-rc1"
    assert extract_chart_versions(chart) == ("0.3.0-rc1", "0.3.0-rc1")
    assert extract_terraform_gateway_versions(terraform_vars) == (
        "0.3.0-rc1",
        "v0.3.0-rc1",
    )
