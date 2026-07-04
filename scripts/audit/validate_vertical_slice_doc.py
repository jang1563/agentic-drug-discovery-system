#!/usr/bin/env python3
"""Validate the public SCD vertical-slice documentation."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "12_scd_vertical_slice.md"
README = ROOT / "README.md"
HF_CARD = ROOT / "huggingface" / "README.md"
RELEASE_MANIFEST = ROOT / "release_manifest.json"
HF_MANIFEST = ROOT / "huggingface" / "release_manifest.json"

REQUIRED_DOC_PHRASES = (
    "one disease",
    "N=8",
    "not a broad multi-disease atlas",
    "not a validated clinical predictor",
    "not an autonomous drug designer",
    "evaluator-only",
    "not published here",
    "retrospective",
    "prospective",
    "DEFER",
    "BOLTZ_ENDPOINT",
    "RDKit molprops",
    "cached data snapshots and evaluation case banks",
    "do not ship",
)

REQUIRED_POINTER_PHRASES = (
    "docs/12_scd_vertical_slice.md",
    "scripts/audit/validate_vertical_slice_doc.py",
)

FORBIDDEN_UNQUALIFIED_PHRASES = (
    "validated clinical candidate",
    "approval prediction",
    "autonomous drug designer",
    "full 8-stage trajectory atlas",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def normalize(text: str) -> str:
    return " ".join(text.replace("*", "").split()).lower()


def main() -> int:
    errors: list[str] = []
    doc = read(DOC)
    if not doc:
        errors.append("missing docs/12_scd_vertical_slice.md")

    normalized_doc = normalize(doc)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase.lower() not in normalized_doc:
            errors.append(f"docs/12_scd_vertical_slice.md missing phrase: {phrase}")

    lower_doc = normalized_doc
    for phrase in FORBIDDEN_UNQUALIFIED_PHRASES:
        idx = lower_doc.find(phrase.lower())
        if idx != -1:
            window = lower_doc[max(0, idx - 48) : idx + len(phrase) + 48]
            if not any(qualifier in window for qualifier in ("not", "never", "no ")):
                errors.append(f"unqualified overclaim phrase in vertical-slice doc: {phrase}")

    for path in (README, HF_CARD, RELEASE_MANIFEST, HF_MANIFEST):
        text = read(path)
        for phrase in REQUIRED_POINTER_PHRASES:
            if phrase not in text:
                errors.append(f"{path.relative_to(ROOT)} missing pointer: {phrase}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} vertical-slice documentation error(s)", file=sys.stderr)
        return 1

    print("PASS: SCD vertical-slice documentation validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
