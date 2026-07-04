#!/usr/bin/env python3
"""Validate the public launch decision packet and checklist."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "release_decision_packet.json"
CHECKLIST = ROOT / "docs" / "public_launch_checklist.md"

REQUIRED_CHECKS = {
    "python3 scripts/audit/github_release_file_audit.py",
    "python3 scripts/audit/validate_hf_release_package.py",
    "python3 scripts/audit/validate_public_launch_packet.py",
    "python3 scripts/audit/validate_vertical_slice_doc.py",
    "git diff --check",
    "python3 -m compileall adapters chains scripts/audit",
}

REQUIRED_EXCLUSIONS = {
    "raw source snapshots",
    "hidden or evaluator-only labels",
    "locked episode records",
    "generated reward or verifier outputs",
    "run logs",
    "credentials and key material",
    "machine-local paths",
    "model weights",
}

REQUIRED_CHECKLIST_PHRASES = (
    "GitHub remained private",
    "Hugging Face remained private",
    "explicit human approval",
    "release_decision_packet.json",
    "validate_public_launch_packet.py",
)


def load_packet(errors: list[str]) -> dict:
    try:
        return json.loads(PACKET.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"release_decision_packet.json is not valid JSON: {exc}")
        return {}


def main() -> int:
    errors: list[str] = []

    packet = load_packet(errors)
    if not CHECKLIST.exists():
        errors.append("missing docs/public_launch_checklist.md")
        checklist = ""
    else:
        checklist = CHECKLIST.read_text(encoding="utf-8", errors="ignore")

    if packet.get("artifact") != "agentic-drug-discovery-system":
        errors.append("release_decision_packet.json artifact is incorrect")
    if packet.get("decision_status") != "public_released_after_human_approval":
        errors.append("release_decision_packet.json must record public release after approval")
    if packet.get("human_readable_checklist") != "docs/public_launch_checklist.md":
        errors.append("release_decision_packet.json must point to docs/public_launch_checklist.md")

    surfaces = packet.get("surfaces") or {}
    github = surfaces.get("github") or {}
    hf = surfaces.get("hugging_face") or {}
    if github.get("current_visibility") != "public":
        errors.append("GitHub current_visibility must be public")
    if not str(github.get("url", "")).startswith("https://github.com/"):
        errors.append("GitHub URL must point to github.com")
    if hf.get("current_visibility") != "public":
        errors.append("Hugging Face current_visibility must be public")
    if hf.get("repo_type") != "dataset":
        errors.append("Hugging Face repo_type must be dataset")
    if not str(hf.get("url", "")).startswith("https://huggingface.co/datasets/"):
        errors.append("Hugging Face URL must point to a Dataset repo")

    launch = packet.get("launch_decision") or {}
    if launch.get("default") != "published_after_approval":
        errors.append("launch_decision.default must be published_after_approval")
    if launch.get("human_approval_required") is not True:
        errors.append("launch_decision.human_approval_required must be true")
    if launch.get("no_public_visibility_change_without_explicit_approval") is not True:
        errors.append("launch_decision must require explicit approval before public visibility")

    commands = {
        item.get("command")
        for item in packet.get("required_checks") or []
        if isinstance(item, dict) and item.get("blocking") is True
    }
    for command in sorted(REQUIRED_CHECKS - commands):
        errors.append(f"release_decision_packet.json missing blocking check: {command}")

    exclusions = set(((packet.get("release_scope") or {}).get("exclude")) or [])
    for exclusion in sorted(REQUIRED_EXCLUSIONS - exclusions):
        errors.append(f"release_decision_packet.json missing exclusion: {exclusion}")

    for phrase in REQUIRED_CHECKLIST_PHRASES:
        if phrase not in checklist:
            errors.append(f"docs/public_launch_checklist.md missing phrase: {phrase}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} public launch packet error(s)", file=sys.stderr)
        return 1

    print("PASS: public launch decision packet validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
