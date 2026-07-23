#!/usr/bin/env python3
"""Validate the public aggregate for the external sealed policy evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "retrospective_policy_evaluation_snapshot.json"
DOCUMENT = ROOT / "docs" / "25_cutoff_safe_policy_evaluation.md"
README = ROOT / "README.md"
TRUST_REPORT = ROOT / "docs" / "release_trust_report.md"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
LOCAL_PATH = re.compile(r"(?:/Users|/home|/scratch|/lustre|/gpfs|/nfs)/")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)} must contain a JSON object")
        return {}
    return value


def _expect(
    condition: bool,
    message: str,
    errors: list[str],
) -> None:
    if not condition:
        errors.append(message)


def _metric(
    policies: dict[str, dict[str, Any]],
    policy_id: str,
    field: str,
) -> Any:
    return policies.get(policy_id, {}).get(field)


def _json_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for item in value.values()
            for key in _json_keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _json_keys(item)}
    return set()


def main() -> int:
    errors: list[str] = []
    snapshot = _load_json(SNAPSHOT, errors)
    document = DOCUMENT.read_text(encoding="utf-8", errors="ignore")
    readme = README.read_text(encoding="utf-8", errors="ignore")
    trust = TRUST_REPORT.read_text(encoding="utf-8", errors="ignore")
    serialized = json.dumps(snapshot, sort_keys=True)

    _expect(
        snapshot.get("schema_version")
        == "adds.public-retrospective-policy-evaluation-snapshot.v1",
        "snapshot schema_version is incorrect",
        errors,
    )
    scope = snapshot.get("scope") or {}
    _expect(scope.get("matched_pair_count") == 4, "pair count must be 4", errors)
    _expect(scope.get("episode_count") == 8, "episode count must be 8", errors)
    _expect(
        {
            "drug_discovery_performance",
            "prospective_clinical_utility",
            "confidence_calibration",
            "policy_optimality",
        }.issubset(set(scope.get("not_claimed") or [])),
        "snapshot not_claimed boundary is incomplete",
        errors,
    )

    board = snapshot.get("board") or {}
    for field in (
        "board_fingerprint_sha256",
        "sealed_board_artifact_sha256",
        "policy_comparison_report_artifact_sha256",
        "evaluation_summary_artifact_sha256",
    ):
        _expect(
            isinstance(board.get(field), str)
            and SHA256.fullmatch(board[field]) is not None,
            f"{field} must be a lowercase SHA-256 digest",
            errors,
        )
    _expect(
        board.get("role_assignments_public") is False
        and board.get("per_episode_labels_public") is False
        and board.get("raw_source_bytes_embedded") is False,
        "board public boundary flags are incorrect",
        errors,
    )
    _expect(
        board.get("cached_policy_visible_packets_embedded") is True
        and board.get("independent_deterministic_rerun_exact") is True,
        "board replay flags are incomplete",
        errors,
    )

    policy_rows = snapshot.get("policy_metrics") or []
    policies = {
        row.get("policy_id"): row
        for row in policy_rows
        if isinstance(row, dict) and isinstance(row.get("policy_id"), str)
    }
    expected_policy_ids = {
        "deterministic-gated-stage-output",
        "always-advance-counterfactual",
        "defer-safe-counterfactual",
    }
    _expect(
        set(policies) == expected_policy_ids,
        "policy metric identities are incomplete",
        errors,
    )
    expected_metrics = {
        "deterministic-gated-stage-output": {
            "exact_accuracy": 1.0,
            "success_arm_accuracy": 1.0,
            "failure_arm_accuracy": 1.0,
            "both_correct_rate": 1.0,
            "unsafe_advance_rate": 0.0,
        },
        "always-advance-counterfactual": {
            "exact_accuracy": 0.125,
            "success_arm_accuracy": 0.25,
            "failure_arm_accuracy": 0.0,
            "both_correct_rate": 0.0,
            "unsafe_advance_rate": 1.0,
        },
        "defer-safe-counterfactual": {
            "exact_accuracy": 0.5,
            "success_arm_accuracy": 0.0,
            "failure_arm_accuracy": 1.0,
            "both_correct_rate": 0.0,
            "unsafe_advance_rate": 0.0,
        },
    }
    for policy_id, fields in expected_metrics.items():
        for field, expected in fields.items():
            actual = _metric(policies, policy_id, field)
            _expect(
                isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and math.isclose(float(actual), expected, abs_tol=1e-12),
                f"{policy_id} {field} changed",
                errors,
            )

    expected_gate_checks = {
        "senicapoc_complete_clinical_disposition": "kill",
        "senicapoc_missing_publication_corroboration": "defer",
        "paloma2_approved_candidate_alias": "hold",
        "paloma2_unapproved_candidate_alias": "defer",
        "paloma3_approved_disease_context": "advance",
        "paloma3_unapproved_disease_alias": "defer",
        "paloma_source_disjoint_endpoint_mapping": "hold",
        "paloma_overlapping_source_hash_mapping": "defer",
        "paloma_positive_non_pooled_synthesis": "hold",
    }
    _expect(
        snapshot.get("real_gate_checks") == expected_gate_checks,
        "real gate check aggregate changed",
        errors,
    )

    verification = snapshot.get("verification") or {}
    expected_module_hashes = {
        "sealed_evaluation_module_sha256": _sha256(
            ROOT / "agentic_drug_discovery" / "sealed_evaluation.py"
        ),
        "clinical_promotion_module_sha256": _sha256(
            ROOT / "agentic_drug_discovery" / "promotion.py"
        ),
    }
    for field, expected in expected_module_hashes.items():
        _expect(
            verification.get(field) == expected,
            f"{field} does not match the current public implementation",
            errors,
        )
    for field in (
        "source_bundle_hashes_verified",
        "board_vault_commitments_open_exactly",
        "submission_observation_fingerprints_exact",
        "all_external_artifact_manifest_hashes_verified",
        "all_board_vault_submission_report_schemas_validated",
    ):
        _expect(
            verification.get(field) is True,
            f"verification flag {field} must be true",
            errors,
        )
    _expect(
        verification.get("public_board_label_leak_scan_hits") == 0,
        "public board label leak scan must report zero hits",
        errors,
    )

    boundary = snapshot.get("release_boundary") or {}
    _expect(
        boundary.get("full_external_board_public_release_approved") is False,
        "full external board must remain unapproved for public release",
        errors,
    )
    _expect(
        {
            "full_program_states",
            "cached_real_episode_packets",
            "label_vault",
            "commitment_nonces",
            "per_episode_evaluations",
            "raw_source_bytes",
            "review_jobs",
            "local_paths",
        }.issubset(set(boundary.get("withheld") or [])),
        "snapshot withheld boundary is incomplete",
        errors,
    )
    _expect(
        LOCAL_PATH.search(serialized) is None,
        "snapshot contains a machine-local path",
        errors,
    )
    _expect(
        not {
            "episode_id",
            "evaluator_label_id",
            "gold_decision",
            "failure_causes",
            "commitment_nonce",
        }
        & _json_keys(snapshot),
        "snapshot contains per-episode evaluator fields",
        errors,
    )

    for phrase in (
        "8/8",
        "1/8",
        "4/8",
        "cannot support a calibration claim",
        "docs/retrospective_policy_evaluation_snapshot.json",
    ):
        _expect(phrase in document, f"evaluation document missing: {phrase}", errors)
    for text, label in ((readme, "README.md"), (trust, "release_trust_report.md")):
        _expect(
            "docs/25_cutoff_safe_policy_evaluation.md" in text
            and "docs/retrospective_policy_evaluation_snapshot.json" in text,
            f"{label} is missing sealed evaluation anchors",
            errors,
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("PASS: sealed policy-evaluation snapshot and documentation are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
