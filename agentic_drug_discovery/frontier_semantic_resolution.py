"""Sealed unblinding and canonical replay for ADDS-Frontier review consensus."""

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
from .frontier_calibration import (
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_semantic_review import (
    frontier_semantic_key_set_integrity_sha256,
    frontier_semantic_packet_set_integrity_sha256,
    frontier_semantic_review_view,
    validate_frontier_semantic_review_summary,
)
from .frontier_semantic_workflow import (
    FRONTIER_SEMANTIC_WORKFLOW_ID,
    frontier_semantic_triage_integrity_sha256,
    triage_frontier_semantic_responses,
    validate_frontier_semantic_workflow_private_opening,
    validate_frontier_semantic_workflow_summary,
)
from .frontier_tasks import score_frontier_stage_components


FRONTIER_SEMANTIC_REPLAY_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-canonical-replay.v1"
)
FRONTIER_SEMANTIC_RECEIPT_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-resolution-receipt.v1"
)
FRONTIER_SEMANTIC_RESOLUTION_LEDGER_SCHEMA_VERSION = (
    "adds.frontier-private-semantic-review-resolution-ledger.v1"
)
FRONTIER_SEMANTIC_RESOLUTION_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-semantic-review-resolution-summary.v1"
)
FRONTIER_SEMANTIC_RESOLUTION_ID = "adds-frontier-semantic-resolution-v1"

FRONTIER_SEMANTIC_REPLAY_ROUTES = (
    "canonical_replay_pass_resolution_receipt_pending",
    "adjudication_required_canonical_replay_failure",
)
FRONTIER_SEMANTIC_RESOLUTION_DECISIONS = (
    "accept_consensus",
    "override_consensus",
    "reauthor_packet",
    "reject_packet",
)
FRONTIER_SEMANTIC_UNBLINDING_RULE = (
    "three_response_consensus_candidate_before_sealed_key_opening"
)
FRONTIER_SEMANTIC_REPLAY_RULE = "all_30_canonical_stage_components_exact"
FRONTIER_SEMANTIC_RECEIPT_RULE = (
    "human_resolution_receipt_before_admission_review"
)
FRONTIER_SEMANTIC_GATE_TRANSITION_RULE = (
    "resolution_evidence_never_changes_board_gates_automatically"
)

_COMPONENT_KEYS = (
    "disposition_correct",
    "next_action_correct",
    "risk_flags_correct",
    "witness_valid",
    "blocker_certificate_valid",
)
_RECEIPT_RATIONALE_CODES = {
    "canonical_replay_exact",
    "canonical_replay_failure",
    "reviewer_consensus_supported",
    "adjudicator_override",
    "packet_ambiguity",
    "oracle_revision_required",
    "conflict_or_contamination_concern",
    "other_bounded_reason",
}
_PUBLIC_NONCLAIMS = {
    "Resolution readiness is not unblinding, replay evidence, or a scientific judgment.",
    "Synthetic replay and receipt tests are not live review or adjudication evidence.",
    "A canonical replay pass cannot change a board gate without a human resolution receipt and frozen admission review.",
    "No canonical-arm identity, oracle label, reviewer response, replay detail, or receipt bytes are public.",
    "No unblinding, replay, resolution receipt, board admission, model run, or benchmark result is claimed.",
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


def frontier_semantic_replay_integrity_sha256(replay: Mapping[str, Any]) -> str:
    return _canonical_sha256(replay, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_resolution_receipt_integrity_sha256(
    receipt: Mapping[str, Any],
) -> str:
    return _canonical_sha256(receipt, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_resolution_ledger_integrity_sha256(
    ledger: Mapping[str, Any],
) -> str:
    return _canonical_sha256(ledger, exclude=frozenset({"integrity_sha256"}))


def frontier_semantic_resolution_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _index_records(
    records: Any, *, id_field: str, path: str
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in _sequence(records, path):
        if not isinstance(item, Mapping):
            raise FrontierContractError(f"{path} entries must be objects")
        record = dict(item)
        record_id = _text(record.get(id_field), f"{path}.{id_field}")
        if record_id in index:
            raise FrontierContractError(f"{path} contains duplicate {id_field}")
        index[record_id] = record
    return index


def replay_frontier_semantic_consensus(
    *,
    triage: Mapping[str, Any],
    responses: Sequence[Mapping[str, Any]],
    packet_set: Mapping[str, Any],
    key_set: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    """Open one consensus candidate and replay only its canonical arm.

    This produces private resolution evidence. It never admits a packet or changes
    a board gate, including when every oracle-comparable component passes.
    """

    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    tasks_data = validate_frontier_calibration_task_set(
        task_set, **validation_kwargs
    )
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set,
        task_set=tasks_data,
        **validation_kwargs,
    )
    packet_integrity = packet_set.get("integrity_sha256")
    if packet_integrity != frontier_semantic_packet_set_integrity_sha256(packet_set):
        raise FrontierContractError("semantic replay packet-set integrity mismatch")
    key_integrity = key_set.get("integrity_sha256")
    if key_integrity != frontier_semantic_key_set_integrity_sha256(key_set):
        raise FrontierContractError("semantic replay key-set integrity mismatch")
    if key_set.get("packet_set_integrity_sha256") != packet_integrity:
        raise FrontierContractError("semantic replay key set rebound its packets")
    for field_name in ("protocol_id", "board_id"):
        if (
            packet_set.get(field_name) != tasks_data[field_name]
            or key_set.get(field_name) != tasks_data[field_name]
        ):
            raise FrontierContractError(
                f"semantic replay private sets rebound {field_name}"
            )

    packet_id = _text(triage.get("packet_id"), "semantic replay triage packet_id")
    recomputed_triage = triage_frontier_semantic_responses(
        responses,
        packet_set=packet_set,
        packet_id=packet_id,
    )
    if triage != recomputed_triage:
        raise FrontierContractError("semantic replay triage does not replay")
    if triage.get("integrity_sha256") != frontier_semantic_triage_integrity_sha256(
        triage
    ):
        raise FrontierContractError("semantic replay triage integrity mismatch")
    if triage["route"] != "consensus_candidate" or triage["response_count"] != 3:
        raise FrontierContractError(
            "sealed unblinding requires a three-response consensus candidate"
        )

    packets = _index_records(
        packet_set.get("packets"), id_field="packet_id", path="semantic packets"
    )
    keys = _index_records(
        key_set.get("keys"), id_field="packet_id", path="semantic keys"
    )
    if set(packets) != set(keys) or len(packets) != 20:
        raise FrontierContractError("semantic replay requires twenty paired keys")
    if packet_id not in packets or packet_id not in keys:
        raise FrontierContractError("semantic replay references an unpaired packet")
    packet = packets[packet_id]
    key = keys[packet_id]
    canonical_arm = key.get("canonical_arm")
    mutated_arm = key.get("mutated_arm")
    if {canonical_arm, mutated_arm} != {"arm_a", "arm_b"}:
        raise FrontierContractError("semantic replay key has invalid arm mapping")
    if packet[f"{canonical_arm}_commitment"] != _canonical_sha256(
        packet[canonical_arm]
    ):
        raise FrontierContractError("canonical arm commitment does not open")

    tasks = _index_records(
        tasks_data["tasks"], id_field="slot_id", path="calibration tasks"
    )
    oracles = _index_records(
        oracles_data["oracles"], id_field="slot_id", path="calibration oracles"
    )
    slot_id = _text(key.get("slot_id"), "semantic replay key slot_id")
    if slot_id not in tasks or slot_id not in oracles:
        raise FrontierContractError("semantic replay key references unknown slot")
    task = tasks[slot_id]
    oracle = oracles[slot_id]
    if key.get("canonical_task_commitment") != frontier_calibration_task_sha256(task):
        raise FrontierContractError("semantic replay key rebound canonical task")
    if packet[canonical_arm] != frontier_semantic_review_view(task):
        raise FrontierContractError(
            "semantic replay canonical arm does not open canonical task"
        )

    consensus_response = responses[0]
    canonical_answers = consensus_response["arm_answers"][canonical_arm]
    expectations = oracle["stage_expectations"]
    if len(canonical_answers) != len(expectations) or len(expectations) != 6:
        raise FrontierContractError("canonical replay requires six stages")
    stage_results: list[dict[str, Any]] = []
    passed_component_count = 0
    for answer, expectation in zip(canonical_answers, expectations, strict=True):
        if answer["stage_id"] != expectation["stage_id"]:
            raise FrontierContractError("canonical replay stage identity mismatch")
        components = score_frontier_stage_components(
            expectation,
            action=FrontierAction(
                disposition=answer["disposition"],
                next_action=answer["next_action"],
                risk_flags=tuple(answer["risk_flags"]),
            ),
            witness_evidence_ids=tuple(answer["witness_evidence_ids"]),
            blocker_codes=tuple(answer["blocker_codes"]),
        )
        if tuple(components) != _COMPONENT_KEYS:
            raise FrontierContractError("canonical replay scorer contract changed")
        component_pass_count = sum(components.values())
        passed_component_count += component_pass_count
        stage_results.append(
            {
                "stage_id": answer["stage_id"],
                "component_results": components,
                "passed_component_count": component_pass_count,
                "stage_replay_passed": component_pass_count == 5,
            }
        )
    replay_passed = passed_component_count == 30
    unblinding_identity_commitment = _canonical_sha256(
        {
            "packet_id": packet_id,
            "triage_commitment": triage["integrity_sha256"],
            "key_set_integrity_sha256": key_integrity,
            "canonical_arm": canonical_arm,
            "mutated_arm": mutated_arm,
            "canonical_task_commitment": key["canonical_task_commitment"],
        }
    )
    replay: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_REPLAY_SCHEMA_VERSION,
        "resolution_id": FRONTIER_SEMANTIC_RESOLUTION_ID,
        "packet_id": packet_id,
        "packet_set_integrity_sha256": packet_integrity,
        "key_set_integrity_sha256": key_integrity,
        "triage_commitment": triage["integrity_sha256"],
        "response_commitments": list(triage["response_commitments"]),
        "consensus_candidate_commitment": triage[
            "consensus_candidate_commitment"
        ],
        "canonical_arm": canonical_arm,
        "mutated_arm": mutated_arm,
        "canonical_task_commitment": key["canonical_task_commitment"],
        "oracle_set_integrity_sha256": oracles_data["integrity_sha256"],
        "unblinding_identity_commitment": unblinding_identity_commitment,
        "stage_results": stage_results,
        "component_check_count": 30,
        "passed_component_count": passed_component_count,
        "canonical_replay_passed": replay_passed,
        "route": FRONTIER_SEMANTIC_REPLAY_ROUTES[0 if replay_passed else 1],
        "resolution_receipt_required": True,
        "board_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    replay["integrity_sha256"] = frontier_semantic_replay_integrity_sha256(replay)
    return replay


def build_frontier_semantic_resolution_receipt(
    *,
    replay: Mapping[str, Any],
    decision: str,
    adjudicator_identity_commitment: str,
    adjudicator_affiliation_commitment: str,
    conflict_of_interest_declared: bool,
    independence_attested: bool,
    completed_on: str,
    rationale_codes: Sequence[str],
    replacement_resolution_commitment: str | None = None,
) -> dict[str, Any]:
    """Create a private human resolution receipt without changing any board gate."""

    if replay.get("integrity_sha256") != frontier_semantic_replay_integrity_sha256(
        replay
    ):
        raise FrontierContractError("resolution receipt replay integrity mismatch")
    if decision not in FRONTIER_SEMANTIC_RESOLUTION_DECISIONS:
        raise FrontierContractError("unsupported semantic resolution decision")
    replay_passed = _boolean(
        replay.get("canonical_replay_passed"),
        "resolution receipt canonical_replay_passed",
    )
    if decision == "accept_consensus" and not replay_passed:
        raise FrontierContractError("failed canonical replay cannot accept consensus")
    if decision == "override_consensus":
        replacement = _sha256(
            replacement_resolution_commitment,
            "resolution receipt replacement_resolution_commitment",
        )
    else:
        if replacement_resolution_commitment is not None:
            raise FrontierContractError(
                "only override_consensus may bind a replacement resolution"
            )
        replacement = None
    if conflict_of_interest_declared:
        raise FrontierContractError("conflicted adjudicator cannot issue a receipt")
    if not independence_attested:
        raise FrontierContractError("resolution receipt requires independence")
    _sha256(
        adjudicator_identity_commitment,
        "resolution receipt adjudicator_identity_commitment",
    )
    _sha256(
        adjudicator_affiliation_commitment,
        "resolution receipt adjudicator_affiliation_commitment",
    )
    _date(completed_on, "resolution receipt completed_on")
    reasons = list(rationale_codes)
    if not reasons or len(reasons) != len(set(reasons)):
        raise FrontierContractError("resolution receipt requires unique rationale codes")
    if not set(reasons).issubset(_RECEIPT_RATIONALE_CODES):
        raise FrontierContractError("resolution receipt has unknown rationale code")
    accepted_result_commitment = (
        replay["consensus_candidate_commitment"]
        if decision == "accept_consensus"
        else replacement
    )
    receipt: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_RECEIPT_SCHEMA_VERSION,
        "resolution_id": FRONTIER_SEMANTIC_RESOLUTION_ID,
        "packet_id": replay["packet_id"],
        "packet_set_integrity_sha256": replay["packet_set_integrity_sha256"],
        "key_set_integrity_sha256": replay["key_set_integrity_sha256"],
        "triage_commitment": replay["triage_commitment"],
        "response_commitments": list(replay["response_commitments"]),
        "unblinding_identity_commitment": replay[
            "unblinding_identity_commitment"
        ],
        "canonical_replay_integrity_sha256": replay["integrity_sha256"],
        "canonical_replay_passed": replay_passed,
        "decision": decision,
        "accepted_result_commitment": accepted_result_commitment,
        "replacement_resolution_commitment": replacement,
        "adjudicator_identity_commitment": adjudicator_identity_commitment,
        "adjudicator_affiliation_commitment": adjudicator_affiliation_commitment,
        "conflict_of_interest_declared": False,
        "independence_attested": True,
        "completed_on": completed_on,
        "rationale_codes": reasons,
        "admission_review_required": True,
        "board_gate_changed": False,
        "integrity_sha256": "0" * 64,
    }
    receipt["integrity_sha256"] = (
        frontier_semantic_resolution_receipt_integrity_sha256(receipt)
    )
    return receipt


def validate_frontier_semantic_resolution_receipt(
    receipt: Mapping[str, Any], *, replay: Mapping[str, Any]
) -> dict[str, Any]:
    data = _record(
        receipt,
        "semantic_resolution_receipt",
        {
            "schema_version",
            "resolution_id",
            "packet_id",
            "packet_set_integrity_sha256",
            "key_set_integrity_sha256",
            "triage_commitment",
            "response_commitments",
            "unblinding_identity_commitment",
            "canonical_replay_integrity_sha256",
            "canonical_replay_passed",
            "decision",
            "accepted_result_commitment",
            "replacement_resolution_commitment",
            "adjudicator_identity_commitment",
            "adjudicator_affiliation_commitment",
            "conflict_of_interest_declared",
            "independence_attested",
            "completed_on",
            "rationale_codes",
            "admission_review_required",
            "board_gate_changed",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_SEMANTIC_RECEIPT_SCHEMA_VERSION:
        raise FrontierContractError("unsupported semantic resolution receipt schema")
    if data["resolution_id"] != FRONTIER_SEMANTIC_RESOLUTION_ID:
        raise FrontierContractError("unexpected semantic resolution id")
    replay_bindings = {
        "packet_id": "packet_id",
        "packet_set_integrity_sha256": "packet_set_integrity_sha256",
        "key_set_integrity_sha256": "key_set_integrity_sha256",
        "triage_commitment": "triage_commitment",
        "response_commitments": "response_commitments",
        "unblinding_identity_commitment": "unblinding_identity_commitment",
        "canonical_replay_passed": "canonical_replay_passed",
    }
    if any(data[field] != replay[target] for field, target in replay_bindings.items()):
        raise FrontierContractError("semantic resolution receipt rebound replay evidence")
    if data["canonical_replay_integrity_sha256"] != replay["integrity_sha256"]:
        raise FrontierContractError("semantic resolution receipt rebound replay hash")
    expected = build_frontier_semantic_resolution_receipt(
        replay=replay,
        decision=data["decision"],
        adjudicator_identity_commitment=data["adjudicator_identity_commitment"],
        adjudicator_affiliation_commitment=data[
            "adjudicator_affiliation_commitment"
        ],
        conflict_of_interest_declared=data["conflict_of_interest_declared"],
        independence_attested=data["independence_attested"],
        completed_on=data["completed_on"],
        rationale_codes=data["rationale_codes"],
        replacement_resolution_commitment=data[
            "replacement_resolution_commitment"
        ],
    )
    if data != expected:
        raise FrontierContractError("semantic resolution receipt does not replay")
    return data


def build_frontier_semantic_resolution_artifacts(
    *,
    workflow_ledger: Mapping[str, Any],
    workflow_summary: Mapping[str, Any],
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
    workflow_data = validate_frontier_semantic_workflow_summary(
        workflow_summary,
        semantic_summary=semantic_data,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_semantic_workflow_private_opening(
        ledger=workflow_ledger,
        public_summary=workflow_data,
        packet_set=packet_set,
        key_set=key_set,
        semantic_summary=semantic_data,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    _date(compiled_on, "semantic resolution compiled_on")
    packets = _index_records(
        packet_set.get("packets"), id_field="packet_id", path="semantic packets"
    )
    keys = _index_records(
        key_set.get("keys"), id_field="packet_id", path="semantic keys"
    )
    workflow_records = _index_records(
        workflow_ledger.get("records"),
        id_field="packet_id",
        path="semantic workflow records",
    )
    if set(packets) != set(keys) or set(packets) != set(workflow_records):
        raise FrontierContractError("semantic resolution inputs do not share packets")

    records = []
    for packet_id in sorted(packets):
        records.append(
            {
                "packet_id": packet_id,
                "packet_commitment": _canonical_sha256(packets[packet_id]),
                "key_commitment": _canonical_sha256(keys[packet_id]),
                "workflow_record_commitment": _canonical_sha256(
                    workflow_records[packet_id]
                ),
                "status": "awaiting_reviewer_responses",
                "triage_commitment": None,
                "unblinding_identity_commitment": None,
                "canonical_replay_commitment": None,
                "resolution_receipt_commitment": None,
                "board_gate_changed": False,
            }
        )
    ledger: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_RESOLUTION_LEDGER_SCHEMA_VERSION,
        "resolution_id": FRONTIER_SEMANTIC_RESOLUTION_ID,
        "workflow_id": FRONTIER_SEMANTIC_WORKFLOW_ID,
        "protocol_id": workflow_data["protocol_id"],
        "board_id": workflow_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "key_set_integrity_sha256": key_set["integrity_sha256"],
        "workflow_ledger_integrity_sha256": workflow_ledger["integrity_sha256"],
        "workflow_summary_integrity_sha256": workflow_data["integrity_sha256"],
        "unblinding_rule": FRONTIER_SEMANTIC_UNBLINDING_RULE,
        "canonical_replay_rule": FRONTIER_SEMANTIC_REPLAY_RULE,
        "resolution_receipt_rule": FRONTIER_SEMANTIC_RECEIPT_RULE,
        "gate_transition_rule": FRONTIER_SEMANTIC_GATE_TRANSITION_RULE,
        "records": records,
        "awaiting_reviewer_responses_count": 20,
        "unblinded_packet_count": 0,
        "canonical_replay_count": 0,
        "canonical_replay_pass_count": 0,
        "canonical_replay_failure_count": 0,
        "resolution_receipt_count": 0,
        "board_admitted_count": 0,
        "independent_review_complete": False,
        "integrity_sha256": "0" * 64,
    }
    ledger["integrity_sha256"] = (
        frontier_semantic_resolution_ledger_integrity_sha256(ledger)
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_SEMANTIC_RESOLUTION_SUMMARY_SCHEMA_VERSION,
        "resolution_id": FRONTIER_SEMANTIC_RESOLUTION_ID,
        "workflow_id": FRONTIER_SEMANTIC_WORKFLOW_ID,
        "protocol_id": workflow_data["protocol_id"],
        "board_id": workflow_data["board_id"],
        "status": "resolution_contract_ready_no_unblinding",
        "compiled_on": compiled_on,
        "workflow_summary_integrity_sha256": workflow_data["integrity_sha256"],
        "private_resolution_ledger_commitment": ledger["integrity_sha256"],
        "packet_count": 20,
        "awaiting_reviewer_responses_count": 20,
        "unblinding_contract_ready": True,
        "canonical_replay_contract_ready": True,
        "resolution_receipt_contract_ready": True,
        "gate_transition_rule_frozen": True,
        "unblinding_rule": FRONTIER_SEMANTIC_UNBLINDING_RULE,
        "canonical_replay_rule": FRONTIER_SEMANTIC_REPLAY_RULE,
        "resolution_receipt_rule": FRONTIER_SEMANTIC_RECEIPT_RULE,
        "gate_transition_rule": FRONTIER_SEMANTIC_GATE_TRANSITION_RULE,
        "unblinded_packet_count": 0,
        "canonical_replay_count": 0,
        "canonical_replay_pass_count": 0,
        "canonical_replay_failure_count": 0,
        "resolution_receipt_count": 0,
        "independent_review_complete": False,
        "human_resolution_required": True,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = (
        frontier_semantic_resolution_summary_integrity_sha256(summary)
    )
    return ledger, summary


def validate_frontier_semantic_resolution_summary(
    summary: Mapping[str, Any],
    *,
    workflow_summary: Mapping[str, Any],
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
    workflow_data = validate_frontier_semantic_workflow_summary(
        workflow_summary,
        semantic_summary=semantic_data,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    data = _record(
        summary,
        "semantic_resolution_summary",
        {
            "schema_version",
            "resolution_id",
            "workflow_id",
            "protocol_id",
            "board_id",
            "status",
            "compiled_on",
            "workflow_summary_integrity_sha256",
            "private_resolution_ledger_commitment",
            "packet_count",
            "awaiting_reviewer_responses_count",
            "unblinding_contract_ready",
            "canonical_replay_contract_ready",
            "resolution_receipt_contract_ready",
            "gate_transition_rule_frozen",
            "unblinding_rule",
            "canonical_replay_rule",
            "resolution_receipt_rule",
            "gate_transition_rule",
            "unblinded_packet_count",
            "canonical_replay_count",
            "canonical_replay_pass_count",
            "canonical_replay_failure_count",
            "resolution_receipt_count",
            "independent_review_complete",
            "human_resolution_required",
            "board_admitted_count",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "private_payload_published",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_SEMANTIC_RESOLUTION_SUMMARY_SCHEMA_VERSION:
        raise FrontierContractError("unsupported semantic resolution summary schema")
    if (
        data["resolution_id"] != FRONTIER_SEMANTIC_RESOLUTION_ID
        or data["workflow_id"] != FRONTIER_SEMANTIC_WORKFLOW_ID
    ):
        raise FrontierContractError("unexpected semantic resolution identity")
    if (
        data["protocol_id"] != workflow_data["protocol_id"]
        or data["board_id"] != workflow_data["board_id"]
    ):
        raise FrontierContractError("semantic resolution rebound protocol or board")
    if data["status"] != "resolution_contract_ready_no_unblinding":
        raise FrontierContractError("semantic resolution overstates maturity")
    _date(data["compiled_on"], "semantic_resolution_summary.compiled_on")
    if (
        _sha256(
            data["workflow_summary_integrity_sha256"],
            "semantic_resolution_summary.workflow_summary_integrity_sha256",
        )
        != workflow_data["integrity_sha256"]
    ):
        raise FrontierContractError("semantic resolution does not bind workflow")
    _sha256(
        data["private_resolution_ledger_commitment"],
        "semantic_resolution_summary.private_resolution_ledger_commitment",
    )
    exact_counts = {
        "packet_count": 20,
        "awaiting_reviewer_responses_count": 20,
        "unblinded_packet_count": 0,
        "canonical_replay_count": 0,
        "canonical_replay_pass_count": 0,
        "canonical_replay_failure_count": 0,
        "resolution_receipt_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if (
            _integer(data[field_name], f"semantic_resolution_summary.{field_name}")
            != expected
        ):
            raise FrontierContractError(
                f"semantic resolution {field_name} must remain {expected}"
            )
    for field_name in (
        "unblinding_contract_ready",
        "canonical_replay_contract_ready",
        "resolution_receipt_contract_ready",
        "gate_transition_rule_frozen",
        "human_resolution_required",
    ):
        if not _boolean(data[field_name], f"semantic_resolution_summary.{field_name}"):
            raise FrontierContractError(
                f"semantic_resolution_summary.{field_name} must remain true"
            )
    for field_name in (
        "independent_review_complete",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"semantic_resolution_summary.{field_name}"):
            raise FrontierContractError(
                f"semantic_resolution_summary.{field_name} must remain false"
            )
    frozen_rules = {
        "unblinding_rule": FRONTIER_SEMANTIC_UNBLINDING_RULE,
        "canonical_replay_rule": FRONTIER_SEMANTIC_REPLAY_RULE,
        "resolution_receipt_rule": FRONTIER_SEMANTIC_RECEIPT_RULE,
        "gate_transition_rule": FRONTIER_SEMANTIC_GATE_TRANSITION_RULE,
    }
    if any(data[field] != value for field, value in frozen_rules.items()):
        raise FrontierContractError("semantic resolution changed a frozen rule")
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "semantic_resolution_summary.nonclaims"))
    ):
        raise FrontierContractError("semantic resolution removed a nonclaim")
    if data["integrity_sha256"] != (
        frontier_semantic_resolution_summary_integrity_sha256(data)
    ):
        raise FrontierContractError("semantic resolution summary integrity mismatch")
    return data


def validate_frontier_semantic_resolution_private_opening(
    *,
    ledger: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    workflow_ledger: Mapping[str, Any],
    workflow_summary: Mapping[str, Any],
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
    data = validate_frontier_semantic_resolution_summary(
        public_summary,
        workflow_summary=workflow_summary,
        semantic_summary=semantic_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    )
    if ledger.get("integrity_sha256") != (
        frontier_semantic_resolution_ledger_integrity_sha256(ledger)
    ):
        raise FrontierContractError("semantic resolution ledger integrity mismatch")
    expected_ledger, expected_summary = build_frontier_semantic_resolution_artifacts(
        workflow_ledger=workflow_ledger,
        workflow_summary=workflow_summary,
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
            "semantic resolution does not replay from committed inputs"
        )
    return semantic_resolution_summary(
        public_summary,
        workflow_summary=workflow_summary,
        semantic_summary=semantic_summary,
        public_preflight=public_preflight,
        progress=progress,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
        board_slots=board_slots,
    ) | {"private_semantic_resolution_commitment_opened": True}


def load_frontier_semantic_resolution_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_semantic_resolution_summary(
        _load_json(path.read_text(encoding="utf-8"), "semantic resolution summary"),
        **kwargs,
    )


def load_frontier_semantic_resolution_ledger(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "semantic resolution ledger")


def semantic_resolution_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_semantic_resolution_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "packet_count": data["packet_count"],
        "awaiting_reviewer_responses_count": data[
            "awaiting_reviewer_responses_count"
        ],
        "unblinding_contract_ready": data["unblinding_contract_ready"],
        "canonical_replay_contract_ready": data[
            "canonical_replay_contract_ready"
        ],
        "resolution_receipt_contract_ready": data[
            "resolution_receipt_contract_ready"
        ],
        "unblinded_packet_count": data["unblinded_packet_count"],
        "canonical_replay_count": data["canonical_replay_count"],
        "resolution_receipt_count": data["resolution_receipt_count"],
        "human_resolution_required": data["human_resolution_required"],
        "board_admitted_count": data["board_admitted_count"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
