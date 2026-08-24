"""Strict contracts for the ADDS-Frontier research benchmark."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


FRONTIER_PROTOCOL_SCHEMA_VERSION = "adds.frontier-research-protocol.v1"
FRONTIER_SEED_MANIFEST_SCHEMA_VERSION = "adds.frontier-pilot-seed-manifest.v1"
FRONTIER_PROTOCOL_ID = "adds-frontier-v1"

FRONTIER_DISPOSITIONS = ("advance", "hold", "terminate")
FRONTIER_NEXT_ACTIONS = (
    "retrieve",
    "verify",
    "experiment",
    "human_review",
    "none",
)
FRONTIER_RISK_FLAGS = (
    "safety",
    "contradiction",
    "provenance",
    "out_of_distribution",
    "temporal_leakage",
)
FRONTIER_TASK_FAMILIES = (
    "evidence_lineage_trap",
    "temporal_reversal",
    "translational_handoff",
    "non_exchangeable_replication",
    "budgeted_evidence_resolution",
)
FRONTIER_MANDATORY_GATES = (
    "evidence_retrieval_complete",
    "identity_continuity",
    "cutoff_compliance",
    "lineage_independence",
    "endpoint_population_alignment",
    "uncertainty_handling",
    "disposition_correct",
    "next_action_correct",
    "risk_flags_correct",
    "witness_valid",
    "blocker_certificate_valid",
    "budget_compliance",
    "exact_replay",
)
FRONTIER_PARTIAL_METRICS = (
    "valid_trajectory_survival",
    "first_critical_failure_stage",
    "evidence_retrieval_recall",
    "witness_blocker_exactness",
    "unauthorized_commit_rate",
    "contradiction_recovery_rate",
    "risk_coverage_cost",
    "normalized_valid_progress",
)

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
_THREAT_IDS = {
    "benchmark_contamination",
    "post_cutoff_leakage",
    "identity_rebinding",
    "derivative_source_double_counting",
    "endpoint_population_mismatch",
    "prompt_injection_in_source_text",
    "abstention_only_safety_gain",
    "automation_bias",
    "benchmark_author_overfitting",
}
_REQUIRED_NONCLAIMS = {
    "A launch-band score is an observational target, not a task-selection criterion.",
    "Design seeds and synthetic mutations are not benchmark performance evidence.",
    "Cryptographic provenance does not establish source truth or scientific independence.",
    "Full-trajectory success does not establish therapeutic efficacy or clinical utility.",
    "No real independently curated ADDS-Frontier board result is currently claimed.",
}


class FrontierContractError(ValueError):
    """Raised when an ADDS-Frontier artifact violates its frozen contract."""


@dataclass(frozen=True, slots=True)
class FrontierAction:
    """Factorized scientific action used across frontier task families."""

    disposition: str
    next_action: str
    risk_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition not in FRONTIER_DISPOSITIONS:
            raise FrontierContractError("unsupported frontier disposition")
        if self.next_action not in FRONTIER_NEXT_ACTIONS:
            raise FrontierContractError("unsupported frontier next action")
        flags = tuple(self.risk_flags)
        object.__setattr__(self, "risk_flags", flags)
        if len(flags) != len(set(flags)):
            raise FrontierContractError("frontier risk flags must be unique")
        unknown = set(flags) - set(FRONTIER_RISK_FLAGS)
        if unknown:
            raise FrontierContractError(
                f"unsupported frontier risk flags: {', '.join(sorted(unknown))}"
            )
        if self.disposition == "terminate" and self.next_action != "none":
            raise FrontierContractError("terminate must not schedule a next action")
        if self.disposition == "hold" and self.next_action == "none":
            raise FrontierContractError("hold requires a bounded next action")


def fully_authorized_trajectory_success(
    gate_results: Mapping[str, bool],
    *,
    unauthorized_commit_count: int,
) -> bool:
    """Return the strict primary metric for one completed trajectory.

    Gate results must be evaluator-generated. A final answer cannot compensate for
    a failed gate, a missing gate, or any unauthorized commit.
    """

    if not isinstance(gate_results, Mapping):
        raise FrontierContractError("gate_results must be an object")
    missing = set(FRONTIER_MANDATORY_GATES) - set(gate_results)
    extra = set(gate_results) - set(FRONTIER_MANDATORY_GATES)
    if missing:
        raise FrontierContractError(
            f"gate_results missing mandatory gates: {', '.join(sorted(missing))}"
        )
    if extra:
        raise FrontierContractError(
            f"gate_results has unknown gates: {', '.join(sorted(extra))}"
        )
    if any(not isinstance(value, bool) for value in gate_results.values()):
        raise FrontierContractError("every mandatory gate result must be boolean")
    if (
        not isinstance(unauthorized_commit_count, int)
        or isinstance(unauthorized_commit_count, bool)
        or unauthorized_commit_count < 0
    ):
        raise FrontierContractError(
            "unauthorized_commit_count must be a non-negative integer"
        )
    return all(gate_results.values()) and unauthorized_commit_count == 0


def _reject_constant(value: str) -> None:
    raise FrontierContractError(f"non-finite JSON constant is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrontierContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str, artifact_name: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except FrontierContractError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrontierContractError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FrontierContractError(f"{artifact_name} must be a JSON object")
    return value


def _record(value: Any, path: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FrontierContractError(f"{path} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing:
        raise FrontierContractError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise FrontierContractError(
            f"{path} has unknown fields: {', '.join(sorted(extra))}"
        )
    return dict(value)


def _sequence(value: Any, path: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FrontierContractError(f"{path} must be an array")
    return list(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrontierContractError(f"{path} must be a non-empty string")
    return value


def _text_list(value: Any, path: str, *, nonempty: bool = True) -> list[str]:
    items = _sequence(value, path)
    if nonempty and not items:
        raise FrontierContractError(f"{path} must not be empty")
    result = [_text(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if len(result) != len(set(result)):
        raise FrontierContractError(f"{path} must contain unique values")
    return result


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise FrontierContractError(f"{path} must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FrontierContractError(f"{path} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise FrontierContractError(f"{path} must be finite")
    return number


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise FrontierContractError(f"{path} must be boolean")
    return value


def _date(value: Any, path: str) -> date:
    text = _text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise FrontierContractError(f"{path} must be an ISO date") from exc


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if len(text) != 64 or text.lower() != text:
        raise FrontierContractError(f"{path} must be a lowercase SHA-256 digest")
    try:
        int(text, 16)
    except ValueError as exc:
        raise FrontierContractError(
            f"{path} must be a lowercase SHA-256 digest"
        ) from exc
    return text


def _relative_path(value: Any, path: str) -> str:
    text = _text(value, path)
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or text != pure.as_posix():
        raise FrontierContractError(f"{path} must be a normalized relative POSIX path")
    return text


def _integrity_sha256(artifact: Mapping[str, Any]) -> str:
    payload = {
        key: value for key, value in artifact.items() if key != "integrity_sha256"
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def frontier_protocol_integrity_sha256(protocol: Mapping[str, Any]) -> str:
    """Return the canonical protocol hash, excluding its integrity field."""

    return _integrity_sha256(protocol)


def frontier_seed_manifest_integrity_sha256(manifest: Mapping[str, Any]) -> str:
    """Return the canonical seed-manifest hash, excluding its integrity field."""

    return _integrity_sha256(manifest)


def _require_exact_order(value: Any, path: str, expected: tuple[str, ...]) -> None:
    actual = tuple(_text_list(value, path))
    if actual != expected:
        raise FrontierContractError(f"{path} changed the frozen vocabulary or ordering")


def _validate_score_band(value: Any, path: str) -> None:
    data = _record(
        value,
        path,
        {"lower", "nominal", "upper", "used_for_task_selection"},
    )
    lower = _number(data["lower"], f"{path}.lower")
    nominal = _number(data["nominal"], f"{path}.nominal")
    upper = _number(data["upper"], f"{path}.upper")
    if (lower, nominal, upper) != (0.005, 0.02, 0.05):
        raise FrontierContractError("frontier launch band changed")
    if _boolean(data["used_for_task_selection"], f"{path}.used_for_task_selection"):
        raise FrontierContractError(
            "frontier launch band must not be used for task selection"
        )


def validate_frontier_protocol(
    protocol: Mapping[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    """Validate the frozen public ADDS-Frontier research protocol."""

    data = _record(
        protocol,
        "protocol",
        {
            "schema_version",
            "protocol_id",
            "version",
            "status",
            "registered_on",
            "research_question",
            "primary_metric",
            "frontier_launch_band",
            "action_ontology",
            "mandatory_gates",
            "task_families",
            "benchmark_tiers",
            "sampling_policy",
            "evaluation_policy",
            "threat_model",
            "nonclaims",
            "next_milestone",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_PROTOCOL_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier protocol schema_version")
    if data["protocol_id"] != FRONTIER_PROTOCOL_ID:
        raise FrontierContractError("unexpected frontier protocol_id")
    _text(data["version"], "protocol.version")
    if data["status"] != "preregistered_pilot_design":
        raise FrontierContractError("frontier protocol status overstates maturity")
    _date(data["registered_on"], "protocol.registered_on")
    _text(data["research_question"], "protocol.research_question")

    metric = _record(
        data["primary_metric"],
        "protocol.primary_metric",
        {"metric_id", "name", "success_rule", "final_answer_override_allowed"},
    )
    if metric["metric_id"] != "fully_authorized_trajectory_success":
        raise FrontierContractError("primary frontier metric changed")
    _text(metric["name"], "protocol.primary_metric.name")
    if metric["success_rule"] != "all_mandatory_gates_and_zero_unauthorized_commits":
        raise FrontierContractError("primary frontier success rule changed")
    if _boolean(
        metric["final_answer_override_allowed"],
        "protocol.primary_metric.final_answer_override_allowed",
    ):
        raise FrontierContractError(
            "a final answer cannot override a failed trajectory"
        )
    _validate_score_band(data["frontier_launch_band"], "protocol.frontier_launch_band")

    ontology = _record(
        data["action_ontology"],
        "protocol.action_ontology",
        {"dispositions", "next_actions", "risk_flags"},
    )
    _require_exact_order(
        ontology["dispositions"],
        "protocol.action_ontology.dispositions",
        FRONTIER_DISPOSITIONS,
    )
    _require_exact_order(
        ontology["next_actions"],
        "protocol.action_ontology.next_actions",
        FRONTIER_NEXT_ACTIONS,
    )
    _require_exact_order(
        ontology["risk_flags"],
        "protocol.action_ontology.risk_flags",
        FRONTIER_RISK_FLAGS,
    )
    _require_exact_order(
        data["mandatory_gates"],
        "protocol.mandatory_gates",
        FRONTIER_MANDATORY_GATES,
    )

    root = root.resolve()
    family_ids: list[str] = []
    pilot_total = 0
    for index, item in enumerate(
        _sequence(data["task_families"], "protocol.task_families")
    ):
        family = _record(
            item,
            f"protocol.task_families[{index}]",
            {
                "family_id",
                "name",
                "research_question",
                "required_gates",
                "seed_artifacts",
                "pilot_base_tasks",
            },
        )
        family_id = _text(family["family_id"], f"task family {index}.family_id")
        family_ids.append(family_id)
        _text(family["name"], f"task family {family_id}.name")
        _text(
            family["research_question"],
            f"task family {family_id}.research_question",
        )
        gates = set(
            _text_list(
                family["required_gates"], f"task family {family_id}.required_gates"
            )
        )
        unknown_gates = gates - set(FRONTIER_MANDATORY_GATES)
        if unknown_gates:
            raise FrontierContractError(
                f"task family {family_id} references unknown gates"
            )
        if family_id in _FAMILY_REQUIRED_GATES and not _FAMILY_REQUIRED_GATES[
            family_id
        ].issubset(gates):
            raise FrontierContractError(
                f"task family {family_id} lost its defining gates"
            )
        artifacts = _text_list(
            family["seed_artifacts"], f"task family {family_id}.seed_artifacts"
        )
        for artifact_index, value in enumerate(artifacts):
            relative = _relative_path(
                value, f"task family {family_id}.seed_artifacts[{artifact_index}]"
            )
            resolved = (root / relative).resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise FrontierContractError(
                    f"task family {family_id} seed artifact escapes the repository"
                ) from exc
            if not resolved.is_file():
                raise FrontierContractError(
                    f"task family {family_id} seed artifact is missing: {relative}"
                )
        pilot_count = _integer(
            family["pilot_base_tasks"],
            f"task family {family_id}.pilot_base_tasks",
            minimum=1,
        )
        if pilot_count != 8:
            raise FrontierContractError(
                "each frontier family must begin with eight pilot tasks"
            )
        pilot_total += pilot_count
    if tuple(family_ids) != FRONTIER_TASK_FAMILIES:
        raise FrontierContractError("task families changed the frozen set or ordering")

    tiers = _sequence(data["benchmark_tiers"], "protocol.benchmark_tiers")
    if len(tiers) != 2:
        raise FrontierContractError(
            "frontier protocol requires diagnostic and frontier tiers"
        )
    expected_tiers = (
        ("diagnostic", False, 1, 3),
        ("frontier", True, 6, 12),
    )
    for index, expected in enumerate(expected_tiers):
        tier = _record(
            tiers[index],
            f"protocol.benchmark_tiers[{index}]",
            {"tier_id", "primary", "minimum_stages", "maximum_stages", "purpose"},
        )
        observed = (
            tier["tier_id"],
            _boolean(tier["primary"], f"benchmark tier {index}.primary"),
            _integer(
                tier["minimum_stages"],
                f"benchmark tier {index}.minimum_stages",
                minimum=1,
            ),
            _integer(
                tier["maximum_stages"],
                f"benchmark tier {index}.maximum_stages",
                minimum=1,
            ),
        )
        if observed != expected:
            raise FrontierContractError("benchmark tier contract changed")
        if observed[2] > observed[3]:
            raise FrontierContractError("benchmark tier stage bounds are inconsistent")
        _text(tier["purpose"], f"benchmark tier {index}.purpose")

    sampling = _record(
        data["sampling_policy"],
        "protocol.sampling_policy",
        {
            "pilot_base_task_count",
            "pilot_min_mutations_per_task",
            "full_base_task_minimum",
            "full_diagnostic_case_minimum",
            "baseline_blind_selection",
            "model_failure_filtering_prohibited",
            "heldout_split_by_program_disease_time",
            "rotating_private_test",
        },
    )
    expected_counts = {
        "pilot_base_task_count": 40,
        "pilot_min_mutations_per_task": 5,
        "full_base_task_minimum": 300,
        "full_diagnostic_case_minimum": 1500,
    }
    for field_name, expected in expected_counts.items():
        if (
            _integer(sampling[field_name], f"sampling_policy.{field_name}", minimum=1)
            != expected
        ):
            raise FrontierContractError(f"sampling_policy.{field_name} changed")
    if pilot_total != sampling["pilot_base_task_count"]:
        raise FrontierContractError(
            "task-family pilot counts do not match sampling policy"
        )
    for field_name in (
        "baseline_blind_selection",
        "model_failure_filtering_prohibited",
        "heldout_split_by_program_disease_time",
        "rotating_private_test",
    ):
        if not _boolean(sampling[field_name], f"sampling_policy.{field_name}"):
            raise FrontierContractError(
                f"sampling_policy.{field_name} must remain true"
            )

    evaluation = _record(
        data["evaluation_policy"],
        "protocol.evaluation_policy",
        {
            "structured_oracle_minimum_success",
            "independent_expert_baseline_required",
            "common_frozen_environment_required",
            "cost_and_wall_time_reporting_required",
            "primary_pass_k",
            "reported_pass_k",
            "program_clustered_intervals",
            "paired_comparisons",
            "partial_metrics",
        },
    )
    if (
        _number(
            evaluation["structured_oracle_minimum_success"],
            "evaluation_policy.structured_oracle_minimum_success",
        )
        != 0.95
    ):
        raise FrontierContractError("structured oracle minimum changed")
    for field_name in (
        "independent_expert_baseline_required",
        "common_frozen_environment_required",
        "cost_and_wall_time_reporting_required",
        "program_clustered_intervals",
        "paired_comparisons",
    ):
        if not _boolean(evaluation[field_name], f"evaluation_policy.{field_name}"):
            raise FrontierContractError(
                f"evaluation_policy.{field_name} must remain true"
            )
    if (
        _integer(
            evaluation["primary_pass_k"], "evaluation_policy.primary_pass_k", minimum=1
        )
        != 1
    ):
        raise FrontierContractError("primary frontier metric must remain pass@1")
    reported_pass_k = _sequence(
        evaluation["reported_pass_k"], "evaluation_policy.reported_pass_k"
    )
    if reported_pass_k != [1, 3, 8]:
        raise FrontierContractError("reported pass@k schedule changed")
    _require_exact_order(
        evaluation["partial_metrics"],
        "evaluation_policy.partial_metrics",
        FRONTIER_PARTIAL_METRICS,
    )

    threats = _sequence(data["threat_model"], "protocol.threat_model")
    threat_ids: set[str] = set()
    for index, item in enumerate(threats):
        threat = _record(
            item,
            f"protocol.threat_model[{index}]",
            {"threat_id", "failure", "required_control"},
        )
        threat_id = _text(threat["threat_id"], f"threat {index}.threat_id")
        if threat_id in threat_ids:
            raise FrontierContractError(f"duplicate threat_id: {threat_id}")
        threat_ids.add(threat_id)
        _text(threat["failure"], f"threat {threat_id}.failure")
        _text(threat["required_control"], f"threat {threat_id}.required_control")
    if threat_ids != _THREAT_IDS:
        raise FrontierContractError("threat model must preserve the frozen threat set")

    nonclaims = set(_text_list(data["nonclaims"], "protocol.nonclaims"))
    if not _REQUIRED_NONCLAIMS.issubset(nonclaims):
        raise FrontierContractError("frontier protocol removed a required nonclaim")

    milestone = _record(
        data["next_milestone"],
        "protocol.next_milestone",
        {
            "name",
            "canonical_tasks_per_family",
            "status",
            "benchmark_evidence_claimed",
            "exit_condition",
        },
    )
    _text(milestone["name"], "next_milestone.name")
    if (
        _integer(
            milestone["canonical_tasks_per_family"],
            "next_milestone.canonical_tasks_per_family",
            minimum=1,
        )
        != 8
    ):
        raise FrontierContractError("next milestone must retain eight tasks per family")
    if milestone["status"] != "not_started":
        raise FrontierContractError("next milestone status overstates current evidence")
    if _boolean(
        milestone["benchmark_evidence_claimed"],
        "next_milestone.benchmark_evidence_claimed",
    ):
        raise FrontierContractError("pilot design cannot claim benchmark evidence")
    _text(milestone["exit_condition"], "next_milestone.exit_condition")

    expected_integrity = _sha256(data["integrity_sha256"], "protocol.integrity_sha256")
    actual_integrity = frontier_protocol_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier protocol integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def frontier_protocol_from_json(text: str, *, root: Path) -> dict[str, Any]:
    """Parse and validate a strict frontier research protocol."""

    return validate_frontier_protocol(_load_json(text, "protocol"), root=root)


def load_frontier_protocol(path: Path, *, root: Path) -> dict[str, Any]:
    """Load and validate a frontier research protocol from disk."""

    return frontier_protocol_from_json(path.read_text(encoding="utf-8"), root=root)


def frontier_protocol_summary(
    protocol: Mapping[str, Any], *, root: Path
) -> dict[str, Any]:
    """Return a compact machine-facing summary after full validation."""

    data = validate_frontier_protocol(protocol, root=root)
    return {
        "protocol_id": data["protocol_id"],
        "version": data["version"],
        "status": data["status"],
        "primary_metric": data["primary_metric"]["metric_id"],
        "frontier_launch_nominal": data["frontier_launch_band"]["nominal"],
        "task_family_count": len(data["task_families"]),
        "mandatory_gate_count": len(data["mandatory_gates"]),
        "pilot_base_task_count": data["sampling_policy"]["pilot_base_task_count"],
        "pilot_minimum_diagnostic_cases": (
            data["sampling_policy"]["pilot_base_task_count"]
            * data["sampling_policy"]["pilot_min_mutations_per_task"]
        ),
        "real_benchmark_evidence_claimed": data["next_milestone"][
            "benchmark_evidence_claimed"
        ],
    }


def validate_frontier_seed_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one design-only seed for every frozen frontier task family."""

    protocol_data = validate_frontier_protocol(protocol, root=root)
    data = _record(
        manifest,
        "seed_manifest",
        {
            "schema_version",
            "protocol_id",
            "manifest_status",
            "benchmark_evidence_claimed",
            "seeds",
            "integrity_sha256",
        },
    )
    if data["schema_version"] != FRONTIER_SEED_MANIFEST_SCHEMA_VERSION:
        raise FrontierContractError("unsupported frontier seed manifest schema_version")
    if data["protocol_id"] != protocol_data["protocol_id"]:
        raise FrontierContractError("seed manifest does not bind the frontier protocol")
    if data["manifest_status"] != "design_seeds_only":
        raise FrontierContractError("seed manifest status overstates maturity")
    if _boolean(
        data["benchmark_evidence_claimed"], "seed_manifest.benchmark_evidence_claimed"
    ):
        raise FrontierContractError("design seeds cannot claim benchmark evidence")

    root = root.resolve()
    protocol_families = {
        family["family_id"]: family for family in protocol_data["task_families"]
    }
    family_ids: list[str] = []
    seed_ids: set[str] = set()
    for index, item in enumerate(_sequence(data["seeds"], "seed_manifest.seeds")):
        seed = _record(
            item,
            f"seed_manifest.seeds[{index}]",
            {
                "seed_id",
                "family_id",
                "maturity",
                "evidence_geometry",
                "source_artifacts",
                "planned_stage_count",
                "planned_mutations",
                "nonclaim",
            },
        )
        seed_id = _text(seed["seed_id"], f"seed {index}.seed_id")
        if seed_id in seed_ids:
            raise FrontierContractError(f"duplicate seed_id: {seed_id}")
        seed_ids.add(seed_id)
        family_id = _text(seed["family_id"], f"seed {seed_id}.family_id")
        family_ids.append(family_id)
        protocol_family = protocol_families.get(family_id)
        if protocol_family is None:
            raise FrontierContractError(
                f"seed {seed_id} references an unknown task family"
            )
        if seed["maturity"] != "design_seed":
            raise FrontierContractError(f"seed {seed_id} overstates maturity")
        _text(seed["evidence_geometry"], f"seed {seed_id}.evidence_geometry")
        artifacts = _text_list(
            seed["source_artifacts"], f"seed {seed_id}.source_artifacts"
        )
        if artifacts != protocol_family["seed_artifacts"]:
            raise FrontierContractError(
                f"seed {seed_id} source_artifacts changed the protocol binding"
            )
        for artifact_index, value in enumerate(artifacts):
            relative = _relative_path(
                value, f"seed {seed_id}.source_artifacts[{artifact_index}]"
            )
            resolved = (root / relative).resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise FrontierContractError(
                    f"seed {seed_id} artifact escapes the repository"
                ) from exc
            if not resolved.is_file():
                raise FrontierContractError(
                    f"seed {seed_id} artifact is missing: {relative}"
                )
        stage_count = _integer(
            seed["planned_stage_count"],
            f"seed {seed_id}.planned_stage_count",
            minimum=1,
        )
        if not 6 <= stage_count <= 12:
            raise FrontierContractError(
                f"seed {seed_id} is not a frontier-length 6-12 stage trajectory"
            )
        if (
            len(
                _text_list(
                    seed["planned_mutations"], f"seed {seed_id}.planned_mutations"
                )
            )
            < 5
        ):
            raise FrontierContractError(
                f"seed {seed_id} requires at least five mutations"
            )
        if (
            seed["nonclaim"]
            != "This design seed is not benchmark performance evidence."
        ):
            raise FrontierContractError(f"seed {seed_id} removed its nonclaim")
    if tuple(family_ids) != FRONTIER_TASK_FAMILIES:
        raise FrontierContractError(
            "seed manifest must cover each task family exactly once in order"
        )

    expected_integrity = _sha256(
        data["integrity_sha256"], "seed_manifest.integrity_sha256"
    )
    actual_integrity = frontier_seed_manifest_integrity_sha256(data)
    if expected_integrity != actual_integrity:
        raise FrontierContractError(
            f"frontier seed manifest integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )
    return data


def frontier_seed_manifest_from_json(
    text: str,
    *,
    root: Path,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse and validate a strict frontier pilot seed manifest."""

    return validate_frontier_seed_manifest(
        _load_json(text, "seed manifest"),
        root=root,
        protocol=protocol,
    )


def load_frontier_seed_manifest(
    path: Path,
    *,
    root: Path,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Load and validate a frontier pilot seed manifest from disk."""

    return frontier_seed_manifest_from_json(
        path.read_text(encoding="utf-8"),
        root=root,
        protocol=protocol,
    )


def frontier_seed_manifest_summary(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a compact summary after validating all design seeds."""

    data = validate_frontier_seed_manifest(manifest, root=root, protocol=protocol)
    return {
        "protocol_id": data["protocol_id"],
        "manifest_status": data["manifest_status"],
        "seed_count": len(data["seeds"]),
        "family_ids": [seed["family_id"] for seed in data["seeds"]],
        "planned_mutation_count": sum(
            len(seed["planned_mutations"]) for seed in data["seeds"]
        ),
        "benchmark_evidence_claimed": data["benchmark_evidence_claimed"],
    }
