"""Machine-only fragility and support-selectivity audit for private frontier oracles."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .frontier import (
    FRONTIER_NEXT_ACTIONS,
    FrontierAction,
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
from .frontier_preflight import (
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)
from .frontier_tasks import FRONTIER_EVIDENCE_ROLES, score_frontier_stage_components


FRONTIER_ORACLE_FRAGILITY_REPORT_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-fragility-report.v1"
)
FRONTIER_ORACLE_FRAGILITY_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-oracle-fragility-summary.v1"
)
FRONTIER_ORACLE_FRAGILITY_AUDIT_ID = "adds-frontier-oracle-fragility-v1"
FRONTIER_ORACLE_LOCALIZATION_RULE = (
    "applicable_valid_mutation_fails_exactly_one_target_component"
)
FRONTIER_ORACLE_SUPPORT_REVIEW_TRIGGER = (
    "any_task_uses_all_accessible_evidence_as_witnesses_at_every_stage"
)
FRONTIER_ORACLE_LINEAGE_REVIEW_TRIGGER = (
    "any_stage_uses_multiple_witness_ids_from_the_same_lineage"
)
FRONTIER_ORACLE_COMPONENTS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_SCORE_KEYS = (
    "disposition_correct",
    "next_action_correct",
    "risk_flags_correct",
    "witness_valid",
    "blocker_certificate_valid",
)
_COMPONENT_SCORE_KEY = dict(zip(FRONTIER_ORACLE_COMPONENTS, _SCORE_KEYS, strict=True))
_PUBLIC_NONCLAIMS = {
    "Single-component localization tests scorer factorization, not scientific oracle correctness.",
    "Witness saturation is a support-selectivity review trigger, not proof that a cited item is irrelevant.",
    "Repeated witness lineages require review and cannot be counted as independent support by this audit.",
    "Machine fragility checks cannot satisfy independent expert solve or board-admission gates.",
    "No private task, oracle, stage record, identity, nonce, or probe payload is public.",
    "No model run or benchmark performance result is claimed.",
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


def frontier_oracle_fragility_report_integrity_sha256(
    report: Mapping[str, Any],
) -> str:
    return _canonical_sha256(report, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_fragility_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _baseline_submission(expectation: Mapping[str, Any]) -> tuple[Any, list[str], list[str]]:
    action_data = expectation["action"]
    action = FrontierAction(
        disposition=action_data["disposition"],
        next_action=action_data["next_action"],
        risk_flags=tuple(action_data["risk_flags"]),
    )
    return (
        action,
        list(expectation["witness_evidence_ids"]),
        list(expectation["blocker_codes"]),
    )


def _component_probe(
    expectation: Mapping[str, Any], *, component: str
) -> dict[str, Any]:
    action, witnesses, blockers = _baseline_submission(expectation)
    if component == "disposition":
        if action.next_action == "none":
            disposition = "advance" if action.disposition != "advance" else "terminate"
        else:
            disposition = "advance" if action.disposition == "hold" else "hold"
        action = FrontierAction(
            disposition=disposition,
            next_action=action.next_action,
            risk_flags=action.risk_flags,
        )
    elif component == "next_action":
        if action.disposition == "terminate":
            return {
                "component": component,
                "applicable": False,
                "nonapplicability_reason": (
                    "terminate_requires_none_so_next_action_cannot_change_alone"
                ),
                "score_results": None,
                "isolated_target_failure": False,
            }
        alternatives = [
            item
            for item in FRONTIER_NEXT_ACTIONS
            if item != action.next_action
            and not (action.disposition == "hold" and item == "none")
        ]
        action = FrontierAction(
            disposition=action.disposition,
            next_action=alternatives[0],
            risk_flags=action.risk_flags,
        )
    elif component == "risk_flags":
        risk_flags = list(action.risk_flags)
        if risk_flags:
            risk_flags.pop(0)
        else:
            risk_flags.append("provenance")
        action = FrontierAction(
            disposition=action.disposition,
            next_action=action.next_action,
            risk_flags=tuple(risk_flags),
        )
    elif component == "witness":
        witnesses.pop()
    elif component == "blockers":
        blockers.pop()
    else:
        raise FrontierContractError("unknown oracle fragility component")

    scores = score_frontier_stage_components(
        expectation,
        action=action,
        witness_evidence_ids=witnesses,
        blocker_codes=blockers,
    )
    target = _COMPONENT_SCORE_KEY[component]
    isolated = not scores[target] and all(
        passed for score_name, passed in scores.items() if score_name != target
    )
    return {
        "component": component,
        "applicable": True,
        "nonapplicability_reason": None,
        "score_results": scores,
        "isolated_target_failure": isolated,
    }


def compile_frontier_oracle_fragility_artifacts(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile stage-local perturbations and support diagnostics without new labels."""

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
    if (
        public_preflight_data["private_preflight_report_commitment"]
        != private_preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("oracle fragility inputs do not share a preflight")
    _date(compiled_on, "oracle fragility compiled_on")

    records: list[dict[str, Any]] = []
    aggregate: Counter[str] = Counter()
    task_wide_saturation_count = 0
    for task, oracle in zip(
        tasks_data["tasks"], oracles_data["oracles"], strict=True
    ):
        evidence_by_id = {
            item["evidence_id"]: item for item in task["evidence_nodes"]
        }
        task_stage_saturation: list[bool] = []
        previous_expectation: Mapping[str, Any] | None = None
        for stage, expectation in zip(
            task["stages"], oracle["stage_expectations"], strict=True
        ):
            baseline_action, baseline_witnesses, baseline_blockers = (
                _baseline_submission(expectation)
            )
            baseline_scores = score_frontier_stage_components(
                expectation,
                action=baseline_action,
                witness_evidence_ids=baseline_witnesses,
                blocker_codes=baseline_blockers,
            )
            if not all(baseline_scores.values()):
                raise FrontierContractError(
                    "oracle fragility baseline does not replay exactly"
                )
            probes = [
                _component_probe(expectation, component=component)
                for component in FRONTIER_ORACLE_COMPONENTS
            ]
            aggregate["planned_component_probe_count"] += len(probes)
            aggregate["applicable_component_probe_count"] += sum(
                probe["applicable"] for probe in probes
            )
            aggregate["nonapplicable_component_probe_count"] += sum(
                not probe["applicable"] for probe in probes
            )
            aggregate["component_localization_pass_count"] += sum(
                probe["isolated_target_failure"] for probe in probes
            )

            accessible = set(stage["accessible_evidence_ids"])
            witnesses = set(expectation["witness_evidence_ids"])
            nonwitnesses = accessible - witnesses
            witness_lineages = [
                evidence_by_id[item]["lineage_id"] for item in witnesses
            ]
            repeated_lineage_count = len(witness_lineages) - len(
                set(witness_lineages)
            )
            role_counts = Counter(
                evidence_by_id[item]["evidence_role"] for item in witnesses
            )
            saturated = witnesses == accessible
            task_stage_saturation.append(saturated)
            aggregate["canonical_stage_count"] += 1
            aggregate["witness_saturated_stage_count"] += saturated
            aggregate["accessible_nonwitness_evidence_count"] += len(nonwitnesses)
            aggregate["repeated_lineage_witness_stage_count"] += bool(
                repeated_lineage_count
            )
            aggregate["repeated_lineage_witness_id_count"] += repeated_lineage_count
            aggregate["context_witness_stage_count"] += bool(role_counts["context"])
            aggregate["derivative_witness_stage_count"] += bool(
                role_counts["derivative"]
            )
            aggregate["decision_record_witness_stage_count"] += bool(
                role_counts["decision_record"]
            )
            aggregate["contradiction_witness_stage_count"] += bool(
                role_counts["contradiction"]
            )
            singleton_blocker = len(expectation["blocker_codes"]) == 1
            aggregate["singleton_blocker_stage_count"] += singleton_blocker

            if previous_expectation is None:
                transition = {
                    "is_first_stage": True,
                    "action_changed_from_previous": None,
                    "witness_changed_from_previous": None,
                    "blocker_changed_from_previous": None,
                }
            else:
                action_changed = (
                    expectation["action"] != previous_expectation["action"]
                )
                witness_changed = set(expectation["witness_evidence_ids"]) != set(
                    previous_expectation["witness_evidence_ids"]
                )
                blocker_changed = set(expectation["blocker_codes"]) != set(
                    previous_expectation["blocker_codes"]
                )
                aggregate["action_change_without_witness_delta_count"] += (
                    action_changed and not witness_changed
                )
                aggregate["witness_change_without_action_delta_count"] += (
                    witness_changed and not action_changed
                )
                transition = {
                    "is_first_stage": False,
                    "action_changed_from_previous": action_changed,
                    "witness_changed_from_previous": witness_changed,
                    "blocker_changed_from_previous": blocker_changed,
                }
            previous_expectation = expectation
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
                    "stage_id": stage["stage_id"],
                    "accessible_evidence_count": len(accessible),
                    "witness_count": len(witnesses),
                    "accessible_nonwitness_count": len(nonwitnesses),
                    "witness_saturated": saturated,
                    "witness_lineage_count": len(set(witness_lineages)),
                    "repeated_lineage_witness_id_count": repeated_lineage_count,
                    "witness_role_counts": {
                        role: role_counts[role] for role in FRONTIER_EVIDENCE_ROLES
                    },
                    "blocker_count": len(expectation["blocker_codes"]),
                    "singleton_blocker": singleton_blocker,
                    "transition": transition,
                    "component_probes": probes,
                }
            )
        task_wide_saturation_count += all(task_stage_saturation)

    aggregate["task_wide_witness_saturation_count"] = task_wide_saturation_count
    localization_ready = (
        aggregate["applicable_component_probe_count"] > 0
        and aggregate["component_localization_pass_count"]
        == aggregate["applicable_component_probe_count"]
    )
    support_review_required = task_wide_saturation_count > 0
    lineage_review_required = aggregate["repeated_lineage_witness_stage_count"] > 0
    support_ready = (
        localization_ready
        and not support_review_required
        and not lineage_review_required
    )
    status = (
        "machine_audit_complete_support_ready"
        if support_ready
        else "machine_audit_complete_support_revision_required"
    )
    report: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_FRAGILITY_REPORT_SCHEMA_VERSION,
        "audit_id": FRONTIER_ORACLE_FRAGILITY_AUDIT_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "component_localization_rule": FRONTIER_ORACLE_LOCALIZATION_RULE,
        "support_selectivity_review_trigger": FRONTIER_ORACLE_SUPPORT_REVIEW_TRIGGER,
        "lineage_redundancy_review_trigger": FRONTIER_ORACLE_LINEAGE_REVIEW_TRIGGER,
        "records": records,
        **dict(aggregate),
        "component_localization_ready": localization_ready,
        "support_selectivity_review_required": support_review_required,
        "lineage_redundancy_review_required": lineage_review_required,
        "oracle_support_ready_for_independent_challenge": support_ready,
        "scientific_minimality_established": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    report["integrity_sha256"] = frontier_oracle_fragility_report_integrity_sha256(
        report
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_FRAGILITY_SUMMARY_SCHEMA_VERSION,
        "audit_id": FRONTIER_ORACLE_FRAGILITY_AUDIT_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": status,
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data[
            "integrity_sha256"
        ],
        "private_report_commitment": report["integrity_sha256"],
        "component_localization_rule": FRONTIER_ORACLE_LOCALIZATION_RULE,
        "support_selectivity_review_trigger": FRONTIER_ORACLE_SUPPORT_REVIEW_TRIGGER,
        "lineage_redundancy_review_trigger": FRONTIER_ORACLE_LINEAGE_REVIEW_TRIGGER,
        **dict(aggregate),
        "component_localization_ready": localization_ready,
        "support_selectivity_review_required": support_review_required,
        "lineage_redundancy_review_required": lineage_review_required,
        "oracle_support_ready_for_independent_challenge": support_ready,
        "human_curation_required": not support_ready,
        "scientific_minimality_established": False,
        "independent_review_complete": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = frontier_oracle_fragility_summary_integrity_sha256(
        summary
    )
    return report, summary


_AGGREGATE_FIELDS = {
    "canonical_stage_count",
    "planned_component_probe_count",
    "applicable_component_probe_count",
    "nonapplicable_component_probe_count",
    "component_localization_pass_count",
    "witness_saturated_stage_count",
    "task_wide_witness_saturation_count",
    "accessible_nonwitness_evidence_count",
    "repeated_lineage_witness_stage_count",
    "repeated_lineage_witness_id_count",
    "context_witness_stage_count",
    "derivative_witness_stage_count",
    "decision_record_witness_stage_count",
    "contradiction_witness_stage_count",
    "singleton_blocker_stage_count",
    "action_change_without_witness_delta_count",
    "witness_change_without_action_delta_count",
}


def validate_frontier_oracle_fragility_summary(
    summary: Mapping[str, Any],
    *,
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
    fields = {
        "schema_version",
        "audit_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "private_report_commitment",
        "component_localization_rule",
        "support_selectivity_review_trigger",
        "lineage_redundancy_review_trigger",
        *_AGGREGATE_FIELDS,
        "component_localization_ready",
        "support_selectivity_review_required",
        "lineage_redundancy_review_required",
        "oracle_support_ready_for_independent_challenge",
        "human_curation_required",
        "scientific_minimality_established",
        "independent_review_complete",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "oracle_fragility_summary", fields)
    if data["schema_version"] != FRONTIER_ORACLE_FRAGILITY_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported oracle fragility summary schema")
    if (
        data["audit_id"] != FRONTIER_ORACLE_FRAGILITY_AUDIT_ID
        or data["protocol_id"] != preflight_data["protocol_id"]
        or data["board_id"] != preflight_data["board_id"]
    ):
        raise FrontierContractError("oracle fragility summary rebound provenance")
    _date(data["compiled_on"], "oracle fragility summary compiled_on")
    if (
        _sha256(
            data["public_preflight_integrity_sha256"],
            "oracle fragility public preflight commitment",
        )
        != preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("oracle fragility summary does not bind preflight")
    _sha256(data["private_report_commitment"], "oracle fragility report commitment")
    _sha256(data["integrity_sha256"], "oracle fragility summary integrity")
    if (
        data["component_localization_rule"] != FRONTIER_ORACLE_LOCALIZATION_RULE
        or data["support_selectivity_review_trigger"]
        != FRONTIER_ORACLE_SUPPORT_REVIEW_TRIGGER
        or data["lineage_redundancy_review_trigger"]
        != FRONTIER_ORACLE_LINEAGE_REVIEW_TRIGGER
    ):
        raise FrontierContractError("oracle fragility summary changed frozen rules")
    counts = {
        field_name: _integer(
            data[field_name], f"oracle fragility summary {field_name}"
        )
        for field_name in _AGGREGATE_FIELDS
    }
    if counts["canonical_stage_count"] != 60:
        raise FrontierContractError("oracle fragility requires sixty stages")
    if counts["planned_component_probe_count"] != 300:
        raise FrontierContractError("oracle fragility requires three hundred probes")
    if (
        counts["applicable_component_probe_count"]
        + counts["nonapplicable_component_probe_count"]
        != counts["planned_component_probe_count"]
    ):
        raise FrontierContractError("oracle fragility probe counts do not close")
    bounded_by_stage = {
        "component_localization_pass_count": counts[
            "applicable_component_probe_count"
        ],
        "witness_saturated_stage_count": 60,
        "task_wide_witness_saturation_count": 10,
        "repeated_lineage_witness_stage_count": 60,
        "context_witness_stage_count": 60,
        "derivative_witness_stage_count": 60,
        "decision_record_witness_stage_count": 60,
        "contradiction_witness_stage_count": 60,
        "singleton_blocker_stage_count": 60,
        "action_change_without_witness_delta_count": 50,
        "witness_change_without_action_delta_count": 50,
    }
    for field_name, maximum in bounded_by_stage.items():
        if counts[field_name] > maximum:
            raise FrontierContractError(
                f"oracle fragility summary {field_name} exceeds {maximum}"
            )
    if (
        counts["task_wide_witness_saturation_count"] * 6
        > counts["witness_saturated_stage_count"]
    ):
        raise FrontierContractError(
            "oracle fragility task-wide saturation exceeds saturated stages"
        )
    if (counts["witness_saturated_stage_count"] == 60) != (
        counts["accessible_nonwitness_evidence_count"] == 0
    ):
        raise FrontierContractError(
            "oracle fragility saturation and non-witness counts are inconsistent"
        )
    if (counts["witness_saturated_stage_count"] == 60) != (
        counts["task_wide_witness_saturation_count"] == 10
    ):
        raise FrontierContractError(
            "oracle fragility stage and task saturation counts are inconsistent"
        )
    if (
        counts["repeated_lineage_witness_id_count"]
        < counts["repeated_lineage_witness_stage_count"]
    ):
        raise FrontierContractError(
            "oracle fragility repeated-lineage counts are inconsistent"
        )
    localization_ready = (
        counts["applicable_component_probe_count"] > 0
        and counts["component_localization_pass_count"]
        == counts["applicable_component_probe_count"]
    )
    support_review = counts["task_wide_witness_saturation_count"] > 0
    lineage_review = counts["repeated_lineage_witness_stage_count"] > 0
    support_ready = localization_ready and not support_review and not lineage_review
    expected_booleans = {
        "component_localization_ready": localization_ready,
        "support_selectivity_review_required": support_review,
        "lineage_redundancy_review_required": lineage_review,
        "oracle_support_ready_for_independent_challenge": support_ready,
        "human_curation_required": not support_ready,
    }
    for field_name, expected in expected_booleans.items():
        if _boolean(data[field_name], f"oracle fragility summary {field_name}") != expected:
            raise FrontierContractError(
                f"oracle fragility summary {field_name} is inconsistent"
            )
    expected_status = (
        "machine_audit_complete_support_ready"
        if support_ready
        else "machine_audit_complete_support_revision_required"
    )
    if data["status"] != expected_status:
        raise FrontierContractError("oracle fragility summary status is inconsistent")
    for field_name in (
        "scientific_minimality_established",
        "independent_review_complete",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"oracle fragility summary {field_name}"):
            raise FrontierContractError(
                f"oracle fragility summary {field_name} must remain false"
            )
    if _integer(data["board_admitted_count"], "oracle fragility board count") != 0:
        raise FrontierContractError("oracle fragility cannot claim board admission")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "oracle fragility nonclaims"))
    ):
        raise FrontierContractError("oracle fragility summary removed a nonclaim")
    if data["integrity_sha256"] != frontier_oracle_fragility_summary_integrity_sha256(
        data
    ):
        raise FrontierContractError("oracle fragility summary integrity mismatch")
    return data


def validate_frontier_oracle_fragility_private_opening(
    *,
    private_report: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_frontier_oracle_fragility_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if (
        private_report.get("integrity_sha256")
        != frontier_oracle_fragility_report_integrity_sha256(private_report)
    ):
        raise FrontierContractError("oracle fragility private report integrity mismatch")
    expected_report, expected_summary = compile_frontier_oracle_fragility_artifacts(
        task_set=task_set,
        oracle_set=oracle_set,
        private_preflight=private_preflight,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        compiled_on=data["compiled_on"],
    )
    if private_report != expected_report or public_summary != expected_summary:
        raise FrontierContractError(
            "oracle fragility artifacts do not replay from committed inputs"
        )
    return oracle_fragility_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_oracle_fragility_commitment_opened": True}


def load_frontier_oracle_fragility_report(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "oracle fragility report")


def load_frontier_oracle_fragility_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_oracle_fragility_summary(
        _load_json(path.read_text(encoding="utf-8"), "oracle fragility summary"),
        **kwargs,
    )


def oracle_fragility_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_oracle_fragility_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "canonical_stage_count": data["canonical_stage_count"],
        "planned_component_probe_count": data["planned_component_probe_count"],
        "applicable_component_probe_count": data[
            "applicable_component_probe_count"
        ],
        "component_localization_pass_count": data[
            "component_localization_pass_count"
        ],
        "witness_saturated_stage_count": data["witness_saturated_stage_count"],
        "task_wide_witness_saturation_count": data[
            "task_wide_witness_saturation_count"
        ],
        "repeated_lineage_witness_stage_count": data[
            "repeated_lineage_witness_stage_count"
        ],
        "component_localization_ready": data["component_localization_ready"],
        "oracle_support_ready_for_independent_challenge": data[
            "oracle_support_ready_for_independent_challenge"
        ],
        "human_curation_required": data["human_curation_required"],
        "admission_gate_changed": data["admission_gate_changed"],
        "integrity_sha256": data["integrity_sha256"],
    }
