"""PII/PHI redaction engine with configurable pattern sets.

Scans both inbound messages (before provider call) and outbound responses
(after provider call) for sensitive data patterns.  Supports UK and US
formats for national identifiers, medical record numbers, dates of birth,
phone numbers, email addresses, and credit card numbers.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------


class PatternCategory(Enum):
    PHI = "phi"
    PII = "pii"
    FINANCIAL = "financial"


@dataclass(frozen=True)
class RedactionPattern:
    name: str
    regex: re.Pattern[str]
    replacement: str
    category: PatternCategory


# Core patterns — always active when redaction is enabled
_CORE_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern(
        name="mrn",
        regex=re.compile(r"\bMRN[:\s-]*\d{6,10}\b", re.IGNORECASE),
        replacement="[MRN_REDACTED]",
        category=PatternCategory.PHI,
    ),
    RedactionPattern(
        name="dob",
        regex=re.compile(
            r"\b(?:DOB[:\s-]*)?\d{2}[/-]\d{2}[/-]\d{4}\b", re.IGNORECASE
        ),
        replacement="[DOB_REDACTED]",
        category=PatternCategory.PHI,
    ),
    RedactionPattern(
        name="nhs_number",
        regex=re.compile(r"\b\d{3}[\s-]?\d{3}[\s-]?\d{4}\b"),
        replacement="[NHS_NUMBER_REDACTED]",
        category=PatternCategory.PHI,
    ),
    RedactionPattern(
        name="nino",
        regex=re.compile(
            r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
            re.IGNORECASE,
        ),
        replacement="[NINO_REDACTED]",
        category=PatternCategory.PII,
    ),
    RedactionPattern(
        name="ssn",
        regex=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        replacement="[SSN_REDACTED]",
        category=PatternCategory.PII,
    ),
    RedactionPattern(
        name="email",
        regex=re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
        replacement="[EMAIL_REDACTED]",
        category=PatternCategory.PII,
    ),
    RedactionPattern(
        name="phone_us",
        regex=re.compile(
            r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        ),
        replacement="[PHONE_REDACTED]",
        category=PatternCategory.PII,
    ),
    RedactionPattern(
        name="phone_uk",
        regex=re.compile(
            r"\b(?:\+44[-.\s]?|0)(?:\d[-.\s]?){9,10}\b"
        ),
        replacement="[PHONE_UK_REDACTED]",
        category=PatternCategory.PII,
    ),
    RedactionPattern(
        name="credit_card",
        regex=re.compile(r"\b(?:\d[-.\s]?){13,19}\b"),
        replacement="[CREDIT_CARD_REDACTED]",
        category=PatternCategory.FINANCIAL,
    ),
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RedactionResult:
    messages: list[dict[str, str]]
    redaction_count: int
    matched_categories: set[str] = field(default_factory=set)


@dataclass
class TextRedactionResult:
    text: str
    redaction_count: int
    matched_categories: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RedactionEngine:
    """Configurable regex-based PII/PHI redaction engine.

    Parameters
    ----------
    extra_patterns : tuple of ``RedactionPattern``, optional
        Additional patterns appended after core set.
    enabled_categories : set of ``PatternCategory``, optional
        Limit scanning to specific categories.  ``None`` means all.
    """

    def __init__(
        self,
        extra_patterns: tuple[RedactionPattern, ...] = (),
        enabled_categories: set[PatternCategory] | None = None,
    ) -> None:
        all_patterns = _CORE_PATTERNS + extra_patterns
        if enabled_categories is not None:
            all_patterns = tuple(
                p for p in all_patterns if p.category in enabled_categories
            )
        self._patterns = all_patterns

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)

    # -- Public API ---------------------------------------------------------

    def redact_messages(
        self, messages: list[dict[str, str]]
    ) -> RedactionResult:
        """Redact all message contents, returning new messages and hit count."""
        redacted_messages: list[dict[str, str]] = []
        total_hits = 0
        categories: set[str] = set()
        for message in messages:
            result = self.redact_text(message["content"])
            total_hits += result.redaction_count
            categories |= result.matched_categories
            redacted_messages.append(
                {"role": message["role"], "content": result.text}
            )
        return RedactionResult(
            messages=redacted_messages,
            redaction_count=total_hits,
            matched_categories=categories,
        )

    def redact_text(self, text: str) -> TextRedactionResult:
        """Redact a single text string."""
        redacted = text
        hit_count = 0
        categories: set[str] = set()
        for pattern in self._patterns:
            redacted, substitutions = pattern.regex.subn(
                pattern.replacement, redacted
            )
            if substitutions > 0:
                hit_count += substitutions
                categories.add(pattern.category.value)
        return TextRedactionResult(
            text=redacted,
            redaction_count=hit_count,
            matched_categories=categories,
        )
