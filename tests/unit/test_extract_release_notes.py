from scripts.extract_release_notes import extract_release_notes


def test_extract_release_notes_section() -> None:
    changelog = (
        "# Changelog\n\n"
        "## v0.2.0 - 2026-02-18\n"
        "- Added x\n\n"
        "## v0.1.0 - 2026-02-01\n"
        "- Added y\n"
    )
    notes = extract_release_notes(changelog, "v0.2.0")
    assert "## v0.2.0 - 2026-02-18" in notes
    assert "Added x" in notes
    assert "Added y" not in notes
