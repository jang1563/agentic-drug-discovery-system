"""Strict JSON ingestion and deterministic replay for public model records."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Sequence, TypeVar

from .environment import GatedDiscoveryEnvironment
from .execution import (
    ExecutionMode,
    ToolExecutionLedger,
    ToolOutcome,
    ToolRequest,
    ToolStatus,
)
from .models import (
    ActionRecord,
    ActionType,
    AssayRecord,
    BenefitRiskSynthesisRecord,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    ClinicalEndpointBindingRecord,
    ClinicalEndpointMappingRecord,
    ClaimDisposition,
    Decision,
    DecisionPacket,
    DecisionRecord,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    InterventionRecord,
    ModelSystemRecord,
    ProgramState,
    ProgramStatus,
    ScientificClaim,
    SerializableRecord,
    SourceReference,
    Stage,
    StudyBenefitRiskRecord,
    TargetRecord,
    TrialArmRecord,
    TrialArmRole,
    TrialDesignRecord,
    TrialEndpointRecord,
    TrialPopulationRecord,
    TrialRecord,
    TrialSafetyArmRecord,
    TrialSafetyRecord,
    TransitionResult,
    VerifierKind,
    VerifierResult,
    VerifierStatus,
    _require_instance,
)


class RecordParseError(ValueError):
    """Raised when a serialized public record violates its declared shape."""


EnumT = TypeVar("EnumT", bound=Enum)


def _record(
    value: Any,
    path: str,
    *,
    required: set[str],
    optional: set[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise RecordParseError(f"{path} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise RecordParseError(f"{path} has unknown fields: {', '.join(sorted(extra))}")
    return dict(value)


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    return dict(value)


def _identifiers(value: Any, path: str) -> dict[str, str]:
    identifiers = _mapping(value, path)
    if any(not isinstance(item, str) for item in identifiers.values()):
        raise RecordParseError(f"{path} values must be strings")
    return identifiers


def _enum(enum_type: type[EnumT], value: Any, path: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is not a valid {enum_type.__name__}") from exc


def _date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date string") from exc
    return parsed


def _datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO datetime string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO datetime string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecordParseError(f"{path} must include a timezone offset")
    return parsed


def _text_tuple(value: Any, path: str) -> tuple[str, ...]:
    values = _sequence(value, path)
    if any(not isinstance(item, str) for item in values):
        raise RecordParseError(f"{path} must contain only strings")
    return values


def source_reference_from_dict(value: Any, path: str = "source") -> SourceReference:
    data = _record(
        value,
        path,
        required={"source_id", "source_version", "locator"},
        optional={"content_hash"},
    )
    return SourceReference(
        source_id=data["source_id"],
        source_version=data["source_version"],
        locator=data["locator"],
        content_hash=data.get("content_hash"),
    )


def evidence_event_from_dict(value: Any, path: str = "evidence") -> EvidenceEvent:
    data = _record(
        value,
        path,
        required={
            "evidence_id",
            "stage",
            "subject",
            "predicate",
            "object_value",
            "source",
            "observed_at",
            "available_at",
        },
        optional={
            "relation",
            "direction",
            "biological_context",
            "confidence",
            "metadata",
        },
    )
    return EvidenceEvent(
        evidence_id=data["evidence_id"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        subject=data["subject"],
        predicate=data["predicate"],
        object_value=data["object_value"],
        source=source_reference_from_dict(data["source"], f"{path}.source"),
        observed_at=_date(data["observed_at"], f"{path}.observed_at"),
        available_at=_date(data["available_at"], f"{path}.available_at"),
        relation=_enum(
            EvidenceRelation,
            data.get("relation", EvidenceRelation.SUPPORTS.value),
            f"{path}.relation",
        ),
        direction=data.get("direction"),
        biological_context=_mapping(
            data.get("biological_context", {}), f"{path}.biological_context"
        ),
        confidence=data.get("confidence", 1.0),
        metadata=_mapping(data.get("metadata", {}), f"{path}.metadata"),
    )


def scientific_claim_from_dict(value: Any, path: str = "claim") -> ScientificClaim:
    data = _record(
        value,
        path,
        required={
            "claim_id",
            "stage",
            "subject",
            "predicate",
            "object_value",
            "disposition",
        },
        optional={
            "supporting_evidence",
            "contradicting_evidence",
            "confidence",
            "direction",
            "resolution_rationale",
            "biological_context",
        },
    )
    return ScientificClaim(
        claim_id=data["claim_id"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        subject=data["subject"],
        predicate=data["predicate"],
        object_value=data["object_value"],
        disposition=_enum(ClaimDisposition, data["disposition"], f"{path}.disposition"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        contradicting_evidence=_text_tuple(
            data.get("contradicting_evidence", []), f"{path}.contradicting_evidence"
        ),
        confidence=data.get("confidence", 0.0),
        direction=data.get("direction"),
        resolution_rationale=data.get("resolution_rationale"),
        biological_context=_mapping(
            data.get("biological_context", {}), f"{path}.biological_context"
        ),
    )


def disease_record_from_dict(value: Any, path: str = "disease") -> DiseaseRecord:
    data = _record(
        value,
        path,
        required={"disease_id", "name", "stage"},
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return DiseaseRecord(
        disease_id=data["disease_id"],
        name=data["name"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def candidate_record_from_dict(value: Any, path: str = "candidate") -> CandidateRecord:
    data = _record(
        value,
        path,
        required={"candidate_id", "name", "modality", "stage"},
        optional={"status", "attributes"},
    )
    return CandidateRecord(
        candidate_id=data["candidate_id"],
        name=data["name"],
        modality=data["modality"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        status=_enum(
            CandidateStatus,
            data.get("status", CandidateStatus.ACTIVE.value),
            f"{path}.status",
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def target_record_from_dict(value: Any, path: str = "target") -> TargetRecord:
    data = _record(
        value,
        path,
        required={"target_id", "symbol", "disease_id", "organism", "stage"},
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return TargetRecord(
        target_id=data["target_id"],
        symbol=data["symbol"],
        disease_id=data["disease_id"],
        organism=data["organism"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def assay_record_from_dict(value: Any, path: str = "assay") -> AssayRecord:
    data = _record(
        value,
        path,
        required={
            "assay_id",
            "name",
            "assay_type",
            "target_id",
            "disease_id",
            "organism",
            "stage",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return AssayRecord(
        assay_id=data["assay_id"],
        name=data["name"],
        assay_type=data["assay_type"],
        target_id=data["target_id"],
        disease_id=data["disease_id"],
        organism=data["organism"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def model_system_record_from_dict(
    value: Any,
    path: str = "model_system",
) -> ModelSystemRecord:
    data = _record(
        value,
        path,
        required={
            "model_system_id",
            "name",
            "model_type",
            "disease_id",
            "organism",
            "stage",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return ModelSystemRecord(
        model_system_id=data["model_system_id"],
        name=data["name"],
        model_type=data["model_type"],
        disease_id=data["disease_id"],
        organism=data["organism"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def intervention_record_from_dict(
    value: Any,
    path: str = "intervention",
) -> InterventionRecord:
    data = _record(
        value,
        path,
        required={
            "intervention_id",
            "name",
            "candidate_id",
            "disease_id",
            "modality",
            "stage",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return InterventionRecord(
        intervention_id=data["intervention_id"],
        name=data["name"],
        candidate_id=data["candidate_id"],
        disease_id=data["disease_id"],
        modality=data["modality"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_record_from_dict(value: Any, path: str = "trial") -> TrialRecord:
    data = _record(
        value,
        path,
        required={"trial_id", "registry", "intervention_id", "disease_id", "stage"},
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return TrialRecord(
        trial_id=data["trial_id"],
        registry=data["registry"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_arm_record_from_dict(
    value: Any,
    path: str = "trial_arm",
) -> TrialArmRecord:
    data = _record(
        value,
        path,
        required={"arm_id", "trial_id", "label", "arm_type", "role", "stage"},
        optional={
            "intervention_id",
            "intervention_names",
            "identifiers",
            "supporting_evidence",
            "attributes",
        },
    )
    return TrialArmRecord(
        arm_id=data["arm_id"],
        trial_id=data["trial_id"],
        label=data["label"],
        arm_type=data["arm_type"],
        role=_enum(TrialArmRole, data["role"], f"{path}.role"),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        intervention_id=data.get("intervention_id"),
        intervention_names=_text_tuple(
            data.get("intervention_names", []), f"{path}.intervention_names"
        ),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_population_record_from_dict(
    value: Any,
    path: str = "trial_population",
) -> TrialPopulationRecord:
    data = _record(
        value,
        path,
        required={
            "population_id",
            "trial_id",
            "disease_id",
            "description",
            "enrollment_count",
            "enrollment_type",
            "sex",
            "minimum_age",
            "healthy_volunteers",
            "stage",
        },
        optional={
            "maximum_age",
            "identifiers",
            "supporting_evidence",
            "attributes",
        },
    )
    return TrialPopulationRecord(
        population_id=data["population_id"],
        trial_id=data["trial_id"],
        disease_id=data["disease_id"],
        description=data["description"],
        enrollment_count=data["enrollment_count"],
        enrollment_type=data["enrollment_type"],
        sex=data["sex"],
        minimum_age=data["minimum_age"],
        healthy_volunteers=data["healthy_volunteers"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        maximum_age=data.get("maximum_age"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_endpoint_record_from_dict(
    value: Any,
    path: str = "trial_endpoint",
) -> TrialEndpointRecord:
    data = _record(
        value,
        path,
        required={
            "endpoint_id",
            "trial_id",
            "population_id",
            "name",
            "outcome_type",
            "time_frame",
            "parameter_type",
            "unit",
            "reporting_status",
            "arm_ids",
            "stage",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return TrialEndpointRecord(
        endpoint_id=data["endpoint_id"],
        trial_id=data["trial_id"],
        population_id=data["population_id"],
        name=data["name"],
        outcome_type=data["outcome_type"],
        time_frame=data["time_frame"],
        parameter_type=data["parameter_type"],
        unit=data["unit"],
        reporting_status=data["reporting_status"],
        arm_ids=_text_tuple(data["arm_ids"], f"{path}.arm_ids"),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_safety_arm_record_from_dict(
    value: Any,
    path: str = "trial_safety_arm",
) -> TrialSafetyArmRecord:
    data = _record(
        value,
        path,
        required={
            "safety_arm_id",
            "safety_id",
            "trial_id",
            "arm_id",
            "role",
            "source_group_id",
            "source_group_title",
            "serious_num_affected",
            "serious_num_at_risk",
            "stage",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return TrialSafetyArmRecord(
        safety_arm_id=data["safety_arm_id"],
        safety_id=data["safety_id"],
        trial_id=data["trial_id"],
        arm_id=data["arm_id"],
        role=_enum(TrialArmRole, data["role"], f"{path}.role"),
        source_group_id=data["source_group_id"],
        source_group_title=data["source_group_title"],
        serious_num_affected=data["serious_num_affected"],
        serious_num_at_risk=data["serious_num_at_risk"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_safety_record_from_dict(
    value: Any,
    path: str = "trial_safety",
) -> TrialSafetyRecord:
    data = _record(
        value,
        path,
        required={
            "safety_id",
            "trial_id",
            "event_category",
            "reporting_status",
            "time_frame",
            "event_term_count",
            "arm_summaries",
            "stage",
        },
        optional={"description", "identifiers", "supporting_evidence", "attributes"},
    )
    return TrialSafetyRecord(
        safety_id=data["safety_id"],
        trial_id=data["trial_id"],
        event_category=data["event_category"],
        reporting_status=data["reporting_status"],
        time_frame=data["time_frame"],
        event_term_count=data["event_term_count"],
        arm_summaries=tuple(
            trial_safety_arm_record_from_dict(
                item, f"{path}.arm_summaries[{index}]"
            )
            for index, item in enumerate(
                _sequence(data["arm_summaries"], f"{path}.arm_summaries")
            )
        ),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        description=data.get("description"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def trial_design_record_from_dict(
    value: Any,
    path: str = "trial_design",
) -> TrialDesignRecord:
    data = _record(
        value,
        path,
        required={
            "design_id",
            "trial_id",
            "intervention_id",
            "disease_id",
            "stage",
            "arms",
            "populations",
            "endpoints",
            "safety_records",
        },
        optional={"identifiers", "supporting_evidence", "attributes"},
    )
    return TrialDesignRecord(
        design_id=data["design_id"],
        trial_id=data["trial_id"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        arms=tuple(
            trial_arm_record_from_dict(item, f"{path}.arms[{index}]")
            for index, item in enumerate(_sequence(data["arms"], f"{path}.arms"))
        ),
        populations=tuple(
            trial_population_record_from_dict(
                item, f"{path}.populations[{index}]"
            )
            for index, item in enumerate(
                _sequence(data["populations"], f"{path}.populations")
            )
        ),
        endpoints=tuple(
            trial_endpoint_record_from_dict(item, f"{path}.endpoints[{index}]")
            for index, item in enumerate(
                _sequence(data["endpoints"], f"{path}.endpoints")
            )
        ),
        safety_records=tuple(
            trial_safety_record_from_dict(
                item, f"{path}.safety_records[{index}]"
            )
            for index, item in enumerate(
                _sequence(data["safety_records"], f"{path}.safety_records")
            )
        ),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def study_benefit_risk_record_from_dict(
    value: Any,
    path: str = "study_benefit_risk",
) -> StudyBenefitRiskRecord:
    data = _record(
        value,
        path,
        required={
            "study_record_id",
            "trial_id",
            "design_id",
            "endpoint_id",
            "safety_id",
            "endpoint_family",
            "effect_measure",
            "effect_estimate",
            "confidence_interval_percent",
            "confidence_interval_lower",
            "confidence_interval_upper",
            "candidate_measurement",
            "comparator_measurement",
            "measurement_unit",
            "endpoint_time_frame",
            "safety_time_frame",
            "candidate_serious_num_affected",
            "candidate_serious_num_at_risk",
            "comparator_serious_num_affected",
            "comparator_serious_num_at_risk",
            "candidate_serious_event_risk",
            "comparator_serious_event_risk",
            "serious_event_risk_difference",
            "benefit_direction",
            "safety_direction",
            "source_evidence_ids",
            "source_content_hashes",
            "stage",
        },
        optional={"identifiers", "attributes"},
    )
    return StudyBenefitRiskRecord(
        study_record_id=data["study_record_id"],
        trial_id=data["trial_id"],
        design_id=data["design_id"],
        endpoint_id=data["endpoint_id"],
        safety_id=data["safety_id"],
        endpoint_family=data["endpoint_family"],
        effect_measure=data["effect_measure"],
        effect_estimate=data["effect_estimate"],
        confidence_interval_percent=data["confidence_interval_percent"],
        confidence_interval_lower=data["confidence_interval_lower"],
        confidence_interval_upper=data["confidence_interval_upper"],
        candidate_measurement=data["candidate_measurement"],
        comparator_measurement=data["comparator_measurement"],
        measurement_unit=data["measurement_unit"],
        endpoint_time_frame=data["endpoint_time_frame"],
        safety_time_frame=data["safety_time_frame"],
        candidate_serious_num_affected=data["candidate_serious_num_affected"],
        candidate_serious_num_at_risk=data["candidate_serious_num_at_risk"],
        comparator_serious_num_affected=data["comparator_serious_num_affected"],
        comparator_serious_num_at_risk=data["comparator_serious_num_at_risk"],
        candidate_serious_event_risk=data["candidate_serious_event_risk"],
        comparator_serious_event_risk=data["comparator_serious_event_risk"],
        serious_event_risk_difference=data["serious_event_risk_difference"],
        benefit_direction=data["benefit_direction"],
        safety_direction=data["safety_direction"],
        source_evidence_ids=_text_tuple(
            data["source_evidence_ids"], f"{path}.source_evidence_ids"
        ),
        source_content_hashes=_text_tuple(
            data["source_content_hashes"], f"{path}.source_content_hashes"
        ),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def clinical_endpoint_binding_record_from_dict(
    value: Any,
    path: str = "clinical_endpoint_binding",
) -> ClinicalEndpointBindingRecord:
    data = _record(
        value,
        path,
        required={
            "trial_id",
            "design_id",
            "endpoint_id",
            "safety_id",
            "endpoint_fingerprint_sha256",
            "safety_fingerprint_sha256",
            "source_evidence_ids",
            "source_content_hashes",
        },
    )
    return ClinicalEndpointBindingRecord(
        trial_id=data["trial_id"],
        design_id=data["design_id"],
        endpoint_id=data["endpoint_id"],
        safety_id=data["safety_id"],
        endpoint_fingerprint_sha256=data["endpoint_fingerprint_sha256"],
        safety_fingerprint_sha256=data["safety_fingerprint_sha256"],
        source_evidence_ids=_text_tuple(
            data["source_evidence_ids"], f"{path}.source_evidence_ids"
        ),
        source_content_hashes=_text_tuple(
            data["source_content_hashes"], f"{path}.source_content_hashes"
        ),
    )


def clinical_endpoint_mapping_record_from_dict(
    value: Any,
    path: str = "clinical_endpoint_mapping",
) -> ClinicalEndpointMappingRecord:
    data = _record(
        value,
        path,
        required={
            "mapping_id",
            "portfolio_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_family_id",
            "endpoint_family_label",
            "ontology_system",
            "ontology_version",
            "ontology_code",
            "ontology_label",
            "effect_measure",
            "favorable_direction",
            "safety_measure",
            "bindings",
            "review_status",
            "reviewer_id",
            "reviewed_at",
            "source_evidence_ids",
            "source_content_hashes",
            "stage",
        },
        optional={"supporting_evidence", "identifiers", "attributes"},
    )
    return ClinicalEndpointMappingRecord(
        mapping_id=data["mapping_id"],
        portfolio_id=data["portfolio_id"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        endpoint_family_id=data["endpoint_family_id"],
        endpoint_family_label=data["endpoint_family_label"],
        ontology_system=data["ontology_system"],
        ontology_version=data["ontology_version"],
        ontology_code=data["ontology_code"],
        ontology_label=data["ontology_label"],
        effect_measure=data["effect_measure"],
        favorable_direction=data["favorable_direction"],
        safety_measure=data["safety_measure"],
        bindings=tuple(
            clinical_endpoint_binding_record_from_dict(
                item, f"{path}.bindings[{index}]"
            )
            for index, item in enumerate(
                _sequence(data["bindings"], f"{path}.bindings")
            )
        ),
        review_status=data["review_status"],
        reviewer_id=data["reviewer_id"],
        reviewed_at=_datetime(data["reviewed_at"], f"{path}.reviewed_at"),
        source_evidence_ids=_text_tuple(
            data["source_evidence_ids"], f"{path}.source_evidence_ids"
        ),
        source_content_hashes=_text_tuple(
            data["source_content_hashes"], f"{path}.source_content_hashes"
        ),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def benefit_risk_synthesis_record_from_dict(
    value: Any,
    path: str = "benefit_risk_synthesis",
) -> BenefitRiskSynthesisRecord:
    data = _record(
        value,
        path,
        required={
            "synthesis_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "safety_measure",
            "harmonization_policy_id",
            "studies",
            "pooling_method",
            "pooling_performed",
            "benefit_direction_consistent",
            "safety_direction_consistent",
            "source_disjoint",
            "clinical_acceptability_inferred",
            "source_evidence_ids",
            "source_content_hashes",
            "stage",
        },
        optional={"supporting_evidence", "identifiers", "attributes"},
    )
    return BenefitRiskSynthesisRecord(
        synthesis_id=data["synthesis_id"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        endpoint_mapping_id=data["endpoint_mapping_id"],
        endpoint_family=data["endpoint_family"],
        effect_measure=data["effect_measure"],
        safety_measure=data["safety_measure"],
        harmonization_policy_id=data["harmonization_policy_id"],
        studies=tuple(
            study_benefit_risk_record_from_dict(
                item, f"{path}.studies[{index}]"
            )
            for index, item in enumerate(
                _sequence(data["studies"], f"{path}.studies")
            )
        ),
        pooling_method=data["pooling_method"],
        pooling_performed=data["pooling_performed"],
        benefit_direction_consistent=data["benefit_direction_consistent"],
        safety_direction_consistent=data["safety_direction_consistent"],
        source_disjoint=data["source_disjoint"],
        clinical_acceptability_inferred=data["clinical_acceptability_inferred"],
        source_evidence_ids=_text_tuple(
            data["source_evidence_ids"], f"{path}.source_evidence_ids"
        ),
        source_content_hashes=_text_tuple(
            data["source_content_hashes"], f"{path}.source_content_hashes"
        ),
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        supporting_evidence=_text_tuple(
            data.get("supporting_evidence", []), f"{path}.supporting_evidence"
        ),
        identifiers=_identifiers(data.get("identifiers", {}), f"{path}.identifiers"),
        attributes=_mapping(data.get("attributes", {}), f"{path}.attributes"),
    )


def action_record_from_dict(value: Any, path: str = "action") -> ActionRecord:
    data = _record(
        value,
        path,
        required={"action_id", "action_type", "purpose"},
        optional={"cost", "evidence_ids", "metadata"},
    )
    return ActionRecord(
        action_id=data["action_id"],
        action_type=_enum(ActionType, data["action_type"], f"{path}.action_type"),
        purpose=data["purpose"],
        cost=data.get("cost", 0.0),
        evidence_ids=_text_tuple(data.get("evidence_ids", []), f"{path}.evidence_ids"),
        metadata=_mapping(data.get("metadata", {}), f"{path}.metadata"),
    )


def budget_state_from_dict(value: Any, path: str = "budget") -> BudgetState:
    data = _record(value, path, required={"limit"}, optional={"spent"})
    return BudgetState(limit=data["limit"], spent=data.get("spent", 0.0))


def verifier_result_from_dict(value: Any, path: str = "verifier") -> VerifierResult:
    data = _record(
        value,
        path,
        required={"verifier_id", "kind", "status", "code", "message", "stage"},
        optional={"blocking", "score", "details"},
    )
    return VerifierResult(
        verifier_id=data["verifier_id"],
        kind=_enum(VerifierKind, data["kind"], f"{path}.kind"),
        status=_enum(VerifierStatus, data["status"], f"{path}.status"),
        code=data["code"],
        message=data["message"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        blocking=data.get("blocking", False),
        score=data.get("score"),
        details=_mapping(data.get("details", {}), f"{path}.details"),
    )


def decision_record_from_dict(value: Any, path: str = "decision") -> DecisionRecord:
    data = _record(
        value,
        path,
        required={
            "packet_id",
            "decision",
            "stage_before",
            "stage_after",
            "status_after",
            "confidence",
            "rationale",
            "verifier_codes",
            "verifier_result_start",
            "verifier_result_count",
            "action_ids",
            "action_cost",
            "created_at",
        },
    )
    return DecisionRecord(
        packet_id=data["packet_id"],
        decision=_enum(Decision, data["decision"], f"{path}.decision"),
        stage_before=_enum(Stage, data["stage_before"], f"{path}.stage_before"),
        stage_after=_enum(Stage, data["stage_after"], f"{path}.stage_after"),
        status_after=_enum(ProgramStatus, data["status_after"], f"{path}.status_after"),
        confidence=data["confidence"],
        rationale=data["rationale"],
        verifier_codes=_text_tuple(data["verifier_codes"], f"{path}.verifier_codes"),
        verifier_result_start=data["verifier_result_start"],
        verifier_result_count=data["verifier_result_count"],
        action_ids=_text_tuple(data["action_ids"], f"{path}.action_ids"),
        action_cost=data["action_cost"],
        created_at=_datetime(data["created_at"], f"{path}.created_at"),
    )


def decision_packet_from_dict(value: Any, path: str = "packet") -> DecisionPacket:
    data = _record(
        value,
        path,
        required={
            "packet_id",
            "program_id",
            "expected_state_version",
            "stage",
            "decision",
            "rationale",
            "confidence",
            "created_at",
        },
        optional={
            "actions",
            "evidence_additions",
            "claim_updates",
            "disease_updates",
            "target_updates",
            "candidate_updates",
            "assay_updates",
            "model_system_updates",
            "intervention_updates",
            "trial_updates",
            "trial_design_updates",
            "clinical_endpoint_mapping_updates",
            "benefit_risk_synthesis_updates",
            "next_stage",
            "backtrack_stage",
            "metadata",
        },
    )
    return DecisionPacket(
        packet_id=data["packet_id"],
        program_id=data["program_id"],
        expected_state_version=data["expected_state_version"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        decision=_enum(Decision, data["decision"], f"{path}.decision"),
        rationale=data["rationale"],
        confidence=data["confidence"],
        actions=tuple(
            action_record_from_dict(item, f"{path}.actions[{index}]")
            for index, item in enumerate(
                _sequence(data.get("actions", []), f"{path}.actions")
            )
        ),
        evidence_additions=tuple(
            evidence_event_from_dict(item, f"{path}.evidence_additions[{index}]")
            for index, item in enumerate(
                _sequence(
                    data.get("evidence_additions", []), f"{path}.evidence_additions"
                )
            )
        ),
        claim_updates=tuple(
            scientific_claim_from_dict(item, f"{path}.claim_updates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("claim_updates", []), f"{path}.claim_updates")
            )
        ),
        disease_updates=tuple(
            disease_record_from_dict(item, f"{path}.disease_updates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("disease_updates", []), f"{path}.disease_updates")
            )
        ),
        target_updates=tuple(
            target_record_from_dict(item, f"{path}.target_updates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("target_updates", []), f"{path}.target_updates")
            )
        ),
        candidate_updates=tuple(
            candidate_record_from_dict(item, f"{path}.candidate_updates[{index}]")
            for index, item in enumerate(
                _sequence(
                    data.get("candidate_updates", []), f"{path}.candidate_updates"
                )
            )
        ),
        assay_updates=tuple(
            assay_record_from_dict(item, f"{path}.assay_updates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("assay_updates", []), f"{path}.assay_updates")
            )
        ),
        model_system_updates=tuple(
            model_system_record_from_dict(
                item, f"{path}.model_system_updates[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("model_system_updates", []),
                    f"{path}.model_system_updates",
                )
            )
        ),
        intervention_updates=tuple(
            intervention_record_from_dict(
                item, f"{path}.intervention_updates[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("intervention_updates", []),
                    f"{path}.intervention_updates",
                )
            )
        ),
        trial_updates=tuple(
            trial_record_from_dict(item, f"{path}.trial_updates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("trial_updates", []), f"{path}.trial_updates")
            )
        ),
        trial_design_updates=tuple(
            trial_design_record_from_dict(
                item, f"{path}.trial_design_updates[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("trial_design_updates", []),
                    f"{path}.trial_design_updates",
                )
            )
        ),
        clinical_endpoint_mapping_updates=tuple(
            clinical_endpoint_mapping_record_from_dict(
                item, f"{path}.clinical_endpoint_mapping_updates[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("clinical_endpoint_mapping_updates", []),
                    f"{path}.clinical_endpoint_mapping_updates",
                )
            )
        ),
        benefit_risk_synthesis_updates=tuple(
            benefit_risk_synthesis_record_from_dict(
                item, f"{path}.benefit_risk_synthesis_updates[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("benefit_risk_synthesis_updates", []),
                    f"{path}.benefit_risk_synthesis_updates",
                )
            )
        ),
        next_stage=(
            _enum(Stage, data["next_stage"], f"{path}.next_stage")
            if data.get("next_stage") is not None
            else None
        ),
        backtrack_stage=(
            _enum(Stage, data["backtrack_stage"], f"{path}.backtrack_stage")
            if data.get("backtrack_stage") is not None
            else None
        ),
        created_at=_datetime(data["created_at"], f"{path}.created_at"),
        metadata=_mapping(data.get("metadata", {}), f"{path}.metadata"),
    )


def program_state_from_dict(value: Any, path: str = "state") -> ProgramState:
    data = _record(
        value,
        path,
        required={
            "program_id",
            "disease",
            "therapeutic_hypothesis",
            "as_of_date",
            "current_stage",
            "budget",
        },
        optional={
            "target_product_profile",
            "evidence",
            "claims",
            "diseases",
            "targets",
            "candidates",
            "assays",
            "model_systems",
            "interventions",
            "trials",
            "trial_designs",
            "clinical_endpoint_mappings",
            "benefit_risk_syntheses",
            "action_history",
            "packet_history",
            "decision_history",
            "verifier_history",
            "status",
            "version",
        },
    )
    return ProgramState(
        program_id=data["program_id"],
        disease=data["disease"],
        therapeutic_hypothesis=data["therapeutic_hypothesis"],
        as_of_date=_date(data["as_of_date"], f"{path}.as_of_date"),
        current_stage=_enum(Stage, data["current_stage"], f"{path}.current_stage"),
        budget=budget_state_from_dict(data["budget"], f"{path}.budget"),
        target_product_profile=_mapping(
            data.get("target_product_profile", {}), f"{path}.target_product_profile"
        ),
        evidence=tuple(
            evidence_event_from_dict(item, f"{path}.evidence[{index}]")
            for index, item in enumerate(
                _sequence(data.get("evidence", []), f"{path}.evidence")
            )
        ),
        claims=tuple(
            scientific_claim_from_dict(item, f"{path}.claims[{index}]")
            for index, item in enumerate(
                _sequence(data.get("claims", []), f"{path}.claims")
            )
        ),
        diseases=tuple(
            disease_record_from_dict(item, f"{path}.diseases[{index}]")
            for index, item in enumerate(
                _sequence(data.get("diseases", []), f"{path}.diseases")
            )
        ),
        targets=tuple(
            target_record_from_dict(item, f"{path}.targets[{index}]")
            for index, item in enumerate(
                _sequence(data.get("targets", []), f"{path}.targets")
            )
        ),
        candidates=tuple(
            candidate_record_from_dict(item, f"{path}.candidates[{index}]")
            for index, item in enumerate(
                _sequence(data.get("candidates", []), f"{path}.candidates")
            )
        ),
        assays=tuple(
            assay_record_from_dict(item, f"{path}.assays[{index}]")
            for index, item in enumerate(
                _sequence(data.get("assays", []), f"{path}.assays")
            )
        ),
        model_systems=tuple(
            model_system_record_from_dict(item, f"{path}.model_systems[{index}]")
            for index, item in enumerate(
                _sequence(data.get("model_systems", []), f"{path}.model_systems")
            )
        ),
        interventions=tuple(
            intervention_record_from_dict(item, f"{path}.interventions[{index}]")
            for index, item in enumerate(
                _sequence(data.get("interventions", []), f"{path}.interventions")
            )
        ),
        trials=tuple(
            trial_record_from_dict(item, f"{path}.trials[{index}]")
            for index, item in enumerate(
                _sequence(data.get("trials", []), f"{path}.trials")
            )
        ),
        trial_designs=tuple(
            trial_design_record_from_dict(item, f"{path}.trial_designs[{index}]")
            for index, item in enumerate(
                _sequence(data.get("trial_designs", []), f"{path}.trial_designs")
            )
        ),
        clinical_endpoint_mappings=tuple(
            clinical_endpoint_mapping_record_from_dict(
                item, f"{path}.clinical_endpoint_mappings[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("clinical_endpoint_mappings", []),
                    f"{path}.clinical_endpoint_mappings",
                )
            )
        ),
        benefit_risk_syntheses=tuple(
            benefit_risk_synthesis_record_from_dict(
                item, f"{path}.benefit_risk_syntheses[{index}]"
            )
            for index, item in enumerate(
                _sequence(
                    data.get("benefit_risk_syntheses", []),
                    f"{path}.benefit_risk_syntheses",
                )
            )
        ),
        action_history=tuple(
            action_record_from_dict(item, f"{path}.action_history[{index}]")
            for index, item in enumerate(
                _sequence(data.get("action_history", []), f"{path}.action_history")
            )
        ),
        packet_history=tuple(
            decision_packet_from_dict(item, f"{path}.packet_history[{index}]")
            for index, item in enumerate(
                _sequence(data.get("packet_history", []), f"{path}.packet_history")
            )
        ),
        decision_history=tuple(
            decision_record_from_dict(item, f"{path}.decision_history[{index}]")
            for index, item in enumerate(
                _sequence(data.get("decision_history", []), f"{path}.decision_history")
            )
        ),
        verifier_history=tuple(
            verifier_result_from_dict(item, f"{path}.verifier_history[{index}]")
            for index, item in enumerate(
                _sequence(data.get("verifier_history", []), f"{path}.verifier_history")
            )
        ),
        status=_enum(
            ProgramStatus,
            data.get("status", ProgramStatus.ACTIVE.value),
            f"{path}.status",
        ),
        version=data.get("version", 0),
    )


def tool_request_from_dict(value: Any, path: str = "tool_request") -> ToolRequest:
    data = _record(
        value,
        path,
        required={
            "request_id",
            "program_id",
            "expected_state_version",
            "stage",
            "tool_id",
            "operation",
            "action_type",
            "purpose",
            "arguments",
            "max_cost",
            "created_at",
        },
        optional={"fingerprint"},
    )
    request = ToolRequest(
        request_id=data["request_id"],
        program_id=data["program_id"],
        expected_state_version=data["expected_state_version"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        tool_id=data["tool_id"],
        operation=data["operation"],
        action_type=_enum(ActionType, data["action_type"], f"{path}.action_type"),
        purpose=data["purpose"],
        arguments=_mapping(data["arguments"], f"{path}.arguments"),
        max_cost=data["max_cost"],
        created_at=_datetime(data["created_at"], f"{path}.created_at"),
    )
    if data.get("fingerprint") not in {None, request.fingerprint}:
        raise RecordParseError(f"{path}.fingerprint does not match the request content")
    return request


def tool_outcome_from_dict(value: Any, path: str = "tool_outcome") -> ToolOutcome:
    data = _record(
        value,
        path,
        required={
            "request",
            "contract_id",
            "status",
            "action_type",
            "payload",
            "cost",
            "execution_mode",
            "completed_at",
        },
        optional={"sources", "error_code", "message", "payload_sha256"},
    )
    outcome = ToolOutcome(
        request=tool_request_from_dict(data["request"], f"{path}.request"),
        contract_id=data["contract_id"],
        status=_enum(ToolStatus, data["status"], f"{path}.status"),
        action_type=_enum(ActionType, data["action_type"], f"{path}.action_type"),
        payload=_mapping(data["payload"], f"{path}.payload"),
        cost=data["cost"],
        execution_mode=_enum(
            ExecutionMode, data["execution_mode"], f"{path}.execution_mode"
        ),
        completed_at=_datetime(data["completed_at"], f"{path}.completed_at"),
        sources=tuple(
            source_reference_from_dict(item, f"{path}.sources[{index}]")
            for index, item in enumerate(
                _sequence(data.get("sources", []), f"{path}.sources")
            )
        ),
        error_code=data.get("error_code"),
        message=data.get("message", "Tool invocation completed."),
    )
    if data.get("payload_sha256") not in {None, outcome.payload_sha256}:
        raise RecordParseError(f"{path}.payload_sha256 does not match the payload")
    return outcome


def tool_execution_ledger_from_dict(
    value: Any,
    path: str = "tool_execution_ledger",
) -> ToolExecutionLedger:
    data = _record(value, path, required={"outcomes"})
    return ToolExecutionLedger(
        outcomes=tuple(
            tool_outcome_from_dict(item, f"{path}.outcomes[{index}]")
            for index, item in enumerate(
                _sequence(data["outcomes"], f"{path}.outcomes")
            )
        )
    )


@dataclass(frozen=True, slots=True)
class ReplayBundle(SerializableRecord):
    initial_state: ProgramState
    packets: tuple[DecisionPacket, ...]
    tool_execution_ledger: ToolExecutionLedger = ToolExecutionLedger()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_instance(self.initial_state, ProgramState, "initial_state")
        object.__setattr__(self, "packets", tuple(self.packets))
        for packet in self.packets:
            _require_instance(packet, DecisionPacket, "packets item")
        _require_instance(
            self.tool_execution_ledger,
            ToolExecutionLedger,
            "tool_execution_ledger",
        )
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        self.initial_state.validate_committed_history()
        self._validate_tool_links()

    def _validate_tool_links(self) -> None:
        outcomes = self.tool_execution_ledger.by_request_id
        packet_by_request: dict[str, str] = {}
        for packet in (*self.initial_state.packet_history, *self.packets):
            raw_request_ids = packet.metadata.get("tool_request_ids")
            action_by_request: dict[str, ActionRecord] = {}
            for action in packet.actions:
                request_id = action.metadata.get("tool_request_id")
                if request_id is None:
                    continue
                if not isinstance(request_id, str) or not request_id:
                    raise ValueError(
                        "tool-linked action request id must be a non-empty string"
                    )
                if request_id in action_by_request:
                    raise ValueError(
                        f"packet has duplicate tool-linked actions: {request_id}"
                    )
                action_by_request[request_id] = action

            if raw_request_ids is None:
                if action_by_request:
                    raise ValueError(
                        "tool-linked actions require packet tool_request_ids metadata"
                    )
                continue
            request_ids = _text_tuple(
                raw_request_ids,
                f"packet[{packet.packet_id}].metadata.tool_request_ids",
            )
            if len(request_ids) != len(set(request_ids)):
                raise ValueError("packet tool_request_ids must be unique")
            if set(action_by_request) != set(request_ids):
                raise ValueError(
                    "packet tool actions do not match tool_request_ids metadata"
                )
            raw_hashes = packet.metadata.get("tool_outcome_hashes")
            if not isinstance(raw_hashes, Mapping):
                raise ValueError(
                    "tool-linked packet requires tool_outcome_hashes metadata"
                )
            hashes = dict(raw_hashes)
            if set(hashes) != set(request_ids):
                raise ValueError(
                    "packet tool outcome hashes do not match tool_request_ids"
                )
            if packet.metadata.get("full_tool_payloads_external_to_packet") is not True:
                raise ValueError(
                    "tool-linked packet must keep full payloads in the execution ledger"
                )
            for request_id in request_ids:
                previous_packet = packet_by_request.get(request_id)
                if previous_packet is not None:
                    raise ValueError(
                        f"tool request is linked to multiple packets: {request_id} "
                        f"({previous_packet}, {packet.packet_id})"
                    )
                packet_by_request[request_id] = packet.packet_id

            evidence_by_request: dict[str, set[str]] = {
                request_id: set() for request_id in request_ids
            }
            evidence_records_by_request: dict[str, list[EvidenceEvent]] = {
                request_id: [] for request_id in request_ids
            }
            for evidence in packet.evidence_additions:
                request_id = evidence.metadata.get("tool_request_id")
                if request_id is None:
                    continue
                if request_id not in evidence_by_request:
                    raise ValueError(
                        f"packet evidence references undeclared tool request: {request_id}"
                    )
                evidence_by_request[request_id].add(evidence.evidence_id)
                evidence_records_by_request[request_id].append(evidence)

            for request_id in request_ids:
                outcome = outcomes.get(request_id)
                if outcome is None:
                    raise ValueError(
                        f"packet references missing tool outcome: {request_id}"
                    )
                request = outcome.request
                if (
                    request.program_id != packet.program_id
                    or request.expected_state_version != packet.expected_state_version
                    or request.stage is not packet.stage
                ):
                    raise ValueError(
                        f"tool outcome context does not match packet: {request_id}"
                    )
                if packet.created_at < outcome.completed_at:
                    raise ValueError(
                        f"packet predates linked tool outcome: {request_id}"
                    )
                if hashes[request_id] != outcome.payload_sha256:
                    raise ValueError(f"packet tool outcome hash mismatch: {request_id}")
                if (
                    evidence_records_by_request[request_id]
                    and outcome.status is not ToolStatus.SUCCEEDED
                ):
                    raise ValueError(
                        "tool evidence cannot originate from a non-successful "
                        f"outcome: {request_id}"
                    )

                action = action_by_request[request_id]
                if action.action_type is not outcome.action_type:
                    raise ValueError(f"tool action type mismatch: {request_id}")
                if action.purpose != request.purpose:
                    raise ValueError(f"tool action purpose mismatch: {request_id}")
                if not math.isclose(
                    float(action.cost),
                    float(outcome.cost),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError(f"tool action cost mismatch: {request_id}")
                expected_metadata = {
                    "tool_request_fingerprint": request.fingerprint,
                    "tool_contract_id": outcome.contract_id,
                    "tool_payload_sha256": outcome.payload_sha256,
                    "tool_status": outcome.status.value,
                    "execution_mode": outcome.execution_mode.value,
                    "completed_at": outcome.completed_at.isoformat(),
                    "error_code": outcome.error_code,
                }
                for key, expected in expected_metadata.items():
                    if action.metadata.get(key) != expected:
                        raise ValueError(
                            f"tool action metadata mismatch for {request_id}: {key}"
                        )
                if set(action.evidence_ids) != evidence_by_request[request_id]:
                    raise ValueError(
                        f"tool action evidence links mismatch: {request_id}"
                    )
                expected_evidence_metadata = {
                    "tool_request_fingerprint": request.fingerprint,
                    "tool_contract_id": outcome.contract_id,
                    "tool_payload_sha256": outcome.payload_sha256,
                    "execution_mode": outcome.execution_mode.value,
                }
                for evidence in evidence_records_by_request[request_id]:
                    for key, expected in expected_evidence_metadata.items():
                        if evidence.metadata.get(key) != expected:
                            raise ValueError(
                                f"tool evidence metadata mismatch for {request_id}: {key}"
                            )


@dataclass(frozen=True, slots=True)
class ReplayReport(SerializableRecord):
    initial_state: ProgramState
    final_state: ProgramState
    attempted_packets: tuple[DecisionPacket, ...]
    results: tuple[TransitionResult, ...]
    stopped_on_block: bool

    def __post_init__(self) -> None:
        _require_instance(self.initial_state, ProgramState, "initial_state")
        _require_instance(self.final_state, ProgramState, "final_state")
        object.__setattr__(self, "attempted_packets", tuple(self.attempted_packets))
        object.__setattr__(self, "results", tuple(self.results))
        for packet in self.attempted_packets:
            _require_instance(packet, DecisionPacket, "attempted_packets item")
        for result in self.results:
            _require_instance(result, TransitionResult, "results item")
        if len(self.attempted_packets) != len(self.results):
            raise ValueError("attempted_packets and results must have equal length")
        if not isinstance(self.stopped_on_block, bool):
            raise TypeError("stopped_on_block must be boolean")

    @property
    def accepted_count(self) -> int:
        return sum(item.applied for item in self.results)

    @property
    def blocked_count(self) -> int:
        return len(self.results) - self.accepted_count


def replay_bundle_from_dict(value: Any, path: str = "bundle") -> ReplayBundle:
    data = _record(
        value,
        path,
        required={"schema_version", "initial_state", "packets"},
        optional={"tool_execution_ledger"},
    )
    return ReplayBundle(
        initial_state=program_state_from_dict(
            data["initial_state"], f"{path}.initial_state"
        ),
        packets=tuple(
            decision_packet_from_dict(item, f"{path}.packets[{index}]")
            for index, item in enumerate(_sequence(data["packets"], f"{path}.packets"))
        ),
        tool_execution_ledger=tool_execution_ledger_from_dict(
            data.get("tool_execution_ledger", {"outcomes": []}),
            f"{path}.tool_execution_ledger",
        ),
        schema_version=data["schema_version"],
    )


def replay_bundle_from_json(text: str) -> ReplayBundle:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RecordParseError(f"bundle is not valid JSON: {exc}") from exc
    try:
        return replay_bundle_from_dict(value)
    except RecordParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"bundle contains invalid records: {exc}") from exc


def replay_bundle_to_json(bundle: ReplayBundle, *, indent: int = 2) -> str:
    _require_instance(bundle, ReplayBundle, "bundle")
    return (
        json.dumps(bundle.to_dict(), indent=indent, sort_keys=True, allow_nan=False)
        + "\n"
    )


def replay_program(
    bundle: ReplayBundle,
    *,
    environment: GatedDiscoveryEnvironment | None = None,
    stop_on_block: bool = True,
) -> ReplayReport:
    """Replay packets through the same verifier path used for live transitions."""

    _require_instance(bundle, ReplayBundle, "bundle")
    if not isinstance(stop_on_block, bool):
        raise TypeError("stop_on_block must be boolean")
    resolved_environment = environment or GatedDiscoveryEnvironment()
    if not isinstance(resolved_environment, GatedDiscoveryEnvironment):
        raise TypeError("environment must be a GatedDiscoveryEnvironment")
    state = bundle.initial_state
    packets: list[DecisionPacket] = []
    results: list[TransitionResult] = []
    stopped = False
    for packet in bundle.packets:
        result = resolved_environment.transition(state, packet)
        packets.append(packet)
        results.append(result)
        if result.applied:
            state = result.state
        elif stop_on_block:
            stopped = True
            break
    return ReplayReport(
        initial_state=bundle.initial_state,
        final_state=state,
        attempted_packets=tuple(packets),
        results=tuple(results),
        stopped_on_block=stopped,
    )
