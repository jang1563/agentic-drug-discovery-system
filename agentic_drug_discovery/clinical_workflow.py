"""Stable user-facing workflow for clinical evidence decision packages."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .clinical_decision import (
    ClinicalDecisionPackage,
    ClinicalDecisionPolicy,
    ClinicalEvidenceActionOption,
    clinical_decision_package_envelope,
    clinical_decision_policy_from_dict,
    clinical_evidence_action_catalog_from_dict,
    compile_clinical_decision_package,
    validate_clinical_decision_package,
)
from .clinical_synthesis import validate_benefit_risk_synthesis
from .models import (
    ProgramState,
    SerializableRecord,
    _require_instance,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_DECISION_CONFIG_SCHEMA_VERSION = (
    "adds.clinical-evidence-decision-config.v1"
)
CLINICAL_DECISION_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-evidence-decision-summary.v1"
)


class ClinicalEvidenceWorkflowError(ValueError):
    """Raised when a committed clinical workflow cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class ClinicalDecisionConfig(SerializableRecord):
    """Policy and identifiers needed to compile one decision package."""

    synthesis_id: str
    package_id: str
    tensor_id: str
    plan_id: str
    policy: ClinicalDecisionPolicy
    action_catalog: tuple[ClinicalEvidenceActionOption, ...]

    def __post_init__(self) -> None:
        for field_name in ("synthesis_id", "package_id", "tensor_id", "plan_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.policy, ClinicalDecisionPolicy, "policy")
        catalog = tuple(self.action_catalog)
        object.__setattr__(self, "action_catalog", catalog)
        for option in catalog:
            _require_instance(
                option,
                ClinicalEvidenceActionOption,
                "action_catalog item",
            )
        action_ids = tuple(item.action_id for item in catalog)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action_catalog action ids must be unique")


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing:
        raise RecordParseError(f"{path} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise RecordParseError(
            f"{path} has unknown fields: {', '.join(sorted(extra))}"
        )
    return data


def _strict_json(payload: str, label: str) -> Any:
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RecordParseError(f"{label} duplicates key {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise RecordParseError(f"{label} contains {value}")

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(f"{label} is not valid JSON") from exc


def clinical_decision_config_from_dict(value: Any) -> ClinicalDecisionConfig:
    """Parse one exact decision compiler configuration."""

    path = "clinical_decision_config"
    data = _record(
        value,
        path,
        {
            "schema_version",
            "synthesis_id",
            "package_id",
            "tensor_id",
            "plan_id",
            "policy",
            "action_catalog",
        },
    )
    if data["schema_version"] != CLINICAL_DECISION_CONFIG_SCHEMA_VERSION:
        raise RecordParseError("clinical decision config schema_version is unsupported")
    return ClinicalDecisionConfig(
        synthesis_id=data["synthesis_id"],
        package_id=data["package_id"],
        tensor_id=data["tensor_id"],
        plan_id=data["plan_id"],
        policy=clinical_decision_policy_from_dict(
            data["policy"],
            f"{path}.policy",
        ),
        action_catalog=clinical_evidence_action_catalog_from_dict(
            data["action_catalog"],
            f"{path}.action_catalog",
        ),
    )


def clinical_decision_config_from_json(payload: str) -> ClinicalDecisionConfig:
    """Parse config JSON while rejecting duplicate keys and non-finite values."""

    return clinical_decision_config_from_dict(
        _strict_json(payload, "clinical decision config")
    )


def clinical_decision_config_to_dict(
    config: ClinicalDecisionConfig,
) -> dict[str, Any]:
    """Return the canonical JSON-compatible compiler configuration."""

    _require_instance(config, ClinicalDecisionConfig, "config")
    value = to_primitive(config)
    if not isinstance(value, dict):
        raise TypeError("serialized clinical decision config must be an object")
    return {"schema_version": CLINICAL_DECISION_CONFIG_SCHEMA_VERSION, **value}


def _has_exact_packet_update(
    state: ProgramState,
    field_name: str,
    record: SerializableRecord,
) -> bool:
    return any(record in getattr(packet, field_name) for packet in state.packet_history)


def _committed_synthesis_failures(
    state: ProgramState,
    synthesis_id: str,
) -> tuple[str, ...]:
    try:
        state.validate_committed_history()
    except (TypeError, ValueError):
        return ("program_committed_history_invalid",)
    synthesis = state.benefit_risk_syntheses_by_id.get(synthesis_id)
    if synthesis is None:
        return ("committed_synthesis_missing",)
    if not _has_exact_packet_update(
        state,
        "benefit_risk_synthesis_updates",
        synthesis,
    ):
        return ("synthesis_packet_provenance_missing",)
    mapping = state.clinical_endpoint_mappings_by_id.get(
        synthesis.endpoint_mapping_id
    )
    if mapping is None:
        return ("committed_endpoint_mapping_missing",)
    if not _has_exact_packet_update(
        state,
        "clinical_endpoint_mapping_updates",
        mapping,
    ):
        return ("mapping_packet_provenance_missing",)
    continuity_failures = validate_benefit_risk_synthesis(state, synthesis)
    return tuple(f"synthesis_replay:{code}" for code in continuity_failures)


def validate_clinical_decision_against_state(
    state: ProgramState,
    package: ClinicalDecisionPackage,
) -> tuple[str, ...]:
    """Replay a package against its exact committed synthesis and packet history."""

    _require_instance(state, ProgramState, "state")
    _require_instance(package, ClinicalDecisionPackage, "package")
    failures = _committed_synthesis_failures(
        state,
        package.tensor.synthesis_id,
    )
    if failures:
        return failures
    return validate_clinical_decision_package(state, package)


def compile_clinical_decision_from_config(
    state: ProgramState,
    config: ClinicalDecisionConfig,
) -> ClinicalDecisionPackage:
    """Compile a package from an exact accepted-ledger synthesis."""

    _require_instance(state, ProgramState, "state")
    _require_instance(config, ClinicalDecisionConfig, "config")
    failures = _committed_synthesis_failures(state, config.synthesis_id)
    if failures:
        raise ClinicalEvidenceWorkflowError(
            "clinical synthesis is not safely committed: " + ", ".join(failures)
        )
    synthesis = state.benefit_risk_syntheses_by_id[config.synthesis_id]
    package = compile_clinical_decision_package(
        state,
        synthesis,
        config.policy,
        config.action_catalog,
        package_id=config.package_id,
        tensor_id=config.tensor_id,
        plan_id=config.plan_id,
    )
    replay_failures = validate_clinical_decision_against_state(state, package)
    if replay_failures:
        raise ClinicalEvidenceWorkflowError(
            "compiled clinical package failed replay: "
            + ", ".join(replay_failures)
        )
    return package


def clinical_decision_package_summary(
    package: ClinicalDecisionPackage,
) -> dict[str, Any]:
    """Create a compact summary that preserves decision and provenance boundaries."""

    _require_instance(package, ClinicalDecisionPackage, "package")
    catalog = {item.action_id: item for item in package.action_catalog}
    status_counts = {
        status: sum(
            item.status.value == status for item in package.tensor.dimensions
        )
        for status in ("satisfied", "gap", "blocking_signal")
    }
    return {
        "schema_version": CLINICAL_DECISION_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": package.fingerprint,
        "package_id": package.package_id,
        "program_id": package.program_id,
        "as_of_date": package.as_of_date.isoformat(),
        "policy": {
            "policy_id": package.policy.policy_id,
            "version": package.policy.version,
            "registered_on": package.policy.registered_on.isoformat(),
        },
        "evidence": {
            "synthesis_id": package.tensor.synthesis_id,
            "endpoint_mapping_id": package.tensor.endpoint_mapping_id,
            "candidate_id": package.tensor.candidate_id,
            "intervention_id": package.tensor.intervention_id,
            "disease_id": package.tensor.disease_id,
            "trial_count": len(package.tensor.cells),
            "trial_ids": [item.trial_id for item in package.tensor.cells],
            "source_content_hash_count": len(
                package.tensor.source_content_hashes
            ),
            "dimension_status_counts": status_counts,
            "gaps": [
                {
                    "gap_id": item.gap_id,
                    "code": item.code.value,
                    "dimension": item.dimension.value,
                    "summary": item.summary,
                    "gap_mass": item.gap_mass,
                    "blocking": item.blocking,
                }
                for item in package.tensor.gaps
            ],
        },
        "plan": {
            "decision": package.plan.decision.value,
            "code": package.plan.code,
            "rationale_codes": list(package.plan.rationale_codes),
            "selected_actions": [
                {
                    "rank": item.rank,
                    "action_id": item.action_id,
                    "purpose": catalog[item.action_id].purpose,
                    "tool_id": catalog[item.action_id].tool_id,
                    "operation": catalog[item.action_id].operation,
                    "targeted_gap_ids": list(item.targeted_gap_ids),
                    "bounded_voi": item.bounded_voi,
                    "voi_per_cost": item.voi_per_cost,
                    "max_cost": item.max_cost,
                }
                for item in package.plan.selected_actions
            ],
            "untargeted_gap_ids": list(package.plan.untargeted_gap_ids),
            "budget": {
                "limit": package.plan.budget_limit,
                "spent": package.plan.budget_spent,
                "available": package.plan.budget_available,
                "planned_cost": package.plan.planned_cost,
                "remaining_after_plan": (
                    package.plan.budget_remaining_after_plan
                ),
            },
        },
        "guardrails": {
            "workflow_scope": package.plan.workflow_scope,
            "pooling_performed": package.tensor.pooling_performed,
            "cross_trial_comparability_inferred": (
                package.tensor.cross_trial_comparability_inferred
            ),
            "population_homogeneity_inferred": (
                package.tensor.population_homogeneity_inferred
            ),
            "clinical_acceptability_inferred": (
                package.tensor.clinical_acceptability_inferred
                or package.plan.clinical_acceptability_inferred
            ),
            "terminal_decision_issued": package.plan.terminal_decision_issued,
        },
    }


def clinical_decision_validation_report(
    package: ClinicalDecisionPackage,
    *,
    state: ProgramState | None = None,
) -> dict[str, Any]:
    """Return one machine-readable integrity or full state-replay report."""

    summary = clinical_decision_package_summary(package)
    failures = (
        ()
        if state is None
        else validate_clinical_decision_against_state(state, package)
    )
    return {
        **summary,
        "validation": {
            "status": "valid" if not failures else "invalid",
            "scope": (
                "integrity_and_structure"
                if state is None
                else "integrity_structure_and_state_replay"
            ),
            "failure_codes": list(failures),
        },
    }


def clinical_decision_envelope_from_config(
    state: ProgramState,
    config: ClinicalDecisionConfig,
) -> dict[str, Any]:
    """Compile and serialize one integrity-bound decision package."""

    return clinical_decision_package_envelope(
        compile_clinical_decision_from_config(state, config)
    )
