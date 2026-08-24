"""Blinded three-arm placebo controls for coupled frontier augmentation."""

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
from .frontier_calibration import (
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_coupled_augmentation import (
    validate_frontier_coupled_augmentation_private_opening,
    validate_frontier_coupled_augmentation_summary,
)
from .frontier_semantic_review import (
    _delta_certificate,
    _validate_materialized_task,
    frontier_semantic_review_view,
)


FRONTIER_COUPLED_PLACEBO_PACKET_SCHEMA_VERSION = (
    "adds.frontier-private-coupled-placebo-packet-set.v1"
)
FRONTIER_COUPLED_PLACEBO_KEY_SCHEMA_VERSION = (
    "adds.frontier-private-coupled-placebo-key-set.v1"
)
FRONTIER_COUPLED_PLACEBO_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-coupled-placebo-summary.v1"
)
FRONTIER_COUPLED_PLACEBO_SET_ID = "adds-frontier-coupled-placebo-v1"
FRONTIER_COUPLED_PLACEBO_DESIGN_RULE = (
    "blind_canonical_targeted_reveal_and_same_slot_content_null_reveal_"
    "with_equal_structural_delta_and_whitespace_token_count"
)
_ARM_IDS = ("arm_a", "arm_b", "arm_c")
_ROLE_IDS = ("canonical", "candidate", "placebo")
_REVIEW_DIMENSIONS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_PLACEBO_VOCABULARY = (
    "packet",
    "transport",
    "format",
    "parser",
    "record",
    "control",
    "checksum",
    "schema",
)
_PACKET_NONCLAIMS = {
    "Three-arm packet compilation is an experiment design, not a semantic label.",
    "Neutral-vocabulary construction does not prove scientific irrelevance.",
    "Equal structural deltas and whitespace-token counts do not establish full lexical matching.",
    "Arm roles and author expectations are absent from reviewer packets.",
    "Private payload semantics may still make an arm role inferable despite order blinding.",
    "No reviewer response, consensus label, oracle edit, admission, or model result is claimed.",
}
_PUBLIC_NONCLAIMS = {
    "Ten triplets are machine-compiled experiment drafts, not independently reviewed labels.",
    "Structural matching does not establish that the placebo is scientifically irrelevant.",
    "Whitespace-token matching is not tokenizer, syntax, readability, or semantic matching.",
    "Author-expected candidate changes and placebo intent are sealed selection metadata, not observations.",
    "No arm role, task, oracle, evidence text, identity, nonce, or reviewer payload is public.",
    "No reviewer was assigned and no coupling, invariance, contrast, consensus, or adjudication label exists.",
    "No oracle revision, challenge assignment, board admission, model run, or benchmark result is authorized.",
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


def frontier_coupled_placebo_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_coupled_placebo_key_set_integrity_sha256(
    key_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(key_set, exclude=frozenset({"integrity_sha256"}))


def frontier_coupled_placebo_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _neutral_summary(*, token_count: int) -> str:
    if token_count < 1:
        raise FrontierContractError("placebo summary requires at least one token")
    tokens = [
        _PLACEBO_VOCABULARY[index % len(_PLACEBO_VOCABULARY)]
        for index in range(token_count)
    ]
    tokens[-1] = f"{tokens[-1]}."
    return " ".join(tokens)


def _materialize_content_null_reveal(
    task: Mapping[str, Any], *, candidate_summary: str
) -> dict[str, Any]:
    mutated = copy.deepcopy(task)
    token = hashlib.sha256(
        f"{task['slot_id']}|content-null-evidence-reveal".encode("utf-8")
    ).hexdigest()[:16]
    evidence_id = f"ev-placebo-{token}"
    mutated["evidence_nodes"].append(
        {
            "evidence_id": evidence_id,
            "available_on": mutated["stages"][3]["as_of_date"],
            "lineage_id": f"lineage-placebo-{token}",
            "evidence_role": "source",
            "evidence_summary": _neutral_summary(
                token_count=len(candidate_summary.split())
            ),
        }
    )
    for stage in mutated["stages"][3:]:
        stage["accessible_evidence_ids"].append(evidence_id)
    return mutated


def _added_node(
    canonical: Mapping[str, Any], mutated: Mapping[str, Any]
) -> Mapping[str, Any]:
    canonical_ids = {node["evidence_id"] for node in canonical["evidence_nodes"]}
    added = [
        node for node in mutated["evidence_nodes"] if node["evidence_id"] not in canonical_ids
    ]
    if len(added) != 1:
        raise FrontierContractError("placebo design arm must add exactly one node")
    return added[0]


def _structural_fingerprint(
    canonical: Mapping[str, Any], mutated: Mapping[str, Any]
) -> dict[str, Any]:
    node = _added_node(canonical, mutated)
    canonical_lineages = {
        item["lineage_id"] for item in canonical["evidence_nodes"]
    }
    changed_stage_ids: list[str] = []
    access_delta_counts: list[int] = []
    appended_at_end: list[bool] = []
    for canonical_stage, mutated_stage in zip(
        canonical["stages"], mutated["stages"], strict=True
    ):
        if (
            canonical_stage["accessible_evidence_ids"]
            == mutated_stage["accessible_evidence_ids"]
        ):
            continue
        changed_stage_ids.append(canonical_stage["stage_id"])
        access_delta_counts.append(
            len(mutated_stage["accessible_evidence_ids"])
            - len(canonical_stage["accessible_evidence_ids"])
        )
        appended_at_end.append(
            mutated_stage["accessible_evidence_ids"][:-1]
            == canonical_stage["accessible_evidence_ids"]
            and mutated_stage["accessible_evidence_ids"][-1]
            == node["evidence_id"]
        )
    return {
        "added_node_field_names": sorted(node),
        "added_node_available_on": node["available_on"],
        "added_node_evidence_role": node["evidence_role"],
        "added_node_lineage_independent_from_canonical": (
            node["lineage_id"] not in canonical_lineages
        ),
        "changed_stage_ids": changed_stage_ids,
        "access_delta_counts": access_delta_counts,
        "added_node_appended_at_end": appended_at_end,
    }


def _arm_mapping(*, task_index: int) -> dict[str, str]:
    shift = task_index % len(_ARM_IDS)
    return {
        role: _ARM_IDS[(role_index + shift) % len(_ARM_IDS)]
        for role_index, role in enumerate(_ROLE_IDS)
    }


def compile_frontier_coupled_placebo_artifacts(
    *,
    private_coupled_packet_set: Mapping[str, Any],
    public_coupled_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compile blinded triplets without assigning semantic roles as labels."""

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
    coupled_data = validate_frontier_coupled_augmentation_summary(
        public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_coupled_augmentation_private_opening(
        private_packet_set=private_coupled_packet_set,
        public_summary=coupled_data,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight,
        public_preflight=public_preflight,
        private_semantic_packets=private_semantic_packets,
        private_semantic_keys=private_semantic_keys,
        public_semantic_summary=public_semantic_summary,
        private_transition_report=private_transition_report,
        public_transition_summary=public_transition_summary,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=public_fragility_summary,
        private_support_curation_packets=private_support_curation_packets,
        public_support_curation_summary=public_support_curation_summary,
        progress=progress_data,
        **validation_kwargs,
    )
    _date(compiled_on, "coupled placebo compiled_on")

    semantic_packet_by_id = {
        packet["packet_id"]: packet for packet in private_semantic_packets["packets"]
    }
    reveal_key_by_slot = {
        key["slot_id"]: key
        for key in private_semantic_keys["keys"]
        if key["structural_delta_certificate"]["probe_kind"]
        == "bounded_evidence_reveal"
    }
    packets: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for task_index, (task, oracle) in enumerate(
        zip(tasks_data["tasks"], oracles_data["oracles"], strict=True)
    ):
        slot_id = task["slot_id"]
        candidate_key = reveal_key_by_slot.get(slot_id)
        if candidate_key is None:
            raise FrontierContractError(
                f"coupled placebo candidate key missing for {slot_id}"
            )
        source_packet = semantic_packet_by_id.get(candidate_key["packet_id"])
        if source_packet is None:
            raise FrontierContractError(
                f"coupled placebo source packet missing for {slot_id}"
            )
        canonical_view = source_packet[candidate_key["canonical_arm"]]
        candidate_view = source_packet[candidate_key["mutated_arm"]]
        candidate_node = _added_node(canonical_view, candidate_view)
        placebo_task = _materialize_content_null_reveal(
            task, candidate_summary=candidate_node["evidence_summary"]
        )
        _validate_materialized_task(
            task_set=tasks_data,
            oracle_set=oracles_data,
            task_index=task_index,
            mutated_task=placebo_task,
            validation_kwargs=validation_kwargs,
        )
        placebo_view = frontier_semantic_review_view(placebo_task)
        candidate_certificate = candidate_key["structural_delta_certificate"]
        placebo_certificate = _delta_certificate(
            task, placebo_task, probe_kind="bounded_evidence_reveal"
        )
        candidate_fingerprint = _structural_fingerprint(
            canonical_view, candidate_view
        )
        placebo_fingerprint = _structural_fingerprint(
            canonical_view, placebo_view
        )
        placebo_node = _added_node(canonical_view, placebo_view)
        token_count_matched = len(candidate_node["evidence_summary"].split()) == len(
            placebo_node["evidence_summary"].split()
        )
        structural_match = (
            candidate_certificate == placebo_certificate
            and candidate_fingerprint == placebo_fingerprint
        )
        placebo_tokens = {
            token.rstrip(".")
            for token in placebo_node["evidence_summary"].split()
        }
        vocabulary_passed = placebo_tokens.issubset(_PLACEBO_VOCABULARY)
        if not (
            candidate_certificate["exact_delta_passed"]
            and placebo_certificate["exact_delta_passed"]
            and structural_match
            and token_count_matched
            and vocabulary_passed
        ):
            raise FrontierContractError(
                f"coupled placebo matching failed for {slot_id}"
            )

        mapping = _arm_mapping(task_index=task_index)
        role_payloads = {
            "canonical": canonical_view,
            "candidate": candidate_view,
            "placebo": placebo_view,
        }
        arm_payloads = {
            mapping[role]: role_payloads[role] for role in _ROLE_IDS
        }
        blind_digest = hashlib.sha256(
            (
                f"{oracle['oracle_commitment_nonce']}|{slot_id}|"
                "coupled-placebo-triplet"
            ).encode("utf-8")
        ).hexdigest()
        packet_id = f"placebo-{blind_digest[:20]}"
        structure_bundle = {
            "candidate_certificate": candidate_certificate,
            "placebo_certificate": placebo_certificate,
            "candidate_fingerprint": candidate_fingerprint,
            "placebo_fingerprint": placebo_fingerprint,
            "whitespace_token_count_matched": token_count_matched,
        }
        packet = {
            "packet_id": packet_id,
            "review_dimensions": list(_REVIEW_DIMENSIONS),
            **{arm_id: arm_payloads[arm_id] for arm_id in _ARM_IDS},
            **{
                f"{arm_id}_commitment": _canonical_sha256(arm_payloads[arm_id])
                for arm_id in _ARM_IDS
            },
            "matched_structure_commitment": _canonical_sha256(structure_bundle),
        }
        packets.append(packet)
        keys.append(
            {
                "packet_id": packet_id,
                "slot_id": slot_id,
                "source_semantic_packet_id": source_packet["packet_id"],
                "canonical_arm": mapping["canonical"],
                "candidate_arm": mapping["candidate"],
                "placebo_arm": mapping["placebo"],
                "canonical_task_commitment": frontier_calibration_task_sha256(
                    task
                ),
                "candidate_task_commitment": candidate_key[
                    "mutated_task_commitment"
                ],
                "placebo_task_commitment": frontier_calibration_task_sha256(
                    placebo_task
                ),
                "candidate_expected_changed_components": list(
                    candidate_key["expected_changed_components"]
                ),
                "placebo_intended_changed_components": [],
                "candidate_structural_delta_certificate": candidate_certificate,
                "placebo_structural_delta_certificate": placebo_certificate,
                "candidate_structural_fingerprint": candidate_fingerprint,
                "placebo_structural_fingerprint": placebo_fingerprint,
                "candidate_placebo_structural_match_passed": structural_match,
                "whitespace_token_count_matched": token_count_matched,
                "placebo_vocabulary_policy_passed": vocabulary_passed,
                "tokenizer_level_match_established": False,
                "placebo_scientific_invariance_established": False,
                "candidate_scientific_coupling_established": False,
                "contrast_identifiability_established": False,
            }
        )

    packets.sort(key=lambda packet: packet["packet_id"])
    keys.sort(key=lambda key: key["packet_id"])
    arm_role_counts = {
        role: dict(
            Counter(key[f"{role}_arm"] for key in keys)
        )
        for role in _ROLE_IDS
    }
    for counts in arm_role_counts.values():
        for arm_id in _ARM_IDS:
            counts.setdefault(arm_id, 0)
    max_arm_role_imbalance = max(
        max(counts.values()) - min(counts.values())
        for counts in arm_role_counts.values()
    )
    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_COUPLED_PLACEBO_PACKET_SCHEMA_VERSION,
        "set_id": FRONTIER_COUPLED_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "private_coupled_augmentation_packet_set_integrity_sha256": (
            private_coupled_packet_set["integrity_sha256"]
        ),
        "arm_role_mapping_included": False,
        "author_expectations_included": False,
        "minimum_independent_curators_per_packet": 3,
        "review_instructions": [
            "Solve all three arms independently before comparing them.",
            "Return all six stage actions, witnesses, and blockers for every arm.",
            "One arm is canonical and two add one synthetic source from stage 4 onward.",
            "Do not infer scientific relevance from synthetic-source presence or arm order.",
            "Assess candidate/placebo contrast only after completing independent arm solves.",
        ],
        "packets": packets,
        "nonclaims": sorted(_PACKET_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = (
        frontier_coupled_placebo_packet_set_integrity_sha256(packet_set)
    )
    key_set: dict[str, Any] = {
        "schema_version": FRONTIER_COUPLED_PLACEBO_KEY_SCHEMA_VERSION,
        "set_id": FRONTIER_COUPLED_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "keys": keys,
        "arm_role_counts": arm_role_counts,
        "arm_role_balance_max_imbalance": max_arm_role_imbalance,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "independent_review_complete": False,
        "integrity_sha256": "0" * 64,
    }
    key_set["integrity_sha256"] = (
        frontier_coupled_placebo_key_set_integrity_sha256(key_set)
    )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_COUPLED_PLACEBO_SUMMARY_SCHEMA_VERSION,
        "set_id": FRONTIER_COUPLED_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "three_arm_placebo_packets_compiled_review_not_started",
        "compiled_on": compiled_on,
        "public_coupled_augmentation_summary_integrity_sha256": coupled_data[
            "integrity_sha256"
        ],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "private_key_set_commitment": key_set["integrity_sha256"],
        "design_rule": FRONTIER_COUPLED_PLACEBO_DESIGN_RULE,
        "triplet_packet_count": len(packets),
        "canonical_arm_count": len(packets),
        "candidate_reveal_arm_count": len(packets),
        "placebo_reveal_arm_count": len(packets),
        "candidate_exact_structural_delta_count": sum(
            key["candidate_structural_delta_certificate"]["exact_delta_passed"]
            for key in keys
        ),
        "placebo_exact_structural_delta_count": sum(
            key["placebo_structural_delta_certificate"]["exact_delta_passed"]
            for key in keys
        ),
        "candidate_placebo_structural_match_count": sum(
            key["candidate_placebo_structural_match_passed"] for key in keys
        ),
        "whitespace_token_count_match_count": sum(
            key["whitespace_token_count_matched"] for key in keys
        ),
        "placebo_vocabulary_policy_pass_count": sum(
            key["placebo_vocabulary_policy_passed"] for key in keys
        ),
        "arm_role_balance_max_imbalance": max_arm_role_imbalance,
        "arm_role_balance_passed": max_arm_role_imbalance <= 1,
        "tokenizer_level_match_count": 0,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "three_arm_design_ready": len(packets) == 10,
        "structural_confound_control_ready": True,
        "lexical_confound_control_ready": False,
        "human_semantic_review_required": True,
        "placebo_scientific_invariance_established": False,
        "candidate_scientific_coupling_established": False,
        "contrast_identifiability_established": False,
        "canonical_transition_coupling_coverage_ready": coupled_data[
            "canonical_transition_coupling_coverage_ready"
        ],
        "oracle_revision_applied": False,
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
        frontier_coupled_placebo_summary_integrity_sha256(summary)
    )
    return packet_set, key_set, summary


def validate_frontier_coupled_placebo_summary(
    summary: Mapping[str, Any],
    *,
    public_coupled_summary: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
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
    coupled_data = validate_frontier_coupled_augmentation_summary(
        public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    fields = {
        "schema_version",
        "set_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_coupled_augmentation_summary_integrity_sha256",
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "design_rule",
        "triplet_packet_count",
        "canonical_arm_count",
        "candidate_reveal_arm_count",
        "placebo_reveal_arm_count",
        "candidate_exact_structural_delta_count",
        "placebo_exact_structural_delta_count",
        "candidate_placebo_structural_match_count",
        "whitespace_token_count_match_count",
        "placebo_vocabulary_policy_pass_count",
        "arm_role_balance_max_imbalance",
        "arm_role_balance_passed",
        "tokenizer_level_match_count",
        "reviewer_assignment_count",
        "reviewer_response_count",
        "candidate_coupling_label_count",
        "placebo_invariance_label_count",
        "contrast_label_count",
        "consensus_label_count",
        "three_arm_design_ready",
        "structural_confound_control_ready",
        "lexical_confound_control_ready",
        "human_semantic_review_required",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "contrast_identifiability_established",
        "canonical_transition_coupling_coverage_ready",
        "oracle_revision_applied",
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
    data = _record(summary, "coupled_placebo_summary", fields)
    if (
        data["schema_version"] != FRONTIER_COUPLED_PLACEBO_SUMMARY_SCHEMA_VERSION
        or data["set_id"] != FRONTIER_COUPLED_PLACEBO_SET_ID
        or data["protocol_id"] != coupled_data["protocol_id"]
        or data["board_id"] != coupled_data["board_id"]
    ):
        raise FrontierContractError("coupled placebo summary rebound provenance")
    if data["status"] != "three_arm_placebo_packets_compiled_review_not_started":
        raise FrontierContractError("coupled placebo summary overstates maturity")
    _date(data["compiled_on"], "coupled placebo compiled_on")
    if (
        _sha256(
            data["public_coupled_augmentation_summary_integrity_sha256"],
            "coupled placebo upstream summary",
        )
        != coupled_data["integrity_sha256"]
    ):
        raise FrontierContractError("coupled placebo does not bind augmentation")
    for field_name in (
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "integrity_sha256",
    ):
        _sha256(data[field_name], f"coupled placebo {field_name}")
    if data["design_rule"] != FRONTIER_COUPLED_PLACEBO_DESIGN_RULE:
        raise FrontierContractError("coupled placebo changed the frozen design rule")
    exact_counts = {
        "triplet_packet_count": 10,
        "canonical_arm_count": 10,
        "candidate_reveal_arm_count": 10,
        "placebo_reveal_arm_count": 10,
        "candidate_exact_structural_delta_count": 10,
        "placebo_exact_structural_delta_count": 10,
        "candidate_placebo_structural_match_count": 10,
        "whitespace_token_count_match_count": 10,
        "placebo_vocabulary_policy_pass_count": 10,
        "arm_role_balance_max_imbalance": 1,
        "tokenizer_level_match_count": 0,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if _integer(data[field_name], f"coupled placebo {field_name}") != expected:
            raise FrontierContractError(
                f"coupled placebo {field_name} must remain {expected}"
            )
    for field_name in (
        "three_arm_design_ready",
        "structural_confound_control_ready",
        "arm_role_balance_passed",
        "human_semantic_review_required",
    ):
        if not _boolean(data[field_name], f"coupled placebo {field_name}"):
            raise FrontierContractError(f"coupled placebo {field_name} must be true")
    if _boolean(
        data["canonical_transition_coupling_coverage_ready"],
        "coupled placebo canonical coverage",
    ) != coupled_data["canonical_transition_coupling_coverage_ready"]:
        raise FrontierContractError("coupled placebo changed canonical coverage")
    for field_name in (
        "lexical_confound_control_ready",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "contrast_identifiability_established",
        "oracle_revision_applied",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"coupled placebo {field_name}"):
            raise FrontierContractError(
                f"coupled placebo {field_name} must remain false"
            )
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "coupled placebo nonclaims"))
    ):
        raise FrontierContractError("coupled placebo removed a public nonclaim")
    if data["integrity_sha256"] != (
        frontier_coupled_placebo_summary_integrity_sha256(data)
    ):
        raise FrontierContractError("coupled placebo summary integrity mismatch")
    return data


def validate_frontier_coupled_placebo_private_opening(
    *,
    private_packet_set: Mapping[str, Any],
    private_key_set: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    private_coupled_packet_set: Mapping[str, Any],
    public_coupled_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
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
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    data = validate_frontier_coupled_placebo_summary(
        public_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    )
    if private_packet_set.get("integrity_sha256") != (
        frontier_coupled_placebo_packet_set_integrity_sha256(private_packet_set)
    ):
        raise FrontierContractError("coupled placebo packet-set integrity mismatch")
    if private_key_set.get("integrity_sha256") != (
        frontier_coupled_placebo_key_set_integrity_sha256(private_key_set)
    ):
        raise FrontierContractError("coupled placebo key-set integrity mismatch")
    expected_packets, expected_keys, expected_summary = (
        compile_frontier_coupled_placebo_artifacts(
            private_coupled_packet_set=private_coupled_packet_set,
            public_coupled_summary=public_coupled_summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=private_semantic_packets,
            private_semantic_keys=private_semantic_keys,
            public_semantic_summary=public_semantic_summary,
            private_transition_report=private_transition_report,
            public_transition_summary=public_transition_summary,
            private_fragility_report=private_fragility_report,
            public_fragility_summary=public_fragility_summary,
            private_support_curation_packets=private_support_curation_packets,
            public_support_curation_summary=public_support_curation_summary,
            progress=progress,
            compiled_on=data["compiled_on"],
            **validation_kwargs,
        )
    )
    if (
        private_packet_set != expected_packets
        or private_key_set != expected_keys
        or public_summary != expected_summary
    ):
        raise FrontierContractError(
            "coupled placebo artifacts do not replay from committed inputs"
        )
    return coupled_placebo_summary(
        public_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    ) | {"private_coupled_placebo_commitments_opened": True}


def load_frontier_coupled_placebo_packet_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "coupled placebo packets")


def load_frontier_coupled_placebo_key_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "coupled placebo keys")


def load_frontier_coupled_placebo_summary(
    path: Path, **kwargs: Any
) -> dict[str, Any]:
    return validate_frontier_coupled_placebo_summary(
        _load_json(path.read_text(encoding="utf-8"), "coupled placebo summary"),
        **kwargs,
    )


def coupled_placebo_summary(
    summary: Mapping[str, Any], **kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_coupled_placebo_summary(summary, **kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "triplet_packet_count": data["triplet_packet_count"],
        "candidate_placebo_structural_match_count": data[
            "candidate_placebo_structural_match_count"
        ],
        "whitespace_token_count_match_count": data[
            "whitespace_token_count_match_count"
        ],
        "arm_role_balance_max_imbalance": data[
            "arm_role_balance_max_imbalance"
        ],
        "arm_role_balance_passed": data["arm_role_balance_passed"],
        "tokenizer_level_match_count": data["tokenizer_level_match_count"],
        "reviewer_response_count": data["reviewer_response_count"],
        "three_arm_design_ready": data["three_arm_design_ready"],
        "structural_confound_control_ready": data[
            "structural_confound_control_ready"
        ],
        "lexical_confound_control_ready": data[
            "lexical_confound_control_ready"
        ],
        "placebo_scientific_invariance_established": data[
            "placebo_scientific_invariance_established"
        ],
        "candidate_scientific_coupling_established": data[
            "candidate_scientific_coupling_established"
        ],
        "contrast_identifiability_established": data[
            "contrast_identifiability_established"
        ],
        "human_semantic_review_required": data["human_semantic_review_required"],
    }
