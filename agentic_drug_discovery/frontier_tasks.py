"""Curation contracts for executable ADDS-Frontier development tasks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .frontier import (
    FRONTIER_MANDATORY_GATES,
    FRONTIER_PROTOCOL_ID,
    FRONTIER_TASK_FAMILIES,
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
    validate_frontier_seed_manifest,
)


FRONTIER_TASK_SET_SCHEMA_VERSION = "adds.frontier-task-set.v1"
FRONTIER_ORACLE_SET_SCHEMA_VERSION = "adds.frontier-oracle-set.v1"
FRONTIER_CURATION_SCHEMA_VERSION = "adds.frontier-curation-tranche.v1"
FRONTIER_DEVELOPMENT_SET_ID = "adds-frontier-development-tranche-v1"

FRONTIER_EVIDENCE_ROLES = (
    "source",
    "context",
    "contradiction",
    "derivative",
    "decision_record",
)
FRONTIER_LINEAGE_RELATIONSHIPS = (
    "derives_from",
    "corroborates",
    "supersedes",
    "conflicts_with",
)
FRONTIER_STAGE_KINDS = (
    "retrieve",
    "identity",
    "chronology",
    "lineage",
    "alignment",
    "synthesis",
    "action",
    "replay",
)
FRONTIER_MUTATION_CLASSES = (
    "critical_flip",
    "nuisance_invariance",
    "evidence_ladder",
)
FRONTIER_CHANGED_COMPONENTS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)

_TASK_NONCLAIM = "This public development task is not a private pilot-board item or benchmark evidence."
_ORACLE_NONCLAIM = "This public development oracle is a contract fixture, not a hidden benchmark label."
_CURATION_NONCLAIM = "Development fixtures do not count toward the independently curated 40-task pilot board."


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


def frontier_task_sha256(task: Mapping[str, Any]) -> str:
    """Return the canonical commitment for one model-visible task."""

    return _canonical_sha256(task)


def frontier_task_set_integrity_sha256(task_set: Mapping[str, Any]) -> str:
    """Return the canonical task-set hash, excluding its integrity field."""

    return _canonical_sha256(task_set, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_set_integrity_sha256(oracle_set: Mapping[str, Any]) -> str:
    """Return the canonical oracle-set hash, excluding its integrity field."""

    return _canonical_sha256(oracle_set, exclude=frozenset({"integrity_sha256"}))


def frontier_curation_integrity_sha256(curation: Mapping[str, Any]) -> str:
    """Return the canonical curation hash, excluding its integrity field."""

    return _canonical_sha256(curation, exclude=frozenset({"integrity_sha256"}))


def score_frontier_stage_components(
    expectation: Mapping[str, Any],
    *,
    action: FrontierAction,
    witness_evidence_ids: Sequence[str],
    blocker_codes: Sequence[str],
) -> dict[str, bool]:
    """Score only the five oracle-comparable stage components.

    Retrieval, identity, chronology, lineage, alignment, uncertainty, budget, and
    replay gates still require evaluator-generated evidence. This helper cannot
    promote its partial result to full-trajectory success.
    """

    data = _record(
        expectation,
        "stage_expectation",
        {"stage_id", "action", "witness_evidence_ids", "blocker_codes"},
    )
    expected_action = _record(
        data["action"],
        "stage_expectation.action",
        {"disposition", "next_action", "risk_flags"},
    )
    expected_flags = tuple(
        _text_list(
            expected_action["risk_flags"],
            "stage_expectation.action.risk_flags",
            nonempty=False,
        )
    )
    submitted_witnesses = tuple(
        _text_list(
            witness_evidence_ids,
            "submitted witness_evidence_ids",
            nonempty=False,
        )
    )
    submitted_blockers = tuple(
        _text_list(blocker_codes, "submitted blocker_codes", nonempty=False)
    )
    return {
        "disposition_correct": action.disposition == expected_action["disposition"],
        "next_action_correct": action.next_action == expected_action["next_action"],
        "risk_flags_correct": set(action.risk_flags) == set(expected_flags),
        "witness_valid": set(submitted_witnesses) == set(data["witness_evidence_ids"]),
        "blocker_certificate_valid": set(submitted_blockers)
        == set(data["blocker_codes"]),
    }


def _resolve_artifact(root: Path, relative: str, *, path: str) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FrontierContractError(f"{path} escapes the repository") from exc
    if not resolved.is_file():
        raise FrontierContractError(f"{path} is missing: {relative}")
    return resolved


def _validate_lineage_dag(
    evidence_ids: set[str],
    lineage_by_evidence: Mapping[str, str],
    value: Any,
    *,
    path: str,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    adjacency = {evidence_id: set() for evidence_id in evidence_ids}
    for index, item in enumerate(_sequence(value, path)):
        edge = _record(
            item,
            f"{path}[{index}]",
            {"parent_evidence_id", "child_evidence_id", "relationship"},
        )
        parent = _text(
            edge["parent_evidence_id"], f"{path}[{index}].parent_evidence_id"
        )
        child = _text(edge["child_evidence_id"], f"{path}[{index}].child_evidence_id")
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
            and lineage_by_evidence[parent] != lineage_by_evidence[child]
        ):
            raise FrontierContractError(
                f"{path}[{index}] derivative edge crosses lineage roots"
            )
        edges.append(edge)

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

    for evidence_id in sorted(evidence_ids):
        visit(evidence_id)
    return edges


def validate_frontier_task_set(
    task_set: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate five public development tasks without exposing benchmark claims."""

    protocol_data = validate_frontier_protocol(protocol, root=root)
    seeds_data = validate_frontier_seed_manifest(
        seed_manifest,
        root=root,
        protocol=protocol_data,
    )
    data = _record(
        task_set,
        "task_set",
        {
            "schema_version",
            "protocol_id",
            "set_id",
            "set_role",
            "benchmark_evidence_claimed",
            "baseline_model_runs_started",
            "tasks",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_TASK_SET_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier task-set schema_version")
    if data["protocol_id"] != FRONTIER_PROTOCOL_ID:
        raise FrontierContractError("task set does not bind the frontier protocol")
    if data["set_id"] != FRONTIER_DEVELOPMENT_SET_ID:
        raise FrontierContractError("unexpected frontier development set_id")
    if data["set_role"] != "public_development_only":
        raise FrontierContractError("task set overstates its board role")
    for field_name in ("benchmark_evidence_claimed", "baseline_model_runs_started"):
        if _boolean(data[field_name], f"task_set.{field_name}"):
            raise FrontierContractError(f"task_set.{field_name} must remain false")

    root = root.resolve()
    seed_by_family = {seed["family_id"]: seed for seed in seeds_data["seeds"]}
    protocol_family_by_id = {
        family["family_id"]: family for family in protocol_data["task_families"]
    }
    task_ids: set[str] = set()
    family_ids: list[str] = []
    validated_tasks: list[dict[str, Any]] = []
    for task_index, item in enumerate(_sequence(data["tasks"], "task_set.tasks")):
        task = _record(
            item,
            f"task_set.tasks[{task_index}]",
            {
                "task_id",
                "family_id",
                "seed_id",
                "disease_area",
                "prompt",
                "stage_budget",
                "tool_call_budget",
                "evidence_nodes",
                "lineage_edges",
                "stages",
                "nonclaim",
            },
        )
        task_id = _text(task["task_id"], f"task {task_index}.task_id")
        if task_id in task_ids:
            raise FrontierContractError(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)
        family_id = _text(task["family_id"], f"task {task_id}.family_id")
        family_ids.append(family_id)
        seed = seed_by_family.get(family_id)
        family = protocol_family_by_id.get(family_id)
        if seed is None or family is None:
            raise FrontierContractError(f"task {task_id} has unknown family_id")
        if task["seed_id"] != seed["seed_id"]:
            raise FrontierContractError(f"task {task_id} rebound its design seed")
        _text(task["disease_area"], f"task {task_id}.disease_area")
        _text(task["prompt"], f"task {task_id}.prompt")
        stage_budget = _integer(
            task["stage_budget"], f"task {task_id}.stage_budget", minimum=6
        )
        if stage_budget > 12:
            raise FrontierContractError(f"task {task_id} exceeds 12 stages")
        tool_call_budget = _integer(
            task["tool_call_budget"],
            f"task {task_id}.tool_call_budget",
            minimum=1,
        )

        evidence_ids: set[str] = set()
        artifact_paths: list[str] = []
        availability_by_evidence: dict[str, Any] = {}
        lineage_by_evidence: dict[str, str] = {}
        for evidence_index, evidence_item in enumerate(
            _sequence(task["evidence_nodes"], f"task {task_id}.evidence_nodes")
        ):
            evidence = _record(
                evidence_item,
                f"task {task_id}.evidence_nodes[{evidence_index}]",
                {
                    "evidence_id",
                    "artifact_path",
                    "artifact_sha256",
                    "availability_date",
                    "lineage_id",
                    "evidence_role",
                },
            )
            evidence_id = _text(
                evidence["evidence_id"],
                f"task {task_id}.evidence_nodes[{evidence_index}].evidence_id",
            )
            if evidence_id in evidence_ids:
                raise FrontierContractError(
                    f"task {task_id} has duplicate evidence_id: {evidence_id}"
                )
            evidence_ids.add(evidence_id)
            artifact_path = _relative_path(
                evidence["artifact_path"],
                f"task {task_id}.evidence_nodes[{evidence_index}].artifact_path",
            )
            artifact_paths.append(artifact_path)
            artifact = _resolve_artifact(
                root,
                artifact_path,
                path=f"task {task_id} evidence artifact",
            )
            declared_hash = _sha256(
                evidence["artifact_sha256"],
                f"task {task_id}.evidence_nodes[{evidence_index}].artifact_sha256",
            )
            actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if declared_hash != actual_hash:
                raise FrontierContractError(
                    f"task {task_id} evidence hash mismatch: {artifact_path}"
                )
            availability_by_evidence[evidence_id] = _date(
                evidence["availability_date"],
                f"task {task_id}.evidence_nodes[{evidence_index}].availability_date",
            )
            lineage_by_evidence[evidence_id] = _text(
                evidence["lineage_id"],
                f"task {task_id}.evidence_nodes[{evidence_index}].lineage_id",
            )
            if evidence["evidence_role"] not in FRONTIER_EVIDENCE_ROLES:
                raise FrontierContractError(
                    f"task {task_id} evidence node has unknown role"
                )
        if artifact_paths != seed["source_artifacts"]:
            raise FrontierContractError(
                f"task {task_id} evidence artifacts changed the seed binding"
            )
        _validate_lineage_dag(
            evidence_ids,
            lineage_by_evidence,
            task["lineage_edges"],
            path=f"task {task_id}.lineage_edges",
        )

        stages = _sequence(task["stages"], f"task {task_id}.stages")
        if len(stages) != stage_budget:
            raise FrontierContractError(
                f"task {task_id} stage count does not match stage_budget"
            )
        prior_date = None
        prior_access: set[str] = set()
        required_gate_union: set[str] = set()
        total_stage_tool_budget = 0
        for stage_index, stage_item in enumerate(stages):
            stage = _record(
                stage_item,
                f"task {task_id}.stages[{stage_index}]",
                {
                    "stage_id",
                    "stage_kind",
                    "as_of_date",
                    "accessible_evidence_ids",
                    "required_gates",
                    "max_tool_calls",
                },
            )
            expected_stage_id = f"s{stage_index + 1:02d}"
            if stage["stage_id"] != expected_stage_id:
                raise FrontierContractError(
                    f"task {task_id} stage ids must be contiguous from s01"
                )
            if stage["stage_kind"] not in FRONTIER_STAGE_KINDS:
                raise FrontierContractError(f"task {task_id} has unknown stage_kind")
            as_of_date = _date(
                stage["as_of_date"], f"task {task_id}.{expected_stage_id}.as_of_date"
            )
            if prior_date is not None and as_of_date < prior_date:
                raise FrontierContractError(
                    f"task {task_id} stage chronology must be monotone"
                )
            prior_date = as_of_date
            accessible = set(
                _text_list(
                    stage["accessible_evidence_ids"],
                    f"task {task_id}.{expected_stage_id}.accessible_evidence_ids",
                    nonempty=False,
                )
            )
            if not accessible.issubset(evidence_ids):
                raise FrontierContractError(
                    f"task {task_id}.{expected_stage_id} exposes unknown evidence"
                )
            if not prior_access.issubset(accessible):
                raise FrontierContractError(
                    f"task {task_id} evidence access cannot be revoked"
                )
            for evidence_id in accessible:
                if availability_by_evidence[evidence_id] > as_of_date:
                    raise FrontierContractError(
                        f"task {task_id}.{expected_stage_id} leaks post-cutoff evidence"
                    )
            prior_access = accessible
            gates = set(
                _text_list(
                    stage["required_gates"],
                    f"task {task_id}.{expected_stage_id}.required_gates",
                )
            )
            if not gates.issubset(set(FRONTIER_MANDATORY_GATES)):
                raise FrontierContractError(
                    f"task {task_id}.{expected_stage_id} uses unknown gates"
                )
            required_gate_union.update(gates)
            total_stage_tool_budget += _integer(
                stage["max_tool_calls"],
                f"task {task_id}.{expected_stage_id}.max_tool_calls",
                minimum=0,
            )
        if prior_access != evidence_ids:
            raise FrontierContractError(
                f"task {task_id} does not expose every evidence node by its final stage"
            )
        if not set(family["required_gates"]).issubset(required_gate_union):
            raise FrontierContractError(
                f"task {task_id} does not exercise every family-required gate"
            )
        if total_stage_tool_budget != tool_call_budget:
            raise FrontierContractError(
                f"task {task_id} stage budgets do not sum to tool_call_budget"
            )
        if task["nonclaim"] != _TASK_NONCLAIM:
            raise FrontierContractError(f"task {task_id} removed its nonclaim")
        validated_tasks.append(task)

    if tuple(family_ids) != FRONTIER_TASK_FAMILIES:
        raise FrontierContractError(
            "development task set must cover each frontier family once in order"
        )
    expected_integrity = _sha256(data["integrity_sha256"], "task_set.integrity_sha256")
    actual_integrity = frontier_task_set_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier task-set integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    data["tasks"] = validated_tasks
    return data


def validate_frontier_oracle_set(
    oracle_set: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    task_set: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate evaluator-only expectations bound to a development task set."""

    tasks_data = validate_frontier_task_set(
        task_set,
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
    )
    seeds_data = validate_frontier_seed_manifest(
        seed_manifest,
        root=root,
        protocol=protocol,
    )
    seed_by_family = {seed["family_id"]: seed for seed in seeds_data["seeds"]}
    data = _record(
        oracle_set,
        "oracle_set",
        {
            "schema_version",
            "protocol_id",
            "set_id",
            "set_role",
            "benchmark_evidence_claimed",
            "task_set_integrity_sha256",
            "oracles",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_ORACLE_SET_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier oracle-set schema_version")
    if data["protocol_id"] != FRONTIER_PROTOCOL_ID:
        raise FrontierContractError("oracle set does not bind the frontier protocol")
    if data["set_id"] != tasks_data["set_id"]:
        raise FrontierContractError("oracle set_id does not match task set")
    if data["set_role"] != "public_development_oracle":
        raise FrontierContractError("oracle set has an invalid role")
    if _boolean(
        data["benchmark_evidence_claimed"], "oracle_set.benchmark_evidence_claimed"
    ):
        raise FrontierContractError(
            "development oracles cannot claim benchmark evidence"
        )
    bound_task_set_hash = _sha256(
        data["task_set_integrity_sha256"],
        "oracle_set.task_set_integrity_sha256",
    )
    if bound_task_set_hash != tasks_data["integrity_sha256"]:
        raise FrontierContractError("oracle set does not open the task-set commitment")

    task_by_id = {task["task_id"]: task for task in tasks_data["tasks"]}
    observed_task_ids: list[str] = []
    for oracle_index, oracle_item in enumerate(
        _sequence(data["oracles"], "oracle_set.oracles")
    ):
        oracle = _record(
            oracle_item,
            f"oracle_set.oracles[{oracle_index}]",
            {
                "task_id",
                "task_sha256",
                "stage_expectations",
                "mutation_expectations",
                "nonclaim",
            },
        )
        task_id = _text(oracle["task_id"], f"oracle {oracle_index}.task_id")
        observed_task_ids.append(task_id)
        task = task_by_id.get(task_id)
        if task is None:
            raise FrontierContractError(f"oracle references unknown task: {task_id}")
        if _sha256(
            oracle["task_sha256"], f"oracle {task_id}.task_sha256"
        ) != frontier_task_sha256(task):
            raise FrontierContractError(
                f"oracle {task_id} does not open task commitment"
            )
        evidence_ids = {item["evidence_id"] for item in task["evidence_nodes"]}
        stages = task["stages"]
        expectations = _sequence(
            oracle["stage_expectations"], f"oracle {task_id}.stage_expectations"
        )
        if len(expectations) != len(stages):
            raise FrontierContractError(f"oracle {task_id} must cover every task stage")
        for stage_index, expectation_item in enumerate(expectations):
            expectation = _record(
                expectation_item,
                f"oracle {task_id}.stage_expectations[{stage_index}]",
                {
                    "stage_id",
                    "action",
                    "witness_evidence_ids",
                    "blocker_codes",
                },
            )
            stage = stages[stage_index]
            if expectation["stage_id"] != stage["stage_id"]:
                raise FrontierContractError(
                    f"oracle {task_id} stage order does not match task"
                )
            action_data = _record(
                expectation["action"],
                f"oracle {task_id}.{stage['stage_id']}.action",
                {"disposition", "next_action", "risk_flags"},
            )
            FrontierAction(
                disposition=action_data["disposition"],
                next_action=action_data["next_action"],
                risk_flags=tuple(
                    _text_list(
                        action_data["risk_flags"],
                        f"oracle {task_id}.{stage['stage_id']}.action.risk_flags",
                        nonempty=False,
                    )
                ),
            )
            witnesses = set(
                _text_list(
                    expectation["witness_evidence_ids"],
                    f"oracle {task_id}.{stage['stage_id']}.witness_evidence_ids",
                    nonempty=False,
                )
            )
            if not witnesses.issubset(evidence_ids):
                raise FrontierContractError(
                    f"oracle {task_id}.{stage['stage_id']} references unknown witness"
                )
            if not witnesses.issubset(set(stage["accessible_evidence_ids"])):
                raise FrontierContractError(
                    f"oracle {task_id}.{stage['stage_id']} uses inaccessible witness"
                )
            _text_list(
                expectation["blocker_codes"],
                f"oracle {task_id}.{stage['stage_id']}.blocker_codes",
                nonempty=False,
            )

        mutations = _sequence(
            oracle["mutation_expectations"],
            f"oracle {task_id}.mutation_expectations",
        )
        if len(mutations) < 5:
            raise FrontierContractError(
                f"oracle {task_id} requires at least five mutations"
            )
        mutation_ids: set[str] = set()
        mutation_classes: set[str] = set()
        for mutation_index, mutation_item in enumerate(mutations):
            mutation = _record(
                mutation_item,
                f"oracle {task_id}.mutation_expectations[{mutation_index}]",
                {
                    "mutation_id",
                    "mutation_class",
                    "operation",
                    "expected_changed_components",
                },
            )
            mutation_id = _text(
                mutation["mutation_id"],
                f"oracle {task_id}.mutation {mutation_index}.mutation_id",
            )
            if mutation_id in mutation_ids:
                raise FrontierContractError(
                    f"oracle {task_id} has duplicate mutation_id"
                )
            mutation_ids.add(mutation_id)
            mutation_class = _text(
                mutation["mutation_class"],
                f"oracle {task_id}.mutation {mutation_id}.mutation_class",
            )
            if mutation_class not in FRONTIER_MUTATION_CLASSES:
                raise FrontierContractError(
                    f"oracle {task_id} has unknown mutation class"
                )
            mutation_classes.add(mutation_class)
            _text(
                mutation["operation"],
                f"oracle {task_id}.mutation {mutation_id}.operation",
            )
            changed = _text_list(
                mutation["expected_changed_components"],
                f"oracle {task_id}.mutation {mutation_id}.expected_changed_components",
                nonempty=False,
            )
            if not set(changed).issubset(set(FRONTIER_CHANGED_COMPONENTS)):
                raise FrontierContractError(
                    f"oracle {task_id} mutation changes an unknown component"
                )
            if mutation_class == "nuisance_invariance" and changed:
                raise FrontierContractError(
                    f"oracle {task_id} nuisance mutation cannot change the oracle"
                )
            if mutation_class != "nuisance_invariance" and not changed:
                raise FrontierContractError(
                    f"oracle {task_id} causal mutation must change an oracle component"
                )
        if mutation_classes != set(FRONTIER_MUTATION_CLASSES):
            raise FrontierContractError(
                f"oracle {task_id} must cover all mutation classes"
            )
        expected_mutation_ids = seed_by_family[task["family_id"]]["planned_mutations"]
        if [item["mutation_id"] for item in mutations] != expected_mutation_ids:
            raise FrontierContractError(
                f"oracle {task_id} mutations changed the design-seed binding"
            )
        if oracle["nonclaim"] != _ORACLE_NONCLAIM:
            raise FrontierContractError(f"oracle {task_id} removed its nonclaim")

    expected_task_ids = [task["task_id"] for task in tasks_data["tasks"]]
    if observed_task_ids != expected_task_ids:
        raise FrontierContractError(
            "oracle set must cover each task exactly once in order"
        )
    expected_integrity = _sha256(
        data["integrity_sha256"], "oracle_set.integrity_sha256"
    )
    actual_integrity = frontier_oracle_set_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier oracle-set integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def validate_frontier_curation_tranche(
    curation: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate development curation status without admitting private-board tasks."""

    tasks_data = validate_frontier_task_set(
        task_set,
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
    )
    oracles_data = validate_frontier_oracle_set(
        oracle_set,
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
        task_set=tasks_data,
    )
    data = _record(
        curation,
        "curation",
        {
            "schema_version",
            "protocol_id",
            "set_id",
            "status",
            "canonical_task_target",
            "development_fixture_count",
            "independent_review_complete",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "task_set_integrity_sha256",
            "oracle_set_integrity_sha256",
            "records",
            "nonclaim",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_CURATION_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier curation schema_version")
    if (
        data["protocol_id"] != FRONTIER_PROTOCOL_ID
        or data["set_id"] != tasks_data["set_id"]
    ):
        raise FrontierContractError("curation does not bind the development set")
    if data["status"] != "development_curation_in_progress":
        raise FrontierContractError("curation status overstates pilot maturity")
    if (
        _integer(
            data["canonical_task_target"], "curation.canonical_task_target", minimum=1
        )
        != 40
    ):
        raise FrontierContractError("curation must preserve the 40-task pilot target")
    if (
        _integer(
            data["development_fixture_count"],
            "curation.development_fixture_count",
            minimum=0,
        )
        != 5
    ):
        raise FrontierContractError("curation must report five development fixtures")
    for field_name in (
        "independent_review_complete",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
    ):
        if _boolean(data[field_name], f"curation.{field_name}"):
            raise FrontierContractError(f"curation.{field_name} must remain false")
    if (
        _sha256(data["task_set_integrity_sha256"], "curation.task_set_integrity_sha256")
        != tasks_data["integrity_sha256"]
    ):
        raise FrontierContractError("curation does not open the task-set commitment")
    if (
        _sha256(
            data["oracle_set_integrity_sha256"], "curation.oracle_set_integrity_sha256"
        )
        != oracles_data["integrity_sha256"]
    ):
        raise FrontierContractError("curation does not open the oracle-set commitment")

    records = _sequence(data["records"], "curation.records")
    if len(records) != len(tasks_data["tasks"]):
        raise FrontierContractError("curation must cover every development task")
    observed_task_ids: list[str] = []
    for index, item in enumerate(records):
        record = _record(
            item,
            f"curation.records[{index}]",
            {
                "task_id",
                "family_id",
                "authoring_blinded_to_baseline",
                "scientific_review_status",
                "lineage_review_status",
                "leakage_review_status",
                "mutation_review_status",
                "independent_curator_count",
                "curator_roster_commitment",
                "board_admitted",
            },
        )
        task = tasks_data["tasks"][index]
        if (
            record["task_id"] != task["task_id"]
            or record["family_id"] != task["family_id"]
        ):
            raise FrontierContractError("curation record order or task binding changed")
        observed_task_ids.append(record["task_id"])
        if not _boolean(
            record["authoring_blinded_to_baseline"],
            f"curation record {record['task_id']}.authoring_blinded_to_baseline",
        ):
            raise FrontierContractError(
                "development authoring must remain baseline-blind"
            )
        for field_name in (
            "scientific_review_status",
            "lineage_review_status",
            "leakage_review_status",
            "mutation_review_status",
        ):
            if record[field_name] != "pending":
                raise FrontierContractError(
                    f"curation record {record['task_id']} overstates review completion"
                )
        if (
            _integer(
                record["independent_curator_count"],
                f"curation record {record['task_id']}.independent_curator_count",
                minimum=0,
            )
            != 0
        ):
            raise FrontierContractError(
                "development fixtures have no independent curator count"
            )
        if record["curator_roster_commitment"] is not None:
            raise FrontierContractError(
                "development fixtures cannot claim a curator roster"
            )
        if _boolean(
            record["board_admitted"],
            f"curation record {record['task_id']}.board_admitted",
        ):
            raise FrontierContractError(
                "development fixtures cannot enter the private board"
            )
    if len(observed_task_ids) != len(set(observed_task_ids)):
        raise FrontierContractError("curation contains duplicate task records")
    if data["nonclaim"] != _CURATION_NONCLAIM:
        raise FrontierContractError("curation removed its nonclaim")
    expected_integrity = _sha256(data["integrity_sha256"], "curation.integrity_sha256")
    actual_integrity = frontier_curation_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier curation integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def frontier_task_set_from_json(
    text: str,
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_frontier_task_set(
        _load_json(text, "frontier task set"),
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
    )


def load_frontier_task_set(
    path: Path,
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return frontier_task_set_from_json(
        path.read_text(encoding="utf-8"),
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
    )


def load_frontier_oracle_set(
    path: Path,
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    task_set: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_frontier_oracle_set(
        _load_json(path.read_text(encoding="utf-8"), "frontier oracle set"),
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
        task_set=task_set,
    )


def load_frontier_curation_tranche(
    path: Path,
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_frontier_curation_tranche(
        _load_json(path.read_text(encoding="utf-8"), "frontier curation tranche"),
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
        task_set=task_set,
        oracle_set=oracle_set,
    )


def frontier_development_summary(
    curation: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
    seed_manifest: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_frontier_curation_tranche(
        curation,
        root=root,
        protocol=protocol,
        seed_manifest=seed_manifest,
        task_set=task_set,
        oracle_set=oracle_set,
    )
    return {
        "protocol_id": data["protocol_id"],
        "set_id": data["set_id"],
        "status": data["status"],
        "development_fixture_count": data["development_fixture_count"],
        "canonical_task_target": data["canonical_task_target"],
        "independent_review_complete": data["independent_review_complete"],
        "baseline_model_runs_started": data["baseline_model_runs_started"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
        "board_admitted_count": sum(
            bool(record["board_admitted"]) for record in data["records"]
        ),
    }
