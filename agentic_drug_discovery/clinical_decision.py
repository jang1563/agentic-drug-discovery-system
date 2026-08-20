"""Provenance-preserving clinical evidence tensors and bounded VOI planning."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from .clinical_effects import (
    ratio_benefit_direction,
    ratio_effect_favorable_direction,
)
from .clinical_synthesis import validate_benefit_risk_synthesis
from .models import (
    ActionType,
    BenefitRiskSynthesisRecord,
    BudgetState,
    Decision,
    ProgramState,
    SerializableRecord,
    Stage,
    StudyBenefitRiskRecord,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_date,
    _require_instance,
    _require_probability,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_DECISION_PACKAGE_SCHEMA_VERSION = "adds.clinical-evidence-decision-package.v1"
CLINICAL_EVIDENCE_TENSOR_METHOD_ID = (
    "adds.provenance-preserving-clinical-evidence-tensor.v1"
)
BOUNDED_VOI_METHOD_ID = "adds.bounded-voi-priority.v1"
CLINICAL_WORKFLOW_SCOPE = "evidence_workflow_only"

_ALLOWED_ACTION_TYPES = {
    ActionType.RETRIEVE_EVIDENCE,
    ActionType.QUERY_DATABASE,
    ActionType.RUN_VERIFIER,
}
_REQUIRED_LIMITATIONS = (
    (
        "ADVANCE means that preregistered evidence-workflow criteria are "
        "satisfied; it is not a treatment, regulatory, or clinical "
        "acceptability recommendation."
    ),
    (
        "Serious-event risk differences are unadjusted posted aggregate "
        "comparisons and do not establish causality."
    ),
    (
        "Bounded VOI is a deterministic prioritization heuristic based on "
        "declared gap mass, resolution probability, decision relevance, and "
        "cost; it is not calibrated economic value of information."
    ),
    (
        "No cross-trial pooling, population-homogeneity inference, or "
        "clinical benefit-risk score is performed."
    ),
)


class ClinicalDecisionError(ValueError):
    """Raised when a clinical decision package cannot be compiled safely."""


class ClinicalEvidenceDimension(str, Enum):
    SOURCE_INDEPENDENCE = "source_independence"
    TRIAL_COUNT = "trial_count"
    BENEFIT_DIRECTION = "benefit_direction"
    BENEFIT_PRECISION = "benefit_precision"
    DESCRIPTIVE_ARM_MEASUREMENT_COMPLETENESS = (
        "descriptive_arm_measurement_completeness"
    )
    SAFETY_DIRECTION = "safety_direction"
    SAFETY_EXPOSURE = "safety_exposure"
    ENDPOINT_TIMEFRAME_ALIGNMENT = "endpoint_timeframe_alignment"
    SAFETY_TIMEFRAME_ALIGNMENT = "safety_timeframe_alignment"
    MEASUREMENT_UNIT_ALIGNMENT = "measurement_unit_alignment"


class ClinicalDimensionStatus(str, Enum):
    SATISFIED = "satisfied"
    GAP = "gap"
    BLOCKING_SIGNAL = "blocking_signal"


class ClinicalEvidenceGapCode(str, Enum):
    INSUFFICIENT_INDEPENDENT_TRIALS = "insufficient_independent_trials"
    BENEFIT_NOT_DEMONSTRATED = "benefit_not_demonstrated"
    BENEFIT_DIRECTION_CONFLICT = "benefit_direction_conflict"
    BENEFIT_HARM_SIGNAL = "benefit_harm_signal"
    IMPRECISE_BENEFIT_ESTIMATE = "imprecise_benefit_estimate"
    MISSING_DESCRIPTIVE_ARM_MEASUREMENT = (
        "missing_descriptive_arm_measurement"
    )
    HIGHER_OBSERVED_SERIOUS_EVENT_RISK = "higher_observed_serious_event_risk"
    SAFETY_DIRECTION_CONFLICT = "safety_direction_conflict"
    INSUFFICIENT_SAFETY_EXPOSURE = "insufficient_safety_exposure"
    ENDPOINT_TIMEFRAME_MISMATCH = "endpoint_timeframe_mismatch"
    SAFETY_TIMEFRAME_MISMATCH = "safety_timeframe_mismatch"
    MEASUREMENT_UNIT_MISMATCH = "measurement_unit_mismatch"


_DIMENSION_ORDER = tuple(ClinicalEvidenceDimension)
_DIMENSION_INDEX = {
    dimension: index for index, dimension in enumerate(_DIMENSION_ORDER)
}
_GAP_ORDER = tuple(ClinicalEvidenceGapCode)
_GAP_INDEX = {code: index for index, code in enumerate(_GAP_ORDER)}
_GAP_DIMENSIONS = {
    ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS: (
        ClinicalEvidenceDimension.TRIAL_COUNT
    ),
    ClinicalEvidenceGapCode.BENEFIT_NOT_DEMONSTRATED: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.BENEFIT_DIRECTION_CONFLICT: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.IMPRECISE_BENEFIT_ESTIMATE: (
        ClinicalEvidenceDimension.BENEFIT_PRECISION
    ),
    ClinicalEvidenceGapCode.MISSING_DESCRIPTIVE_ARM_MEASUREMENT: (
        ClinicalEvidenceDimension.DESCRIPTIVE_ARM_MEASUREMENT_COMPLETENESS
    ),
    ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK: (
        ClinicalEvidenceDimension.SAFETY_DIRECTION
    ),
    ClinicalEvidenceGapCode.SAFETY_DIRECTION_CONFLICT: (
        ClinicalEvidenceDimension.SAFETY_DIRECTION
    ),
    ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE: (
        ClinicalEvidenceDimension.SAFETY_EXPOSURE
    ),
    ClinicalEvidenceGapCode.ENDPOINT_TIMEFRAME_MISMATCH: (
        ClinicalEvidenceDimension.ENDPOINT_TIMEFRAME_ALIGNMENT
    ),
    ClinicalEvidenceGapCode.SAFETY_TIMEFRAME_MISMATCH: (
        ClinicalEvidenceDimension.SAFETY_TIMEFRAME_ALIGNMENT
    ),
    ClinicalEvidenceGapCode.MEASUREMENT_UNIT_MISMATCH: (
        ClinicalEvidenceDimension.MEASUREMENT_UNIT_ALIGNMENT
    ),
}
_BLOCKING_GAP_CODES = {
    ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL,
    ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK,
}
_GAP_SUMMARIES = {
    ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS: (
        "Fewer source-disjoint trials are available than the policy requires."
    ),
    ClinicalEvidenceGapCode.BENEFIT_NOT_DEMONSTRATED: (
        "At least one selected trial does not have a confidence interval "
        "entirely in the declared favorable direction."
    ),
    ClinicalEvidenceGapCode.BENEFIT_DIRECTION_CONFLICT: (
        "Selected trials do not agree on the descriptive benefit direction."
    ),
    ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL: (
        "At least one selected trial has a confidence interval entirely in "
        "the declared unfavorable direction."
    ),
    ClinicalEvidenceGapCode.IMPRECISE_BENEFIT_ESTIMATE: (
        "At least one log-scale effect confidence interval is wider than the "
        "preregistered workflow threshold."
    ),
    ClinicalEvidenceGapCode.MISSING_DESCRIPTIVE_ARM_MEASUREMENT: (
        "At least one selected trial has a source-reported missing descriptive "
        "candidate or comparator arm measurement."
    ),
    ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK: (
        "At least one selected trial has a higher observed aggregate serious-"
        "event risk in the candidate arm."
    ),
    ClinicalEvidenceGapCode.SAFETY_DIRECTION_CONFLICT: (
        "Selected trials do not agree on the observed serious-event risk direction."
    ),
    ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE: (
        "At least one trial arm has fewer safety participants than the policy requires."
    ),
    ClinicalEvidenceGapCode.ENDPOINT_TIMEFRAME_MISMATCH: (
        "Selected endpoint time frames are not identical across trials."
    ),
    ClinicalEvidenceGapCode.SAFETY_TIMEFRAME_MISMATCH: (
        "Selected safety time frames are not identical across trials."
    ),
    ClinicalEvidenceGapCode.MEASUREMENT_UNIT_MISMATCH: (
        "Selected endpoint measurement units are not identical across trials."
    ),
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_non_negative_number(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _require_positive_number(value: float, field_name: str) -> None:
    _require_non_negative_number(value, field_name)
    if float(value) <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_probability_above_zero(value: float, field_name: str) -> None:
    _require_probability(value, field_name)
    if float(value) <= 0:
        raise ValueError(f"{field_name} must be greater than zero")


def _require_sorted_unique_text(
    values: Any,
    field_name: str,
) -> tuple[str, ...]:
    result = _freeze_text_tuple(values, field_name)
    if result != tuple(sorted(result)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return result


def _round_metric(value: float) -> float:
    return round(float(value), 12)


def _round_positive_metric(value: float) -> float:
    result = _round_metric(value)
    if value > 0 and result == 0:
        return 1e-12
    return result


@dataclass(frozen=True, slots=True)
class ClinicalDecisionPolicy(SerializableRecord):
    """Preregistered workflow criteria and action-planning bounds."""

    policy_id: str
    version: str
    registered_on: date
    minimum_independent_trials: int
    maximum_log_effect_ci_width: float
    minimum_safety_participants_per_arm: int
    max_planned_actions: int
    max_planned_cost: float
    minimum_bounded_voi: float
    workflow_scope: str = CLINICAL_WORKFLOW_SCOPE
    require_all_trials_benefit: bool = True
    require_consistent_safety_direction: bool = True
    prohibit_higher_observed_serious_event_risk: bool = True
    require_aligned_endpoint_timeframes: bool = True
    require_aligned_safety_timeframes: bool = True
    require_aligned_measurement_units: bool = True
    automatic_pooling_prohibited: bool = True
    clinical_acceptability_inference_prohibited: bool = True
    terminal_decisions_prohibited: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        _require_positive_int(
            self.minimum_independent_trials,
            "minimum_independent_trials",
        )
        if self.minimum_independent_trials < 2:
            raise ValueError("minimum_independent_trials must be at least two")
        _require_positive_number(
            self.maximum_log_effect_ci_width,
            "maximum_log_effect_ci_width",
        )
        _require_positive_int(
            self.minimum_safety_participants_per_arm,
            "minimum_safety_participants_per_arm",
        )
        _require_positive_int(self.max_planned_actions, "max_planned_actions")
        _require_non_negative_number(self.max_planned_cost, "max_planned_cost")
        _require_probability(
            self.minimum_bounded_voi,
            "minimum_bounded_voi",
        )
        if self.workflow_scope != CLINICAL_WORKFLOW_SCOPE:
            raise ValueError(f"workflow_scope must be {CLINICAL_WORKFLOW_SCOPE}")
        for field_name in (
            "require_all_trials_benefit",
            "require_consistent_safety_direction",
            "prohibit_higher_observed_serious_event_risk",
            "require_aligned_endpoint_timeframes",
            "require_aligned_safety_timeframes",
            "require_aligned_measurement_units",
            "automatic_pooling_prohibited",
            "clinical_acceptability_inference_prohibited",
            "terminal_decisions_prohibited",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata, "metadata"),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceCell(SerializableRecord):
    """One exact trial endpoint/safety cell with source-level provenance."""

    cell_id: str
    study_record_id: str
    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str
    effect_measure: str
    effect_estimate: float
    confidence_interval_percent: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    log_effect_ci_width: float
    benefit_direction: str
    candidate_measurement: float | None
    comparator_measurement: float | None
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
    safety_direction: str
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    endpoint_fingerprint_sha256: str
    safety_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "cell_id",
            "study_record_id",
            "trial_id",
            "design_id",
            "endpoint_id",
            "safety_id",
            "effect_measure",
            "benefit_direction",
            "measurement_unit",
            "endpoint_time_frame",
            "safety_time_frame",
            "safety_direction",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "effect_estimate",
            "confidence_interval_percent",
            "confidence_interval_lower",
            "confidence_interval_upper",
            "log_effect_ci_width",
            "candidate_serious_event_risk",
            "comparator_serious_event_risk",
            "serious_event_risk_difference",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
        for field_name in ("candidate_measurement", "comparator_measurement"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric or null")
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite when present")
        if not (
            0
            < self.confidence_interval_lower
            <= self.effect_estimate
            <= self.confidence_interval_upper
        ):
            raise ValueError("confidence interval must contain effect_estimate")
        if not 0 < self.confidence_interval_percent <= 100:
            raise ValueError("confidence_interval_percent must be in (0, 100]")
        expected_width = math.log(
            self.confidence_interval_upper / self.confidence_interval_lower
        )
        if not math.isclose(
            self.log_effect_ci_width,
            expected_width,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("log_effect_ci_width does not match confidence interval")
        expected_benefit_direction = ratio_benefit_direction(
            self.confidence_interval_lower,
            self.confidence_interval_upper,
            ratio_effect_favorable_direction(self.effect_measure),
        )
        if self.benefit_direction != expected_benefit_direction:
            raise ValueError("benefit_direction does not match confidence interval")
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
            raise ValueError("candidate serious-event denominator must be positive")
        if self.comparator_serious_num_at_risk <= 0:
            raise ValueError("comparator serious-event denominator must be positive")
        if (
            self.candidate_serious_num_affected > self.candidate_serious_num_at_risk
            or self.comparator_serious_num_affected
            > self.comparator_serious_num_at_risk
        ):
            raise ValueError("serious-event count exceeds its denominator")
        expected_candidate_risk = (
            self.candidate_serious_num_affected / self.candidate_serious_num_at_risk
        )
        expected_comparator_risk = (
            self.comparator_serious_num_affected / self.comparator_serious_num_at_risk
        )
        expected_difference = expected_candidate_risk - expected_comparator_risk
        for observed, expected, label in (
            (
                self.candidate_serious_event_risk,
                expected_candidate_risk,
                "candidate_serious_event_risk",
            ),
            (
                self.comparator_serious_event_risk,
                expected_comparator_risk,
                "comparator_serious_event_risk",
            ),
            (
                self.serious_event_risk_difference,
                expected_difference,
                "serious_event_risk_difference",
            ),
        ):
            if not math.isclose(
                observed,
                expected,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(f"{label} does not match raw counts")
        expected_safety_direction = "equal_observed_serious_event_risk"
        if expected_difference < -1e-12:
            expected_safety_direction = "lower_observed_serious_event_risk"
        elif expected_difference > 1e-12:
            expected_safety_direction = "higher_observed_serious_event_risk"
        if self.safety_direction != expected_safety_direction:
            raise ValueError("safety_direction does not match raw serious-event counts")
        object.__setattr__(
            self,
            "source_evidence_ids",
            _require_sorted_unique_text(
                self.source_evidence_ids,
                "source_evidence_ids",
            ),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _require_sorted_unique_text(
                self.source_content_hashes,
                "source_content_hashes",
            ),
        )
        if not self.source_evidence_ids or not self.source_content_hashes:
            raise ValueError("cell provenance must not be empty")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        _require_sha256(
            self.endpoint_fingerprint_sha256,
            "endpoint_fingerprint_sha256",
        )
        _require_sha256(
            self.safety_fingerprint_sha256,
            "safety_fingerprint_sha256",
        )


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceGap(SerializableRecord):
    """One policy-relative evidence gap linked to exact contributing cells."""

    gap_id: str
    code: ClinicalEvidenceGapCode
    dimension: ClinicalEvidenceDimension
    summary: str
    gap_mass: float
    blocking: bool
    study_record_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.gap_id, "gap_id")
        _require_instance(self.code, ClinicalEvidenceGapCode, "code")
        _require_instance(
            self.dimension,
            ClinicalEvidenceDimension,
            "dimension",
        )
        if self.dimension is not _GAP_DIMENSIONS[self.code]:
            raise ValueError("gap code does not match dimension")
        _require_text(self.summary, "summary")
        if self.summary != _GAP_SUMMARIES[self.code]:
            raise ValueError("summary does not match the canonical gap code")
        _require_probability_above_zero(self.gap_mass, "gap_mass")
        _require_bool(self.blocking, "blocking")
        if self.blocking != (self.code in _BLOCKING_GAP_CODES):
            raise ValueError("blocking does not match the canonical gap code")
        object.__setattr__(
            self,
            "study_record_ids",
            _require_sorted_unique_text(
                self.study_record_ids,
                "study_record_ids",
            ),
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            _require_sorted_unique_text(
                self.source_evidence_ids,
                "source_evidence_ids",
            ),
        )
        if not self.study_record_ids or not self.source_evidence_ids:
            raise ValueError("gap provenance must not be empty")


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceDimensionRecord(SerializableRecord):
    """Policy-relative status for one tensor dimension."""

    dimension: ClinicalEvidenceDimension
    status: ClinicalDimensionStatus
    observed: Mapping[str, Any]
    criterion: Mapping[str, Any]
    gap_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_instance(
            self.dimension,
            ClinicalEvidenceDimension,
            "dimension",
        )
        _require_instance(self.status, ClinicalDimensionStatus, "status")
        object.__setattr__(
            self,
            "observed",
            _freeze_mapping(self.observed, "observed"),
        )
        object.__setattr__(
            self,
            "criterion",
            _freeze_mapping(self.criterion, "criterion"),
        )
        object.__setattr__(
            self,
            "gap_ids",
            _require_sorted_unique_text(self.gap_ids, "gap_ids"),
        )
        if self.status is ClinicalDimensionStatus.SATISFIED and self.gap_ids:
            raise ValueError("satisfied dimensions cannot reference gaps")
        if self.status is not ClinicalDimensionStatus.SATISFIED and not self.gap_ids:
            raise ValueError("non-satisfied dimensions must reference gaps")


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceTensor(SerializableRecord):
    """Exact clinical evidence cells plus policy-relative dimensions and gaps."""

    tensor_id: str
    method_id: str
    program_id: str
    synthesis_id: str
    synthesis_fingerprint: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    effect_measure: str
    safety_measure: str
    as_of_date: date
    stage: Stage
    cells: tuple[ClinicalEvidenceCell, ...]
    dimensions: tuple[ClinicalEvidenceDimensionRecord, ...]
    gaps: tuple[ClinicalEvidenceGap, ...]
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    pooling_performed: bool = False
    cross_trial_comparability_inferred: bool = False
    population_homogeneity_inferred: bool = False
    clinical_acceptability_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "tensor_id",
            "program_id",
            "synthesis_id",
            "policy_id",
            "policy_version",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "safety_measure",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_EVIDENCE_TENSOR_METHOD_ID:
            raise ValueError("method_id is unsupported")
        _require_sha256(
            self.synthesis_fingerprint,
            "synthesis_fingerprint",
        )
        _require_sha256(self.policy_fingerprint, "policy_fingerprint")
        _require_date(self.as_of_date, "as_of_date")
        _require_instance(self.stage, Stage, "stage")
        cells = tuple(self.cells)
        object.__setattr__(self, "cells", cells)
        if len(cells) < 2:
            raise ValueError("clinical evidence tensor requires two cells")
        for cell in cells:
            _require_instance(cell, ClinicalEvidenceCell, "cells item")
        for field_name, values in (
            ("cell ids", tuple(item.cell_id for item in cells)),
            (
                "study record ids",
                tuple(item.study_record_id for item in cells),
            ),
            ("trial ids", tuple(item.trial_id for item in cells)),
            ("design ids", tuple(item.design_id for item in cells)),
            ("endpoint ids", tuple(item.endpoint_id for item in cells)),
            ("safety ids", tuple(item.safety_id for item in cells)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        for cell in cells:
            if cell.cell_id != f"{self.tensor_id}:cell:{cell.trial_id}":
                raise ValueError("cell_id is not bound to tensor and trial")
        cell_hash_sets = [set(item.source_content_hashes) for item in cells]
        for index, values in enumerate(cell_hash_sets):
            if any(values & other for other in cell_hash_sets[index + 1 :]):
                raise ValueError("tensor cell source hashes must be pairwise disjoint")
        dimensions = tuple(self.dimensions)
        object.__setattr__(self, "dimensions", dimensions)
        if tuple(item.dimension for item in dimensions) != _DIMENSION_ORDER:
            raise ValueError("dimensions must exactly follow canonical order")
        gaps = tuple(self.gaps)
        object.__setattr__(self, "gaps", gaps)
        for gap in gaps:
            _require_instance(gap, ClinicalEvidenceGap, "gaps item")
        if len({item.gap_id for item in gaps}) != len(gaps):
            raise ValueError("gap ids must be unique")
        if len({item.code for item in gaps}) != len(gaps):
            raise ValueError("gap codes must be unique")
        expected_gap_order = tuple(
            sorted(
                gaps,
                key=lambda item: (
                    _DIMENSION_INDEX[item.dimension],
                    _GAP_INDEX[item.code],
                ),
            )
        )
        if gaps != expected_gap_order:
            raise ValueError("gaps must use canonical dimension/code order")
        gaps_by_dimension = {
            dimension: tuple(item for item in gaps if item.dimension is dimension)
            for dimension in _DIMENSION_ORDER
        }
        for dimension_record in dimensions:
            dimension_gaps = gaps_by_dimension[dimension_record.dimension]
            expected_ids = tuple(sorted(item.gap_id for item in dimension_gaps))
            if dimension_record.gap_ids != expected_ids:
                raise ValueError("dimension gap ids do not match tensor gaps")
            expected_status = ClinicalDimensionStatus.SATISFIED
            if any(item.blocking for item in dimension_gaps):
                expected_status = ClinicalDimensionStatus.BLOCKING_SIGNAL
            elif dimension_gaps:
                expected_status = ClinicalDimensionStatus.GAP
            if dimension_record.status is not expected_status:
                raise ValueError("dimension status does not match tensor gaps")
        expected_gap_ids = {f"{self.tensor_id}:gap:{item.code.value}" for item in gaps}
        if {item.gap_id for item in gaps} != expected_gap_ids:
            raise ValueError("gap ids are not bound to tensor_id")
        cells_by_study_id = {item.study_record_id: item for item in cells}
        cell_study_ids = set(cells_by_study_id)
        cell_evidence_ids = {
            evidence_id for cell in cells for evidence_id in cell.source_evidence_ids
        }
        for gap in gaps:
            if not set(gap.study_record_ids).issubset(cell_study_ids):
                raise ValueError("gap references an unknown study record")
            if not set(gap.source_evidence_ids).issubset(cell_evidence_ids):
                raise ValueError("gap references unknown source evidence")
            expected_gap_evidence = tuple(
                sorted(
                    {
                        evidence_id
                        for study_id in gap.study_record_ids
                        for evidence_id in cells_by_study_id[
                            study_id
                        ].source_evidence_ids
                    }
                )
            )
            if gap.source_evidence_ids != expected_gap_evidence:
                raise ValueError(
                    "gap source evidence does not match implicated studies"
                )
        expected_evidence_ids = tuple(sorted(cell_evidence_ids))
        expected_hashes = tuple(
            sorted({digest for cell in cells for digest in cell.source_content_hashes})
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            _require_sorted_unique_text(
                self.source_evidence_ids,
                "source_evidence_ids",
            ),
        )
        object.__setattr__(
            self,
            "source_content_hashes",
            _require_sorted_unique_text(
                self.source_content_hashes,
                "source_content_hashes",
            ),
        )
        if self.source_evidence_ids != expected_evidence_ids:
            raise ValueError("source_evidence_ids do not match tensor cells")
        if self.source_content_hashes != expected_hashes:
            raise ValueError("source_content_hashes do not match tensor cells")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        for field_name in (
            "pooling_performed",
            "cross_trial_comparability_inferred",
            "population_homogeneity_inferred",
            "clinical_acceptability_inferred",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if value:
                raise ValueError(f"{field_name} must be false")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceActionOption(SerializableRecord):
    """Predeclared evidence action with explicit cost and heuristic inputs."""

    action_id: str
    action_type: ActionType
    tool_id: str
    operation: str
    purpose: str
    targeted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    expected_gap_resolution_probability: float
    decision_relevance: float
    max_cost: float
    arguments: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "action_id",
            "tool_id",
            "operation",
            "purpose",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.action_type, ActionType, "action_type")
        if self.action_type not in _ALLOWED_ACTION_TYPES:
            raise ValueError(
                "clinical evidence actions must retrieve, query, or verify"
            )
        codes = tuple(self.targeted_gap_codes)
        object.__setattr__(self, "targeted_gap_codes", codes)
        if not codes or len(codes) != len(set(codes)):
            raise ValueError("targeted_gap_codes must be non-empty and unique")
        for code in codes:
            _require_instance(
                code,
                ClinicalEvidenceGapCode,
                "targeted_gap_codes item",
            )
        if codes != tuple(sorted(codes, key=_GAP_INDEX.__getitem__)):
            raise ValueError("targeted_gap_codes must use canonical gap-code order")
        _require_probability_above_zero(
            self.expected_gap_resolution_probability,
            "expected_gap_resolution_probability",
        )
        _require_probability_above_zero(
            self.decision_relevance,
            "decision_relevance",
        )
        _require_positive_number(self.max_cost, "max_cost")
        object.__setattr__(
            self,
            "arguments",
            _freeze_mapping(self.arguments, "arguments"),
        )
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata, "metadata"),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceActionSelection(SerializableRecord):
    """One ranked action and its marginal bounded-VOI calculation."""

    rank: int
    action_id: str
    action_fingerprint: str
    targeted_gap_ids: tuple[str, ...]
    marginal_gap_mass: float
    bounded_voi: float
    voi_per_cost: float
    max_cost: float

    def __post_init__(self) -> None:
        _require_positive_int(self.rank, "rank")
        _require_text(self.action_id, "action_id")
        _require_sha256(self.action_fingerprint, "action_fingerprint")
        object.__setattr__(
            self,
            "targeted_gap_ids",
            _require_sorted_unique_text(
                self.targeted_gap_ids,
                "targeted_gap_ids",
            ),
        )
        if not self.targeted_gap_ids:
            raise ValueError("selected actions must target at least one gap")
        _require_probability_above_zero(
            self.marginal_gap_mass,
            "marginal_gap_mass",
        )
        _require_probability_above_zero(self.bounded_voi, "bounded_voi")
        _require_positive_number(self.voi_per_cost, "voi_per_cost")
        _require_positive_number(self.max_cost, "max_cost")


@dataclass(frozen=True, slots=True)
class ClinicalDecisionPlan(SerializableRecord):
    """Fail-closed workflow disposition and bounded evidence-action batch."""

    plan_id: str
    tensor_id: str
    tensor_fingerprint: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    decision: Decision
    code: str
    rationale_codes: tuple[str, ...]
    selected_actions: tuple[ClinicalEvidenceActionSelection, ...]
    open_gap_ids: tuple[str, ...]
    targeted_gap_ids: tuple[str, ...]
    untargeted_gap_ids: tuple[str, ...]
    budget_limit: float
    budget_spent: float
    budget_available: float
    planned_cost: float
    budget_remaining_after_plan: float
    voi_method_id: str = BOUNDED_VOI_METHOD_ID
    workflow_scope: str = CLINICAL_WORKFLOW_SCOPE
    clinical_acceptability_inferred: bool = False
    terminal_decision_issued: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "plan_id",
            "tensor_id",
            "policy_id",
            "policy_version",
            "code",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.tensor_fingerprint, "tensor_fingerprint")
        _require_sha256(self.policy_fingerprint, "policy_fingerprint")
        _require_instance(self.decision, Decision, "decision")
        if self.decision not in {
            Decision.ADVANCE,
            Decision.HOLD,
            Decision.DEFER,
        }:
            raise ValueError(
                "clinical workflow plans support only advance, hold, or defer"
            )
        object.__setattr__(
            self,
            "rationale_codes",
            _freeze_text_tuple(self.rationale_codes, "rationale_codes"),
        )
        if not self.rationale_codes:
            raise ValueError("rationale_codes must not be empty")
        selected = tuple(self.selected_actions)
        object.__setattr__(self, "selected_actions", selected)
        for action in selected:
            _require_instance(
                action,
                ClinicalEvidenceActionSelection,
                "selected_actions item",
            )
        if tuple(item.rank for item in selected) != tuple(range(1, len(selected) + 1)):
            raise ValueError("selected action ranks must be contiguous")
        if len({item.action_id for item in selected}) != len(selected):
            raise ValueError("selected action ids must be unique")
        open_gap_ids = _require_sorted_unique_text(
            self.open_gap_ids,
            "open_gap_ids",
        )
        targeted_gap_ids = _require_sorted_unique_text(
            self.targeted_gap_ids,
            "targeted_gap_ids",
        )
        untargeted_gap_ids = _require_sorted_unique_text(
            self.untargeted_gap_ids,
            "untargeted_gap_ids",
        )
        object.__setattr__(self, "open_gap_ids", open_gap_ids)
        object.__setattr__(self, "targeted_gap_ids", targeted_gap_ids)
        object.__setattr__(self, "untargeted_gap_ids", untargeted_gap_ids)
        selected_gap_ids = tuple(
            sorted(
                {gap_id for action in selected for gap_id in action.targeted_gap_ids}
            )
        )
        if selected_gap_ids != targeted_gap_ids:
            raise ValueError("targeted_gap_ids must equal selected action gap union")
        if set(targeted_gap_ids) & set(untargeted_gap_ids):
            raise ValueError("targeted and untargeted gaps must be disjoint")
        if tuple(sorted((*targeted_gap_ids, *untargeted_gap_ids))) != (open_gap_ids):
            raise ValueError("targeted and untargeted gaps must partition open gaps")
        for field_name in (
            "budget_limit",
            "budget_spent",
            "budget_available",
            "planned_cost",
            "budget_remaining_after_plan",
        ):
            _require_non_negative_number(
                getattr(self, field_name),
                field_name,
            )
        if self.budget_spent > self.budget_limit + 1e-12:
            raise ValueError("budget_spent exceeds budget_limit")
        if self.budget_available > (self.budget_limit - self.budget_spent + 1e-12):
            raise ValueError("budget_available exceeds remaining budget")
        expected_cost = sum(item.max_cost for item in selected)
        if not math.isclose(
            self.planned_cost,
            expected_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("planned_cost does not match selected actions")
        if self.planned_cost > self.budget_available + 1e-12:
            raise ValueError("planned_cost exceeds budget_available")
        if not math.isclose(
            self.budget_remaining_after_plan,
            self.budget_available - self.planned_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("budget_remaining_after_plan does not match planned cost")
        if self.decision is Decision.ADVANCE:
            if open_gap_ids or selected:
                raise ValueError("advance requires no open gaps or selected actions")
        elif self.decision is Decision.HOLD:
            if not open_gap_ids or not selected:
                raise ValueError("hold requires open gaps and selected actions")
        elif not open_gap_ids or selected:
            raise ValueError("defer requires open gaps and no selected actions")
        if self.voi_method_id != BOUNDED_VOI_METHOD_ID:
            raise ValueError("voi_method_id is unsupported")
        if self.workflow_scope != CLINICAL_WORKFLOW_SCOPE:
            raise ValueError("workflow_scope is unsupported")
        for field_name in (
            "clinical_acceptability_inferred",
            "terminal_decision_issued",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if value:
                raise ValueError(f"{field_name} must be false")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalDecisionPackage(SerializableRecord):
    """Self-contained policy, evidence tensor, catalog, and decision plan."""

    package_id: str
    program_id: str
    as_of_date: date
    policy: ClinicalDecisionPolicy
    action_catalog: tuple[ClinicalEvidenceActionOption, ...]
    tensor: ClinicalEvidenceTensor
    plan: ClinicalDecisionPlan
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in ("package_id", "program_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.as_of_date, "as_of_date")
        _require_instance(
            self.policy,
            ClinicalDecisionPolicy,
            "policy",
        )
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
        if action_ids != tuple(sorted(action_ids)):
            raise ValueError("action_catalog must use canonical action-id order")
        _require_instance(
            self.tensor,
            ClinicalEvidenceTensor,
            "tensor",
        )
        _require_instance(self.plan, ClinicalDecisionPlan, "plan")
        if self.program_id != self.tensor.program_id:
            raise ValueError("package and tensor program ids do not match")
        if self.as_of_date != self.tensor.as_of_date:
            raise ValueError("package and tensor cutoff dates do not match")
        if (
            self.tensor.policy_id != self.policy.policy_id
            or self.tensor.policy_version != self.policy.version
            or self.tensor.policy_fingerprint != self.policy.fingerprint
        ):
            raise ValueError("tensor is not bound to package policy")
        if (
            self.plan.tensor_id != self.tensor.tensor_id
            or self.plan.tensor_fingerprint != self.tensor.fingerprint
            or self.plan.policy_id != self.policy.policy_id
            or self.plan.policy_version != self.policy.version
            or self.plan.policy_fingerprint != self.policy.fingerprint
        ):
            raise ValueError("plan is not bound to tensor and policy")
        catalog_by_id = {item.action_id: item for item in catalog}
        for selection in self.plan.selected_actions:
            option = catalog_by_id.get(selection.action_id)
            if option is None or selection.action_fingerprint != option.fingerprint:
                raise ValueError("selected action is not bound to action_catalog")
        expected_plan = plan_clinical_evidence_actions(
            self.tensor,
            self.policy,
            catalog,
            BudgetState(
                limit=self.plan.budget_limit,
                spent=self.plan.budget_spent,
            ),
            plan_id=self.plan.plan_id,
        )
        if expected_plan != self.plan:
            raise ValueError("plan does not match deterministic bounded-VOI replay")
        limitations = _freeze_text_tuple(
            self.limitations,
            "limitations",
        )
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required clinical decision limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _cell_from_study(
    tensor_id: str,
    study: StudyBenefitRiskRecord,
) -> ClinicalEvidenceCell:
    endpoint_fingerprint = study.identifiers.get("endpoint_fingerprint_sha256")
    safety_fingerprint = study.identifiers.get("safety_fingerprint_sha256")
    if endpoint_fingerprint is None or safety_fingerprint is None:
        raise ClinicalDecisionError(
            "study endpoint and safety fingerprints are required"
        )
    return ClinicalEvidenceCell(
        cell_id=f"{tensor_id}:cell:{study.trial_id}",
        study_record_id=study.study_record_id,
        trial_id=study.trial_id,
        design_id=study.design_id,
        endpoint_id=study.endpoint_id,
        safety_id=study.safety_id,
        effect_measure=study.effect_measure,
        effect_estimate=study.effect_estimate,
        confidence_interval_percent=study.confidence_interval_percent,
        confidence_interval_lower=study.confidence_interval_lower,
        confidence_interval_upper=study.confidence_interval_upper,
        log_effect_ci_width=math.log(
            study.confidence_interval_upper / study.confidence_interval_lower
        ),
        benefit_direction=study.benefit_direction,
        candidate_measurement=study.candidate_measurement,
        comparator_measurement=study.comparator_measurement,
        measurement_unit=study.measurement_unit,
        endpoint_time_frame=study.endpoint_time_frame,
        safety_time_frame=study.safety_time_frame,
        candidate_serious_num_affected=(study.candidate_serious_num_affected),
        candidate_serious_num_at_risk=study.candidate_serious_num_at_risk,
        comparator_serious_num_affected=(study.comparator_serious_num_affected),
        comparator_serious_num_at_risk=study.comparator_serious_num_at_risk,
        candidate_serious_event_risk=study.candidate_serious_event_risk,
        comparator_serious_event_risk=study.comparator_serious_event_risk,
        serious_event_risk_difference=study.serious_event_risk_difference,
        safety_direction=study.safety_direction,
        source_evidence_ids=study.source_evidence_ids,
        source_content_hashes=study.source_content_hashes,
        endpoint_fingerprint_sha256=endpoint_fingerprint,
        safety_fingerprint_sha256=safety_fingerprint,
    )


def _gap(
    tensor_id: str,
    code: ClinicalEvidenceGapCode,
    gap_mass: float,
    cells: Sequence[ClinicalEvidenceCell],
) -> ClinicalEvidenceGap:
    return ClinicalEvidenceGap(
        gap_id=f"{tensor_id}:gap:{code.value}",
        code=code,
        dimension=_GAP_DIMENSIONS[code],
        summary=_GAP_SUMMARIES[code],
        gap_mass=_round_positive_metric(gap_mass),
        blocking=code in _BLOCKING_GAP_CODES,
        study_record_ids=tuple(sorted({item.study_record_id for item in cells})),
        source_evidence_ids=tuple(
            sorted(
                {
                    evidence_id
                    for item in cells
                    for evidence_id in item.source_evidence_ids
                }
            )
        ),
    )


def _direction_counts(
    cells: Sequence[ClinicalEvidenceCell],
    field_name: str,
) -> dict[str, int]:
    values: dict[str, int] = {}
    for cell in cells:
        value = getattr(cell, field_name)
        values[value] = values.get(value, 0) + 1
    return dict(sorted(values.items()))


def _dimension_record(
    dimension: ClinicalEvidenceDimension,
    observed: Mapping[str, Any],
    criterion: Mapping[str, Any],
    gaps: Sequence[ClinicalEvidenceGap],
) -> ClinicalEvidenceDimensionRecord:
    relevant = tuple(item for item in gaps if item.dimension is dimension)
    status = ClinicalDimensionStatus.SATISFIED
    if any(item.blocking for item in relevant):
        status = ClinicalDimensionStatus.BLOCKING_SIGNAL
    elif relevant:
        status = ClinicalDimensionStatus.GAP
    return ClinicalEvidenceDimensionRecord(
        dimension=dimension,
        status=status,
        observed=observed,
        criterion=criterion,
        gap_ids=tuple(sorted(item.gap_id for item in relevant)),
    )


def compile_clinical_evidence_tensor(
    state: ProgramState,
    synthesis: BenefitRiskSynthesisRecord,
    policy: ClinicalDecisionPolicy,
    *,
    tensor_id: str,
) -> ClinicalEvidenceTensor:
    """Compile a policy-relative tensor from one committed synthesis."""

    _require_instance(state, ProgramState, "state")
    _require_instance(
        synthesis,
        BenefitRiskSynthesisRecord,
        "synthesis",
    )
    _require_instance(policy, ClinicalDecisionPolicy, "policy")
    _require_text(tensor_id, "tensor_id")
    if policy.registered_on > state.as_of_date:
        raise ClinicalDecisionError(
            "clinical decision policy is after the program cutoff"
        )
    try:
        state.validate_committed_history()
    except (TypeError, ValueError) as exc:
        raise ClinicalDecisionError("program committed history is invalid") from exc
    committed = state.benefit_risk_syntheses_by_id.get(synthesis.synthesis_id)
    if committed is None or committed != synthesis:
        raise ClinicalDecisionError(
            "synthesis must exactly match the committed state ledger"
        )
    continuity_failures = validate_benefit_risk_synthesis(state, synthesis)
    if continuity_failures:
        raise ClinicalDecisionError(
            "committed synthesis failed continuity replay: "
            + ", ".join(continuity_failures)
        )
    cells = tuple(_cell_from_study(tensor_id, item) for item in synthesis.studies)
    gaps: list[ClinicalEvidenceGap] = []
    trial_count = len(cells)
    if trial_count < policy.minimum_independent_trials:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,
                (policy.minimum_independent_trials - trial_count)
                / policy.minimum_independent_trials,
                cells,
            )
        )
    benefit_directions = {item.benefit_direction for item in cells}
    non_benefit_cells = tuple(
        item for item in cells if item.benefit_direction != "benefit"
    )
    if "harm" in benefit_directions:
        implicated = tuple(item for item in cells if item.benefit_direction == "harm")
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL,
                1.0,
                implicated,
            )
        )
    elif non_benefit_cells and len(benefit_directions) > 1:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.BENEFIT_DIRECTION_CONFLICT,
                1.0,
                cells,
            )
        )
    elif non_benefit_cells:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.BENEFIT_NOT_DEMONSTRATED,
                1.0,
                non_benefit_cells,
            )
        )
    imprecise_cells = tuple(
        item
        for item in cells
        if item.log_effect_ci_width > policy.maximum_log_effect_ci_width + 1e-12
    )
    if imprecise_cells:
        maximum_width = max(item.log_effect_ci_width for item in imprecise_cells)
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.IMPRECISE_BENEFIT_ESTIMATE,
                1.0 - policy.maximum_log_effect_ci_width / maximum_width,
                imprecise_cells,
            )
        )
    incomplete_measurement_cells = tuple(
        item
        for item in cells
        if item.candidate_measurement is None
        or item.comparator_measurement is None
    )
    if incomplete_measurement_cells:
        missing_measurement_count = sum(
            item.candidate_measurement is None
            for item in incomplete_measurement_cells
        ) + sum(
            item.comparator_measurement is None
            for item in incomplete_measurement_cells
        )
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.MISSING_DESCRIPTIVE_ARM_MEASUREMENT,
                missing_measurement_count / (2 * len(cells)),
                incomplete_measurement_cells,
            )
        )
    higher_safety_cells = tuple(
        item
        for item in cells
        if item.safety_direction == "higher_observed_serious_event_risk"
    )
    safety_directions = {item.safety_direction for item in cells}
    if higher_safety_cells:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK,
                1.0,
                higher_safety_cells,
            )
        )
    elif len(safety_directions) > 1:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.SAFETY_DIRECTION_CONFLICT,
                1.0,
                cells,
            )
        )
    low_exposure_cells = tuple(
        item
        for item in cells
        if min(
            item.candidate_serious_num_at_risk,
            item.comparator_serious_num_at_risk,
        )
        < policy.minimum_safety_participants_per_arm
    )
    if low_exposure_cells:
        minimum_observed = min(
            min(
                item.candidate_serious_num_at_risk,
                item.comparator_serious_num_at_risk,
            )
            for item in low_exposure_cells
        )
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE,
                1.0 - minimum_observed / policy.minimum_safety_participants_per_arm,
                low_exposure_cells,
            )
        )
    endpoint_time_frames = sorted({item.endpoint_time_frame for item in cells})
    if len(endpoint_time_frames) > 1:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.ENDPOINT_TIMEFRAME_MISMATCH,
                1.0,
                cells,
            )
        )
    safety_time_frames = sorted({item.safety_time_frame for item in cells})
    if len(safety_time_frames) > 1:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.SAFETY_TIMEFRAME_MISMATCH,
                1.0,
                cells,
            )
        )
    measurement_units = sorted({item.measurement_unit for item in cells})
    if len(measurement_units) > 1:
        gaps.append(
            _gap(
                tensor_id,
                ClinicalEvidenceGapCode.MEASUREMENT_UNIT_MISMATCH,
                1.0,
                cells,
            )
        )
    ordered_gaps = tuple(
        sorted(
            gaps,
            key=lambda item: (
                _DIMENSION_INDEX[item.dimension],
                _GAP_INDEX[item.code],
            ),
        )
    )
    widths = {
        item.study_record_id: _round_metric(item.log_effect_ci_width) for item in cells
    }
    minimum_safety_counts = {
        item.study_record_id: min(
            item.candidate_serious_num_at_risk,
            item.comparator_serious_num_at_risk,
        )
        for item in cells
    }
    dimensions = (
        _dimension_record(
            ClinicalEvidenceDimension.SOURCE_INDEPENDENCE,
            {
                "source_disjoint": synthesis.source_disjoint,
                "source_content_hash_count": len(synthesis.source_content_hashes),
            },
            {"source_disjoint": True},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.TRIAL_COUNT,
            {"independent_trial_count": trial_count},
            {"minimum_independent_trials": (policy.minimum_independent_trials)},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.BENEFIT_DIRECTION,
            {
                "direction_counts": _direction_counts(
                    cells,
                    "benefit_direction",
                )
            },
            {"all_trials_benefit": True},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.BENEFIT_PRECISION,
            {
                "log_effect_ci_width_by_study": widths,
                "maximum_observed_log_effect_ci_width": max(widths.values()),
            },
            {"maximum_log_effect_ci_width": (policy.maximum_log_effect_ci_width)},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.DESCRIPTIVE_ARM_MEASUREMENT_COMPLETENESS,
            {
                "missing_arms_by_study": {
                    item.study_record_id: [
                        role
                        for role, value in (
                            ("candidate", item.candidate_measurement),
                            ("comparator", item.comparator_measurement),
                        )
                        if value is None
                    ]
                    for item in cells
                    if item.candidate_measurement is None
                    or item.comparator_measurement is None
                },
                "complete_study_count": (
                    len(cells) - len(incomplete_measurement_cells)
                ),
            },
            {"missing_descriptive_arm_measurements": 0},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.SAFETY_DIRECTION,
            {
                "direction_counts": _direction_counts(
                    cells,
                    "safety_direction",
                ),
                "risk_difference_by_study": {
                    item.study_record_id: item.serious_event_risk_difference
                    for item in cells
                },
            },
            {
                "higher_observed_serious_event_risk_trials": 0,
                "consistent_direction_required": True,
            },
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.SAFETY_EXPOSURE,
            {
                "minimum_arm_participants_by_study": (minimum_safety_counts),
                "minimum_observed_arm_participants": min(
                    minimum_safety_counts.values()
                ),
            },
            {
                "minimum_safety_participants_per_arm": (
                    policy.minimum_safety_participants_per_arm
                )
            },
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.ENDPOINT_TIMEFRAME_ALIGNMENT,
            {"endpoint_time_frames": endpoint_time_frames},
            {"identical_across_trials": True},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.SAFETY_TIMEFRAME_ALIGNMENT,
            {"safety_time_frames": safety_time_frames},
            {"identical_across_trials": True},
            ordered_gaps,
        ),
        _dimension_record(
            ClinicalEvidenceDimension.MEASUREMENT_UNIT_ALIGNMENT,
            {"measurement_units": measurement_units},
            {"identical_across_trials": True},
            ordered_gaps,
        ),
    )
    return ClinicalEvidenceTensor(
        tensor_id=tensor_id,
        method_id=CLINICAL_EVIDENCE_TENSOR_METHOD_ID,
        program_id=state.program_id,
        synthesis_id=synthesis.synthesis_id,
        synthesis_fingerprint=_sha256(synthesis),
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint,
        candidate_id=synthesis.candidate_id,
        intervention_id=synthesis.intervention_id,
        disease_id=synthesis.disease_id,
        endpoint_mapping_id=synthesis.endpoint_mapping_id,
        endpoint_family=synthesis.endpoint_family,
        effect_measure=synthesis.effect_measure,
        safety_measure=synthesis.safety_measure,
        as_of_date=state.as_of_date,
        stage=synthesis.stage,
        cells=cells,
        dimensions=dimensions,
        gaps=ordered_gaps,
        source_evidence_ids=synthesis.source_evidence_ids,
        source_content_hashes=synthesis.source_content_hashes,
    )


def _marginal_gap_mass(gaps: Sequence[ClinicalEvidenceGap]) -> float:
    complement = 1.0
    for gap in gaps:
        complement *= 1.0 - gap.gap_mass
    return _round_positive_metric(1.0 - complement)


def _score_action(
    option: ClinicalEvidenceActionOption,
    gaps: Sequence[ClinicalEvidenceGap],
    *,
    rank: int,
) -> ClinicalEvidenceActionSelection:
    gap_mass = _marginal_gap_mass(gaps)
    bounded_voi = _round_positive_metric(
        gap_mass
        * option.expected_gap_resolution_probability
        * option.decision_relevance
    )
    return ClinicalEvidenceActionSelection(
        rank=rank,
        action_id=option.action_id,
        action_fingerprint=option.fingerprint,
        targeted_gap_ids=tuple(sorted(item.gap_id for item in gaps)),
        marginal_gap_mass=gap_mass,
        bounded_voi=bounded_voi,
        voi_per_cost=_round_positive_metric(bounded_voi / option.max_cost),
        max_cost=option.max_cost,
    )


def plan_clinical_evidence_actions(
    tensor: ClinicalEvidenceTensor,
    policy: ClinicalDecisionPolicy,
    action_catalog: Sequence[ClinicalEvidenceActionOption],
    budget: BudgetState,
    *,
    plan_id: str,
) -> ClinicalDecisionPlan:
    """Choose a deterministic marginal-VOI action batch within hard bounds."""

    _require_instance(tensor, ClinicalEvidenceTensor, "tensor")
    _require_instance(policy, ClinicalDecisionPolicy, "policy")
    _require_instance(budget, BudgetState, "budget")
    _require_text(plan_id, "plan_id")
    if (
        tensor.policy_id != policy.policy_id
        or tensor.policy_version != policy.version
        or tensor.policy_fingerprint != policy.fingerprint
    ):
        raise ClinicalDecisionError("tensor is not bound to policy")
    catalog = tuple(action_catalog)
    for option in catalog:
        _require_instance(
            option,
            ClinicalEvidenceActionOption,
            "action_catalog item",
        )
    if len({item.action_id for item in catalog}) != len(catalog):
        raise ClinicalDecisionError("action_catalog action ids must be unique")
    gaps_by_code = {item.code: item for item in tensor.gaps}
    open_gap_ids = tuple(sorted(item.gap_id for item in tensor.gaps))
    available_budget = _round_metric(min(budget.remaining, policy.max_planned_cost))
    if not tensor.gaps:
        return ClinicalDecisionPlan(
            plan_id=plan_id,
            tensor_id=tensor.tensor_id,
            tensor_fingerprint=tensor.fingerprint,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_fingerprint=policy.fingerprint,
            decision=Decision.ADVANCE,
            code="clinical_evidence_workflow_ready",
            rationale_codes=("all_preregistered_workflow_criteria_satisfied",),
            selected_actions=(),
            open_gap_ids=(),
            targeted_gap_ids=(),
            untargeted_gap_ids=(),
            budget_limit=budget.limit,
            budget_spent=budget.spent,
            budget_available=available_budget,
            planned_cost=0.0,
            budget_remaining_after_plan=available_budget,
        )
    addressable = tuple(
        item
        for item in catalog
        if any(code in gaps_by_code for code in item.targeted_gap_codes)
    )
    qualified_before_budget = tuple(
        item
        for item in addressable
        if _score_action(
            item,
            tuple(
                gaps_by_code[code]
                for code in item.targeted_gap_codes
                if code in gaps_by_code
            ),
            rank=1,
        ).bounded_voi
        >= policy.minimum_bounded_voi - 1e-12
    )
    selected: list[ClinicalEvidenceActionSelection] = []
    selected_ids: set[str] = set()
    targeted_ids: set[str] = set()
    planned_cost = 0.0
    while len(selected) < policy.max_planned_actions:
        candidates: list[
            tuple[
                tuple[float, float, float, str],
                ClinicalEvidenceActionSelection,
            ]
        ] = []
        for option in catalog:
            if option.action_id in selected_ids:
                continue
            marginal_gaps = tuple(
                gaps_by_code[code]
                for code in option.targeted_gap_codes
                if code in gaps_by_code
                and gaps_by_code[code].gap_id not in targeted_ids
            )
            if not marginal_gaps:
                continue
            scored = _score_action(
                option,
                marginal_gaps,
                rank=len(selected) + 1,
            )
            if scored.bounded_voi < policy.minimum_bounded_voi - 1e-12:
                continue
            if planned_cost + option.max_cost > available_budget + 1e-12:
                continue
            candidates.append(
                (
                    (
                        -scored.voi_per_cost,
                        -scored.bounded_voi,
                        scored.max_cost,
                        scored.action_id,
                    ),
                    scored,
                )
            )
        if not candidates:
            break
        _, chosen = min(candidates, key=lambda item: item[0])
        selected.append(chosen)
        selected_ids.add(chosen.action_id)
        targeted_ids.update(chosen.targeted_gap_ids)
        planned_cost = _round_metric(planned_cost + chosen.max_cost)
    targeted_gap_ids = tuple(sorted(targeted_ids))
    untargeted_gap_ids = tuple(sorted(set(open_gap_ids) - targeted_ids))
    if selected:
        decision = Decision.HOLD
        code = "clinical_evidence_acquisition_planned"
        leading_rationale = "open_evidence_gaps_have_bounded_actions"
    else:
        decision = Decision.DEFER
        if qualified_before_budget:
            code = "clinical_evidence_action_budget_insufficient"
            leading_rationale = "qualified_actions_exceed_available_budget"
        elif addressable:
            code = "clinical_evidence_actions_below_voi_threshold"
            leading_rationale = "addressable_actions_below_voi_threshold"
        else:
            code = "clinical_evidence_gaps_unaddressed"
            leading_rationale = "no_catalog_action_targets_open_gaps"
    rationale_codes = (
        leading_rationale,
        *tuple(f"gap:{item.code.value}" for item in tensor.gaps),
    )
    return ClinicalDecisionPlan(
        plan_id=plan_id,
        tensor_id=tensor.tensor_id,
        tensor_fingerprint=tensor.fingerprint,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint,
        decision=decision,
        code=code,
        rationale_codes=rationale_codes,
        selected_actions=tuple(selected),
        open_gap_ids=open_gap_ids,
        targeted_gap_ids=targeted_gap_ids,
        untargeted_gap_ids=untargeted_gap_ids,
        budget_limit=budget.limit,
        budget_spent=budget.spent,
        budget_available=available_budget,
        planned_cost=planned_cost,
        budget_remaining_after_plan=_round_metric(available_budget - planned_cost),
    )


def compile_clinical_decision_package(
    state: ProgramState,
    synthesis: BenefitRiskSynthesisRecord,
    policy: ClinicalDecisionPolicy,
    action_catalog: Sequence[ClinicalEvidenceActionOption],
    *,
    package_id: str,
    tensor_id: str,
    plan_id: str,
) -> ClinicalDecisionPackage:
    """Compile a replayable clinical evidence tensor and bounded action plan."""

    _require_text(package_id, "package_id")
    catalog = tuple(sorted(action_catalog, key=lambda item: item.action_id))
    tensor = compile_clinical_evidence_tensor(
        state,
        synthesis,
        policy,
        tensor_id=tensor_id,
    )
    plan = plan_clinical_evidence_actions(
        tensor,
        policy,
        catalog,
        state.budget,
        plan_id=plan_id,
    )
    return ClinicalDecisionPackage(
        package_id=package_id,
        program_id=state.program_id,
        as_of_date=state.as_of_date,
        policy=policy,
        action_catalog=catalog,
        tensor=tensor,
        plan=plan,
    )


def validate_clinical_decision_package(
    state: ProgramState,
    package: ClinicalDecisionPackage,
) -> tuple[str, ...]:
    """Recompile a package from the committed synthesis and exact catalog."""

    _require_instance(state, ProgramState, "state")
    _require_instance(package, ClinicalDecisionPackage, "package")
    synthesis = state.benefit_risk_syntheses_by_id.get(package.tensor.synthesis_id)
    if synthesis is None:
        return ("committed_synthesis_missing",)
    try:
        rebuilt = compile_clinical_decision_package(
            state,
            synthesis,
            package.policy,
            package.action_catalog,
            package_id=package.package_id,
            tensor_id=package.tensor.tensor_id,
            plan_id=package.plan.plan_id,
        )
    except (ClinicalDecisionError, TypeError, ValueError):
        return ("recompile_failed",)
    if rebuilt != package:
        return ("recompiled_package_mismatch",)
    return ()


def clinical_decision_package_envelope(
    package: ClinicalDecisionPackage,
) -> dict[str, Any]:
    """Return a strict, integrity-bound public package envelope."""

    _require_instance(
        package,
        ClinicalDecisionPackage,
        "package",
    )
    return {
        "schema_version": CLINICAL_DECISION_PACKAGE_SCHEMA_VERSION,
        "integrity_sha256": package.fingerprint,
        "package": package.to_dict(),
    }


def _parse_record(
    value: Any,
    path: str,
    fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing:
        raise RecordParseError(f"{path} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise RecordParseError(f"{path} has unknown fields: {', '.join(sorted(extra))}")
    return data


def _parse_sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _parse_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    return dict(value)


def _parse_enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is not a valid {enum_type.__name__}") from exc


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc


def _parse_policy(value: Any, path: str) -> ClinicalDecisionPolicy:
    fields = {
        "policy_id",
        "version",
        "registered_on",
        "minimum_independent_trials",
        "maximum_log_effect_ci_width",
        "minimum_safety_participants_per_arm",
        "max_planned_actions",
        "max_planned_cost",
        "minimum_bounded_voi",
        "workflow_scope",
        "require_all_trials_benefit",
        "require_consistent_safety_direction",
        "prohibit_higher_observed_serious_event_risk",
        "require_aligned_endpoint_timeframes",
        "require_aligned_safety_timeframes",
        "require_aligned_measurement_units",
        "automatic_pooling_prohibited",
        "clinical_acceptability_inference_prohibited",
        "terminal_decisions_prohibited",
        "metadata",
    }
    data = _parse_record(value, path, fields)
    return ClinicalDecisionPolicy(
        policy_id=data["policy_id"],
        version=data["version"],
        registered_on=_parse_date(
            data["registered_on"],
            f"{path}.registered_on",
        ),
        minimum_independent_trials=data["minimum_independent_trials"],
        maximum_log_effect_ci_width=data["maximum_log_effect_ci_width"],
        minimum_safety_participants_per_arm=(
            data["minimum_safety_participants_per_arm"]
        ),
        max_planned_actions=data["max_planned_actions"],
        max_planned_cost=data["max_planned_cost"],
        minimum_bounded_voi=data["minimum_bounded_voi"],
        workflow_scope=data["workflow_scope"],
        require_all_trials_benefit=data["require_all_trials_benefit"],
        require_consistent_safety_direction=(
            data["require_consistent_safety_direction"]
        ),
        prohibit_higher_observed_serious_event_risk=(
            data["prohibit_higher_observed_serious_event_risk"]
        ),
        require_aligned_endpoint_timeframes=(
            data["require_aligned_endpoint_timeframes"]
        ),
        require_aligned_safety_timeframes=(data["require_aligned_safety_timeframes"]),
        require_aligned_measurement_units=(data["require_aligned_measurement_units"]),
        automatic_pooling_prohibited=data["automatic_pooling_prohibited"],
        clinical_acceptability_inference_prohibited=(
            data["clinical_acceptability_inference_prohibited"]
        ),
        terminal_decisions_prohibited=data["terminal_decisions_prohibited"],
        metadata=_parse_mapping(data["metadata"], f"{path}.metadata"),
    )


def _parse_cell(value: Any, path: str) -> ClinicalEvidenceCell:
    fields = {
        "cell_id",
        "study_record_id",
        "trial_id",
        "design_id",
        "endpoint_id",
        "safety_id",
        "effect_measure",
        "effect_estimate",
        "confidence_interval_percent",
        "confidence_interval_lower",
        "confidence_interval_upper",
        "log_effect_ci_width",
        "benefit_direction",
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
        "safety_direction",
        "source_evidence_ids",
        "source_content_hashes",
        "endpoint_fingerprint_sha256",
        "safety_fingerprint_sha256",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceCell(
        **{
            **data,
            "source_evidence_ids": _parse_sequence(
                data["source_evidence_ids"],
                f"{path}.source_evidence_ids",
            ),
            "source_content_hashes": _parse_sequence(
                data["source_content_hashes"],
                f"{path}.source_content_hashes",
            ),
        }
    )


def _parse_gap(value: Any, path: str) -> ClinicalEvidenceGap:
    fields = {
        "gap_id",
        "code",
        "dimension",
        "summary",
        "gap_mass",
        "blocking",
        "study_record_ids",
        "source_evidence_ids",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceGap(
        gap_id=data["gap_id"],
        code=_parse_enum(
            ClinicalEvidenceGapCode,
            data["code"],
            f"{path}.code",
        ),
        dimension=_parse_enum(
            ClinicalEvidenceDimension,
            data["dimension"],
            f"{path}.dimension",
        ),
        summary=data["summary"],
        gap_mass=data["gap_mass"],
        blocking=data["blocking"],
        study_record_ids=_parse_sequence(
            data["study_record_ids"],
            f"{path}.study_record_ids",
        ),
        source_evidence_ids=_parse_sequence(
            data["source_evidence_ids"],
            f"{path}.source_evidence_ids",
        ),
    )


def _parse_dimension(
    value: Any,
    path: str,
) -> ClinicalEvidenceDimensionRecord:
    fields = {"dimension", "status", "observed", "criterion", "gap_ids"}
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceDimensionRecord(
        dimension=_parse_enum(
            ClinicalEvidenceDimension,
            data["dimension"],
            f"{path}.dimension",
        ),
        status=_parse_enum(
            ClinicalDimensionStatus,
            data["status"],
            f"{path}.status",
        ),
        observed=_parse_mapping(data["observed"], f"{path}.observed"),
        criterion=_parse_mapping(data["criterion"], f"{path}.criterion"),
        gap_ids=_parse_sequence(data["gap_ids"], f"{path}.gap_ids"),
    )


def _parse_tensor(value: Any, path: str) -> ClinicalEvidenceTensor:
    fields = {
        "tensor_id",
        "method_id",
        "program_id",
        "synthesis_id",
        "synthesis_fingerprint",
        "policy_id",
        "policy_version",
        "policy_fingerprint",
        "candidate_id",
        "intervention_id",
        "disease_id",
        "endpoint_mapping_id",
        "endpoint_family",
        "effect_measure",
        "safety_measure",
        "as_of_date",
        "stage",
        "cells",
        "dimensions",
        "gaps",
        "source_evidence_ids",
        "source_content_hashes",
        "pooling_performed",
        "cross_trial_comparability_inferred",
        "population_homogeneity_inferred",
        "clinical_acceptability_inferred",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceTensor(
        tensor_id=data["tensor_id"],
        method_id=data["method_id"],
        program_id=data["program_id"],
        synthesis_id=data["synthesis_id"],
        synthesis_fingerprint=data["synthesis_fingerprint"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        policy_fingerprint=data["policy_fingerprint"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        endpoint_mapping_id=data["endpoint_mapping_id"],
        endpoint_family=data["endpoint_family"],
        effect_measure=data["effect_measure"],
        safety_measure=data["safety_measure"],
        as_of_date=_parse_date(data["as_of_date"], f"{path}.as_of_date"),
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        cells=tuple(
            _parse_cell(item, f"{path}.cells[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["cells"], f"{path}.cells")
            )
        ),
        dimensions=tuple(
            _parse_dimension(item, f"{path}.dimensions[{index}]")
            for index, item in enumerate(
                _parse_sequence(
                    data["dimensions"],
                    f"{path}.dimensions",
                )
            )
        ),
        gaps=tuple(
            _parse_gap(item, f"{path}.gaps[{index}]")
            for index, item in enumerate(_parse_sequence(data["gaps"], f"{path}.gaps"))
        ),
        source_evidence_ids=_parse_sequence(
            data["source_evidence_ids"],
            f"{path}.source_evidence_ids",
        ),
        source_content_hashes=_parse_sequence(
            data["source_content_hashes"],
            f"{path}.source_content_hashes",
        ),
        pooling_performed=data["pooling_performed"],
        cross_trial_comparability_inferred=(data["cross_trial_comparability_inferred"]),
        population_homogeneity_inferred=(data["population_homogeneity_inferred"]),
        clinical_acceptability_inferred=(data["clinical_acceptability_inferred"]),
    )


def _parse_action_option(
    value: Any,
    path: str,
) -> ClinicalEvidenceActionOption:
    fields = {
        "action_id",
        "action_type",
        "tool_id",
        "operation",
        "purpose",
        "targeted_gap_codes",
        "expected_gap_resolution_probability",
        "decision_relevance",
        "max_cost",
        "arguments",
        "metadata",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceActionOption(
        action_id=data["action_id"],
        action_type=_parse_enum(
            ActionType,
            data["action_type"],
            f"{path}.action_type",
        ),
        tool_id=data["tool_id"],
        operation=data["operation"],
        purpose=data["purpose"],
        targeted_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.targeted_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["targeted_gap_codes"],
                    f"{path}.targeted_gap_codes",
                )
            )
        ),
        expected_gap_resolution_probability=(
            data["expected_gap_resolution_probability"]
        ),
        decision_relevance=data["decision_relevance"],
        max_cost=data["max_cost"],
        arguments=_parse_mapping(data["arguments"], f"{path}.arguments"),
        metadata=_parse_mapping(data["metadata"], f"{path}.metadata"),
    )


def clinical_decision_policy_from_dict(
    value: Any,
    path: str = "clinical_decision_policy",
) -> ClinicalDecisionPolicy:
    """Parse one strict, fail-closed clinical evidence policy."""

    return _parse_policy(value, path)


def clinical_evidence_action_option_from_dict(
    value: Any,
    path: str = "clinical_evidence_action_option",
) -> ClinicalEvidenceActionOption:
    """Parse one strict action-catalog entry."""

    return _parse_action_option(value, path)


def clinical_evidence_action_catalog_from_dict(
    value: Any,
    path: str = "clinical_evidence_action_catalog",
) -> tuple[ClinicalEvidenceActionOption, ...]:
    """Parse an action catalog and reject ambiguous duplicate action ids."""

    catalog = tuple(
        _parse_action_option(item, f"{path}[{index}]")
        for index, item in enumerate(_parse_sequence(value, path))
    )
    action_ids = tuple(item.action_id for item in catalog)
    if len(action_ids) != len(set(action_ids)):
        raise RecordParseError(f"{path} action ids must be unique")
    return catalog


def _parse_action_selection(
    value: Any,
    path: str,
) -> ClinicalEvidenceActionSelection:
    fields = {
        "rank",
        "action_id",
        "action_fingerprint",
        "targeted_gap_ids",
        "marginal_gap_mass",
        "bounded_voi",
        "voi_per_cost",
        "max_cost",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceActionSelection(
        rank=data["rank"],
        action_id=data["action_id"],
        action_fingerprint=data["action_fingerprint"],
        targeted_gap_ids=_parse_sequence(
            data["targeted_gap_ids"],
            f"{path}.targeted_gap_ids",
        ),
        marginal_gap_mass=data["marginal_gap_mass"],
        bounded_voi=data["bounded_voi"],
        voi_per_cost=data["voi_per_cost"],
        max_cost=data["max_cost"],
    )


def _parse_plan(value: Any, path: str) -> ClinicalDecisionPlan:
    fields = {
        "plan_id",
        "tensor_id",
        "tensor_fingerprint",
        "policy_id",
        "policy_version",
        "policy_fingerprint",
        "decision",
        "code",
        "rationale_codes",
        "selected_actions",
        "open_gap_ids",
        "targeted_gap_ids",
        "untargeted_gap_ids",
        "budget_limit",
        "budget_spent",
        "budget_available",
        "planned_cost",
        "budget_remaining_after_plan",
        "voi_method_id",
        "workflow_scope",
        "clinical_acceptability_inferred",
        "terminal_decision_issued",
    }
    data = _parse_record(value, path, fields)
    return ClinicalDecisionPlan(
        plan_id=data["plan_id"],
        tensor_id=data["tensor_id"],
        tensor_fingerprint=data["tensor_fingerprint"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        policy_fingerprint=data["policy_fingerprint"],
        decision=_parse_enum(
            Decision,
            data["decision"],
            f"{path}.decision",
        ),
        code=data["code"],
        rationale_codes=_parse_sequence(
            data["rationale_codes"],
            f"{path}.rationale_codes",
        ),
        selected_actions=tuple(
            _parse_action_selection(
                item,
                f"{path}.selected_actions[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["selected_actions"],
                    f"{path}.selected_actions",
                )
            )
        ),
        open_gap_ids=_parse_sequence(
            data["open_gap_ids"],
            f"{path}.open_gap_ids",
        ),
        targeted_gap_ids=_parse_sequence(
            data["targeted_gap_ids"],
            f"{path}.targeted_gap_ids",
        ),
        untargeted_gap_ids=_parse_sequence(
            data["untargeted_gap_ids"],
            f"{path}.untargeted_gap_ids",
        ),
        budget_limit=data["budget_limit"],
        budget_spent=data["budget_spent"],
        budget_available=data["budget_available"],
        planned_cost=data["planned_cost"],
        budget_remaining_after_plan=data["budget_remaining_after_plan"],
        voi_method_id=data["voi_method_id"],
        workflow_scope=data["workflow_scope"],
        clinical_acceptability_inferred=(data["clinical_acceptability_inferred"]),
        terminal_decision_issued=data["terminal_decision_issued"],
    )


def clinical_decision_package_from_dict(
    value: Any,
) -> ClinicalDecisionPackage:
    """Parse one strict integrity-bound clinical decision package."""

    envelope = _parse_record(
        value,
        "clinical_decision_package_envelope",
        {"schema_version", "integrity_sha256", "package"},
    )
    if envelope["schema_version"] != CLINICAL_DECISION_PACKAGE_SCHEMA_VERSION:
        raise RecordParseError(
            "clinical decision package schema_version is unsupported"
        )
    expected_hash = envelope["integrity_sha256"]
    if (
        not isinstance(expected_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
    ):
        raise RecordParseError("clinical decision package integrity_sha256 is invalid")
    raw = _parse_mapping(
        envelope["package"],
        "clinical_decision_package_envelope.package",
    )
    if _sha256(raw) != expected_hash:
        raise RecordParseError(
            "clinical decision package integrity hash does not match"
        )
    path = "clinical_decision_package_envelope.package"
    data = _parse_record(
        raw,
        path,
        {
            "package_id",
            "program_id",
            "as_of_date",
            "policy",
            "action_catalog",
            "tensor",
            "plan",
            "limitations",
        },
    )
    package = ClinicalDecisionPackage(
        package_id=data["package_id"],
        program_id=data["program_id"],
        as_of_date=_parse_date(data["as_of_date"], f"{path}.as_of_date"),
        policy=_parse_policy(data["policy"], f"{path}.policy"),
        action_catalog=tuple(
            _parse_action_option(
                item,
                f"{path}.action_catalog[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["action_catalog"],
                    f"{path}.action_catalog",
                )
            )
        ),
        tensor=_parse_tensor(data["tensor"], f"{path}.tensor"),
        plan=_parse_plan(data["plan"], f"{path}.plan"),
        limitations=_parse_sequence(
            data["limitations"],
            f"{path}.limitations",
        ),
    )
    if package.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed clinical decision package changed canonical identity"
        )
    return package


def _parse_envelope_json(payload: str) -> Any:
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RecordParseError(
                    f"clinical decision package duplicates key {key}"
                )
            result[key] = item
        return result

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RecordParseError(f"clinical decision package contains {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError("clinical decision package is not valid JSON") from exc


def clinical_decision_package_from_json(
    payload: str,
) -> ClinicalDecisionPackage:
    """Parse JSON without duplicate keys or non-finite numeric values."""

    return clinical_decision_package_from_dict(_parse_envelope_json(payload))
