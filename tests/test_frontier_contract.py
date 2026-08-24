from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery.frontier import (
    FRONTIER_MANDATORY_GATES,
    FRONTIER_PROTOCOL_ID,
    FrontierAction,
    FrontierContractError,
    frontier_protocol_from_json,
    frontier_protocol_integrity_sha256,
    frontier_protocol_summary,
    frontier_seed_manifest_integrity_sha256,
    frontier_seed_manifest_summary,
    fully_authorized_trajectory_success,
    load_frontier_protocol,
    load_frontier_seed_manifest,
    validate_frontier_protocol,
    validate_frontier_seed_manifest,
)
from agentic_drug_discovery.frontier_board import (
    frontier_board_protocol_integrity_sha256,
    frontier_board_slot_manifest_integrity_sha256,
    frontier_board_summary,
    load_frontier_board_protocol,
    load_frontier_board_slot_manifest,
    validate_frontier_board_protocol,
    validate_frontier_board_slot_manifest,
)
from agentic_drug_discovery.frontier_tasks import (
    frontier_curation_integrity_sha256,
    frontier_development_summary,
    frontier_oracle_set_integrity_sha256,
    frontier_task_set_integrity_sha256,
    load_frontier_curation_tranche,
    load_frontier_oracle_set,
    load_frontier_task_set,
    score_frontier_stage_components,
    validate_frontier_curation_tranche,
    validate_frontier_oracle_set,
    validate_frontier_task_set,
)
from agentic_drug_discovery.frontier_calibration import (
    FRONTIER_CALIBRATION_ORACLE_SET_SCHEMA_VERSION,
    FRONTIER_CALIBRATION_SET_ID,
    FRONTIER_CALIBRATION_TASK_SET_SCHEMA_VERSION,
    build_frontier_calibration_progress,
    frontier_calibration_oracle_set_integrity_sha256,
    frontier_calibration_progress_integrity_sha256,
    frontier_calibration_progress_summary,
    frontier_calibration_task_set_integrity_sha256,
    frontier_calibration_task_sha256,
    frontier_private_identity_commitment,
    load_frontier_calibration_progress,
    validate_frontier_calibration_private_opening,
    validate_frontier_calibration_progress,
)
from agentic_drug_discovery.frontier_preflight import (
    build_frontier_calibration_preflight_summary,
    frontier_private_preflight_integrity_sha256,
    frontier_public_preflight_integrity_sha256,
    load_frontier_public_preflight_summary,
    run_frontier_calibration_preflight,
    validate_frontier_preflight_private_opening,
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)
from agentic_drug_discovery.frontier_oracle_challenge import (
    FRONTIER_ORACLE_CHALLENGE_RESPONSE_SCHEMA_VERSION,
    compare_frontier_oracle_challenge_responses,
    compile_frontier_oracle_challenge_artifacts,
    frontier_oracle_challenge_key_set_integrity_sha256,
    frontier_oracle_challenge_response_integrity_sha256,
    frontier_oracle_challenge_summary_integrity_sha256,
    load_frontier_oracle_challenge_summary,
    validate_frontier_oracle_challenge_private_opening,
    validate_frontier_oracle_challenge_response,
    validate_frontier_oracle_challenge_summary,
)
from agentic_drug_discovery.frontier_oracle_fragility import (
    compile_frontier_oracle_fragility_artifacts,
    frontier_oracle_fragility_report_integrity_sha256,
    frontier_oracle_fragility_summary_integrity_sha256,
    load_frontier_oracle_fragility_summary,
    validate_frontier_oracle_fragility_private_opening,
    validate_frontier_oracle_fragility_summary,
)
from agentic_drug_discovery.frontier_oracle_support_curation import (
    compile_frontier_support_curation_artifacts,
    frontier_support_curation_packet_set_integrity_sha256,
    frontier_support_curation_summary_integrity_sha256,
    load_frontier_support_curation_summary,
    validate_frontier_support_curation_private_opening,
    validate_frontier_support_curation_summary,
)
from agentic_drug_discovery.frontier_oracle_transition_audit import (
    compile_frontier_transition_audit_artifacts,
    frontier_transition_audit_report_integrity_sha256,
    frontier_transition_audit_summary_integrity_sha256,
    load_frontier_transition_audit_summary,
    validate_frontier_transition_audit_private_opening,
    validate_frontier_transition_audit_summary,
)
from agentic_drug_discovery.frontier_coupled_augmentation import (
    compile_frontier_coupled_augmentation_artifacts,
    frontier_coupled_augmentation_packet_set_integrity_sha256,
    frontier_coupled_augmentation_summary_integrity_sha256,
    load_frontier_coupled_augmentation_summary,
    validate_frontier_coupled_augmentation_private_opening,
    validate_frontier_coupled_augmentation_summary,
)
from agentic_drug_discovery.frontier_coupled_placebo import (
    compile_frontier_coupled_placebo_artifacts,
    frontier_coupled_placebo_summary_integrity_sha256,
    load_frontier_coupled_placebo_summary,
    validate_frontier_coupled_placebo_private_opening,
    validate_frontier_coupled_placebo_summary,
)
from agentic_drug_discovery.frontier_tokenizer_placebo import (
    compile_frontier_tokenizer_placebo_artifacts,
    frontier_tokenizer_placebo_summary_integrity_sha256,
    load_frontier_tokenizer_placebo_summary,
    validate_frontier_tokenizer_placebo_private_opening,
    validate_frontier_tokenizer_placebo_summary,
)
from agentic_drug_discovery.frontier_tokenizer_independent_evaluation import (
    load_protocol as load_independent_tokenizer_protocol,
    load_summary as load_independent_tokenizer_summary,
    summary_integrity_sha256 as independent_tokenizer_summary_integrity_sha256,
    validate_private_opening as validate_independent_tokenizer_private_opening,
    validate_summary as validate_independent_tokenizer_summary,
)
from agentic_drug_discovery.frontier_semantic_review import (
    compile_frontier_semantic_review_artifacts,
    frontier_semantic_key_set_integrity_sha256,
    frontier_semantic_summary_integrity_sha256,
    load_frontier_semantic_review_summary,
    validate_frontier_semantic_review_private_opening,
    validate_frontier_semantic_review_summary,
)
from agentic_drug_discovery.frontier_semantic_resolution import (
    build_frontier_semantic_resolution_artifacts,
    build_frontier_semantic_resolution_receipt,
    frontier_semantic_resolution_summary_integrity_sha256,
    load_frontier_semantic_resolution_summary,
    replay_frontier_semantic_consensus,
    validate_frontier_semantic_resolution_private_opening,
    validate_frontier_semantic_resolution_receipt,
    validate_frontier_semantic_resolution_summary,
)
from agentic_drug_discovery.frontier_semantic_workflow import (
    FRONTIER_SEMANTIC_RESPONSE_SCHEMA_VERSION,
    build_frontier_semantic_workflow_artifacts,
    frontier_semantic_observed_pair_deltas,
    frontier_semantic_response_integrity_sha256,
    frontier_semantic_workflow_summary_integrity_sha256,
    load_frontier_semantic_workflow_summary,
    triage_frontier_semantic_responses,
    validate_frontier_semantic_reviewer_response,
    validate_frontier_semantic_workflow_private_opening,
    validate_frontier_semantic_workflow_summary,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "adds_frontier_research_protocol.json"
PROTOCOL_SCHEMA = ROOT / "rl_env" / "specs" / "frontier_research_protocol.schema.json"
SEEDS = ROOT / "rl_env" / "specs" / "frontier_pilot_seed_manifest.example.json"
SEEDS_SCHEMA = ROOT / "rl_env" / "specs" / "frontier_pilot_seed_manifest.schema.json"
TASKS = ROOT / "rl_env" / "specs" / "frontier_development_task_set.example.json"
TASKS_SCHEMA = ROOT / "rl_env" / "specs" / "frontier_development_task_set.schema.json"
ORACLES = ROOT / "rl_env" / "specs" / "frontier_development_oracle_set.example.json"
ORACLES_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_development_oracle_set.schema.json"
)
CURATION = (
    ROOT / "rl_env" / "specs" / "frontier_development_curation_tranche.example.json"
)
CURATION_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_development_curation_tranche.schema.json"
)
BOARD_PROTOCOL = ROOT / "docs" / "adds_frontier_board_protocol.json"
BOARD_PROTOCOL_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_board_protocol.schema.json"
)
BOARD_SLOTS = ROOT / "rl_env" / "specs" / "frontier_private_board_slots.example.json"
BOARD_SLOTS_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_board_slots.schema.json"
)
CALIBRATION_PROGRESS = (
    ROOT / "rl_env" / "specs" / "frontier_calibration_authoring_progress.json"
)
CALIBRATION_PROGRESS_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_calibration_authoring_progress.schema.json"
)
PRIVATE_CALIBRATION_TASK_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_calibration_task_set.schema.json"
)
PRIVATE_CALIBRATION_ORACLE_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_calibration_oracle_set.schema.json"
)
PREFLIGHT_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_calibration_preflight_summary.json"
)
PREFLIGHT_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_calibration_preflight_summary.schema.json"
)
PRIVATE_PREFLIGHT_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_calibration_preflight.schema.json"
)
SEMANTIC_REVIEW_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_semantic_review_readiness_summary.json"
)
SEMANTIC_REVIEW_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_semantic_review_readiness_summary.schema.json"
)
PRIVATE_SEMANTIC_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_semantic_review_packet_set.schema.json"
)
PRIVATE_SEMANTIC_KEY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_semantic_review_key_set.schema.json"
)
SEMANTIC_WORKFLOW_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_semantic_review_workflow_summary.json"
)
SEMANTIC_WORKFLOW_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_semantic_review_workflow_summary.schema.json"
)
PRIVATE_SEMANTIC_RESPONSE_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_semantic_review_response.schema.json"
)
PRIVATE_SEMANTIC_TRIAGE_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_semantic_review_triage.schema.json"
)
PRIVATE_SEMANTIC_LEDGER_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_semantic_review_workflow_ledger.schema.json"
)
SEMANTIC_RESOLUTION_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_semantic_review_resolution_summary.json"
)
SEMANTIC_RESOLUTION_SUMMARY_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_semantic_review_resolution_summary.schema.json"
)
PRIVATE_SEMANTIC_REPLAY_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_semantic_review_canonical_replay.schema.json"
)
PRIVATE_SEMANTIC_RECEIPT_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_semantic_review_resolution_receipt.schema.json"
)
PRIVATE_SEMANTIC_RESOLUTION_LEDGER_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_semantic_review_resolution_ledger.schema.json"
)
ORACLE_CHALLENGE_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_challenge_readiness_summary.json"
)
ORACLE_CHALLENGE_SUMMARY_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_oracle_challenge_readiness_summary.schema.json"
)
PRIVATE_ORACLE_CHALLENGE_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_oracle_challenge_packet_set.schema.json"
)
PRIVATE_ORACLE_CHALLENGE_KEY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_oracle_challenge_key_set.schema.json"
)
PRIVATE_ORACLE_CHALLENGE_RESPONSE_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_oracle_challenge_response.schema.json"
)
PRIVATE_ORACLE_CHALLENGE_COMPARISON_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_oracle_challenge_comparison.schema.json"
)
PRIVATE_ORACLE_CHALLENGE_LEDGER_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_oracle_challenge_ledger.schema.json"
)
ORACLE_FRAGILITY_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_fragility_summary.json"
)
ORACLE_FRAGILITY_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_fragility_summary.schema.json"
)
PRIVATE_ORACLE_FRAGILITY_REPORT_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_oracle_fragility_report.schema.json"
)
SUPPORT_CURATION_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_support_curation_summary.json"
)
SUPPORT_CURATION_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_support_curation_summary.schema.json"
)
PRIVATE_SUPPORT_CURATION_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_oracle_support_curation_packet_set.schema.json"
)
TRANSITION_AUDIT_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_transition_audit_summary.json"
)
TRANSITION_AUDIT_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_oracle_transition_audit_summary.schema.json"
)
PRIVATE_TRANSITION_AUDIT_REPORT_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_oracle_transition_audit_report.schema.json"
)
COUPLED_AUGMENTATION_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_coupled_augmentation_summary.json"
)
COUPLED_AUGMENTATION_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_coupled_augmentation_summary.schema.json"
)
PRIVATE_COUPLED_AUGMENTATION_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_coupled_augmentation_packet_set.schema.json"
)
COUPLED_PLACEBO_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_coupled_placebo_summary.json"
)
COUPLED_PLACEBO_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_coupled_placebo_summary.schema.json"
)
PRIVATE_COUPLED_PLACEBO_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_coupled_placebo_packet_set.schema.json"
)
PRIVATE_COUPLED_PLACEBO_KEY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_coupled_placebo_key_set.schema.json"
)
TOKENIZER_PLACEBO_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_tokenizer_placebo_summary.json"
)
TOKENIZER_PLACEBO_SUMMARY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_tokenizer_placebo_summary.schema.json"
)
PRIVATE_TOKENIZER_PLACEBO_PACKET_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_tokenizer_placebo_packet_set.schema.json"
)
PRIVATE_TOKENIZER_PLACEBO_KEY_SCHEMA = (
    ROOT / "rl_env" / "specs" / "frontier_private_tokenizer_placebo_key_set.schema.json"
)
TOKENIZER_INDEPENDENT_PROTOCOL = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_tokenizer_independent_evaluation_protocol.json"
)
TOKENIZER_INDEPENDENT_PROTOCOL_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_tokenizer_independent_evaluation_protocol.schema.json"
)
TOKENIZER_INDEPENDENT_SUMMARY = (
    ROOT / "rl_env" / "specs" / "frontier_tokenizer_independent_evaluation_summary.json"
)
TOKENIZER_INDEPENDENT_SUMMARY_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_tokenizer_independent_evaluation_summary.schema.json"
)
PRIVATE_TOKENIZER_INDEPENDENT_REPORT_SCHEMA = (
    ROOT
    / "rl_env"
    / "specs"
    / "frontier_private_tokenizer_independent_evaluation_report.schema.json"
)
TOKENIZER_INDEPENDENT_ASSET_ROOT = (
    ROOT / "case_banks" / "frontier_private" / "tokenizer_assets"
)
PRIVATE_TOKENIZER_PLACEBO_PACKETS = (
    ROOT
    / "case_banks"
    / "frontier_private"
    / "calibration"
    / "frontier_tokenizer_placebo_packets.private.json"
)
PRIVATE_TOKENIZER_PLACEBO_KEYS = (
    ROOT
    / "case_banks"
    / "frontier_private"
    / "calibration"
    / "frontier_tokenizer_placebo_keys.private.json"
)
PRIVATE_TOKENIZER_INDEPENDENT_REPORT = (
    ROOT
    / "case_banks"
    / "frontier_private"
    / "calibration"
    / "frontier_tokenizer_independent_evaluation.private.json"
)


def _protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def _seeds() -> dict:
    return json.loads(SEEDS.read_text(encoding="utf-8"))


def _tasks() -> dict:
    return json.loads(TASKS.read_text(encoding="utf-8"))


def _oracles() -> dict:
    return json.loads(ORACLES.read_text(encoding="utf-8"))


def _curation() -> dict:
    return json.loads(CURATION.read_text(encoding="utf-8"))


def _board_protocol() -> dict:
    return json.loads(BOARD_PROTOCOL.read_text(encoding="utf-8"))


def _board_slots() -> dict:
    return json.loads(BOARD_SLOTS.read_text(encoding="utf-8"))


def _calibration_progress() -> dict:
    return json.loads(CALIBRATION_PROGRESS.read_text(encoding="utf-8"))


def _preflight_summary() -> dict:
    return json.loads(PREFLIGHT_SUMMARY.read_text(encoding="utf-8"))


def _semantic_review_summary() -> dict:
    return json.loads(SEMANTIC_REVIEW_SUMMARY.read_text(encoding="utf-8"))


def _semantic_workflow_summary() -> dict:
    return json.loads(SEMANTIC_WORKFLOW_SUMMARY.read_text(encoding="utf-8"))


def _oracle_fragility_summary() -> dict:
    return json.loads(ORACLE_FRAGILITY_SUMMARY.read_text(encoding="utf-8"))


def _support_curation_summary() -> dict:
    return json.loads(SUPPORT_CURATION_SUMMARY.read_text(encoding="utf-8"))


def _transition_audit_summary() -> dict:
    return json.loads(TRANSITION_AUDIT_SUMMARY.read_text(encoding="utf-8"))


def _coupled_augmentation_summary() -> dict:
    return json.loads(COUPLED_AUGMENTATION_SUMMARY.read_text(encoding="utf-8"))


def _coupled_placebo_summary() -> dict:
    return json.loads(COUPLED_PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def _tokenizer_placebo_summary() -> dict:
    return json.loads(TOKENIZER_PLACEBO_SUMMARY.read_text(encoding="utf-8"))


def _tokenizer_independent_protocol() -> dict:
    return json.loads(TOKENIZER_INDEPENDENT_PROTOCOL.read_text(encoding="utf-8"))


def _tokenizer_independent_summary() -> dict:
    return json.loads(TOKENIZER_INDEPENDENT_SUMMARY.read_text(encoding="utf-8"))


def _rehash_protocol(protocol: dict) -> dict:
    protocol["integrity_sha256"] = frontier_protocol_integrity_sha256(protocol)
    return protocol


def _rehash_seeds(manifest: dict) -> dict:
    manifest["integrity_sha256"] = frontier_seed_manifest_integrity_sha256(manifest)
    return manifest


def _rehash_tasks(task_set: dict) -> dict:
    task_set["integrity_sha256"] = frontier_task_set_integrity_sha256(task_set)
    return task_set


def _rehash_oracles(oracle_set: dict) -> dict:
    oracle_set["integrity_sha256"] = frontier_oracle_set_integrity_sha256(oracle_set)
    return oracle_set


def _rehash_curation(curation: dict) -> dict:
    curation["integrity_sha256"] = frontier_curation_integrity_sha256(curation)
    return curation


def _rehash_board_protocol(board_protocol: dict) -> dict:
    board_protocol["integrity_sha256"] = frontier_board_protocol_integrity_sha256(
        board_protocol
    )
    return board_protocol


def _rehash_board_slots(board_slots: dict) -> dict:
    board_slots["integrity_sha256"] = frontier_board_slot_manifest_integrity_sha256(
        board_slots
    )
    return board_slots


def _rehash_calibration_progress(progress: dict) -> dict:
    progress["integrity_sha256"] = frontier_calibration_progress_integrity_sha256(
        progress
    )
    return progress


def _development() -> tuple[dict, dict, dict, dict, dict]:
    protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
    seeds = load_frontier_seed_manifest(SEEDS, root=ROOT, protocol=protocol)
    tasks = load_frontier_task_set(
        TASKS,
        root=ROOT,
        protocol=protocol,
        seed_manifest=seeds,
    )
    oracles = load_frontier_oracle_set(
        ORACLES,
        root=ROOT,
        protocol=protocol,
        seed_manifest=seeds,
        task_set=tasks,
    )
    curation = load_frontier_curation_tranche(
        CURATION,
        root=ROOT,
        protocol=protocol,
        seed_manifest=seeds,
        task_set=tasks,
        oracle_set=oracles,
    )
    return protocol, seeds, tasks, oracles, curation


def _board() -> tuple[dict, dict, dict]:
    protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
    board_protocol = load_frontier_board_protocol(
        BOARD_PROTOCOL,
        root=ROOT,
        frontier_protocol=protocol,
    )
    slots = load_frontier_board_slot_manifest(
        BOARD_SLOTS,
        root=ROOT,
        frontier_protocol=protocol,
        board_protocol=board_protocol,
    )
    return protocol, board_protocol, slots


def _calibration() -> tuple[dict, dict, dict, dict]:
    protocol, board_protocol, slots = _board()
    progress = load_frontier_calibration_progress(
        CALIBRATION_PROGRESS,
        root=ROOT,
        frontier_protocol=protocol,
        board_protocol=board_protocol,
        board_slots=slots,
    )
    return protocol, board_protocol, slots, progress


def _nonce(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _synthetic_private_calibration() -> tuple[dict, dict, dict]:
    protocol, board_protocol, board_slots = _board()
    calibration_slots = [
        slot for slot in board_slots["slots"] if slot["partition"] == "calibration"
    ]
    source_paths = ("README.md", "docs/50_adds_frontier_research_protocol.md")
    sources = [
        {
            "artifact_path": path,
            "artifact_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
            "source_role": "authoring_context",
            "model_visible": False,
        }
        for path in source_paths
    ]
    tasks = []
    for slot in calibration_slots:
        anchor = (
            "2023-12-31"
            if slot["temporal_regime"] == "historical_pre_2024"
            else "2025-06-30"
        )
        post_anchor = (
            "2024-01-01"
            if slot["temporal_regime"] == "historical_pre_2024"
            else "2026-01-01"
        )
        evidence_dates = (
            ("2023-01-01", "2023-06-01", "2023-11-01")
            if slot["temporal_regime"] == "historical_pre_2024"
            else ("2024-01-01", "2025-01-01", "2025-06-01")
        )
        if slot["family_id"] == "temporal_reversal":
            evidence_dates = (*evidence_dates[:2], post_anchor)
        stage_dates = [anchor] * 6
        if slot["family_id"] == "temporal_reversal":
            stage_dates[3:] = [post_anchor] * 3
        access_counts = (1, 1, 2, 3, 3, 3)
        stage_kinds = (
            "retrieve",
            "identity",
            "chronology",
            "alignment",
            "action",
            "replay",
        )
        stage_gates = (
            ("evidence_retrieval_complete",),
            ("identity_continuity", "cutoff_compliance"),
            ("lineage_independence", "witness_valid"),
            (
                "endpoint_population_alignment",
                "uncertainty_handling",
                "risk_flags_correct",
            ),
            (
                "disposition_correct",
                "next_action_correct",
                "blocker_certificate_valid",
                "budget_compliance",
            ),
            ("exact_replay",),
        )
        evidence_ids = [f"ev-{slot['slot_id']}-{index}" for index in range(1, 4)]
        tasks.append(
            {
                "slot_id": slot["slot_id"],
                "task_id": f"synthetic-{slot['slot_id']}",
                "family_id": slot["family_id"],
                "disease_domain": slot["disease_domain"],
                "temporal_regime": slot["temporal_regime"],
                "task_commitment_nonce": _nonce(f"task:{slot['slot_id']}"),
                "disease_identity": f"synthetic disease {slot['slot_id']}",
                "disease_identity_nonce": _nonce(f"disease:{slot['slot_id']}"),
                "program_identity": f"synthetic program {slot['slot_id']}",
                "program_identity_nonce": _nonce(f"program:{slot['slot_id']}"),
                "prompt": "Resolve the staged synthetic evidence and issue a bounded action.",
                "anchor_cutoff_date": anchor,
                "stage_budget": 6,
                "tool_call_budget": 6,
                "authoring_source_artifacts": copy.deepcopy(sources),
                "evidence_nodes": [
                    {
                        "evidence_id": evidence_id,
                        "available_on": available_on,
                        "lineage_id": f"lineage-{index}",
                        "evidence_role": "source",
                        "evidence_summary": f"Synthetic evidence item {index}.",
                    }
                    for index, (evidence_id, available_on) in enumerate(
                        zip(evidence_ids, evidence_dates, strict=True), start=1
                    )
                ],
                "lineage_edges": [],
                "stages": [
                    {
                        "stage_id": f"s{index + 1:02d}",
                        "stage_kind": stage_kinds[index],
                        "as_of_date": stage_dates[index],
                        "accessible_evidence_ids": evidence_ids[: access_counts[index]],
                        "required_gates": list(stage_gates[index]),
                        "max_tool_calls": 1,
                    }
                    for index in range(6)
                ],
                "nonclaim": "This is an authored calibration draft pending independent review and board admission.",
            }
        )
    task_set = {
        "schema_version": FRONTIER_CALIBRATION_TASK_SET_SCHEMA_VERSION,
        "protocol_id": protocol["protocol_id"],
        "board_id": board_protocol["board_id"],
        "set_id": FRONTIER_CALIBRATION_SET_ID,
        "set_role": "private_calibration_authoring",
        "authoring_status": "authored_pending_review",
        "task_selection_blinded_to_models": True,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "tasks": tasks,
        "integrity_sha256": "0" * 64,
    }
    task_set["integrity_sha256"] = frontier_calibration_task_set_integrity_sha256(
        task_set
    )

    oracles = []
    for task in tasks:
        mutations = [
            ("rename", "source_id_rename", "nuisance_invariance", []),
            (
                "remove",
                "critical_evidence_removal",
                "critical_flip",
                ["witness", "blockers"],
            ),
            (
                "rebind",
                "temporal_access_rebind",
                "critical_flip",
                ["risk_flags", "blockers"],
            ),
            (
                "reveal",
                "bounded_evidence_reveal",
                "evidence_ladder",
                ["next_action", "witness"],
            ),
            ("flip", "identity_rebind", "critical_flip", ["disposition", "blockers"]),
        ]
        oracles.append(
            {
                "slot_id": task["slot_id"],
                "task_id": task["task_id"],
                "task_sha256": frontier_calibration_task_sha256(task),
                "oracle_commitment_nonce": _nonce(f"oracle:{task['slot_id']}"),
                "stage_expectations": [
                    {
                        "stage_id": stage["stage_id"],
                        "action": {
                            "disposition": "hold",
                            "next_action": "verify",
                            "risk_flags": ["provenance"],
                        },
                        "witness_evidence_ids": stage["accessible_evidence_ids"],
                        "blocker_codes": ["synthetic_pending_gate"],
                    }
                    for stage in task["stages"]
                ],
                "mutation_expectations": [
                    {
                        "mutation_id": f"{task['slot_id']}-{mutation_id}",
                        "probe_kind": probe_kind,
                        "mutation_class": mutation_class,
                        "operation": f"Synthetic {mutation_id} operation.",
                        "expected_changed_components": changed,
                    }
                    for mutation_id, probe_kind, mutation_class, changed in mutations
                ],
                "nonclaim": "This sealed draft oracle has not passed independent review, expert solve, or replay admission.",
            }
        )
    oracle_set = {
        "schema_version": FRONTIER_CALIBRATION_ORACLE_SET_SCHEMA_VERSION,
        "protocol_id": protocol["protocol_id"],
        "board_id": board_protocol["board_id"],
        "set_id": FRONTIER_CALIBRATION_SET_ID,
        "set_role": "private_sealed_calibration_oracle",
        "authoring_status": "authored_pending_review",
        "benchmark_evidence_claimed": False,
        "task_set_integrity_sha256": task_set["integrity_sha256"],
        "oracles": oracles,
        "integrity_sha256": "0" * 64,
    }
    oracle_set["integrity_sha256"] = frontier_calibration_oracle_set_integrity_sha256(
        oracle_set
    )
    progress = build_frontier_calibration_progress(
        task_set=task_set,
        oracle_set=oracle_set,
        root=ROOT,
        frontier_protocol=protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        updated_on="2026-08-21",
    )
    return task_set, oracle_set, progress


def _synthetic_semantic_response(
    packet_set: dict, *, packet_id: str, reviewer_index: int
) -> dict:
    packet = next(
        item for item in packet_set["packets"] if item["packet_id"] == packet_id
    )
    arm_answers = {}
    for arm_id in ("arm_a", "arm_b"):
        arm_answers[arm_id] = [
            {
                "stage_id": stage["stage_id"],
                "disposition": "hold",
                "next_action": "verify",
                "risk_flags": ["provenance"],
                "witness_evidence_ids": list(stage["accessible_evidence_ids"]),
                "blocker_codes": ["synthetic_pending_gate"],
                "abstained": False,
            }
            for stage in packet[arm_id]["stages"]
        ]
    if packet["probe_kind"] == "identity_rebind":
        for answer in arm_answers["arm_b"]:
            answer["blocker_codes"].append(
                "synthetic_identity_discontinuity_review_required"
            )
    response = {
        "schema_version": FRONTIER_SEMANTIC_RESPONSE_SCHEMA_VERSION,
        "packet_id": packet_id,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "arm_a_commitment": packet["arm_a_commitment"],
        "arm_b_commitment": packet["arm_b_commitment"],
        "reviewer_identity_commitment": _nonce(f"reviewer:{reviewer_index}"),
        "reviewer_affiliation_commitment": _nonce(f"affiliation:{reviewer_index}"),
        "conflict_of_interest_declared": False,
        "independence_attested": True,
        "completed_on": "2026-08-22",
        "arm_answers": arm_answers,
        "pair_assessment": {
            "semantic_change_detected": False,
            "changed_components": [],
            "reason_codes": [
                "evidence_sufficiency_change"
                if packet["probe_kind"] == "bounded_evidence_reveal"
                else "identity_discontinuity"
            ],
            "abstained": False,
        },
        "integrity_sha256": "0" * 64,
    }
    _sync_semantic_pair_assessment(response)
    return response


def _synthetic_oracle_challenge_response(
    packet_set: dict,
    key_set: dict,
    oracle_set: dict,
    *,
    packet_id: str,
    challenger_index: int,
) -> dict:
    packet = next(
        item for item in packet_set["packets"] if item["packet_id"] == packet_id
    )
    key = next(item for item in key_set["keys"] if item["packet_id"] == packet_id)
    oracle = next(
        item for item in oracle_set["oracles"] if item["slot_id"] == key["slot_id"]
    )
    response = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_RESPONSE_SCHEMA_VERSION,
        "packet_id": packet_id,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "challenge_task_commitment": packet["challenge_task_commitment"],
        "challenger_identity_commitment": _nonce(
            f"oracle-challenger:{challenger_index}"
        ),
        "challenger_affiliation_commitment": _nonce(
            f"oracle-affiliation:{challenger_index}"
        ),
        "conflict_of_interest_declared": False,
        "independence_attested": True,
        "author_oracle_accessed": False,
        "semantic_review_material_accessed": False,
        "authoring_source_artifacts_accessed": False,
        "completed_on": "2026-08-23",
        "stage_answers": [
            {
                "stage_id": expectation["stage_id"],
                "disposition": expectation["action"]["disposition"],
                "next_action": expectation["action"]["next_action"],
                "risk_flags": list(expectation["action"]["risk_flags"]),
                "witness_evidence_ids": list(expectation["witness_evidence_ids"]),
                "blocker_codes": list(expectation["blocker_codes"]),
                "abstained": False,
            }
            for expectation in oracle["stage_expectations"]
        ],
        "overall_abstained": False,
        "integrity_sha256": "0" * 64,
    }
    response["integrity_sha256"] = frontier_oracle_challenge_response_integrity_sha256(
        response
    )
    return response


def _sync_semantic_pair_assessment(response: dict) -> None:
    observed = frontier_semantic_observed_pair_deltas(response)["changed_components"]
    response["pair_assessment"]["semantic_change_detected"] = bool(observed)
    response["pair_assessment"]["changed_components"] = observed
    response["integrity_sha256"] = frontier_semantic_response_integrity_sha256(response)


def _oracle_aligned_semantic_responses(
    packet_set: dict,
    key_set: dict,
    oracle_set: dict,
    *,
    packet_id: str,
) -> list[dict]:
    key = next(item for item in key_set["keys"] if item["packet_id"] == packet_id)
    oracle = next(
        item for item in oracle_set["oracles"] if item["slot_id"] == key["slot_id"]
    )
    responses = [
        _synthetic_semantic_response(
            packet_set,
            packet_id=packet_id,
            reviewer_index=index,
        )
        for index in range(3)
    ]
    canonical_arm = key["canonical_arm"]
    for response in responses:
        response["arm_answers"][canonical_arm] = [
            {
                "stage_id": expectation["stage_id"],
                "disposition": expectation["action"]["disposition"],
                "next_action": expectation["action"]["next_action"],
                "risk_flags": list(expectation["action"]["risk_flags"]),
                "witness_evidence_ids": list(expectation["witness_evidence_ids"]),
                "blocker_codes": list(expectation["blocker_codes"]),
                "abstained": False,
            }
            for expectation in oracle["stage_expectations"]
        ]
        _sync_semantic_pair_assessment(response)
    return responses


class FrontierContractTests(unittest.TestCase):
    def test_factorized_action_enforces_bounded_semantics(self) -> None:
        action = FrontierAction(
            disposition="hold",
            next_action="verify",
            risk_flags=("provenance", "temporal_leakage"),
        )
        self.assertEqual(action.disposition, "hold")

        with self.assertRaisesRegex(
            FrontierContractError, "requires a bounded next action"
        ):
            FrontierAction(disposition="hold", next_action="none")
        with self.assertRaisesRegex(FrontierContractError, "must not schedule"):
            FrontierAction(disposition="terminate", next_action="retrieve")
        with self.assertRaisesRegex(FrontierContractError, "must be unique"):
            FrontierAction(
                disposition="advance",
                next_action="experiment",
                risk_flags=("safety", "safety"),
            )

    def test_full_success_requires_every_gate_and_zero_unauthorized_commits(
        self,
    ) -> None:
        passing = {gate: True for gate in FRONTIER_MANDATORY_GATES}
        self.assertTrue(
            fully_authorized_trajectory_success(
                passing,
                unauthorized_commit_count=0,
            )
        )

        one_failure = dict(passing)
        one_failure["lineage_independence"] = False
        self.assertFalse(
            fully_authorized_trajectory_success(
                one_failure,
                unauthorized_commit_count=0,
            )
        )
        self.assertFalse(
            fully_authorized_trajectory_success(
                passing,
                unauthorized_commit_count=1,
            )
        )
        missing = dict(passing)
        missing.pop("exact_replay")
        with self.assertRaisesRegex(FrontierContractError, "missing mandatory gates"):
            fully_authorized_trajectory_success(
                missing,
                unauthorized_commit_count=0,
            )

    def test_protocol_and_seed_manifest_validate(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        protocol_summary = frontier_protocol_summary(protocol, root=ROOT)
        self.assertEqual(protocol_summary["protocol_id"], FRONTIER_PROTOCOL_ID)
        self.assertEqual(protocol_summary["task_family_count"], 5)
        self.assertEqual(protocol_summary["mandatory_gate_count"], 13)
        self.assertEqual(protocol_summary["pilot_base_task_count"], 40)
        self.assertEqual(protocol_summary["pilot_minimum_diagnostic_cases"], 200)
        self.assertFalse(protocol_summary["real_benchmark_evidence_claimed"])

        seeds = load_frontier_seed_manifest(
            SEEDS,
            root=ROOT,
            protocol=protocol,
        )
        seed_summary = frontier_seed_manifest_summary(
            seeds,
            root=ROOT,
            protocol=protocol,
        )
        self.assertEqual(seed_summary["seed_count"], 5)
        self.assertEqual(seed_summary["planned_mutation_count"], 25)
        self.assertFalse(seed_summary["benchmark_evidence_claimed"])

    def test_development_tranche_validates_without_board_claims(self) -> None:
        protocol, seeds, tasks, oracles, curation = _development()
        summary = frontier_development_summary(
            curation,
            root=ROOT,
            protocol=protocol,
            seed_manifest=seeds,
            task_set=tasks,
            oracle_set=oracles,
        )
        self.assertEqual(summary["development_fixture_count"], 5)
        self.assertEqual(summary["canonical_task_target"], 40)
        self.assertEqual(summary["board_admitted_count"], 0)
        self.assertFalse(summary["independent_review_complete"])
        self.assertFalse(summary["baseline_model_runs_started"])
        self.assertFalse(summary["benchmark_evidence_claimed"])

    def test_private_board_sampling_frame_is_balanced_and_empty(self) -> None:
        protocol, board_protocol, slots = _board()
        summary = frontier_board_summary(
            slots,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
        )
        self.assertEqual(summary["slot_count"], 40)
        self.assertEqual(summary["calibration_slot_count"], 10)
        self.assertEqual(summary["sealed_slot_count"], 30)
        self.assertEqual(summary["disease_domain_count"], 8)
        self.assertEqual(summary["assigned_task_count"], 0)
        self.assertEqual(summary["board_admitted_count"], 0)
        self.assertFalse(summary["baseline_model_runs_started"])
        self.assertFalse(summary["benchmark_evidence_claimed"])

    def test_calibration_authoring_progress_is_payload_free_and_unadmitted(
        self,
    ) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        summary = frontier_calibration_progress_summary(
            progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertEqual(summary["authored_task_count"], 10)
        self.assertEqual(summary["task_family_count"], 5)
        self.assertEqual(summary["calibration_domain_count"], 2)
        self.assertEqual(summary["total_stage_count"], 60)
        self.assertEqual(summary["total_mutation_count"], 50)
        self.assertEqual(summary["board_admitted_count"], 0)
        self.assertFalse(summary["independent_review_complete"])
        self.assertFalse(summary["private_payload_published"])
        self.assertFalse(summary["baseline_model_runs_started"])
        self.assertFalse(summary["benchmark_evidence_claimed"])

    def test_calibration_progress_rejects_premature_review_and_baseline_claims(
        self,
    ) -> None:
        protocol, board_protocol, slots, _ = _calibration()
        mutations = (
            ("curator", "independent_curator_count", 3),
            ("admission", "board_admitted", True),
        )
        for name, field_name, value in mutations:
            with self.subTest(mutation=name):
                progress = copy.deepcopy(_calibration_progress())
                progress["records"][0][field_name] = value
                _rehash_calibration_progress(progress)
                with self.assertRaises(FrontierContractError):
                    validate_frontier_calibration_progress(
                        progress,
                        root=ROOT,
                        frontier_protocol=protocol,
                        board_protocol=board_protocol,
                        board_slots=slots,
                    )

        progress = copy.deepcopy(_calibration_progress())
        progress["baseline_model_runs_started"] = True
        _rehash_calibration_progress(progress)
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_calibration_progress(
                progress,
                root=ROOT,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
                board_slots=slots,
            )

    def test_private_identity_commitments_are_salted_per_slot(self) -> None:
        shared = {
            "slot_id": "slot-lineage-01",
            "identity_kind": "disease",
            "identity": "sickle cell disease|MONDO:0011382",
        }
        first = frontier_private_identity_commitment(**shared, nonce="1" * 64)
        second = frontier_private_identity_commitment(**shared, nonce="2" * 64)
        self.assertNotEqual(first, second)

    def test_synthetic_private_calibration_opens_every_public_commitment(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        summary = validate_frontier_calibration_private_opening(
            progress=progress,
            task_set=task_set,
            oracle_set=oracle_set,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertTrue(summary["private_commitments_opened"])
        self.assertEqual(summary["authored_task_count"], 10)
        self.assertEqual(summary["total_stage_count"], 60)
        self.assertEqual(summary["total_mutation_count"], 50)
        self.assertEqual(summary["board_admitted_count"], 0)

        for schema_path, artifact in (
            (PRIVATE_CALIBRATION_TASK_SCHEMA, task_set),
            (PRIVATE_CALIBRATION_ORACLE_SCHEMA, oracle_set),
            (CALIBRATION_PROGRESS_SCHEMA, progress),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tampered = copy.deepcopy(progress)
        tampered["records"][0]["task_commitment"] = "0" * 64
        _rehash_calibration_progress(tampered)
        with self.assertRaisesRegex(FrontierContractError, "do not open"):
            validate_frontier_calibration_private_opening(
                progress=tampered,
                task_set=task_set,
                oracle_set=oracle_set,
                root=ROOT,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
                board_slots=slots,
            )

    def test_calibration_preflight_separates_machine_and_semantic_probes(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_report = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_summary = build_frontier_calibration_preflight_summary(
            private_report=private_report,
            progress=progress,
            **validation_kwargs,
        )
        opening = validate_frontier_preflight_private_opening(
            private_report=private_report,
            public_summary=public_summary,
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_preflight_commitment_opened"])
        self.assertEqual(opening["canonical_stage_round_trip"], "60/60")
        self.assertEqual(opening["mutation_probe_count"], 50)
        self.assertEqual(opening["machine_decidable_probe_count"], 30)
        self.assertEqual(opening["machine_expected_outcome_match_count"], 30)
        self.assertEqual(opening["semantic_review_required_probe_count"], 20)
        self.assertEqual(opening["structurally_accepted_semantic_probe_count"], 20)
        self.assertTrue(opening["human_review_required"])
        self.assertEqual(opening["board_admitted_count"], 0)
        self.assertFalse(opening["baseline_model_runs_started"])
        self.assertFalse(opening["benchmark_evidence_claimed"])

        for schema_path, artifact in (
            (PRIVATE_PREFLIGHT_SCHEMA, private_report),
            (PREFLIGHT_SUMMARY_SCHEMA, public_summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tampered_public = copy.deepcopy(public_summary)
        tampered_public["semantic_review_required_probe_count"] = 19
        tampered_public["integrity_sha256"] = (
            frontier_public_preflight_integrity_sha256(tampered_public)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 20"):
            validate_frontier_public_preflight_summary(
                tampered_public,
                progress=progress,
                **validation_kwargs,
            )

        tampered_private = copy.deepcopy(private_report)
        tampered_private["task_results"][0]["canonical_stage_results"][0][
            "round_trip_passed"
        ] = False
        tampered_private["integrity_sha256"] = (
            frontier_private_preflight_integrity_sha256(tampered_private)
        )
        with self.assertRaisesRegex(FrontierContractError, "must pass"):
            validate_frontier_private_preflight_report(
                tampered_private,
                task_set=task_set,
                oracle_set=oracle_set,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_calibration_preflight_is_bound_and_nonclaiming(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        summary = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertEqual(summary["canonical_stage_pass_count"], 60)
        self.assertEqual(summary["machine_expected_outcome_match_count"], 30)
        self.assertEqual(summary["semantic_review_required_probe_count"], 20)
        self.assertFalse(summary["independent_review_complete"])
        self.assertTrue(summary["human_review_required"])
        self.assertEqual(summary["board_admitted_count"], 0)
        self.assertFalse(summary["private_payload_published"])

    def test_independent_oracle_challenge_routes_shared_error_without_promotion(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        packets, keys, ledger, summary = compile_frontier_oracle_challenge_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        opening = validate_frontier_oracle_challenge_private_opening(
            packet_set=packets,
            key_set=keys,
            ledger=ledger,
            public_summary=summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_oracle_challenge_commitments_opened"])
        self.assertEqual(opening["challenge_packet_count"], 10)
        self.assertEqual(opening["unassigned_packet_count"], 10)
        self.assertFalse(opening["expert_solve_gate_changed"])
        self.assertFalse(opening["admission_gate_changed"])

        for packet in packets["packets"]:
            for forbidden in (
                "slot_id",
                "task_id",
                "task_commitment_nonce",
                "disease_identity_nonce",
                "program_identity_nonce",
                "oracle_commitment_nonce",
                "authoring_source_artifacts",
                "stage_expectations",
                "mutation_expectations",
            ):
                self.assertNotIn(forbidden, packet["challenge_task"])
            self.assertNotIn("stage_expectations", json.dumps(packet["challenge_task"]))
        self.assertFalse(packets["author_oracle_labels_included"])
        self.assertFalse(packets["semantic_review_material_included"])
        self.assertFalse(packets["task_identity_mapping_included"])

        packet_id = packets["packets"][0]["packet_id"]
        responses = [
            _synthetic_oracle_challenge_response(
                packets,
                keys,
                oracle_set,
                packet_id=packet_id,
                challenger_index=index,
            )
            for index in range(2)
        ]
        awaiting = compare_frontier_oracle_challenge_responses(
            responses[:1],
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            packet_id=packet_id,
            **validation_kwargs,
        )
        self.assertEqual(awaiting["route"], "awaiting_challengers")
        self.assertFalse(awaiting["author_oracle_opened"])
        self.assertIsNone(awaiting["opened_key_set_integrity_sha256"])
        self.assertIsNone(awaiting["opened_author_oracle_commitment"])
        self.assertIsNone(awaiting["component_match_count"])

        convergence = compare_frontier_oracle_challenge_responses(
            responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            packet_id=packet_id,
            **validation_kwargs,
        )
        self.assertEqual(convergence["route"], "oracle_convergence_candidate")
        self.assertEqual(convergence["component_match_count"], 30)
        self.assertEqual(convergence["component_total"], 30)
        self.assertTrue(convergence["author_oracle_opened"])
        self.assertEqual(
            convergence["opened_key_set_integrity_sha256"],
            keys["integrity_sha256"],
        )
        self.assertIsNotNone(convergence["opened_author_oracle_commitment"])
        self.assertFalse(convergence["scientific_correctness_established"])
        self.assertFalse(convergence["shared_expert_error_excluded"])
        self.assertFalse(convergence["expert_solve_gate_changed"])
        self.assertFalse(convergence["board_gate_changed"])

        abstention_responses = copy.deepcopy(responses)
        abstention_responses[1]["stage_answers"][0]["abstained"] = True
        abstention_responses[1]["overall_abstained"] = True
        abstention_responses[1]["integrity_sha256"] = (
            frontier_oracle_challenge_response_integrity_sha256(abstention_responses[1])
        )
        abstention = compare_frontier_oracle_challenge_responses(
            abstention_responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            packet_id=packet_id,
            **validation_kwargs,
        )
        self.assertEqual(
            abstention["route"],
            "adjudication_required_challenger_abstention",
        )
        self.assertFalse(abstention["author_oracle_opened"])

        disagreement_responses = copy.deepcopy(responses)
        disagreement_responses[1]["stage_answers"][0]["disposition"] = "advance"
        disagreement_responses[1]["integrity_sha256"] = (
            frontier_oracle_challenge_response_integrity_sha256(
                disagreement_responses[1]
            )
        )
        disagreement = compare_frontier_oracle_challenge_responses(
            disagreement_responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            packet_id=packet_id,
            **validation_kwargs,
        )
        self.assertEqual(
            disagreement["route"],
            "adjudication_required_challenger_disagreement",
        )
        self.assertEqual(
            disagreement["challenger_disagreement_components"],
            ["s01.disposition"],
        )
        self.assertFalse(disagreement["author_oracle_opened"])

        shared_wrong_responses = copy.deepcopy(responses)
        for response in shared_wrong_responses:
            response["stage_answers"][0]["disposition"] = "advance"
            response["integrity_sha256"] = (
                frontier_oracle_challenge_response_integrity_sha256(response)
            )
        shared_wrong = compare_frontier_oracle_challenge_responses(
            shared_wrong_responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            packet_id=packet_id,
            **validation_kwargs,
        )
        self.assertEqual(
            shared_wrong["route"],
            "adjudication_required_author_oracle_disagreement",
        )
        self.assertEqual(
            shared_wrong["author_oracle_disagreement_components"],
            ["s01.disposition"],
        )
        self.assertEqual(shared_wrong["component_match_count"], 29)
        self.assertTrue(shared_wrong["human_adjudication_required"])

        oracle_access = copy.deepcopy(responses[0])
        oracle_access["author_oracle_accessed"] = True
        oracle_access["integrity_sha256"] = (
            frontier_oracle_challenge_response_integrity_sha256(oracle_access)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_oracle_challenge_response(
                oracle_access, packet_set=packets
            )

        duplicate_challengers = copy.deepcopy(responses)
        duplicate_challengers[1]["challenger_identity_commitment"] = (
            duplicate_challengers[0]["challenger_identity_commitment"]
        )
        duplicate_challengers[1]["integrity_sha256"] = (
            frontier_oracle_challenge_response_integrity_sha256(
                duplicate_challengers[1]
            )
        )
        with self.assertRaisesRegex(FrontierContractError, "unique challengers"):
            compare_frontier_oracle_challenge_responses(
                duplicate_challengers,
                packet_set=packets,
                key_set=keys,
                task_set=task_set,
                oracle_set=oracle_set,
                packet_id=packet_id,
                **validation_kwargs,
            )

        forged_keys = copy.deepcopy(keys)
        forged_keys["keys"][0]["slot_id"] = keys["keys"][1]["slot_id"]
        forged_keys["integrity_sha256"] = (
            frontier_oracle_challenge_key_set_integrity_sha256(forged_keys)
        )
        with self.assertRaisesRegex(FrontierContractError, "rebound task identity"):
            compare_frontier_oracle_challenge_responses(
                responses,
                packet_set=packets,
                key_set=forged_keys,
                task_set=task_set,
                oracle_set=oracle_set,
                packet_id=packet_id,
                **validation_kwargs,
            )

        for schema_path, artifact in (
            (PRIVATE_ORACLE_CHALLENGE_PACKET_SCHEMA, packets),
            (PRIVATE_ORACLE_CHALLENGE_KEY_SCHEMA, keys),
            (PRIVATE_ORACLE_CHALLENGE_RESPONSE_SCHEMA, responses[0]),
            (PRIVATE_ORACLE_CHALLENGE_COMPARISON_SCHEMA, convergence),
            (PRIVATE_ORACLE_CHALLENGE_LEDGER_SCHEMA, ledger),
            (ORACLE_CHALLENGE_SUMMARY_SCHEMA, summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tampered_summary = copy.deepcopy(summary)
        tampered_summary["oracle_convergence_candidate_count"] = 1
        tampered_summary["integrity_sha256"] = (
            frontier_oracle_challenge_summary_integrity_sha256(tampered_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 0"):
            validate_frontier_oracle_challenge_summary(
                tampered_summary,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_oracle_challenge_is_ready_but_unassigned(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        summary = load_frontier_oracle_challenge_summary(
            ORACLE_CHALLENGE_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertTrue(summary["response_contract_ready"])
        self.assertTrue(summary["oracle_comparison_state_machine_ready"])
        self.assertEqual(summary["challenge_packet_count"], 10)
        self.assertEqual(summary["unassigned_packet_count"], 10)
        self.assertEqual(summary["challenger_response_count"], 0)
        self.assertFalse(summary["independent_oracle_challenge_complete"])
        self.assertFalse(summary["expert_solve_gate_changed"])

    def test_oracle_fragility_localizes_components_and_blocks_saturated_support(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        report, summary = compile_frontier_oracle_fragility_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        opening = validate_frontier_oracle_fragility_private_opening(
            private_report=report,
            public_summary=summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_oracle_fragility_commitment_opened"])
        self.assertEqual(report["planned_component_probe_count"], 300)
        self.assertEqual(report["applicable_component_probe_count"], 300)
        self.assertEqual(report["component_localization_pass_count"], 300)
        self.assertEqual(report["nonapplicable_component_probe_count"], 0)
        self.assertEqual(report["witness_saturated_stage_count"], 60)
        self.assertEqual(report["task_wide_witness_saturation_count"], 10)
        self.assertEqual(report["accessible_nonwitness_evidence_count"], 0)
        self.assertEqual(report["repeated_lineage_witness_stage_count"], 0)
        self.assertFalse(summary["oracle_support_ready_for_independent_challenge"])
        self.assertTrue(summary["human_curation_required"])
        self.assertFalse(summary["scientific_minimality_established"])
        self.assertFalse(summary["admission_gate_changed"])

        for record in report["records"]:
            self.assertEqual(len(record["component_probes"]), 5)
            for probe in record["component_probes"]:
                self.assertTrue(probe["applicable"])
                self.assertTrue(probe["isolated_target_failure"])
                scores = probe["score_results"]
                self.assertEqual(sum(not passed for passed in scores.values()), 1)

        for schema_path, artifact in (
            (PRIVATE_ORACLE_FRAGILITY_REPORT_SCHEMA, report),
            (ORACLE_FRAGILITY_SUMMARY_SCHEMA, summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        forged_report = copy.deepcopy(report)
        forged_report["records"][0]["witness_count"] += 1
        forged_report["integrity_sha256"] = (
            frontier_oracle_fragility_report_integrity_sha256(forged_report)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not replay"):
            validate_frontier_oracle_fragility_private_opening(
                private_report=forged_report,
                public_summary=summary,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_summary = copy.deepcopy(summary)
        forged_summary["task_wide_witness_saturation_count"] = 0
        forged_summary["integrity_sha256"] = (
            frontier_oracle_fragility_summary_integrity_sha256(forged_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "inconsistent"):
            validate_frontier_oracle_fragility_summary(
                forged_summary,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_oracle_fragility_exposes_support_revision_without_payload(
        self,
    ) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        summary = load_frontier_oracle_fragility_summary(
            ORACLE_FRAGILITY_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertEqual(summary["component_localization_pass_count"], 296)
        self.assertEqual(summary["applicable_component_probe_count"], 296)
        self.assertEqual(summary["nonapplicable_component_probe_count"], 4)
        self.assertEqual(summary["witness_saturated_stage_count"], 60)
        self.assertEqual(summary["task_wide_witness_saturation_count"], 10)
        self.assertEqual(summary["accessible_nonwitness_evidence_count"], 0)
        self.assertEqual(summary["repeated_lineage_witness_stage_count"], 7)
        self.assertEqual(summary["repeated_lineage_witness_id_count"], 7)
        self.assertEqual(summary["singleton_blocker_stage_count"], 60)
        self.assertTrue(summary["component_localization_ready"])
        self.assertTrue(summary["support_selectivity_review_required"])
        self.assertTrue(summary["lineage_redundancy_review_required"])
        self.assertFalse(summary["oracle_support_ready_for_independent_challenge"])
        self.assertTrue(summary["human_curation_required"])
        self.assertFalse(summary["private_payload_published"])
        self.assertFalse(summary["expert_solve_gate_changed"])
        self.assertFalse(summary["admission_gate_changed"])

    def test_support_curation_compiles_leave_one_out_workload_without_edits(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        private_fragility, public_fragility = (
            compile_frontier_oracle_fragility_artifacts(
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        packets, summary = compile_frontier_support_curation_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        opening = validate_frontier_support_curation_private_opening(
            private_packet_set=packets,
            public_summary=summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_support_curation_commitment_opened"])
        self.assertEqual(summary["planned_ablation_candidate_count"], 130)
        self.assertEqual(summary["applicable_ablation_candidate_count"], 110)
        self.assertEqual(summary["nonapplicable_ablation_candidate_count"], 20)
        self.assertEqual(summary["ablation_localization_pass_count"], 110)
        self.assertEqual(summary["protected_singleton_candidate_count"], 20)
        self.assertEqual(summary["lineage_redundancy_candidate_count"], 0)
        self.assertEqual(summary["support_selectivity_candidate_count"], 110)
        self.assertEqual(
            summary["witness_occurrence_role_counts"],
            {
                "source": 130,
                "context": 0,
                "contradiction": 0,
                "derivative": 0,
                "decision_record": 0,
            },
        )
        self.assertTrue(summary["curation_packets_ready_for_human_review"])
        self.assertFalse(summary["oracle_revision_applied"])
        self.assertFalse(summary["challenge_assignment_authorized"])

        applicable_count = 0
        protected_count = 0
        for packet in packets["packets"]:
            for stage in packet["stage_records"]:
                self.assertEqual(len(stage["candidates"]), stage["witness_count"])
                for candidate in stage["candidates"]:
                    self.assertFalse(candidate["scientific_removal_supported"])
                    self.assertFalse(candidate["automatic_oracle_edit_authorized"])
                    if candidate["ablation_applicable"]:
                        applicable_count += 1
                        self.assertTrue(candidate["isolated_witness_failure"])
                        self.assertEqual(
                            candidate["score_results"],
                            {
                                "disposition_correct": True,
                                "next_action_correct": True,
                                "risk_flags_correct": True,
                                "witness_valid": False,
                                "blocker_certificate_valid": True,
                            },
                        )
                        self.assertEqual(
                            len(candidate["counterfactual_witness_evidence_ids"]),
                            stage["witness_count"] - 1,
                        )
                    else:
                        protected_count += 1
                        self.assertEqual(
                            candidate["review_priority"], "protected_singleton"
                        )
                        self.assertIsNone(
                            candidate["counterfactual_witness_evidence_ids"]
                        )
        self.assertEqual(applicable_count, 110)
        self.assertEqual(protected_count, 20)

        for schema_path, artifact in (
            (PRIVATE_SUPPORT_CURATION_PACKET_SCHEMA, packets),
            (SUPPORT_CURATION_SUMMARY_SCHEMA, summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        forged_packets = copy.deepcopy(packets)
        forged_packets["packets"][0]["stage_records"][0]["candidates"][0][
            "evidence_role"
        ] = "context"
        forged_packets["integrity_sha256"] = (
            frontier_support_curation_packet_set_integrity_sha256(forged_packets)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not replay"):
            validate_frontier_support_curation_private_opening(
                private_packet_set=forged_packets,
                public_summary=summary,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                progress=progress,
                **validation_kwargs,
            )

        forged_summary = copy.deepcopy(summary)
        forged_summary["applicable_ablation_candidate_count"] -= 1
        forged_summary["integrity_sha256"] = (
            frontier_support_curation_summary_integrity_sha256(forged_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not close"):
            validate_frontier_support_curation_summary(
                forged_summary,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_support_curation_is_payload_free_and_unassigned(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            **validation_kwargs,
        )
        public_fragility = load_frontier_oracle_fragility_summary(
            ORACLE_FRAGILITY_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        summary = load_frontier_support_curation_summary(
            SUPPORT_CURATION_SUMMARY,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(summary["planned_ablation_candidate_count"], 130)
        self.assertEqual(summary["applicable_ablation_candidate_count"], 110)
        self.assertEqual(summary["nonapplicable_ablation_candidate_count"], 20)
        self.assertEqual(summary["ablation_localization_pass_count"], 110)
        self.assertEqual(summary["repeated_lineage_group_count"], 7)
        self.assertEqual(summary["lineage_redundancy_candidate_count"], 14)
        self.assertEqual(summary["support_selectivity_candidate_count"], 96)
        self.assertEqual(summary["protected_singleton_candidate_count"], 20)
        self.assertEqual(
            summary["witness_occurrence_role_counts"],
            {
                "source": 85,
                "context": 8,
                "contradiction": 4,
                "derivative": 7,
                "decision_record": 26,
            },
        )
        self.assertTrue(summary["curation_packets_ready_for_human_review"])
        self.assertTrue(summary["human_curation_required"])
        self.assertFalse(summary["oracle_revision_applied"])
        self.assertFalse(summary["oracle_support_ready_for_independent_challenge"])
        self.assertFalse(summary["challenge_assignment_authorized"])
        self.assertFalse(summary["private_payload_published"])

    def test_transition_audit_separates_structure_from_causal_judgment(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        private_fragility, public_fragility = (
            compile_frontier_oracle_fragility_artifacts(
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        private_curation, public_curation = compile_frontier_support_curation_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        report, summary = compile_frontier_transition_audit_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        opening = validate_frontier_transition_audit_private_opening(
            private_report=report,
            public_summary=summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_transition_audit_commitment_opened"])
        self.assertEqual(summary["canonical_transition_count"], 50)
        self.assertEqual(summary["action_changed_transition_count"], 0)
        self.assertEqual(summary["witness_changed_transition_count"], 20)
        self.assertEqual(summary["witness_changed_without_action_delta_count"], 20)
        self.assertEqual(summary["action_and_witness_stable_transition_count"], 30)
        self.assertEqual(summary["action_and_witness_changed_transition_count"], 0)
        self.assertEqual(summary["action_changed_with_access_delta_count"], 0)
        self.assertEqual(summary["witness_access_delta_alignment_pass_count"], 50)
        self.assertEqual(summary["blocker_action_delta_alignment_pass_count"], 50)
        self.assertFalse(summary["canonical_transition_coupling_coverage_ready"])
        self.assertFalse(summary["scientific_causality_established"])
        self.assertFalse(summary["oracle_revision_applied"])
        self.assertFalse(summary["challenge_assignment_authorized"])

        for record in report["records"]:
            self.assertTrue(record["witness_access_delta_aligned"])
            self.assertTrue(record["blocker_action_delta_aligned"])
            self.assertFalse(record["scientific_consistency_established"])
            self.assertFalse(record["causal_explanation_established"])
            self.assertFalse(record["automatic_oracle_edit_authorized"])

        for schema_path, artifact in (
            (PRIVATE_TRANSITION_AUDIT_REPORT_SCHEMA, report),
            (TRANSITION_AUDIT_SUMMARY_SCHEMA, summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        forged_report = copy.deepcopy(report)
        forged_report["records"][0]["causal_explanation_established"] = True
        forged_report["integrity_sha256"] = (
            frontier_transition_audit_report_integrity_sha256(forged_report)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not replay"):
            validate_frontier_transition_audit_private_opening(
                private_report=forged_report,
                public_summary=summary,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                private_support_curation_packets=private_curation,
                public_support_curation_summary=public_curation,
                progress=progress,
                **validation_kwargs,
            )

        forged_summary = copy.deepcopy(summary)
        forged_summary["action_changed_transition_count"] = 1
        forged_summary["integrity_sha256"] = (
            frontier_transition_audit_summary_integrity_sha256(forged_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not close"):
            validate_frontier_transition_audit_summary(
                forged_summary,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_transition_audit_exposes_coupling_coverage_gap(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            **validation_kwargs,
        )
        public_fragility = load_frontier_oracle_fragility_summary(
            ORACLE_FRAGILITY_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        public_curation = load_frontier_support_curation_summary(
            SUPPORT_CURATION_SUMMARY,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        summary = load_frontier_transition_audit_summary(
            TRANSITION_AUDIT_SUMMARY,
            public_support_curation_summary=public_curation,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(summary["canonical_transition_count"], 50)
        self.assertEqual(summary["action_changed_transition_count"], 20)
        self.assertEqual(summary["witness_changed_transition_count"], 20)
        self.assertEqual(summary["blocker_changed_transition_count"], 20)
        self.assertEqual(summary["accessible_evidence_changed_transition_count"], 20)
        self.assertEqual(summary["action_and_witness_changed_transition_count"], 0)
        self.assertEqual(summary["action_changed_without_witness_delta_count"], 20)
        self.assertEqual(summary["witness_changed_without_action_delta_count"], 20)
        self.assertEqual(summary["action_and_witness_stable_transition_count"], 10)
        self.assertEqual(summary["action_changed_with_access_delta_count"], 0)
        self.assertEqual(summary["action_changed_without_access_delta_count"], 20)
        self.assertEqual(summary["access_delta_without_action_change_count"], 20)
        self.assertEqual(summary["witness_access_delta_alignment_pass_count"], 50)
        self.assertEqual(summary["blocker_action_delta_alignment_pass_count"], 50)
        self.assertEqual(summary["disposition_changed_transition_count"], 4)
        self.assertEqual(summary["next_action_changed_transition_count"], 20)
        self.assertEqual(summary["risk_flags_changed_transition_count"], 8)
        self.assertFalse(summary["canonical_transition_coupling_coverage_ready"])
        self.assertTrue(summary["evidence_action_coupling_review_required"])
        self.assertTrue(summary["human_transition_review_required"])
        self.assertFalse(summary["scientific_causality_established"])
        self.assertFalse(summary["challenge_assignment_authorized"])
        self.assertFalse(summary["private_payload_published"])

    def test_coupled_augmentation_pairs_candidates_with_invariance_controls(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        semantic_packets, semantic_keys, semantic_summary = (
            compile_frontier_semantic_review_artifacts(
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        private_fragility, public_fragility = (
            compile_frontier_oracle_fragility_artifacts(
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        private_curation, public_curation = compile_frontier_support_curation_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        private_transition, public_transition = (
            compile_frontier_transition_audit_artifacts(
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                private_support_curation_packets=private_curation,
                public_support_curation_summary=public_curation,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        private_design, public_design = compile_frontier_coupled_augmentation_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=semantic_packets,
            private_semantic_keys=semantic_keys,
            public_semantic_summary=semantic_summary,
            private_transition_report=private_transition,
            public_transition_summary=public_transition,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            compiled_on="2026-08-23",
            **validation_kwargs,
        )
        opening = validate_frontier_coupled_augmentation_private_opening(
            private_packet_set=private_design,
            public_summary=public_design,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=semantic_packets,
            private_semantic_keys=semantic_keys,
            public_semantic_summary=semantic_summary,
            private_transition_report=private_transition,
            public_transition_summary=public_transition,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_coupled_augmentation_commitment_opened"])
        self.assertEqual(public_design["matched_design_unit_count"], 10)
        self.assertEqual(public_design["semantic_label_recorded_count"], 0)
        self.assertEqual(public_design["coupled_transition_admitted_count"], 0)
        self.assertTrue(public_design["coupled_augmentation_design_ready"])
        self.assertFalse(public_design["scientific_coupling_established"])
        self.assertNotIn(
            "author_expected_changed_components", json.dumps(public_design)
        )
        for record in private_design["records"]:
            self.assertTrue(record["candidate_exact_structural_delta_passed"])
            self.assertTrue(record["control_expected_outcome_matched"])
            self.assertEqual(record["semantic_label_status"], "pending_human_review")
            self.assertFalse(record["scientific_coupling_established"])
            self.assertFalse(record["coupled_transition_admitted"])

        for schema_path, artifact in (
            (PRIVATE_COUPLED_AUGMENTATION_PACKET_SCHEMA, private_design),
            (COUPLED_AUGMENTATION_SUMMARY_SCHEMA, public_design),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        placebo_packets, placebo_keys, placebo_summary = (
            compile_frontier_coupled_placebo_artifacts(
                private_coupled_packet_set=private_design,
                public_coupled_summary=public_design,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_semantic_packets=semantic_packets,
                private_semantic_keys=semantic_keys,
                public_semantic_summary=semantic_summary,
                private_transition_report=private_transition,
                public_transition_summary=public_transition,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                private_support_curation_packets=private_curation,
                public_support_curation_summary=public_curation,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        placebo_opening = validate_frontier_coupled_placebo_private_opening(
            private_packet_set=placebo_packets,
            private_key_set=placebo_keys,
            public_summary=placebo_summary,
            private_coupled_packet_set=private_design,
            public_coupled_summary=public_design,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=semantic_packets,
            private_semantic_keys=semantic_keys,
            public_semantic_summary=semantic_summary,
            private_transition_report=private_transition,
            public_transition_summary=public_transition,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(placebo_opening["private_coupled_placebo_commitments_opened"])
        self.assertEqual(placebo_summary["triplet_packet_count"], 10)
        self.assertEqual(
            placebo_summary["candidate_placebo_structural_match_count"], 10
        )
        self.assertEqual(placebo_summary["whitespace_token_count_match_count"], 10)
        self.assertEqual(placebo_summary["arm_role_balance_max_imbalance"], 1)
        self.assertTrue(placebo_summary["arm_role_balance_passed"])
        self.assertTrue(placebo_summary["structural_confound_control_ready"])
        self.assertFalse(placebo_summary["lexical_confound_control_ready"])
        self.assertEqual(placebo_summary["reviewer_response_count"], 0)
        self.assertFalse(placebo_summary["placebo_scientific_invariance_established"])
        self.assertFalse(placebo_summary["contrast_identifiability_established"])
        self.assertFalse(placebo_packets["arm_role_mapping_included"])
        self.assertFalse(placebo_packets["author_expectations_included"])
        for packet in placebo_packets["packets"]:
            self.assertNotIn("canonical_arm", packet)
            self.assertNotIn("candidate_arm", packet)
            self.assertNotIn("placebo_arm", packet)
            self.assertNotIn("expected_changed_components", json.dumps(packet))
        self.assertEqual(
            placebo_keys["arm_role_counts"],
            {
                "canonical": {"arm_a": 4, "arm_b": 3, "arm_c": 3},
                "candidate": {"arm_a": 3, "arm_b": 4, "arm_c": 3},
                "placebo": {"arm_a": 3, "arm_b": 3, "arm_c": 4},
            },
        )
        for key in placebo_keys["keys"]:
            self.assertTrue(key["candidate_placebo_structural_match_passed"])
            self.assertTrue(key["whitespace_token_count_matched"])
            self.assertTrue(key["placebo_vocabulary_policy_passed"])
            self.assertFalse(key["tokenizer_level_match_established"])
            self.assertFalse(key["placebo_scientific_invariance_established"])

        for schema_path, artifact in (
            (PRIVATE_COUPLED_PLACEBO_PACKET_SCHEMA, placebo_packets),
            (PRIVATE_COUPLED_PLACEBO_KEY_SCHEMA, placebo_keys),
            (COUPLED_PLACEBO_SUMMARY_SCHEMA, placebo_summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tokenizer_packets, tokenizer_keys, tokenizer_summary = (
            compile_frontier_tokenizer_placebo_artifacts(
                private_coupled_placebo_packets=placebo_packets,
                private_coupled_placebo_keys=placebo_keys,
                public_coupled_placebo_summary=placebo_summary,
                private_coupled_packet_set=private_design,
                public_coupled_summary=public_design,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_semantic_packets=semantic_packets,
                private_semantic_keys=semantic_keys,
                public_semantic_summary=semantic_summary,
                private_transition_report=private_transition,
                public_transition_summary=public_transition,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                private_support_curation_packets=private_curation,
                public_support_curation_summary=public_curation,
                progress=progress,
                compiled_on="2026-08-23",
                **validation_kwargs,
            )
        )
        tokenizer_opening = validate_frontier_tokenizer_placebo_private_opening(
            private_packet_set=tokenizer_packets,
            private_key_set=tokenizer_keys,
            public_summary=tokenizer_summary,
            private_coupled_placebo_packets=placebo_packets,
            private_coupled_placebo_keys=placebo_keys,
            public_coupled_placebo_summary=placebo_summary,
            private_coupled_packet_set=private_design,
            public_coupled_summary=public_design,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=semantic_packets,
            private_semantic_keys=semantic_keys,
            public_semantic_summary=semantic_summary,
            private_transition_report=private_transition,
            public_transition_summary=public_transition,
            private_fragility_report=private_fragility,
            public_fragility_summary=public_fragility,
            private_support_curation_packets=private_curation,
            public_support_curation_summary=public_curation,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(
            tokenizer_opening["private_tokenizer_placebo_commitments_opened"]
        )
        self.assertEqual(tokenizer_summary["five_arm_packet_count"], 10)
        self.assertEqual(tokenizer_summary["placebo_reveal_arm_count"], 30)
        self.assertEqual(
            tokenizer_summary["candidate_placebo_structural_match_count"], 30
        )
        self.assertEqual(
            tokenizer_summary["tokenizer_exact_token_count_match_count"], 60
        )
        self.assertEqual(tokenizer_summary["tokenizer_comparison_count"], 60)
        self.assertEqual(
            tokenizer_summary["token_byte_length_histogram_match_count"], 0
        )
        self.assertEqual(
            tokenizer_summary["token_rank_decile_histogram_match_count"], 0
        )
        self.assertEqual(tokenizer_summary["baseline_profile_l1_distance_total"], 1908)
        self.assertEqual(tokenizer_summary["optimized_profile_l1_distance_total"], 1454)
        self.assertEqual(tokenizer_summary["profile_l1_distance_reduction_total"], 454)
        self.assertEqual(
            tokenizer_summary["strict_profile_improvement_placebo_count"], 30
        )
        self.assertEqual(tokenizer_summary["profile_component_comparison_count"], 120)
        self.assertEqual(
            tokenizer_summary["profile_component_nonregression_count"], 120
        )
        self.assertEqual(
            tokenizer_summary["profile_component_strict_improvement_count"], 102
        )
        self.assertEqual(tokenizer_summary["profile_encoding_comparison_count"], 60)
        self.assertEqual(tokenizer_summary["profile_encoding_nonregression_count"], 60)
        self.assertEqual(
            tokenizer_summary["distribution_optimization_acceptance_count"], 30
        )
        self.assertEqual(
            [
                profile["encoding_name"]
                for profile in tokenizer_summary["evaluation_only_tokenizer_profiles"]
            ],
            ["r50k_base", "p50k_base"],
        )
        self.assertEqual(
            tokenizer_summary["heldout_evaluation_status"],
            "post_selection_diagnostic",
        )
        self.assertFalse(tokenizer_summary["heldout_evaluation_used_for_selection"])
        self.assertFalse(tokenizer_summary["heldout_evaluation_preregistered"])
        self.assertEqual(
            tokenizer_summary["heldout_profile_l1_distance_baseline_total"],
            2166,
        )
        self.assertEqual(
            tokenizer_summary["heldout_profile_l1_distance_optimized_total"],
            1940,
        )
        self.assertEqual(
            tokenizer_summary["heldout_profile_l1_distance_reduction_total"],
            226,
        )
        self.assertEqual(
            tokenizer_summary["heldout_profile_encoding_nonregression_count"],
            52,
        )
        self.assertEqual(
            tokenizer_summary["heldout_all_profile_nonregression_placebo_count"],
            26,
        )
        self.assertEqual(
            tokenizer_summary["heldout_profile_regression_placebo_count"], 4
        )
        self.assertTrue(
            tokenizer_summary["heldout_aggregate_profile_improvement_observed"]
        )
        self.assertFalse(
            tokenizer_summary["heldout_robust_placebo_generalization_ready"]
        )
        self.assertFalse(
            tokenizer_summary["heldout_token_count_confound_control_ready"]
        )
        self.assertEqual(tokenizer_summary["arm_role_balance_max_imbalance"], 0)
        self.assertTrue(tokenizer_summary["tokenizer_count_confound_control_ready"])
        self.assertTrue(
            tokenizer_summary["deterministic_distribution_optimization_ready"]
        )
        self.assertFalse(
            tokenizer_summary["tokenizer_distribution_confound_control_ready"]
        )
        self.assertFalse(tokenizer_summary["lexical_confound_control_ready"])
        self.assertFalse(tokenizer_packets["arm_role_mapping_included"])
        self.assertFalse(tokenizer_packets["author_expectations_included"])
        for packet in tokenizer_packets["packets"]:
            self.assertNotIn("canonical_arm", packet)
            self.assertNotIn("candidate_arm", packet)
            self.assertNotIn("placebo_transport_arm", packet)
            self.assertNotIn("expected_changed_components", json.dumps(packet))
        balanced = {
            arm_id: 2 for arm_id in ("arm_a", "arm_b", "arm_c", "arm_d", "arm_e")
        }
        self.assertEqual(
            tokenizer_keys["arm_role_counts"],
            {
                role: balanced
                for role in (
                    "canonical",
                    "candidate",
                    "placebo_transport",
                    "placebo_schema",
                    "placebo_audit",
                )
            },
        )
        for key in tokenizer_keys["keys"]:
            self.assertEqual(len(key["placebos"]), 3)
            for placebo in key["placebos"]:
                self.assertTrue(placebo["candidate_placebo_structural_match_passed"])
                self.assertTrue(placebo["whitespace_token_count_matched"])
                self.assertEqual(placebo["exact_token_count_match_count"], 2)
                self.assertEqual(
                    placebo["candidate_token_counts"],
                    placebo["placebo_token_counts"],
                )
                self.assertEqual(placebo["token_byte_length_histogram_match_count"], 0)
                self.assertEqual(placebo["token_rank_decile_histogram_match_count"], 0)
                self.assertGreater(
                    placebo["baseline_profile_l1_distance"],
                    placebo["optimized_profile_l1_distance"],
                )
                self.assertEqual(
                    placebo["profile_l1_distance_reduction"],
                    placebo["baseline_profile_l1_distance"]
                    - placebo["optimized_profile_l1_distance"],
                )
                self.assertEqual(placebo["profile_component_comparison_count"], 4)
                self.assertEqual(placebo["profile_component_nonregression_count"], 4)
                self.assertGreaterEqual(
                    placebo["profile_component_strict_improvement_count"], 1
                )
                self.assertEqual(placebo["profile_encoding_comparison_count"], 2)
                self.assertEqual(placebo["profile_encoding_nonregression_count"], 2)
                for encoding_name, baseline_components in placebo[
                    "profile_component_distances"
                ]["baseline"].items():
                    optimized_components = placebo["profile_component_distances"][
                        "optimized"
                    ][encoding_name]
                    for component_name in (
                        "token_byte_length_l1_distance",
                        "token_rank_decile_l1_distance",
                        "combined_l1_distance",
                    ):
                        self.assertLessEqual(
                            optimized_components[component_name],
                            baseline_components[component_name],
                        )
                self.assertTrue(placebo["strict_profile_improvement_passed"])
                self.assertTrue(placebo["distribution_optimization_acceptance_passed"])
                self.assertEqual(
                    placebo["heldout_profile_l1_distance_reduction"],
                    placebo["heldout_profile_l1_distance_baseline"]
                    - placebo["heldout_profile_l1_distance_optimized"],
                )
                self.assertEqual(
                    placebo["heldout_profile_encoding_comparison_count"], 2
                )
                self.assertEqual(
                    placebo["heldout_profile_component_comparison_count"], 4
                )
                self.assertEqual(placebo["heldout_token_count_gap_comparison_count"], 2)
                self.assertEqual(
                    placebo["heldout_all_profile_nonregression_passed"],
                    placebo["heldout_profile_encoding_nonregression_count"] == 2,
                )
                self.assertEqual(
                    placebo["heldout_all_profile_strict_improvement_passed"],
                    placebo["heldout_profile_encoding_strict_improvement_count"] == 2,
                )
                self.assertTrue(placebo["tokenizer_count_match_established"])
                self.assertFalse(placebo["tokenizer_distribution_match_established"])
                self.assertFalse(placebo["placebo_scientific_invariance_established"])

        for schema_path, artifact in (
            (PRIVATE_TOKENIZER_PLACEBO_PACKET_SCHEMA, tokenizer_packets),
            (PRIVATE_TOKENIZER_PLACEBO_KEY_SCHEMA, tokenizer_keys),
            (TOKENIZER_PLACEBO_SUMMARY_SCHEMA, tokenizer_summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        forged_tokenizer_summary = copy.deepcopy(tokenizer_summary)
        forged_tokenizer_summary["tokenizer_distribution_confound_control_ready"] = True
        forged_tokenizer_summary["integrity_sha256"] = (
            frontier_tokenizer_placebo_summary_integrity_sha256(
                forged_tokenizer_summary
            )
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_tokenizer_placebo_summary(
                forged_tokenizer_summary,
                public_coupled_placebo_summary=placebo_summary,
                public_coupled_summary=public_design,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_optimization_summary = copy.deepcopy(tokenizer_summary)
        forged_optimization_summary["profile_component_nonregression_count"] = 119
        forged_optimization_summary["integrity_sha256"] = (
            frontier_tokenizer_placebo_summary_integrity_sha256(
                forged_optimization_summary
            )
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 120"):
            validate_frontier_tokenizer_placebo_summary(
                forged_optimization_summary,
                public_coupled_placebo_summary=placebo_summary,
                public_coupled_summary=public_design,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_heldout_summary = copy.deepcopy(tokenizer_summary)
        forged_heldout_summary["heldout_robust_placebo_generalization_ready"] = True
        forged_heldout_summary["integrity_sha256"] = (
            frontier_tokenizer_placebo_summary_integrity_sha256(forged_heldout_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_tokenizer_placebo_summary(
                forged_heldout_summary,
                public_coupled_placebo_summary=placebo_summary,
                public_coupled_summary=public_design,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_selection_summary = copy.deepcopy(tokenizer_summary)
        forged_selection_summary["heldout_evaluation_used_for_selection"] = True
        forged_selection_summary["integrity_sha256"] = (
            frontier_tokenizer_placebo_summary_integrity_sha256(
                forged_selection_summary
            )
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_tokenizer_placebo_summary(
                forged_selection_summary,
                public_coupled_placebo_summary=placebo_summary,
                public_coupled_summary=public_design,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_placebo_summary = copy.deepcopy(placebo_summary)
        forged_placebo_summary["lexical_confound_control_ready"] = True
        forged_placebo_summary["integrity_sha256"] = (
            frontier_coupled_placebo_summary_integrity_sha256(forged_placebo_summary)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_coupled_placebo_summary(
                forged_placebo_summary,
                public_coupled_summary=public_design,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

        forged_private = copy.deepcopy(private_design)
        forged_private["records"][0]["scientific_coupling_established"] = True
        forged_private["integrity_sha256"] = (
            frontier_coupled_augmentation_packet_set_integrity_sha256(forged_private)
        )
        with self.assertRaisesRegex(FrontierContractError, "do not replay"):
            validate_frontier_coupled_augmentation_private_opening(
                private_packet_set=forged_private,
                public_summary=public_design,
                task_set=task_set,
                oracle_set=oracle_set,
                private_preflight=private_preflight,
                public_preflight=public_preflight,
                private_semantic_packets=semantic_packets,
                private_semantic_keys=semantic_keys,
                public_semantic_summary=semantic_summary,
                private_transition_report=private_transition,
                public_transition_summary=public_transition,
                private_fragility_report=private_fragility,
                public_fragility_summary=public_fragility,
                private_support_curation_packets=private_curation,
                public_support_curation_summary=public_curation,
                progress=progress,
                **validation_kwargs,
            )

        forged_public = copy.deepcopy(public_design)
        forged_public["semantic_label_recorded_count"] = 1
        forged_public["integrity_sha256"] = (
            frontier_coupled_augmentation_summary_integrity_sha256(forged_public)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 0"):
            validate_frontier_coupled_augmentation_summary(
                forged_public,
                public_semantic_summary=semantic_summary,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_coupled_augmentation_is_payload_free_and_unadmitted(
        self,
    ) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            **validation_kwargs,
        )
        public_semantic = load_frontier_semantic_review_summary(
            SEMANTIC_REVIEW_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        public_fragility = load_frontier_oracle_fragility_summary(
            ORACLE_FRAGILITY_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        public_curation = load_frontier_support_curation_summary(
            SUPPORT_CURATION_SUMMARY,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        public_transition = load_frontier_transition_audit_summary(
            TRANSITION_AUDIT_SUMMARY,
            public_support_curation_summary=public_curation,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        summary = load_frontier_coupled_augmentation_summary(
            COUPLED_AUGMENTATION_SUMMARY,
            public_semantic_summary=public_semantic,
            public_transition_summary=public_transition,
            public_support_curation_summary=public_curation,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(summary["matched_design_unit_count"], 10)
        self.assertEqual(summary["action_witness_coupling_candidate_count"], 10)
        self.assertEqual(summary["semantic_label_recorded_count"], 0)
        self.assertEqual(summary["coupled_transition_admitted_count"], 0)
        self.assertTrue(summary["coupled_augmentation_design_ready"])
        self.assertFalse(summary["canonical_transition_coupling_coverage_ready"])
        self.assertTrue(summary["evidence_action_coupling_review_required"])
        self.assertFalse(summary["scientific_coupling_established"])
        self.assertFalse(summary["private_payload_published"])

        placebo = load_frontier_coupled_placebo_summary(
            COUPLED_PLACEBO_SUMMARY,
            public_coupled_summary=summary,
            public_semantic_summary=public_semantic,
            public_transition_summary=public_transition,
            public_support_curation_summary=public_curation,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(placebo["triplet_packet_count"], 10)
        self.assertEqual(placebo["candidate_placebo_structural_match_count"], 10)
        self.assertEqual(placebo["whitespace_token_count_match_count"], 10)
        self.assertTrue(placebo["arm_role_balance_passed"])
        self.assertTrue(placebo["three_arm_design_ready"])
        self.assertTrue(placebo["structural_confound_control_ready"])
        self.assertFalse(placebo["lexical_confound_control_ready"])
        self.assertEqual(placebo["reviewer_response_count"], 0)
        self.assertFalse(placebo["placebo_scientific_invariance_established"])
        self.assertFalse(placebo["contrast_identifiability_established"])
        self.assertFalse(placebo["private_payload_published"])

        tokenizer_placebo = load_frontier_tokenizer_placebo_summary(
            TOKENIZER_PLACEBO_SUMMARY
        )
        tokenizer_placebo = validate_frontier_tokenizer_placebo_summary(
            tokenizer_placebo,
            public_coupled_placebo_summary=placebo,
            public_coupled_summary=summary,
            public_semantic_summary=public_semantic,
            public_transition_summary=public_transition,
            public_support_curation_summary=public_curation,
            public_fragility_summary=public_fragility,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(tokenizer_placebo["five_arm_packet_count"], 10)
        self.assertEqual(
            tokenizer_placebo["tokenizer_exact_token_count_match_count"], 60
        )
        self.assertTrue(tokenizer_placebo["tokenizer_count_confound_control_ready"])
        self.assertEqual(tokenizer_placebo["baseline_profile_l1_distance_total"], 1908)
        self.assertEqual(tokenizer_placebo["optimized_profile_l1_distance_total"], 1454)
        self.assertEqual(tokenizer_placebo["profile_l1_distance_reduction_total"], 454)
        self.assertEqual(
            tokenizer_placebo["profile_component_nonregression_count"], 120
        )
        self.assertEqual(tokenizer_placebo["profile_component_comparison_count"], 120)
        self.assertTrue(
            tokenizer_placebo["deterministic_distribution_optimization_ready"]
        )
        self.assertEqual(
            tokenizer_placebo["heldout_profile_l1_distance_baseline_total"],
            2166,
        )
        self.assertEqual(
            tokenizer_placebo["heldout_profile_l1_distance_optimized_total"],
            1940,
        )
        self.assertEqual(
            tokenizer_placebo["heldout_profile_regression_placebo_count"], 4
        )
        self.assertTrue(
            tokenizer_placebo["heldout_aggregate_profile_improvement_observed"]
        )
        self.assertFalse(
            tokenizer_placebo["heldout_robust_placebo_generalization_ready"]
        )
        self.assertFalse(
            tokenizer_placebo["tokenizer_distribution_confound_control_ready"]
        )
        self.assertFalse(tokenizer_placebo["lexical_confound_control_ready"])
        self.assertEqual(tokenizer_placebo["reviewer_response_count"], 0)
        self.assertFalse(tokenizer_placebo["private_payload_published"])

        independent_protocol = load_independent_tokenizer_protocol(
            TOKENIZER_INDEPENDENT_PROTOCOL
        )
        independent_summary = load_independent_tokenizer_summary(
            TOKENIZER_INDEPENDENT_SUMMARY
        )
        independent_summary = validate_independent_tokenizer_summary(
            independent_summary,
            protocol=independent_protocol,
            parent_summary=tokenizer_placebo,
        )
        self.assertEqual(
            independent_summary["profile_l1_distance_reduction_total"], 188
        )
        self.assertEqual(
            independent_summary["profile_encoding_nonregression_count"], 51
        )
        self.assertEqual(independent_summary["profile_regression_placebo_count"], 7)
        self.assertFalse(
            independent_summary[
                "robust_independent_family_profile_generalization_ready"
            ]
        )
        self.assertFalse(independent_summary["independent_family_control_ready"])
        self.assertFalse(independent_summary["private_payload_published"])
        serialized = json.dumps(independent_summary)
        self.assertNotIn('"records"', serialized)
        self.assertNotIn('"packet_id"', serialized)
        self.assertNotIn('"trial_zero_summary_commitment"', serialized)

        forged_independent_ready = copy.deepcopy(independent_summary)
        forged_independent_ready[
            "robust_independent_family_profile_generalization_ready"
        ] = True
        forged_independent_ready["integrity_sha256"] = (
            independent_tokenizer_summary_integrity_sha256(forged_independent_ready)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_independent_tokenizer_summary(
                forged_independent_ready,
                protocol=independent_protocol,
                parent_summary=tokenizer_placebo,
            )

        forged_independent_count = copy.deepcopy(independent_summary)
        forged_independent_count["profile_encoding_nonregression_count"] = 60
        forged_independent_count["integrity_sha256"] = (
            independent_tokenizer_summary_integrity_sha256(forged_independent_count)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 51"):
            validate_independent_tokenizer_summary(
                forged_independent_count,
                protocol=independent_protocol,
                parent_summary=tokenizer_placebo,
            )

    @unittest.skipUnless(
        PRIVATE_TOKENIZER_PLACEBO_PACKETS.is_file()
        and PRIVATE_TOKENIZER_PLACEBO_KEYS.is_file()
        and PRIVATE_TOKENIZER_INDEPENDENT_REPORT.is_file()
        and TOKENIZER_INDEPENDENT_ASSET_ROOT.is_dir(),
        "private independent-tokenizer fixtures are not present",
    )
    def test_private_independent_tokenizer_evaluation_replays_locally(self) -> None:
        independent_protocol = load_independent_tokenizer_protocol(
            TOKENIZER_INDEPENDENT_PROTOCOL
        )
        parent_summary = _tokenizer_placebo_summary()
        independent_summary = _tokenizer_independent_summary()
        private_packets = json.loads(
            PRIVATE_TOKENIZER_PLACEBO_PACKETS.read_text(encoding="utf-8")
        )
        private_keys = json.loads(
            PRIVATE_TOKENIZER_PLACEBO_KEYS.read_text(encoding="utf-8")
        )
        private_report = json.loads(
            PRIVATE_TOKENIZER_INDEPENDENT_REPORT.read_text(encoding="utf-8")
        )
        opening = validate_independent_tokenizer_private_opening(
            private_report=private_report,
            summary=independent_summary,
            protocol=independent_protocol,
            private_packet_set=private_packets,
            private_key_set=private_keys,
            parent_summary=parent_summary,
            asset_root=TOKENIZER_INDEPENDENT_ASSET_ROOT,
        )
        self.assertTrue(opening["private_independent_tokenizer_commitment_opened"])
        self.assertEqual(
            independent_summary["profile_l1_distance_reduction_total"], 188
        )
        self.assertEqual(independent_summary["profile_regression_placebo_count"], 7)
        self.assertFalse(independent_summary["independent_family_control_ready"])

        schema = json.loads(
            PRIVATE_TOKENIZER_INDEPENDENT_REPORT_SCHEMA.read_text(encoding="utf-8")
        )
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(private_report)

    def test_semantic_review_packets_are_blinded_and_structurally_exact(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        packets, keys, summary = compile_frontier_semantic_review_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-22",
            **validation_kwargs,
        )
        opening = validate_frontier_semantic_review_private_opening(
            packet_set=packets,
            key_set=keys,
            public_summary=summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_semantic_review_commitments_opened"])
        self.assertEqual(opening["machine_compiled_packet_count"], 20)
        self.assertEqual(opening["exact_structural_delta_count"], 20)
        self.assertEqual(opening["reviewer_assignment_count"], 0)
        self.assertEqual(opening["reviewer_response_count"], 0)
        self.assertEqual(opening["consensus_label_count"], 0)
        self.assertTrue(opening["human_review_required"])

        for packet in packets["packets"]:
            self.assertNotIn("canonical_arm", packet)
            self.assertNotIn("mutated_arm", packet)
            self.assertNotIn("expected_changed_components", packet)
            self.assertNotIn("stage_expectations", json.dumps(packet))
        self.assertFalse(packets["canonical_arm_mapping_included"])
        self.assertFalse(packets["oracle_labels_included"])
        self.assertTrue(
            all(
                key["structural_delta_certificate"]["exact_delta_passed"]
                for key in keys["keys"]
            )
        )

        for schema_path, artifact in (
            (PRIVATE_SEMANTIC_PACKET_SCHEMA, packets),
            (PRIVATE_SEMANTIC_KEY_SCHEMA, keys),
            (SEMANTIC_REVIEW_SUMMARY_SCHEMA, summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tampered = copy.deepcopy(summary)
        tampered["reviewer_response_count"] = 1
        tampered["integrity_sha256"] = frontier_semantic_summary_integrity_sha256(
            tampered
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 0"):
            validate_frontier_semantic_review_summary(
                tampered,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_semantic_review_readiness_is_payload_free(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        summary = load_frontier_semantic_review_summary(
            SEMANTIC_REVIEW_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertEqual(summary["semantic_probe_count"], 20)
        self.assertEqual(summary["exact_structural_delta_count"], 20)
        self.assertEqual(summary["reviewer_response_count"], 0)
        self.assertFalse(summary["independent_review_complete"])
        self.assertFalse(summary["private_payload_published"])

    def test_semantic_workflow_routes_synthetic_disagreement_without_live_claims(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        packets, keys, semantic_summary = compile_frontier_semantic_review_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-22",
            **validation_kwargs,
        )
        ledger, workflow_summary = build_frontier_semantic_workflow_artifacts(
            packet_set=packets,
            key_set=keys,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-22",
            **validation_kwargs,
        )
        opening = validate_frontier_semantic_workflow_private_opening(
            ledger=ledger,
            public_summary=workflow_summary,
            packet_set=packets,
            key_set=keys,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_semantic_workflow_commitment_opened"])
        self.assertEqual(opening["unassigned_packet_count"], 20)
        self.assertEqual(opening["reviewer_response_count"], 0)
        self.assertEqual(opening["consensus_candidate_count"], 0)

        packet_id = next(
            packet["packet_id"]
            for packet in packets["packets"]
            if packet["probe_kind"] == "bounded_evidence_reveal"
        )
        responses = [
            _synthetic_semantic_response(
                packets, packet_id=packet_id, reviewer_index=index
            )
            for index in range(3)
        ]
        observed = frontier_semantic_observed_pair_deltas(responses[0])
        self.assertEqual(observed["changed_components"], ["witness"])
        self.assertTrue(
            all(
                not stage["changed_components"]
                for stage in observed["stage_deltas"][:3]
            )
        )
        self.assertTrue(
            all(
                stage["changed_components"] == ["witness"]
                for stage in observed["stage_deltas"][3:]
            )
        )
        awaiting = triage_frontier_semantic_responses(
            responses[:2], packet_set=packets, packet_id=packet_id
        )
        self.assertEqual(awaiting["route"], "awaiting_responses")

        consensus = triage_frontier_semantic_responses(
            responses, packet_set=packets, packet_id=packet_id
        )
        self.assertEqual(consensus["route"], "consensus_candidate")
        self.assertIsNotNone(consensus["consensus_candidate_commitment"])
        self.assertFalse(consensus["board_gate_changed"])

        false_change = copy.deepcopy(responses[0])
        for arm_id in ("arm_a", "arm_b"):
            for answer in false_change["arm_answers"][arm_id]:
                answer["witness_evidence_ids"] = []
        false_change["integrity_sha256"] = frontier_semantic_response_integrity_sha256(
            false_change
        )
        with self.assertRaisesRegex(
            FrontierContractError,
            "pair assessment does not match observed arm deltas",
        ):
            validate_frontier_semantic_reviewer_response(
                false_change,
                packet_set=packets,
            )

        hidden_change = copy.deepcopy(responses[0])
        hidden_change["pair_assessment"].update(
            {"semantic_change_detected": False, "changed_components": []}
        )
        hidden_change["integrity_sha256"] = frontier_semantic_response_integrity_sha256(
            hidden_change
        )
        with self.assertRaisesRegex(
            FrontierContractError,
            "pair assessment does not match observed arm deltas",
        ):
            validate_frontier_semantic_reviewer_response(
                hidden_change,
                packet_set=packets,
            )

        future_leakage = copy.deepcopy(responses[0])
        future_leakage["arm_answers"]["arm_b"][0]["blocker_codes"].append(
            "future_evidence_used_before_access"
        )
        _sync_semantic_pair_assessment(future_leakage)
        with self.assertRaisesRegex(
            FrontierContractError,
            "changed before evidence access",
        ):
            validate_frontier_semantic_reviewer_response(
                future_leakage,
                packet_set=packets,
            )

        identity_packet_id = next(
            packet["packet_id"]
            for packet in packets["packets"]
            if packet["probe_kind"] == "identity_rebind"
        )
        wrong_identity_reason = _synthetic_semantic_response(
            packets,
            packet_id=identity_packet_id,
            reviewer_index=99,
        )
        wrong_identity_reason["pair_assessment"]["reason_codes"] = [
            "evidence_sufficiency_change"
        ]
        wrong_identity_reason["integrity_sha256"] = (
            frontier_semantic_response_integrity_sha256(wrong_identity_reason)
        )
        with self.assertRaisesRegex(
            FrontierContractError,
            "requires identity_discontinuity",
        ):
            validate_frontier_semantic_reviewer_response(
                wrong_identity_reason,
                packet_set=packets,
            )

        def mutate_action(response: dict) -> None:
            response["arm_answers"]["arm_a"][3]["disposition"] = "advance"
            _sync_semantic_pair_assessment(response)

        def mutate_support(response: dict) -> None:
            response["arm_answers"]["arm_a"][3]["witness_evidence_ids"] = []
            _sync_semantic_pair_assessment(response)

        def mutate_change_reason(response: dict) -> None:
            response["pair_assessment"]["reason_codes"] = ["uncertainty_change"]

        def mutate_abstention(response: dict) -> None:
            response["pair_assessment"].update(
                {
                    "abstained": True,
                    "reason_codes": ["insufficient_information"],
                }
            )

        route_mutations = (
            (
                "adjudication_required_action_disagreement",
                mutate_action,
            ),
            (
                "adjudication_required_support_disagreement",
                mutate_support,
            ),
            (
                "adjudication_required_change_disagreement",
                mutate_change_reason,
            ),
            (
                "adjudication_required_abstention",
                mutate_abstention,
            ),
        )
        triage_schema = json.loads(
            PRIVATE_SEMANTIC_TRIAGE_SCHEMA.read_text(encoding="utf-8")
        )
        for expected_route, mutate in route_mutations:
            with self.subTest(route=expected_route):
                routed_responses = copy.deepcopy(responses)
                mutate(routed_responses[2])
                routed_responses[2]["integrity_sha256"] = (
                    frontier_semantic_response_integrity_sha256(routed_responses[2])
                )
                triage = triage_frontier_semantic_responses(
                    routed_responses,
                    packet_set=packets,
                    packet_id=packet_id,
                )
                self.assertEqual(triage["route"], expected_route)
                self.assertTrue(triage["human_adjudication_required"])
                Draft202012Validator(triage_schema).validate(triage)

        for schema_path, artifact in (
            (PRIVATE_SEMANTIC_RESPONSE_SCHEMA, responses[0]),
            (PRIVATE_SEMANTIC_TRIAGE_SCHEMA, consensus),
            (PRIVATE_SEMANTIC_LEDGER_SCHEMA, ledger),
            (SEMANTIC_WORKFLOW_SUMMARY_SCHEMA, workflow_summary),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        tampered = copy.deepcopy(workflow_summary)
        tampered["consensus_candidate_count"] = 1
        tampered["integrity_sha256"] = (
            frontier_semantic_workflow_summary_integrity_sha256(tampered)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 0"):
            validate_frontier_semantic_workflow_summary(
                tampered,
                semantic_summary=semantic_summary,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_semantic_workflow_is_ready_but_unassigned(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        semantic_summary = load_frontier_semantic_review_summary(
            SEMANTIC_REVIEW_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        summary = load_frontier_semantic_workflow_summary(
            SEMANTIC_WORKFLOW_SUMMARY,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            root=ROOT,
            frontier_protocol=protocol,
            board_protocol=board_protocol,
            board_slots=slots,
        )
        self.assertTrue(summary["response_contract_ready"])
        self.assertTrue(summary["triage_state_machine_ready"])
        self.assertTrue(summary["pairwise_causal_consistency_ready"])
        self.assertTrue(summary["pre_access_invariance_ready"])
        self.assertEqual(summary["unassigned_packet_count"], 20)
        self.assertEqual(summary["reviewer_response_count"], 0)
        self.assertFalse(summary["independent_review_complete"])

    def test_semantic_resolution_replays_consensus_without_gate_promotion(
        self,
    ) -> None:
        protocol, board_protocol, slots = _board()
        task_set, oracle_set, progress = _synthetic_private_calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        private_preflight = run_frontier_calibration_preflight(
            task_set=task_set,
            oracle_set=oracle_set,
            progress=progress,
            run_on="2026-08-21",
            **validation_kwargs,
        )
        public_preflight = build_frontier_calibration_preflight_summary(
            private_report=private_preflight,
            progress=progress,
            **validation_kwargs,
        )
        packets, keys, semantic_summary = compile_frontier_semantic_review_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-22",
            **validation_kwargs,
        )
        workflow_ledger, workflow_summary = build_frontier_semantic_workflow_artifacts(
            packet_set=packets,
            key_set=keys,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            compiled_on="2026-08-22",
            **validation_kwargs,
        )
        resolution_ledger, resolution_summary = (
            build_frontier_semantic_resolution_artifacts(
                workflow_ledger=workflow_ledger,
                workflow_summary=workflow_summary,
                packet_set=packets,
                key_set=keys,
                semantic_summary=semantic_summary,
                public_preflight=public_preflight,
                progress=progress,
                compiled_on="2026-08-22",
                **validation_kwargs,
            )
        )
        opening = validate_frontier_semantic_resolution_private_opening(
            ledger=resolution_ledger,
            public_summary=resolution_summary,
            workflow_ledger=workflow_ledger,
            workflow_summary=workflow_summary,
            packet_set=packets,
            key_set=keys,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertTrue(opening["private_semantic_resolution_commitment_opened"])
        self.assertEqual(opening["awaiting_reviewer_responses_count"], 20)
        self.assertEqual(opening["unblinded_packet_count"], 0)
        self.assertEqual(opening["canonical_replay_count"], 0)
        self.assertEqual(opening["resolution_receipt_count"], 0)

        for schema_path, artifact in (
            (PRIVATE_SEMANTIC_RESOLUTION_LEDGER_SCHEMA, resolution_ledger),
            (SEMANTIC_RESOLUTION_SUMMARY_SCHEMA, resolution_summary),
        ):
            Draft202012Validator(
                json.loads(schema_path.read_text(encoding="utf-8")),
                format_checker=FormatChecker(),
            ).validate(artifact)

        packet_id = next(
            packet["packet_id"]
            for packet in packets["packets"]
            if packet["probe_kind"] == "identity_rebind"
        )
        responses = _oracle_aligned_semantic_responses(
            packets,
            keys,
            oracle_set,
            packet_id=packet_id,
        )
        triage = triage_frontier_semantic_responses(
            responses,
            packet_set=packets,
            packet_id=packet_id,
        )
        replay = replay_frontier_semantic_consensus(
            triage=triage,
            responses=responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            **validation_kwargs,
        )
        self.assertTrue(replay["canonical_replay_passed"])
        self.assertEqual(replay["passed_component_count"], 30)
        self.assertEqual(
            replay["route"],
            "canonical_replay_pass_resolution_receipt_pending",
        )
        self.assertTrue(replay["resolution_receipt_required"])
        self.assertFalse(replay["board_gate_changed"])
        Draft202012Validator(
            json.loads(PRIVATE_SEMANTIC_REPLAY_SCHEMA.read_text(encoding="utf-8"))
        ).validate(replay)

        receipt = build_frontier_semantic_resolution_receipt(
            replay=replay,
            decision="accept_consensus",
            adjudicator_identity_commitment=_nonce("resolution-adjudicator"),
            adjudicator_affiliation_commitment=_nonce("resolution-affiliation"),
            conflict_of_interest_declared=False,
            independence_attested=True,
            completed_on="2026-08-22",
            rationale_codes=[
                "canonical_replay_exact",
                "reviewer_consensus_supported",
            ],
        )
        validate_frontier_semantic_resolution_receipt(receipt, replay=replay)
        self.assertTrue(receipt["admission_review_required"])
        self.assertFalse(receipt["board_gate_changed"])
        Draft202012Validator(
            json.loads(PRIVATE_SEMANTIC_RECEIPT_SCHEMA.read_text(encoding="utf-8")),
            format_checker=FormatChecker(),
        ).validate(receipt)

        awaiting = triage_frontier_semantic_responses(
            responses[:2],
            packet_set=packets,
            packet_id=packet_id,
        )
        with self.assertRaisesRegex(
            FrontierContractError,
            "three-response consensus candidate",
        ):
            replay_frontier_semantic_consensus(
                triage=awaiting,
                responses=responses[:2],
                packet_set=packets,
                key_set=keys,
                task_set=task_set,
                oracle_set=oracle_set,
                **validation_kwargs,
            )

        forged_keys = copy.deepcopy(keys)
        forged_key = next(
            item for item in forged_keys["keys"] if item["packet_id"] == packet_id
        )
        forged_key["canonical_arm"], forged_key["mutated_arm"] = (
            forged_key["mutated_arm"],
            forged_key["canonical_arm"],
        )
        forged_keys["integrity_sha256"] = frontier_semantic_key_set_integrity_sha256(
            forged_keys
        )
        with self.assertRaisesRegex(
            FrontierContractError,
            "canonical arm does not open canonical task",
        ):
            replay_frontier_semantic_consensus(
                triage=triage,
                responses=responses,
                packet_set=packets,
                key_set=forged_keys,
                task_set=task_set,
                oracle_set=oracle_set,
                **validation_kwargs,
            )

        canonical_arm = next(
            item for item in keys["keys"] if item["packet_id"] == packet_id
        )["canonical_arm"]
        failed_responses = copy.deepcopy(responses)
        for response in failed_responses:
            for answer in response["arm_answers"][canonical_arm]:
                flags = answer["risk_flags"]
                if "contradiction" in flags:
                    flags.remove("contradiction")
                else:
                    flags.append("contradiction")
            _sync_semantic_pair_assessment(response)
        failed_triage = triage_frontier_semantic_responses(
            failed_responses,
            packet_set=packets,
            packet_id=packet_id,
        )
        failed_replay = replay_frontier_semantic_consensus(
            triage=failed_triage,
            responses=failed_responses,
            packet_set=packets,
            key_set=keys,
            task_set=task_set,
            oracle_set=oracle_set,
            **validation_kwargs,
        )
        self.assertFalse(failed_replay["canonical_replay_passed"])
        self.assertEqual(failed_replay["passed_component_count"], 24)
        self.assertEqual(
            failed_replay["route"],
            "adjudication_required_canonical_replay_failure",
        )
        self.assertFalse(failed_replay["board_gate_changed"])
        with self.assertRaisesRegex(
            FrontierContractError,
            "failed canonical replay cannot accept consensus",
        ):
            build_frontier_semantic_resolution_receipt(
                replay=failed_replay,
                decision="accept_consensus",
                adjudicator_identity_commitment=_nonce("failed-adjudicator"),
                adjudicator_affiliation_commitment=_nonce("failed-affiliation"),
                conflict_of_interest_declared=False,
                independence_attested=True,
                completed_on="2026-08-22",
                rationale_codes=["canonical_replay_failure"],
            )

        tampered = copy.deepcopy(resolution_summary)
        tampered["unblinded_packet_count"] = 1
        tampered["integrity_sha256"] = (
            frontier_semantic_resolution_summary_integrity_sha256(tampered)
        )
        with self.assertRaisesRegex(FrontierContractError, "must remain 0"):
            validate_frontier_semantic_resolution_summary(
                tampered,
                workflow_summary=workflow_summary,
                semantic_summary=semantic_summary,
                public_preflight=public_preflight,
                progress=progress,
                **validation_kwargs,
            )

    def test_public_semantic_resolution_is_ready_but_sealed(self) -> None:
        protocol, board_protocol, slots, progress = _calibration()
        validation_kwargs = {
            "root": ROOT,
            "frontier_protocol": protocol,
            "board_protocol": board_protocol,
            "board_slots": slots,
        }
        public_preflight = load_frontier_public_preflight_summary(
            PREFLIGHT_SUMMARY,
            progress=progress,
            **validation_kwargs,
        )
        semantic_summary = load_frontier_semantic_review_summary(
            SEMANTIC_REVIEW_SUMMARY,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        workflow_summary = load_frontier_semantic_workflow_summary(
            SEMANTIC_WORKFLOW_SUMMARY,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        summary = load_frontier_semantic_resolution_summary(
            SEMANTIC_RESOLUTION_SUMMARY,
            workflow_summary=workflow_summary,
            semantic_summary=semantic_summary,
            public_preflight=public_preflight,
            progress=progress,
            **validation_kwargs,
        )
        self.assertEqual(summary["awaiting_reviewer_responses_count"], 20)
        self.assertTrue(summary["unblinding_contract_ready"])
        self.assertTrue(summary["canonical_replay_contract_ready"])
        self.assertTrue(summary["resolution_receipt_contract_ready"])
        self.assertEqual(summary["unblinded_packet_count"], 0)
        self.assertEqual(summary["canonical_replay_count"], 0)
        self.assertEqual(summary["resolution_receipt_count"], 0)
        self.assertFalse(summary["private_payload_published"])

    def test_board_protocol_rejects_model_informed_selection(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        board_protocol = copy.deepcopy(_board_protocol())
        board_protocol["contamination_policy"]["model_failure_filtering_prohibited"] = (
            False
        )
        _rehash_board_protocol(board_protocol)
        with self.assertRaisesRegex(FrontierContractError, "must remain true"):
            validate_frontier_board_protocol(
                board_protocol,
                root=ROOT,
                frontier_protocol=protocol,
            )

    def test_board_slots_reject_rebinding_and_premature_progress(self) -> None:
        protocol, board_protocol, _ = _board()
        mutations = (
            ("partition", "partition", "sealed_evaluation"),
            ("task commitment", "task_commitment", "0" * 64),
            ("board admission", "board_admitted", True),
        )
        for name, field_name, value in mutations:
            with self.subTest(mutation=name):
                slots = copy.deepcopy(_board_slots())
                slots["slots"][0][field_name] = value
                _rehash_board_slots(slots)
                with self.assertRaises(FrontierContractError):
                    validate_frontier_board_slot_manifest(
                        slots,
                        root=ROOT,
                        frontier_protocol=protocol,
                        board_protocol=board_protocol,
                    )

    def test_board_slots_reject_baseline_exposure_before_freeze(self) -> None:
        protocol, board_protocol, _ = _board()
        slots = copy.deepcopy(_board_slots())
        slots["baseline_model_runs_started"] = True
        _rehash_board_slots(slots)
        with self.assertRaisesRegex(FrontierContractError, "must remain false"):
            validate_frontier_board_slot_manifest(
                slots,
                root=ROOT,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )

    def test_stage_component_scorer_cannot_hide_factorized_error(self) -> None:
        _, _, _, oracles, _ = _development()
        expectation = oracles["oracles"][0]["stage_expectations"][0]
        exact = score_frontier_stage_components(
            expectation,
            action=FrontierAction(
                disposition="hold",
                next_action="retrieve",
                risk_flags=("provenance",),
            ),
            witness_evidence_ids=("ev-lineage-preclinical",),
            blocker_codes=("second_lineage_not_yet_visible",),
        )
        self.assertTrue(all(exact.values()))

        wrong_action = score_frontier_stage_components(
            expectation,
            action=FrontierAction(
                disposition="advance",
                next_action="retrieve",
                risk_flags=("provenance",),
            ),
            witness_evidence_ids=("ev-lineage-preclinical",),
            blocker_codes=("second_lineage_not_yet_visible",),
        )
        self.assertFalse(wrong_action["disposition_correct"])
        self.assertTrue(wrong_action["next_action_correct"])

        two_flag_expectation = oracles["oracles"][0]["stage_expectations"][3]
        order_invariant = score_frontier_stage_components(
            two_flag_expectation,
            action=FrontierAction(
                disposition="hold",
                next_action="verify",
                risk_flags=("out_of_distribution", "provenance"),
            ),
            witness_evidence_ids=(
                "ev-lineage-ra-tensor",
                "ev-lineage-preclinical",
            ),
            blocker_codes=("cross_domain_corroboration_not_authorized",),
        )
        self.assertTrue(all(order_invariant.values()))

    def test_task_set_rejects_post_cutoff_evidence_leakage(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        seeds = load_frontier_seed_manifest(SEEDS, root=ROOT, protocol=protocol)
        tasks = copy.deepcopy(_tasks())
        temporal = tasks["tasks"][1]
        temporal["stages"][0]["accessible_evidence_ids"].append(
            "ev-temporal-cutoff-eval"
        )
        _rehash_tasks(tasks)
        with self.assertRaisesRegex(FrontierContractError, "post-cutoff evidence"):
            validate_frontier_task_set(
                tasks,
                root=ROOT,
                protocol=protocol,
                seed_manifest=seeds,
            )

    def test_task_set_rejects_lineage_cycles(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        seeds = load_frontier_seed_manifest(SEEDS, root=ROOT, protocol=protocol)
        tasks = copy.deepcopy(_tasks())
        tasks["tasks"][2]["lineage_edges"].append(
            {
                "parent_evidence_id": "ev-handoff-m6",
                "child_evidence_id": "ev-handoff-bridge",
                "relationship": "derives_from",
            }
        )
        _rehash_tasks(tasks)
        with self.assertRaisesRegex(FrontierContractError, "must be acyclic"):
            validate_frontier_task_set(
                tasks,
                root=ROOT,
                protocol=protocol,
                seed_manifest=seeds,
            )

    def test_oracle_rejects_task_and_seed_rebinding(self) -> None:
        protocol, seeds, tasks, _, _ = _development()
        for mutation in ("task_hash", "mutation_id"):
            with self.subTest(mutation=mutation):
                oracles = copy.deepcopy(_oracles())
                if mutation == "task_hash":
                    oracles["oracles"][0]["task_sha256"] = "0" * 64
                    expected = "does not open task commitment"
                else:
                    oracles["oracles"][0]["mutation_expectations"][0]["mutation_id"] = (
                        "model_selected_mutation"
                    )
                    expected = "design-seed binding"
                _rehash_oracles(oracles)
                with self.assertRaisesRegex(FrontierContractError, expected):
                    validate_frontier_oracle_set(
                        oracles,
                        root=ROOT,
                        protocol=protocol,
                        seed_manifest=seeds,
                        task_set=tasks,
                    )

    def test_curation_cannot_admit_unreviewed_development_task(self) -> None:
        protocol, seeds, tasks, oracles, _ = _development()
        curation = copy.deepcopy(_curation())
        curation["records"][0]["board_admitted"] = True
        _rehash_curation(curation)
        with self.assertRaisesRegex(FrontierContractError, "cannot enter"):
            validate_frontier_curation_tranche(
                curation,
                root=ROOT,
                protocol=protocol,
                seed_manifest=seeds,
                task_set=tasks,
                oracle_set=oracles,
            )

    def test_protocol_and_seed_manifest_match_json_schemas(self) -> None:
        for schema_path, artifact in (
            (PROTOCOL_SCHEMA, _protocol()),
            (SEEDS_SCHEMA, _seeds()),
            (TASKS_SCHEMA, _tasks()),
            (ORACLES_SCHEMA, _oracles()),
            (CURATION_SCHEMA, _curation()),
            (BOARD_PROTOCOL_SCHEMA, _board_protocol()),
            (BOARD_SLOTS_SCHEMA, _board_slots()),
            (CALIBRATION_PROGRESS_SCHEMA, _calibration_progress()),
            (PREFLIGHT_SUMMARY_SCHEMA, _preflight_summary()),
            (SEMANTIC_REVIEW_SUMMARY_SCHEMA, _semantic_review_summary()),
            (SEMANTIC_WORKFLOW_SUMMARY_SCHEMA, _semantic_workflow_summary()),
            (
                ORACLE_CHALLENGE_SUMMARY_SCHEMA,
                json.loads(ORACLE_CHALLENGE_SUMMARY.read_text(encoding="utf-8")),
            ),
            (ORACLE_FRAGILITY_SUMMARY_SCHEMA, _oracle_fragility_summary()),
            (SUPPORT_CURATION_SUMMARY_SCHEMA, _support_curation_summary()),
            (TRANSITION_AUDIT_SUMMARY_SCHEMA, _transition_audit_summary()),
            (
                COUPLED_AUGMENTATION_SUMMARY_SCHEMA,
                _coupled_augmentation_summary(),
            ),
            (COUPLED_PLACEBO_SUMMARY_SCHEMA, _coupled_placebo_summary()),
            (TOKENIZER_PLACEBO_SUMMARY_SCHEMA, _tokenizer_placebo_summary()),
            (
                TOKENIZER_INDEPENDENT_PROTOCOL_SCHEMA,
                _tokenizer_independent_protocol(),
            ),
            (
                TOKENIZER_INDEPENDENT_SUMMARY_SCHEMA,
                _tokenizer_independent_summary(),
            ),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)

        for schema_path in (
            PRIVATE_CALIBRATION_TASK_SCHEMA,
            PRIVATE_CALIBRATION_ORACLE_SCHEMA,
            PRIVATE_PREFLIGHT_SCHEMA,
            PRIVATE_SEMANTIC_PACKET_SCHEMA,
            PRIVATE_SEMANTIC_KEY_SCHEMA,
            PRIVATE_SEMANTIC_RESPONSE_SCHEMA,
            PRIVATE_SEMANTIC_TRIAGE_SCHEMA,
            PRIVATE_SEMANTIC_LEDGER_SCHEMA,
            PRIVATE_ORACLE_CHALLENGE_PACKET_SCHEMA,
            PRIVATE_ORACLE_CHALLENGE_KEY_SCHEMA,
            PRIVATE_ORACLE_CHALLENGE_RESPONSE_SCHEMA,
            PRIVATE_ORACLE_CHALLENGE_COMPARISON_SCHEMA,
            PRIVATE_ORACLE_CHALLENGE_LEDGER_SCHEMA,
            PRIVATE_ORACLE_FRAGILITY_REPORT_SCHEMA,
            PRIVATE_SUPPORT_CURATION_PACKET_SCHEMA,
            PRIVATE_TRANSITION_AUDIT_REPORT_SCHEMA,
            PRIVATE_COUPLED_AUGMENTATION_PACKET_SCHEMA,
            PRIVATE_COUPLED_PLACEBO_PACKET_SCHEMA,
            PRIVATE_COUPLED_PLACEBO_KEY_SCHEMA,
            PRIVATE_TOKENIZER_PLACEBO_PACKET_SCHEMA,
            PRIVATE_TOKENIZER_PLACEBO_KEY_SCHEMA,
            PRIVATE_TOKENIZER_INDEPENDENT_REPORT_SCHEMA,
        ):
            Draft202012Validator.check_schema(
                json.loads(schema_path.read_text(encoding="utf-8"))
            )

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = PROTOCOL.read_text(encoding="utf-8")
        duplicate = text.replace(
            '  "protocol_id":',
            '  "schema_version": "duplicate",\n  "protocol_id":',
            1,
        )
        with self.assertRaisesRegex(FrontierContractError, "duplicate JSON key"):
            frontier_protocol_from_json(duplicate, root=ROOT)

    def test_launch_band_cannot_be_used_to_select_tasks(self) -> None:
        protocol = copy.deepcopy(_protocol())
        protocol["frontier_launch_band"]["used_for_task_selection"] = True
        _rehash_protocol(protocol)
        with self.assertRaisesRegex(FrontierContractError, "must not be used"):
            validate_frontier_protocol(protocol, root=ROOT)

    def test_nonfinite_launch_band_is_rejected(self) -> None:
        protocol = copy.deepcopy(_protocol())
        _rehash_protocol(protocol)
        protocol["frontier_launch_band"]["nominal"] = float("nan")
        with self.assertRaisesRegex(FrontierContractError, "must be finite"):
            validate_frontier_protocol(protocol, root=ROOT)

    def test_model_failure_filtering_cannot_be_enabled(self) -> None:
        protocol = copy.deepcopy(_protocol())
        protocol["sampling_policy"]["model_failure_filtering_prohibited"] = False
        _rehash_protocol(protocol)
        with self.assertRaisesRegex(
            FrontierContractError,
            "model_failure_filtering_prohibited must remain true",
        ):
            validate_frontier_protocol(protocol, root=ROOT)

    def test_family_cannot_drop_its_defining_gate(self) -> None:
        protocol = copy.deepcopy(_protocol())
        family = protocol["task_families"][0]
        family["required_gates"].remove("lineage_independence")
        _rehash_protocol(protocol)
        with self.assertRaisesRegex(FrontierContractError, "lost its defining gates"):
            validate_frontier_protocol(protocol, root=ROOT)

    def test_seed_manifest_cannot_claim_benchmark_evidence(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        seeds = copy.deepcopy(_seeds())
        seeds["benchmark_evidence_claimed"] = True
        _rehash_seeds(seeds)
        with self.assertRaisesRegex(FrontierContractError, "cannot claim"):
            validate_frontier_seed_manifest(seeds, root=ROOT, protocol=protocol)

    def test_seed_manifest_requires_frontier_length(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        for invalid_stage_count in (3, 13):
            with self.subTest(stage_count=invalid_stage_count):
                seeds = copy.deepcopy(_seeds())
                seeds["seeds"][0]["planned_stage_count"] = invalid_stage_count
                _rehash_seeds(seeds)
                with self.assertRaisesRegex(
                    FrontierContractError, "not a frontier-length"
                ):
                    validate_frontier_seed_manifest(
                        seeds,
                        root=ROOT,
                        protocol=protocol,
                    )

    def test_seed_manifest_cannot_rebind_protocol_artifacts(self) -> None:
        protocol = load_frontier_protocol(PROTOCOL, root=ROOT)
        seeds = copy.deepcopy(_seeds())
        seeds["seeds"][0]["source_artifacts"] = ["README.md"]
        _rehash_seeds(seeds)
        with self.assertRaisesRegex(FrontierContractError, "protocol binding"):
            validate_frontier_seed_manifest(seeds, root=ROOT, protocol=protocol)

    def test_cli_validates_and_summarizes_both_contracts(self) -> None:
        for command in (
            "validate-protocol",
            "summarize-protocol",
            "validate-seeds",
            "summarize-seeds",
            "validate-development",
            "summarize-development",
            "validate-board",
            "summarize-board",
            "validate-calibration",
            "summarize-calibration",
            "validate-preflight",
            "summarize-preflight",
            "validate-semantic-review",
            "summarize-semantic-review",
            "validate-semantic-workflow",
            "summarize-semantic-workflow",
            "validate-semantic-resolution",
            "summarize-semantic-resolution",
            "validate-oracle-challenge",
            "summarize-oracle-challenge",
            "validate-oracle-fragility",
            "summarize-oracle-fragility",
            "validate-support-curation",
            "summarize-support-curation",
            "validate-transition-audit",
            "summarize-transition-audit",
            "validate-coupled-augmentation",
            "summarize-coupled-augmentation",
            "validate-coupled-placebo",
            "summarize-coupled-placebo",
            "validate-tokenizer-placebo",
            "summarize-tokenizer-placebo",
            "validate-tokenizer-independent-evaluation",
            "summarize-tokenizer-independent-evaluation",
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.frontier_cli",
                    command,
                    "--root",
                    str(ROOT),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            expected_protocol_id = (
                "adds-frontier-tokenizer-independent-family-evaluation-v1"
                if "tokenizer-independent" in command
                else FRONTIER_PROTOCOL_ID
            )
            self.assertEqual(payload["protocol_id"], expected_protocol_id)

    def test_cli_rejects_tampered_protocol(self) -> None:
        protocol = copy.deepcopy(_protocol())
        protocol["next_milestone"]["benchmark_evidence_claimed"] = True
        _rehash_protocol(protocol)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.frontier_cli",
                    "validate-protocol",
                    "--protocol",
                    str(path),
                    "--root",
                    str(ROOT),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stderr)
        self.assertEqual(payload["error"]["code"], "invalid_frontier_contract")


if __name__ == "__main__":
    unittest.main()
