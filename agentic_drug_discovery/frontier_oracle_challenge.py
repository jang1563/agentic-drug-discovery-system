"""Independent expert challenge contracts for private ADDS-Frontier oracles."""

from __future__ import annotations

import copy
import hashlib
import json
import re
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
    _sequence,
    _sha256,
    _text,
    _text_list,
)
from .frontier_board import FRONTIER_BOARD_ID
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
from .frontier_tasks import (
    FRONTIER_EVIDENCE_ROLES,
    FRONTIER_LINEAGE_RELATIONSHIPS,
    FRONTIER_STAGE_KINDS,
    score_frontier_stage_components,
)


FRONTIER_ORACLE_CHALLENGE_PACKET_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-challenge-packet-set.v1"
)
FRONTIER_ORACLE_CHALLENGE_KEY_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-challenge-key-set.v1"
)
FRONTIER_ORACLE_CHALLENGE_RESPONSE_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-challenge-response.v1"
)
FRONTIER_ORACLE_CHALLENGE_COMPARISON_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-challenge-comparison.v1"
)
FRONTIER_ORACLE_CHALLENGE_LEDGER_SCHEMA_VERSION = (
    "adds.frontier-private-oracle-challenge-ledger.v1"
)
FRONTIER_ORACLE_CHALLENGE_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-oracle-challenge-readiness-summary.v1"
)
FRONTIER_ORACLE_CHALLENGE_SET_ID = "adds-frontier-independent-oracle-challenge-v1"
FRONTIER_ORACLE_CHALLENGE_ROUTES = (
    "adjudication_required_challenger_abstention",
    "adjudication_required_challenger_disagreement",
    "adjudication_required_author_oracle_disagreement",
    "oracle_convergence_candidate",
)
FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE = (
    "open_author_oracle_only_after_two_valid_independent_responses"
)
FRONTIER_ORACLE_CHALLENGE_COMPARISON_RULE = (
    "exact_two_challenger_agreement_then_thirty_component_author_oracle_comparison"
)

_CHALLENGE_VIEW_FIELDS = {
    "family_id",
    "disease_domain",
    "temporal_regime",
    "disease_identity",
    "program_identity",
    "prompt",
    "anchor_cutoff_date",
    "stage_budget",
    "tool_call_budget",
    "evidence_nodes",
    "lineage_edges",
    "stages",
}
_COMPONENT_FIELDS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_SCORE_TO_COMPONENT = {
    "disposition_correct": "disposition",
    "next_action_correct": "next_action",
    "risk_flags_correct": "risk_flags",
    "witness_valid": "witness",
    "blocker_certificate_valid": "blockers",
}
_PACKET_NONCLAIMS = {
    "Challenge packets expose canonical task evidence but not author-oracle labels or mappings.",
    "Packet compilation is not an independent expert solve or scientific judgment.",
    "Two-challenger agreement cannot establish source truth or exclude shared expert error.",
    "No challenger response, oracle convergence, adjudication, or board admission is claimed.",
}
_PUBLIC_NONCLAIMS = {
    "Challenge readiness is not an independent expert solve or scientific judgment.",
    "Two-challenger agreement is necessary for convergence but does not establish correctness.",
    "Shared challenger error remains possible even when both challengers and the author oracle agree.",
    "No private task, oracle, packet, key, response, comparison, challenger, or affiliation bytes are public.",
    "No challenger assignment, response, convergence, adjudication, board admission, model run, or benchmark result is claimed.",
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


def frontier_oracle_challenge_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_key_set_integrity_sha256(
    key_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(key_set, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_response_integrity_sha256(
    response: Mapping[str, Any],
) -> str:
    return _canonical_sha256(response, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_comparison_integrity_sha256(
    comparison: Mapping[str, Any],
) -> str:
    return _canonical_sha256(comparison, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_ledger_integrity_sha256(
    ledger: Mapping[str, Any],
) -> str:
    return _canonical_sha256(ledger, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def frontier_oracle_challenge_view(task: Mapping[str, Any]) -> dict[str, Any]:
    """Project a canonical task into the private challenger-visible view."""

    return {
        field_name: copy.deepcopy(task[field_name])
        for field_name in sorted(_CHALLENGE_VIEW_FIELDS)
    }


def _packet_index(packet_set: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    packets = _sequence(packet_set.get("packets"), "oracle_challenge_packets.packets")
    index: dict[str, dict[str, Any]] = {}
    for item_index, item in enumerate(packets):
        packet = _record(
            item,
            f"oracle_challenge_packets.packets[{item_index}]",
            {"packet_id", "challenge_task", "challenge_task_commitment"},
        )
        packet_id = _text(packet["packet_id"], f"challenge packet {item_index} id")
        if re.fullmatch(r"oracle-challenge-[0-9a-f]{20}", packet_id) is None:
            raise FrontierContractError("oracle challenge packet id is malformed")
        if packet_id in index:
            raise FrontierContractError("oracle challenge packet ids must be unique")
        challenge_task = _record(
            packet["challenge_task"],
            f"oracle challenge packet {packet_id} task",
            _CHALLENGE_VIEW_FIELDS,
        )
        if (
            _sha256(
                packet["challenge_task_commitment"],
                f"oracle challenge packet {packet_id} task commitment",
            )
            != _canonical_sha256(challenge_task)
        ):
            raise FrontierContractError(
                "oracle challenge packet task commitment mismatch"
            )
        stages = _sequence(
            challenge_task["stages"], f"oracle challenge packet {packet_id} stages"
        )
        if len(stages) != 6 or _integer(
            challenge_task["stage_budget"],
            f"oracle challenge packet {packet_id} stage_budget",
            minimum=6,
        ) != 6:
            raise FrontierContractError(
                "oracle challenge packet must preserve the six-stage contract"
            )
        if challenge_task["family_id"] not in FRONTIER_TASK_FAMILIES:
            raise FrontierContractError("oracle challenge task family is invalid")
        if challenge_task["disease_domain"] not in {
            "hematology",
            "immune_inflammatory",
        }:
            raise FrontierContractError("oracle challenge disease domain is invalid")
        if challenge_task["temporal_regime"] not in {
            "historical_pre_2024",
            "historical_2024_2025",
        }:
            raise FrontierContractError("oracle challenge temporal regime is invalid")
        for field_name in ("disease_identity", "program_identity", "prompt"):
            _text(
                challenge_task[field_name],
                f"oracle challenge packet {packet_id} {field_name}",
            )
        _date(
            challenge_task["anchor_cutoff_date"],
            f"oracle challenge packet {packet_id} anchor cutoff",
        )
        tool_call_budget = _integer(
            challenge_task["tool_call_budget"],
            f"oracle challenge packet {packet_id} tool budget",
            minimum=1,
        )
        evidence_ids: set[str] = set()
        evidence_dates = {}
        lineage_by_id = {}
        evidence_nodes = _sequence(
            challenge_task["evidence_nodes"],
            f"oracle challenge packet {packet_id} evidence",
        )
        if len(evidence_nodes) < 2:
            raise FrontierContractError(
                "oracle challenge packet requires at least two evidence nodes"
            )
        for evidence_index, node_item in enumerate(evidence_nodes):
            node = _record(
                node_item,
                f"oracle challenge packet {packet_id} evidence {evidence_index}",
                {
                    "evidence_id",
                    "available_on",
                    "lineage_id",
                    "evidence_role",
                    "evidence_summary",
                },
            )
            evidence_id = _text(node["evidence_id"], "oracle challenge evidence id")
            if evidence_id in evidence_ids:
                raise FrontierContractError(
                    "oracle challenge packet contains duplicate evidence ids"
                )
            evidence_ids.add(evidence_id)
            evidence_dates[evidence_id] = _date(
                node["available_on"], "oracle challenge evidence available_on"
            )
            lineage_by_id[evidence_id] = _text(
                node["lineage_id"], "oracle challenge evidence lineage_id"
            )
            if node["evidence_role"] not in FRONTIER_EVIDENCE_ROLES:
                raise FrontierContractError(
                    "oracle challenge evidence role is invalid"
                )
            _text(node["evidence_summary"], "oracle challenge evidence summary")

        adjacency = {evidence_id: set() for evidence_id in evidence_ids}
        seen_edges: set[tuple[str, str, str]] = set()
        for edge_index, edge_item in enumerate(
            _sequence(
                challenge_task["lineage_edges"],
                f"oracle challenge packet {packet_id} lineage edges",
            )
        ):
            edge = _record(
                edge_item,
                f"oracle challenge packet {packet_id} edge {edge_index}",
                {"parent_evidence_id", "child_evidence_id", "relationship"},
            )
            parent = _text(edge["parent_evidence_id"], "oracle challenge edge parent")
            child = _text(edge["child_evidence_id"], "oracle challenge edge child")
            relationship = _text(
                edge["relationship"], "oracle challenge edge relationship"
            )
            key = (parent, child, relationship)
            if (
                parent not in evidence_ids
                or child not in evidence_ids
                or parent == child
                or relationship not in FRONTIER_LINEAGE_RELATIONSHIPS
                or key in seen_edges
            ):
                raise FrontierContractError("oracle challenge lineage edge is invalid")
            if (
                relationship == "derives_from"
                and lineage_by_id[parent] != lineage_by_id[child]
            ):
                raise FrontierContractError(
                    "oracle challenge derivative edge crosses lineage roots"
                )
            seen_edges.add(key)
            adjacency[parent].add(child)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise FrontierContractError("oracle challenge lineage graph has a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child_id in adjacency[node_id]:
                visit(child_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for evidence_id in evidence_ids:
            visit(evidence_id)

        prior_access: set[str] = set()
        prior_date = None
        total_stage_calls = 0
        for stage_index, stage_item in enumerate(stages):
            stage = _record(
                stage_item,
                f"oracle challenge packet {packet_id} stage {stage_index}",
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
                raise FrontierContractError("oracle challenge stage order is invalid")
            if stage["stage_kind"] not in FRONTIER_STAGE_KINDS:
                raise FrontierContractError("oracle challenge stage kind is invalid")
            as_of_date = _date(
                stage["as_of_date"], "oracle challenge stage as_of_date"
            )
            if prior_date is not None and as_of_date < prior_date:
                raise FrontierContractError(
                    "oracle challenge stage chronology must be monotone"
                )
            prior_date = as_of_date
            accessible = _text_list(
                stage["accessible_evidence_ids"],
                f"oracle challenge packet {packet_id} stage access",
            )
            if len(accessible) != len(set(accessible)) or not set(
                accessible
            ).issubset(evidence_ids):
                raise FrontierContractError(
                    "oracle challenge stage has invalid evidence access"
                )
            if not prior_access.issubset(accessible):
                raise FrontierContractError(
                    "oracle challenge evidence access must be cumulative"
                )
            if any(evidence_dates[item] > as_of_date for item in accessible):
                raise FrontierContractError(
                    "oracle challenge stage exposes unavailable evidence"
                )
            prior_access = set(accessible)
            gates = _text_list(
                stage["required_gates"], "oracle challenge stage required gates"
            )
            if len(gates) != len(set(gates)) or not set(gates).issubset(
                FRONTIER_MANDATORY_GATES
            ):
                raise FrontierContractError(
                    "oracle challenge stage has invalid required gates"
                )
            total_stage_calls += _integer(
                stage["max_tool_calls"],
                "oracle challenge stage max tool calls",
                minimum=1,
            )
        if total_stage_calls != tool_call_budget:
            raise FrontierContractError(
                "oracle challenge stage calls do not match tool budget"
            )
        index[packet_id] = dict(packet)
    if len(index) != 10:
        raise FrontierContractError("oracle challenge requires exactly ten packets")
    return index


def validate_frontier_oracle_challenge_packet_set(
    packet_set: Mapping[str, Any],
) -> dict[str, Any]:
    data = _record(
        packet_set,
        "oracle_challenge_packets",
        {
            "schema_version",
            "set_id",
            "protocol_id",
            "board_id",
            "compiled_on",
            "private_preflight_integrity_sha256",
            "author_oracle_labels_included",
            "semantic_review_material_included",
            "authoring_source_artifacts_included",
            "task_identity_mapping_included",
            "minimum_independent_challengers_per_packet",
            "challenge_instructions",
            "packets",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_ORACLE_CHALLENGE_PACKET_SCHEMA_VERSION:
        raise FrontierContractError("unsupported oracle challenge packet schema")
    if data["set_id"] != FRONTIER_ORACLE_CHALLENGE_SET_ID:
        raise FrontierContractError("unexpected oracle challenge set id")
    if (
        data["protocol_id"] != FRONTIER_PROTOCOL_ID
        or data["board_id"] != FRONTIER_BOARD_ID
    ):
        raise FrontierContractError("oracle challenge packet set rebound protocol or board")
    _date(data["compiled_on"], "oracle_challenge_packets.compiled_on")
    _sha256(
        data["private_preflight_integrity_sha256"],
        "oracle_challenge_packets.private_preflight_integrity_sha256",
    )
    for field_name in (
        "author_oracle_labels_included",
        "semantic_review_material_included",
        "authoring_source_artifacts_included",
        "task_identity_mapping_included",
    ):
        if _boolean(data[field_name], f"oracle_challenge_packets.{field_name}"):
            raise FrontierContractError(
                f"oracle_challenge_packets.{field_name} must remain false"
            )
    if (
        _integer(
            data["minimum_independent_challengers_per_packet"],
            "oracle challenge minimum challengers",
        )
        != 2
    ):
        raise FrontierContractError("oracle challenge requires two challengers")
    _text_list(data["challenge_instructions"], "oracle challenge instructions")
    if not _PACKET_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "oracle challenge packet nonclaims"))
    ):
        raise FrontierContractError("oracle challenge packets removed a nonclaim")
    _packet_index(data)
    if data["integrity_sha256"] != frontier_oracle_challenge_packet_set_integrity_sha256(
        data
    ):
        raise FrontierContractError("oracle challenge packet-set integrity mismatch")
    return data


def validate_frontier_oracle_challenge_response(
    response: Mapping[str, Any], *, packet_set: Mapping[str, Any]
) -> dict[str, Any]:
    packet_data = validate_frontier_oracle_challenge_packet_set(packet_set)
    packets = _packet_index(packet_data)
    data = _record(
        response,
        "oracle_challenge_response",
        {
            "schema_version",
            "packet_id",
            "packet_set_integrity_sha256",
            "challenge_task_commitment",
            "challenger_identity_commitment",
            "challenger_affiliation_commitment",
            "conflict_of_interest_declared",
            "independence_attested",
            "author_oracle_accessed",
            "semantic_review_material_accessed",
            "authoring_source_artifacts_accessed",
            "completed_on",
            "stage_answers",
            "overall_abstained",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_ORACLE_CHALLENGE_RESPONSE_SCHEMA_VERSION:
        raise FrontierContractError("unsupported oracle challenge response schema")
    packet_id = _text(data["packet_id"], "oracle challenge response packet_id")
    if packet_id not in packets:
        raise FrontierContractError("oracle challenge response references unknown packet")
    packet = packets[packet_id]
    if (
        _sha256(
            data["packet_set_integrity_sha256"],
            "oracle challenge response packet-set commitment",
        )
        != packet_data["integrity_sha256"]
        or _sha256(
            data["challenge_task_commitment"],
            "oracle challenge response task commitment",
        )
        != packet["challenge_task_commitment"]
    ):
        raise FrontierContractError("oracle challenge response rebound its packet")
    _sha256(
        data["challenger_identity_commitment"],
        "oracle challenge challenger identity commitment",
    )
    _sha256(
        data["challenger_affiliation_commitment"],
        "oracle challenge challenger affiliation commitment",
    )
    if _boolean(
        data["conflict_of_interest_declared"],
        "oracle challenge conflict_of_interest_declared",
    ):
        raise FrontierContractError("conflicted challenger response is not eligible")
    if not _boolean(
        data["independence_attested"], "oracle challenge independence_attested"
    ):
        raise FrontierContractError("oracle challenge independence must be attested")
    for field_name in (
        "author_oracle_accessed",
        "semantic_review_material_accessed",
        "authoring_source_artifacts_accessed",
    ):
        if _boolean(data[field_name], f"oracle challenge response {field_name}"):
            raise FrontierContractError(
                f"oracle challenge response {field_name} must remain false"
            )
    completed_on = _date(
        data["completed_on"], "oracle challenge response completed_on"
    )
    if completed_on < _date(
        packet_data["compiled_on"], "oracle challenge packet compiled_on"
    ):
        raise FrontierContractError(
            "oracle challenge response predates packet compilation"
        )

    stages = packet["challenge_task"]["stages"]
    answers = _sequence(data["stage_answers"], "oracle challenge stage answers")
    if len(answers) != len(stages):
        raise FrontierContractError("oracle challenge response must answer every stage")
    any_abstention = False
    for index, (answer_item, stage) in enumerate(zip(answers, stages, strict=True)):
        answer = _record(
            answer_item,
            f"oracle challenge stage answer {index}",
            {
                "stage_id",
                "disposition",
                "next_action",
                "risk_flags",
                "witness_evidence_ids",
                "blocker_codes",
                "abstained",
            },
        )
        if answer["stage_id"] != stage["stage_id"]:
            raise FrontierContractError("oracle challenge response rebound a stage")
        FrontierAction(
            disposition=answer["disposition"],
            next_action=answer["next_action"],
            risk_flags=tuple(
                _text_list(
                    answer["risk_flags"],
                    f"oracle challenge answer {index} risk flags",
                    nonempty=False,
                )
            ),
        )
        witnesses = _text_list(
            answer["witness_evidence_ids"],
            f"oracle challenge answer {index} witnesses",
            nonempty=False,
        )
        blockers = _text_list(
            answer["blocker_codes"],
            f"oracle challenge answer {index} blockers",
            nonempty=False,
        )
        if len(witnesses) != len(set(witnesses)) or not set(witnesses).issubset(
            stage["accessible_evidence_ids"]
        ):
            raise FrontierContractError(
                "oracle challenge response cites inaccessible or duplicate evidence"
            )
        if len(blockers) != len(set(blockers)):
            raise FrontierContractError(
                "oracle challenge response blocker codes must be unique"
            )
        any_abstention = any_abstention or _boolean(
            answer["abstained"], f"oracle challenge answer {index} abstained"
        )
    overall_abstained = _boolean(
        data["overall_abstained"], "oracle challenge response overall_abstained"
    )
    if overall_abstained != any_abstention:
        raise FrontierContractError(
            "oracle challenge stage abstention must equal overall abstention"
        )
    if data["integrity_sha256"] != frontier_oracle_challenge_response_integrity_sha256(
        data
    ):
        raise FrontierContractError("oracle challenge response integrity mismatch")
    return data


def _challenger_disagreements(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> list[str]:
    disagreements: list[str] = []
    for first_answer, second_answer in zip(
        first["stage_answers"], second["stage_answers"], strict=True
    ):
        stage_id = first_answer["stage_id"]
        for component in _COMPONENT_FIELDS:
            first_value: Any
            second_value: Any
            if component == "witness":
                first_value = set(first_answer["witness_evidence_ids"])
                second_value = set(second_answer["witness_evidence_ids"])
            elif component == "blockers":
                first_value = set(first_answer["blocker_codes"])
                second_value = set(second_answer["blocker_codes"])
            elif component == "risk_flags":
                first_value = set(first_answer["risk_flags"])
                second_value = set(second_answer["risk_flags"])
            else:
                first_value = first_answer[component]
                second_value = second_answer[component]
            if first_value != second_value:
                disagreements.append(f"{stage_id}.{component}")
        if first_answer["abstained"] != second_answer["abstained"]:
            disagreements.append(f"{stage_id}.abstained")
    return disagreements


def _validate_key_opening(
    *,
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    packet_data = validate_frontier_oracle_challenge_packet_set(packet_set)
    tasks_data = validate_frontier_calibration_task_set(task_set, **validation_kwargs)
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set, task_set=tasks_data, **validation_kwargs
    )
    data = _record(
        key_set,
        "oracle_challenge_keys",
        {
            "schema_version",
            "set_id",
            "protocol_id",
            "board_id",
            "compiled_on",
            "packet_set_integrity_sha256",
            "task_set_integrity_sha256",
            "oracle_set_integrity_sha256",
            "author_oracle_reveal_rule",
            "keys",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_ORACLE_CHALLENGE_KEY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported oracle challenge key schema")
    if data["set_id"] != FRONTIER_ORACLE_CHALLENGE_SET_ID:
        raise FrontierContractError("unexpected oracle challenge key set id")
    if (
        data["protocol_id"] != tasks_data["protocol_id"]
        or data["board_id"] != tasks_data["board_id"]
        or data["compiled_on"] != packet_data["compiled_on"]
    ):
        raise FrontierContractError("oracle challenge keys rebound provenance")
    if data["author_oracle_reveal_rule"] != FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE:
        raise FrontierContractError("oracle challenge changed its reveal rule")
    commitments = {
        "packet_set_integrity_sha256": packet_data["integrity_sha256"],
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
    }
    for field_name, expected in commitments.items():
        if _sha256(data[field_name], f"oracle challenge keys {field_name}") != expected:
            raise FrontierContractError(
                f"oracle challenge keys do not bind {field_name}"
            )
    packets = _packet_index(packet_data)
    tasks_by_slot = {task["slot_id"]: task for task in tasks_data["tasks"]}
    oracles_by_slot = {
        oracle["slot_id"]: oracle for oracle in oracles_data["oracles"]
    }
    key_index: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_sequence(data["keys"], "oracle challenge keys")):
        key = _record(
            item,
            f"oracle challenge key {index}",
            {
                "packet_id",
                "slot_id",
                "task_id",
                "canonical_task_commitment",
                "author_oracle_commitment",
            },
        )
        packet_id = _text(key["packet_id"], f"oracle challenge key {index} packet")
        if packet_id in key_index or packet_id not in packets:
            raise FrontierContractError("oracle challenge key mapping is invalid")
        task = tasks_by_slot.get(key["slot_id"])
        oracle = oracles_by_slot.get(key["slot_id"])
        if task is None or oracle is None or key["task_id"] != task["task_id"]:
            raise FrontierContractError("oracle challenge key rebound task identity")
        if (
            key["canonical_task_commitment"]
            != frontier_calibration_task_sha256(task)
            or key["author_oracle_commitment"]
            != frontier_calibration_oracle_sha256(oracle)
            or packets[packet_id]["challenge_task"]
            != frontier_oracle_challenge_view(task)
        ):
            raise FrontierContractError("oracle challenge key does not open its packet")
        key_index[packet_id] = dict(key)
    if set(key_index) != set(packets):
        raise FrontierContractError("oracle challenge keys do not cover all packets")
    if data["integrity_sha256"] != frontier_oracle_challenge_key_set_integrity_sha256(
        data
    ):
        raise FrontierContractError("oracle challenge key-set integrity mismatch")
    return tasks_data, oracles_data, key_index


def compare_frontier_oracle_challenge_responses(
    responses: Sequence[Mapping[str, Any]],
    *,
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    packet_id: str,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare challengers first and open the author oracle only after agreement."""

    packet_data = validate_frontier_oracle_challenge_packet_set(packet_set)
    validated = [
        validate_frontier_oracle_challenge_response(item, packet_set=packet_data)
        for item in responses
    ]
    if any(item["packet_id"] != packet_id for item in validated):
        raise FrontierContractError("oracle challenge comparison cannot mix packets")
    if len(validated) > 2:
        raise FrontierContractError("oracle challenge comparison accepts two responses")
    challenger_ids = [
        item["challenger_identity_commitment"] for item in validated
    ]
    if len(challenger_ids) != len(set(challenger_ids)):
        raise FrontierContractError("oracle challenge requires unique challengers")

    route = "awaiting_challengers"
    challenger_disagreements: list[str] = []
    author_disagreements: list[str] = []
    component_match_count: int | None = None
    component_total: int | None = None
    author_oracle_opened = False
    opened_key_set_commitment: str | None = None
    opened_author_oracle_commitment: str | None = None
    convergence_commitment: str | None = None
    if len(validated) == 2:
        if any(item["overall_abstained"] for item in validated):
            route = FRONTIER_ORACLE_CHALLENGE_ROUTES[0]
        else:
            challenger_disagreements = _challenger_disagreements(
                validated[0], validated[1]
            )
            if challenger_disagreements:
                route = FRONTIER_ORACLE_CHALLENGE_ROUTES[1]
            else:
                tasks_data, oracles_data, keys = _validate_key_opening(
                    packet_set=packet_data,
                    key_set=key_set,
                    task_set=task_set,
                    oracle_set=oracle_set,
                    root=root,
                    frontier_protocol=frontier_protocol,
                    board_protocol=board_protocol,
                    board_slots=board_slots,
                )
                author_oracle_opened = True
                key = keys.get(packet_id)
                if key is None:
                    raise FrontierContractError(
                        "oracle challenge packet has no sealed mapping"
                    )
                opened_key_set_commitment = key_set["integrity_sha256"]
                opened_author_oracle_commitment = key["author_oracle_commitment"]
                task = next(
                    item for item in tasks_data["tasks"] if item["slot_id"] == key["slot_id"]
                )
                oracle = next(
                    item
                    for item in oracles_data["oracles"]
                    if item["slot_id"] == key["slot_id"]
                )
                if len(validated[0]["stage_answers"]) != len(
                    oracle["stage_expectations"]
                ):
                    raise FrontierContractError(
                        "oracle challenge response and author oracle stage counts differ"
                    )
                component_total = 5 * len(oracle["stage_expectations"])
                component_match_count = 0
                for answer, expectation, stage in zip(
                    validated[0]["stage_answers"],
                    oracle["stage_expectations"],
                    task["stages"],
                    strict=True,
                ):
                    if answer["stage_id"] != stage["stage_id"]:
                        raise FrontierContractError(
                            "oracle challenge comparison rebound stage identity"
                        )
                    scores = score_frontier_stage_components(
                        expectation,
                        action=FrontierAction(
                            disposition=answer["disposition"],
                            next_action=answer["next_action"],
                            risk_flags=tuple(answer["risk_flags"]),
                        ),
                        witness_evidence_ids=answer["witness_evidence_ids"],
                        blocker_codes=answer["blocker_codes"],
                    )
                    component_match_count += sum(scores.values())
                    author_disagreements.extend(
                        f"{answer['stage_id']}.{_SCORE_TO_COMPONENT[score_name]}"
                        for score_name, passed in scores.items()
                        if not passed
                    )
                if author_disagreements:
                    route = FRONTIER_ORACLE_CHALLENGE_ROUTES[2]
                else:
                    route = FRONTIER_ORACLE_CHALLENGE_ROUTES[3]
                    convergence_commitment = _canonical_sha256(
                        {
                            "packet_id": packet_id,
                            "response_commitments": sorted(
                                item["integrity_sha256"] for item in validated
                            ),
                            "author_oracle_commitment": key[
                                "author_oracle_commitment"
                            ],
                            "component_match_count": component_match_count,
                        }
                    )

    comparison: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_COMPARISON_SCHEMA_VERSION,
        "packet_id": packet_id,
        "packet_set_integrity_sha256": packet_data["integrity_sha256"],
        "response_count": len(validated),
        "response_commitments": sorted(
            item["integrity_sha256"] for item in validated
        ),
        "route": route,
        "challenger_disagreement_components": challenger_disagreements,
        "author_oracle_disagreement_components": author_disagreements,
        "component_match_count": component_match_count,
        "component_total": component_total,
        "author_oracle_opened": author_oracle_opened,
        "opened_key_set_integrity_sha256": opened_key_set_commitment,
        "opened_author_oracle_commitment": opened_author_oracle_commitment,
        "oracle_convergence_candidate_commitment": convergence_commitment,
        "human_adjudication_required": route
        in FRONTIER_ORACLE_CHALLENGE_ROUTES[:3],
        "human_admission_review_required": True,
        "scientific_correctness_established": False,
        "shared_expert_error_excluded": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    comparison["integrity_sha256"] = (
        frontier_oracle_challenge_comparison_integrity_sha256(comparison)
    )
    return validate_frontier_oracle_challenge_comparison(
        comparison, packet_set=packet_data
    )


def validate_frontier_oracle_challenge_comparison(
    comparison: Mapping[str, Any], *, packet_set: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate route-specific reveal, disagreement, and non-promotion invariants."""

    packet_data = validate_frontier_oracle_challenge_packet_set(packet_set)
    packets = _packet_index(packet_data)
    data = _record(
        comparison,
        "oracle_challenge_comparison",
        {
            "schema_version",
            "packet_id",
            "packet_set_integrity_sha256",
            "response_count",
            "response_commitments",
            "route",
            "challenger_disagreement_components",
            "author_oracle_disagreement_components",
            "component_match_count",
            "component_total",
            "author_oracle_opened",
            "opened_key_set_integrity_sha256",
            "opened_author_oracle_commitment",
            "oracle_convergence_candidate_commitment",
            "human_adjudication_required",
            "human_admission_review_required",
            "scientific_correctness_established",
            "shared_expert_error_excluded",
            "expert_solve_gate_changed",
            "admission_gate_changed",
            "board_gate_changed",
            "integrity_sha256",
        },
    )
    if (
        data["schema_version"]
        != FRONTIER_ORACLE_CHALLENGE_COMPARISON_SCHEMA_VERSION
    ):
        raise FrontierContractError("unsupported oracle challenge comparison schema")
    packet_id = _text(data["packet_id"], "oracle challenge comparison packet_id")
    if packet_id not in packets:
        raise FrontierContractError("oracle challenge comparison references unknown packet")
    if (
        _sha256(
            data["packet_set_integrity_sha256"],
            "oracle challenge comparison packet-set commitment",
        )
        != packet_data["integrity_sha256"]
    ):
        raise FrontierContractError("oracle challenge comparison rebound packet set")
    response_count = _integer(
        data["response_count"], "oracle challenge comparison response_count"
    )
    if response_count > 2:
        raise FrontierContractError("oracle challenge comparison accepts two responses")
    response_commitments = _text_list(
        data["response_commitments"],
        "oracle challenge comparison response commitments",
        nonempty=False,
    )
    if len(response_commitments) != response_count or len(response_commitments) != len(
        set(response_commitments)
    ):
        raise FrontierContractError(
            "oracle challenge comparison response commitments are invalid"
        )
    for commitment in response_commitments:
        _sha256(commitment, "oracle challenge comparison response commitment")
    challenger_disagreements = _text_list(
        data["challenger_disagreement_components"],
        "oracle challenge comparison challenger disagreements",
        nonempty=False,
    )
    author_disagreements = _text_list(
        data["author_oracle_disagreement_components"],
        "oracle challenge comparison author disagreements",
        nonempty=False,
    )
    if len(challenger_disagreements) != len(set(challenger_disagreements)) or len(
        author_disagreements
    ) != len(set(author_disagreements)):
        raise FrontierContractError(
            "oracle challenge comparison disagreement components must be unique"
        )
    opened = _boolean(
        data["author_oracle_opened"],
        "oracle challenge comparison author_oracle_opened",
    )
    opened_key_set_commitment = data["opened_key_set_integrity_sha256"]
    opened_author_oracle_commitment = data["opened_author_oracle_commitment"]
    if opened:
        _sha256(
            opened_key_set_commitment,
            "oracle challenge comparison opened key-set commitment",
        )
        _sha256(
            opened_author_oracle_commitment,
            "oracle challenge comparison opened author-oracle commitment",
        )
    elif (
        opened_key_set_commitment is not None
        or opened_author_oracle_commitment is not None
    ):
        raise FrontierContractError(
            "oracle challenge comparison exposed sealed commitments before opening"
        )
    human_adjudication = _boolean(
        data["human_adjudication_required"],
        "oracle challenge comparison human_adjudication_required",
    )
    route = data["route"]
    if route == "awaiting_challengers":
        valid_route_state = (
            response_count < 2
            and not opened
            and opened_key_set_commitment is None
            and opened_author_oracle_commitment is None
            and not challenger_disagreements
            and not author_disagreements
            and data["component_match_count"] is None
            and data["component_total"] is None
            and data["oracle_convergence_candidate_commitment"] is None
            and not human_adjudication
        )
    elif route == FRONTIER_ORACLE_CHALLENGE_ROUTES[0]:
        valid_route_state = (
            response_count == 2
            and not opened
            and opened_key_set_commitment is None
            and opened_author_oracle_commitment is None
            and not challenger_disagreements
            and not author_disagreements
            and data["component_match_count"] is None
            and data["component_total"] is None
            and data["oracle_convergence_candidate_commitment"] is None
            and human_adjudication
        )
    elif route == FRONTIER_ORACLE_CHALLENGE_ROUTES[1]:
        valid_route_state = (
            response_count == 2
            and not opened
            and opened_key_set_commitment is None
            and opened_author_oracle_commitment is None
            and bool(challenger_disagreements)
            and not author_disagreements
            and data["component_match_count"] is None
            and data["component_total"] is None
            and data["oracle_convergence_candidate_commitment"] is None
            and human_adjudication
        )
    elif route == FRONTIER_ORACLE_CHALLENGE_ROUTES[2]:
        valid_route_state = (
            response_count == 2
            and opened
            and isinstance(opened_key_set_commitment, str)
            and isinstance(opened_author_oracle_commitment, str)
            and not challenger_disagreements
            and bool(author_disagreements)
            and isinstance(data["component_match_count"], int)
            and not isinstance(data["component_match_count"], bool)
            and 0 <= data["component_match_count"] < 30
            and data["component_total"] == 30
            and data["oracle_convergence_candidate_commitment"] is None
            and human_adjudication
        )
    elif route == FRONTIER_ORACLE_CHALLENGE_ROUTES[3]:
        valid_route_state = (
            response_count == 2
            and opened
            and isinstance(opened_key_set_commitment, str)
            and isinstance(opened_author_oracle_commitment, str)
            and not challenger_disagreements
            and not author_disagreements
            and data["component_match_count"] == 30
            and data["component_total"] == 30
            and isinstance(data["oracle_convergence_candidate_commitment"], str)
            and not human_adjudication
        )
        if valid_route_state:
            _sha256(
                data["oracle_convergence_candidate_commitment"],
                "oracle challenge convergence commitment",
            )
    else:
        raise FrontierContractError("oracle challenge comparison has unknown route")
    if not valid_route_state:
        raise FrontierContractError(
            "oracle challenge comparison fields disagree with its route"
        )
    if not _boolean(
        data["human_admission_review_required"],
        "oracle challenge comparison human admission review",
    ):
        raise FrontierContractError("oracle convergence cannot bypass human admission")
    for field_name in (
        "scientific_correctness_established",
        "shared_expert_error_excluded",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_gate_changed",
    ):
        if _boolean(data[field_name], f"oracle challenge comparison {field_name}"):
            raise FrontierContractError(
                f"oracle challenge comparison {field_name} must remain false"
            )
    if (
        data["integrity_sha256"]
        != frontier_oracle_challenge_comparison_integrity_sha256(data)
    ):
        raise FrontierContractError("oracle challenge comparison integrity mismatch")
    return data


def compile_frontier_oracle_challenge_artifacts(
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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compile blind packets, sealed mappings, an empty ledger, and public readiness."""

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
        raise FrontierContractError("oracle challenge inputs do not share a preflight")
    _date(compiled_on, "oracle challenge compiled_on")

    packets: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for task, oracle in zip(
        tasks_data["tasks"], oracles_data["oracles"], strict=True
    ):
        packet_digest = hashlib.sha256(
            (
                f"{task['task_commitment_nonce']}|"
                f"{oracle['oracle_commitment_nonce']}|independent-oracle-challenge"
            ).encode("utf-8")
        ).hexdigest()
        packet_id = f"oracle-challenge-{packet_digest[:20]}"
        challenge_task = frontier_oracle_challenge_view(task)
        packets.append(
            {
                "packet_id": packet_id,
                "challenge_task": challenge_task,
                "challenge_task_commitment": _canonical_sha256(challenge_task),
            }
        )
        keys.append(
            {
                "packet_id": packet_id,
                "slot_id": task["slot_id"],
                "task_id": task["task_id"],
                "canonical_task_commitment": frontier_calibration_task_sha256(task),
                "author_oracle_commitment": frontier_calibration_oracle_sha256(
                    oracle
                ),
            }
        )
    packets.sort(key=lambda item: item["packet_id"])
    keys.sort(key=lambda item: item["packet_id"])

    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_PACKET_SCHEMA_VERSION,
        "set_id": FRONTIER_ORACLE_CHALLENGE_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "author_oracle_labels_included": False,
        "semantic_review_material_included": False,
        "authoring_source_artifacts_included": False,
        "task_identity_mapping_included": False,
        "minimum_independent_challengers_per_packet": 2,
        "challenge_instructions": [
            "Solve all six stages independently from the supplied task evidence.",
            "Return factorized actions, exact witnesses, blockers, and abstention state for every stage.",
            "Do not access the author oracle, semantic-review artifacts, or authoring source files.",
            "Complete the response before any sealed task-oracle mapping is opened.",
        ],
        "packets": packets,
        "nonclaims": sorted(_PACKET_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = (
        frontier_oracle_challenge_packet_set_integrity_sha256(packet_set)
    )
    key_set: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_KEY_SCHEMA_VERSION,
        "set_id": FRONTIER_ORACLE_CHALLENGE_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "task_set_integrity_sha256": tasks_data["integrity_sha256"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "author_oracle_reveal_rule": FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE,
        "keys": keys,
        "integrity_sha256": "0" * 64,
    }
    key_set["integrity_sha256"] = (
        frontier_oracle_challenge_key_set_integrity_sha256(key_set)
    )
    key_index = {item["packet_id"]: item for item in keys}
    packet_index = {item["packet_id"]: item for item in packets}
    records = [
        {
            "packet_id": packet_id,
            "packet_commitment": _canonical_sha256(packet_index[packet_id]),
            "key_commitment": _canonical_sha256(key_index[packet_id]),
            "required_response_count": 2,
            "status": "unassigned",
            "challenger_assignment_commitments": [],
            "response_commitments": [],
            "comparison_commitment": None,
            "adjudication_commitment": None,
        }
        for packet_id in sorted(packet_index)
    ]
    ledger: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_LEDGER_SCHEMA_VERSION,
        "set_id": FRONTIER_ORACLE_CHALLENGE_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "key_set_integrity_sha256": key_set["integrity_sha256"],
        "private_preflight_integrity_sha256": private_preflight_data[
            "integrity_sha256"
        ],
        "required_response_count_per_packet": 2,
        "author_oracle_reveal_rule": FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE,
        "comparison_rule": FRONTIER_ORACLE_CHALLENGE_COMPARISON_RULE,
        "routing_precedence": list(FRONTIER_ORACLE_CHALLENGE_ROUTES),
        "records": records,
        "challenger_assignment_count": 0,
        "challenger_response_count": 0,
        "oracle_convergence_candidate_count": 0,
        "adjudication_count": 0,
        "independent_oracle_challenge_complete": False,
        "integrity_sha256": "0" * 64,
    }
    ledger["integrity_sha256"] = frontier_oracle_challenge_ledger_integrity_sha256(
        ledger
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_ORACLE_CHALLENGE_SUMMARY_SCHEMA_VERSION,
        "set_id": FRONTIER_ORACLE_CHALLENGE_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "challenge_contract_ready_no_assignments",
        "compiled_on": compiled_on,
        "public_preflight_integrity_sha256": public_preflight_data[
            "integrity_sha256"
        ],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "private_key_set_commitment": key_set["integrity_sha256"],
        "private_ledger_commitment": ledger["integrity_sha256"],
        "challenge_packet_count": 10,
        "unassigned_packet_count": 10,
        "response_contract_ready": True,
        "oracle_comparison_state_machine_ready": True,
        "minimum_independent_challengers_per_packet": 2,
        "author_oracle_reveal_rule": FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE,
        "comparison_rule": FRONTIER_ORACLE_CHALLENGE_COMPARISON_RULE,
        "routing_precedence": list(FRONTIER_ORACLE_CHALLENGE_ROUTES),
        "challenger_assignment_count": 0,
        "challenger_response_count": 0,
        "oracle_convergence_candidate_count": 0,
        "adjudication_count": 0,
        "independent_oracle_challenge_complete": False,
        "human_challenge_required": True,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = frontier_oracle_challenge_summary_integrity_sha256(
        summary
    )
    validate_frontier_oracle_challenge_packet_set(packet_set)
    _validate_key_opening(
        packet_set=packet_set,
        key_set=key_set,
        task_set=tasks_data,
        oracle_set=oracles_data,
        **validation_kwargs,
    )
    return packet_set, key_set, ledger, summary


def validate_frontier_oracle_challenge_summary(
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
        "set_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_preflight_integrity_sha256",
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "private_ledger_commitment",
        "challenge_packet_count",
        "unassigned_packet_count",
        "response_contract_ready",
        "oracle_comparison_state_machine_ready",
        "minimum_independent_challengers_per_packet",
        "author_oracle_reveal_rule",
        "comparison_rule",
        "routing_precedence",
        "challenger_assignment_count",
        "challenger_response_count",
        "oracle_convergence_candidate_count",
        "adjudication_count",
        "independent_oracle_challenge_complete",
        "human_challenge_required",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "oracle_challenge_summary", fields)
    if data["schema_version"] != FRONTIER_ORACLE_CHALLENGE_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported oracle challenge summary schema")
    if (
        data["set_id"] != FRONTIER_ORACLE_CHALLENGE_SET_ID
        or data["protocol_id"] != preflight_data["protocol_id"]
        or data["board_id"] != preflight_data["board_id"]
    ):
        raise FrontierContractError("oracle challenge summary rebound provenance")
    if data["status"] != "challenge_contract_ready_no_assignments":
        raise FrontierContractError("oracle challenge summary overstates maturity")
    _date(data["compiled_on"], "oracle challenge summary compiled_on")
    if (
        _sha256(
            data["public_preflight_integrity_sha256"],
            "oracle challenge summary public preflight commitment",
        )
        != preflight_data["integrity_sha256"]
    ):
        raise FrontierContractError("oracle challenge summary does not bind preflight")
    for field_name in (
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "private_ledger_commitment",
        "integrity_sha256",
    ):
        _sha256(data[field_name], f"oracle challenge summary {field_name}")
    counts = {
        "challenge_packet_count": 10,
        "unassigned_packet_count": 10,
        "minimum_independent_challengers_per_packet": 2,
        "challenger_assignment_count": 0,
        "challenger_response_count": 0,
        "oracle_convergence_candidate_count": 0,
        "adjudication_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in counts.items():
        if _integer(data[field_name], f"oracle challenge summary {field_name}") != expected:
            raise FrontierContractError(
                f"oracle challenge summary {field_name} must remain {expected}"
            )
    for field_name in (
        "response_contract_ready",
        "oracle_comparison_state_machine_ready",
        "human_challenge_required",
    ):
        if not _boolean(data[field_name], f"oracle challenge summary {field_name}"):
            raise FrontierContractError(
                f"oracle challenge summary {field_name} must remain true"
            )
    for field_name in (
        "independent_oracle_challenge_complete",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"oracle challenge summary {field_name}"):
            raise FrontierContractError(
                f"oracle challenge summary {field_name} must remain false"
            )
    if (
        data["author_oracle_reveal_rule"] != FRONTIER_ORACLE_CHALLENGE_REVEAL_RULE
        or data["comparison_rule"] != FRONTIER_ORACLE_CHALLENGE_COMPARISON_RULE
        or tuple(
            _text_list(
                data["routing_precedence"],
                "oracle challenge summary routing precedence",
            )
        )
        != FRONTIER_ORACLE_CHALLENGE_ROUTES
    ):
        raise FrontierContractError("oracle challenge summary changed frozen rules")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "oracle challenge summary nonclaims"))
    ):
        raise FrontierContractError("oracle challenge summary removed a nonclaim")
    if data["integrity_sha256"] != frontier_oracle_challenge_summary_integrity_sha256(
        data
    ):
        raise FrontierContractError("oracle challenge summary integrity mismatch")
    return data


def validate_frontier_oracle_challenge_private_opening(
    *,
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    ledger: Mapping[str, Any],
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
    data = validate_frontier_oracle_challenge_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if ledger.get("integrity_sha256") != frontier_oracle_challenge_ledger_integrity_sha256(
        ledger
    ):
        raise FrontierContractError("oracle challenge ledger integrity mismatch")
    expected = compile_frontier_oracle_challenge_artifacts(
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
    if (packet_set, key_set, ledger, public_summary) != expected:
        raise FrontierContractError(
            "oracle challenge artifacts do not replay from committed inputs"
        )
    return oracle_challenge_summary(
        public_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_oracle_challenge_commitments_opened": True}


def load_frontier_oracle_challenge_packet_set(path: Path) -> dict[str, Any]:
    return validate_frontier_oracle_challenge_packet_set(
        _load_json(path.read_text(encoding="utf-8"), "oracle challenge packet set")
    )


def load_frontier_oracle_challenge_key_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "oracle challenge key set")


def load_frontier_oracle_challenge_ledger(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "oracle challenge ledger")


def load_frontier_oracle_challenge_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_oracle_challenge_summary(
        _load_json(path.read_text(encoding="utf-8"), "oracle challenge summary"),
        **kwargs,
    )


def oracle_challenge_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_oracle_challenge_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "challenge_packet_count": data["challenge_packet_count"],
        "unassigned_packet_count": data["unassigned_packet_count"],
        "minimum_independent_challengers_per_packet": data[
            "minimum_independent_challengers_per_packet"
        ],
        "challenger_response_count": data["challenger_response_count"],
        "oracle_convergence_candidate_count": data[
            "oracle_convergence_candidate_count"
        ],
        "human_challenge_required": data["human_challenge_required"],
        "expert_solve_gate_changed": data["expert_solve_gate_changed"],
        "admission_gate_changed": data["admission_gate_changed"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
        "integrity_sha256": data["integrity_sha256"],
    }
