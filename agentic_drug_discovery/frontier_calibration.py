"""Private calibration authoring and payload-free public progress contracts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from .frontier import (
    FRONTIER_MANDATORY_GATES,
    FrontierAction,
    FrontierContractError,
    _boolean,
    _date,
    _integer,
    _load_json,
    _record,
    _relative_path,
    _sequence,
    _sha256,
    _text,
    _text_list,
    validate_frontier_protocol,
)
from .frontier_board import (
    FRONTIER_ADMISSION_GATES,
    FRONTIER_BOARD_ID,
    validate_frontier_board_protocol,
    validate_frontier_board_slot_manifest,
)
from .frontier_tasks import (
    FRONTIER_CHANGED_COMPONENTS,
    FRONTIER_EVIDENCE_ROLES,
    FRONTIER_LINEAGE_RELATIONSHIPS,
    FRONTIER_MUTATION_CLASSES,
    FRONTIER_STAGE_KINDS,
)


FRONTIER_CALIBRATION_TASK_SET_SCHEMA_VERSION = (
    "adds.frontier-private-calibration-task-set.v1"
)
FRONTIER_CALIBRATION_ORACLE_SET_SCHEMA_VERSION = (
    "adds.frontier-private-calibration-oracle-set.v1"
)
FRONTIER_CALIBRATION_PROGRESS_SCHEMA_VERSION = "adds.frontier-calibration-progress.v1"
FRONTIER_CALIBRATION_SET_ID = "adds-frontier-private-calibration-v1"
FRONTIER_CALIBRATION_PROBE_KINDS = (
    "source_id_rename",
    "critical_evidence_removal",
    "temporal_access_rebind",
    "bounded_evidence_reveal",
    "identity_rebind",
)

_PRIVATE_TASK_NONCLAIM = "This is an authored calibration draft pending independent review and board admission."
_PRIVATE_ORACLE_NONCLAIM = "This sealed draft oracle has not passed independent review, expert solve, or replay admission."
_PROGRESS_NONCLAIMS = {
    "Authored calibration drafts are not independently curated or board-admitted tasks.",
    "Commitment integrity does not establish source truth, scientific validity, or expert solvability.",
    "No baseline model run or benchmark performance evidence is claimed.",
    "Private task, oracle, disease, program, curator, and canary bytes are not published.",
}
_FAMILY_REQUIRED_GATES = {
    "evidence_lineage_trap": {"lineage_independence", "witness_valid"},
    "temporal_reversal": {"cutoff_compliance", "disposition_correct"},
    "translational_handoff": {"identity_continuity", "uncertainty_handling"},
    "non_exchangeable_replication": {
        "endpoint_population_alignment",
        "blocker_certificate_valid",
    },
    "budgeted_evidence_resolution": {"next_action_correct", "budget_compliance"},
}
_AUTHORED_GATE_RESULTS = {
    gate: "pass"
    if gate in {"task_packet_integrity", "oracle_commitment_sealed"}
    else "pending"
    for gate in FRONTIER_ADMISSION_GATES
}
_PROBE_MUTATION_CLASSES = {
    "source_id_rename": "nuisance_invariance",
    "critical_evidence_removal": "critical_flip",
    "temporal_access_rebind": "critical_flip",
    "bounded_evidence_reveal": "evidence_ladder",
    "identity_rebind": "critical_flip",
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


def frontier_calibration_task_sha256(task: Mapping[str, Any]) -> str:
    return _canonical_sha256(task)


def frontier_calibration_oracle_sha256(oracle: Mapping[str, Any]) -> str:
    return _canonical_sha256(oracle)


def frontier_calibration_task_set_integrity_sha256(
    task_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(task_set, exclude=frozenset({"integrity_sha256"}))


def frontier_calibration_oracle_set_integrity_sha256(
    oracle_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(oracle_set, exclude=frozenset({"integrity_sha256"}))


def frontier_calibration_progress_integrity_sha256(
    progress: Mapping[str, Any],
) -> str:
    return _canonical_sha256(progress, exclude=frozenset({"integrity_sha256"}))


def frontier_private_identity_commitment(
    *, slot_id: str, identity_kind: str, identity: str, nonce: str
) -> str:
    """Commit a low-entropy private identity with a per-slot 256-bit nonce."""

    _text(slot_id, "identity commitment slot_id")
    if identity_kind not in {"disease", "program"}:
        raise FrontierContractError("identity_kind must be disease or program")
    _text(identity, f"private {identity_kind} identity")
    _sha256(nonce, f"private {identity_kind} identity nonce")
    return _canonical_sha256(
        {
            "slot_id": slot_id,
            "identity_kind": identity_kind,
            "identity": identity,
            "nonce": nonce,
        }
    )


def _resolve_source(root: Path, relative: str, *, path: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FrontierContractError(f"{path} escapes the repository") from exc
    if not candidate.is_file():
        raise FrontierContractError(f"{path} is missing: {relative}")
    return candidate


def _calibration_slots(
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> list[dict[str, Any]]:
    slots_data = validate_frontier_board_slot_manifest(
        board_slots,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
    )
    return [slot for slot in slots_data["slots"] if slot["partition"] == "calibration"]


def _validate_lineage_edges(
    value: Any,
    *,
    evidence_ids: set[str],
    lineage_by_id: Mapping[str, str],
    path: str,
) -> None:
    adjacency = {evidence_id: set() for evidence_id in evidence_ids}
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(_sequence(value, path)):
        edge = _record(
            item,
            f"{path}[{index}]",
            {"parent_evidence_id", "child_evidence_id", "relationship"},
        )
        parent = _text(edge["parent_evidence_id"], f"{path}[{index}].parent")
        child = _text(edge["child_evidence_id"], f"{path}[{index}].child")
        relationship = _text(edge["relationship"], f"{path}[{index}].relationship")
        if parent not in evidence_ids or child not in evidence_ids:
            raise FrontierContractError(f"{path}[{index}] references unknown evidence")
        if parent == child:
            raise FrontierContractError(f"{path}[{index}] cannot be a self-edge")
        if relationship not in FRONTIER_LINEAGE_RELATIONSHIPS:
            raise FrontierContractError(f"{path}[{index}] has unknown relationship")
        key = (parent, child, relationship)
        if key in seen:
            raise FrontierContractError(f"{path} contains a duplicate edge")
        seen.add(key)
        adjacency[parent].add(child)
        if (
            relationship == "derives_from"
            and lineage_by_id[parent] != lineage_by_id[child]
        ):
            raise FrontierContractError(
                f"{path}[{index}] derivative edge crosses lineage roots"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise FrontierContractError(f"{path} must be acyclic")
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency[node]:
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for evidence_id in evidence_ids:
        visit(evidence_id)


def _validate_temporal_anchor(
    *, temporal_regime: str, anchor_cutoff: date, path: str
) -> None:
    if temporal_regime == "historical_pre_2024" and anchor_cutoff >= date(2024, 1, 1):
        raise FrontierContractError(f"{path} must precede 2024")
    if temporal_regime == "historical_2024_2025" and not (
        date(2024, 1, 1) <= anchor_cutoff <= date(2025, 12, 31)
    ):
        raise FrontierContractError(f"{path} must fall in 2024-2025")


def validate_frontier_calibration_task_set(
    task_set: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate ten private calibration drafts without treating them as admitted."""

    root = root.resolve()
    protocol_data = validate_frontier_protocol(frontier_protocol, root=root)
    board_data = validate_frontier_board_protocol(
        board_protocol,
        root=root,
        frontier_protocol=protocol_data,
    )
    expected_slots = _calibration_slots(
        root=root,
        frontier_protocol=protocol_data,
        board_protocol=board_data,
        board_slots=board_slots,
    )
    data = _record(
        task_set,
        "calibration_tasks",
        {
            "schema_version",
            "protocol_id",
            "board_id",
            "set_id",
            "set_role",
            "authoring_status",
            "task_selection_blinded_to_models",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "tasks",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_CALIBRATION_TASK_SET_SCHEMA_VERSION:
        raise FrontierContractError("unsupported calibration task-set schema_version")
    if data["protocol_id"] != protocol_data["protocol_id"]:
        raise FrontierContractError("calibration tasks do not bind ADDS-Frontier")
    if data["board_id"] != board_data["board_id"]:
        raise FrontierContractError("calibration tasks do not bind the board")
    if data["set_id"] != FRONTIER_CALIBRATION_SET_ID:
        raise FrontierContractError("unexpected calibration set_id")
    if data["set_role"] != "private_calibration_authoring":
        raise FrontierContractError("calibration task set overstates its board role")
    if data["authoring_status"] != "authored_pending_review":
        raise FrontierContractError(
            "calibration authoring status must remain pending review"
        )
    if not _boolean(
        data["task_selection_blinded_to_models"],
        "calibration_tasks.task_selection_blinded_to_models",
    ):
        raise FrontierContractError(
            "calibration task selection must remain model-blind"
        )
    for field_name in ("baseline_model_runs_started", "benchmark_evidence_claimed"):
        if _boolean(data[field_name], f"calibration_tasks.{field_name}"):
            raise FrontierContractError(
                f"calibration_tasks.{field_name} must remain false"
            )

    tasks = _sequence(data["tasks"], "calibration_tasks.tasks")
    if len(tasks) != 10:
        raise FrontierContractError(
            "calibration task set must contain exactly 10 tasks"
        )
    task_ids: set[str] = set()
    program_identities: set[str] = set()
    for index, (item, expected_slot) in enumerate(
        zip(tasks, expected_slots, strict=True)
    ):
        path = f"calibration_tasks.tasks[{index}]"
        task = _record(
            item,
            path,
            {
                "slot_id",
                "task_id",
                "family_id",
                "disease_domain",
                "temporal_regime",
                "task_commitment_nonce",
                "disease_identity",
                "disease_identity_nonce",
                "program_identity",
                "program_identity_nonce",
                "prompt",
                "anchor_cutoff_date",
                "stage_budget",
                "tool_call_budget",
                "authoring_source_artifacts",
                "evidence_nodes",
                "lineage_edges",
                "stages",
                "nonclaim",
            },
        )
        for field_name in ("slot_id", "family_id", "disease_domain", "temporal_regime"):
            if task[field_name] != expected_slot[field_name]:
                raise FrontierContractError(
                    f"{path}.{field_name} rebound the preregistered slot"
                )
        task_id = _text(task["task_id"], f"{path}.task_id")
        if task_id in task_ids:
            raise FrontierContractError(f"duplicate calibration task_id: {task_id}")
        task_ids.add(task_id)
        for nonce_name in (
            "task_commitment_nonce",
            "disease_identity_nonce",
            "program_identity_nonce",
        ):
            _sha256(task[nonce_name], f"{path}.{nonce_name}")
        _text(task["disease_identity"], f"{path}.disease_identity")
        program_identity = _text(task["program_identity"], f"{path}.program_identity")
        if program_identity in program_identities:
            raise FrontierContractError("calibration programs must be unique per task")
        program_identities.add(program_identity)
        _text(task["prompt"], f"{path}.prompt")
        anchor_cutoff = _date(task["anchor_cutoff_date"], f"{path}.anchor_cutoff_date")
        _validate_temporal_anchor(
            temporal_regime=task["temporal_regime"],
            anchor_cutoff=anchor_cutoff,
            path=f"{path}.anchor_cutoff_date",
        )
        stage_budget = _integer(task["stage_budget"], f"{path}.stage_budget", minimum=6)
        if stage_budget > 12:
            raise FrontierContractError(f"{path}.stage_budget exceeds 12")
        tool_call_budget = _integer(
            task["tool_call_budget"], f"{path}.tool_call_budget", minimum=1
        )

        source_paths: set[str] = set()
        sources = _sequence(
            task["authoring_source_artifacts"], f"{path}.authoring_source_artifacts"
        )
        if len(sources) < 2:
            raise FrontierContractError(
                f"{path} requires at least two authoring sources"
            )
        for source_index, source_item in enumerate(sources):
            source_path = f"{path}.authoring_source_artifacts[{source_index}]"
            source = _record(
                source_item,
                source_path,
                {"artifact_path", "artifact_sha256", "source_role", "model_visible"},
            )
            relative = _relative_path(
                source["artifact_path"], f"{source_path}.artifact_path"
            )
            if relative in source_paths:
                raise FrontierContractError(f"{path} contains duplicate source paths")
            source_paths.add(relative)
            artifact = _resolve_source(
                root, relative, path=f"{source_path}.artifact_path"
            )
            expected_hash = _sha256(
                source["artifact_sha256"], f"{source_path}.artifact_sha256"
            )
            actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if expected_hash != actual_hash:
                raise FrontierContractError(
                    f"{source_path} hash mismatch: expected {expected_hash}, got {actual_hash}"
                )
            if source["source_role"] not in {
                "authoring_context",
                "source_index",
                "verification_record",
            }:
                raise FrontierContractError(f"{source_path}.source_role is unsupported")
            if _boolean(source["model_visible"], f"{source_path}.model_visible"):
                raise FrontierContractError(
                    "authoring source artifacts must remain evaluator-only"
                )

        evidence_ids: set[str] = set()
        availability_by_id: dict[str, date] = {}
        lineage_by_id: dict[str, str] = {}
        for evidence_index, evidence_item in enumerate(
            _sequence(task["evidence_nodes"], f"{path}.evidence_nodes")
        ):
            evidence_path = f"{path}.evidence_nodes[{evidence_index}]"
            evidence = _record(
                evidence_item,
                evidence_path,
                {
                    "evidence_id",
                    "available_on",
                    "lineage_id",
                    "evidence_role",
                    "evidence_summary",
                },
            )
            evidence_id = _text(evidence["evidence_id"], f"{evidence_path}.evidence_id")
            if evidence_id in evidence_ids:
                raise FrontierContractError(f"{path} contains duplicate evidence ids")
            evidence_ids.add(evidence_id)
            availability_by_id[evidence_id] = _date(
                evidence["available_on"], f"{evidence_path}.available_on"
            )
            lineage_by_id[evidence_id] = _text(
                evidence["lineage_id"], f"{evidence_path}.lineage_id"
            )
            if evidence["evidence_role"] not in FRONTIER_EVIDENCE_ROLES:
                raise FrontierContractError(
                    f"{evidence_path}.evidence_role is unsupported"
                )
            _text(evidence["evidence_summary"], f"{evidence_path}.evidence_summary")
        if len(evidence_ids) < 2:
            raise FrontierContractError(f"{path} requires at least two evidence nodes")
        _validate_lineage_edges(
            task["lineage_edges"],
            evidence_ids=evidence_ids,
            lineage_by_id=lineage_by_id,
            path=f"{path}.lineage_edges",
        )

        stages = _sequence(task["stages"], f"{path}.stages")
        if len(stages) != stage_budget:
            raise FrontierContractError(f"{path}.stages must match stage_budget")
        prior_access: set[str] = set()
        prior_date: date | None = None
        gate_union: set[str] = set()
        total_stage_calls = 0
        post_anchor_stage_seen = False
        for stage_index, stage_item in enumerate(stages):
            stage_path = f"{path}.stages[{stage_index}]"
            stage = _record(
                stage_item,
                stage_path,
                {
                    "stage_id",
                    "stage_kind",
                    "as_of_date",
                    "accessible_evidence_ids",
                    "required_gates",
                    "max_tool_calls",
                },
            )
            if stage["stage_id"] != f"s{stage_index + 1:02d}":
                raise FrontierContractError(
                    f"{path}.stages must use ordered s01... ids"
                )
            if stage["stage_kind"] not in FRONTIER_STAGE_KINDS:
                raise FrontierContractError(f"{stage_path}.stage_kind is unsupported")
            as_of = _date(stage["as_of_date"], f"{stage_path}.as_of_date")
            if prior_date is not None and as_of < prior_date:
                raise FrontierContractError(f"{path}.stage chronology must be monotone")
            prior_date = as_of
            post_anchor_stage_seen = post_anchor_stage_seen or as_of > anchor_cutoff
            accessible = _text_list(
                stage["accessible_evidence_ids"],
                f"{stage_path}.accessible_evidence_ids",
            )
            if len(accessible) != len(set(accessible)) or not set(accessible).issubset(
                evidence_ids
            ):
                raise FrontierContractError(f"{stage_path} has invalid evidence access")
            if not prior_access.issubset(set(accessible)):
                raise FrontierContractError(
                    f"{path}.evidence access must be cumulative"
                )
            for evidence_id in accessible:
                if availability_by_id[evidence_id] > as_of:
                    raise FrontierContractError(
                        f"{stage_path} exposes post-cutoff evidence: {evidence_id}"
                    )
            prior_access = set(accessible)
            gates = set(
                _text_list(stage["required_gates"], f"{stage_path}.required_gates")
            )
            if not gates.issubset(FRONTIER_MANDATORY_GATES):
                raise FrontierContractError(f"{stage_path} contains unknown gates")
            gate_union.update(gates)
            total_stage_calls += _integer(
                stage["max_tool_calls"], f"{stage_path}.max_tool_calls", minimum=1
            )
        if not _FAMILY_REQUIRED_GATES[task["family_id"]].issubset(gate_union):
            raise FrontierContractError(f"{path} omits family-critical gates")
        if total_stage_calls != tool_call_budget:
            raise FrontierContractError(
                f"{path}.tool_call_budget does not match stages"
            )
        if task["family_id"] == "temporal_reversal" and not post_anchor_stage_seen:
            raise FrontierContractError(
                "temporal-reversal task needs a post-anchor stage"
            )
        if task["nonclaim"] != _PRIVATE_TASK_NONCLAIM:
            raise FrontierContractError(f"{path} removed its authoring nonclaim")

    expected_integrity = _sha256(
        data["integrity_sha256"], "calibration_tasks.integrity_sha256"
    )
    actual_integrity = frontier_calibration_task_set_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"calibration task-set integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def validate_frontier_calibration_oracle_set(
    oracle_set: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    task_set: Mapping[str, Any],
) -> dict[str, Any]:
    tasks_data = validate_frontier_calibration_task_set(
        task_set,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    data = _record(
        oracle_set,
        "calibration_oracles",
        {
            "schema_version",
            "protocol_id",
            "board_id",
            "set_id",
            "set_role",
            "authoring_status",
            "benchmark_evidence_claimed",
            "task_set_integrity_sha256",
            "oracles",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_CALIBRATION_ORACLE_SET_SCHEMA_VERSION:
        raise FrontierContractError("unsupported calibration oracle-set schema_version")
    for field_name in ("protocol_id", "board_id", "set_id"):
        if data[field_name] != tasks_data[field_name]:
            raise FrontierContractError(f"calibration oracles rebound {field_name}")
    if data["set_role"] != "private_sealed_calibration_oracle":
        raise FrontierContractError("calibration oracle set overstates its board role")
    if data["authoring_status"] != "authored_pending_review":
        raise FrontierContractError(
            "calibration oracle status must remain pending review"
        )
    if _boolean(
        data["benchmark_evidence_claimed"],
        "calibration_oracles.benchmark_evidence_claimed",
    ):
        raise FrontierContractError(
            "calibration oracle cannot claim benchmark evidence"
        )
    if (
        _sha256(
            data["task_set_integrity_sha256"],
            "calibration_oracles.task_set_integrity_sha256",
        )
        != tasks_data["integrity_sha256"]
    ):
        raise FrontierContractError("calibration oracle set does not bind the task set")

    tasks_by_slot = {task["slot_id"]: task for task in tasks_data["tasks"]}
    oracles = _sequence(data["oracles"], "calibration_oracles.oracles")
    if len(oracles) != 10:
        raise FrontierContractError(
            "calibration oracle set must contain exactly 10 oracles"
        )
    mutation_count = 0
    for index, (item, task) in enumerate(
        zip(oracles, tasks_data["tasks"], strict=True)
    ):
        path = f"calibration_oracles.oracles[{index}]"
        oracle = _record(
            item,
            path,
            {
                "slot_id",
                "task_id",
                "task_sha256",
                "oracle_commitment_nonce",
                "stage_expectations",
                "mutation_expectations",
                "nonclaim",
            },
        )
        if (
            oracle["slot_id"] != task["slot_id"]
            or tasks_by_slot.get(oracle["slot_id"]) is not task
        ):
            raise FrontierContractError(f"{path} rebound its slot")
        if oracle["task_id"] != task["task_id"]:
            raise FrontierContractError(f"{path} rebound its task_id")
        if _sha256(
            oracle["task_sha256"], f"{path}.task_sha256"
        ) != frontier_calibration_task_sha256(task):
            raise FrontierContractError(f"{path} does not open the task commitment")
        _sha256(oracle["oracle_commitment_nonce"], f"{path}.oracle_commitment_nonce")

        stages = task["stages"]
        expectations = _sequence(
            oracle["stage_expectations"], f"{path}.stage_expectations"
        )
        if len(expectations) != len(stages):
            raise FrontierContractError(f"{path} must cover every stage")
        for stage_index, (expectation_item, stage) in enumerate(
            zip(expectations, stages, strict=True)
        ):
            expectation_path = f"{path}.stage_expectations[{stage_index}]"
            expectation = _record(
                expectation_item,
                expectation_path,
                {"stage_id", "action", "witness_evidence_ids", "blocker_codes"},
            )
            if expectation["stage_id"] != stage["stage_id"]:
                raise FrontierContractError(f"{expectation_path} rebound its stage")
            action = _record(
                expectation["action"],
                f"{expectation_path}.action",
                {"disposition", "next_action", "risk_flags"},
            )
            FrontierAction(
                disposition=action["disposition"],
                next_action=action["next_action"],
                risk_flags=tuple(
                    _text_list(
                        action["risk_flags"],
                        f"{expectation_path}.action.risk_flags",
                        nonempty=False,
                    )
                ),
            )
            witnesses = _text_list(
                expectation["witness_evidence_ids"],
                f"{expectation_path}.witness_evidence_ids",
            )
            if not set(witnesses).issubset(stage["accessible_evidence_ids"]):
                raise FrontierContractError(
                    f"{expectation_path} cites inaccessible evidence"
                )
            _text_list(
                expectation["blocker_codes"], f"{expectation_path}.blocker_codes"
            )

        mutations = _sequence(
            oracle["mutation_expectations"], f"{path}.mutation_expectations"
        )
        if len(mutations) < 5:
            raise FrontierContractError(f"{path} requires at least five mutations")
        mutation_ids: set[str] = set()
        probe_kinds: list[str] = []
        mutation_classes: Counter[str] = Counter()
        for mutation_index, mutation_item in enumerate(mutations):
            mutation_path = f"{path}.mutation_expectations[{mutation_index}]"
            mutation = _record(
                mutation_item,
                mutation_path,
                {
                    "mutation_id",
                    "probe_kind",
                    "mutation_class",
                    "operation",
                    "expected_changed_components",
                },
            )
            mutation_id = _text(mutation["mutation_id"], f"{mutation_path}.mutation_id")
            if mutation_id in mutation_ids:
                raise FrontierContractError(f"{path} has duplicate mutation ids")
            mutation_ids.add(mutation_id)
            probe_kind = _text(mutation["probe_kind"], f"{mutation_path}.probe_kind")
            if probe_kind not in FRONTIER_CALIBRATION_PROBE_KINDS:
                raise FrontierContractError(f"{mutation_path} has unknown probe_kind")
            probe_kinds.append(probe_kind)
            mutation_class = _text(
                mutation["mutation_class"], f"{mutation_path}.mutation_class"
            )
            if mutation_class not in FRONTIER_MUTATION_CLASSES:
                raise FrontierContractError(
                    f"{mutation_path} has unknown mutation class"
                )
            if mutation_class != _PROBE_MUTATION_CLASSES[probe_kind]:
                raise FrontierContractError(
                    f"{mutation_path} probe_kind and mutation_class disagree"
                )
            mutation_classes[mutation_class] += 1
            _text(mutation["operation"], f"{mutation_path}.operation")
            changed = _text_list(
                mutation["expected_changed_components"],
                f"{mutation_path}.expected_changed_components",
                nonempty=False,
            )
            if len(changed) != len(set(changed)) or not set(changed).issubset(
                FRONTIER_CHANGED_COMPONENTS
            ):
                raise FrontierContractError(
                    f"{mutation_path} has invalid changed components"
                )
            if mutation_class == "nuisance_invariance" and changed:
                raise FrontierContractError(
                    f"{mutation_path} nuisance mutation must preserve scored components"
                )
            if mutation_class != "nuisance_invariance" and not changed:
                raise FrontierContractError(
                    f"{mutation_path} diagnostic mutation must change a scored component"
                )
        if set(mutation_classes) != set(FRONTIER_MUTATION_CLASSES):
            raise FrontierContractError(f"{path} must cover all mutation classes")
        if tuple(probe_kinds) != FRONTIER_CALIBRATION_PROBE_KINDS:
            raise FrontierContractError(
                f"{path} must preserve the executable probe order"
            )
        mutation_count += len(mutations)
        if oracle["nonclaim"] != _PRIVATE_ORACLE_NONCLAIM:
            raise FrontierContractError(f"{path} removed its authoring nonclaim")

    expected_integrity = _sha256(
        data["integrity_sha256"], "calibration_oracles.integrity_sha256"
    )
    actual_integrity = frontier_calibration_oracle_set_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"calibration oracle-set integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    if mutation_count < 50:
        raise FrontierContractError(
            "calibration oracle set requires at least 50 mutations"
        )
    return data


def build_frontier_calibration_progress(
    *,
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    updated_on: str,
) -> dict[str, Any]:
    """Build the public payload-free progress manifest from validated private bytes."""

    tasks_data = validate_frontier_calibration_task_set(
        task_set,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        task_set=tasks_data,
    )
    board_data = validate_frontier_board_protocol(
        board_protocol,
        root=root,
        frontier_protocol=frontier_protocol,
    )
    slots_data = validate_frontier_board_slot_manifest(
        board_slots,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_data,
    )
    _date(updated_on, "calibration progress updated_on")
    records = []
    for task, oracle in zip(tasks_data["tasks"], oracles_data["oracles"], strict=True):
        records.append(
            {
                "slot_id": task["slot_id"],
                "family_id": task["family_id"],
                "disease_domain": task["disease_domain"],
                "temporal_regime": task["temporal_regime"],
                "status": "authored_pending_review",
                "task_commitment": frontier_calibration_task_sha256(task),
                "oracle_commitment": frontier_calibration_oracle_sha256(oracle),
                "program_commitment": frontier_private_identity_commitment(
                    slot_id=task["slot_id"],
                    identity_kind="program",
                    identity=task["program_identity"],
                    nonce=task["program_identity_nonce"],
                ),
                "disease_identity_commitment": frontier_private_identity_commitment(
                    slot_id=task["slot_id"],
                    identity_kind="disease",
                    identity=task["disease_identity"],
                    nonce=task["disease_identity_nonce"],
                ),
                "stage_count": len(task["stages"]),
                "mutation_count": len(oracle["mutation_expectations"]),
                "authoring_source_count": len(task["authoring_source_artifacts"]),
                "curator_roster_commitment": None,
                "independent_curator_count": 0,
                "admission_gate_results": dict(_AUTHORED_GATE_RESULTS),
                "board_admitted": False,
            }
        )
    progress: dict[str, Any] = {
        "schema_version": FRONTIER_CALIBRATION_PROGRESS_SCHEMA_VERSION,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": FRONTIER_BOARD_ID,
        "status": "calibration_authored_pending_independent_review",
        "updated_on": updated_on,
        "board_protocol_integrity_sha256": board_data["integrity_sha256"],
        "slot_manifest_integrity_sha256": slots_data["integrity_sha256"],
        "task_set_commitment": tasks_data["integrity_sha256"],
        "oracle_set_commitment": oracles_data["integrity_sha256"],
        "private_payload_published": False,
        "task_selection_blinded_to_models": True,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "authored_task_count": 10,
        "board_admitted_count": 0,
        "records": records,
        "nonclaims": sorted(_PROGRESS_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    progress["integrity_sha256"] = frontier_calibration_progress_integrity_sha256(
        progress
    )
    return progress


def validate_frontier_calibration_progress(
    progress: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate public commitments and nonclaims without requiring private bytes."""

    protocol_data = validate_frontier_protocol(frontier_protocol, root=root)
    board_data = validate_frontier_board_protocol(
        board_protocol,
        root=root,
        frontier_protocol=protocol_data,
    )
    slots_data = validate_frontier_board_slot_manifest(
        board_slots,
        root=root,
        frontier_protocol=protocol_data,
        board_protocol=board_data,
    )
    expected_slots = [
        slot for slot in slots_data["slots"] if slot["partition"] == "calibration"
    ]
    data = _record(
        progress,
        "calibration_progress",
        {
            "schema_version",
            "protocol_id",
            "board_id",
            "status",
            "updated_on",
            "board_protocol_integrity_sha256",
            "slot_manifest_integrity_sha256",
            "task_set_commitment",
            "oracle_set_commitment",
            "private_payload_published",
            "task_selection_blinded_to_models",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "authored_task_count",
            "board_admitted_count",
            "records",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_CALIBRATION_PROGRESS_SCHEMA_VERSION:
        raise FrontierContractError("unsupported calibration progress schema_version")
    if (
        data["protocol_id"] != protocol_data["protocol_id"]
        or data["board_id"] != board_data["board_id"]
    ):
        raise FrontierContractError(
            "calibration progress rebound its protocol or board"
        )
    if data["status"] != "calibration_authored_pending_independent_review":
        raise FrontierContractError("calibration progress overstates current maturity")
    _date(data["updated_on"], "calibration_progress.updated_on")
    if (
        _sha256(
            data["board_protocol_integrity_sha256"],
            "calibration_progress.board_protocol_integrity_sha256",
        )
        != board_data["integrity_sha256"]
    ):
        raise FrontierContractError("calibration progress does not bind board protocol")
    if (
        _sha256(
            data["slot_manifest_integrity_sha256"],
            "calibration_progress.slot_manifest_integrity_sha256",
        )
        != slots_data["integrity_sha256"]
    ):
        raise FrontierContractError("calibration progress does not bind slot registry")
    _sha256(data["task_set_commitment"], "calibration_progress.task_set_commitment")
    _sha256(data["oracle_set_commitment"], "calibration_progress.oracle_set_commitment")
    if _boolean(
        data["private_payload_published"],
        "calibration_progress.private_payload_published",
    ):
        raise FrontierContractError("private calibration payload must not be published")
    if not _boolean(
        data["task_selection_blinded_to_models"],
        "calibration_progress.task_selection_blinded_to_models",
    ):
        raise FrontierContractError("calibration authoring must remain model-blind")
    for field_name in ("baseline_model_runs_started", "benchmark_evidence_claimed"):
        if _boolean(data[field_name], f"calibration_progress.{field_name}"):
            raise FrontierContractError(
                f"calibration_progress.{field_name} must remain false"
            )
    if (
        _integer(
            data["authored_task_count"],
            "calibration_progress.authored_task_count",
            minimum=0,
        )
        != 10
    ):
        raise FrontierContractError(
            "calibration progress must bind ten authored drafts"
        )
    if (
        _integer(
            data["board_admitted_count"],
            "calibration_progress.board_admitted_count",
            minimum=0,
        )
        != 0
    ):
        raise FrontierContractError("calibration drafts cannot claim board admission")

    records = _sequence(data["records"], "calibration_progress.records")
    if len(records) != 10:
        raise FrontierContractError("calibration progress must contain ten records")
    task_commitments: set[str] = set()
    oracle_commitments: set[str] = set()
    program_commitments: set[str] = set()
    for index, (item, expected_slot) in enumerate(
        zip(records, expected_slots, strict=True)
    ):
        path = f"calibration_progress.records[{index}]"
        record = _record(
            item,
            path,
            {
                "slot_id",
                "family_id",
                "disease_domain",
                "temporal_regime",
                "status",
                "task_commitment",
                "oracle_commitment",
                "program_commitment",
                "disease_identity_commitment",
                "stage_count",
                "mutation_count",
                "authoring_source_count",
                "curator_roster_commitment",
                "independent_curator_count",
                "admission_gate_results",
                "board_admitted",
            },
        )
        for field_name in ("slot_id", "family_id", "disease_domain", "temporal_regime"):
            if record[field_name] != expected_slot[field_name]:
                raise FrontierContractError(f"{path}.{field_name} rebound its slot")
        if record["status"] != "authored_pending_review":
            raise FrontierContractError(f"{path} overstates authoring progress")
        for field_name, seen in (
            ("task_commitment", task_commitments),
            ("oracle_commitment", oracle_commitments),
            ("program_commitment", program_commitments),
        ):
            commitment = _sha256(record[field_name], f"{path}.{field_name}")
            if commitment in seen:
                raise FrontierContractError(f"{path}.{field_name} must be unique")
            seen.add(commitment)
        _sha256(
            record["disease_identity_commitment"],
            f"{path}.disease_identity_commitment",
        )
        _integer(record["stage_count"], f"{path}.stage_count", minimum=6)
        _integer(record["mutation_count"], f"{path}.mutation_count", minimum=5)
        _integer(
            record["authoring_source_count"],
            f"{path}.authoring_source_count",
            minimum=2,
        )
        if record["curator_roster_commitment"] is not None:
            raise FrontierContractError(f"{path} cannot claim a curator roster")
        if (
            _integer(
                record["independent_curator_count"],
                f"{path}.independent_curator_count",
                minimum=0,
            )
            != 0
        ):
            raise FrontierContractError(f"{path} cannot claim independent curators")
        gate_results = _record(
            record["admission_gate_results"],
            f"{path}.admission_gate_results",
            set(FRONTIER_ADMISSION_GATES),
        )
        if gate_results != _AUTHORED_GATE_RESULTS:
            raise FrontierContractError(f"{path} has premature admission-gate claims")
        if _boolean(record["board_admitted"], f"{path}.board_admitted"):
            raise FrontierContractError(f"{path} cannot claim board admission")

    if not _PROGRESS_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "calibration_progress.nonclaims"))
    ):
        raise FrontierContractError("calibration progress removed a required nonclaim")
    expected_integrity = _sha256(
        data["integrity_sha256"], "calibration_progress.integrity_sha256"
    )
    actual_integrity = frontier_calibration_progress_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"calibration progress integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def load_frontier_calibration_task_set(
    path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    return validate_frontier_calibration_task_set(
        _load_json(path.read_text(encoding="utf-8"), "private calibration task set"),
        **kwargs,
    )


def load_frontier_calibration_oracle_set(
    path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    return validate_frontier_calibration_oracle_set(
        _load_json(path.read_text(encoding="utf-8"), "private calibration oracle set"),
        **kwargs,
    )


def load_frontier_calibration_progress(
    path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    return validate_frontier_calibration_progress(
        _load_json(path.read_text(encoding="utf-8"), "calibration progress"),
        **kwargs,
    )


def frontier_calibration_progress_summary(
    progress: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    data = validate_frontier_calibration_progress(progress, **kwargs)
    records = data["records"]
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "authored_task_count": data["authored_task_count"],
        "task_family_count": len({record["family_id"] for record in records}),
        "calibration_domain_count": len(
            {record["disease_domain"] for record in records}
        ),
        "total_stage_count": sum(record["stage_count"] for record in records),
        "total_mutation_count": sum(record["mutation_count"] for record in records),
        "independent_review_complete": all(
            record["independent_curator_count"] >= 3 for record in records
        ),
        "board_admitted_count": data["board_admitted_count"],
        "baseline_model_runs_started": data["baseline_model_runs_started"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
        "private_payload_published": data["private_payload_published"],
    }


def validate_frontier_calibration_private_opening(
    *,
    progress: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    """Open every public commitment against local private authoring bytes."""

    progress_data = validate_frontier_calibration_progress(
        progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    expected = build_frontier_calibration_progress(
        task_set=task_set,
        oracle_set=oracle_set,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        updated_on=progress_data["updated_on"],
    )
    if expected != progress_data:
        raise FrontierContractError(
            "private calibration bytes do not open the public progress commitments"
        )
    summary = frontier_calibration_progress_summary(
        progress_data,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    return {**summary, "private_commitments_opened": True}
