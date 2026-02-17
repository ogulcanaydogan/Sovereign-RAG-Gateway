#!/usr/bin/env python3
import argparse
from pathlib import Path

DOCUMENTS = {
    "triage-note-01.txt": """
Patient presents with chest discomfort and mild shortness of breath after exertion.
No acute distress observed in triage. Recommended ECG and troponin panel.
Discharge guidance should include follow-up with cardiology within 48 hours.
""",
    "discharge-summary-02.txt": """
Discharge diagnosis: uncomplicated viral upper respiratory infection.
Patient tolerated oral intake and remained hemodynamically stable.
Home care plan includes hydration, acetaminophen as needed, and return precautions.
""",
    "policy-guardrail-03.md": """
# Clinical Assistant Guardrails
- Never reveal direct patient identifiers in model responses.
- Summarize findings and include evidence-backed rationale.
- Escalate to clinician review for high-risk recommendations.
""",
}


def generate_corpus(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name, text in DOCUMENTS.items():
        path = output_dir / file_name
        path.write_text(text.strip() + "\n", encoding="utf-8")
    return len(DOCUMENTS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic healthcare corpus files")
    parser.add_argument(
        "--output-dir",
        default="benchmarks/data/synthetic_corpus",
        help="Output directory for generated corpus",
    )
    args = parser.parse_args()

    count = generate_corpus(Path(args.output_dir))
    print(f"Generated {count} files in {args.output_dir}")


if __name__ == "__main__":
    main()
