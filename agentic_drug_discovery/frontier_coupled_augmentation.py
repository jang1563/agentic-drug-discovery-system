"""Matched evidence/action augmentation design for ADDS-Frontier oracles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .frontier import (
    FrontierContractError,
    _boolean,
    _date,
    _integer,
    _load_json,
    _record,
    _sha256,
    _text_list,
)
from .frontier_calibration import (
    frontier_calibration_oracle_sha256,
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_oracle_transition_audit import (
    validate_frontier_transition_audit_private_opening,
    validate_frontier_transition_audit_summary,
)
from .frontier_preflight import (
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)
from .frontier_semantic_review import (
    validate_frontier_semantic_review_private_opening,
    validate_frontier_semantic_review_summary,
)


FRONTIER_COUPLED_AUGMENTATION_PACKET_SCHEMA_VERSION = (
    "adds.frontier-private-coupled-augmentation-packet-set.v1"
)
FRONTIER_COUPLED_AUGMENTATION_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-coupled-augmentation-summary.v1"
)
FRONTIER_COUPLED_AUGMENTATION_ID = "adds-frontier-coupled-augmentation-v1"
FRONTIER_COUPLED_AUGMENTATION_PAIRING_RULE = (
    "pair_each_bounded_evidence_reveal_candidate_with_its_same_slot_"
    "source_id_rename_invariance_control"
)
_REQUIRED_COUPLED_CANDIDATE_COMPONENTS = {"next_action", "witness"}
_PUBLIC_NONCLAIMS = {
    "A matched design unit is a review-ready experiment proposal, not a scientific transition label.",
    "Author-expected component changes select candidates but do not establish observed action/evidence coupling.",
    "Source-identifier invariance controls test nuisance stability, not scientific correctness.",
    "No candidate is admitted as a coupled transition until independent semantic review is complete.",
    "Machine compilation cannot revise author oracles or satisfy human review and challenge gates.",
    "No private arm, task, oracle, mutation key, expected component payload, or reviewer material is public.",
    "No challenge assignment, model run, benchmark result, or board admission is authorized.",
}


def _canonical_sha256(
    value: Mapping[str, Any], *, exclude: frozenset[str] = frozenset()
) -> str:
    payload = {key: item for key, item in value.items() if key not in exclude}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def frontier_coupled_augmentation_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_coupled_augmentation_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _only(items: list[Mapping[str, Any]], description: str) -> Mapping[str, Any]:
    if len(items) != 1:
        raise FrontierContractError(f"expected exactly one {description}")
    return items[0]


def compile_frontier_coupled_augmentation_artifacts(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    private_support_curation_packets: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile matched candidates and controls without creating semantic labels."""

    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    tasks_data = validate_frontier_calibration_task_set(task_set, **validation_kwargs)
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set, task_set=tasks_data, **validation_kwargs
    )
    progress_data = validate_frontier_calibration_progress(
        progress, **validation_kwargs
    )
    private_preflight_data = validate_frontier_private_preflight_report(
        private_preflight,
        task_set=tasks_data,
        oracle_set=oracles_data,
        progress=progress_data,
        **validation_kwargs,
    )
    public_preflight_data = validate_frontier_public_preflight_summary(
        public_preflight, progress=progress_data, **validation_kwargs
    )
    semantic_data = validate_frontier_semantic_review_summary(
        public_semantic_summary,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_semantic_review_private_opening(
        packet_set=private_semantic_packets,
        key_set=private_semantic_keys,
        public_summary=semantic_data,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight_data,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    transition_data = validate_frontier_transition_audit_summary(
        public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_transition_audit_private_opening(
        private_report=private_transition_report,
        public_summary=transition_data,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight_data,
        public_preflight=public_preflight_data,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=public_fragility_summary,
        private_support_curation_packets=private_support_curation_packets,
        public_support_curation_summary=public_support_curation_summary,
        progress=progress_data,
        **validation_kwargs,
    )
    _date(compiled_on, "coupled augmentation compiled_on")

    packet_by_id = {
        packet["packet_id"]: packet for packet in private_semantic_packets["packets"]
    }
    keys_by_slot: dict[str, list[Mapping[str, Any]]] = {}
    for key in private_semantic_keys["keys"]:
        keys_by_slot.setdefault(key["slot_id"], []).append(key)
    preflight_by_slot = {
        result["slot_id"]: result
        for result in private_preflight_data["task_results"]
    }

    records: list[dict[str, Any]] = []
    for task, oracle in zip(
        tasks_data["tasks"], oracles_data["oracles"], strict=True
    ):
        slot_id = task["slot_id"]
        candidate_mutation = _only(
            [
                mutation
                for mutation in oracle["mutation_expectations"]
                if mutation["probe_kind"] == "bounded_evidence_reveal"
            ],
            f"bounded evidence reveal mutation for {slot_id}",
        )
        control_mutation = _only(
            [
                mutation
                for mutation in oracle["mutation_expectations"]
                if mutation["probe_kind"] == "source_id_rename"
            ],
            f"source identifier control for {slot_id}",
        )
        candidate_key = _only(
            [
                key
                for key in keys_by_slot.get(slot_id, [])
                if key["mutation_id"] == candidate_mutation["mutation_id"]
            ],
            f"sealed evidence reveal key for {slot_id}",
        )
        packet = packet_by_id.get(candidate_key["packet_id"])
        if packet is None or packet["probe_kind"] != "bounded_evidence_reveal":
            raise FrontierContractError(
                f"coupled augmentation packet mismatch for {slot_id}"
            )
        task_result = preflight_by_slot.get(slot_id)
        if task_result is None:
            raise FrontierContractError(
                f"coupled augmentation preflight result missing for {slot_id}"
            )
        candidate_probe = _only(
            [
                result
                for result in task_result["mutation_results"]
                if result["mutation_id"] == candidate_mutation["mutation_id"]
            ],
            f"evidence reveal preflight probe for {slot_id}",
        )
        control_probe = _only(
            [
                result
                for result in task_result["mutation_results"]
                if result["mutation_id"] == control_mutation["mutation_id"]
            ],
            f"source identifier preflight control for {slot_id}",
        )

        expected_components = list(candidate_key["expected_changed_components"])
        certificate = candidate_key["structural_delta_certificate"]
        candidate_ready = (
            _REQUIRED_COUPLED_CANDIDATE_COMPONENTS.issubset(expected_components)
            and expected_components == list(candidate_mutation["expected_changed_components"])
            and expected_components
            == list(candidate_probe["expected_changed_components"])
            and certificate["exact_delta_passed"] is True
            and packet["delta_certificate_commitment"]
            == _canonical_sha256(certificate)
            and candidate_probe["assessment_lane"] == "semantic_review_required"
            and candidate_probe["observed_contract_outcome"]
            == "structurally_valid_semantic_outcome_unresolved"
            and candidate_probe["expected_outcome_matched"] is None
        )
        control_ready = (
            list(control_mutation["expected_changed_components"]) == []
            and list(control_probe["expected_changed_components"]) == []
            and control_probe["assessment_lane"] == "machine_decidable"
            and control_probe["expected_contract_outcome"] == "valid_invariant"
            and control_probe["observed_contract_outcome"] == "valid_invariant"
            and control_probe["expected_outcome_matched"] is True
        )
        if not candidate_ready or not control_ready:
            raise FrontierContractError(
                f"coupled augmentation design unit is not structurally ready: {slot_id}"
            )

        design_seed = {
            "slot_id": slot_id,
            "candidate_packet_id": packet["packet_id"],
            "candidate_mutation_id": candidate_mutation["mutation_id"],
            "control_mutation_id": control_mutation["mutation_id"],
        }
        records.append(
            {
                "design_unit_id": f"coupled-{_canonical_sha256(design_seed)[:20]}",
                "slot_id": slot_id,
                "canonical_task_commitment": frontier_calibration_task_sha256(task),
                "author_oracle_commitment": frontier_calibration_oracle_sha256(
                    oracle
                ),
                "candidate_packet_id": packet["packet_id"],
                "candidate_packet_commitment": _canonical_sha256(packet),
                "candidate_key_commitment": _canonical_sha256(candidate_key),
                "candidate_preflight_probe_commitment": _canonical_sha256(
                    candidate_probe
                ),
                "control_preflight_probe_commitment": _canonical_sha256(
                    control_probe
                ),
                "candidate_mutation_id": candidate_mutation["mutation_id"],
                "control_mutation_id": control_mutation["mutation_id"],
                "candidate_probe_kind": "bounded_evidence_reveal",
                "control_probe_kind": "source_id_rename",
                "candidate_assessment_lane": "semantic_review_required",
                "control_assessment_lane": "machine_decidable",
                "candidate_structural_delta_certificate": dict(certificate),
                "candidate_exact_structural_delta_passed": True,
                "control_expected_contract_outcome": "valid_invariant",
                "control_observed_contract_outcome": "valid_invariant",
                "control_expected_outcome_matched": True,
                "author_expected_changed_components": expected_components,
                "candidate_action_witness_coupling_targeted": True,
                "semantic_label_status": "pending_human_review",
                "scientific_coupling_established": False,
                "coupled_transition_admitted": False,
                "automatic_oracle_edit_authorized": False,
            }
        )

    records.sort(key=lambda record: record["design_unit_id"])
    design_ready = (
        len(records) == 10
        and all(record["candidate_exact_structural_delta_passed"] for record in records)
        and all(record["control_expected_outcome_matched"] for record in records)
        and all(
            record["candidate_action_witness_coupling_targeted"]
            for record in records
        )
    )
    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_COUPLED_AUGMENTATION_PACKET_SCHEMA_VERSION,
        "design_id": FRONTIER_COUPLED_AUGMENTATION_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "private_semantic_packet_set_integrity_sha256": private_semantic_packets[
            "integrity_sha256"
        ],
        "private_semantic_key_set_integrity_sha256": private_semantic_keys[
            "integrity_sha256"
        ],
        "private_transition_audit_report_integrity_sha256": (
            private_transition_report["integrity_sha256"]
        ),
        "pairing_rule": FRONTIER_COUPLED_AUGMENTATION_PAIRING_RULE,
        "records": records,
        "matched_design_unit_count": len(records),
        "evidence_reveal_candidate_count": len(records),
        "nuisance_invariance_control_count": len(records),
        "exact_structural_delta_candidate_count": sum(
            record["candidate_exact_structural_delta_passed"] for record in records
        ),
        "machine_invariance_control_pass_count": sum(
            record["control_expected_outcome_matched"] for record in records
        ),
        "action_witness_coupling_candidate_count": sum(
            record["candidate_action_witness_coupling_targeted"]
            for record in records
        ),
        "semantic_label_recorded_count": 0,
        "coupled_transition_admitted_count": 0,
        "coupled_augmentation_design_ready": design_ready,
        "scientific_coupling_established": False,
        "oracle_revision_applied": False,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = (
        frontier_coupled_augmentation_packet_set_integrity_sha256(packet_set)
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_COUPLED_AUGMENTATION_SUMMARY_SCHEMA_VERSION,
        "design_id": FRONTIER_COUPLED_AUGMENTATION_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "matched_augmentation_design_compiled_semantic_labels_pending",
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data[
            "integrity_sha256"
        ],
        "public_semantic_summary_integrity_sha256": semantic_data[
            "integrity_sha256"
        ],
        "public_transition_audit_summary_integrity_sha256": transition_data[
            "integrity_sha256"
        ],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "pairing_rule": FRONTIER_COUPLED_AUGMENTATION_PAIRING_RULE,
        "matched_design_unit_count": len(records),
        "evidence_reveal_candidate_count": len(records),
        "nuisance_invariance_control_count": len(records),
        "exact_structural_delta_candidate_count": packet_set[
            "exact_structural_delta_candidate_count"
        ],
        "machine_invariance_control_pass_count": packet_set[
            "machine_invariance_control_pass_count"
        ],
        "action_witness_coupling_candidate_count": packet_set[
            "action_witness_coupling_candidate_count"
        ],
        "semantic_label_required_count": len(records),
        "semantic_label_recorded_count": 0,
        "coupled_transition_admitted_count": 0,
        "coupled_augmentation_design_ready": design_ready,
        "canonical_transition_coupling_coverage_ready": transition_data[
            "canonical_transition_coupling_coverage_ready"
        ],
        "evidence_action_coupling_review_required": transition_data[
            "evidence_action_coupling_review_required"
        ],
        "human_semantic_review_required": True,
        "scientific_coupling_established": False,
        "oracle_revision_applied": False,
        "oracle_support_ready_for_independent_challenge": False,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "author_expected_component_payload_published": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = (
        frontier_coupled_augmentation_summary_integrity_sha256(summary)
    )
    return packet_set, summary


def validate_frontier_coupled_augmentation_summary(
    summary: Mapping[str, Any],
    *,
    public_semantic_summary: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    progress_data = validate_frontier_calibration_progress(
        progress, **validation_kwargs
    )
    preflight_data = validate_frontier_public_preflight_summary(
        public_preflight, progress=progress_data, **validation_kwargs
    )
    semantic_data = validate_frontier_semantic_review_summary(
        public_semantic_summary,
        public_preflight=preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    transition_data = validate_frontier_transition_audit_summary(
        public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    fields = {
        "schema_version",
        "design_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "public_semantic_summary_integrity_sha256",
        "public_transition_audit_summary_integrity_sha256",
        "private_packet_set_commitment",
        "pairing_rule",
        "matched_design_unit_count",
        "evidence_reveal_candidate_count",
        "nuisance_invariance_control_count",
        "exact_structural_delta_candidate_count",
        "machine_invariance_control_pass_count",
        "action_witness_coupling_candidate_count",
        "semantic_label_required_count",
        "semantic_label_recorded_count",
        "coupled_transition_admitted_count",
        "coupled_augmentation_design_ready",
        "canonical_transition_coupling_coverage_ready",
        "evidence_action_coupling_review_required",
        "human_semantic_review_required",
        "scientific_coupling_established",
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "author_expected_component_payload_published",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "coupled_augmentation_summary", fields)
    if (
        data["schema_version"]
        != FRONTIER_COUPLED_AUGMENTATION_SUMMARY_SCHEMA_VERSION
        or data["design_id"] != FRONTIER_COUPLED_AUGMENTATION_ID
        or data["protocol_id"] != transition_data["protocol_id"]
        or data["board_id"] != transition_data["board_id"]
    ):
        raise FrontierContractError("coupled augmentation rebound provenance")
    if data["status"] != (
        "matched_augmentation_design_compiled_semantic_labels_pending"
    ):
        raise FrontierContractError("coupled augmentation overstates maturity")
    _date(data["compiled_on"], "coupled augmentation compiled_on")
    commitments = {
        "public_preflight_integrity_sha256": preflight_data["integrity_sha256"],
        "public_semantic_summary_integrity_sha256": semantic_data[
            "integrity_sha256"
        ],
        "public_transition_audit_summary_integrity_sha256": transition_data[
            "integrity_sha256"
        ],
    }
    for field_name, expected in commitments.items():
        if _sha256(data[field_name], f"coupled augmentation {field_name}") != expected:
            raise FrontierContractError(
                f"coupled augmentation does not bind {field_name}"
            )
    _sha256(data["private_packet_set_commitment"], "coupled augmentation packets")
    _sha256(data["integrity_sha256"], "coupled augmentation summary integrity")
    if data["pairing_rule"] != FRONTIER_COUPLED_AUGMENTATION_PAIRING_RULE:
        raise FrontierContractError("coupled augmentation changed the pairing rule")
    exact_counts = {
        "matched_design_unit_count": 10,
        "evidence_reveal_candidate_count": 10,
        "nuisance_invariance_control_count": 10,
        "exact_structural_delta_candidate_count": 10,
        "machine_invariance_control_pass_count": 10,
        "action_witness_coupling_candidate_count": 10,
        "semantic_label_required_count": 10,
        "semantic_label_recorded_count": 0,
        "coupled_transition_admitted_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if _integer(data[field_name], f"coupled augmentation {field_name}") != expected:
            raise FrontierContractError(
                f"coupled augmentation {field_name} must remain {expected}"
            )
    if not _boolean(
        data["coupled_augmentation_design_ready"],
        "coupled augmentation design readiness",
    ):
        raise FrontierContractError("coupled augmentation design must be ready")
    if not _boolean(
        data["human_semantic_review_required"],
        "coupled augmentation human review",
    ):
        raise FrontierContractError("coupled augmentation must retain human review")
    for field_name in (
        "canonical_transition_coupling_coverage_ready",
        "evidence_action_coupling_review_required",
    ):
        if _boolean(data[field_name], f"coupled augmentation {field_name}") != (
            transition_data[field_name]
        ):
            raise FrontierContractError(
                f"coupled augmentation changed transition status: {field_name}"
            )
    for field_name in (
        "scientific_coupling_established",
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "author_expected_component_payload_published",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"coupled augmentation {field_name}"):
            raise FrontierContractError(
                f"coupled augmentation {field_name} must remain false"
            )
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "coupled augmentation nonclaims"))
    ):
        raise FrontierContractError("coupled augmentation removed a public nonclaim")
    if data["integrity_sha256"] != (
        frontier_coupled_augmentation_summary_integrity_sha256(data)
    ):
        raise FrontierContractError("coupled augmentation summary integrity mismatch")
    return data


def validate_frontier_coupled_augmentation_private_opening(
    *,
    private_packet_set: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    private_support_curation_packets: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    data = validate_frontier_coupled_augmentation_summary(
        public_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    )
    if private_packet_set.get("integrity_sha256") != (
        frontier_coupled_augmentation_packet_set_integrity_sha256(
            private_packet_set
        )
    ):
        raise FrontierContractError(
            "coupled augmentation private packet-set integrity mismatch"
        )
    expected_packets, expected_summary = (
        compile_frontier_coupled_augmentation_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=private_semantic_packets,
            private_semantic_keys=private_semantic_keys,
            public_semantic_summary=public_semantic_summary,
            private_transition_report=private_transition_report,
            public_transition_summary=public_transition_summary,
            private_fragility_report=private_fragility_report,
            public_fragility_summary=public_fragility_summary,
            private_support_curation_packets=private_support_curation_packets,
            public_support_curation_summary=public_support_curation_summary,
            progress=progress,
            compiled_on=data["compiled_on"],
            **validation_kwargs,
        )
    )
    if private_packet_set != expected_packets or public_summary != expected_summary:
        raise FrontierContractError(
            "coupled augmentation artifacts do not replay from committed inputs"
        )
    return coupled_augmentation_summary(
        public_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    ) | {"private_coupled_augmentation_commitment_opened": True}


def load_frontier_coupled_augmentation_packet_set(path: Path) -> dict[str, Any]:
    return _load_json(
        path.read_text(encoding="utf-8"), "coupled augmentation packet set"
    )


def load_frontier_coupled_augmentation_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_coupled_augmentation_summary(
        _load_json(path.read_text(encoding="utf-8"), "coupled augmentation summary"),
        **kwargs,
    )


def coupled_augmentation_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_coupled_augmentation_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "matched_design_unit_count": data["matched_design_unit_count"],
        "exact_structural_delta_candidate_count": data[
            "exact_structural_delta_candidate_count"
        ],
        "machine_invariance_control_pass_count": data[
            "machine_invariance_control_pass_count"
        ],
        "action_witness_coupling_candidate_count": data[
            "action_witness_coupling_candidate_count"
        ],
        "semantic_label_recorded_count": data["semantic_label_recorded_count"],
        "coupled_transition_admitted_count": data[
            "coupled_transition_admitted_count"
        ],
        "coupled_augmentation_design_ready": data[
            "coupled_augmentation_design_ready"
        ],
        "canonical_transition_coupling_coverage_ready": data[
            "canonical_transition_coupling_coverage_ready"
        ],
        "human_semantic_review_required": data["human_semantic_review_required"],
        "scientific_coupling_established": data[
            "scientific_coupling_established"
        ],
    }
