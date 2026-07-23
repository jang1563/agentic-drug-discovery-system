"""Typed, serializable records for evidence-governed discovery programs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class Stage(str, Enum):
    DISEASE_CONTEXT = "disease_context"
    TARGET_NOMINATION = "target_nomination"
    MODALITY_SELECTION = "modality_selection"
    CANDIDATE_GENERATION = "candidate_generation"
    LEAD_OPTIMIZATION = "lead_optimization"
    PRECLINICAL_VALIDATION = "preclinical_validation"
    CLINICAL_STRATEGY = "clinical_strategy"
    REGULATORY_POSTMARKET = "regulatory_postmarket"


DEFAULT_STAGE_SEQUENCE = tuple(Stage)


class Decision(str, Enum):
    ADVANCE = "advance"
    HOLD = "hold"
    PIVOT = "pivot"
    KILL = "kill"
    DEFER = "defer"


class ProgramStatus(str, Enum):
    ACTIVE = "active"
    HELD = "held"
    DEFERRED = "deferred"
    TERMINATED = "terminated"
    COMPLETED = "completed"


class EvidenceRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUALIZES = "contextualizes"
    NEUTRAL = "neutral"


class ClaimDisposition(str, Enum):
    SUPPORTED = "supported"
    CONTESTED = "contested"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class CandidateStatus(str, Enum):
    ACTIVE = "active"
    HELD = "held"
    REJECTED = "rejected"
    SELECTED = "selected"


class TrialArmRole(str, Enum):
    CANDIDATE = "candidate"
    COMPARATOR = "comparator"


class ActionType(str, Enum):
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    QUERY_DATABASE = "query_database"
    RUN_SFM = "run_sfm"
    RUN_STRUCTURE_TOOL = "run_structure_tool"
    SCORE_CANDIDATE = "score_candidate"
    EDIT_CANDIDATE = "edit_candidate"
    RUN_VERIFIER = "run_verifier"


class VerifierKind(str, Enum):
    DETERMINISTIC = "deterministic"
    SOFT = "soft"


class VerifierStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_probability(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")


def _require_sha256(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if len(value) != 64 or value != value.lower():
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest") from exc


def _require_instance(value: Any, expected: type[Any], field_name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be {expected.__name__}")


def _require_date(value: Any, field_name: str) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a date")


def _freeze_json(value: Any, path: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain non-finite floats")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{path}[]") for item in value)
    raise TypeError(
        f"{path} must contain JSON-compatible values, got {type(value).__name__}"
    )


def _ensure_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")


def _freeze_text_tuple(
    values: Any,
    field_name: str,
    *,
    unique: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    try:
        frozen = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of strings") from exc
    for value in frozen:
        _require_text(value, field_name)
    if unique:
        _ensure_unique(frozen, field_name)
    return frozen


def _freeze_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return _freeze_json(value, field_name)


def _freeze_identifiers(value: Any, field_name: str = "identifiers") -> Mapping[str, str]:
    frozen = _freeze_mapping(value, field_name)
    for namespace, identifier in frozen.items():
        _require_text(namespace, "identifier namespace")
        _require_text(identifier, f"identifier value for {namespace}")
    return frozen


def to_primitive(value: Any) -> Any:
    """Convert model values into JSON-serializable Python primitives."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_primitive(getattr(value, item.name)) for item in fields(value)
        }
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"cannot serialize {type(value).__name__}")


class SerializableRecord:
    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class SourceReference(SerializableRecord):
    source_id: str
    source_version: str
    locator: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.source_version, "source_version")
        _require_text(self.locator, "locator")
        if self.content_hash is not None:
            _require_text(self.content_hash, "content_hash")


@dataclass(frozen=True, slots=True)
class EvidenceEvent(SerializableRecord):
    evidence_id: str
    stage: Stage
    subject: str
    predicate: str
    object_value: str
    source: SourceReference
    observed_at: date
    available_at: date
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS
    direction: str | None = None
    biological_context: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.source, SourceReference, "source")
        _require_instance(self.relation, EvidenceRelation, "relation")
        _require_date(self.observed_at, "observed_at")
        _require_date(self.available_at, "available_at")
        for field_name in ("evidence_id", "subject", "predicate", "object_value"):
            _require_text(getattr(self, field_name), field_name)
        if self.direction is not None:
            _require_text(self.direction, "direction")
        if self.available_at < self.observed_at:
            raise ValueError("available_at cannot precede observed_at")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(
            self,
            "biological_context",
            _freeze_mapping(self.biological_context, "biological_context"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    def is_visible_at(self, cutoff: date) -> bool:
        return self.available_at <= cutoff


@dataclass(frozen=True, slots=True)
class ScientificClaim(SerializableRecord):
    claim_id: str
    stage: Stage
    subject: str
    predicate: str
    object_value: str
    disposition: ClaimDisposition
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    direction: str | None = None
    resolution_rationale: str | None = None
    biological_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.disposition, ClaimDisposition, "disposition")
        for field_name in ("claim_id", "subject", "predicate", "object_value"):
            _require_text(getattr(self, field_name), field_name)
        if self.direction is not None:
            _require_text(self.direction, "direction")
        if self.resolution_rationale is not None:
            _require_text(self.resolution_rationale, "resolution_rationale")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self,
            "contradicting_evidence",
            _freeze_text_tuple(self.contradicting_evidence, "contradicting_evidence"),
        )
        object.__setattr__(
            self,
            "biological_context",
            _freeze_mapping(self.biological_context, "biological_context"),
        )


@dataclass(frozen=True, slots=True)
class DiseaseRecord(SerializableRecord):
    """Canonical disease identity used across every discovery stage."""

    disease_id: str
    name: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in ("disease_id", "name"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class CandidateRecord(SerializableRecord):
    candidate_id: str
    name: str
    modality: str
    stage: Stage
    status: CandidateStatus = CandidateStatus.ACTIVE
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.status, CandidateStatus, "status")
        for field_name in ("candidate_id", "name", "modality"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TargetRecord(SerializableRecord):
    """Canonical target identity with evidence-backed namespace bindings."""

    target_id: str
    symbol: str
    disease_id: str
    organism: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in ("target_id", "symbol", "disease_id", "organism"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class AssayRecord(SerializableRecord):
    """Canonical assay identity linked to one target and disease context."""

    assay_id: str
    name: str
    assay_type: str
    target_id: str
    disease_id: str
    organism: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "assay_id",
            "name",
            "assay_type",
            "target_id",
            "disease_id",
            "organism",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class ModelSystemRecord(SerializableRecord):
    """Canonical experimental model identity for disease-effect evidence."""

    model_system_id: str
    name: str
    model_type: str
    disease_id: str
    organism: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "model_system_id",
            "name",
            "model_type",
            "disease_id",
            "organism",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class InterventionRecord(SerializableRecord):
    """Canonical clinical intervention linked to one discovery candidate."""

    intervention_id: str
    name: str
    candidate_id: str
    disease_id: str
    modality: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "intervention_id",
            "name",
            "candidate_id",
            "disease_id",
            "modality",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialRecord(SerializableRecord):
    """Canonical registered trial linked to an accepted clinical intervention."""

    trial_id: str
    registry: str
    intervention_id: str
    disease_id: str
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in ("trial_id", "registry", "intervention_id", "disease_id"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialArmRecord(SerializableRecord):
    """Canonical protocol/result arm within one registered trial."""

    arm_id: str
    trial_id: str
    label: str
    arm_type: str
    role: TrialArmRole
    stage: Stage
    intervention_id: str | None = None
    intervention_names: tuple[str, ...] = ()
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.role, TrialArmRole, "role")
        for field_name in ("arm_id", "trial_id", "label", "arm_type"):
            _require_text(getattr(self, field_name), field_name)
        if self.intervention_id is not None:
            _require_text(self.intervention_id, "intervention_id")
        object.__setattr__(
            self,
            "intervention_names",
            _freeze_text_tuple(self.intervention_names, "intervention_names"),
        )
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialPopulationRecord(SerializableRecord):
    """Canonical analysis population and bounded eligibility summary."""

    population_id: str
    trial_id: str
    disease_id: str
    description: str
    enrollment_count: int
    enrollment_type: str
    sex: str
    minimum_age: str
    healthy_volunteers: bool
    stage: Stage
    maximum_age: str | None = None
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "population_id",
            "trial_id",
            "disease_id",
            "description",
            "enrollment_type",
            "sex",
            "minimum_age",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.maximum_age is not None:
            _require_text(self.maximum_age, "maximum_age")
        if (
            not isinstance(self.enrollment_count, int)
            or isinstance(self.enrollment_count, bool)
            or self.enrollment_count <= 0
        ):
            raise ValueError("enrollment_count must be a positive integer")
        if not isinstance(self.healthy_volunteers, bool):
            raise TypeError("healthy_volunteers must be a boolean")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialEndpointRecord(SerializableRecord):
    """Canonical posted endpoint linked to exact trial arms and population."""

    endpoint_id: str
    trial_id: str
    population_id: str
    name: str
    outcome_type: str
    time_frame: str
    parameter_type: str
    unit: str
    reporting_status: str
    arm_ids: tuple[str, ...]
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "endpoint_id",
            "trial_id",
            "population_id",
            "name",
            "outcome_type",
            "time_frame",
            "parameter_type",
            "unit",
            "reporting_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(
            self, "arm_ids", _freeze_text_tuple(self.arm_ids, "arm_ids")
        )
        if len(self.arm_ids) < 2:
            raise ValueError("arm_ids must contain at least two canonical arms")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialSafetyArmRecord(SerializableRecord):
    """Posted serious-adverse-event summary linked to one canonical trial arm."""

    safety_arm_id: str
    safety_id: str
    trial_id: str
    arm_id: str
    role: TrialArmRole
    source_group_id: str
    source_group_title: str
    serious_num_affected: int
    serious_num_at_risk: int
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.role, TrialArmRole, "role")
        for field_name in (
            "safety_arm_id",
            "safety_id",
            "trial_id",
            "arm_id",
            "source_group_id",
            "source_group_title",
        ):
            _require_text(getattr(self, field_name), field_name)
        if (
            not isinstance(self.serious_num_affected, int)
            or isinstance(self.serious_num_affected, bool)
            or self.serious_num_affected < 0
        ):
            raise ValueError("serious_num_affected must be a non-negative integer")
        if (
            not isinstance(self.serious_num_at_risk, int)
            or isinstance(self.serious_num_at_risk, bool)
            or self.serious_num_at_risk <= 0
        ):
            raise ValueError("serious_num_at_risk must be a positive integer")
        if self.serious_num_affected > self.serious_num_at_risk:
            raise ValueError("serious_num_affected cannot exceed serious_num_at_risk")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialSafetyRecord(SerializableRecord):
    """Atomic posted safety summary compiled from one exact registry snapshot."""

    safety_id: str
    trial_id: str
    event_category: str
    reporting_status: str
    time_frame: str
    event_term_count: int
    arm_summaries: tuple[TrialSafetyArmRecord, ...]
    stage: Stage
    description: str | None = None
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "safety_id",
            "trial_id",
            "event_category",
            "reporting_status",
            "time_frame",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.description is not None:
            _require_text(self.description, "description")
        if (
            not isinstance(self.event_term_count, int)
            or isinstance(self.event_term_count, bool)
            or self.event_term_count < 0
        ):
            raise ValueError("event_term_count must be a non-negative integer")
        summaries = tuple(self.arm_summaries)
        object.__setattr__(self, "arm_summaries", summaries)
        if len(summaries) < 2:
            raise ValueError("arm_summaries must contain at least two arms")
        for summary in summaries:
            _require_instance(summary, TrialSafetyArmRecord, "arm_summaries item")
            if (
                summary.safety_id != self.safety_id
                or summary.trial_id != self.trial_id
                or summary.stage is not self.stage
            ):
                raise ValueError(
                    "arm_summaries must match the safety record identity and stage"
                )
        _ensure_unique(
            tuple(item.safety_arm_id for item in summaries),
            "trial safety arm summary ids",
        )
        _ensure_unique(
            tuple(item.arm_id for item in summaries),
            "trial safety canonical arm ids",
        )
        _ensure_unique(
            tuple(item.source_group_id for item in summaries),
            "trial safety source group ids",
        )
        if {item.role for item in summaries} != {
            TrialArmRole.CANDIDATE,
            TrialArmRole.COMPARATOR,
        }:
            raise ValueError("trial safety must include candidate and comparator arms")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class TrialDesignRecord(SerializableRecord):
    """Atomic clinical design identity compiled from one exact registry snapshot."""

    design_id: str
    trial_id: str
    intervention_id: str
    disease_id: str
    stage: Stage
    arms: tuple[TrialArmRecord, ...]
    populations: tuple[TrialPopulationRecord, ...]
    endpoints: tuple[TrialEndpointRecord, ...]
    safety_records: tuple[TrialSafetyRecord, ...]
    identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_evidence: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in ("design_id", "trial_id", "intervention_id", "disease_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name, expected in (
            ("arms", TrialArmRecord),
            ("populations", TrialPopulationRecord),
            ("endpoints", TrialEndpointRecord),
            ("safety_records", TrialSafetyRecord),
        ):
            values = tuple(getattr(self, field_name))
            object.__setattr__(self, field_name, values)
            if not values:
                raise ValueError(f"{field_name} must not be empty")
            for value in values:
                _require_instance(value, expected, f"{field_name} item")
                if value.trial_id != self.trial_id or value.stage is not self.stage:
                    raise ValueError(
                        f"{field_name} items must match the design trial and stage"
                    )
        _ensure_unique(tuple(item.arm_id for item in self.arms), "trial design arm ids")
        _ensure_unique(
            tuple(item.population_id for item in self.populations),
            "trial design population ids",
        )
        _ensure_unique(
            tuple(item.endpoint_id for item in self.endpoints),
            "trial design endpoint ids",
        )
        _ensure_unique(
            tuple(item.safety_id for item in self.safety_records),
            "trial design safety ids",
        )
        arm_ids = {item.arm_id for item in self.arms}
        population_ids = {item.population_id for item in self.populations}
        if {item.role for item in self.arms} != {
            TrialArmRole.CANDIDATE,
            TrialArmRole.COMPARATOR,
        }:
            raise ValueError("trial design must include candidate and comparator arms")
        for arm in self.arms:
            if (
                arm.role is TrialArmRole.CANDIDATE
                and arm.intervention_id != self.intervention_id
            ):
                raise ValueError("candidate arm must link the canonical intervention")
            if (
                arm.role is TrialArmRole.COMPARATOR
                and arm.intervention_id == self.intervention_id
            ):
                raise ValueError("comparator arm cannot link the canonical intervention")
        for endpoint in self.endpoints:
            if endpoint.population_id not in population_ids:
                raise ValueError("trial endpoint references an unknown population")
            if not set(endpoint.arm_ids).issubset(arm_ids):
                raise ValueError("trial endpoint references an unknown arm")
        arm_roles = {item.arm_id: item.role for item in self.arms}
        for safety in self.safety_records:
            if {item.arm_id for item in safety.arm_summaries} != arm_ids:
                raise ValueError("trial safety must cover every canonical design arm")
            if any(
                arm_roles.get(item.arm_id) is not item.role
                for item in safety.arm_summaries
            ):
                raise ValueError("trial safety arm role conflicts with the design")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class ClinicalEndpointBindingRecord(SerializableRecord):
    """Exact trial endpoint and safety identities approved for one family."""

    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str
    endpoint_fingerprint_sha256: str
    safety_fingerprint_sha256: str
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("trial_id", "design_id", "endpoint_id", "safety_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "endpoint_fingerprint_sha256",
            "safety_fingerprint_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        object.__setattr__(
            self,
            "source_evidence_ids",
            _freeze_text_tuple(self.source_evidence_ids, "source_evidence_ids"),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _freeze_text_tuple(self.source_content_hashes, "source_content_hashes"),
        )
        if not self.source_evidence_ids or not self.source_content_hashes:
            raise ValueError("endpoint binding requires source-pinned evidence")
        if self.source_evidence_ids != tuple(sorted(self.source_evidence_ids)):
            raise ValueError("source_evidence_ids must use canonical sorted order")
        if self.source_content_hashes != tuple(sorted(self.source_content_hashes)):
            raise ValueError("source_content_hashes must use canonical sorted order")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")


@dataclass(frozen=True, slots=True)
class ClinicalEndpointMappingRecord(SerializableRecord):
    """Reviewer-approved ontology mapping bound to exact trial ledger records."""

    mapping_id: str
    portfolio_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_family_id: str
    endpoint_family_label: str
    ontology_system: str
    ontology_version: str
    ontology_code: str
    ontology_label: str
    effect_measure: str
    favorable_direction: str
    safety_measure: str
    bindings: tuple[ClinicalEndpointBindingRecord, ...]
    review_status: str
    reviewer_id: str
    reviewed_at: datetime
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    stage: Stage
    supporting_evidence: tuple[str, ...] = ()
    identifiers: Mapping[str, str] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.reviewed_at, datetime, "reviewed_at")
        for field_name in (
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
            "review_status",
            "reviewer_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.stage is not Stage.REGULATORY_POSTMARKET:
            raise ValueError("endpoint mapping is limited to regulatory_postmarket")
        if self.review_status != "approved":
            raise ValueError("endpoint mapping review_status must be approved")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        bindings = tuple(self.bindings)
        object.__setattr__(self, "bindings", bindings)
        if len(bindings) < 2:
            raise ValueError("endpoint mapping requires at least two trial bindings")
        for binding in bindings:
            _require_instance(binding, ClinicalEndpointBindingRecord, "bindings item")
        for field_name, values in (
            ("trial ids", tuple(item.trial_id for item in bindings)),
            ("design ids", tuple(item.design_id for item in bindings)),
            ("endpoint ids", tuple(item.endpoint_id for item in bindings)),
            ("safety ids", tuple(item.safety_id for item in bindings)),
        ):
            _ensure_unique(values, field_name)
        binding_hash_sets = [set(item.source_content_hashes) for item in bindings]
        for index, values in enumerate(binding_hash_sets):
            if any(values & other for other in binding_hash_sets[index + 1 :]):
                raise ValueError("endpoint mapping trial sources must be disjoint")
        expected_evidence = tuple(
            sorted(
                {
                    evidence_id
                    for binding in bindings
                    for evidence_id in binding.source_evidence_ids
                }
            )
        )
        expected_hashes = tuple(
            sorted(
                {
                    digest
                    for binding in bindings
                    for digest in binding.source_content_hashes
                }
            )
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            _freeze_text_tuple(self.source_evidence_ids, "source_evidence_ids"),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _freeze_text_tuple(self.source_content_hashes, "source_content_hashes"),
        )
        if self.source_evidence_ids != expected_evidence:
            raise ValueError("source_evidence_ids must equal the binding union")
        if self.source_content_hashes != expected_hashes:
            raise ValueError("source_content_hashes must equal the binding union")
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        source_count = len(self.source_evidence_ids)
        if self.supporting_evidence[:source_count] != self.source_evidence_ids:
            raise ValueError(
                "supporting_evidence must begin with canonical source evidence ids"
            )
        if len(self.supporting_evidence) > source_count + 1:
            raise ValueError(
                "supporting_evidence permits at most one derived mapping event"
            )
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class StudyBenefitRiskRecord(SerializableRecord):
    """Harmonized trial-level benefit and serious-event values without pooling."""

    study_record_id: str
    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str
    endpoint_family: str
    effect_measure: str
    effect_estimate: float
    confidence_interval_percent: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    candidate_measurement: float
    comparator_measurement: float
    measurement_unit: str
    endpoint_time_frame: str
    safety_time_frame: str
    candidate_serious_num_affected: int
    candidate_serious_num_at_risk: int
    comparator_serious_num_affected: int
    comparator_serious_num_at_risk: int
    candidate_serious_event_risk: float
    comparator_serious_event_risk: float
    serious_event_risk_difference: float
    benefit_direction: str
    safety_direction: str
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    stage: Stage
    identifiers: Mapping[str, str] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "study_record_id",
            "trial_id",
            "design_id",
            "endpoint_id",
            "safety_id",
            "endpoint_family",
            "effect_measure",
            "measurement_unit",
            "endpoint_time_frame",
            "safety_time_frame",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "effect_estimate",
            "confidence_interval_percent",
            "confidence_interval_lower",
            "confidence_interval_upper",
            "candidate_measurement",
            "comparator_measurement",
            "candidate_serious_event_risk",
            "comparator_serious_event_risk",
            "serious_event_risk_difference",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
        if self.effect_estimate <= 0:
            raise ValueError("effect_estimate must be positive")
        if not 0 < self.confidence_interval_percent <= 100:
            raise ValueError("confidence_interval_percent must be in (0, 100]")
        if not (
            0 < self.confidence_interval_lower
            <= self.effect_estimate
            <= self.confidence_interval_upper
        ):
            raise ValueError("confidence interval must contain the effect estimate")
        for field_name in (
            "candidate_serious_num_affected",
            "candidate_serious_num_at_risk",
            "comparator_serious_num_affected",
            "comparator_serious_num_at_risk",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.candidate_serious_num_at_risk <= 0:
            raise ValueError("candidate_serious_num_at_risk must be positive")
        if self.comparator_serious_num_at_risk <= 0:
            raise ValueError("comparator_serious_num_at_risk must be positive")
        if self.candidate_serious_num_affected > self.candidate_serious_num_at_risk:
            raise ValueError("candidate serious-event count exceeds number at risk")
        if self.comparator_serious_num_affected > self.comparator_serious_num_at_risk:
            raise ValueError("comparator serious-event count exceeds number at risk")
        expected_candidate_risk = (
            self.candidate_serious_num_affected
            / self.candidate_serious_num_at_risk
        )
        expected_comparator_risk = (
            self.comparator_serious_num_affected
            / self.comparator_serious_num_at_risk
        )
        if not math.isclose(
            self.candidate_serious_event_risk,
            expected_candidate_risk,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("candidate_serious_event_risk does not match raw counts")
        if not math.isclose(
            self.comparator_serious_event_risk,
            expected_comparator_risk,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("comparator_serious_event_risk does not match raw counts")
        if not math.isclose(
            self.serious_event_risk_difference,
            expected_candidate_risk - expected_comparator_risk,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("serious_event_risk_difference does not match raw counts")
        if self.benefit_direction not in {
            "benefit",
            "harm",
            "null_or_uncertain",
        }:
            raise ValueError("benefit_direction is not recognized")
        if self.safety_direction not in {
            "lower_observed_serious_event_risk",
            "higher_observed_serious_event_risk",
            "equal_observed_serious_event_risk",
        }:
            raise ValueError("safety_direction is not recognized")
        object.__setattr__(
            self,
            "source_evidence_ids",
            _freeze_text_tuple(self.source_evidence_ids, "source_evidence_ids"),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _freeze_text_tuple(self.source_content_hashes, "source_content_hashes"),
        )
        if not self.source_evidence_ids or not self.source_content_hashes:
            raise ValueError("source evidence ids and content hashes must not be empty")
        _ensure_unique(self.source_evidence_ids, "study source evidence ids")
        _ensure_unique(self.source_content_hashes, "study source content hashes")
        if self.source_content_hashes != tuple(sorted(self.source_content_hashes)):
            raise ValueError("source_content_hashes must use canonical sorted order")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class BenefitRiskSynthesisRecord(SerializableRecord):
    """Source-disjoint descriptive synthesis with no clinical acceptability claim."""

    synthesis_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    effect_measure: str
    safety_measure: str
    harmonization_policy_id: str
    studies: tuple[StudyBenefitRiskRecord, ...]
    pooling_method: str
    pooling_performed: bool
    benefit_direction_consistent: bool
    safety_direction_consistent: bool
    source_disjoint: bool
    clinical_acceptability_inferred: bool
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    stage: Stage
    supporting_evidence: tuple[str, ...] = ()
    identifiers: Mapping[str, str] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "synthesis_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "safety_measure",
            "harmonization_policy_id",
            "pooling_method",
        ):
            _require_text(getattr(self, field_name), field_name)
        studies = tuple(self.studies)
        object.__setattr__(self, "studies", studies)
        if len(studies) < 2:
            raise ValueError("studies must contain at least two trials")
        for study in studies:
            _require_instance(study, StudyBenefitRiskRecord, "studies item")
            if (
                study.endpoint_family != self.endpoint_family
                or study.effect_measure != self.effect_measure
                or study.stage is not self.stage
            ):
                raise ValueError("study harmonization dimensions must match synthesis")
        for field_name, values in (
            ("study record ids", tuple(item.study_record_id for item in studies)),
            ("study trial ids", tuple(item.trial_id for item in studies)),
            ("study design ids", tuple(item.design_id for item in studies)),
            ("study endpoint ids", tuple(item.endpoint_id for item in studies)),
            ("study safety ids", tuple(item.safety_id for item in studies)),
        ):
            _ensure_unique(values, field_name)
        if self.pooling_method != "none" or self.pooling_performed:
            raise ValueError("automatic cross-trial pooling is not permitted")
        for field_name in (
            "benefit_direction_consistent",
            "safety_direction_consistent",
            "source_disjoint",
            "clinical_acceptability_inferred",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        if not self.source_disjoint:
            raise ValueError("synthesis requires source-disjoint trial records")
        if self.clinical_acceptability_inferred:
            raise ValueError("clinical acceptability cannot be inferred by synthesis")
        expected_benefit_consistency = len(
            {item.benefit_direction for item in studies}
        ) == 1
        expected_safety_consistency = len(
            {item.safety_direction for item in studies}
        ) == 1
        if self.benefit_direction_consistent != expected_benefit_consistency:
            raise ValueError("benefit_direction_consistent does not match studies")
        if self.safety_direction_consistent != expected_safety_consistency:
            raise ValueError("safety_direction_consistent does not match studies")
        study_hash_sets = [set(item.source_content_hashes) for item in studies]
        for index, values in enumerate(study_hash_sets):
            if any(values & other for other in study_hash_sets[index + 1 :]):
                raise ValueError("study source content hashes are not disjoint")
        expected_evidence = tuple(
            sorted(
                {
                    evidence_id
                    for study in studies
                    for evidence_id in study.source_evidence_ids
                }
            )
        )
        expected_hashes = tuple(
            sorted(
                {
                    digest
                    for study in studies
                    for digest in study.source_content_hashes
                }
            )
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            _freeze_text_tuple(self.source_evidence_ids, "source_evidence_ids"),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _freeze_text_tuple(self.source_content_hashes, "source_content_hashes"),
        )
        if self.source_evidence_ids != expected_evidence:
            raise ValueError("source_evidence_ids must equal the canonical study union")
        if self.source_content_hashes != expected_hashes:
            raise ValueError("source_content_hashes must equal the canonical study union")
        object.__setattr__(
            self,
            "supporting_evidence",
            _freeze_text_tuple(self.supporting_evidence, "supporting_evidence"),
        )
        if not set(self.source_evidence_ids).issubset(self.supporting_evidence):
            raise ValueError("supporting_evidence must retain every source evidence id")
        _ensure_unique(self.supporting_evidence, "synthesis supporting evidence ids")
        source_count = len(self.source_evidence_ids)
        if self.supporting_evidence[:source_count] != self.source_evidence_ids:
            raise ValueError(
                "supporting_evidence must begin with canonical source evidence ids"
            )
        if len(self.supporting_evidence) > source_count + 1:
            raise ValueError(
                "supporting_evidence permits at most one derived synthesis event"
            )
        object.__setattr__(self, "identifiers", _freeze_identifiers(self.identifiers))
        object.__setattr__(
            self, "attributes", _freeze_mapping(self.attributes, "attributes")
        )


@dataclass(frozen=True, slots=True)
class ActionRecord(SerializableRecord):
    action_id: str
    action_type: ActionType
    purpose: str
    cost: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.action_type, ActionType, "action_type")
        _require_text(self.action_id, "action_id")
        _require_text(self.purpose, "purpose")
        if not isinstance(self.cost, (int, float)) or isinstance(self.cost, bool):
            raise TypeError("cost must be numeric")
        if not math.isfinite(float(self.cost)) or self.cost < 0:
            raise ValueError("cost must be finite and non-negative")
        object.__setattr__(
            self,
            "evidence_ids",
            _freeze_text_tuple(self.evidence_ids, "evidence_ids"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class BudgetState(SerializableRecord):
    limit: float
    spent: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("limit", "spent"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if self.spent > self.limit:
            raise ValueError("spent cannot exceed limit")

    @property
    def remaining(self) -> float:
        return self.limit - self.spent

    def can_afford(self, cost: float) -> bool:
        return cost <= self.remaining + 1e-12

    def charge(self, cost: float) -> "BudgetState":
        if not self.can_afford(cost):
            raise ValueError("cost exceeds remaining budget")
        return replace(self, spent=self.spent + cost)


@dataclass(frozen=True, slots=True)
class VerifierResult(SerializableRecord):
    verifier_id: str
    kind: VerifierKind
    status: VerifierStatus
    code: str
    message: str
    stage: Stage
    blocking: bool = False
    score: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.kind, VerifierKind, "kind")
        _require_instance(self.status, VerifierStatus, "status")
        _require_instance(self.stage, Stage, "stage")
        for field_name in ("verifier_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        if self.score is not None:
            _require_probability(self.score, "score")
        if self.blocking and self.status is not VerifierStatus.FAIL:
            raise ValueError("blocking verifier results must have fail status")
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


@dataclass(frozen=True, slots=True)
class DecisionRecord(SerializableRecord):
    packet_id: str
    decision: Decision
    stage_before: Stage
    stage_after: Stage
    status_after: ProgramStatus
    confidence: float
    rationale: str
    verifier_codes: tuple[str, ...]
    verifier_result_start: int
    verifier_result_count: int
    action_ids: tuple[str, ...]
    action_cost: float
    created_at: datetime

    def __post_init__(self) -> None:
        _require_instance(self.decision, Decision, "decision")
        _require_instance(self.stage_before, Stage, "stage_before")
        _require_instance(self.stage_after, Stage, "stage_after")
        _require_instance(self.status_after, ProgramStatus, "status_after")
        _require_instance(self.created_at, datetime, "created_at")
        _require_text(self.packet_id, "packet_id")
        _require_text(self.rationale, "rationale")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(
            self,
            "verifier_codes",
            _freeze_text_tuple(self.verifier_codes, "verifier_codes", unique=False),
        )
        if (
            not isinstance(self.verifier_result_start, int)
            or isinstance(self.verifier_result_start, bool)
            or self.verifier_result_start < 0
        ):
            raise ValueError("verifier_result_start must be a non-negative integer")
        if (
            not isinstance(self.verifier_result_count, int)
            or isinstance(self.verifier_result_count, bool)
            or self.verifier_result_count < 1
        ):
            raise ValueError("verifier_result_count must be a positive integer")
        object.__setattr__(
            self,
            "action_ids",
            _freeze_text_tuple(self.action_ids, "action_ids"),
        )
        if not isinstance(self.action_cost, (int, float)) or isinstance(
            self.action_cost, bool
        ):
            raise TypeError("action_cost must be numeric")
        if not math.isfinite(float(self.action_cost)) or self.action_cost < 0:
            raise ValueError("action_cost must be finite and non-negative")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ProgramState(SerializableRecord):
    program_id: str
    disease: str
    therapeutic_hypothesis: str
    as_of_date: date
    current_stage: Stage
    budget: BudgetState
    target_product_profile: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[EvidenceEvent, ...] = ()
    claims: tuple[ScientificClaim, ...] = ()
    diseases: tuple[DiseaseRecord, ...] = ()
    targets: tuple[TargetRecord, ...] = ()
    candidates: tuple[CandidateRecord, ...] = ()
    assays: tuple[AssayRecord, ...] = ()
    model_systems: tuple[ModelSystemRecord, ...] = ()
    interventions: tuple[InterventionRecord, ...] = ()
    trials: tuple[TrialRecord, ...] = ()
    trial_designs: tuple[TrialDesignRecord, ...] = ()
    clinical_endpoint_mappings: tuple[ClinicalEndpointMappingRecord, ...] = ()
    benefit_risk_syntheses: tuple[BenefitRiskSynthesisRecord, ...] = ()
    action_history: tuple[ActionRecord, ...] = ()
    packet_history: tuple[DecisionPacket, ...] = ()
    decision_history: tuple[DecisionRecord, ...] = ()
    verifier_history: tuple[VerifierResult, ...] = ()
    status: ProgramStatus = ProgramStatus.ACTIVE
    version: int = 0

    def __post_init__(self) -> None:
        _require_date(self.as_of_date, "as_of_date")
        _require_instance(self.current_stage, Stage, "current_stage")
        _require_instance(self.budget, BudgetState, "budget")
        _require_instance(self.status, ProgramStatus, "status")
        for field_name in ("program_id", "disease", "therapeutic_hypothesis"):
            _require_text(getattr(self, field_name), field_name)
        if (
            not isinstance(self.version, int)
            or isinstance(self.version, bool)
            or self.version < 0
        ):
            raise ValueError("version must be a non-negative integer")
        object.__setattr__(
            self,
            "target_product_profile",
            _freeze_mapping(self.target_product_profile, "target_product_profile"),
        )
        for field_name in (
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
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for item in self.evidence:
            _require_instance(item, EvidenceEvent, "evidence item")
        for item in self.claims:
            _require_instance(item, ScientificClaim, "claim item")
        for item in self.diseases:
            _require_instance(item, DiseaseRecord, "disease item")
        for item in self.targets:
            _require_instance(item, TargetRecord, "target item")
        for item in self.candidates:
            _require_instance(item, CandidateRecord, "candidate item")
        for item in self.assays:
            _require_instance(item, AssayRecord, "assay item")
        for item in self.model_systems:
            _require_instance(item, ModelSystemRecord, "model_system item")
        for item in self.interventions:
            _require_instance(item, InterventionRecord, "intervention item")
        for item in self.trials:
            _require_instance(item, TrialRecord, "trial item")
        for item in self.trial_designs:
            _require_instance(item, TrialDesignRecord, "trial_design item")
        for item in self.clinical_endpoint_mappings:
            _require_instance(
                item,
                ClinicalEndpointMappingRecord,
                "clinical_endpoint_mapping item",
            )
        for item in self.benefit_risk_syntheses:
            _require_instance(
                item,
                BenefitRiskSynthesisRecord,
                "benefit_risk_synthesis item",
            )
        for item in self.action_history:
            _require_instance(item, ActionRecord, "action_history item")
        for item in self.packet_history:
            _require_instance(item, DecisionPacket, "packet_history item")
        for item in self.decision_history:
            _require_instance(item, DecisionRecord, "decision_history item")
        for item in self.verifier_history:
            _require_instance(item, VerifierResult, "verifier_history item")
        _ensure_unique(
            tuple(item.evidence_id for item in self.evidence), "evidence ids"
        )
        _ensure_unique(tuple(item.claim_id for item in self.claims), "claim ids")
        _ensure_unique(tuple(item.disease_id for item in self.diseases), "disease ids")
        _ensure_unique(tuple(item.target_id for item in self.targets), "target ids")
        _ensure_unique(
            tuple(item.candidate_id for item in self.candidates), "candidate ids"
        )
        _ensure_unique(tuple(item.assay_id for item in self.assays), "assay ids")
        _ensure_unique(
            tuple(item.model_system_id for item in self.model_systems),
            "model system ids",
        )
        _ensure_unique(
            tuple(item.intervention_id for item in self.interventions),
            "intervention ids",
        )
        _ensure_unique(tuple(item.trial_id for item in self.trials), "trial ids")
        _ensure_unique(
            tuple(item.design_id for item in self.trial_designs), "trial design ids"
        )
        _ensure_unique(
            tuple(item.mapping_id for item in self.clinical_endpoint_mappings),
            "clinical endpoint mapping ids",
        )
        _ensure_unique(
            tuple(item.synthesis_id for item in self.benefit_risk_syntheses),
            "benefit-risk synthesis ids",
        )
        _ensure_unique(
            tuple(item.action_id for item in self.action_history), "action ids"
        )
        _ensure_unique(
            tuple(item.packet_id for item in self.packet_history), "packet history ids"
        )
        _ensure_unique(
            tuple(item.packet_id for item in self.decision_history), "packet ids"
        )
        if len(self.packet_history) != len(self.decision_history):
            raise ValueError("packet and decision histories must have equal length")
        if self.version != len(self.decision_history):
            raise ValueError(
                "state version must equal the number of accepted decisions"
            )
        actions_by_id = {item.action_id: item for item in self.action_history}
        referenced_action_ids: list[str] = []
        verifier_cursor = 0
        previous_decision: DecisionRecord | None = None
        for index, (packet, decision) in enumerate(
            zip(self.packet_history, self.decision_history, strict=True)
        ):
            if packet.program_id != self.program_id:
                raise ValueError(
                    f"packet history program_id mismatch: {packet.packet_id}"
                )
            if packet.expected_state_version != index:
                raise ValueError(
                    f"packet history state version mismatch: {packet.packet_id}"
                )
            if packet.packet_id != decision.packet_id:
                raise ValueError("packet and decision histories are out of alignment")
            if (
                packet.decision is not decision.decision
                or packet.stage is not decision.stage_before
            ):
                raise ValueError(
                    f"decision summary does not match packet: {packet.packet_id}"
                )
            if (
                previous_decision is not None
                and decision.stage_before is not previous_decision.stage_after
            ):
                raise ValueError(
                    f"decision stage history is not contiguous: {packet.packet_id}"
                )
            if (
                previous_decision is not None
                and decision.created_at < previous_decision.created_at
            ):
                raise ValueError(
                    f"decision timestamps are not monotonic: {packet.packet_id}"
                )
            if packet.rationale != decision.rationale or not math.isclose(
                float(packet.confidence),
                float(decision.confidence),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"decision rationale or confidence mismatch: {packet.packet_id}"
                )
            if packet.created_at != decision.created_at:
                raise ValueError(
                    f"decision timestamp does not match packet: {packet.packet_id}"
                )
            packet_action_ids = tuple(item.action_id for item in packet.actions)
            if packet_action_ids != decision.action_ids or not math.isclose(
                packet.action_cost,
                float(decision.action_cost),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"decision action summary does not match packet: {packet.packet_id}"
                )
            missing_action_ids = set(decision.action_ids) - set(actions_by_id)
            if missing_action_ids:
                missing = ", ".join(sorted(missing_action_ids))
                raise ValueError(f"decision references unknown action ids: {missing}")
            for action in packet.actions:
                if actions_by_id[action.action_id] != action:
                    raise ValueError(
                        f"action history does not match packet: {action.action_id}"
                    )
            recorded_cost = sum(
                float(actions_by_id[item].cost) for item in decision.action_ids
            )
            if not math.isclose(
                recorded_cost,
                float(decision.action_cost),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"decision action_cost does not match action ledger: {decision.packet_id}"
                )
            referenced_action_ids.extend(decision.action_ids)
            if decision.verifier_result_start != verifier_cursor:
                raise ValueError(
                    f"decision verifier segment is not contiguous: {decision.packet_id}"
                )
            verifier_end = verifier_cursor + decision.verifier_result_count
            verifier_segment = self.verifier_history[verifier_cursor:verifier_end]
            if len(verifier_segment) != decision.verifier_result_count:
                raise ValueError(
                    f"decision verifier segment exceeds verifier history: {decision.packet_id}"
                )
            if tuple(item.code for item in verifier_segment) != decision.verifier_codes:
                raise ValueError(
                    f"decision verifier codes do not match verifier history: {decision.packet_id}"
                )
            verifier_cursor = verifier_end
            previous_decision = decision
        _ensure_unique(tuple(referenced_action_ids), "decision action ids")
        unreferenced_actions = set(actions_by_id) - set(referenced_action_ids)
        if unreferenced_actions:
            missing = ", ".join(sorted(unreferenced_actions))
            raise ValueError(
                f"action ledger contains unreferenced action ids: {missing}"
            )
        if verifier_cursor != len(self.verifier_history):
            raise ValueError(
                "verifier history contains results not linked to a decision"
            )
        if previous_decision is not None:
            if self.current_stage is not previous_decision.stage_after:
                raise ValueError(
                    "current stage does not match the last accepted decision"
                )
            if self.status is not previous_decision.status_after:
                raise ValueError(
                    "program status does not match the last accepted decision"
                )
        recorded_spend = sum(float(item.action_cost) for item in self.decision_history)
        if not math.isclose(
            recorded_spend,
            float(self.budget.spent),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("budget spent does not match the decision action ledger")

    def validate_committed_history(self) -> None:
        """Check that accepted packet replay agrees with committed content ledgers."""

        replayed_evidence: dict[str, EvidenceEvent] = {}
        replayed_claims: dict[str, ScientificClaim] = {}
        replayed_diseases: dict[str, DiseaseRecord] = {}
        replayed_targets: dict[str, TargetRecord] = {}
        replayed_candidates: dict[str, CandidateRecord] = {}
        replayed_assays: dict[str, AssayRecord] = {}
        replayed_model_systems: dict[str, ModelSystemRecord] = {}
        replayed_interventions: dict[str, InterventionRecord] = {}
        replayed_trials: dict[str, TrialRecord] = {}
        replayed_trial_designs: dict[str, TrialDesignRecord] = {}
        replayed_clinical_endpoint_mappings: dict[
            str, ClinicalEndpointMappingRecord
        ] = {}
        replayed_benefit_risk_syntheses: dict[
            str, BenefitRiskSynthesisRecord
        ] = {}
        for packet in self.packet_history:
            for evidence in packet.evidence_additions:
                if evidence.evidence_id in replayed_evidence:
                    raise ValueError(
                        f"evidence id is added by multiple packets: {evidence.evidence_id}"
                    )
                replayed_evidence[evidence.evidence_id] = evidence
            replayed_claims.update(
                {item.claim_id: item for item in packet.claim_updates}
            )
            replayed_diseases.update(
                {item.disease_id: item for item in packet.disease_updates}
            )
            replayed_targets.update(
                {item.target_id: item for item in packet.target_updates}
            )
            replayed_candidates.update(
                {item.candidate_id: item for item in packet.candidate_updates}
            )
            replayed_assays.update(
                {item.assay_id: item for item in packet.assay_updates}
            )
            replayed_model_systems.update(
                {
                    item.model_system_id: item
                    for item in packet.model_system_updates
                }
            )
            replayed_interventions.update(
                {
                    item.intervention_id: item
                    for item in packet.intervention_updates
                }
            )
            replayed_trials.update(
                {item.trial_id: item for item in packet.trial_updates}
            )
            replayed_trial_designs.update(
                {item.design_id: item for item in packet.trial_design_updates}
            )
            replayed_clinical_endpoint_mappings.update(
                {
                    item.mapping_id: item
                    for item in packet.clinical_endpoint_mapping_updates
                }
            )
            replayed_benefit_risk_syntheses.update(
                {
                    item.synthesis_id: item
                    for item in packet.benefit_risk_synthesis_updates
                }
            )

        current_evidence = self.evidence_by_id
        current_claims = self.claims_by_id
        current_diseases = self.diseases_by_id
        current_targets = self.targets_by_id
        current_candidates = self.candidates_by_id
        current_assays = self.assays_by_id
        current_model_systems = self.model_systems_by_id
        current_interventions = self.interventions_by_id
        current_trials = self.trials_by_id
        current_trial_designs = self.trial_designs_by_id
        current_clinical_endpoint_mappings = self.clinical_endpoint_mappings_by_id
        current_benefit_risk_syntheses = self.benefit_risk_syntheses_by_id
        for evidence_id, evidence in replayed_evidence.items():
            if current_evidence.get(evidence_id) != evidence:
                raise ValueError(
                    f"evidence ledger does not match packet replay: {evidence_id}"
                )
        for claim_id, claim in replayed_claims.items():
            if current_claims.get(claim_id) != claim:
                raise ValueError(
                    f"claim ledger does not match packet replay: {claim_id}"
                )
        for disease_id, disease in replayed_diseases.items():
            if current_diseases.get(disease_id) != disease:
                raise ValueError(
                    f"disease ledger does not match packet replay: {disease_id}"
                )
        for target_id, target in replayed_targets.items():
            if current_targets.get(target_id) != target:
                raise ValueError(
                    f"target ledger does not match packet replay: {target_id}"
                )
        for candidate_id, candidate in replayed_candidates.items():
            if current_candidates.get(candidate_id) != candidate:
                raise ValueError(
                    f"candidate ledger does not match packet replay: {candidate_id}"
                )
        for assay_id, assay in replayed_assays.items():
            if current_assays.get(assay_id) != assay:
                raise ValueError(f"assay ledger does not match packet replay: {assay_id}")
        for model_system_id, model_system in replayed_model_systems.items():
            if current_model_systems.get(model_system_id) != model_system:
                raise ValueError(
                    "model-system ledger does not match packet replay: "
                    f"{model_system_id}"
                )
        for intervention_id, intervention in replayed_interventions.items():
            if current_interventions.get(intervention_id) != intervention:
                raise ValueError(
                    "intervention ledger does not match packet replay: "
                    f"{intervention_id}"
                )
        for trial_id, trial in replayed_trials.items():
            if current_trials.get(trial_id) != trial:
                raise ValueError(
                    f"trial ledger does not match packet replay: {trial_id}"
                )
        for design_id, design in replayed_trial_designs.items():
            if current_trial_designs.get(design_id) != design:
                raise ValueError(
                    f"trial-design ledger does not match packet replay: {design_id}"
                )
        for mapping_id, mapping in replayed_clinical_endpoint_mappings.items():
            if current_clinical_endpoint_mappings.get(mapping_id) != mapping:
                raise ValueError(
                    "clinical endpoint mapping ledger does not match packet replay: "
                    f"{mapping_id}"
                )
        for synthesis_id, synthesis in replayed_benefit_risk_syntheses.items():
            if current_benefit_risk_syntheses.get(synthesis_id) != synthesis:
                raise ValueError(
                    "benefit-risk synthesis ledger does not match packet replay: "
                    f"{synthesis_id}"
                )

    @property
    def is_terminal(self) -> bool:
        return self.status in {ProgramStatus.COMPLETED, ProgramStatus.TERMINATED}

    @property
    def evidence_by_id(self) -> dict[str, EvidenceEvent]:
        return {item.evidence_id: item for item in self.evidence}

    @property
    def claims_by_id(self) -> dict[str, ScientificClaim]:
        return {item.claim_id: item for item in self.claims}

    @property
    def diseases_by_id(self) -> dict[str, DiseaseRecord]:
        return {item.disease_id: item for item in self.diseases}

    @property
    def targets_by_id(self) -> dict[str, TargetRecord]:
        return {item.target_id: item for item in self.targets}

    @property
    def candidates_by_id(self) -> dict[str, CandidateRecord]:
        return {item.candidate_id: item for item in self.candidates}

    @property
    def assays_by_id(self) -> dict[str, AssayRecord]:
        return {item.assay_id: item for item in self.assays}

    @property
    def model_systems_by_id(self) -> dict[str, ModelSystemRecord]:
        return {item.model_system_id: item for item in self.model_systems}

    @property
    def interventions_by_id(self) -> dict[str, InterventionRecord]:
        return {item.intervention_id: item for item in self.interventions}

    @property
    def trials_by_id(self) -> dict[str, TrialRecord]:
        return {item.trial_id: item for item in self.trials}

    @property
    def trial_designs_by_id(self) -> dict[str, TrialDesignRecord]:
        return {item.design_id: item for item in self.trial_designs}

    @property
    def clinical_endpoint_mappings_by_id(
        self,
    ) -> dict[str, ClinicalEndpointMappingRecord]:
        return {item.mapping_id: item for item in self.clinical_endpoint_mappings}

    @property
    def benefit_risk_syntheses_by_id(
        self,
    ) -> dict[str, BenefitRiskSynthesisRecord]:
        return {item.synthesis_id: item for item in self.benefit_risk_syntheses}

    @property
    def actions_by_id(self) -> dict[str, ActionRecord]:
        return {item.action_id: item for item in self.action_history}


@dataclass(frozen=True, slots=True)
class DecisionPacket(SerializableRecord):
    packet_id: str
    program_id: str
    expected_state_version: int
    stage: Stage
    decision: Decision
    rationale: str
    confidence: float
    actions: tuple[ActionRecord, ...] = ()
    evidence_additions: tuple[EvidenceEvent, ...] = ()
    claim_updates: tuple[ScientificClaim, ...] = ()
    disease_updates: tuple[DiseaseRecord, ...] = ()
    target_updates: tuple[TargetRecord, ...] = ()
    candidate_updates: tuple[CandidateRecord, ...] = ()
    assay_updates: tuple[AssayRecord, ...] = ()
    model_system_updates: tuple[ModelSystemRecord, ...] = ()
    intervention_updates: tuple[InterventionRecord, ...] = ()
    trial_updates: tuple[TrialRecord, ...] = ()
    trial_design_updates: tuple[TrialDesignRecord, ...] = ()
    clinical_endpoint_mapping_updates: tuple[ClinicalEndpointMappingRecord, ...] = ()
    benefit_risk_synthesis_updates: tuple[BenefitRiskSynthesisRecord, ...] = ()
    next_stage: Stage | None = None
    backtrack_stage: Stage | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.decision, Decision, "decision")
        if self.next_stage is not None:
            _require_instance(self.next_stage, Stage, "next_stage")
        if self.backtrack_stage is not None:
            _require_instance(self.backtrack_stage, Stage, "backtrack_stage")
        _require_instance(self.created_at, datetime, "created_at")
        for field_name in ("packet_id", "program_id", "rationale"):
            _require_text(getattr(self, field_name), field_name)
        if (
            not isinstance(self.expected_state_version, int)
            or isinstance(self.expected_state_version, bool)
            or self.expected_state_version < 0
        ):
            raise ValueError("expected_state_version must be a non-negative integer")
        _require_probability(self.confidence, "confidence")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        for field_name in (
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
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for item in self.actions:
            _require_instance(item, ActionRecord, "action item")
        for item in self.evidence_additions:
            _require_instance(item, EvidenceEvent, "evidence_addition item")
        for item in self.claim_updates:
            _require_instance(item, ScientificClaim, "claim_update item")
        for item in self.disease_updates:
            _require_instance(item, DiseaseRecord, "disease_update item")
        for item in self.target_updates:
            _require_instance(item, TargetRecord, "target_update item")
        for item in self.candidate_updates:
            _require_instance(item, CandidateRecord, "candidate_update item")
        for item in self.assay_updates:
            _require_instance(item, AssayRecord, "assay_update item")
        for item in self.model_system_updates:
            _require_instance(item, ModelSystemRecord, "model_system_update item")
        for item in self.intervention_updates:
            _require_instance(item, InterventionRecord, "intervention_update item")
        for item in self.trial_updates:
            _require_instance(item, TrialRecord, "trial_update item")
        for item in self.trial_design_updates:
            _require_instance(item, TrialDesignRecord, "trial_design_update item")
        for item in self.clinical_endpoint_mapping_updates:
            _require_instance(
                item,
                ClinicalEndpointMappingRecord,
                "clinical_endpoint_mapping_update item",
            )
        for item in self.benefit_risk_synthesis_updates:
            _require_instance(
                item,
                BenefitRiskSynthesisRecord,
                "benefit_risk_synthesis_update item",
            )
        _ensure_unique(tuple(item.action_id for item in self.actions), "action ids")
        _ensure_unique(
            tuple(item.evidence_id for item in self.evidence_additions),
            "evidence addition ids",
        )
        _ensure_unique(
            tuple(item.claim_id for item in self.claim_updates), "claim update ids"
        )
        _ensure_unique(
            tuple(item.disease_id for item in self.disease_updates),
            "disease update ids",
        )
        _ensure_unique(
            tuple(item.target_id for item in self.target_updates), "target update ids"
        )
        _ensure_unique(
            tuple(item.candidate_id for item in self.candidate_updates),
            "candidate update ids",
        )
        _ensure_unique(
            tuple(item.assay_id for item in self.assay_updates), "assay update ids"
        )
        _ensure_unique(
            tuple(item.model_system_id for item in self.model_system_updates),
            "model system update ids",
        )
        _ensure_unique(
            tuple(item.intervention_id for item in self.intervention_updates),
            "intervention update ids",
        )
        _ensure_unique(
            tuple(item.trial_id for item in self.trial_updates),
            "trial update ids",
        )
        _ensure_unique(
            tuple(item.design_id for item in self.trial_design_updates),
            "trial design update ids",
        )
        _ensure_unique(
            tuple(item.mapping_id for item in self.clinical_endpoint_mapping_updates),
            "clinical endpoint mapping update ids",
        )
        _ensure_unique(
            tuple(item.synthesis_id for item in self.benefit_risk_synthesis_updates),
            "benefit-risk synthesis update ids",
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def action_cost(self) -> float:
        return sum(float(item.cost) for item in self.actions)


@dataclass(frozen=True, slots=True)
class StageGate(SerializableRecord):
    stage: Stage
    required_claim_predicates: tuple[str, ...] = ()
    required_evidence_predicates: tuple[str, ...] = ()
    required_target_identifier_namespaces: tuple[str, ...] = ()
    minimum_evidence_events: int = 1
    minimum_independent_sources: int = 0
    require_source_content_hashes: bool = False
    minimum_viable_candidates: int = 0
    minimum_disease_records: int = 0
    minimum_assay_records: int = 0
    minimum_model_system_records: int = 0
    minimum_intervention_records: int = 0
    minimum_trial_records: int = 0
    minimum_trial_design_records: int = 0
    minimum_benefit_risk_synthesis_records: int = 0
    minimum_confidence: float = 0.0

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        object.__setattr__(
            self,
            "required_claim_predicates",
            _freeze_text_tuple(
                self.required_claim_predicates, "required_claim_predicates"
            ),
        )
        object.__setattr__(
            self,
            "required_evidence_predicates",
            _freeze_text_tuple(
                self.required_evidence_predicates, "required_evidence_predicates"
            ),
        )
        object.__setattr__(
            self,
            "required_target_identifier_namespaces",
            _freeze_text_tuple(
                self.required_target_identifier_namespaces,
                "required_target_identifier_namespaces",
            ),
        )
        if (
            not isinstance(self.minimum_evidence_events, int)
            or isinstance(self.minimum_evidence_events, bool)
            or self.minimum_evidence_events < 0
        ):
            raise ValueError("minimum_evidence_events must be a non-negative integer")
        if (
            not isinstance(self.minimum_independent_sources, int)
            or isinstance(self.minimum_independent_sources, bool)
            or self.minimum_independent_sources < 0
        ):
            raise ValueError(
                "minimum_independent_sources must be a non-negative integer"
            )
        if not isinstance(self.require_source_content_hashes, bool):
            raise TypeError("require_source_content_hashes must be a boolean")
        if (
            not isinstance(self.minimum_viable_candidates, int)
            or isinstance(self.minimum_viable_candidates, bool)
            or self.minimum_viable_candidates < 0
        ):
            raise ValueError("minimum_viable_candidates must be a non-negative integer")
        for field_name in (
            "minimum_disease_records",
            "minimum_assay_records",
            "minimum_model_system_records",
            "minimum_intervention_records",
            "minimum_trial_records",
            "minimum_trial_design_records",
            "minimum_benefit_risk_synthesis_records",
        ):
            value = getattr(self, field_name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer")
        _require_probability(self.minimum_confidence, "minimum_confidence")


@dataclass(frozen=True, slots=True)
class TransitionResult(SerializableRecord):
    applied: bool
    state: ProgramState
    packet: DecisionPacket
    verifier_results: tuple[VerifierResult, ...]
    reason: str

    def __post_init__(self) -> None:
        _require_instance(self.state, ProgramState, "state")
        _require_instance(self.packet, DecisionPacket, "packet")
        object.__setattr__(self, "verifier_results", tuple(self.verifier_results))
        for item in self.verifier_results:
            _require_instance(item, VerifierResult, "verifier_result item")
        _require_text(self.reason, "reason")

    @property
    def blocking_results(self) -> tuple[VerifierResult, ...]:
        return tuple(item for item in self.verifier_results if item.blocking)
