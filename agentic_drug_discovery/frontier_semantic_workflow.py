"""Response and disagreement workflow for private ADDS-Frontier review packets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
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
    _text,
    _text_list,
)
from .frontier_calibration import validate_frontier_calibration_progress
from .frontier_semantic_review import (
    frontier_semantic_key_set_integrity_sha256,
    frontier_semantic_packet_set_integrity_sha256,
    validate_frontier_semantic_review_summary,
)


FRONTIER_SEMANTIC_RESPONSE_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-response.v1"
)
FRONTIER_SEMANTIC_LEDGER_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-workflow-ledger.v1"
)
FRONTIER_SEMANTIC_WORKFLOW_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-semantic-review-workflow-summary.v1"
)
FRONTIER_SEMANTIC_WORKFLOW_ID = "adds-frontier-semantic-review-workflow-v1"
FRONTIER_SEMANTIC_PAIR_CONSISTENCY_RULE = (
    "pair_assessment_equals_observed_stage_deltas"
)
FRONTIER_SEMANTIC_PRE_ACCESS_INVARIANCE_RULE = (
    "bounded_evidence_arms_invariant_before_access_delta"
)

FRONTIER_SEMANTIC_TRIAGE_ROUTES = (
    "adjudication_required_abstention",
    "adjudication_required_action_disagreement",
    "adjudication_required_support_disagreement",
    "adjudication_required_change_disagreement",
    "consensus_candidate",
)
_CHANGED_COMPONENTS = {
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
}
_CHANGED_COMPONENT_ORDER = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_EVIDENCE_REVEAL_REASON_CODES = {
    "evidence_sufficiency_change",
    "temporal_eligibility_change",
    "lineage_independence_change",
    "uncertainty_change",
}
_REASON_CODES = {
    "evidence_sufficiency_change",
    "identity_discontinuity",
    "temporal_eligibility_change",
    "lineage_independence_change",
    "endpoint_population_change",
    "uncertainty_change",
    "insufficient_information",
    "other_bounded_reason",
}
_PUBLIC_NONCLAIMS = {
    "Workflow readiness is not a reviewer response or scientific judgment.",
    "Synthetic state-machine tests are not live review evidence.",
    "Consensus candidates cannot pass board gates without the frozen human and replay process.",
    "Pairwise causal consistency is necessary but does not establish scientific correctness.",
    "No private packet, key, response, reviewer, affiliation, or adjudication bytes are public.",
    "No reviewer assignment, response, consensus, board admission, model run, or benchmark result is claimed.",
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


def frontier_semantic_response_integrity_sha256(
    response: Mapping[str, Any],
) -> str:
    return _canonical_sha256(response, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_triage_integrity_sha256(
    triage: Mapping[str, Any],
) -> str:
    return _canonical_sha256(triage, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_ledger_integrity_sha256(
    ledger: Mapping[str, Any],
) -> str:
    return _canonical_sha256(ledger, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_workflow_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _packet_index(packet_set: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    packets = packet_set.get("packets")
    if not isinstance(packets, list):
        raise FrontierContractError("semantic packet set must contain packets")
    index: dict[str, dict[str, Any]] = {}
    for item in packets:
        if not isinstance(item, Mapping):
            raise FrontierContractError("semantic packet must be an object")
        packet = dict(item)
        packet_id = _text(packet.get("packet_id"), "semantic packet packet_id")
        if packet_id in index:
            raise FrontierContractError("semantic packet ids must be unique")
        index[packet_id] = packet
    return index


def frontier_semantic_observed_pair_deltas(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive factorized arm differences directly from stage-level answers."""

    arm_answers = response.get("arm_answers")
    if not isinstance(arm_answers, Mapping):
        raise FrontierContractError("semantic response must contain arm answers")
    answers_a = _sequence(
        arm_answers.get("arm_a"), "semantic_response.arm_answers.arm_a"
    )
    answers_b = _sequence(
        arm_answers.get("arm_b"), "semantic_response.arm_answers.arm_b"
    )
    if len(answers_a) != len(answers_b):
        raise FrontierContractError("semantic response arms must have equal stages")
    observed: set[str] = set()
    stage_deltas: list[dict[str, Any]] = []
    for index, (answer_a, answer_b) in enumerate(
        zip(answers_a, answers_b, strict=True)
    ):
        if not isinstance(answer_a, Mapping) or not isinstance(answer_b, Mapping):
            raise FrontierContractError("semantic response stage answers must be objects")
        stage_id = answer_a.get("stage_id")
        if stage_id != answer_b.get("stage_id"):
            raise FrontierContractError("semantic response arms rebound stage identity")
        changed: set[str] = set()
        if answer_a.get("disposition") != answer_b.get("disposition"):
            changed.add("disposition")
        if answer_a.get("next_action") != answer_b.get("next_action"):
            changed.add("next_action")
        if set(answer_a.get("risk_flags", ())) != set(
            answer_b.get("risk_flags", ())
        ):
            changed.add("risk_flags")
        if set(answer_a.get("witness_evidence_ids", ())) != set(
            answer_b.get("witness_evidence_ids", ())
        ):
            changed.add("witness")
        if set(answer_a.get("blocker_codes", ())) != set(
            answer_b.get("blocker_codes", ())
        ):
            changed.add("blockers")
        observed.update(changed)
        stage_deltas.append(
            {
                "stage_id": _text(
                    stage_id, f"semantic_response.stage_deltas[{index}].stage_id"
                ),
                "changed_components": [
                    component
                    for component in _CHANGED_COMPONENT_ORDER
                    if component in changed
                ],
            }
        )
    return {
        "changed_components": [
            component
            for component in _CHANGED_COMPONENT_ORDER
            if component in observed
        ],
        "stage_deltas": stage_deltas,
    }


def validate_frontier_semantic_reviewer_response(
    response: Mapping[str, Any],
    *,
    packet_set: Mapping[str, Any],
) -> dict[str, Any]:
    data = _record(
        response,
        "semantic_response",
        {
            "schema_version",
            "packet_id",
            "packet_set_integrity_sha256",
            "arm_a_commitment",
            "arm_b_commitment",
            "reviewer_identity_commitment",
            "reviewer_affiliation_commitment",
            "conflict_of_interest_declared",
            "independence_attested",
            "completed_on",
            "arm_answers",
            "pair_assessment",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_SEMANTIC_RESPONSE_SCHEMA_VERSION:
        raise FrontierContractError("unsupported semantic response schema")
    packet_integrity = packet_set.get("integrity_sha256")
    if packet_integrity != frontier_semantic_packet_set_integrity_sha256(packet_set):
        raise FrontierContractError("semantic response packet set integrity mismatch")
    if (
        _sha256(
            data["packet_set_integrity_sha256"],
            "semantic_response.packet_set_integrity_sha256",
        )
        != packet_integrity
    ):
        raise FrontierContractError("semantic response rebound its packet set")
    packet_id = _text(data["packet_id"], "semantic_response.packet_id")
    packets = _packet_index(packet_set)
    if packet_id not in packets:
        raise FrontierContractError("semantic response references unknown packet")
    packet = packets[packet_id]
    for arm_id in ("arm_a", "arm_b"):
        if (
            _sha256(
                data[f"{arm_id}_commitment"],
                f"semantic_response.{arm_id}_commitment",
            )
            != packet[f"{arm_id}_commitment"]
        ):
            raise FrontierContractError("semantic response rebound an arm")
    _sha256(
        data["reviewer_identity_commitment"],
        "semantic_response.reviewer_identity_commitment",
    )
    _sha256(
        data["reviewer_affiliation_commitment"],
        "semantic_response.reviewer_affiliation_commitment",
    )
    if _boolean(
        data["conflict_of_interest_declared"],
        "semantic_response.conflict_of_interest_declared",
    ):
        raise FrontierContractError("conflicted response cannot enter automatic triage")
    if not _boolean(
        data["independence_attested"],
        "semantic_response.independence_attested",
    ):
        raise FrontierContractError(
            "semantic response requires independence attestation"
        )
    _date(data["completed_on"], "semantic_response.completed_on")

    arm_answers = _record(
        data["arm_answers"],
        "semantic_response.arm_answers",
        {"arm_a", "arm_b"},
    )
    any_stage_abstention = False
    for arm_id in ("arm_a", "arm_b"):
        answers = _sequence(
            arm_answers[arm_id], f"semantic_response.arm_answers.{arm_id}"
        )
        stages = packet[arm_id]["stages"]
        if len(answers) != len(stages):
            raise FrontierContractError("semantic response must answer every stage")
        for stage_index, (answer_item, stage) in enumerate(
            zip(answers, stages, strict=True)
        ):
            path = f"semantic_response.arm_answers.{arm_id}[{stage_index}]"
            answer = _record(
                answer_item,
                path,
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
                raise FrontierContractError("semantic response rebound a stage")
            FrontierAction(
                disposition=answer["disposition"],
                next_action=answer["next_action"],
                risk_flags=tuple(
                    _text_list(
                        answer["risk_flags"], f"{path}.risk_flags", nonempty=False
                    )
                ),
            )
            witnesses = _text_list(
                answer["witness_evidence_ids"],
                f"{path}.witness_evidence_ids",
                nonempty=False,
            )
            if len(witnesses) != len(set(witnesses)):
                raise FrontierContractError(
                    "semantic response witnesses must be unique"
                )
            if not set(witnesses).issubset(stage["accessible_evidence_ids"]):
                raise FrontierContractError(
                    "semantic response cites inaccessible evidence"
                )
            blockers = _text_list(
                answer["blocker_codes"], f"{path}.blocker_codes", nonempty=False
            )
            if len(blockers) != len(set(blockers)):
                raise FrontierContractError(
                    "semantic response blockers must be unique"
                )
            any_stage_abstention |= _boolean(answer["abstained"], f"{path}.abstained")

    assessment = _record(
        data["pair_assessment"],
        "semantic_response.pair_assessment",
        {
            "semantic_change_detected",
            "changed_components",
            "reason_codes",
            "abstained",
        },
    )
    semantic_change = _boolean(
        assessment["semantic_change_detected"],
        "semantic_response.pair_assessment.semantic_change_detected",
    )
    changed = _text_list(
        assessment["changed_components"],
        "semantic_response.pair_assessment.changed_components",
        nonempty=False,
    )
    if not set(changed).issubset(_CHANGED_COMPONENTS):
        raise FrontierContractError("semantic response has unknown changed component")
    if len(changed) != len(set(changed)):
        raise FrontierContractError(
            "semantic response changed components must be unique"
        )
    reasons = _text_list(
        assessment["reason_codes"],
        "semantic_response.pair_assessment.reason_codes",
    )
    if not set(reasons).issubset(_REASON_CODES):
        raise FrontierContractError("semantic response has unknown reason code")
    if len(reasons) != len(set(reasons)):
        raise FrontierContractError("semantic response reason codes must be unique")
    pair_abstention = _boolean(
        assessment["abstained"], "semantic_response.pair_assessment.abstained"
    )
    observed_deltas = frontier_semantic_observed_pair_deltas(data)
    observed_changed = set(observed_deltas["changed_components"])
    probe_kind = packet.get("probe_kind")
    if probe_kind == "bounded_evidence_reveal":
        access_delta_index = next(
            (
                index
                for index, (stage_a, stage_b) in enumerate(
                    zip(
                        packet["arm_a"]["stages"],
                        packet["arm_b"]["stages"],
                        strict=True,
                    )
                )
                if set(stage_a["accessible_evidence_ids"])
                != set(stage_b["accessible_evidence_ids"])
            ),
            None,
        )
        if access_delta_index is None:
            raise FrontierContractError(
                "bounded evidence packet has no evidence-access delta"
            )
        if any(
            stage_delta["changed_components"]
            for stage_delta in observed_deltas["stage_deltas"][:access_delta_index]
        ):
            raise FrontierContractError(
                "bounded evidence response changed before evidence access"
            )
    if any_stage_abstention and not pair_abstention:
        raise FrontierContractError(
            "stage abstention must propagate to pair assessment"
        )
    if pair_abstention and "insufficient_information" not in reasons:
        raise FrontierContractError("abstention requires insufficient_information")
    if not pair_abstention:
        if set(changed) != observed_changed:
            raise FrontierContractError(
                "pair assessment does not match observed arm deltas"
            )
        if semantic_change != bool(observed_changed):
            raise FrontierContractError(
                "semantic_change_detected must agree with observed arm deltas"
            )
        if probe_kind == "bounded_evidence_reveal" and not (
            set(reasons) & _EVIDENCE_REVEAL_REASON_CODES
        ):
            raise FrontierContractError(
                "bounded evidence change requires an evidence-eligibility reason"
            )
        if (
            probe_kind == "identity_rebind"
            and "identity_discontinuity" not in reasons
        ):
            raise FrontierContractError(
                "identity rebind change requires identity_discontinuity"
            )
    if data["integrity_sha256"] != frontier_semantic_response_integrity_sha256(data):
        raise FrontierContractError("semantic response integrity mismatch")
    return data


def _normalized_signatures(response: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    action_signature = []
    support_signature = []
    for arm_id in ("arm_a", "arm_b"):
        for answer in response["arm_answers"][arm_id]:
            action_signature.append(
                (
                    arm_id,
                    answer["stage_id"],
                    answer["disposition"],
                    answer["next_action"],
                    tuple(sorted(answer["risk_flags"])),
                )
            )
            support_signature.append(
                (
                    arm_id,
                    answer["stage_id"],
                    tuple(sorted(answer["witness_evidence_ids"])),
                    tuple(sorted(answer["blocker_codes"])),
                )
            )
    assessment = response["pair_assessment"]
    change_signature = (
        assessment["semantic_change_detected"],
        tuple(sorted(assessment["changed_components"])),
        tuple(sorted(assessment["reason_codes"])),
    )
    return tuple(action_signature), tuple(support_signature), change_signature


def triage_frontier_semantic_responses(
    responses: Sequence[Mapping[str, Any]],
    *,
    packet_set: Mapping[str, Any],
    packet_id: str,
) -> dict[str, Any]:
    validated = [
        validate_frontier_semantic_reviewer_response(response, packet_set=packet_set)
        for response in responses
    ]
    if any(response["packet_id"] != packet_id for response in validated):
        raise FrontierContractError("semantic triage cannot mix packets")
    reviewer_ids = [response["reviewer_identity_commitment"] for response in validated]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise FrontierContractError("semantic triage requires unique reviewers")
    if len(validated) > 3:
        raise FrontierContractError(
            "semantic triage accepts exactly three curator responses"
        )

    if len(validated) < 3:
        route = "awaiting_responses"
        consensus_commitment = None
    elif any(
        response["pair_assessment"]["abstained"]
        or any(
            answer["abstained"]
            for arm_id in ("arm_a", "arm_b")
            for answer in response["arm_answers"][arm_id]
        )
        for response in validated
    ):
        route = FRONTIER_SEMANTIC_TRIAGE_ROUTES[0]
        consensus_commitment = None
    else:
        signatures = [_normalized_signatures(response) for response in validated]
        if len({signature[0] for signature in signatures}) != 1:
            route = FRONTIER_SEMANTIC_TRIAGE_ROUTES[1]
            consensus_commitment = None
        elif len({signature[1] for signature in signatures}) != 1:
            route = FRONTIER_SEMANTIC_TRIAGE_ROUTES[2]
            consensus_commitment = None
        elif len({signature[2] for signature in signatures}) != 1:
            route = FRONTIER_SEMANTIC_TRIAGE_ROUTES[3]
            consensus_commitment = None
        else:
            route = FRONTIER_SEMANTIC_TRIAGE_ROUTES[4]
            consensus_commitment = _canonical_sha256(
                {
                    "packet_id": packet_id,
                    "action_signature": signatures[0][0],
                    "support_signature": signatures[0][1],
                    "change_signature": signatures[0][2],
                }
            )
    triage: dict[str, Any] = {
        "packet_id": packet_id,
        "response_count": len(validated),
        "response_commitments": sorted(
            response["integrity_sha256"] for response in validated
        ),
        "route": route,
        "consensus_candidate_commitment": consensus_commitment,
        "human_adjudication_required": route
        not in {
            "awaiting_responses",
            "consensus_candidate",
        },
        "board_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    triage["integrity_sha256"] = frontier_semantic_triage_integrity_sha256(triage)
    return triage


def build_frontier_semantic_workflow_artifacts(
    *,
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    progress_data = validate_frontier_calibration_progress(
        progress, **validation_kwargs
    )
    semantic_data = validate_frontier_semantic_review_summary(
        semantic_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    packet_integrity = packet_set.get("integrity_sha256")
    key_integrity = key_set.get("integrity_sha256")
    if packet_integrity != frontier_semantic_packet_set_integrity_sha256(packet_set):
        raise FrontierContractError("semantic workflow packet-set integrity mismatch")
    if key_integrity != frontier_semantic_key_set_integrity_sha256(key_set):
        raise FrontierContractError("semantic workflow key-set integrity mismatch")
    if (
        semantic_data["private_packet_set_commitment"] != packet_integrity
        or semantic_data["private_key_set_commitment"] != key_integrity
    ):
        raise FrontierContractError(
            "semantic workflow private sets do not open readiness"
        )
    _date(compiled_on, "semantic workflow compiled_on")
    packets = _packet_index(packet_set)
    keys = {item["packet_id"]: item for item in key_set["keys"]}
    if set(packets) != set(keys) or len(packets) != 20:
        raise FrontierContractError("semantic workflow requires twenty paired keys")
    records = []
    for packet_id in sorted(packets):
        records.append(
            {
                "packet_id": packet_id,
                "packet_commitment": _canonical_sha256(packets[packet_id]),
                "key_commitment": _canonical_sha256(keys[packet_id]),
                "required_response_count": 3,
                "status": "unassigned",
                "reviewer_assignment_commitments": [],
                "response_commitments": [],
                "triage_commitment": None,
                "adjudication_commitment": None,
            }
        )
    ledger: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_LEDGER_SCHEMA_VERSION,
        "workflow_id": FRONTIER_SEMANTIC_WORKFLOW_ID,
        "protocol_id": semantic_data["protocol_id"],
        "board_id": semantic_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_integrity,
        "key_set_integrity_sha256": key_integrity,
        "semantic_readiness_integrity_sha256": semantic_data["integrity_sha256"],
        "required_response_count_per_packet": 3,
        "consensus_rule": "three_independent_exact_responses",
        "pair_consistency_rule": FRONTIER_SEMANTIC_PAIR_CONSISTENCY_RULE,
        "pre_access_invariance_rule": FRONTIER_SEMANTIC_PRE_ACCESS_INVARIANCE_RULE,
        "routing_precedence": list(FRONTIER_SEMANTIC_TRIAGE_ROUTES),
        "records": records,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_candidate_count": 0,
        "adjudication_count": 0,
        "independent_review_complete": False,
        "integrity_sha256": "0" * 64,
    }
    ledger["integrity_sha256"] = frontier_semantic_ledger_integrity_sha256(ledger)
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        "workflow_id": FRONTIER_SEMANTIC_WORKFLOW_ID,
        "protocol_id": semantic_data["protocol_id"],
        "board_id": semantic_data["board_id"],
        "status": "workflow_contract_ready_no_reviews",
        "compiled_on": compiled_on,
        "semantic_readiness_integrity_sha256": semantic_data["integrity_sha256"],
        "private_ledger_commitment": ledger["integrity_sha256"],
        "packet_count": 20,
        "unassigned_packet_count": 20,
        "response_contract_ready": True,
        "triage_state_machine_ready": True,
        "pairwise_causal_consistency_ready": True,
        "pre_access_invariance_ready": True,
        "required_response_count_per_packet": 3,
        "consensus_rule": "three_independent_exact_responses",
        "pair_consistency_rule": FRONTIER_SEMANTIC_PAIR_CONSISTENCY_RULE,
        "pre_access_invariance_rule": FRONTIER_SEMANTIC_PRE_ACCESS_INVARIANCE_RULE,
        "routing_precedence": list(FRONTIER_SEMANTIC_TRIAGE_ROUTES),
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_candidate_count": 0,
        "adjudication_count": 0,
        "independent_review_complete": False,
        "human_review_required": True,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = frontier_semantic_workflow_summary_integrity_sha256(
        summary
    )
    return ledger, summary


def validate_frontier_semantic_workflow_summary(
    summary: Mapping[str, Any],
    *,
    semantic_summary: Mapping[str, Any],
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
    semantic_data = validate_frontier_semantic_review_summary(
        semantic_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    data = _record(
        summary,
        "semantic_workflow_summary",
        {
            "schema_version",
            "workflow_id",
            "protocol_id",
            "board_id",
            "status",
            "compiled_on",
            "semantic_readiness_integrity_sha256",
            "private_ledger_commitment",
            "packet_count",
            "unassigned_packet_count",
            "response_contract_ready",
            "triage_state_machine_ready",
            "pairwise_causal_consistency_ready",
            "pre_access_invariance_ready",
            "required_response_count_per_packet",
            "consensus_rule",
            "pair_consistency_rule",
            "pre_access_invariance_rule",
            "routing_precedence",
            "reviewer_assignment_count",
            "reviewer_response_count",
            "consensus_candidate_count",
            "adjudication_count",
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
    if data["schema_version"] != FRONTIER_SEMANTIC_WORKFLOW_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported semantic workflow summary schema")
    if data["workflow_id"] != FRONTIER_SEMANTIC_WORKFLOW_ID:
        raise FrontierContractError("unexpected semantic workflow id")
    if (
        data["protocol_id"] != semantic_data["protocol_id"]
        or data["board_id"] != semantic_data["board_id"]
    ):
        raise FrontierContractError("semantic workflow rebound protocol or board")
    if data["status"] != "workflow_contract_ready_no_reviews":
        raise FrontierContractError("semantic workflow overstates maturity")
    _date(data["compiled_on"], "semantic_workflow_summary.compiled_on")
    if (
        _sha256(
            data["semantic_readiness_integrity_sha256"],
            "semantic_workflow_summary.semantic_readiness_integrity_sha256",
        )
        != semantic_data["integrity_sha256"]
    ):
        raise FrontierContractError("semantic workflow does not bind readiness")
    _sha256(
        data["private_ledger_commitment"],
        "semantic_workflow_summary.private_ledger_commitment",
    )
    _sha256(data["integrity_sha256"], "semantic_workflow_summary.integrity_sha256")
    exact_counts = {
        "packet_count": 20,
        "unassigned_packet_count": 20,
        "required_response_count_per_packet": 3,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "consensus_candidate_count": 0,
        "adjudication_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if (
            _integer(data[field_name], f"semantic_workflow_summary.{field_name}")
            != expected
        ):
            raise FrontierContractError(
                f"semantic workflow {field_name} must remain {expected}"
            )
    for field_name in (
        "response_contract_ready",
        "triage_state_machine_ready",
        "pairwise_causal_consistency_ready",
        "pre_access_invariance_ready",
        "human_review_required",
    ):
        if not _boolean(data[field_name], f"semantic_workflow_summary.{field_name}"):
            raise FrontierContractError(
                f"semantic_workflow_summary.{field_name} must remain true"
            )
    for field_name in (
        "independent_review_complete",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"semantic_workflow_summary.{field_name}"):
            raise FrontierContractError(
                f"semantic_workflow_summary.{field_name} must remain false"
            )
    if data["consensus_rule"] != "three_independent_exact_responses":
        raise FrontierContractError("semantic workflow changed consensus rule")
    if (
        data["pair_consistency_rule"] != FRONTIER_SEMANTIC_PAIR_CONSISTENCY_RULE
        or data["pre_access_invariance_rule"]
        != FRONTIER_SEMANTIC_PRE_ACCESS_INVARIANCE_RULE
    ):
        raise FrontierContractError("semantic workflow changed a causal rule")
    if (
        tuple(
            _text_list(
                data["routing_precedence"],
                "semantic_workflow_summary.routing_precedence",
            )
        )
        != FRONTIER_SEMANTIC_TRIAGE_ROUTES
    ):
        raise FrontierContractError("semantic workflow changed routing precedence")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "semantic_workflow_summary.nonclaims"))
    ):
        raise FrontierContractError("semantic workflow removed a nonclaim")
    if data["integrity_sha256"] != frontier_semantic_workflow_summary_integrity_sha256(
        data
    ):
        raise FrontierContractError("semantic workflow summary integrity mismatch")
    return data


def validate_frontier_semantic_workflow_private_opening(
    *,
    ledger: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_frontier_semantic_workflow_summary(
        public_summary,
        semantic_summary=semantic_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if ledger.get("integrity_sha256") != frontier_semantic_ledger_integrity_sha256(
        ledger
    ):
        raise FrontierContractError("semantic workflow ledger integrity mismatch")
    expected_ledger, expected_summary = build_frontier_semantic_workflow_artifacts(
        packet_set=packet_set,
        key_set=key_set,
        semantic_summary=semantic_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
        compiled_on=data["compiled_on"],
    )
    if ledger != expected_ledger or public_summary != expected_summary:
        raise FrontierContractError(
            "semantic workflow does not replay from committed inputs"
        )
    return semantic_workflow_summary(
        public_summary,
        semantic_summary=semantic_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_semantic_workflow_commitment_opened": True}


def load_frontier_semantic_workflow_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_semantic_workflow_summary(
        _load_json(path.read_text(encoding="utf-8"), "semantic workflow summary"),
        **kwargs,
    )


def load_frontier_semantic_workflow_ledger(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "semantic workflow ledger")


def semantic_workflow_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_semantic_workflow_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "packet_count": data["packet_count"],
        "unassigned_packet_count": data["unassigned_packet_count"],
        "response_contract_ready": data["response_contract_ready"],
        "triage_state_machine_ready": data["triage_state_machine_ready"],
        "pairwise_causal_consistency_ready": data[
            "pairwise_causal_consistency_ready"
        ],
        "pre_access_invariance_ready": data["pre_access_invariance_ready"],
        "reviewer_assignment_count": data["reviewer_assignment_count"],
        "reviewer_response_count": data["reviewer_response_count"],
        "consensus_candidate_count": data["consensus_candidate_count"],
        "adjudication_count": data["adjudication_count"],
        "human_review_required": data["human_review_required"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
