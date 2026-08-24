"""Deterministic preflight probes for private ADDS-Frontier calibration drafts."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import date, timedelta
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
    _sequence,
    _sha256,
    _text_list,
)
from .frontier_board import FRONTIER_ADMISSION_GATES
from .frontier_calibration import (
    FRONTIER_CALIBRATION_PROBE_KINDS,
    frontier_calibration_oracle_set_integrity_sha256,
    frontier_calibration_oracle_sha256,
    frontier_calibration_task_set_integrity_sha256,
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_private_opening,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_tasks import score_frontier_stage_components


FRONTIER_PRIVATE_PREFLIGHT_SCHEMA_VERSION = (
    "adds.frontier-private-calibration-preflight.v1"
)
FRONTIER_PUBLIC_PREFLIGHT_SCHEMA_VERSION = (
    "adds.frontier-calibration-preflight-summary.v1"
)
FRONTIER_PREFLIGHT_ID = "adds-frontier-calibration-preflight-v1"

_MACHINE_DECIDABLE_PROBES = {
    "source_id_rename",
    "critical_evidence_removal",
    "temporal_access_rebind",
}
_SEMANTIC_REVIEW_PROBES = {
    "bounded_evidence_reveal",
    "identity_rebind",
}
_EXPECTED_CONTRACT_OUTCOME = {
    "source_id_rename": "valid_invariant",
    "critical_evidence_removal": "fail_closed",
    "temporal_access_rebind": "fail_closed",
    "bounded_evidence_reveal": "structurally_valid_semantic_outcome_unresolved",
    "identity_rebind": "structurally_valid_semantic_outcome_unresolved",
}
_EXPECTED_PROBE_CLASS = {
    "source_id_rename": "nuisance_invariance",
    "critical_evidence_removal": "critical_flip",
    "temporal_access_rebind": "critical_flip",
    "bounded_evidence_reveal": "evidence_ladder",
    "identity_rebind": "critical_flip",
}
_EXPECTED_VALIDATOR_ERROR_CODE = {
    "source_id_rename": None,
    "critical_evidence_removal": "invalid_evidence_graph_or_access",
    "temporal_access_rebind": "post_cutoff_evidence_access",
    "bounded_evidence_reveal": None,
    "identity_rebind": None,
}
_STAGE_COMPONENTS = {
    "disposition_correct",
    "next_action_correct",
    "risk_flags_correct",
    "witness_valid",
    "blocker_certificate_valid",
}
_PRIVATE_NONCLAIMS = {
    "Canonical scorer round-trip is not independent expert solvability or scientific correctness.",
    "Structural mutation acceptance cannot establish the expected semantic action change.",
    "Automated preflight does not satisfy any human or board-admission gate.",
    "No model was run and no benchmark performance evidence was produced.",
}
_PUBLIC_NONCLAIMS = {
    "Sixty canonical stage checks are deterministic scorer round-trips, not expert solves.",
    "Twenty structurally accepted semantic probes still require independent oracle review.",
    "Automated preflight does not change independent-review or board-admission status.",
    "No private task, oracle, identity, nonce, curator, or canary bytes are published.",
    "No model run or benchmark performance evidence is claimed.",
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


def frontier_private_preflight_integrity_sha256(report: Mapping[str, Any]) -> str:
    return _canonical_sha256(report, exclude=frozenset({"integrity_sha256"}))


def frontier_public_preflight_integrity_sha256(summary: Mapping[str, Any]) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _rehash_task_set(task_set: dict[str, Any]) -> None:
    task_set["integrity_sha256"] = frontier_calibration_task_set_integrity_sha256(
        task_set
    )


def _rehash_oracle_set(
    oracle_set: dict[str, Any], *, task_set: Mapping[str, Any], task_index: int
) -> None:
    oracle_set["task_set_integrity_sha256"] = task_set["integrity_sha256"]
    oracle_set["oracles"][task_index]["task_sha256"] = frontier_calibration_task_sha256(
        task_set["tasks"][task_index]
    )
    oracle_set["integrity_sha256"] = frontier_calibration_oracle_set_integrity_sha256(
        oracle_set
    )


def _validate_mutated_sets(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    validation_kwargs: Mapping[str, Any],
) -> None:
    tasks_data = validate_frontier_calibration_task_set(
        task_set,
        **validation_kwargs,
    )
    validate_frontier_calibration_oracle_set(
        oracle_set,
        task_set=tasks_data,
        **validation_kwargs,
    )


def _rename_evidence_id(*, task: dict[str, Any], oracle: dict[str, Any]) -> None:
    old = task["evidence_nodes"][0]["evidence_id"]
    new = f"{old}-preflight-renamed"
    task["evidence_nodes"][0]["evidence_id"] = new
    for edge in task["lineage_edges"]:
        for field_name in ("parent_evidence_id", "child_evidence_id"):
            if edge[field_name] == old:
                edge[field_name] = new
    for stage in task["stages"]:
        stage["accessible_evidence_ids"] = [
            new if evidence_id == old else evidence_id
            for evidence_id in stage["accessible_evidence_ids"]
        ]
    for expectation in oracle["stage_expectations"]:
        expectation["witness_evidence_ids"] = [
            new if evidence_id == old else evidence_id
            for evidence_id in expectation["witness_evidence_ids"]
        ]


def _canonical_stage_results(
    task: Mapping[str, Any], oracle: Mapping[str, Any]
) -> list[dict[str, Any]]:
    results = []
    for stage, expectation in zip(
        task["stages"], oracle["stage_expectations"], strict=True
    ):
        action_data = expectation["action"]
        component_results = score_frontier_stage_components(
            expectation,
            action=FrontierAction(
                disposition=action_data["disposition"],
                next_action=action_data["next_action"],
                risk_flags=tuple(action_data["risk_flags"]),
            ),
            witness_evidence_ids=tuple(expectation["witness_evidence_ids"]),
            blocker_codes=tuple(expectation["blocker_codes"]),
        )
        results.append(
            {
                "stage_id": stage["stage_id"],
                "component_results": component_results,
                "round_trip_passed": all(component_results.values()),
            }
        )
    return results


def _run_mutation_probe(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    task_index: int,
    mutation: Mapping[str, Any],
    validation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    mutated_tasks = copy.deepcopy(task_set)
    mutated_oracles = copy.deepcopy(oracle_set)
    task = mutated_tasks["tasks"][task_index]
    oracle = mutated_oracles["oracles"][task_index]
    probe_kind = mutation["probe_kind"]
    expected_outcome = _EXPECTED_CONTRACT_OUTCOME[probe_kind]
    observed_outcome: str
    validator_error_code: str | None = None

    if probe_kind == "source_id_rename":
        _rename_evidence_id(task=task, oracle=oracle)
        _rehash_task_set(mutated_tasks)
        _rehash_oracle_set(
            mutated_oracles,
            task_set=mutated_tasks,
            task_index=task_index,
        )
        _validate_mutated_sets(
            task_set=mutated_tasks,
            oracle_set=mutated_oracles,
            validation_kwargs=validation_kwargs,
        )
        observed_outcome = "valid_invariant"
    elif probe_kind == "critical_evidence_removal":
        task["evidence_nodes"].pop()
        _rehash_task_set(mutated_tasks)
        try:
            validate_frontier_calibration_task_set(
                mutated_tasks,
                **validation_kwargs,
            )
        except FrontierContractError:
            observed_outcome = "fail_closed"
            validator_error_code = "invalid_evidence_graph_or_access"
        else:
            observed_outcome = "unexpectedly_valid"
    elif probe_kind == "temporal_access_rebind":
        first_stage_date = date.fromisoformat(task["stages"][0]["as_of_date"])
        task["evidence_nodes"][0]["available_on"] = (
            first_stage_date + timedelta(days=1)
        ).isoformat()
        _rehash_task_set(mutated_tasks)
        try:
            validate_frontier_calibration_task_set(
                mutated_tasks,
                **validation_kwargs,
            )
        except FrontierContractError:
            observed_outcome = "fail_closed"
            validator_error_code = "post_cutoff_evidence_access"
        else:
            observed_outcome = "unexpectedly_valid"
    elif probe_kind == "bounded_evidence_reveal":
        evidence_id = f"ev-{task['slot_id']}-preflight-reveal"
        task["evidence_nodes"].append(
            {
                "evidence_id": evidence_id,
                "available_on": task["stages"][3]["as_of_date"],
                "lineage_id": f"lineage-{task['slot_id']}-preflight-reveal",
                "evidence_role": "context",
                "evidence_summary": (
                    "Automated preflight evidence-ladder probe; not a scientific label."
                ),
            }
        )
        for stage in task["stages"][3:]:
            stage["accessible_evidence_ids"].append(evidence_id)
        _rehash_task_set(mutated_tasks)
        _rehash_oracle_set(
            mutated_oracles,
            task_set=mutated_tasks,
            task_index=task_index,
        )
        _validate_mutated_sets(
            task_set=mutated_tasks,
            oracle_set=mutated_oracles,
            validation_kwargs=validation_kwargs,
        )
        observed_outcome = "structurally_valid_semantic_outcome_unresolved"
    elif probe_kind == "identity_rebind":
        task["program_identity"] = (
            f"{task['program_identity']}|AUTOMATED_PREFLIGHT_REBIND"
        )
        _rehash_task_set(mutated_tasks)
        _rehash_oracle_set(
            mutated_oracles,
            task_set=mutated_tasks,
            task_index=task_index,
        )
        _validate_mutated_sets(
            task_set=mutated_tasks,
            oracle_set=mutated_oracles,
            validation_kwargs=validation_kwargs,
        )
        observed_outcome = "structurally_valid_semantic_outcome_unresolved"
    else:  # pragma: no cover - private oracle validation closes this branch
        raise FrontierContractError(f"unsupported calibration probe_kind: {probe_kind}")

    machine_decidable = probe_kind in _MACHINE_DECIDABLE_PROBES
    expected_outcome_matched = (
        observed_outcome == expected_outcome if machine_decidable else None
    )
    return {
        "mutation_id": mutation["mutation_id"],
        "mutation_class": mutation["mutation_class"],
        "probe_kind": probe_kind,
        "assessment_lane": (
            "machine_decidable" if machine_decidable else "semantic_review_required"
        ),
        "expected_contract_outcome": expected_outcome,
        "observed_contract_outcome": observed_outcome,
        "expected_outcome_matched": expected_outcome_matched,
        "validator_error_code": validator_error_code,
        "expected_changed_components": list(mutation["expected_changed_components"]),
    }


def run_frontier_calibration_preflight(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    run_on: str,
) -> dict[str, Any]:
    """Run deterministic probes while preserving every human gate as pending."""

    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    opening = validate_frontier_calibration_private_opening(
        progress=progress,
        task_set=task_set,
        oracle_set=oracle_set,
        **validation_kwargs,
    )
    if not opening["private_commitments_opened"]:
        raise FrontierContractError("private calibration commitments did not open")
    tasks_data = validate_frontier_calibration_task_set(
        task_set,
        **validation_kwargs,
    )
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set,
        task_set=tasks_data,
        **validation_kwargs,
    )
    progress_data = validate_frontier_calibration_progress(
        progress,
        **validation_kwargs,
    )
    _date(run_on, "calibration preflight run_on")

    task_results = []
    probe_kind_counts: Counter[str] = Counter()
    assessment_lane_counts: Counter[str] = Counter()
    observed_outcome_counts: Counter[str] = Counter()
    canonical_stage_count = 0
    canonical_stage_pass_count = 0
    machine_expected_match_count = 0
    for task_index, (task, oracle) in enumerate(
        zip(tasks_data["tasks"], oracles_data["oracles"], strict=True)
    ):
        canonical_results = _canonical_stage_results(task, oracle)
        mutation_results = []
        for mutation in oracle["mutation_expectations"]:
            result = _run_mutation_probe(
                task_set=tasks_data,
                oracle_set=oracles_data,
                task_index=task_index,
                mutation=mutation,
                validation_kwargs=validation_kwargs,
            )
            mutation_results.append(result)
            probe_kind_counts[result["probe_kind"]] += 1
            assessment_lane_counts[result["assessment_lane"]] += 1
            observed_outcome_counts[result["observed_contract_outcome"]] += 1
            machine_expected_match_count += result["expected_outcome_matched"] is True
        canonical_stage_count += len(canonical_results)
        canonical_stage_pass_count += sum(
            result["round_trip_passed"] for result in canonical_results
        )
        task_results.append(
            {
                "slot_id": task["slot_id"],
                "task_commitment": frontier_calibration_task_sha256(task),
                "oracle_commitment": frontier_calibration_oracle_sha256(oracle),
                "canonical_stage_results": canonical_results,
                "mutation_results": mutation_results,
            }
        )

    report: dict[str, Any] = {
        "schema_version": FRONTIER_PRIVATE_PREFLIGHT_SCHEMA_VERSION,
        "preflight_id": FRONTIER_PREFLIGHT_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "automated_preflight_complete_semantic_review_pending",
        "run_on": run_on,
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "progress_integrity_sha256": progress_data["integrity_sha256"],
        "task_results": task_results,
        "aggregate": {
            "task_count": len(task_results),
            "canonical_stage_count": canonical_stage_count,
            "canonical_stage_pass_count": canonical_stage_pass_count,
            "mutation_probe_count": sum(probe_kind_counts.values()),
            "machine_decidable_probe_count": assessment_lane_counts[
                "machine_decidable"
            ],
            "machine_expected_outcome_match_count": machine_expected_match_count,
            "semantic_review_required_probe_count": assessment_lane_counts[
                "semantic_review_required"
            ],
            "structurally_accepted_semantic_probe_count": observed_outcome_counts[
                "structurally_valid_semantic_outcome_unresolved"
            ],
            "probe_kind_counts": {
                kind: probe_kind_counts[kind]
                for kind in FRONTIER_CALIBRATION_PROBE_KINDS
            },
        },
        "human_review_required": True,
        "board_admission_unchanged": True,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "nonclaims": sorted(_PRIVATE_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    report["integrity_sha256"] = frontier_private_preflight_integrity_sha256(report)
    return report


def build_frontier_calibration_preflight_summary(
    *,
    private_report: Mapping[str, Any],
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
        progress,
        **validation_kwargs,
    )
    report = _validate_private_preflight_shape(private_report)
    if report["progress_integrity_sha256"] != progress_data["integrity_sha256"]:
        raise FrontierContractError("preflight report does not bind public progress")
    aggregate = report["aggregate"]
    gate_results = progress_data["records"][0]["admission_gate_results"]
    if any(
        record["admission_gate_results"] != gate_results
        for record in progress_data["records"]
    ):
        raise FrontierContractError("calibration slots have inconsistent gate states")
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_PUBLIC_PREFLIGHT_SCHEMA_VERSION,
        "preflight_id": FRONTIER_PREFLIGHT_ID,
        "protocol_id": progress_data["protocol_id"],
        "board_id": progress_data["board_id"],
        "status": report["status"],
        "run_on": report["run_on"],
        "progress_integrity_sha256": progress_data["integrity_sha256"],
        "private_preflight_report_commitment": report["integrity_sha256"],
        "task_count": aggregate["task_count"],
        "canonical_stage_count": aggregate["canonical_stage_count"],
        "canonical_stage_pass_count": aggregate["canonical_stage_pass_count"],
        "mutation_probe_count": aggregate["mutation_probe_count"],
        "machine_decidable_probe_count": aggregate["machine_decidable_probe_count"],
        "machine_expected_outcome_match_count": aggregate[
            "machine_expected_outcome_match_count"
        ],
        "semantic_review_required_probe_count": aggregate[
            "semantic_review_required_probe_count"
        ],
        "structurally_accepted_semantic_probe_count": aggregate[
            "structurally_accepted_semantic_probe_count"
        ],
        "probe_kind_counts": dict(aggregate["probe_kind_counts"]),
        "admission_gate_results": dict(gate_results),
        "independent_review_complete": False,
        "human_review_required": True,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = frontier_public_preflight_integrity_sha256(summary)
    return summary


def _validate_private_preflight_shape(
    private_report: Mapping[str, Any],
) -> dict[str, Any]:
    data = _record(
        private_report,
        "private_preflight",
        {
            "schema_version",
            "preflight_id",
            "protocol_id",
            "board_id",
            "status",
            "run_on",
            "task_set_integrity_sha256",
            "oracle_set_integrity_sha256",
            "progress_integrity_sha256",
            "task_results",
            "aggregate",
            "human_review_required",
            "board_admission_unchanged",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_PRIVATE_PREFLIGHT_SCHEMA_VERSION:
        raise FrontierContractError("unsupported private preflight schema_version")
    if data["preflight_id"] != FRONTIER_PREFLIGHT_ID:
        raise FrontierContractError("unexpected calibration preflight_id")
    if data["status"] != "automated_preflight_complete_semantic_review_pending":
        raise FrontierContractError("private preflight overstates current maturity")
    _date(data["run_on"], "private_preflight.run_on")
    for field_name in (
        "task_set_integrity_sha256",
        "oracle_set_integrity_sha256",
        "progress_integrity_sha256",
        "integrity_sha256",
    ):
        _sha256(data[field_name], f"private_preflight.{field_name}")
    task_results = _sequence(data["task_results"], "private_preflight.task_results")
    if len(task_results) != 10:
        raise FrontierContractError("private preflight must contain ten task results")
    slot_ids: set[str] = set()
    canonical_stage_count = 0
    canonical_stage_pass_count = 0
    mutation_probe_count = 0
    machine_decidable_probe_count = 0
    machine_expected_outcome_match_count = 0
    semantic_review_required_probe_count = 0
    structurally_accepted_semantic_probe_count = 0
    observed_probe_counts: Counter[str] = Counter()
    for task_index, task_item in enumerate(task_results):
        task_path = f"private_preflight.task_results[{task_index}]"
        task_result = _record(
            task_item,
            task_path,
            {
                "slot_id",
                "task_commitment",
                "oracle_commitment",
                "canonical_stage_results",
                "mutation_results",
            },
        )
        slot_id = task_result["slot_id"]
        if not isinstance(slot_id, str) or not slot_id.strip():
            raise FrontierContractError(f"{task_path}.slot_id must be non-empty text")
        if slot_id in slot_ids:
            raise FrontierContractError("private preflight has duplicate slot results")
        slot_ids.add(slot_id)
        _sha256(task_result["task_commitment"], f"{task_path}.task_commitment")
        _sha256(task_result["oracle_commitment"], f"{task_path}.oracle_commitment")

        stage_results = _sequence(
            task_result["canonical_stage_results"],
            f"{task_path}.canonical_stage_results",
        )
        if len(stage_results) != 6:
            raise FrontierContractError(f"{task_path} must contain six stage results")
        stage_ids: set[str] = set()
        for stage_index, stage_item in enumerate(stage_results):
            stage_path = f"{task_path}.canonical_stage_results[{stage_index}]"
            stage_result = _record(
                stage_item,
                stage_path,
                {"stage_id", "component_results", "round_trip_passed"},
            )
            stage_id = stage_result["stage_id"]
            if not isinstance(stage_id, str) or not stage_id.strip():
                raise FrontierContractError(
                    f"{stage_path}.stage_id must be non-empty text"
                )
            if stage_id in stage_ids:
                raise FrontierContractError(f"{task_path} has duplicate stage results")
            stage_ids.add(stage_id)
            components = _record(
                stage_result["component_results"],
                f"{stage_path}.component_results",
                _STAGE_COMPONENTS,
            )
            if not all(
                _boolean(value, f"{stage_path}.component_results.{component}")
                for component, value in components.items()
            ):
                raise FrontierContractError(
                    f"{stage_path} canonical components must all pass"
                )
            if not _boolean(
                stage_result["round_trip_passed"],
                f"{stage_path}.round_trip_passed",
            ):
                raise FrontierContractError(
                    f"{stage_path} canonical round-trip must pass"
                )
            canonical_stage_count += 1
            canonical_stage_pass_count += 1

        mutation_results = _sequence(
            task_result["mutation_results"], f"{task_path}.mutation_results"
        )
        if len(mutation_results) != len(FRONTIER_CALIBRATION_PROBE_KINDS):
            raise FrontierContractError(f"{task_path} must contain five probes")
        mutation_ids: set[str] = set()
        observed_kinds: list[str] = []
        for mutation_index, mutation_item in enumerate(mutation_results):
            mutation_path = f"{task_path}.mutation_results[{mutation_index}]"
            mutation_result = _record(
                mutation_item,
                mutation_path,
                {
                    "mutation_id",
                    "mutation_class",
                    "probe_kind",
                    "assessment_lane",
                    "expected_contract_outcome",
                    "observed_contract_outcome",
                    "expected_outcome_matched",
                    "validator_error_code",
                    "expected_changed_components",
                },
            )
            mutation_id = mutation_result["mutation_id"]
            if not isinstance(mutation_id, str) or not mutation_id.strip():
                raise FrontierContractError(
                    f"{mutation_path}.mutation_id must be non-empty text"
                )
            if mutation_id in mutation_ids:
                raise FrontierContractError(f"{task_path} has duplicate mutation ids")
            mutation_ids.add(mutation_id)
            probe_kind = mutation_result["probe_kind"]
            if probe_kind not in FRONTIER_CALIBRATION_PROBE_KINDS:
                raise FrontierContractError(f"{mutation_path} has unknown probe_kind")
            observed_kinds.append(probe_kind)
            if mutation_result["mutation_class"] != _EXPECTED_PROBE_CLASS[probe_kind]:
                raise FrontierContractError(
                    f"{mutation_path} probe_kind and mutation_class disagree"
                )
            expected_lane = (
                "machine_decidable"
                if probe_kind in _MACHINE_DECIDABLE_PROBES
                else "semantic_review_required"
            )
            if mutation_result["assessment_lane"] != expected_lane:
                raise FrontierContractError(f"{mutation_path} has the wrong lane")
            expected_outcome = _EXPECTED_CONTRACT_OUTCOME[probe_kind]
            if (
                mutation_result["expected_contract_outcome"] != expected_outcome
                or mutation_result["observed_contract_outcome"] != expected_outcome
            ):
                raise FrontierContractError(
                    f"{mutation_path} does not match its contract outcome"
                )
            expected_match = mutation_result["expected_outcome_matched"]
            if expected_lane == "machine_decidable":
                if not _boolean(
                    expected_match, f"{mutation_path}.expected_outcome_matched"
                ):
                    raise FrontierContractError(
                        f"{mutation_path} machine outcome must match"
                    )
                machine_decidable_probe_count += 1
                machine_expected_outcome_match_count += 1
            elif expected_match is not None:
                raise FrontierContractError(
                    f"{mutation_path} semantic outcome match must remain unresolved"
                )
            else:
                semantic_review_required_probe_count += 1
                structurally_accepted_semantic_probe_count += 1
            if (
                mutation_result["validator_error_code"]
                != _EXPECTED_VALIDATOR_ERROR_CODE[probe_kind]
            ):
                raise FrontierContractError(
                    f"{mutation_path} has an unexpected validator error code"
                )
            _text_list(
                mutation_result["expected_changed_components"],
                f"{mutation_path}.expected_changed_components",
                nonempty=probe_kind != "source_id_rename",
            )
            observed_probe_counts[probe_kind] += 1
            mutation_probe_count += 1
        if tuple(observed_kinds) != FRONTIER_CALIBRATION_PROBE_KINDS:
            raise FrontierContractError(
                f"{task_path} must preserve executable probe order"
            )
    aggregate = _record(
        data["aggregate"],
        "private_preflight.aggregate",
        {
            "task_count",
            "canonical_stage_count",
            "canonical_stage_pass_count",
            "mutation_probe_count",
            "machine_decidable_probe_count",
            "machine_expected_outcome_match_count",
            "semantic_review_required_probe_count",
            "structurally_accepted_semantic_probe_count",
            "probe_kind_counts",
        },
    )
    expected_counts = {
        "task_count": 10,
        "canonical_stage_count": 60,
        "canonical_stage_pass_count": 60,
        "mutation_probe_count": 50,
        "machine_decidable_probe_count": 30,
        "machine_expected_outcome_match_count": 30,
        "semantic_review_required_probe_count": 20,
        "structurally_accepted_semantic_probe_count": 20,
    }
    for field_name, expected in expected_counts.items():
        if (
            _integer(
                aggregate[field_name],
                f"private_preflight.aggregate.{field_name}",
                minimum=0,
            )
            != expected
        ):
            raise FrontierContractError(
                f"private preflight aggregate {field_name} must remain {expected}"
            )
    observed_aggregate = {
        "task_count": len(task_results),
        "canonical_stage_count": canonical_stage_count,
        "canonical_stage_pass_count": canonical_stage_pass_count,
        "mutation_probe_count": mutation_probe_count,
        "machine_decidable_probe_count": machine_decidable_probe_count,
        "machine_expected_outcome_match_count": machine_expected_outcome_match_count,
        "semantic_review_required_probe_count": semantic_review_required_probe_count,
        "structurally_accepted_semantic_probe_count": (
            structurally_accepted_semantic_probe_count
        ),
    }
    if any(
        aggregate[field_name] != observed
        for field_name, observed in observed_aggregate.items()
    ):
        raise FrontierContractError(
            "private preflight aggregate does not match detailed results"
        )
    probe_counts = _record(
        aggregate["probe_kind_counts"],
        "private_preflight.aggregate.probe_kind_counts",
        set(FRONTIER_CALIBRATION_PROBE_KINDS),
    )
    for probe_kind in FRONTIER_CALIBRATION_PROBE_KINDS:
        if (
            _integer(
                probe_counts[probe_kind],
                f"private_preflight.aggregate.probe_kind_counts.{probe_kind}",
                minimum=0,
            )
            != 10
        ):
            raise FrontierContractError(
                "every preflight probe kind must cover ten tasks"
            )
        if probe_counts[probe_kind] != observed_probe_counts[probe_kind]:
            raise FrontierContractError(
                "private preflight probe counts do not match detailed results"
            )
    for field_name in ("human_review_required", "board_admission_unchanged"):
        if not _boolean(data[field_name], f"private_preflight.{field_name}"):
            raise FrontierContractError(
                f"private_preflight.{field_name} must remain true"
            )
    for field_name in ("baseline_model_runs_started", "benchmark_evidence_claimed"):
        if _boolean(data[field_name], f"private_preflight.{field_name}"):
            raise FrontierContractError(
                f"private_preflight.{field_name} must remain false"
            )
    if not _PRIVATE_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "private_preflight.nonclaims"))
    ):
        raise FrontierContractError("private preflight removed a required nonclaim")
    if data["integrity_sha256"] != frontier_private_preflight_integrity_sha256(data):
        raise FrontierContractError("private preflight integrity mismatch")
    return data


def validate_frontier_private_preflight_report(
    private_report: Mapping[str, Any],
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    data = _validate_private_preflight_shape(private_report)
    expected = run_frontier_calibration_preflight(
        task_set=task_set,
        oracle_set=oracle_set,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        run_on=data["run_on"],
    )
    if expected != data:
        raise FrontierContractError(
            "private preflight report does not replay from committed calibration bytes"
        )
    return data


def validate_frontier_public_preflight_summary(
    summary: Mapping[str, Any],
    *,
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    progress_data = validate_frontier_calibration_progress(
        progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    data = _record(
        summary,
        "public_preflight",
        {
            "schema_version",
            "preflight_id",
            "protocol_id",
            "board_id",
            "status",
            "run_on",
            "progress_integrity_sha256",
            "private_preflight_report_commitment",
            "task_count",
            "canonical_stage_count",
            "canonical_stage_pass_count",
            "mutation_probe_count",
            "machine_decidable_probe_count",
            "machine_expected_outcome_match_count",
            "semantic_review_required_probe_count",
            "structurally_accepted_semantic_probe_count",
            "probe_kind_counts",
            "admission_gate_results",
            "independent_review_complete",
            "human_review_required",
            "board_admitted_count",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "private_payload_published",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_PUBLIC_PREFLIGHT_SCHEMA_VERSION:
        raise FrontierContractError("unsupported public preflight schema_version")
    if data["preflight_id"] != FRONTIER_PREFLIGHT_ID:
        raise FrontierContractError("unexpected public preflight_id")
    if (
        data["protocol_id"] != progress_data["protocol_id"]
        or data["board_id"] != progress_data["board_id"]
    ):
        raise FrontierContractError("public preflight rebound its protocol or board")
    if data["status"] != "automated_preflight_complete_semantic_review_pending":
        raise FrontierContractError("public preflight overstates current maturity")
    _date(data["run_on"], "public_preflight.run_on")
    if (
        _sha256(
            data["progress_integrity_sha256"],
            "public_preflight.progress_integrity_sha256",
        )
        != progress_data["integrity_sha256"]
    ):
        raise FrontierContractError(
            "public preflight does not bind calibration progress"
        )
    _sha256(
        data["private_preflight_report_commitment"],
        "public_preflight.private_preflight_report_commitment",
    )
    expected_counts = {
        "task_count": 10,
        "canonical_stage_count": 60,
        "canonical_stage_pass_count": 60,
        "mutation_probe_count": 50,
        "machine_decidable_probe_count": 30,
        "machine_expected_outcome_match_count": 30,
        "semantic_review_required_probe_count": 20,
        "structurally_accepted_semantic_probe_count": 20,
        "board_admitted_count": 0,
    }
    for field_name, expected in expected_counts.items():
        if (
            _integer(data[field_name], f"public_preflight.{field_name}", minimum=0)
            != expected
        ):
            raise FrontierContractError(
                f"public preflight {field_name} must remain {expected}"
            )
    probe_counts = _record(
        data["probe_kind_counts"],
        "public_preflight.probe_kind_counts",
        set(FRONTIER_CALIBRATION_PROBE_KINDS),
    )
    for probe_kind in FRONTIER_CALIBRATION_PROBE_KINDS:
        if (
            _integer(
                probe_counts[probe_kind],
                f"public_preflight.probe_kind_counts.{probe_kind}",
                minimum=0,
            )
            != 10
        ):
            raise FrontierContractError("every public probe kind must cover ten tasks")
    gate_results = _record(
        data["admission_gate_results"],
        "public_preflight.admission_gate_results",
        set(FRONTIER_ADMISSION_GATES),
    )
    if any(
        record["admission_gate_results"] != gate_results
        for record in progress_data["records"]
    ):
        raise FrontierContractError("public preflight changed admission gate results")
    for field_name in (
        "independent_review_complete",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"public_preflight.{field_name}"):
            raise FrontierContractError(
                f"public_preflight.{field_name} must remain false"
            )
    if not _boolean(
        data["human_review_required"], "public_preflight.human_review_required"
    ):
        raise FrontierContractError("public preflight must retain human review")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "public_preflight.nonclaims"))
    ):
        raise FrontierContractError("public preflight removed a required nonclaim")
    expected_integrity = _sha256(
        data["integrity_sha256"], "public_preflight.integrity_sha256"
    )
    actual_integrity = frontier_public_preflight_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError("public preflight integrity mismatch")
    return data


def validate_frontier_preflight_private_opening(
    *,
    private_report: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    report = validate_frontier_private_preflight_report(
        private_report,
        task_set=task_set,
        oracle_set=oracle_set,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    summary = validate_frontier_public_preflight_summary(
        public_summary,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    expected_summary = build_frontier_calibration_preflight_summary(
        private_report=report,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if summary != expected_summary:
        raise FrontierContractError(
            "private preflight report does not open the public aggregate commitment"
        )
    return frontier_preflight_summary(
        summary,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_preflight_commitment_opened": True}


def load_frontier_private_preflight_report(path: Path, **kwargs: Any) -> dict[str, Any]:
    return validate_frontier_private_preflight_report(
        _load_json(path.read_text(encoding="utf-8"), "private preflight report"),
        **kwargs,
    )


def load_frontier_public_preflight_summary(path: Path, **kwargs: Any) -> dict[str, Any]:
    return validate_frontier_public_preflight_summary(
        _load_json(path.read_text(encoding="utf-8"), "public preflight summary"),
        **kwargs,
    )


def frontier_preflight_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_public_preflight_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "task_count": data["task_count"],
        "canonical_stage_round_trip": (
            f"{data['canonical_stage_pass_count']}/{data['canonical_stage_count']}"
        ),
        "mutation_probe_count": data["mutation_probe_count"],
        "machine_decidable_probe_count": data["machine_decidable_probe_count"],
        "machine_expected_outcome_match_count": data[
            "machine_expected_outcome_match_count"
        ],
        "semantic_review_required_probe_count": data[
            "semantic_review_required_probe_count"
        ],
        "structurally_accepted_semantic_probe_count": data[
            "structurally_accepted_semantic_probe_count"
        ],
        "independent_review_complete": data["independent_review_complete"],
        "human_review_required": data["human_review_required"],
        "board_admitted_count": data["board_admitted_count"],
        "baseline_model_runs_started": data["baseline_model_runs_started"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
