#!/usr/bin/env python3
"""Validate public scientific claim boundaries and aggregate evidence anchors."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "12_scd_vertical_slice.md"
TARGET_DOC = ROOT / "docs" / "13_target_id_governance_node.md"
EVIDENCE = ROOT / "docs" / "public_evidence_summary.json"
README = ROOT / "README.md"
HF_CARD = ROOT / "huggingface" / "README.md"
RELEASE_MANIFEST = ROOT / "release_manifest.json"
HF_MANIFEST = ROOT / "huggingface" / "release_manifest.json"
TRUST_REPORT = ROOT / "docs" / "release_trust_report.md"
DECISION_PACKET = ROOT / "release_decision_packet.json"
CHAIN = ROOT / "chains" / "discovery_flow.py"
BOLTZ = ROOT / "adapters" / "boltz_adapter.py"
EMA = ROOT / "adapters" / "ema_epar_adapter.py"
OPEN_TARGETS = ROOT / "adapters" / "opentargets_adapter.py"

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
    "stale no-readout assumption",
    "invalidated as evidence",
    "source-refreshed",
    "not a current recommendation",
    "BOLTZ_ENDPOINT",
    "RDKit molprops",
    "cached data snapshots and evaluation case banks",
    "do not ship",
    "80.5%",
    "32.9%",
    "n=298",
    "label-uncertainty proxy",
    "δ=0.10",
    "80/80",
    "same fixed eight assets",
    "not independent",
    "post-reconciliation",
    "docs/public_evidence_summary.json",
)

REQUIRED_TARGET_DOC_PHRASES = (
    "32 pairs",
    "23 diseases",
    "0.842",
    "0.713",
    "0.781",
    "0.939",
    "no RCPS certificate",
    "α=0.30",
    "δ=0.10",
    "terminal gold",
)

REQUIRED_POINTER_PHRASES = (
    "docs/12_scd_vertical_slice.md",
    "docs/13_target_id_governance_node.md",
    "docs/public_evidence_summary.json",
    "scripts/audit/validate_vertical_slice_doc.py",
    "benchmark/",
)

FORBIDDEN_STALE_PHRASES = (
    "96.8%",
    "44.7%",
    "3–5/8",
    "roughly one-third the cost",
    "Construct validity holds.",
    "scores near-perfectly",
    "statistically indistinguishable",
    "DEFER at all four stages",
    "clinically validated engagement",
    "pIC50~",
    "asset has no EU centralised filing",
    "weak/absent human genetic-disease evidence",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def normalize(text: str) -> str:
    return " ".join(text.replace("*", "").split()).lower()


def nested(data: dict, *keys: str):
    value = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def main() -> int:
    errors: list[str] = []
    doc = read(DOC)
    target_doc = read(TARGET_DOC)
    if not doc:
        errors.append("missing docs/12_scd_vertical_slice.md")
    if not target_doc:
        errors.append("missing docs/13_target_id_governance_node.md")

    normalized_doc = normalize(doc)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase.lower() not in normalized_doc:
            errors.append(f"docs/12_scd_vertical_slice.md missing phrase: {phrase}")
    normalized_target = normalize(target_doc)
    for phrase in REQUIRED_TARGET_DOC_PHRASES:
        if phrase.lower() not in normalized_target:
            errors.append(f"docs/13_target_id_governance_node.md missing phrase: {phrase}")

    public_claim_texts = {
        "README.md": read(README),
        "docs/12_scd_vertical_slice.md": doc,
        "docs/13_target_id_governance_node.md": target_doc,
        "huggingface/README.md": read(HF_CARD),
        "adapters/boltz_adapter.py": read(BOLTZ),
        "adapters/ema_epar_adapter.py": read(EMA),
        "adapters/opentargets_adapter.py": read(OPEN_TARGETS),
    }
    for label, text in public_claim_texts.items():
        for phrase in FORBIDDEN_STALE_PHRASES:
            if phrase.lower() in text.lower():
                errors.append(f"{label} contains stale or unsupported phrase: {phrase}")

    chain_text = normalize(read(CHAIN))
    for phrase in (
        "HALTED, WITHDRAWN",
        "invalid/implausible/corrupt, or the drug is still approved",
        "withdrawn or revoked is stop, not flag",
    ):
        if phrase.lower() not in chain_text:
            errors.append(f"chains/discovery_flow.py missing stop/flag disambiguation: {phrase}")

    try:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence = {}
        errors.append(f"docs/public_evidence_summary.json is not valid JSON: {exc}")

    expected_values = {
        ("scd_terminal_slice", "unique_assets"): 8,
        ("fixed_slice_prompt_regression", "repeats_per_policy"): 10,
        ("fixed_slice_prompt_regression", "curated_terminal_correct"): 80,
        ("fixed_slice_prompt_regression", "autonomous_terminal_correct"): 80,
        ("fixed_slice_prompt_regression", "independent_samples"): False,
        ("track_a_packet_masking_diagnostic", "n_packets"): 298,
        ("track_a_packet_masking_diagnostic", "no_reasoning_raw_accuracy"): 0.805,
        ("track_a_packet_masking_diagnostic", "no_reasoning_masked_accuracy"): 0.329,
        ("track_a_label_uncertainty_proxy", "risk_signal_auroc"): 0.8,
        ("target_id_masked_node", "unique_pairs"): 32,
        ("target_id_masked_node", "diseases"): 23,
        ("target_id_masked_node", "masked_sonnet_pooled_selective_accuracy"): 0.842,
        ("target_id_masked_node", "drug_field_visible_diagnostic_overall_accuracy"): 0.781,
        ("target_id_calibration", "genetics_only", "risk_auroc_vs_error"): 0.939,
        ("target_id_calibration", "genetics_only", "rcps_certified"): False,
        ("target_id_calibration", "cross_stage", "rcps_only_alpha"): 0.3,
    }
    for keys, expected in expected_values.items():
        actual = nested(evidence, *keys)
        if actual != expected:
            errors.append(
                f"docs/public_evidence_summary.json {'.'.join(keys)} must be {expected!r}, got {actual!r}"
            )
    if nested(evidence, "prospective_demo", "terminal_gold") is not None:
        errors.append("prospective demo terminal_gold must remain null")
    if nested(evidence, "prospective_demo", "status") != "invalidated_stale_time_context":
        errors.append("prospective demo must remain explicitly invalidated for stale time context")
    if nested(evidence, "prospective_demo", "current_recommendation_claim") is not False:
        errors.append("prospective demo must not claim a current recommendation")
    if nested(evidence, "prospective_demo", "citable_result") is not False:
        errors.append("prospective demo must not expose a citable result")
    if nested(evidence, "fixed_slice_prompt_regression", "autonomous_lookup_mode") != "present-day live source lookups":
        errors.append("prompt regression must disclose present-day live source lookups")
    if nested(evidence, "fixed_slice_prompt_regression", "historical_time_gating_claim") is not False:
        errors.append("prompt regression must not claim historical time-gating")
    if nested(evidence, "provenance", "raw_runs_public") is not False:
        errors.append("evidence summary must record that raw runs are not public")

    for path in (README, HF_CARD, RELEASE_MANIFEST, HF_MANIFEST, TRUST_REPORT, DECISION_PACKET):
        text = read(path)
        for phrase in REQUIRED_POINTER_PHRASES:
            if phrase not in text:
                errors.append(f"{path.relative_to(ROOT)} missing pointer: {phrase}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} scientific claim-boundary error(s)", file=sys.stderr)
        return 1

    print("PASS: scientific claim boundaries and aggregate evidence validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
