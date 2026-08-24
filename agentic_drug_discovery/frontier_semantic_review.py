"""Blinded semantic-review packets for unresolved ADDS-Frontier probes."""

from __future__ import annotations

import copy
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
from .frontier_board import FRONTIER_ADMISSION_GATES
from .frontier_calibration import (
    frontier_calibration_oracle_set_integrity_sha256,
    frontier_calibration_task_set_integrity_sha256,
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_preflight import (
    validate_frontier_private_preflight_report,
    validate_frontier_public_preflight_summary,
)


FRONTIER_SEMANTIC_PACKET_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-packet-set.v1"
)
FRONTIER_SEMANTIC_KEY_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-key-set.v1"
)
FRONTIER_SEMANTIC_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-semantic-review-readiness-summary.v1"
)
FRONTIER_SEMANTIC_REVIEW_SET_ID = "adds-frontier-semantic-review-v1"

_SEMANTIC_PROBE_KINDS = ("bounded_evidence_reveal", "identity_rebind")
_REVIEW_DIMENSIONS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_REVIEW_VIEW_FIELDS = {
    "family_id",
    "disease_domain",
    "temporal_regime",
    "disease_identity",
    "program_identity",
    "prompt",
    "anchor_cutoff_date",
    "stage_budget",
    "tool_call_budget",
    "authoring_source_artifacts",
    "evidence_nodes",
    "lineage_edges",
    "stages",
}
_EVIDENCE_REVEAL_SUMMARIES = {
    "evidence_lineage_trap": (
        "Synthetic counterfactual independent replication with no shared source, "
        "recruitment, or analysis lineage corroborates the decision-relevant effect."
    ),
    "temporal_reversal": (
        "Synthetic counterfactual primary evidence becomes eligible at this stage "
        "and resolves the previously unavailable outcome state."
    ),
    "translational_handoff": (
        "Synthetic counterfactual matched-context validation preserves candidate, "
        "target, assay, exposure, endpoint, and population identities."
    ),
    "non_exchangeable_replication": (
        "Synthetic counterfactual independent trial matches the reviewed population, "
        "endpoint, exposure, follow-up, and safety denominator."
    ),
    "budgeted_evidence_resolution": (
        "Synthetic counterfactual budget-eligible primary source resolves one current "
        "decision blocker without asserting resolution of other blockers."
    ),
}
_PACKET_NONCLAIMS = {
    "Packet compilation and exact structural deltas are not semantic judgments.",
    "Synthetic counterfactual evidence is not a factual scientific source.",
    "Canonical arm identity and author expectations are absent from reviewer packets.",
    "Arm-order blinding does not guarantee canonical role is non-inferable from payload semantics.",
    "No reviewer response, consensus label, board admission, or model result is claimed.",
}
_PUBLIC_NONCLAIMS = {
    "Twenty packets are machine-compiled drafts, not independently reviewed labels.",
    "Structural delta certification does not establish a correct action change.",
    "No canonical-arm mapping, task, oracle, identity, nonce, or reviewer bytes are public.",
    "Arm-order blinding does not guarantee canonical role is non-inferable from private payload semantics.",
    "No reviewer was assigned and no consensus or adjudication exists.",
    "No board admission, model run, or benchmark performance is claimed.",
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


def frontier_semantic_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_key_set_integrity_sha256(
    key_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(key_set, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_review_view(task: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact task projection permitted in a blinded review arm."""

    return {
        field_name: copy.deepcopy(task[field_name])
        for field_name in sorted(_REVIEW_VIEW_FIELDS)
    }


def _materialize_evidence_reveal(task: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(task)
    token = hashlib.sha256(
        f"{task['slot_id']}|bounded-evidence-reveal".encode("utf-8")
    ).hexdigest()[:16]
    evidence_id = f"ev-counterfactual-{token}"
    mutated["evidence_nodes"].append(
        {
            "evidence_id": evidence_id,
            "available_on": mutated["stages"][3]["as_of_date"],
            "lineage_id": f"lineage-counterfactual-{token}",
            "evidence_role": "source",
            "evidence_summary": _EVIDENCE_REVEAL_SUMMARIES[task["family_id"]],
        }
    )
    for stage in mutated["stages"][3:]:
        stage["accessible_evidence_ids"].append(evidence_id)
    return mutated


def _materialize_identity_rebind(
    task: Mapping[str, Any], *, candidate_tasks: list[Mapping[str, Any]]
) -> dict[str, Any]:
    alternatives = [
        candidate
        for candidate in candidate_tasks
        if candidate["disease_domain"] == task["disease_domain"]
        and candidate["program_identity"] != task["program_identity"]
    ]
    if not alternatives:
        raise FrontierContractError("identity rebind requires an alternate program")
    alternatives.sort(key=lambda candidate: candidate["slot_id"])
    selected = alternatives[0]
    original_parts = task["program_identity"].split("|")
    selected_parts = selected["program_identity"].split("|")
    existing_identities = {
        candidate["program_identity"] for candidate in candidate_tasks
    }
    candidates = []
    if len(original_parts) > 1 and len(selected_parts) > 1:
        candidates.extend(
            (
                "|".join([*selected_parts[:-1], original_parts[-1]]),
                "|".join([selected_parts[0], *original_parts[1:]]),
                "|".join([original_parts[0], *selected_parts[1:]]),
            )
        )
    candidates.append(f"{selected['program_identity']}|{task['program_identity']}")
    replacement = next(
        (
            candidate
            for candidate in candidates
            if candidate not in existing_identities
            and candidate != task["program_identity"]
        ),
        None,
    )
    if replacement is None:
        raise FrontierContractError("identity rebind could not form a unique hybrid")
    mutated = copy.deepcopy(task)
    mutated["program_identity"] = replacement
    return mutated


def _changed_top_level_fields(
    canonical: Mapping[str, Any], mutated: Mapping[str, Any]
) -> list[str]:
    return sorted(
        field_name
        for field_name in canonical
        if canonical[field_name] != mutated[field_name]
    )


def _delta_certificate(
    canonical: Mapping[str, Any],
    mutated: Mapping[str, Any],
    *,
    probe_kind: str,
) -> dict[str, Any]:
    canonical_nodes = {
        node["evidence_id"]: node for node in canonical["evidence_nodes"]
    }
    mutated_nodes = {node["evidence_id"]: node for node in mutated["evidence_nodes"]}
    added = set(mutated_nodes) - set(canonical_nodes)
    removed = set(canonical_nodes) - set(mutated_nodes)
    modified = {
        evidence_id
        for evidence_id in set(canonical_nodes) & set(mutated_nodes)
        if canonical_nodes[evidence_id] != mutated_nodes[evidence_id]
    }
    changed_stage_access_count = 0
    non_access_stage_field_change_count = 0
    for canonical_stage, mutated_stage in zip(
        canonical["stages"], mutated["stages"], strict=True
    ):
        if (
            canonical_stage["accessible_evidence_ids"]
            != mutated_stage["accessible_evidence_ids"]
        ):
            changed_stage_access_count += 1
        for field_name in set(canonical_stage) - {"accessible_evidence_ids"}:
            if canonical_stage[field_name] != mutated_stage[field_name]:
                non_access_stage_field_change_count += 1
    changed_fields = _changed_top_level_fields(canonical, mutated)
    lineage_edge_change_count = int(
        canonical["lineage_edges"] != mutated["lineage_edges"]
    )
    if probe_kind == "bounded_evidence_reveal":
        exact = (
            changed_fields == ["evidence_nodes", "stages"]
            and len(added) == 1
            and not removed
            and not modified
            and changed_stage_access_count == 3
            and non_access_stage_field_change_count == 0
            and lineage_edge_change_count == 0
        )
    else:
        exact = (
            changed_fields == ["program_identity"]
            and not added
            and not removed
            and not modified
            and changed_stage_access_count == 0
            and non_access_stage_field_change_count == 0
            and lineage_edge_change_count == 0
        )
    return {
        "probe_kind": probe_kind,
        "changed_top_level_fields": changed_fields,
        "added_evidence_node_count": len(added),
        "removed_evidence_node_count": len(removed),
        "modified_existing_evidence_node_count": len(modified),
        "changed_stage_access_count": changed_stage_access_count,
        "non_access_stage_field_change_count": non_access_stage_field_change_count,
        "lineage_edge_change_count": lineage_edge_change_count,
        "exact_delta_passed": exact,
    }


def _validate_materialized_task(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    task_index: int,
    mutated_task: Mapping[str, Any],
    validation_kwargs: Mapping[str, Any],
) -> None:
    mutated_tasks = copy.deepcopy(task_set)
    mutated_oracles = copy.deepcopy(oracle_set)
    mutated_tasks["tasks"][task_index] = copy.deepcopy(mutated_task)
    mutated_tasks["integrity_sha256"] = frontier_calibration_task_set_integrity_sha256(
        mutated_tasks
    )
    mutated_oracles["task_set_integrity_sha256"] = mutated_tasks["integrity_sha256"]
    mutated_oracles["oracles"][task_index]["task_sha256"] = (
        frontier_calibration_task_sha256(mutated_task)
    )
    mutated_oracles["integrity_sha256"] = (
        frontier_calibration_oracle_set_integrity_sha256(mutated_oracles)
    )
    tasks_data = validate_frontier_calibration_task_set(
        mutated_tasks, **validation_kwargs
    )
    validate_frontier_calibration_oracle_set(
        mutated_oracles,
        task_set=tasks_data,
        **validation_kwargs,
    )


def compile_frontier_semantic_review_artifacts(
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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compile deterministic blinded pairs without creating semantic labels."""

    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    tasks_data = validate_frontier_calibration_task_set(task_set, **validation_kwargs)
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set,
        task_set=tasks_data,
        **validation_kwargs,
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
        public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    if (
        public_preflight_data["private_preflight_report_commitment"]
        != private_preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("semantic review inputs do not share a preflight")
    _date(compiled_on, "semantic review compiled_on")

    packets = []
    keys = []
    probe_counts: Counter[str] = Counter()
    for task_index, (task, oracle) in enumerate(
        zip(tasks_data["tasks"], oracles_data["oracles"], strict=True)
    ):
        for mutation in oracle["mutation_expectations"]:
            probe_kind = mutation["probe_kind"]
            if probe_kind not in _SEMANTIC_PROBE_KINDS:
                continue
            if probe_kind == "bounded_evidence_reveal":
                mutated_task = _materialize_evidence_reveal(task)
            else:
                mutated_task = _materialize_identity_rebind(
                    task,
                    candidate_tasks=tasks_data["tasks"],
                )
            _validate_materialized_task(
                task_set=tasks_data,
                oracle_set=oracles_data,
                task_index=task_index,
                mutated_task=mutated_task,
                validation_kwargs=validation_kwargs,
            )
            certificate = _delta_certificate(
                task,
                mutated_task,
                probe_kind=probe_kind,
            )
            if not certificate["exact_delta_passed"]:
                raise FrontierContractError("semantic probe exceeded its minimal delta")

            blind_digest = hashlib.sha256(
                (
                    f"{oracle['oracle_commitment_nonce']}|"
                    f"{mutation['mutation_id']}|semantic-review"
                ).encode("utf-8")
            ).hexdigest()
            packet_id = f"semantic-{blind_digest[:20]}"
            canonical_view = frontier_semantic_review_view(task)
            mutated_view = frontier_semantic_review_view(mutated_task)
            canonical_arm = "arm_a" if int(blind_digest[-1], 16) % 2 == 0 else "arm_b"
            mutated_arm = "arm_b" if canonical_arm == "arm_a" else "arm_a"
            arm_payloads = {
                canonical_arm: canonical_view,
                mutated_arm: mutated_view,
            }
            packet = {
                "packet_id": packet_id,
                "probe_kind": probe_kind,
                "review_dimensions": list(_REVIEW_DIMENSIONS),
                "arm_a": arm_payloads["arm_a"],
                "arm_b": arm_payloads["arm_b"],
                "arm_a_commitment": _canonical_sha256(arm_payloads["arm_a"]),
                "arm_b_commitment": _canonical_sha256(arm_payloads["arm_b"]),
                "delta_certificate_commitment": _canonical_sha256(certificate),
            }
            packets.append(packet)
            keys.append(
                {
                    "packet_id": packet_id,
                    "slot_id": task["slot_id"],
                    "mutation_id": mutation["mutation_id"],
                    "canonical_arm": canonical_arm,
                    "mutated_arm": mutated_arm,
                    "canonical_task_commitment": frontier_calibration_task_sha256(task),
                    "mutated_task_commitment": frontier_calibration_task_sha256(
                        mutated_task
                    ),
                    "expected_changed_components": list(
                        mutation["expected_changed_components"]
                    ),
                    "structural_delta_certificate": certificate,
                }
            )
            probe_counts[probe_kind] += 1

    packets.sort(key=lambda item: item["packet_id"])
    keys.sort(key=lambda item: item["packet_id"])
    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_PACKET_SCHEMA_VERSION,
        "set_id": FRONTIER_SEMANTIC_REVIEW_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "canonical_arm_mapping_included": False,
        "oracle_labels_included": False,
        "minimum_independent_curators_per_packet": 3,
        "review_instructions": [
            "Solve both arms independently before comparing them.",
            "Return all six stage actions, witnesses, and blockers for each arm.",
            "Treat synthetic counterfactual evidence as hypothetical task evidence, not a factual source.",
            "Do not infer canonical status from arm order or packet identifier.",
        ],
        "packets": packets,
        "nonclaims": sorted(_PACKET_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = frontier_semantic_packet_set_integrity_sha256(
        packet_set
    )
    key_set: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_KEY_SCHEMA_VERSION,
        "set_id": FRONTIER_SEMANTIC_REVIEW_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "keys": keys,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_label_count": 0,
        "adjudication_count": 0,
        "independent_review_complete": False,
        "integrity_sha256": "0" * 64,
    }
    key_set["integrity_sha256"] = frontier_semantic_key_set_integrity_sha256(key_set)
    gate_results = progress_data["records"][0]["admission_gate_results"]
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_SUMMARY_SCHEMA_VERSION,
        "set_id": FRONTIER_SEMANTIC_REVIEW_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "semantic_review_packets_compiled_review_not_started",
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data["integrity_sha256"],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "private_key_set_commitment": key_set["integrity_sha256"],
        "semantic_probe_count": len(packets),
        "machine_compiled_packet_count": len(packets),
        "exact_structural_delta_count": sum(
            key["structural_delta_certificate"]["exact_delta_passed"] for key in keys
        ),
        "probe_kind_counts": {
            probe_kind: probe_counts[probe_kind] for probe_kind in _SEMANTIC_PROBE_KINDS
        },
        "minimum_independent_curators_per_packet": 3,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_label_count": 0,
        "adjudication_count": 0,
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
    summary["integrity_sha256"] = frontier_semantic_summary_integrity_sha256(summary)
    return packet_set, key_set, summary


def validate_frontier_semantic_review_summary(
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
        public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    required = {
        "schema_version",
        "set_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "semantic_probe_count",
        "machine_compiled_packet_count",
        "exact_structural_delta_count",
        "probe_kind_counts",
        "minimum_independent_curators_per_packet",
        "reviewer_assignment_count",
        "reviewer_response_count",
        "consensus_label_count",
        "adjudication_count",
        "admission_gate_results",
        "independent_review_complete",
        "human_review_required",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "semantic_review_summary", required)
    if data["schema_version"] != FRONTIER_SEMANTIC_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported semantic review summary schema")
    if data["set_id"] != FRONTIER_SEMANTIC_REVIEW_SET_ID:
        raise FrontierContractError("unexpected semantic review set_id")
    if (
        data["protocol_id"] != progress_data["protocol_id"]
        or data["board_id"] != progress_data["board_id"]
    ):
        raise FrontierContractError("semantic review rebound its protocol or board")
    if data["status"] != "semantic_review_packets_compiled_review_not_started":
        raise FrontierContractError("semantic review summary overstates maturity")
    _date(data["compiled_on"], "semantic_review_summary.compiled_on")
    if (
        _sha256(
            data["public_preflight_integrity_sha256"],
            "semantic_review_summary.public_preflight_integrity_sha256",
        )
        != preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("semantic review does not bind public preflight")
    for field_name in (
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "integrity_sha256",
    ):
        _sha256(data[field_name], f"semantic_review_summary.{field_name}")
    exact_counts = {
        "semantic_probe_count": 20,
        "machine_compiled_packet_count": 20,
        "exact_structural_delta_count": 20,
        "minimum_independent_curators_per_packet": 3,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_label_count": 0,
        "adjudication_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if (
            _integer(data[field_name], f"semantic_review_summary.{field_name}")
            != expected
        ):
            raise FrontierContractError(
                f"semantic review {field_name} must remain {expected}"
            )
    probe_counts = _record(
        data["probe_kind_counts"],
        "semantic_review_summary.probe_kind_counts",
        set(_SEMANTIC_PROBE_KINDS),
    )
    if any(
        _integer(probe_counts[kind], f"semantic_review_summary.{kind}") != 10
        for kind in _SEMANTIC_PROBE_KINDS
    ):
        raise FrontierContractError("semantic review must cover ten probes per kind")
    gate_results = _record(
        data["admission_gate_results"],
        "semantic_review_summary.admission_gate_results",
        set(FRONTIER_ADMISSION_GATES),
    )
    if any(
        record["admission_gate_results"] != gate_results
        for record in progress_data["records"]
    ):
        raise FrontierContractError("semantic review changed admission gates")
    for field_name in (
        "independent_review_complete",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"semantic_review_summary.{field_name}"):
            raise FrontierContractError(
                f"semantic_review_summary.{field_name} must remain false"
            )
    if not _boolean(
        data["human_review_required"],
        "semantic_review_summary.human_review_required",
    ):
        raise FrontierContractError("semantic review must retain human review")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "semantic_review_summary.nonclaims"))
    ):
        raise FrontierContractError("semantic review removed a public nonclaim")
    if data["integrity_sha256"] != frontier_semantic_summary_integrity_sha256(data):
        raise FrontierContractError("semantic review summary integrity mismatch")
    return data


def validate_frontier_semantic_review_private_opening(
    *,
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
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
    summary_data = validate_frontier_semantic_review_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if packet_set.get("integrity_sha256") != (
        frontier_semantic_packet_set_integrity_sha256(packet_set)
    ):
        raise FrontierContractError("semantic packet-set integrity mismatch")
    if key_set.get("integrity_sha256") != frontier_semantic_key_set_integrity_sha256(
        key_set
    ):
        raise FrontierContractError("semantic key-set integrity mismatch")
    expected_packets, expected_keys, expected_summary = (
        compile_frontier_semantic_review_artifacts(
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            progress=progress,
            root=root,
            frontier_protocol=frontier_protocol,
            board_protocol=board_protocol,
            board_slots=board_slots,
            compiled_on=summary_data["compiled_on"],
        )
    )
    if packet_set != expected_packets or key_set != expected_keys:
        raise FrontierContractError(
            "semantic review private artifacts do not replay from committed inputs"
        )
    if public_summary != expected_summary:
        raise FrontierContractError(
            "semantic review private artifacts do not open public summary"
        )
    return semantic_review_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_semantic_review_commitments_opened": True}


def load_frontier_semantic_review_summary(path: Path, **kwargs: Any) -> dict[str, Any]:
    return validate_frontier_semantic_review_summary(
        _load_json(path.read_text(encoding="utf-8"), "semantic review summary"),
        **kwargs,
    )


def load_frontier_semantic_review_packet_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "semantic review packet set")


def load_frontier_semantic_review_key_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "semantic review key set")


def semantic_review_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_semantic_review_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "semantic_probe_count": data["semantic_probe_count"],
        "machine_compiled_packet_count": data["machine_compiled_packet_count"],
        "exact_structural_delta_count": data["exact_structural_delta_count"],
        "reviewer_assignment_count": data["reviewer_assignment_count"],
        "reviewer_response_count": data["reviewer_response_count"],
        "consensus_label_count": data["consensus_label_count"],
        "human_review_required": data["human_review_required"],
        "board_admitted_count": data["board_admitted_count"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
