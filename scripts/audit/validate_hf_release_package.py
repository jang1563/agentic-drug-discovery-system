#!/usr/bin/env python3
"""Validate the local Hugging Face Dataset-card package before upload."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "huggingface" / "README.md"
MANIFEST = ROOT / "huggingface" / "release_manifest.json"

REQUIRED_CARD_FIELDS = {
    "pretty_name": "Agentic Drug Discovery System",
    "license": "apache-2.0",
}

REQUIRED_MANIFEST_VALUES = {
    "target_surface": "huggingface_dataset",
    "repo_type": "dataset",
    "status": "local_package_prepared_not_uploaded",
    "initial_visibility": "private",
}

FORBIDDEN_CARD_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"/home/fs\d+/"),
    re.compile(r"/expanse/lustre/"),
    re.compile(r"\b(Cayuga|Expanse)\b"),
    re.compile(r"\bSlurm job\s+\d{6,}\b", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY"),
)


def parse_simple_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("dataset card must start with YAML front matter")
    try:
        raw = text.split("---\n", 2)[1]
    except IndexError as exc:
        raise ValueError("dataset card front matter is not closed") from exc
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or line.startswith("-"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def main() -> int:
    errors: list[str] = []
    if not CARD.exists():
        errors.append("missing huggingface/README.md")
        card_text = ""
    else:
        card_text = CARD.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_CARD_PATTERNS:
            if pattern.search(card_text):
                errors.append(f"huggingface/README.md forbidden pattern matched: {pattern.pattern}")
        try:
            fields = parse_simple_frontmatter(card_text)
            for key, expected in REQUIRED_CARD_FIELDS.items():
                if fields.get(key) != expected:
                    errors.append(f"huggingface/README.md front matter {key!r} must be {expected!r}")
        except ValueError as exc:
            errors.append(str(exc))

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        manifest = {}
        errors.append(f"huggingface/release_manifest.json is not valid JSON: {exc}")

    for key, expected in REQUIRED_MANIFEST_VALUES.items():
        if manifest.get(key) != expected:
            errors.append(f"huggingface/release_manifest.json {key!r} must be {expected!r}")

    if manifest.get("repo_type") == "model":
        errors.append("Hugging Face repo_type must not be model for this artifact")
    if manifest.get("status") != "local_package_prepared_not_uploaded":
        errors.append("Hugging Face package must remain not-uploaded until explicit approval")

    include = set(manifest.get("include") or [])
    for required in ("huggingface/README.md", "docs/release_boundary.md", "release_manifest.json"):
        if required not in include:
            errors.append(f"huggingface/release_manifest.json missing include: {required}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} Hugging Face package error(s)", file=sys.stderr)
        return 1

    print("PASS: Hugging Face Dataset-card package validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
