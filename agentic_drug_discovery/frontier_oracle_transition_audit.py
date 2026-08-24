"""Cross-stage evidence/action transition diagnostics for private frontier oracles."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
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
from .frontier_oracle_fragility import validate_frontier_oracle_fragility_summary
from .frontier_oracle_support_curation import (
    validate_frontier_support_curation_private_opening,
    validate_frontier_support_curation_summary,
)
from .frontier_preflight import (
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)


FRONTIER_TRANSITION_AUDIT_REPORT_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-transition-audit-report.v1"
)
FRONTIER_TRANSITION_AUDIT_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-oracle-transition-audit-summary.v1"
)
FRONTIER_TRANSITION_AUDIT_ID = "adds-frontier-oracle-transition-audit-v1"
FRONTIER_TRANSITION_CLASSIFICATION_RULE = (
    "classify_exact_action_and_witness_set_deltas_between_adjacent_canonical_stages"
)
FRONTIER_CAUSAL_REVIEW_TRIGGER = (
    "action_and_access_deltas_exist_but_no_transition_contains_both"
)
FRONTIER_TRANSITION_CLASSES = (
    "action_and_witness_changed",
    "action_changed_without_witness_delta",
    "witness_changed_without_action_delta",
    "action_and_witness_stable",
)
_CLASS_COUNT_FIELDS = {
    "action_and_witness_changed": "action_and_witness_changed_transition_count",
    "action_changed_without_witness_delta": (
        "action_changed_without_witness_delta_count"
    ),
    "witness_changed_without_action_delta": (
        "witness_changed_without_action_delta_count"
    ),
    "action_and_witness_stable": "action_and_witness_stable_transition_count",
}
_COUNT_FIELDS = {
    "task_count",
    "canonical_transition_count",
    "action_changed_transition_count",
    "witness_changed_transition_count",
    "blocker_changed_transition_count",
    "accessible_evidence_changed_transition_count",
    "required_gate_set_changed_transition_count",
    "as_of_date_changed_transition_count",
    "new_accessible_evidence_item_count",
    "removed_accessible_evidence_item_count",
    "action_and_witness_changed_transition_count",
    "action_changed_without_witness_delta_count",
    "witness_changed_without_action_delta_count",
    "action_and_witness_stable_transition_count",
    "action_changed_with_access_delta_count",
    "action_changed_without_access_delta_count",
    "access_delta_without_action_change_count",
    "witness_access_delta_alignment_pass_count",
    "blocker_action_delta_alignment_pass_count",
    "disposition_changed_transition_count",
    "next_action_changed_transition_count",
    "risk_flags_changed_transition_count",
}
_PUBLIC_NONCLAIMS = {
    "Structural transition classes do not establish that an action or witness change is scientifically justified.",
    "Zero observed action/evidence coupling is a canonical-trajectory coverage gap, not proof of causal inconsistency.",
    "Stage-kind and gate progression may explain action changes but are not causal evidence by themselves.",
    "Machine diagnostics cannot revise author oracles or satisfy human review and challenge gates.",
    "No private task, oracle, evidence identity, stage transition, gate set, or review payload is public.",
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


def frontier_transition_audit_report_integrity_sha256(
    report: Mapping[str, Any],
) -> str:
    return _canonical_sha256(report, exclude=frozenset({"integrity_sha256"}))


def frontier_transition_audit_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _transition_class(*, action_changed: bool, witness_changed: bool) -> str:
    if action_changed and witness_changed:
        return "action_and_witness_changed"
    if action_changed:
        return "action_changed_without_witness_delta"
    if witness_changed:
        return "witness_changed_without_action_delta"
    return "action_and_witness_stable"


def _ordered_delta(previous: list[str], current: list[str]) -> tuple[list[str], list[str]]:
    previous_set = set(previous)
    current_set = set(current)
    return (
        [item for item in current if item not in previous_set],
        [item for item in previous if item not in current_set],
    )


def compile_frontier_transition_audit_artifacts(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
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
    """Compile adjacent-stage diagnostics without making causal judgments."""

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
    fragility_data = validate_frontier_oracle_fragility_summary(
        public_fragility_summary,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    support_data = validate_frontier_support_curation_summary(
        public_support_curation_summary,
        public_fragility_summary=fragility_data,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_support_curation_private_opening(
        private_packet_set=private_support_curation_packets,
        public_summary=support_data,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight_data,
        public_preflight=public_preflight_data,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=fragility_data,
        progress=progress_data,
        **validation_kwargs,
    )
    _date(compiled_on, "transition audit compiled_on")

    records: list[dict[str, Any]] = []
    aggregate: Counter[str] = Counter()
    for task, oracle in zip(
        tasks_data["tasks"], oracles_data["oracles"], strict=True
    ):
        for index in range(1, len(task["stages"])):
            previous_stage = task["stages"][index - 1]
            current_stage = task["stages"][index]
            previous_expectation = oracle["stage_expectations"][index - 1]
            current_expectation = oracle["stage_expectations"][index]

            previous_action = previous_expectation["action"]
            current_action = current_expectation["action"]
            action_components = [
                component
                for component in ("disposition", "next_action", "risk_flags")
                if previous_action[component] != current_action[component]
            ]
            action_changed = bool(action_components)
            witness_added, witness_removed = _ordered_delta(
                previous_expectation["witness_evidence_ids"],
                current_expectation["witness_evidence_ids"],
            )
            witness_changed = bool(witness_added or witness_removed)
            blocker_added, blocker_removed = _ordered_delta(
                previous_expectation["blocker_codes"],
                current_expectation["blocker_codes"],
            )
            blocker_changed = bool(blocker_added or blocker_removed)
            access_added, access_removed = _ordered_delta(
                previous_stage["accessible_evidence_ids"],
                current_stage["accessible_evidence_ids"],
            )
            access_changed = bool(access_added or access_removed)
            gate_added, gate_removed = _ordered_delta(
                previous_stage["required_gates"], current_stage["required_gates"]
            )
            gate_changed = bool(gate_added or gate_removed)
            transition_class = _transition_class(
                action_changed=action_changed, witness_changed=witness_changed
            )
            witness_access_aligned = (
                witness_added == access_added and witness_removed == access_removed
            )
            blocker_action_aligned = blocker_changed == action_changed

            aggregate["canonical_transition_count"] += 1
            aggregate["action_changed_transition_count"] += action_changed
            aggregate["witness_changed_transition_count"] += witness_changed
            aggregate["blocker_changed_transition_count"] += blocker_changed
            aggregate["accessible_evidence_changed_transition_count"] += (
                access_changed
            )
            aggregate["required_gate_set_changed_transition_count"] += gate_changed
            aggregate["as_of_date_changed_transition_count"] += (
                previous_stage["as_of_date"] != current_stage["as_of_date"]
            )
            aggregate["new_accessible_evidence_item_count"] += len(access_added)
            aggregate["removed_accessible_evidence_item_count"] += len(
                access_removed
            )
            aggregate[_CLASS_COUNT_FIELDS[transition_class]] += 1
            aggregate["action_changed_with_access_delta_count"] += (
                action_changed and access_changed
            )
            aggregate["action_changed_without_access_delta_count"] += (
                action_changed and not access_changed
            )
            aggregate["access_delta_without_action_change_count"] += (
                access_changed and not action_changed
            )
            aggregate["witness_access_delta_alignment_pass_count"] += (
                witness_access_aligned
            )
            aggregate["blocker_action_delta_alignment_pass_count"] += (
                blocker_action_aligned
            )
            for component in action_components:
                aggregate[f"{component}_changed_transition_count"] += 1

            records.append(
                {
                    "slot_id": task["slot_id"],
                    "task_id": task["task_id"],
                    "canonical_task_commitment": frontier_calibration_task_sha256(
                        task
                    ),
                    "author_oracle_commitment": frontier_calibration_oracle_sha256(
                        oracle
                    ),
                    "transition_id": (
                        f"{previous_stage['stage_id']}->{current_stage['stage_id']}"
                    ),
                    "from_stage_id": previous_stage["stage_id"],
                    "to_stage_id": current_stage["stage_id"],
                    "from_stage_kind": previous_stage["stage_kind"],
                    "to_stage_kind": current_stage["stage_kind"],
                    "from_as_of_date": previous_stage["as_of_date"],
                    "to_as_of_date": current_stage["as_of_date"],
                    "previous_accessible_evidence_ids": list(
                        previous_stage["accessible_evidence_ids"]
                    ),
                    "current_accessible_evidence_ids": list(
                        current_stage["accessible_evidence_ids"]
                    ),
                    "accessible_evidence_ids_added": access_added,
                    "accessible_evidence_ids_removed": access_removed,
                    "previous_required_gates": list(previous_stage["required_gates"]),
                    "current_required_gates": list(current_stage["required_gates"]),
                    "required_gates_added": gate_added,
                    "required_gates_removed": gate_removed,
                    "previous_action": dict(previous_action),
                    "current_action": dict(current_action),
                    "changed_action_components": action_components,
                    "previous_witness_evidence_ids": list(
                        previous_expectation["witness_evidence_ids"]
                    ),
                    "current_witness_evidence_ids": list(
                        current_expectation["witness_evidence_ids"]
                    ),
                    "witness_evidence_ids_added": witness_added,
                    "witness_evidence_ids_removed": witness_removed,
                    "previous_blocker_codes": list(
                        previous_expectation["blocker_codes"]
                    ),
                    "current_blocker_codes": list(
                        current_expectation["blocker_codes"]
                    ),
                    "blocker_codes_added": blocker_added,
                    "blocker_codes_removed": blocker_removed,
                    "transition_class": transition_class,
                    "action_changed": action_changed,
                    "witness_changed": witness_changed,
                    "blocker_changed": blocker_changed,
                    "accessible_evidence_changed": access_changed,
                    "required_gate_set_changed": gate_changed,
                    "as_of_date_changed": (
                        previous_stage["as_of_date"] != current_stage["as_of_date"]
                    ),
                    "witness_access_delta_aligned": witness_access_aligned,
                    "blocker_action_delta_aligned": blocker_action_aligned,
                    "scientific_consistency_established": False,
                    "causal_explanation_established": False,
                    "automatic_oracle_edit_authorized": False,
                }
            )
        aggregate["task_count"] += 1

    for field_name in _COUNT_FIELDS:
        aggregate[field_name] += 0
    coupling_coverage_ready = (
        aggregate["action_changed_transition_count"] > 0
        and aggregate["accessible_evidence_changed_transition_count"] > 0
        and aggregate["action_changed_with_access_delta_count"] > 0
    )
    causal_review_required = (
        aggregate["action_changed_transition_count"] > 0
        and aggregate["accessible_evidence_changed_transition_count"] > 0
        and aggregate["action_changed_with_access_delta_count"] == 0
    )
    status = (
        "machine_audit_complete_coupling_coverage_observed"
        if coupling_coverage_ready
        else "machine_audit_complete_causal_discriminability_review_required"
    )
    report: dict[str, Any] = {
        "schema_version": FRONTIER_TRANSITION_AUDIT_REPORT_SCHEMA_VERSION,
        "audit_id": FRONTIER_TRANSITION_AUDIT_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "private_fragility_report_integrity_sha256": private_fragility_report[
            "integrity_sha256"
        ],
        "private_support_curation_packet_set_integrity_sha256": (
            private_support_curation_packets["integrity_sha256"]
        ),
        "transition_classification_rule": FRONTIER_TRANSITION_CLASSIFICATION_RULE,
        "causal_review_trigger": FRONTIER_CAUSAL_REVIEW_TRIGGER,
        "records": records,
        **dict(aggregate),
        "canonical_transition_coupling_coverage_ready": coupling_coverage_ready,
        "evidence_action_coupling_review_required": causal_review_required,
        "scientific_causality_established": False,
        "oracle_revision_applied": False,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    report["integrity_sha256"] = frontier_transition_audit_report_integrity_sha256(
        report
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_TRANSITION_AUDIT_SUMMARY_SCHEMA_VERSION,
        "audit_id": FRONTIER_TRANSITION_AUDIT_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": status,
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data[
            "integrity_sha256"
        ],
        "public_fragility_summary_integrity_sha256": fragility_data[
            "integrity_sha256"
        ],
        "public_support_curation_summary_integrity_sha256": support_data[
            "integrity_sha256"
        ],
        "private_report_commitment": report["integrity_sha256"],
        "transition_classification_rule": FRONTIER_TRANSITION_CLASSIFICATION_RULE,
        "causal_review_trigger": FRONTIER_CAUSAL_REVIEW_TRIGGER,
        **dict(aggregate),
        "canonical_transition_coupling_coverage_ready": coupling_coverage_ready,
        "evidence_action_coupling_review_required": causal_review_required,
        "human_transition_review_required": True,
        "scientific_causality_established": False,
        "oracle_revision_applied": False,
        "oracle_support_ready_for_independent_challenge": False,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = (
        frontier_transition_audit_summary_integrity_sha256(summary)
    )
    return report, summary


def validate_frontier_transition_audit_summary(
    summary: Mapping[str, Any],
    *,
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
    fragility_data = validate_frontier_oracle_fragility_summary(
        public_fragility_summary,
        public_preflight=preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    support_data = validate_frontier_support_curation_summary(
        public_support_curation_summary,
        public_fragility_summary=fragility_data,
        public_preflight=preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    fields = {
        "schema_version",
        "audit_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "public_fragility_summary_integrity_sha256",
        "public_support_curation_summary_integrity_sha256",
        "private_report_commitment",
        "transition_classification_rule",
        "causal_review_trigger",
        *_COUNT_FIELDS,
        "canonical_transition_coupling_coverage_ready",
        "evidence_action_coupling_review_required",
        "human_transition_review_required",
        "scientific_causality_established",
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "transition_audit_summary", fields)
    if data["schema_version"] != FRONTIER_TRANSITION_AUDIT_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported transition audit summary schema")
    if (
        data["audit_id"] != FRONTIER_TRANSITION_AUDIT_ID
        or data["protocol_id"] != support_data["protocol_id"]
        or data["board_id"] != support_data["board_id"]
    ):
        raise FrontierContractError("transition audit summary rebound provenance")
    _date(data["compiled_on"], "transition audit summary compiled_on")
    commitments = {
        "public_preflight_integrity_sha256": preflight_data["integrity_sha256"],
        "public_fragility_summary_integrity_sha256": fragility_data[
            "integrity_sha256"
        ],
        "public_support_curation_summary_integrity_sha256": support_data[
            "integrity_sha256"
        ],
    }
    for field_name, expected in commitments.items():
        if _sha256(data[field_name], f"transition audit {field_name}") != expected:
            raise FrontierContractError(
                f"transition audit summary does not bind {field_name}"
            )
    _sha256(data["private_report_commitment"], "transition audit report")
    _sha256(data["integrity_sha256"], "transition audit summary integrity")
    if (
        data["transition_classification_rule"]
        != FRONTIER_TRANSITION_CLASSIFICATION_RULE
        or data["causal_review_trigger"] != FRONTIER_CAUSAL_REVIEW_TRIGGER
    ):
        raise FrontierContractError("transition audit summary changed frozen rules")
    counts = {
        name: _integer(data[name], f"transition audit summary {name}")
        for name in _COUNT_FIELDS
    }
    if counts["task_count"] != 10 or counts["canonical_transition_count"] != 50:
        raise FrontierContractError("transition audit requires ten tasks and fifty transitions")
    class_total = sum(
        counts[_CLASS_COUNT_FIELDS[transition_class]]
        for transition_class in FRONTIER_TRANSITION_CLASSES
    )
    if class_total != counts["canonical_transition_count"]:
        raise FrontierContractError("transition audit class counts do not close")
    if counts["action_changed_transition_count"] != (
        counts["action_and_witness_changed_transition_count"]
        + counts["action_changed_without_witness_delta_count"]
    ):
        raise FrontierContractError("transition audit action counts do not close")
    if counts["witness_changed_transition_count"] != (
        counts["action_and_witness_changed_transition_count"]
        + counts["witness_changed_without_action_delta_count"]
    ):
        raise FrontierContractError("transition audit witness counts do not close")
    for field_name in (
        "witness_access_delta_alignment_pass_count",
        "blocker_action_delta_alignment_pass_count",
    ):
        if counts[field_name] > counts["canonical_transition_count"]:
            raise FrontierContractError(f"transition audit {field_name} exceeds total")
    if counts["witness_access_delta_alignment_pass_count"] == 50 and (
        counts["witness_changed_transition_count"]
        != counts["accessible_evidence_changed_transition_count"]
    ):
        raise FrontierContractError("transition audit witness/access counts diverge")
    if counts["blocker_action_delta_alignment_pass_count"] == 50 and (
        counts["blocker_changed_transition_count"]
        != counts["action_changed_transition_count"]
    ):
        raise FrontierContractError("transition audit blocker/action counts diverge")
    if counts["action_changed_transition_count"] != (
        counts["action_changed_with_access_delta_count"]
        + counts["action_changed_without_access_delta_count"]
    ):
        raise FrontierContractError("transition audit action/access counts do not close")
    if counts["accessible_evidence_changed_transition_count"] != (
        counts["action_changed_with_access_delta_count"]
        + counts["access_delta_without_action_change_count"]
    ):
        raise FrontierContractError("transition audit access/action counts do not close")
    coupling_ready = (
        counts["action_changed_transition_count"] > 0
        and counts["accessible_evidence_changed_transition_count"] > 0
        and counts["action_changed_with_access_delta_count"] > 0
    )
    causal_review = (
        counts["action_changed_transition_count"] > 0
        and counts["accessible_evidence_changed_transition_count"] > 0
        and counts["action_changed_with_access_delta_count"] == 0
    )
    expected_status = (
        "machine_audit_complete_coupling_coverage_observed"
        if coupling_ready
        else "machine_audit_complete_causal_discriminability_review_required"
    )
    if data["status"] != expected_status:
        raise FrontierContractError("transition audit summary status is inconsistent")
    expected_booleans = {
        "canonical_transition_coupling_coverage_ready": coupling_ready,
        "evidence_action_coupling_review_required": causal_review,
        "human_transition_review_required": True,
    }
    for field_name, expected in expected_booleans.items():
        if _boolean(data[field_name], f"transition audit {field_name}") != expected:
            raise FrontierContractError(f"transition audit {field_name} is inconsistent")
    for field_name in (
        "scientific_causality_established",
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"transition audit {field_name}"):
            raise FrontierContractError(f"transition audit {field_name} must remain false")
    if _integer(data["board_admitted_count"], "transition audit board count") != 0:
        raise FrontierContractError("transition audit board count must remain zero")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "transition audit nonclaims"))
    ):
        raise FrontierContractError("transition audit summary removed a nonclaim")
    if data["integrity_sha256"] != frontier_transition_audit_summary_integrity_sha256(
        data
    ):
        raise FrontierContractError("transition audit summary integrity mismatch")
    return data


def validate_frontier_transition_audit_private_opening(
    *,
    private_report: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
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
    data = validate_frontier_transition_audit_summary(
        public_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if (
        private_report.get("integrity_sha256")
        != frontier_transition_audit_report_integrity_sha256(private_report)
    ):
        raise FrontierContractError("transition audit private report integrity mismatch")
    expected_report, expected_summary = compile_frontier_transition_audit_artifacts(
        task_set=task_set,
        oracle_set=oracle_set,
        private_preflight=private_preflight,
        public_preflight=public_preflight,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=public_fragility_summary,
        private_support_curation_packets=private_support_curation_packets,
        public_support_curation_summary=public_support_curation_summary,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        compiled_on=data["compiled_on"],
    )
    if private_report != expected_report or public_summary != expected_summary:
        raise FrontierContractError(
            "transition audit artifacts do not replay from committed inputs"
        )
    return transition_audit_summary(
        public_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_transition_audit_commitment_opened": True}


def load_frontier_transition_audit_report(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "transition audit report")


def load_frontier_transition_audit_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_transition_audit_summary(
        _load_json(path.read_text(encoding="utf-8"), "transition audit summary"),
        **kwargs,
    )


def transition_audit_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_transition_audit_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "canonical_transition_count": data["canonical_transition_count"],
        "action_changed_transition_count": data[
            "action_changed_transition_count"
        ],
        "witness_changed_transition_count": data[
            "witness_changed_transition_count"
        ],
        "action_changed_without_witness_delta_count": data[
            "action_changed_without_witness_delta_count"
        ],
        "witness_changed_without_action_delta_count": data[
            "witness_changed_without_action_delta_count"
        ],
        "action_changed_with_access_delta_count": data[
            "action_changed_with_access_delta_count"
        ],
        "canonical_transition_coupling_coverage_ready": data[
            "canonical_transition_coupling_coverage_ready"
        ],
        "evidence_action_coupling_review_required": data[
            "evidence_action_coupling_review_required"
        ],
        "challenge_assignment_authorized": data[
            "challenge_assignment_authorized"
        ],
        "integrity_sha256": data["integrity_sha256"],
    }
