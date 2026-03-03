import pytest

from scripts.check_required_workflows import (
    extract_workflow_names,
    find_missing_required_workflows,
    parse_required_workflows,
)


def test_parse_required_workflows_normalizes_values() -> None:
    values = parse_required_workflows(" ci, deploy-smoke ,release-verify ")
    assert values == ["ci", "deploy-smoke", "release-verify"]


def test_parse_required_workflows_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_required_workflows(" , , ")


def test_extract_workflow_names_reads_list() -> None:
    payload = {
        "workflows": [
            {"name": "ci"},
            {"name": "deploy-smoke"},
            {"name": "release-verify"},
        ]
    }
    names = extract_workflow_names(payload)
    assert names == {"ci", "deploy-smoke", "release-verify"}


def test_extract_workflow_names_rejects_invalid_payload() -> None:
    with pytest.raises(RuntimeError, match="invalid workflows payload"):
        extract_workflow_names([])


def test_find_missing_required_workflows_returns_sorted_missing() -> None:
    required = ["ci", "deploy-smoke", "terraform-validate"]
    available = {"ci", "deploy-smoke"}
    missing = find_missing_required_workflows(required, available)
    assert missing == ["terraform-validate"]

