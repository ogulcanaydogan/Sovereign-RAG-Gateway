from app.redaction.engine import RedactionEngine


def test_redaction_engine_masks_patterns() -> None:
    engine = RedactionEngine()
    result = engine.redact_messages(
        [{"role": "user", "content": "DOB 01/01/1990 phone 555-123-4567 MRN 123456"}]
    )

    assert result.redaction_count >= 2
    text = result.messages[0]["content"]
    assert "REDACTED" in text
