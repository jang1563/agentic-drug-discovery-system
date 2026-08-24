"""Machine-generated support-ablation packets for human oracle curation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .frontier import (
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
from .frontier_oracle_fragility import (
    validate_frontier_oracle_fragility_private_opening,
    validate_frontier_oracle_fragility_summary,
)
from .frontier_preflight import (
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)
from .frontier_tasks import FRONTIER_EVIDENCE_ROLES, score_frontier_stage_components


FRONTIER_SUPPORT_CURATION_PACKET_SET_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-support-curation-packet-set.v1"
)
FRONTIER_SUPPORT_CURATION_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-oracle-support-curation-summary.v1"
)
FRONTIER_SUPPORT_CURATION_ID = "adds-frontier-oracle-support-curation-v1"
FRONTIER_SUPPORT_ABLATION_RULE = (
    "leave_one_witness_out_only_when_at_least_one_witness_remains"
)
FRONTIER_SUPPORT_PRIORITY_RULE = (
    "repeated_lineage_members_before_other_witness_saturation_candidates"
)
_SCORE_KEYS = (
    "disposition_correct",
    "next_action_correct",
    "risk_flags_correct",
    "witness_valid",
    "blocker_certificate_valid",
)
_PUBLIC_NONCLAIMS = {
    "A leave-one-out candidate is a review workload item, not a recommendation to remove evidence.",
    "Exact scorer rejection reflects the frozen author-oracle witness set, not scientific necessity.",
    "Evidence roles and repeated lineages prioritize inspection but do not establish relevance or independence.",
    "Machine-generated packets cannot revise author oracles or satisfy human curation gates.",
    "No private task, oracle, evidence identity, lineage identity, stage record, or candidate payload is public.",
    "No challenge assignment, model run, benchmark result, or board admission is authorized.",
}
_COUNT_FIELDS = {
    "task_packet_count",
    "canonical_stage_count",
    "planned_ablation_candidate_count",
    "applicable_ablation_candidate_count",
    "nonapplicable_ablation_candidate_count",
    "ablation_localization_pass_count",
    "witness_saturated_stage_count",
    "repeated_lineage_group_count",
    "lineage_redundancy_candidate_count",
    "support_selectivity_candidate_count",
    "protected_singleton_candidate_count",
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


def frontier_support_curation_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_support_curation_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _candidate_id(*, task_id: str, stage_id: str, evidence_id: str) -> str:
    digest = hashlib.sha256(
        f"{FRONTIER_SUPPORT_CURATION_ID}:{task_id}:{stage_id}:{evidence_id}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"ablation-{digest[:24]}"


def _baseline_action(expectation: Mapping[str, Any]) -> FrontierAction:
    action = expectation["action"]
    return FrontierAction(
        disposition=action["disposition"],
        next_action=action["next_action"],
        risk_flags=tuple(action["risk_flags"]),
    )


def compile_frontier_support_curation_artifacts(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile deterministic review candidates without changing oracle labels."""

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
    validate_frontier_oracle_fragility_private_opening(
        private_report=private_fragility_report,
        public_summary=fragility_data,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight_data,
        public_preflight=public_preflight_data,
        progress=progress_data,
        **validation_kwargs,
    )
    if fragility_data["oracle_support_ready_for_independent_challenge"]:
        raise FrontierContractError(
            "support curation packets require an unresolved fragility review trigger"
        )
    _date(compiled_on, "support curation compiled_on")

    packets: list[dict[str, Any]] = []
    aggregate: Counter[str] = Counter()
    occurrence_role_counts: Counter[str] = Counter()
    applicable_role_counts: Counter[str] = Counter()
    candidate_ids: set[str] = set()
    for task, oracle in zip(
        tasks_data["tasks"], oracles_data["oracles"], strict=True
    ):
        evidence_by_id = {
            evidence["evidence_id"]: evidence for evidence in task["evidence_nodes"]
        }
        stage_records: list[dict[str, Any]] = []
        for stage, expectation in zip(
            task["stages"], oracle["stage_expectations"], strict=True
        ):
            witness_ids = list(expectation["witness_evidence_ids"])
            witness_set = set(witness_ids)
            lineage_counts = Counter(
                evidence_by_id[evidence_id]["lineage_id"]
                for evidence_id in witness_ids
            )
            repeated_lineage_group_count = sum(
                count > 1 for count in lineage_counts.values()
            )
            aggregate["repeated_lineage_group_count"] += (
                repeated_lineage_group_count
            )
            saturated = witness_set == set(stage["accessible_evidence_ids"])
            aggregate["witness_saturated_stage_count"] += saturated
            candidates: list[dict[str, Any]] = []
            for evidence_id in witness_ids:
                evidence = evidence_by_id[evidence_id]
                role = evidence["evidence_role"]
                same_lineage_count = lineage_counts[evidence["lineage_id"]]
                applicable = len(witness_ids) > 1
                candidate_id = _candidate_id(
                    task_id=task["task_id"],
                    stage_id=stage["stage_id"],
                    evidence_id=evidence_id,
                )
                if candidate_id in candidate_ids:
                    raise FrontierContractError(
                        "support curation candidate identifiers must be unique"
                    )
                candidate_ids.add(candidate_id)
                aggregate["planned_ablation_candidate_count"] += 1
                occurrence_role_counts[role] += 1
                reason_codes = ["witness_saturated_stage"] if saturated else []
                if same_lineage_count > 1:
                    reason_codes.append("repeated_lineage_member")
                if not applicable:
                    reason_codes.append("would_leave_empty_witness_set")

                if applicable:
                    ablated_witness_ids = [
                        item for item in witness_ids if item != evidence_id
                    ]
                    scores = score_frontier_stage_components(
                        expectation,
                        action=_baseline_action(expectation),
                        witness_evidence_ids=ablated_witness_ids,
                        blocker_codes=list(expectation["blocker_codes"]),
                    )
                    localized = (
                        scores["witness_valid"] is False
                        and all(
                            scores[key]
                            for key in _SCORE_KEYS
                            if key != "witness_valid"
                        )
                    )
                    if not localized:
                        raise FrontierContractError(
                            "support ablation did not localize to witness_valid"
                        )
                    aggregate["applicable_ablation_candidate_count"] += 1
                    aggregate["ablation_localization_pass_count"] += localized
                    applicable_role_counts[role] += 1
                    if same_lineage_count > 1:
                        priority = "lineage_redundancy_review"
                        aggregate[
                            "lineage_redundancy_candidate_count"
                        ] += 1
                    else:
                        priority = "support_selectivity_review"
                        aggregate[
                            "support_selectivity_candidate_count"
                        ] += 1
                    nonapplicability_reason = None
                else:
                    ablated_witness_ids = None
                    scores = None
                    localized = False
                    priority = "protected_singleton"
                    nonapplicability_reason = "would_leave_empty_witness_set"
                    aggregate["nonapplicable_ablation_candidate_count"] += 1
                    aggregate["protected_singleton_candidate_count"] += 1

                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "evidence_id": evidence_id,
                        "evidence_role": role,
                        "lineage_id": evidence["lineage_id"],
                        "same_lineage_witness_count": same_lineage_count,
                        "review_priority": priority,
                        "reason_codes": reason_codes,
                        "ablation_applicable": applicable,
                        "nonapplicability_reason": nonapplicability_reason,
                        "counterfactual_witness_evidence_ids": ablated_witness_ids,
                        "score_results": scores,
                        "isolated_witness_failure": localized,
                        "scientific_removal_supported": False,
                        "automatic_oracle_edit_authorized": False,
                    }
                )
            aggregate["canonical_stage_count"] += 1
            stage_records.append(
                {
                    "stage_id": stage["stage_id"],
                    "accessible_evidence_count": len(
                        stage["accessible_evidence_ids"]
                    ),
                    "witness_count": len(witness_ids),
                    "witness_saturated": saturated,
                    "witness_lineage_count": len(lineage_counts),
                    "repeated_lineage_group_count": repeated_lineage_group_count,
                    "candidates": candidates,
                }
            )
        packets.append(
            {
                "slot_id": task["slot_id"],
                "task_id": task["task_id"],
                "canonical_task_commitment": frontier_calibration_task_sha256(
                    task
                ),
                "author_oracle_commitment": frontier_calibration_oracle_sha256(
                    oracle
                ),
                "stage_records": stage_records,
            }
        )

    aggregate["task_packet_count"] = len(packets)
    for field_name in _COUNT_FIELDS:
        aggregate[field_name] += 0
    localization_ready = (
        aggregate["applicable_ablation_candidate_count"] > 0
        and aggregate["ablation_localization_pass_count"]
        == aggregate["applicable_ablation_candidate_count"]
    )
    role_counts = {
        role: occurrence_role_counts[role] for role in FRONTIER_EVIDENCE_ROLES
    }
    applicable_counts = {
        role: applicable_role_counts[role] for role in FRONTIER_EVIDENCE_ROLES
    }
    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_SUPPORT_CURATION_PACKET_SET_SCHEMA_VERSION,
        "curation_id": FRONTIER_SUPPORT_CURATION_ID,
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
        "support_ablation_rule": FRONTIER_SUPPORT_ABLATION_RULE,
        "review_priority_rule": FRONTIER_SUPPORT_PRIORITY_RULE,
        "packets": packets,
        **dict(aggregate),
        "witness_occurrence_role_counts": role_counts,
        "applicable_candidate_role_counts": applicable_counts,
        "machine_ablation_localization_ready": localization_ready,
        "oracle_revision_applied": False,
        "human_review_assignment_count": 0,
        "human_decision_count": 0,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = (
        frontier_support_curation_packet_set_integrity_sha256(packet_set)
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_SUPPORT_CURATION_SUMMARY_SCHEMA_VERSION,
        "curation_id": FRONTIER_SUPPORT_CURATION_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "machine_packets_ready_human_curation_unassigned",
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data[
            "integrity_sha256"
        ],
        "public_fragility_summary_integrity_sha256": fragility_data[
            "integrity_sha256"
        ],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "support_ablation_rule": FRONTIER_SUPPORT_ABLATION_RULE,
        "review_priority_rule": FRONTIER_SUPPORT_PRIORITY_RULE,
        **dict(aggregate),
        "witness_occurrence_role_counts": role_counts,
        "applicable_candidate_role_counts": applicable_counts,
        "machine_ablation_localization_ready": localization_ready,
        "curation_packets_ready_for_human_review": localization_ready,
        "human_curation_required": True,
        "oracle_revision_applied": False,
        "oracle_support_ready_for_independent_challenge": False,
        "human_review_assignment_count": 0,
        "human_decision_count": 0,
        "challenge_assignment_authorized": False,
        "scientific_minimality_established": False,
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
        frontier_support_curation_summary_integrity_sha256(summary)
    )
    return packet_set, summary


def _role_counts(value: Any, path: str) -> dict[str, int]:
    data = _record(value, path, set(FRONTIER_EVIDENCE_ROLES))
    return {
        role: _integer(data[role], f"{path}.{role}")
        for role in FRONTIER_EVIDENCE_ROLES
    }


def validate_frontier_support_curation_summary(
    summary: Mapping[str, Any],
    *,
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
    fields = {
        "schema_version",
        "curation_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "public_fragility_summary_integrity_sha256",
        "private_packet_set_commitment",
        "support_ablation_rule",
        "review_priority_rule",
        *_COUNT_FIELDS,
        "witness_occurrence_role_counts",
        "applicable_candidate_role_counts",
        "machine_ablation_localization_ready",
        "curation_packets_ready_for_human_review",
        "human_curation_required",
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "human_review_assignment_count",
        "human_decision_count",
        "challenge_assignment_authorized",
        "scientific_minimality_established",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "support_curation_summary", fields)
    if data["schema_version"] != FRONTIER_SUPPORT_CURATION_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported support curation summary schema")
    if (
        data["curation_id"] != FRONTIER_SUPPORT_CURATION_ID
        or data["protocol_id"] != fragility_data["protocol_id"]
        or data["board_id"] != fragility_data["board_id"]
    ):
        raise FrontierContractError("support curation summary rebound provenance")
    if data["status"] != "machine_packets_ready_human_curation_unassigned":
        raise FrontierContractError("support curation summary status is invalid")
    _date(data["compiled_on"], "support curation summary compiled_on")
    if (
        _sha256(
            data["public_preflight_integrity_sha256"],
            "support curation public preflight commitment",
        )
        != preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("support curation summary does not bind preflight")
    if (
        _sha256(
            data["public_fragility_summary_integrity_sha256"],
            "support curation public fragility commitment",
        )
        != fragility_data["integrity_sha256"]
    ):
        raise FrontierContractError("support curation summary does not bind fragility")
    _sha256(data["private_packet_set_commitment"], "support curation packet set")
    _sha256(data["integrity_sha256"], "support curation summary integrity")
    if (
        data["support_ablation_rule"] != FRONTIER_SUPPORT_ABLATION_RULE
        or data["review_priority_rule"] != FRONTIER_SUPPORT_PRIORITY_RULE
    ):
        raise FrontierContractError("support curation summary changed frozen rules")
    counts = {
        name: _integer(data[name], f"support curation summary {name}")
        for name in _COUNT_FIELDS
    }
    if counts["task_packet_count"] != 10 or counts["canonical_stage_count"] != 60:
        raise FrontierContractError("support curation requires ten tasks and sixty stages")
    if (
        counts["applicable_ablation_candidate_count"]
        + counts["nonapplicable_ablation_candidate_count"]
        != counts["planned_ablation_candidate_count"]
    ):
        raise FrontierContractError("support curation candidate counts do not close")
    if (
        counts["lineage_redundancy_candidate_count"]
        + counts["support_selectivity_candidate_count"]
        != counts["applicable_ablation_candidate_count"]
    ):
        raise FrontierContractError("support curation review-priority counts do not close")
    if (
        counts["protected_singleton_candidate_count"]
        != counts["nonapplicable_ablation_candidate_count"]
    ):
        raise FrontierContractError("support curation singleton counts do not close")
    if (
        counts["ablation_localization_pass_count"]
        > counts["applicable_ablation_candidate_count"]
    ):
        raise FrontierContractError("support curation localization passes exceed candidates")
    repeated_stage_count = fragility_data[
        "repeated_lineage_witness_stage_count"
    ]
    repeated_id_count = fragility_data["repeated_lineage_witness_id_count"]
    if not (
        repeated_stage_count
        <= counts["repeated_lineage_group_count"]
        <= repeated_id_count
    ):
        raise FrontierContractError(
            "support curation repeated-lineage groups do not bind fragility"
        )
    if counts["lineage_redundancy_candidate_count"] != (
        repeated_id_count + counts["repeated_lineage_group_count"]
    ):
        raise FrontierContractError(
            "support curation repeated-lineage candidates do not bind fragility"
        )
    if (
        counts["witness_saturated_stage_count"]
        != fragility_data["witness_saturated_stage_count"]
    ):
        raise FrontierContractError("support curation saturation does not bind fragility")
    occurrence_roles = _role_counts(
        data["witness_occurrence_role_counts"],
        "support curation witness occurrence roles",
    )
    applicable_roles = _role_counts(
        data["applicable_candidate_role_counts"],
        "support curation applicable candidate roles",
    )
    if sum(occurrence_roles.values()) != counts["planned_ablation_candidate_count"]:
        raise FrontierContractError("support curation occurrence role counts do not close")
    if sum(applicable_roles.values()) != counts["applicable_ablation_candidate_count"]:
        raise FrontierContractError("support curation applicable role counts do not close")
    if any(
        applicable_roles[role] > occurrence_roles[role]
        for role in FRONTIER_EVIDENCE_ROLES
    ):
        raise FrontierContractError("support curation role subsets are inconsistent")
    localization_ready = (
        counts["applicable_ablation_candidate_count"] > 0
        and counts["ablation_localization_pass_count"]
        == counts["applicable_ablation_candidate_count"]
    )
    for field_name in (
        "machine_ablation_localization_ready",
        "curation_packets_ready_for_human_review",
    ):
        if _boolean(data[field_name], f"support curation {field_name}") != (
            localization_ready
        ):
            raise FrontierContractError(f"support curation {field_name} is inconsistent")
    if not _boolean(data["human_curation_required"], "support curation human gate"):
        raise FrontierContractError("support curation must retain human curation")
    for field_name in (
        "oracle_revision_applied",
        "oracle_support_ready_for_independent_challenge",
        "challenge_assignment_authorized",
        "scientific_minimality_established",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"support curation {field_name}"):
            raise FrontierContractError(f"support curation {field_name} must remain false")
    for field_name in (
        "human_review_assignment_count",
        "human_decision_count",
        "board_admitted_count",
    ):
        if _integer(data[field_name], f"support curation {field_name}") != 0:
            raise FrontierContractError(f"support curation {field_name} must remain zero")
    if fragility_data["oracle_support_ready_for_independent_challenge"]:
        raise FrontierContractError("support curation cannot override ready fragility state")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "support curation nonclaims"))
    ):
        raise FrontierContractError("support curation summary removed a nonclaim")
    if data["integrity_sha256"] != frontier_support_curation_summary_integrity_sha256(
        data
    ):
        raise FrontierContractError("support curation summary integrity mismatch")
    return data


def validate_frontier_support_curation_private_opening(
    *,
    private_packet_set: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_frontier_support_curation_summary(
        public_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if (
        private_packet_set.get("integrity_sha256")
        != frontier_support_curation_packet_set_integrity_sha256(private_packet_set)
    ):
        raise FrontierContractError("support curation private packet integrity mismatch")
    expected_packets, expected_summary = compile_frontier_support_curation_artifacts(
        task_set=task_set,
        oracle_set=oracle_set,
        private_preflight=private_preflight,
        public_preflight=public_preflight,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=public_fragility_summary,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        compiled_on=data["compiled_on"],
    )
    if private_packet_set != expected_packets or public_summary != expected_summary:
        raise FrontierContractError(
            "support curation artifacts do not replay from committed inputs"
        )
    return support_curation_summary(
        public_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_support_curation_commitment_opened": True}


def load_frontier_support_curation_packet_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "support curation packets")


def load_frontier_support_curation_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_support_curation_summary(
        _load_json(path.read_text(encoding="utf-8"), "support curation summary"),
        **kwargs,
    )


def support_curation_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_support_curation_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "task_packet_count": data["task_packet_count"],
        "canonical_stage_count": data["canonical_stage_count"],
        "planned_ablation_candidate_count": data[
            "planned_ablation_candidate_count"
        ],
        "applicable_ablation_candidate_count": data[
            "applicable_ablation_candidate_count"
        ],
        "protected_singleton_candidate_count": data[
            "protected_singleton_candidate_count"
        ],
        "lineage_redundancy_candidate_count": data[
            "lineage_redundancy_candidate_count"
        ],
        "ablation_localization_pass_count": data[
            "ablation_localization_pass_count"
        ],
        "curation_packets_ready_for_human_review": data[
            "curation_packets_ready_for_human_review"
        ],
        "oracle_support_ready_for_independent_challenge": data[
            "oracle_support_ready_for_independent_challenge"
        ],
        "challenge_assignment_authorized": data[
            "challenge_assignment_authorized"
        ],
        "integrity_sha256": data["integrity_sha256"],
    }
