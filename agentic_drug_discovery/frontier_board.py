"""Preregistered sampling-frame contracts for the private ADDS-Frontier board."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .frontier import (
    FRONTIER_TASK_FAMILIES,
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
    validate_frontier_protocol,
)


FRONTIER_BOARD_PROTOCOL_SCHEMA_VERSION = "adds.frontier-board-protocol.v1"
FRONTIER_BOARD_SLOT_SCHEMA_VERSION = "adds.frontier-board-slot-manifest.v1"
FRONTIER_BOARD_ID = "adds-frontier-private-pilot-v1"

FRONTIER_DISEASE_DOMAINS = (
    "hematology",
    "immune_inflammatory",
    "oncology",
    "neurology",
    "metabolic",
    "infectious_disease",
    "cardiovascular",
    "rare_genetic",
)
FRONTIER_CALIBRATION_DOMAINS = (
    "hematology",
    "immune_inflammatory",
)
FRONTIER_SEALED_DOMAINS = tuple(
    domain
    for domain in FRONTIER_DISEASE_DOMAINS
    if domain not in FRONTIER_CALIBRATION_DOMAINS
)
FRONTIER_TEMPORAL_REGIMES = (
    "historical_pre_2024",
    "historical_2024_2025",
    "contemporary_2026",
)
FRONTIER_ADMISSION_GATES = (
    "task_packet_integrity",
    "oracle_commitment_sealed",
    "independent_scientific_review",
    "evidence_lineage_review",
    "temporal_leakage_review",
    "counterfactual_mutation_review",
    "expert_solvability",
    "structured_oracle_replay",
    "conflict_of_interest_clear",
    "contamination_canary_clear",
)

_DOMAIN_TEMPORAL_REGIME = {
    "hematology": "historical_pre_2024",
    "immune_inflammatory": "historical_2024_2025",
    "oncology": "historical_pre_2024",
    "neurology": "historical_pre_2024",
    "metabolic": "historical_2024_2025",
    "infectious_disease": "historical_2024_2025",
    "cardiovascular": "contemporary_2026",
    "rare_genetic": "contemporary_2026",
}
_BOARD_NONCLAIMS = {
    "An unassigned slot is not a curated task or benchmark evidence.",
    "A task cannot be selected, edited, or rejected based on model performance.",
    "Public allocation strata do not reveal private task, disease, program, oracle, or canary content.",
    "Board admission does not establish therapeutic efficacy, safety, or clinical utility.",
}
_SLOT_NONCLAIM = "This slot contains no private task content or benchmark result."


def _canonical_sha256(value: Mapping[str, Any], *, exclude: str) -> str:
    payload = {key: item for key, item in value.items() if key != exclude}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def frontier_board_protocol_integrity_sha256(protocol: Mapping[str, Any]) -> str:
    return _canonical_sha256(protocol, exclude="integrity_sha256")


def frontier_board_slot_manifest_integrity_sha256(
    manifest: Mapping[str, Any],
) -> str:
    return _canonical_sha256(manifest, exclude="integrity_sha256")


def _validate_expected_count(
    value: Any,
    path: str,
    *,
    expected: int,
) -> None:
    if _integer(value, path, minimum=0) != expected:
        raise FrontierContractError(f"{path} must remain {expected}")


def validate_frontier_board_protocol(
    board_protocol: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the frozen 40-slot private-board allocation policy."""

    frontier_data = validate_frontier_protocol(frontier_protocol, root=root)
    data = _record(
        board_protocol,
        "board_protocol",
        {
            "schema_version",
            "protocol_id",
            "board_id",
            "version",
            "status",
            "registered_on",
            "task_target",
            "tasks_per_family",
            "allocation_policy",
            "curation_policy",
            "oracle_policy",
            "contamination_policy",
            "admission_gates",
            "nonclaims",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_BOARD_PROTOCOL_SCHEMA_VERSION:
        raise FrontierContractError(
            "unsupported frontier board protocol schema_version"
        )
    if data["protocol_id"] != frontier_data["protocol_id"]:
        raise FrontierContractError("board protocol does not bind ADDS-Frontier")
    if data["board_id"] != FRONTIER_BOARD_ID:
        raise FrontierContractError("unexpected frontier board_id")
    _text(data["version"], "board_protocol.version")
    if data["status"] != "preregistered_unpopulated":
        raise FrontierContractError("board protocol overstates current maturity")
    _date(data["registered_on"], "board_protocol.registered_on")
    _validate_expected_count(
        data["task_target"], "board_protocol.task_target", expected=40
    )
    _validate_expected_count(
        data["tasks_per_family"],
        "board_protocol.tasks_per_family",
        expected=8,
    )

    allocation = _record(
        data["allocation_policy"],
        "board_protocol.allocation_policy",
        {
            "disease_domains",
            "calibration_domains",
            "sealed_domains",
            "calibration_task_count",
            "sealed_task_count",
            "temporal_regimes",
            "temporal_task_counts",
            "exact_disease_identity_private_until_release",
            "unique_program_commitment_per_task",
        },
    )
    if (
        tuple(
            _text_list(
                allocation["disease_domains"],
                "board_protocol.allocation_policy.disease_domains",
            )
        )
        != FRONTIER_DISEASE_DOMAINS
    ):
        raise FrontierContractError("board disease-domain allocation changed")
    if (
        tuple(
            _text_list(
                allocation["calibration_domains"],
                "board_protocol.allocation_policy.calibration_domains",
            )
        )
        != FRONTIER_CALIBRATION_DOMAINS
    ):
        raise FrontierContractError("board calibration-domain allocation changed")
    if (
        tuple(
            _text_list(
                allocation["sealed_domains"],
                "board_protocol.allocation_policy.sealed_domains",
            )
        )
        != FRONTIER_SEALED_DOMAINS
    ):
        raise FrontierContractError("board sealed-domain allocation changed")
    _validate_expected_count(
        allocation["calibration_task_count"],
        "board_protocol.allocation_policy.calibration_task_count",
        expected=10,
    )
    _validate_expected_count(
        allocation["sealed_task_count"],
        "board_protocol.allocation_policy.sealed_task_count",
        expected=30,
    )
    if (
        tuple(
            _text_list(
                allocation["temporal_regimes"],
                "board_protocol.allocation_policy.temporal_regimes",
            )
        )
        != FRONTIER_TEMPORAL_REGIMES
    ):
        raise FrontierContractError("board temporal regimes changed")
    temporal_counts = _record(
        allocation["temporal_task_counts"],
        "board_protocol.allocation_policy.temporal_task_counts",
        set(FRONTIER_TEMPORAL_REGIMES),
    )
    for regime, expected in zip(
        FRONTIER_TEMPORAL_REGIMES,
        (15, 15, 10),
        strict=True,
    ):
        _validate_expected_count(
            temporal_counts[regime],
            f"board_protocol temporal count {regime}",
            expected=expected,
        )
    for field_name in (
        "exact_disease_identity_private_until_release",
        "unique_program_commitment_per_task",
    ):
        if not _boolean(
            allocation[field_name], f"board_protocol.allocation_policy.{field_name}"
        ):
            raise FrontierContractError(
                f"board_protocol.allocation_policy.{field_name} must remain true"
            )

    curation = _record(
        data["curation_policy"],
        "board_protocol.curation_policy",
        {
            "minimum_independent_curators",
            "author_cannot_vote",
            "adjudicator_cannot_vote",
            "conflict_declaration_required",
            "reviewers_blinded_to_model_outputs",
            "all_review_timestamps_precede_baseline_runs",
        },
    )
    _validate_expected_count(
        curation["minimum_independent_curators"],
        "board_protocol.curation_policy.minimum_independent_curators",
        expected=3,
    )
    for field_name in (
        "author_cannot_vote",
        "adjudicator_cannot_vote",
        "conflict_declaration_required",
        "reviewers_blinded_to_model_outputs",
        "all_review_timestamps_precede_baseline_runs",
    ):
        if not _boolean(
            curation[field_name], f"board_protocol.curation_policy.{field_name}"
        ):
            raise FrontierContractError(
                f"board_protocol.curation_policy.{field_name} must remain true"
            )

    oracle = _record(
        data["oracle_policy"],
        "board_protocol.oracle_policy",
        {
            "structured_oracle_minimum_success",
            "expert_solve_required",
            "canonical_and_mutation_replay_required",
            "oracle_bytes_sealed_until_evaluation_close",
        },
    )
    if oracle["structured_oracle_minimum_success"] != 0.95:
        raise FrontierContractError("board structured-oracle threshold changed")
    for field_name in (
        "expert_solve_required",
        "canonical_and_mutation_replay_required",
        "oracle_bytes_sealed_until_evaluation_close",
    ):
        if not _boolean(
            oracle[field_name], f"board_protocol.oracle_policy.{field_name}"
        ):
            raise FrontierContractError(
                f"board_protocol.oracle_policy.{field_name} must remain true"
            )

    contamination = _record(
        data["contamination_policy"],
        "board_protocol.contamination_policy",
        {
            "model_runs_before_full_freeze_prohibited",
            "model_failure_filtering_prohibited",
            "private_canary_required_per_sealed_task",
            "rotating_sealed_partition",
            "public_development_oracles_excluded",
        },
    )
    for field_name in (
        "model_runs_before_full_freeze_prohibited",
        "model_failure_filtering_prohibited",
        "private_canary_required_per_sealed_task",
        "rotating_sealed_partition",
        "public_development_oracles_excluded",
    ):
        if not _boolean(
            contamination[field_name],
            f"board_protocol.contamination_policy.{field_name}",
        ):
            raise FrontierContractError(
                f"board_protocol.contamination_policy.{field_name} must remain true"
            )
    if (
        tuple(_text_list(data["admission_gates"], "board_protocol.admission_gates"))
        != FRONTIER_ADMISSION_GATES
    ):
        raise FrontierContractError("board admission gates changed")
    nonclaims = set(_text_list(data["nonclaims"], "board_protocol.nonclaims"))
    if not _BOARD_NONCLAIMS.issubset(nonclaims):
        raise FrontierContractError("board protocol removed a required nonclaim")
    expected_integrity = _sha256(
        data["integrity_sha256"], "board_protocol.integrity_sha256"
    )
    actual_integrity = frontier_board_protocol_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier board protocol integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def _expected_slot_id(family_id: str, domain_index: int) -> str:
    family_token = {
        "evidence_lineage_trap": "lineage",
        "temporal_reversal": "temporal",
        "translational_handoff": "handoff",
        "non_exchangeable_replication": "exchangeability",
        "budgeted_evidence_resolution": "budget",
    }[family_id]
    return f"slot-{family_token}-{domain_index + 1:02d}"


def validate_frontier_board_slot_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the unpopulated, model-blind 40-slot board registry."""

    protocol_data = validate_frontier_protocol(frontier_protocol, root=root)
    board_data = validate_frontier_board_protocol(
        board_protocol,
        root=root,
        frontier_protocol=protocol_data,
    )
    data = _record(
        manifest,
        "board_slots",
        {
            "schema_version",
            "protocol_id",
            "board_id",
            "status",
            "board_protocol_integrity_sha256",
            "task_selection_blinded_to_models",
            "baseline_model_runs_started",
            "benchmark_evidence_claimed",
            "slots",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_BOARD_SLOT_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier board-slot schema_version")
    if data["protocol_id"] != protocol_data["protocol_id"]:
        raise FrontierContractError("board slots do not bind ADDS-Frontier")
    if data["board_id"] != board_data["board_id"]:
        raise FrontierContractError("board slots do not bind the board protocol")
    if data["status"] != "unpopulated_preregistered":
        raise FrontierContractError("board-slot status overstates current maturity")
    if (
        _sha256(
            data["board_protocol_integrity_sha256"],
            "board_slots.board_protocol_integrity_sha256",
        )
        != board_data["integrity_sha256"]
    ):
        raise FrontierContractError("board slots do not open the protocol commitment")
    if not _boolean(
        data["task_selection_blinded_to_models"],
        "board_slots.task_selection_blinded_to_models",
    ):
        raise FrontierContractError("board task selection must remain model-blind")
    for field_name in ("baseline_model_runs_started", "benchmark_evidence_claimed"):
        if _boolean(data[field_name], f"board_slots.{field_name}"):
            raise FrontierContractError(f"board_slots.{field_name} must remain false")

    slots = _sequence(data["slots"], "board_slots.slots")
    if len(slots) != 40:
        raise FrontierContractError("board registry must contain exactly 40 slots")
    family_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    partition_counts: Counter[str] = Counter()
    temporal_counts: Counter[str] = Counter()
    slot_ids: set[str] = set()
    slot_index = 0
    for family_id in FRONTIER_TASK_FAMILIES:
        for domain_index, disease_domain in enumerate(FRONTIER_DISEASE_DOMAINS):
            item = slots[slot_index]
            slot = _record(
                item,
                f"board_slots.slots[{slot_index}]",
                {
                    "slot_id",
                    "family_id",
                    "disease_domain",
                    "temporal_regime",
                    "partition",
                    "status",
                    "task_commitment",
                    "oracle_commitment",
                    "program_commitment",
                    "disease_identity_commitment",
                    "curator_roster_commitment",
                    "independent_curator_count",
                    "admission_gate_results",
                    "board_admitted",
                    "nonclaim",
                },
            )
            expected_slot_id = _expected_slot_id(family_id, domain_index)
            if slot["slot_id"] != expected_slot_id:
                raise FrontierContractError(
                    "board slots must preserve the preregistered family-domain order"
                )
            if slot["slot_id"] in slot_ids:
                raise FrontierContractError(
                    "board registry contains duplicate slot ids"
                )
            slot_ids.add(slot["slot_id"])
            if slot["family_id"] != family_id:
                raise FrontierContractError(
                    f"slot {expected_slot_id} rebound its family"
                )
            if slot["disease_domain"] != disease_domain:
                raise FrontierContractError(
                    f"slot {expected_slot_id} rebound its disease domain"
                )
            expected_temporal = _DOMAIN_TEMPORAL_REGIME[disease_domain]
            if slot["temporal_regime"] != expected_temporal:
                raise FrontierContractError(
                    f"slot {expected_slot_id} rebound its temporal regime"
                )
            expected_partition = (
                "calibration"
                if disease_domain in FRONTIER_CALIBRATION_DOMAINS
                else "sealed_evaluation"
            )
            if slot["partition"] != expected_partition:
                raise FrontierContractError(
                    f"slot {expected_slot_id} rebound its board partition"
                )
            if slot["status"] != "unassigned":
                raise FrontierContractError(
                    f"slot {expected_slot_id} overstates authoring progress"
                )
            for field_name in (
                "task_commitment",
                "oracle_commitment",
                "program_commitment",
                "disease_identity_commitment",
                "curator_roster_commitment",
            ):
                if slot[field_name] is not None:
                    raise FrontierContractError(
                        f"unassigned slot {expected_slot_id} cannot contain {field_name}"
                    )
            if (
                _integer(
                    slot["independent_curator_count"],
                    f"slot {expected_slot_id}.independent_curator_count",
                    minimum=0,
                )
                != 0
            ):
                raise FrontierContractError(
                    f"unassigned slot {expected_slot_id} cannot claim curators"
                )
            gate_results = _record(
                slot["admission_gate_results"],
                f"slot {expected_slot_id}.admission_gate_results",
                set(),
            )
            if gate_results:
                raise FrontierContractError(
                    f"unassigned slot {expected_slot_id} cannot claim admission gates"
                )
            if _boolean(
                slot["board_admitted"], f"slot {expected_slot_id}.board_admitted"
            ):
                raise FrontierContractError(
                    f"unassigned slot {expected_slot_id} cannot enter the board"
                )
            if slot["nonclaim"] != _SLOT_NONCLAIM:
                raise FrontierContractError(
                    f"slot {expected_slot_id} removed its nonclaim"
                )
            family_counts[family_id] += 1
            domain_counts[disease_domain] += 1
            partition_counts[expected_partition] += 1
            temporal_counts[expected_temporal] += 1
            slot_index += 1

    if set(family_counts.values()) != {8}:
        raise FrontierContractError("board must allocate eight slots per family")
    if set(domain_counts.values()) != {5}:
        raise FrontierContractError("board must allocate five slots per disease domain")
    if partition_counts != Counter({"sealed_evaluation": 30, "calibration": 10}):
        raise FrontierContractError("board partition counts changed")
    if temporal_counts != Counter(
        {
            "historical_pre_2024": 15,
            "historical_2024_2025": 15,
            "contemporary_2026": 10,
        }
    ):
        raise FrontierContractError("board temporal counts changed")
    expected_integrity = _sha256(
        data["integrity_sha256"], "board_slots.integrity_sha256"
    )
    actual_integrity = frontier_board_slot_manifest_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier board-slot integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def load_frontier_board_protocol(
    path: Path,
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_frontier_board_protocol(
        _load_json(path.read_text(encoding="utf-8"), "frontier board protocol"),
        root=root,
        frontier_protocol=frontier_protocol,
    )


def load_frontier_board_slot_manifest(
    path: Path,
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_frontier_board_slot_manifest(
        _load_json(path.read_text(encoding="utf-8"), "frontier board slots"),
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
    )


def frontier_board_summary(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_frontier_board_slot_manifest(
        manifest,
        root=root,
        frontier_protocol=frontier_protocol,
        board_protocol=board_protocol,
    )
    slots = data["slots"]
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "slot_count": len(slots),
        "calibration_slot_count": sum(
            slot["partition"] == "calibration" for slot in slots
        ),
        "sealed_slot_count": sum(
            slot["partition"] == "sealed_evaluation" for slot in slots
        ),
        "disease_domain_count": len({slot["disease_domain"] for slot in slots}),
        "assigned_task_count": sum(slot["status"] != "unassigned" for slot in slots),
        "board_admitted_count": sum(bool(slot["board_admitted"]) for slot in slots),
        "baseline_model_runs_started": data["baseline_model_runs_started"],
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
