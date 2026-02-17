import re
from dataclasses import dataclass

PATTERNS = {
    "mrn": re.compile(r"\bMRN[:\s-]*\d{6,10}\b", re.IGNORECASE),
    "dob": re.compile(r"\b(?:DOB[:\s-]*)?\d{2}[/-]\d{2}[/-]\d{4}\b", re.IGNORECASE),
    "phone": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
}


@dataclass
class RedactionResult:
    messages: list[dict[str, str]]
    redaction_count: int


class RedactionEngine:
    def redact_messages(self, messages: list[dict[str, str]]) -> RedactionResult:
        redacted_messages: list[dict[str, str]] = []
        hit_count = 0
        for message in messages:
            redacted_text, hits = self._redact_text(message["content"])
            hit_count += hits
            redacted_messages.append({"role": message["role"], "content": redacted_text})
        return RedactionResult(messages=redacted_messages, redaction_count=hit_count)

    def _redact_text(self, text: str) -> tuple[str, int]:
        redacted = text
        hit_count = 0
        for pattern_name, pattern in PATTERNS.items():
            replacement = f"[{pattern_name.upper()}_REDACTED]"
            redacted, substitutions = pattern.subn(replacement, redacted)
            hit_count += substitutions
        return redacted, hit_count
