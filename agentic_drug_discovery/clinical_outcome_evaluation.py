"""Preregistered outcome evaluation for clinical evidence packages."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from itertools import combinations
from statistics import NormalDist
from typing import Any

from .clinical_cohort import (
    ClinicalCohortPolicyIdentity,
    ClinicalCohortReport,
)
from .heldout_evaluation import BinomialEstimate, IntervalMethod
from .matched_evaluation import _contains_evaluator_key
from .models import (
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _require_date,
    _require_instance,
    _require_probability,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_OUTCOME_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-evaluation-protocol.v1"
)
CLINICAL_PREDICTION_SUBMISSION_SCHEMA_VERSION = "adds.clinical-prediction-submission.v1"
CLINICAL_OUTCOME_MANIFEST_SCHEMA_VERSION = "adds.clinical-outcome-manifest.v1"
CLINICAL_OUTCOME_REPORT_SCHEMA_VERSION = "adds.clinical-outcome-evaluation-report.v1"
CLINICAL_OUTCOME_SUMMARY_SCHEMA_VERSION = "adds.clinical-outcome-evaluation-summary.v1"
CLINICAL_OUTCOME_EVALUATION_METHOD_ID = (
    "adds.preregistered-clinical-outcome-evaluation.v1"
)
CLINICAL_OUTCOME_PREDICTION_TARGET = (
    "probability_of_favorable_composite_benefit_risk_outcome"
)
CLINICAL_OUTCOME_COMPOSITE_RULE_ID = (
    "unfavorable_if_either_domain_unfavorable_otherwise_both_favorable.v1"
)

_CALIBRATION_STATUSES = {
    "preregistered_outcome_calibration_estimable",
    "partially_estimable",
    "not_estimable_insufficient_evaluable_units",
}
_REQUIRED_LIMITATIONS = (
    (
        "Submitted favorable-outcome probabilities are separate forecasts bound "
        "to packages; package ADVANCE, HOLD, and DEFER decisions are not scored "
        "as clinical outcomes."
    ),
    (
        "Indeterminate outcomes are retained in attrition counts and excluded "
        "from binary performance and calibration denominators."
    ),
    (
        "Wilson intervals quantify finite evaluable-unit uncertainty only and do "
        "not adjust for cross-unit dependence, outcome adjudication uncertainty, "
        "or repeated policies on the same unit."
    ),
    (
        "Calibration bins, expected calibration error, and Brier scores are "
        "descriptive for the preregistered target and window; they do not prove "
        "transportability or policy superiority."
    ),
    (
        "Novel post-deadline source hashes prevent exact baseline artifact reuse "
        "but do not establish causal independence, absence of bias, or complete "
        "outcome ascertainment."
    ),
    (
        "Aggregate evaluation does not establish treatment efficacy, safety, "
        "clinical utility, regulatory acceptability, or a treatment recommendation."
    ),
)


class ClinicalOutcomeEvaluationError(ValueError):
    """Raised when clinical outcome evaluation cannot proceed safely."""


class ClinicalOutcomeStatus(str, Enum):
    FAVORABLE = "favorable"
    UNFAVORABLE = "unfavorable"
    INDETERMINATE = "indeterminate"


class ClinicalOutcomeDomain(str, Enum):
    ENDPOINT = "endpoint"
    SAFETY = "safety"


_STATUS_ORDER = tuple(ClinicalOutcomeStatus)
_DOMAIN_ORDER = {item: index for index, item in enumerate(ClinicalOutcomeDomain)}
_HIDDEN_OUTCOME_METADATA_TOKENS = {
    "adjudication",
    "assessment",
    "gold",
    "label",
    "outcome",
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


def _round_metric(value: float) -> float:
    return round(float(value), 12)


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_optional_probability(
    value: float | None,
    field_name: str,
) -> None:
    if value is not None:
        _require_probability(value, field_name)


def _require_finite_metric(
    value: float | None,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")


def _composite_status(
    endpoint_status: ClinicalOutcomeStatus,
    safety_status: ClinicalOutcomeStatus,
) -> ClinicalOutcomeStatus:
    if ClinicalOutcomeStatus.UNFAVORABLE in (endpoint_status, safety_status):
        return ClinicalOutcomeStatus.UNFAVORABLE
    if (
        endpoint_status is ClinicalOutcomeStatus.FAVORABLE
        and safety_status is ClinicalOutcomeStatus.FAVORABLE
    ):
        return ClinicalOutcomeStatus.FAVORABLE
    return ClinicalOutcomeStatus.INDETERMINATE


def _contains_hidden_outcome_metadata(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            expanded = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])",
                "_",
                str(key),
            )
            normalized = "_".join(re.findall(r"[a-z0-9]+", expanded.casefold()))
            if set(normalized.split("_")) & _HIDDEN_OUTCOME_METADATA_TOKENS:
                return True
            if _contains_hidden_outcome_metadata(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_hidden_outcome_metadata(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeEvaluationProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    cohort_id: str
    cohort_specification_sha256: str
    cohort_report_fingerprint: str
    prediction_deadline: date
    outcome_window_start: date
    outcome_window_end: date
    endpoint_harmonization_policy_sha256: str
    safety_harmonization_policy_sha256: str
    outcome_definition_sha256: str
    label_guidance_sha256: str
    exclusion_rules_sha256: str
    curator_roster_commitment: str
    minimum_independent_curators: int
    minimum_evaluable_units: int
    classification_threshold: float
    calibration_bin_edges: tuple[float, ...]
    confidence_level: float
    prediction_target: str = CLINICAL_OUTCOME_PREDICTION_TARGET
    composite_rule_id: str = CLINICAL_OUTCOME_COMPOSITE_RULE_ID
    interval_method: IntervalMethod = IntervalMethod.WILSON_SCORE
    policy_blinding_required: bool = True
    conflict_free_required: bool = True
    adjudicator_independence_required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version", "cohort_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "registered_on",
            "prediction_deadline",
            "outcome_window_start",
            "outcome_window_end",
        ):
            _require_date(getattr(self, field_name), field_name)
        if not (
            self.registered_on
            <= self.prediction_deadline
            < self.outcome_window_start
            <= self.outcome_window_end
        ):
            raise ValueError("protocol dates do not preserve prediction/outcome order")
        for field_name in (
            "cohort_specification_sha256",
            "cohort_report_fingerprint",
            "endpoint_harmonization_policy_sha256",
            "safety_harmonization_policy_sha256",
            "outcome_definition_sha256",
            "label_guidance_sha256",
            "exclusion_rules_sha256",
            "curator_roster_commitment",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_positive_int(
            self.minimum_independent_curators,
            "minimum_independent_curators",
        )
        if self.minimum_independent_curators < 2:
            raise ValueError("clinical outcomes require at least two curators")
        _require_positive_int(self.minimum_evaluable_units, "minimum_evaluable_units")
        _require_probability(self.classification_threshold, "classification_threshold")
        if self.classification_threshold in (0.0, 1.0):
            raise ValueError(
                "classification_threshold must be strictly between 0 and 1"
            )
        edges = _tuple(self.calibration_bin_edges, "calibration_bin_edges")
        object.__setattr__(self, "calibration_bin_edges", edges)
        if len(edges) < 3:
            raise ValueError("calibration_bin_edges require at least two bins")
        for index, edge in enumerate(edges):
            _require_probability(edge, f"calibration_bin_edges[{index}]")
        if edges[0] != 0.0 or edges[-1] != 1.0:
            raise ValueError("calibration_bin_edges must start at 0 and end at 1")
        if any(left >= right for left, right in zip(edges, edges[1:])):
            raise ValueError("calibration_bin_edges must be strictly increasing")
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if self.prediction_target != CLINICAL_OUTCOME_PREDICTION_TARGET:
            raise ValueError("prediction_target is unsupported")
        if self.composite_rule_id != CLINICAL_OUTCOME_COMPOSITE_RULE_ID:
            raise ValueError("composite_rule_id is unsupported")
        _require_instance(self.interval_method, IntervalMethod, "interval_method")
        if self.interval_method is not IntervalMethod.WILSON_SCORE:
            raise ValueError("interval_method is unsupported")
        for field_name in (
            "policy_blinding_required",
            "conflict_free_required",
            "adjudicator_independence_required",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError("protocol metadata cannot contain evaluator outcomes")
        object.__setattr__(self, "metadata", metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalFavorableOutcomePrediction(SerializableRecord):
    package_id: str
    package_integrity_sha256: str
    evidence_unit_id: str
    favorable_probability: float

    def __post_init__(self) -> None:
        _require_text(self.package_id, "package_id")
        _require_sha256(self.package_integrity_sha256, "package_integrity_sha256")
        _require_sha256(self.evidence_unit_id, "evidence_unit_id")
        _require_probability(self.favorable_probability, "favorable_probability")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.evidence_unit_id, self.package_id)


@dataclass(frozen=True, slots=True)
class ClinicalPredictionSubmission(SerializableRecord):
    submission_id: str
    protocol_id: str
    protocol_fingerprint: str
    cohort_report_fingerprint: str
    policy: ClinicalCohortPolicyIdentity
    submitted_on: date
    predictions: tuple[ClinicalFavorableOutcomePrediction, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "protocol_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.protocol_fingerprint, "protocol_fingerprint")
        _require_sha256(self.cohort_report_fingerprint, "cohort_report_fingerprint")
        _require_instance(self.policy, ClinicalCohortPolicyIdentity, "policy")
        _require_date(self.submitted_on, "submitted_on")
        predictions = _tuple(self.predictions, "predictions")
        object.__setattr__(self, "predictions", predictions)
        if not predictions:
            raise ValueError("prediction submission must not be empty")
        for prediction in predictions:
            _require_instance(
                prediction,
                ClinicalFavorableOutcomePrediction,
                "predictions item",
            )
        if tuple(item.sort_key for item in predictions) != tuple(
            sorted(item.sort_key for item in predictions)
        ):
            raise ValueError("predictions must use canonical evidence-unit order")
        if len({item.package_id for item in predictions}) != len(predictions):
            raise ValueError("prediction package ids must be unique")
        if len({item.evidence_unit_id for item in predictions}) != len(predictions):
            raise ValueError("one policy can predict each evidence unit once")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError("submission metadata cannot contain evaluator outcomes")
        object.__setattr__(self, "metadata", metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeSource(SerializableRecord):
    source_id: str
    source_version: str
    source_content_sha256: str
    available_on: date
    domains: tuple[ClinicalOutcomeDomain, ...]
    trial_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("source_id", "source_version"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        _require_date(self.available_on, "available_on")
        domains = _tuple(self.domains, "domains")
        object.__setattr__(self, "domains", domains)
        if not domains:
            raise ValueError("outcome source requires at least one domain")
        for domain in domains:
            _require_instance(domain, ClinicalOutcomeDomain, "domains item")
        if len(domains) != len(set(domains)):
            raise ValueError("outcome source domains must be unique")
        if domains != tuple(sorted(domains, key=_DOMAIN_ORDER.__getitem__)):
            raise ValueError("outcome source domains must use canonical order")
        if self.trial_id is not None:
            _require_text(self.trial_id, "trial_id")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.source_content_sha256, self.source_id, self.source_version)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeAssessment(SerializableRecord):
    evidence_unit_id: str
    program_id: str
    disease_id: str
    candidate_id: str
    intervention_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    stage: Stage
    assessment_date: date
    endpoint_status: ClinicalOutcomeStatus
    safety_status: ClinicalOutcomeStatus
    composite_status: ClinicalOutcomeStatus
    sources: tuple[ClinicalOutcomeSource, ...]
    endpoint_assessment_sha256: str
    safety_assessment_sha256: str
    adjudication_sha256: str
    independent_curator_count: int
    policy_blinded: bool = True
    conflict_free: bool = True
    adjudicator_independent: bool = True

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_unit_id, "evidence_unit_id")
        for field_name in (
            "program_id",
            "disease_id",
            "candidate_id",
            "intervention_id",
            "endpoint_mapping_id",
            "endpoint_family",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.stage, Stage, "stage")
        _require_date(self.assessment_date, "assessment_date")
        for field_name in (
            "endpoint_status",
            "safety_status",
            "composite_status",
        ):
            _require_instance(
                getattr(self, field_name),
                ClinicalOutcomeStatus,
                field_name,
            )
        expected = _composite_status(self.endpoint_status, self.safety_status)
        if self.composite_status is not expected:
            raise ValueError("composite_status does not match the registered rule")
        sources = _tuple(self.sources, "sources")
        object.__setattr__(self, "sources", sources)
        if not sources:
            raise ValueError("outcome assessment requires sources")
        for source in sources:
            _require_instance(source, ClinicalOutcomeSource, "sources item")
        if tuple(item.sort_key for item in sources) != tuple(
            sorted(item.sort_key for item in sources)
        ):
            raise ValueError("outcome sources must use canonical content-hash order")
        hashes = tuple(item.source_content_sha256 for item in sources)
        if len(hashes) != len(set(hashes)):
            raise ValueError("outcome source content hashes must be unique per unit")
        covered_domains = {domain for source in sources for domain in source.domains}
        if covered_domains != set(ClinicalOutcomeDomain):
            raise ValueError("outcome sources must cover endpoint and safety")
        for field_name in (
            "endpoint_assessment_sha256",
            "safety_assessment_sha256",
            "adjudication_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_positive_int(
            self.independent_curator_count, "independent_curator_count"
        )
        for field_name in (
            "policy_blinded",
            "conflict_free",
            "adjudicator_independent",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeManifest(SerializableRecord):
    manifest_id: str
    protocol_id: str
    protocol_fingerprint: str
    cohort_report_fingerprint: str
    curator_roster_commitment: str
    frozen_on: date
    assessments: tuple[ClinicalOutcomeAssessment, ...]

    def __post_init__(self) -> None:
        for field_name in ("manifest_id", "protocol_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "cohort_report_fingerprint",
            "curator_roster_commitment",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_date(self.frozen_on, "frozen_on")
        assessments = _tuple(self.assessments, "assessments")
        object.__setattr__(self, "assessments", assessments)
        if not assessments:
            raise ValueError("outcome manifest must not be empty")
        for assessment in assessments:
            _require_instance(
                assessment,
                ClinicalOutcomeAssessment,
                "assessments item",
            )
        unit_ids = tuple(item.evidence_unit_id for item in assessments)
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("outcome evidence-unit ids must be unique")
        if unit_ids != tuple(sorted(unit_ids)):
            raise ValueError("outcome assessments must use canonical unit order")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _wilson_interval(
    event_count: int,
    total: int,
    confidence_level: float,
) -> tuple[float, float]:
    estimate = event_count / total
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (estimate + z_squared / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(estimate * (1 - estimate) / total + z_squared / (4 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _binomial_estimate(
    event_count: int,
    total: int,
    protocol: ClinicalOutcomeEvaluationProtocol,
) -> BinomialEstimate:
    if total == 0:
        estimate = lower = upper = None
    else:
        estimate = event_count / total
        lower, upper = _wilson_interval(
            event_count,
            total,
            protocol.confidence_level,
        )
    return BinomialEstimate(
        event_count=event_count,
        total=total,
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence_level=protocol.confidence_level,
        method=protocol.interval_method,
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStatusCount(SerializableRecord):
    status: ClinicalOutcomeStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(self.status, ClinicalOutcomeStatus, "status")
        _require_non_negative_int(self.count, "count")


@dataclass(frozen=True, slots=True)
class ClinicalConfusionMatrix(SerializableRecord):
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    def __post_init__(self) -> None:
        for field_name in (
            "true_positive",
            "false_positive",
            "true_negative",
            "false_negative",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)

    @property
    def total(self) -> int:
        return (
            self.true_positive
            + self.false_positive
            + self.true_negative
            + self.false_negative
        )


@dataclass(frozen=True, slots=True)
class ClinicalCalibrationBin(SerializableRecord):
    lower_bound: float
    upper_bound: float
    includes_upper_bound: bool
    unit_count: int
    mean_predicted_probability: float | None
    observed_favorable_rate: BinomialEstimate
    calibration_gap: float | None

    def __post_init__(self) -> None:
        _require_probability(self.lower_bound, "lower_bound")
        _require_probability(self.upper_bound, "upper_bound")
        if self.lower_bound >= self.upper_bound:
            raise ValueError("calibration bin bounds must be increasing")
        _require_bool(self.includes_upper_bound, "includes_upper_bound")
        _require_non_negative_int(self.unit_count, "unit_count")
        _require_optional_probability(
            self.mean_predicted_probability,
            "mean_predicted_probability",
        )
        _require_instance(
            self.observed_favorable_rate,
            BinomialEstimate,
            "observed_favorable_rate",
        )
        if self.observed_favorable_rate.total != self.unit_count:
            raise ValueError("calibration bin outcome denominator is inconsistent")
        _require_finite_metric(
            self.calibration_gap,
            "calibration_gap",
            minimum=-1.0,
            maximum=1.0,
        )
        if self.unit_count == 0:
            if (
                self.mean_predicted_probability is not None
                or self.calibration_gap is not None
            ):
                raise ValueError("empty calibration bins require null metrics")
        else:
            if self.mean_predicted_probability is None or self.calibration_gap is None:
                raise ValueError("non-empty calibration bins require metrics")
            observed = self.observed_favorable_rate.estimate
            assert observed is not None
            expected_gap = _round_metric(self.mean_predicted_probability - observed)
            if not math.isclose(
                self.calibration_gap,
                expected_gap,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("calibration_gap is inconsistent")
            upper_ok = (
                self.mean_predicted_probability <= self.upper_bound
                if self.includes_upper_bound
                else self.mean_predicted_probability < self.upper_bound
            )
            if not self.lower_bound <= self.mean_predicted_probability or not upper_ok:
                raise ValueError("calibration-bin mean falls outside its bounds")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePolicyMetrics(SerializableRecord):
    policy: ClinicalCohortPolicyIdentity
    submission_id: str
    submission_fingerprint: str
    total_units: int
    evaluable_units: int
    indeterminate_units: int
    minimum_evaluable_units: int
    evaluation_requirement_met: bool
    classification_threshold: float
    mean_predicted_probability: float | None
    observed_favorable_rate: BinomialEstimate
    predicted_favorable_rate: BinomialEstimate
    confusion_matrix: ClinicalConfusionMatrix
    classification_accuracy: BinomialEstimate
    sensitivity: BinomialEstimate
    specificity: BinomialEstimate
    positive_predictive_value: BinomialEstimate
    negative_predictive_value: BinomialEstimate
    brier_score: float | None
    calibration_in_the_large: float | None
    expected_calibration_error: float | None
    calibration_bins: tuple[ClinicalCalibrationBin, ...]

    def __post_init__(self) -> None:
        _require_instance(self.policy, ClinicalCohortPolicyIdentity, "policy")
        _require_text(self.submission_id, "submission_id")
        _require_sha256(self.submission_fingerprint, "submission_fingerprint")
        _require_positive_int(self.total_units, "total_units")
        _require_non_negative_int(self.evaluable_units, "evaluable_units")
        _require_non_negative_int(self.indeterminate_units, "indeterminate_units")
        if self.evaluable_units + self.indeterminate_units != self.total_units:
            raise ValueError("outcome attrition counts do not sum to total units")
        _require_positive_int(self.minimum_evaluable_units, "minimum_evaluable_units")
        _require_bool(self.evaluation_requirement_met, "evaluation_requirement_met")
        if self.evaluation_requirement_met != (
            self.evaluable_units >= self.minimum_evaluable_units
        ):
            raise ValueError("evaluation_requirement_met is inconsistent")
        _require_probability(self.classification_threshold, "classification_threshold")
        _require_optional_probability(
            self.mean_predicted_probability,
            "mean_predicted_probability",
        )
        for field_name in (
            "observed_favorable_rate",
            "predicted_favorable_rate",
            "classification_accuracy",
            "sensitivity",
            "specificity",
            "positive_predictive_value",
            "negative_predictive_value",
        ):
            _require_instance(getattr(self, field_name), BinomialEstimate, field_name)
        estimates = tuple(
            getattr(self, field_name)
            for field_name in (
                "observed_favorable_rate",
                "predicted_favorable_rate",
                "classification_accuracy",
                "sensitivity",
                "specificity",
                "positive_predictive_value",
                "negative_predictive_value",
            )
        )
        if len({item.confidence_level for item in estimates}) != 1:
            raise ValueError("policy metric confidence levels must be consistent")
        if len({item.method for item in estimates}) != 1:
            raise ValueError("policy metric interval methods must be consistent")
        _require_instance(
            self.confusion_matrix, ClinicalConfusionMatrix, "confusion_matrix"
        )
        if self.confusion_matrix.total != self.evaluable_units:
            raise ValueError("confusion matrix denominator is inconsistent")
        matrix = self.confusion_matrix
        expected_counts = (
            (
                self.observed_favorable_rate,
                matrix.true_positive + matrix.false_negative,
                self.evaluable_units,
                "observed_favorable_rate",
            ),
            (
                self.predicted_favorable_rate,
                matrix.true_positive + matrix.false_positive,
                self.evaluable_units,
                "predicted_favorable_rate",
            ),
            (
                self.classification_accuracy,
                matrix.true_positive + matrix.true_negative,
                self.evaluable_units,
                "classification_accuracy",
            ),
            (
                self.sensitivity,
                matrix.true_positive,
                matrix.true_positive + matrix.false_negative,
                "sensitivity",
            ),
            (
                self.specificity,
                matrix.true_negative,
                matrix.true_negative + matrix.false_positive,
                "specificity",
            ),
            (
                self.positive_predictive_value,
                matrix.true_positive,
                matrix.true_positive + matrix.false_positive,
                "positive_predictive_value",
            ),
            (
                self.negative_predictive_value,
                matrix.true_negative,
                matrix.true_negative + matrix.false_negative,
                "negative_predictive_value",
            ),
        )
        for estimate, event_count, total, field_name in expected_counts:
            if (estimate.event_count, estimate.total) != (event_count, total):
                raise ValueError(f"{field_name} counts are inconsistent")
        for field_name in (
            "brier_score",
            "expected_calibration_error",
        ):
            _require_finite_metric(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
                maximum=1.0,
            )
        _require_finite_metric(
            self.calibration_in_the_large,
            "calibration_in_the_large",
            minimum=-1.0,
            maximum=1.0,
        )
        bins = _tuple(self.calibration_bins, "calibration_bins")
        object.__setattr__(self, "calibration_bins", bins)
        if len(bins) < 2:
            raise ValueError("calibration_bins require at least two bins")
        for item in bins:
            _require_instance(item, ClinicalCalibrationBin, "calibration_bins item")
        if bins[0].lower_bound != 0.0 or bins[-1].upper_bound != 1.0:
            raise ValueError("calibration bins must cover the unit interval")
        if any(
            left.upper_bound != right.lower_bound for left, right in zip(bins, bins[1:])
        ):
            raise ValueError("calibration bins must be contiguous")
        if any(item.includes_upper_bound for item in bins[:-1]):
            raise ValueError("only the final calibration bin includes its upper bound")
        if not bins[-1].includes_upper_bound:
            raise ValueError("the final calibration bin must include one")
        if sum(item.unit_count for item in bins) != self.evaluable_units:
            raise ValueError("calibration-bin counts do not sum to evaluable units")
        if (
            sum(item.observed_favorable_rate.event_count for item in bins)
            != self.observed_favorable_rate.event_count
        ):
            raise ValueError("calibration-bin events do not sum to favorable outcomes")
        if any(
            item.observed_favorable_rate.confidence_level
            != self.observed_favorable_rate.confidence_level
            or item.observed_favorable_rate.method
            is not self.observed_favorable_rate.method
            for item in bins
        ):
            raise ValueError("calibration-bin interval policies are inconsistent")
        optional_metrics = (
            self.mean_predicted_probability,
            self.brier_score,
            self.calibration_in_the_large,
            self.expected_calibration_error,
        )
        if self.evaluable_units == 0:
            if any(value is not None for value in optional_metrics):
                raise ValueError("zero evaluable units require null scalar metrics")
        else:
            if any(value is None for value in optional_metrics):
                raise ValueError("evaluable units require scalar metrics")
            assert self.mean_predicted_probability is not None
            assert self.observed_favorable_rate.estimate is not None
            expected_calibration = _round_metric(
                self.mean_predicted_probability - self.observed_favorable_rate.estimate
            )
            if not math.isclose(
                self.calibration_in_the_large,
                expected_calibration,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("calibration_in_the_large is inconsistent")
            weighted_probability = _round_metric(
                sum(
                    item.unit_count * (item.mean_predicted_probability or 0.0)
                    for item in bins
                )
                / self.evaluable_units
            )
            if not math.isclose(
                self.mean_predicted_probability,
                weighted_probability,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("mean prediction does not match calibration bins")
            expected_ece = _round_metric(
                sum(item.unit_count * abs(item.calibration_gap or 0.0) for item in bins)
                / self.evaluable_units
            )
            if not math.isclose(
                self.expected_calibration_error,
                expected_ece,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("expected_calibration_error is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalMatchedOutcomeComparison(SerializableRecord):
    policy_a: ClinicalCohortPolicyIdentity
    policy_b: ClinicalCohortPolicyIdentity
    shared_units: int
    shared_evaluable_units: int
    shared_indeterminate_units: int
    mean_brier_a: float | None
    mean_brier_b: float | None
    mean_brier_difference_b_minus_a: float | None
    policy_a_lower_brier_units: int
    equal_brier_units: int
    policy_b_lower_brier_units: int
    classification_disagreement_units: int

    def __post_init__(self) -> None:
        for field_name in ("policy_a", "policy_b"):
            _require_instance(
                getattr(self, field_name),
                ClinicalCohortPolicyIdentity,
                field_name,
            )
        if self.policy_a.sort_key >= self.policy_b.sort_key:
            raise ValueError("matched policies must use canonical order")
        _require_positive_int(self.shared_units, "shared_units")
        _require_non_negative_int(self.shared_evaluable_units, "shared_evaluable_units")
        _require_non_negative_int(
            self.shared_indeterminate_units,
            "shared_indeterminate_units",
        )
        if (
            self.shared_evaluable_units + self.shared_indeterminate_units
            != self.shared_units
        ):
            raise ValueError("matched outcome counts do not sum to shared units")
        for field_name in (
            "policy_a_lower_brier_units",
            "equal_brier_units",
            "policy_b_lower_brier_units",
            "classification_disagreement_units",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if (
            self.policy_a_lower_brier_units
            + self.equal_brier_units
            + self.policy_b_lower_brier_units
            != self.shared_evaluable_units
        ):
            raise ValueError("paired Brier counts do not partition evaluable units")
        if self.classification_disagreement_units > self.shared_evaluable_units:
            raise ValueError("classification disagreements exceed evaluable units")
        for field_name in ("mean_brier_a", "mean_brier_b"):
            _require_finite_metric(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
                maximum=1.0,
            )
        _require_finite_metric(
            self.mean_brier_difference_b_minus_a,
            "mean_brier_difference_b_minus_a",
            minimum=-1.0,
            maximum=1.0,
        )
        values = (
            self.mean_brier_a,
            self.mean_brier_b,
            self.mean_brier_difference_b_minus_a,
        )
        if self.shared_evaluable_units == 0:
            if any(value is not None for value in values):
                raise ValueError("empty paired evaluations require null Brier metrics")
        else:
            if any(value is None for value in values):
                raise ValueError("paired evaluations require Brier metrics")
            assert self.mean_brier_a is not None
            assert self.mean_brier_b is not None
            expected = _round_metric(self.mean_brier_b - self.mean_brier_a)
            if not math.isclose(
                self.mean_brier_difference_b_minus_a,
                expected,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("paired Brier difference is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeEvaluationReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    cohort_id: str
    cohort_report_fingerprint: str
    outcome_manifest_fingerprint: str
    method_id: str
    generated_on: date
    outcome_unit_count: int
    evaluable_outcome_unit_count: int
    indeterminate_outcome_unit_count: int
    submission_count: int
    endpoint_status_counts: tuple[ClinicalOutcomeStatusCount, ...]
    safety_status_counts: tuple[ClinicalOutcomeStatusCount, ...]
    composite_status_counts: tuple[ClinicalOutcomeStatusCount, ...]
    policy_summaries: tuple[ClinicalOutcomePolicyMetrics, ...]
    matched_policy_comparisons: tuple[ClinicalMatchedOutcomeComparison, ...]
    baseline_outcome_source_overlap_count: int
    outcome_cross_unit_source_overlap_count: int
    outcome_cross_unit_trial_overlap_count: int
    outcome_units_source_disjoint: bool
    outcome_units_trial_disjoint: bool
    aggregate_outcomes_included: bool
    unit_level_predictions_included: bool
    unit_level_outcomes_included: bool
    package_decisions_scored_as_outcomes: bool
    calibration_status: str
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "cohort_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "cohort_report_fingerprint",
            "outcome_manifest_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_EVALUATION_METHOD_ID:
            raise ValueError("method_id is unsupported")
        _require_date(self.generated_on, "generated_on")
        _require_positive_int(self.outcome_unit_count, "outcome_unit_count")
        _require_non_negative_int(
            self.evaluable_outcome_unit_count,
            "evaluable_outcome_unit_count",
        )
        _require_non_negative_int(
            self.indeterminate_outcome_unit_count,
            "indeterminate_outcome_unit_count",
        )
        if (
            self.evaluable_outcome_unit_count + self.indeterminate_outcome_unit_count
            != self.outcome_unit_count
        ):
            raise ValueError("global outcome counts do not sum to outcome units")
        _require_positive_int(self.submission_count, "submission_count")
        for field_name in (
            "endpoint_status_counts",
            "safety_status_counts",
            "composite_status_counts",
        ):
            counts = _tuple(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, counts)
            if tuple(item.status for item in counts) != _STATUS_ORDER:
                raise ValueError(
                    f"{field_name} must use complete canonical status order"
                )
            if any(not isinstance(item, ClinicalOutcomeStatusCount) for item in counts):
                raise TypeError(
                    f"{field_name} items must be ClinicalOutcomeStatusCount"
                )
            if sum(item.count for item in counts) != self.outcome_unit_count:
                raise ValueError(f"{field_name} does not sum to outcome units")
        composite = {item.status: item.count for item in self.composite_status_counts}
        if (
            composite[ClinicalOutcomeStatus.INDETERMINATE]
            != self.indeterminate_outcome_unit_count
            or composite[ClinicalOutcomeStatus.FAVORABLE]
            + composite[ClinicalOutcomeStatus.UNFAVORABLE]
            != self.evaluable_outcome_unit_count
        ):
            raise ValueError("composite status counts are inconsistent")
        summaries = _tuple(self.policy_summaries, "policy_summaries")
        object.__setattr__(self, "policy_summaries", summaries)
        if len(summaries) != self.submission_count:
            raise ValueError("submission_count does not match policy summaries")
        for item in summaries:
            _require_instance(
                item, ClinicalOutcomePolicyMetrics, "policy_summaries item"
            )
        if tuple(item.policy.sort_key for item in summaries) != tuple(
            sorted(item.policy.sort_key for item in summaries)
        ):
            raise ValueError("policy summaries must use canonical order")
        if len({item.policy.policy_fingerprint for item in summaries}) != len(
            summaries
        ):
            raise ValueError("policy summary identities must be unique")
        if len({item.submission_id for item in summaries}) != len(summaries):
            raise ValueError("policy summary submission ids must be unique")
        if len({item.submission_fingerprint for item in summaries}) != len(summaries):
            raise ValueError("policy summary submission fingerprints must be unique")
        favorable_outcomes = next(
            item.count
            for item in self.composite_status_counts
            if item.status is ClinicalOutcomeStatus.FAVORABLE
        )
        for item in summaries:
            if (
                item.total_units != self.outcome_unit_count
                or item.evaluable_units != self.evaluable_outcome_unit_count
                or item.indeterminate_units != self.indeterminate_outcome_unit_count
            ):
                raise ValueError(
                    "policy summary attrition must match the shared outcome cohort"
                )
            if (
                item.observed_favorable_rate.event_count != favorable_outcomes
                or item.observed_favorable_rate.total
                != self.evaluable_outcome_unit_count
            ):
                raise ValueError(
                    "policy summary outcomes must match the shared outcome cohort"
                )
        if len({item.minimum_evaluable_units for item in summaries}) != 1:
            raise ValueError("policy summaries must share one evaluable-unit minimum")
        if len({item.classification_threshold for item in summaries}) != 1:
            raise ValueError("policy summaries must share one classification threshold")
        interval_policies = {
            (
                item.observed_favorable_rate.confidence_level,
                item.observed_favorable_rate.method,
            )
            for item in summaries
        }
        if len(interval_policies) != 1:
            raise ValueError("policy summaries must share one interval policy")
        bin_boundaries = {
            tuple(
                (
                    item.lower_bound,
                    item.upper_bound,
                    item.includes_upper_bound,
                )
                for item in summary.calibration_bins
            )
            for summary in summaries
        }
        if len(bin_boundaries) != 1:
            raise ValueError("policy summaries must share calibration bins")
        comparisons = _tuple(
            self.matched_policy_comparisons,
            "matched_policy_comparisons",
        )
        object.__setattr__(self, "matched_policy_comparisons", comparisons)
        for item in comparisons:
            _require_instance(
                item,
                ClinicalMatchedOutcomeComparison,
                "matched_policy_comparisons item",
            )
        comparison_keys = tuple(
            (item.policy_a.sort_key, item.policy_b.sort_key) for item in comparisons
        )
        expected_comparison_keys = tuple(
            (left.policy.sort_key, right.policy.sort_key)
            for left, right in combinations(summaries, 2)
        )
        if comparison_keys != expected_comparison_keys:
            raise ValueError("matched comparisons must exactly cover policy pairs")
        policy_fingerprints = {item.policy.policy_fingerprint for item in summaries}
        if any(
            item.policy_a.policy_fingerprint not in policy_fingerprints
            or item.policy_b.policy_fingerprint not in policy_fingerprints
            for item in comparisons
        ):
            raise ValueError("matched comparison references an unknown policy")
        summaries_by_policy = {
            item.policy.policy_fingerprint: item for item in summaries
        }
        for item in comparisons:
            summary_a = summaries_by_policy[item.policy_a.policy_fingerprint]
            summary_b = summaries_by_policy[item.policy_b.policy_fingerprint]
            if item.policy_a != summary_a.policy or item.policy_b != summary_b.policy:
                raise ValueError("matched comparison policy identity is inconsistent")
            if (
                item.shared_units != self.outcome_unit_count
                or item.shared_evaluable_units != self.evaluable_outcome_unit_count
                or item.shared_indeterminate_units
                != self.indeterminate_outcome_unit_count
            ):
                raise ValueError(
                    "matched comparison attrition must match the shared outcome cohort"
                )
            if (
                item.mean_brier_a != summary_a.brier_score
                or item.mean_brier_b != summary_b.brier_score
            ):
                raise ValueError(
                    "matched comparison Brier means must match policy summaries"
                )
        for field_name in (
            "baseline_outcome_source_overlap_count",
            "outcome_cross_unit_source_overlap_count",
            "outcome_cross_unit_trial_overlap_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.baseline_outcome_source_overlap_count != 0:
            raise ValueError("baseline source reuse must fail before reporting")
        for field_name in (
            "outcome_units_source_disjoint",
            "outcome_units_trial_disjoint",
            "aggregate_outcomes_included",
            "unit_level_predictions_included",
            "unit_level_outcomes_included",
            "package_decisions_scored_as_outcomes",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if self.outcome_units_source_disjoint != (
            self.outcome_cross_unit_source_overlap_count == 0
        ):
            raise ValueError("outcome source-disjoint flag is inconsistent")
        if self.outcome_units_trial_disjoint != (
            self.outcome_cross_unit_trial_overlap_count == 0
        ):
            raise ValueError("outcome trial-disjoint flag is inconsistent")
        if not self.aggregate_outcomes_included:
            raise ValueError("clinical outcome report requires aggregate outcomes")
        if (
            self.unit_level_predictions_included
            or self.unit_level_outcomes_included
            or self.package_decisions_scored_as_outcomes
        ):
            raise ValueError("clinical outcome report crossed its aggregate boundary")
        expected_status = _calibration_status(summaries)
        if self.calibration_status not in _CALIBRATION_STATUSES:
            raise ValueError("calibration_status is unsupported")
        if self.calibration_status != expected_status:
            raise ValueError("calibration_status is inconsistent")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required clinical outcome limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _status_counts(
    values: Sequence[ClinicalOutcomeStatus],
) -> tuple[ClinicalOutcomeStatusCount, ...]:
    return tuple(
        ClinicalOutcomeStatusCount(
            status=status,
            count=sum(value is status for value in values),
        )
        for status in _STATUS_ORDER
    )


def _calibration_status(
    summaries: Sequence[ClinicalOutcomePolicyMetrics],
) -> str:
    met = sum(item.evaluation_requirement_met for item in summaries)
    if met == len(summaries):
        return "preregistered_outcome_calibration_estimable"
    if met:
        return "partially_estimable"
    return "not_estimable_insufficient_evaluable_units"


def _calibration_bins(
    observations: Sequence[tuple[float, int]],
    protocol: ClinicalOutcomeEvaluationProtocol,
) -> tuple[ClinicalCalibrationBin, ...]:
    bins = []
    edges = protocol.calibration_bin_edges
    for index, (lower, upper) in enumerate(zip(edges, edges[1:])):
        includes_upper = index == len(edges) - 2
        members = tuple(
            (probability, label)
            for probability, label in observations
            if lower <= probability
            and (probability <= upper if includes_upper else probability < upper)
        )
        count = len(members)
        mean_probability = (
            None
            if not members
            else _round_metric(sum(item[0] for item in members) / count)
        )
        observed = _binomial_estimate(
            sum(item[1] for item in members),
            count,
            protocol,
        )
        gap = (
            None
            if mean_probability is None
            else _round_metric(mean_probability - (observed.estimate or 0.0))
        )
        bins.append(
            ClinicalCalibrationBin(
                lower_bound=lower,
                upper_bound=upper,
                includes_upper_bound=includes_upper,
                unit_count=count,
                mean_predicted_probability=mean_probability,
                observed_favorable_rate=observed,
                calibration_gap=gap,
            )
        )
    return tuple(bins)


def _policy_metrics(
    submission: ClinicalPredictionSubmission,
    outcomes_by_unit: Mapping[str, ClinicalOutcomeAssessment],
    protocol: ClinicalOutcomeEvaluationProtocol,
) -> ClinicalOutcomePolicyMetrics:
    evaluable: list[tuple[float, int]] = []
    for prediction in submission.predictions:
        status = outcomes_by_unit[prediction.evidence_unit_id].composite_status
        if status is ClinicalOutcomeStatus.INDETERMINATE:
            continue
        evaluable.append(
            (
                prediction.favorable_probability,
                int(status is ClinicalOutcomeStatus.FAVORABLE),
            )
        )
    matrix = ClinicalConfusionMatrix(
        true_positive=sum(
            probability >= protocol.classification_threshold and label == 1
            for probability, label in evaluable
        ),
        false_positive=sum(
            probability >= protocol.classification_threshold and label == 0
            for probability, label in evaluable
        ),
        true_negative=sum(
            probability < protocol.classification_threshold and label == 0
            for probability, label in evaluable
        ),
        false_negative=sum(
            probability < protocol.classification_threshold and label == 1
            for probability, label in evaluable
        ),
    )
    count = len(evaluable)
    mean_probability = (
        None
        if not evaluable
        else _round_metric(sum(item[0] for item in evaluable) / count)
    )
    observed = _binomial_estimate(
        matrix.true_positive + matrix.false_negative,
        count,
        protocol,
    )
    bins = _calibration_bins(evaluable, protocol)
    brier = (
        None
        if not evaluable
        else _round_metric(
            sum((probability - label) ** 2 for probability, label in evaluable) / count
        )
    )
    calibration = (
        None
        if mean_probability is None
        else _round_metric(mean_probability - (observed.estimate or 0.0))
    )
    ece = (
        None
        if not evaluable
        else _round_metric(
            sum(item.unit_count * abs(item.calibration_gap or 0.0) for item in bins)
            / count
        )
    )
    return ClinicalOutcomePolicyMetrics(
        policy=submission.policy,
        submission_id=submission.submission_id,
        submission_fingerprint=submission.fingerprint,
        total_units=len(submission.predictions),
        evaluable_units=count,
        indeterminate_units=len(submission.predictions) - count,
        minimum_evaluable_units=protocol.minimum_evaluable_units,
        evaluation_requirement_met=count >= protocol.minimum_evaluable_units,
        classification_threshold=protocol.classification_threshold,
        mean_predicted_probability=mean_probability,
        observed_favorable_rate=observed,
        predicted_favorable_rate=_binomial_estimate(
            matrix.true_positive + matrix.false_positive,
            count,
            protocol,
        ),
        confusion_matrix=matrix,
        classification_accuracy=_binomial_estimate(
            matrix.true_positive + matrix.true_negative,
            count,
            protocol,
        ),
        sensitivity=_binomial_estimate(
            matrix.true_positive,
            matrix.true_positive + matrix.false_negative,
            protocol,
        ),
        specificity=_binomial_estimate(
            matrix.true_negative,
            matrix.true_negative + matrix.false_positive,
            protocol,
        ),
        positive_predictive_value=_binomial_estimate(
            matrix.true_positive,
            matrix.true_positive + matrix.false_positive,
            protocol,
        ),
        negative_predictive_value=_binomial_estimate(
            matrix.true_negative,
            matrix.true_negative + matrix.false_negative,
            protocol,
        ),
        brier_score=brier,
        calibration_in_the_large=calibration,
        expected_calibration_error=ece,
        calibration_bins=bins,
    )


def _matched_comparison(
    submission_a: ClinicalPredictionSubmission,
    submission_b: ClinicalPredictionSubmission,
    outcomes_by_unit: Mapping[str, ClinicalOutcomeAssessment],
    threshold: float,
) -> ClinicalMatchedOutcomeComparison | None:
    predictions_a = {
        item.evidence_unit_id: item.favorable_probability
        for item in submission_a.predictions
    }
    predictions_b = {
        item.evidence_unit_id: item.favorable_probability
        for item in submission_b.predictions
    }
    shared = tuple(sorted(set(predictions_a) & set(predictions_b)))
    if not shared:
        return None
    scores: list[tuple[float, float]] = []
    disagreements = 0
    for unit_id in shared:
        status = outcomes_by_unit[unit_id].composite_status
        if status is ClinicalOutcomeStatus.INDETERMINATE:
            continue
        label = int(status is ClinicalOutcomeStatus.FAVORABLE)
        probability_a = predictions_a[unit_id]
        probability_b = predictions_b[unit_id]
        scores.append(
            (
                (probability_a - label) ** 2,
                (probability_b - label) ** 2,
            )
        )
        disagreements += (probability_a >= threshold) != (probability_b >= threshold)
    mean_a = (
        None
        if not scores
        else _round_metric(sum(item[0] for item in scores) / len(scores))
    )
    mean_b = (
        None
        if not scores
        else _round_metric(sum(item[1] for item in scores) / len(scores))
    )
    return ClinicalMatchedOutcomeComparison(
        policy_a=submission_a.policy,
        policy_b=submission_b.policy,
        shared_units=len(shared),
        shared_evaluable_units=len(scores),
        shared_indeterminate_units=len(shared) - len(scores),
        mean_brier_a=mean_a,
        mean_brier_b=mean_b,
        mean_brier_difference_b_minus_a=(
            None if mean_a is None or mean_b is None else _round_metric(mean_b - mean_a)
        ),
        policy_a_lower_brier_units=sum(a < b - 1e-12 for a, b in scores),
        equal_brier_units=sum(
            math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12) for a, b in scores
        ),
        policy_b_lower_brier_units=sum(b < a - 1e-12 for a, b in scores),
        classification_disagreement_units=disagreements,
    )


def _validate_evaluation_inputs(
    protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
) -> tuple[
    tuple[ClinicalPredictionSubmission, ...], dict[str, ClinicalOutcomeAssessment]
]:
    _require_instance(protocol, ClinicalOutcomeEvaluationProtocol, "protocol")
    _require_instance(cohort_report, ClinicalCohortReport, "cohort_report")
    _require_instance(outcome_manifest, ClinicalOutcomeManifest, "outcome_manifest")
    if protocol.cohort_id != cohort_report.cohort_id:
        raise ClinicalOutcomeEvaluationError("protocol cohort_id does not match report")
    if (
        protocol.cohort_specification_sha256
        != cohort_report.cohort_specification_sha256
    ):
        raise ClinicalOutcomeEvaluationError(
            "protocol cohort specification does not match"
        )
    if protocol.cohort_report_fingerprint != cohort_report.fingerprint:
        raise ClinicalOutcomeEvaluationError(
            "protocol cohort report binding does not match"
        )
    if cohort_report.latest_as_of_date > protocol.registered_on:
        raise ClinicalOutcomeEvaluationError(
            "protocol predates neither all cohort packages nor their cutoff"
        )
    if protocol.minimum_evaluable_units > cohort_report.evidence_unit_count:
        raise ClinicalOutcomeEvaluationError(
            "minimum evaluable units exceed the cohort"
        )

    resolved_submissions = _tuple(submissions, "submissions")
    if not resolved_submissions:
        raise ClinicalOutcomeEvaluationError(
            "clinical outcome evaluation requires submissions"
        )
    for submission in resolved_submissions:
        _require_instance(submission, ClinicalPredictionSubmission, "submissions item")
    if len({item.submission_id for item in resolved_submissions}) != len(
        resolved_submissions
    ):
        raise ClinicalOutcomeEvaluationError("submission ids must be unique")
    if len({item.policy.policy_fingerprint for item in resolved_submissions}) != len(
        resolved_submissions
    ):
        raise ClinicalOutcomeEvaluationError("one submission is allowed per policy")

    packages_by_policy: dict[str, list[Any]] = defaultdict(list)
    policies_by_fingerprint: dict[str, ClinicalCohortPolicyIdentity] = {}
    for package in cohort_report.packages:
        fingerprint = package.policy.policy_fingerprint
        packages_by_policy[fingerprint].append(package)
        policies_by_fingerprint[fingerprint] = package.policy
    if {item.policy.policy_fingerprint for item in resolved_submissions} != set(
        packages_by_policy
    ):
        raise ClinicalOutcomeEvaluationError(
            "submissions do not exactly cover cohort policies"
        )
    for submission in resolved_submissions:
        if (
            submission.protocol_id != protocol.protocol_id
            or submission.protocol_fingerprint != protocol.fingerprint
        ):
            raise ClinicalOutcomeEvaluationError(
                "submission protocol binding does not match"
            )
        if submission.cohort_report_fingerprint != cohort_report.fingerprint:
            raise ClinicalOutcomeEvaluationError(
                "submission cohort binding does not match"
            )
        if (
            not protocol.registered_on
            <= submission.submitted_on
            <= protocol.prediction_deadline
        ):
            raise ClinicalOutcomeEvaluationError(
                "submission falls outside the preregistered prediction window"
            )
        fingerprint = submission.policy.policy_fingerprint
        if submission.policy != policies_by_fingerprint[fingerprint]:
            raise ClinicalOutcomeEvaluationError(
                "submission policy identity does not match cohort"
            )
        expected = {item.package_id: item for item in packages_by_policy[fingerprint]}
        observed = {item.package_id: item for item in submission.predictions}
        if set(observed) != set(expected):
            raise ClinicalOutcomeEvaluationError(
                "submission predictions do not exactly cover policy packages"
            )
        for package_id, prediction in observed.items():
            package = expected[package_id]
            if (
                prediction.package_integrity_sha256 != package.integrity_sha256
                or prediction.evidence_unit_id != package.evidence_unit_id
            ):
                raise ClinicalOutcomeEvaluationError(
                    "prediction package binding does not match cohort"
                )
            if package.as_of_date > submission.submitted_on:
                raise ClinicalOutcomeEvaluationError(
                    "prediction predates its bound package"
                )

    if (
        outcome_manifest.protocol_id != protocol.protocol_id
        or outcome_manifest.protocol_fingerprint != protocol.fingerprint
    ):
        raise ClinicalOutcomeEvaluationError(
            "outcome manifest protocol binding does not match"
        )
    if outcome_manifest.cohort_report_fingerprint != cohort_report.fingerprint:
        raise ClinicalOutcomeEvaluationError(
            "outcome manifest cohort binding does not match"
        )
    if outcome_manifest.curator_roster_commitment != protocol.curator_roster_commitment:
        raise ClinicalOutcomeEvaluationError(
            "outcome curator roster does not match protocol"
        )
    if outcome_manifest.frozen_on < protocol.outcome_window_end:
        raise ClinicalOutcomeEvaluationError(
            "outcome manifest froze before the outcome window ended"
        )
    outcomes_by_unit = {
        item.evidence_unit_id: item for item in outcome_manifest.assessments
    }
    expected_units = {item.evidence_unit_id for item in cohort_report.packages}
    if set(outcomes_by_unit) != expected_units:
        raise ClinicalOutcomeEvaluationError(
            "outcomes do not exactly cover cohort evidence units"
        )

    diagnostics_by_unit: dict[str, list[Any]] = defaultdict(list)
    for package in cohort_report.packages:
        diagnostics_by_unit[package.evidence_unit_id].append(package)
    baseline_hashes = {
        digest
        for package in cohort_report.packages
        for digest in package.source_content_hashes
    }
    source_identity_by_hash: dict[str, tuple[Any, ...]] = {}
    for unit_id, assessment in outcomes_by_unit.items():
        diagnostics = diagnostics_by_unit[unit_id]
        identity_fields = (
            "program_id",
            "disease_id",
            "candidate_id",
            "intervention_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "stage",
        )
        for field_name in identity_fields:
            values = {getattr(item, field_name) for item in diagnostics}
            if len(values) != 1 or getattr(assessment, field_name) not in values:
                raise ClinicalOutcomeEvaluationError(
                    "outcome identity does not match its evidence unit"
                )
        if (
            not protocol.outcome_window_end
            <= assessment.assessment_date
            <= outcome_manifest.frozen_on
        ):
            raise ClinicalOutcomeEvaluationError(
                "outcome assessment falls outside the freeze window"
            )
        if assessment.independent_curator_count < protocol.minimum_independent_curators:
            raise ClinicalOutcomeEvaluationError(
                "outcome assessment has too few independent curators"
            )
        for source in assessment.sources:
            if (
                not protocol.outcome_window_start
                <= source.available_on
                <= outcome_manifest.frozen_on
            ):
                raise ClinicalOutcomeEvaluationError(
                    "outcome source violates cutoff-safe availability"
                )
            if source.available_on > assessment.assessment_date:
                raise ClinicalOutcomeEvaluationError(
                    "outcome source postdates its assessment"
                )
            if source.source_content_sha256 in baseline_hashes:
                raise ClinicalOutcomeEvaluationError(
                    "outcome source reuses a baseline content hash"
                )
            source_identity = (
                source.source_id,
                source.source_version,
                source.available_on,
                source.trial_id,
            )
            previous = source_identity_by_hash.setdefault(
                source.source_content_sha256,
                source_identity,
            )
            if previous != source_identity:
                raise ClinicalOutcomeEvaluationError(
                    "outcome source content hash is rebound across evidence units"
                )
    return (
        tuple(sorted(resolved_submissions, key=lambda item: item.policy.sort_key)),
        outcomes_by_unit,
    )


def evaluate_clinical_outcomes(
    protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
) -> ClinicalOutcomeEvaluationReport:
    """Evaluate frozen package-bound forecasts against independent outcomes."""

    ordered_submissions, outcomes_by_unit = _validate_evaluation_inputs(
        protocol,
        cohort_report,
        submissions,
        outcome_manifest,
    )
    outcomes = tuple(outcomes_by_unit[unit_id] for unit_id in sorted(outcomes_by_unit))
    summaries = tuple(
        _policy_metrics(submission, outcomes_by_unit, protocol)
        for submission in ordered_submissions
    )
    comparisons = tuple(
        comparison
        for submission_a, submission_b in combinations(ordered_submissions, 2)
        if (
            comparison := _matched_comparison(
                submission_a,
                submission_b,
                outcomes_by_unit,
                protocol.classification_threshold,
            )
        )
        is not None
    )
    source_units: dict[str, set[str]] = defaultdict(set)
    trial_units: dict[str, set[str]] = defaultdict(set)
    for outcome in outcomes:
        for source in outcome.sources:
            source_units[source.source_content_sha256].add(outcome.evidence_unit_id)
            if source.trial_id is not None:
                trial_units[source.trial_id].add(outcome.evidence_unit_id)
    source_overlap_count = sum(len(units) > 1 for units in source_units.values())
    trial_overlap_count = sum(len(units) > 1 for units in trial_units.values())
    composite_statuses = tuple(item.composite_status for item in outcomes)
    evaluable_count = sum(
        status is not ClinicalOutcomeStatus.INDETERMINATE
        for status in composite_statuses
    )
    return ClinicalOutcomeEvaluationReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        cohort_id=cohort_report.cohort_id,
        cohort_report_fingerprint=cohort_report.fingerprint,
        outcome_manifest_fingerprint=outcome_manifest.fingerprint,
        method_id=CLINICAL_OUTCOME_EVALUATION_METHOD_ID,
        generated_on=outcome_manifest.frozen_on,
        outcome_unit_count=len(outcomes),
        evaluable_outcome_unit_count=evaluable_count,
        indeterminate_outcome_unit_count=len(outcomes) - evaluable_count,
        submission_count=len(ordered_submissions),
        endpoint_status_counts=_status_counts(
            tuple(item.endpoint_status for item in outcomes)
        ),
        safety_status_counts=_status_counts(
            tuple(item.safety_status for item in outcomes)
        ),
        composite_status_counts=_status_counts(composite_statuses),
        policy_summaries=summaries,
        matched_policy_comparisons=comparisons,
        baseline_outcome_source_overlap_count=0,
        outcome_cross_unit_source_overlap_count=source_overlap_count,
        outcome_cross_unit_trial_overlap_count=trial_overlap_count,
        outcome_units_source_disjoint=source_overlap_count == 0,
        outcome_units_trial_disjoint=trial_overlap_count == 0,
        aggregate_outcomes_included=True,
        unit_level_predictions_included=False,
        unit_level_outcomes_included=False,
        package_decisions_scored_as_outcomes=False,
        calibration_status=_calibration_status(summaries),
    )


def validate_clinical_outcome_evaluation_report(
    report: ClinicalOutcomeEvaluationReport,
    protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
) -> tuple[str, ...]:
    """Replay all private inputs and compare the aggregate report exactly."""

    try:
        rebuilt = evaluate_clinical_outcomes(
            protocol,
            cohort_report,
            submissions,
            outcome_manifest,
        )
    except (ClinicalOutcomeEvaluationError, TypeError, ValueError):
        return ("clinical_outcome_recompile_failed",)
    if rebuilt != report:
        return ("recompiled_clinical_outcome_report_mismatch",)
    return ()


def clinical_outcome_evaluation_summary(
    report: ClinicalOutcomeEvaluationReport,
) -> dict[str, Any]:
    """Return a compact aggregate projection without unit-level labels."""

    _require_instance(report, ClinicalOutcomeEvaluationReport, "report")
    return {
        "schema_version": CLINICAL_OUTCOME_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "protocol_id": report.protocol_id,
        "cohort_id": report.cohort_id,
        "outcome_units": {
            "total": report.outcome_unit_count,
            "evaluable": report.evaluable_outcome_unit_count,
            "indeterminate": report.indeterminate_outcome_unit_count,
        },
        "calibration_status": report.calibration_status,
        "policy_summaries": [
            {
                "policy_id": item.policy.policy_id,
                "policy_version": item.policy.policy_version,
                "policy_fingerprint": item.policy.policy_fingerprint,
                "evaluable_units": item.evaluable_units,
                "evaluation_requirement_met": item.evaluation_requirement_met,
                "brier_score": item.brier_score,
                "classification_accuracy": item.classification_accuracy.to_dict(),
                "calibration_in_the_large": item.calibration_in_the_large,
                "expected_calibration_error": item.expected_calibration_error,
            }
            for item in report.policy_summaries
        ],
        "matched_policy_comparison_count": len(report.matched_policy_comparisons),
        "outcome_units_source_disjoint": report.outcome_units_source_disjoint,
        "outcome_units_trial_disjoint": report.outcome_units_trial_disjoint,
        "unit_level_outcomes_included": report.unit_level_outcomes_included,
    }


def clinical_outcome_validation_summary(
    report: ClinicalOutcomeEvaluationReport,
    *,
    failures: Sequence[str] = (),
    scope: str = "integrity_and_aggregate_consistency",
) -> dict[str, Any]:
    resolved_failures = tuple(failures)
    for failure in resolved_failures:
        _require_text(failure, "failure code")
    if len(resolved_failures) != len(set(resolved_failures)):
        raise ValueError("failure codes must be unique")
    _require_text(scope, "scope")
    return {
        **clinical_outcome_evaluation_summary(report),
        "validation": {
            "status": "valid" if not resolved_failures else "invalid",
            "scope": scope,
            "failure_codes": list(resolved_failures),
        },
    }


def clinical_outcome_protocol_envelope(
    protocol: ClinicalOutcomeEvaluationProtocol,
) -> dict[str, Any]:
    _require_instance(protocol, ClinicalOutcomeEvaluationProtocol, "protocol")
    return {
        "schema_version": CLINICAL_OUTCOME_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_prediction_submission_envelope(
    submission: ClinicalPredictionSubmission,
) -> dict[str, Any]:
    _require_instance(submission, ClinicalPredictionSubmission, "submission")
    return {
        "schema_version": CLINICAL_PREDICTION_SUBMISSION_SCHEMA_VERSION,
        "integrity_sha256": submission.fingerprint,
        "submission": submission.to_dict(),
    }


def clinical_outcome_manifest_envelope(
    manifest: ClinicalOutcomeManifest,
) -> dict[str, Any]:
    _require_instance(manifest, ClinicalOutcomeManifest, "manifest")
    return {
        "schema_version": CLINICAL_OUTCOME_MANIFEST_SCHEMA_VERSION,
        "integrity_sha256": manifest.fingerprint,
        "manifest": manifest.to_dict(),
    }


def clinical_outcome_report_envelope(
    report: ClinicalOutcomeEvaluationReport,
) -> dict[str, Any]:
    _require_instance(report, ClinicalOutcomeEvaluationReport, "report")
    return {
        "schema_version": CLINICAL_OUTCOME_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing:
        raise RecordParseError(f"{path} is missing fields: {sorted(missing)}")
    if extra:
        raise RecordParseError(f"{path} has unknown fields: {sorted(extra)}")
    return data


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    return dict(value)


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise RecordParseError(f"{path} must use canonical ISO date form")
    return parsed


def _parse_enum(enum_type: type[Enum], value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is unsupported") from exc


def _strict_json(payload: str, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RecordParseError(f"{label} duplicates key {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise RecordParseError(f"{label} contains non-finite value {value}")

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(f"{label} is not valid JSON") from exc


def _integrity_payload(
    value: Any,
    *,
    path: str,
    schema_version: str,
    payload_field: str,
) -> tuple[Any, str]:
    envelope = _record(
        value,
        path,
        {"schema_version", "integrity_sha256", payload_field},
    )
    if envelope["schema_version"] != schema_version:
        raise RecordParseError(f"{path}.schema_version is unsupported")
    integrity = envelope["integrity_sha256"]
    try:
        _require_sha256(integrity, f"{path}.integrity_sha256")
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path}.integrity_sha256 is invalid") from exc
    return envelope[payload_field], integrity


def _parse_policy(value: Any, path: str) -> ClinicalCohortPolicyIdentity:
    data = _record(
        value,
        path,
        {"policy_id", "policy_version", "policy_fingerprint"},
    )
    return ClinicalCohortPolicyIdentity(
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        policy_fingerprint=data["policy_fingerprint"],
    )


def clinical_outcome_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeEvaluationProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_protocol_envelope",
        schema_version=CLINICAL_OUTCOME_PROTOCOL_SCHEMA_VERSION,
        payload_field="protocol",
    )
    data = _record(
        payload,
        "protocol",
        {
            "protocol_id",
            "version",
            "registered_on",
            "cohort_id",
            "cohort_specification_sha256",
            "cohort_report_fingerprint",
            "prediction_deadline",
            "outcome_window_start",
            "outcome_window_end",
            "endpoint_harmonization_policy_sha256",
            "safety_harmonization_policy_sha256",
            "outcome_definition_sha256",
            "label_guidance_sha256",
            "exclusion_rules_sha256",
            "curator_roster_commitment",
            "minimum_independent_curators",
            "minimum_evaluable_units",
            "classification_threshold",
            "calibration_bin_edges",
            "confidence_level",
            "prediction_target",
            "composite_rule_id",
            "interval_method",
            "policy_blinding_required",
            "conflict_free_required",
            "adjudicator_independence_required",
            "metadata",
        },
    )
    protocol = ClinicalOutcomeEvaluationProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        cohort_id=data["cohort_id"],
        cohort_specification_sha256=data["cohort_specification_sha256"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        prediction_deadline=_parse_date(
            data["prediction_deadline"],
            "protocol.prediction_deadline",
        ),
        outcome_window_start=_parse_date(
            data["outcome_window_start"],
            "protocol.outcome_window_start",
        ),
        outcome_window_end=_parse_date(
            data["outcome_window_end"],
            "protocol.outcome_window_end",
        ),
        endpoint_harmonization_policy_sha256=(
            data["endpoint_harmonization_policy_sha256"]
        ),
        safety_harmonization_policy_sha256=(data["safety_harmonization_policy_sha256"]),
        outcome_definition_sha256=data["outcome_definition_sha256"],
        label_guidance_sha256=data["label_guidance_sha256"],
        exclusion_rules_sha256=data["exclusion_rules_sha256"],
        curator_roster_commitment=data["curator_roster_commitment"],
        minimum_independent_curators=data["minimum_independent_curators"],
        minimum_evaluable_units=data["minimum_evaluable_units"],
        classification_threshold=data["classification_threshold"],
        calibration_bin_edges=tuple(
            _sequence(
                data["calibration_bin_edges"],
                "protocol.calibration_bin_edges",
            )
        ),
        confidence_level=data["confidence_level"],
        prediction_target=data["prediction_target"],
        composite_rule_id=data["composite_rule_id"],
        interval_method=_parse_enum(
            IntervalMethod,
            data["interval_method"],
            "protocol.interval_method",
        ),
        policy_blinding_required=data["policy_blinding_required"],
        conflict_free_required=data["conflict_free_required"],
        adjudicator_independence_required=(data["adjudicator_independence_required"]),
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    if protocol.fingerprint != integrity:
        raise RecordParseError("clinical outcome protocol integrity mismatch")
    return protocol


def _parse_prediction(
    value: Any,
    path: str,
) -> ClinicalFavorableOutcomePrediction:
    data = _record(
        value,
        path,
        {
            "package_id",
            "package_integrity_sha256",
            "evidence_unit_id",
            "favorable_probability",
        },
    )
    return ClinicalFavorableOutcomePrediction(
        package_id=data["package_id"],
        package_integrity_sha256=data["package_integrity_sha256"],
        evidence_unit_id=data["evidence_unit_id"],
        favorable_probability=data["favorable_probability"],
    )


def clinical_prediction_submission_from_dict(
    value: Any,
) -> ClinicalPredictionSubmission:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_prediction_submission_envelope",
        schema_version=CLINICAL_PREDICTION_SUBMISSION_SCHEMA_VERSION,
        payload_field="submission",
    )
    data = _record(
        payload,
        "submission",
        {
            "submission_id",
            "protocol_id",
            "protocol_fingerprint",
            "cohort_report_fingerprint",
            "policy",
            "submitted_on",
            "predictions",
            "metadata",
        },
    )
    submission = ClinicalPredictionSubmission(
        submission_id=data["submission_id"],
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        policy=_parse_policy(data["policy"], "submission.policy"),
        submitted_on=_parse_date(data["submitted_on"], "submission.submitted_on"),
        predictions=tuple(
            _parse_prediction(item, f"submission.predictions[{index}]")
            for index, item in enumerate(
                _sequence(data["predictions"], "submission.predictions")
            )
        ),
        metadata=_mapping(data["metadata"], "submission.metadata"),
    )
    if submission.fingerprint != integrity:
        raise RecordParseError("clinical prediction submission integrity mismatch")
    return submission


def _parse_source(value: Any, path: str) -> ClinicalOutcomeSource:
    data = _record(
        value,
        path,
        {
            "source_id",
            "source_version",
            "source_content_sha256",
            "available_on",
            "domains",
            "trial_id",
        },
    )
    trial_id = data["trial_id"]
    if trial_id is not None and not isinstance(trial_id, str):
        raise RecordParseError(f"{path}.trial_id must be text or null")
    return ClinicalOutcomeSource(
        source_id=data["source_id"],
        source_version=data["source_version"],
        source_content_sha256=data["source_content_sha256"],
        available_on=_parse_date(data["available_on"], f"{path}.available_on"),
        domains=tuple(
            _parse_enum(
                ClinicalOutcomeDomain,
                item,
                f"{path}.domains[{index}]",
            )
            for index, item in enumerate(_sequence(data["domains"], f"{path}.domains"))
        ),
        trial_id=trial_id,
    )


def _parse_assessment(value: Any, path: str) -> ClinicalOutcomeAssessment:
    data = _record(
        value,
        path,
        {
            "evidence_unit_id",
            "program_id",
            "disease_id",
            "candidate_id",
            "intervention_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "stage",
            "assessment_date",
            "endpoint_status",
            "safety_status",
            "composite_status",
            "sources",
            "endpoint_assessment_sha256",
            "safety_assessment_sha256",
            "adjudication_sha256",
            "independent_curator_count",
            "policy_blinded",
            "conflict_free",
            "adjudicator_independent",
        },
    )
    return ClinicalOutcomeAssessment(
        evidence_unit_id=data["evidence_unit_id"],
        program_id=data["program_id"],
        disease_id=data["disease_id"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        endpoint_mapping_id=data["endpoint_mapping_id"],
        endpoint_family=data["endpoint_family"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        assessment_date=_parse_date(
            data["assessment_date"],
            f"{path}.assessment_date",
        ),
        endpoint_status=_parse_enum(
            ClinicalOutcomeStatus,
            data["endpoint_status"],
            f"{path}.endpoint_status",
        ),
        safety_status=_parse_enum(
            ClinicalOutcomeStatus,
            data["safety_status"],
            f"{path}.safety_status",
        ),
        composite_status=_parse_enum(
            ClinicalOutcomeStatus,
            data["composite_status"],
            f"{path}.composite_status",
        ),
        sources=tuple(
            _parse_source(item, f"{path}.sources[{index}]")
            for index, item in enumerate(_sequence(data["sources"], f"{path}.sources"))
        ),
        endpoint_assessment_sha256=data["endpoint_assessment_sha256"],
        safety_assessment_sha256=data["safety_assessment_sha256"],
        adjudication_sha256=data["adjudication_sha256"],
        independent_curator_count=data["independent_curator_count"],
        policy_blinded=data["policy_blinded"],
        conflict_free=data["conflict_free"],
        adjudicator_independent=data["adjudicator_independent"],
    )


def clinical_outcome_manifest_from_dict(value: Any) -> ClinicalOutcomeManifest:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_manifest_envelope",
        schema_version=CLINICAL_OUTCOME_MANIFEST_SCHEMA_VERSION,
        payload_field="manifest",
    )
    data = _record(
        payload,
        "manifest",
        {
            "manifest_id",
            "protocol_id",
            "protocol_fingerprint",
            "cohort_report_fingerprint",
            "curator_roster_commitment",
            "frozen_on",
            "assessments",
        },
    )
    manifest = ClinicalOutcomeManifest(
        manifest_id=data["manifest_id"],
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        curator_roster_commitment=data["curator_roster_commitment"],
        frozen_on=_parse_date(data["frozen_on"], "manifest.frozen_on"),
        assessments=tuple(
            _parse_assessment(item, f"manifest.assessments[{index}]")
            for index, item in enumerate(
                _sequence(data["assessments"], "manifest.assessments")
            )
        ),
    )
    if manifest.fingerprint != integrity:
        raise RecordParseError("clinical outcome manifest integrity mismatch")
    return manifest


def _parse_estimate(value: Any, path: str) -> BinomialEstimate:
    data = _record(
        value,
        path,
        {
            "event_count",
            "total",
            "estimate",
            "lower",
            "upper",
            "confidence_level",
            "method",
        },
    )
    return BinomialEstimate(
        event_count=data["event_count"],
        total=data["total"],
        estimate=data["estimate"],
        lower=data["lower"],
        upper=data["upper"],
        confidence_level=data["confidence_level"],
        method=_parse_enum(IntervalMethod, data["method"], f"{path}.method"),
    )


def _parse_status_count(value: Any, path: str) -> ClinicalOutcomeStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomeStatusCount(
        status=_parse_enum(
            ClinicalOutcomeStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_confusion_matrix(value: Any, path: str) -> ClinicalConfusionMatrix:
    data = _record(
        value,
        path,
        {"true_positive", "false_positive", "true_negative", "false_negative"},
    )
    return ClinicalConfusionMatrix(
        true_positive=data["true_positive"],
        false_positive=data["false_positive"],
        true_negative=data["true_negative"],
        false_negative=data["false_negative"],
    )


def _parse_calibration_bin(value: Any, path: str) -> ClinicalCalibrationBin:
    data = _record(
        value,
        path,
        {
            "lower_bound",
            "upper_bound",
            "includes_upper_bound",
            "unit_count",
            "mean_predicted_probability",
            "observed_favorable_rate",
            "calibration_gap",
        },
    )
    return ClinicalCalibrationBin(
        lower_bound=data["lower_bound"],
        upper_bound=data["upper_bound"],
        includes_upper_bound=data["includes_upper_bound"],
        unit_count=data["unit_count"],
        mean_predicted_probability=data["mean_predicted_probability"],
        observed_favorable_rate=_parse_estimate(
            data["observed_favorable_rate"],
            f"{path}.observed_favorable_rate",
        ),
        calibration_gap=data["calibration_gap"],
    )


def _parse_policy_metrics(
    value: Any,
    path: str,
) -> ClinicalOutcomePolicyMetrics:
    fields = {
        "policy",
        "submission_id",
        "submission_fingerprint",
        "total_units",
        "evaluable_units",
        "indeterminate_units",
        "minimum_evaluable_units",
        "evaluation_requirement_met",
        "classification_threshold",
        "mean_predicted_probability",
        "observed_favorable_rate",
        "predicted_favorable_rate",
        "confusion_matrix",
        "classification_accuracy",
        "sensitivity",
        "specificity",
        "positive_predictive_value",
        "negative_predictive_value",
        "brier_score",
        "calibration_in_the_large",
        "expected_calibration_error",
        "calibration_bins",
    }
    data = _record(value, path, fields)
    return ClinicalOutcomePolicyMetrics(
        policy=_parse_policy(data["policy"], f"{path}.policy"),
        submission_id=data["submission_id"],
        submission_fingerprint=data["submission_fingerprint"],
        total_units=data["total_units"],
        evaluable_units=data["evaluable_units"],
        indeterminate_units=data["indeterminate_units"],
        minimum_evaluable_units=data["minimum_evaluable_units"],
        evaluation_requirement_met=data["evaluation_requirement_met"],
        classification_threshold=data["classification_threshold"],
        mean_predicted_probability=data["mean_predicted_probability"],
        observed_favorable_rate=_parse_estimate(
            data["observed_favorable_rate"],
            f"{path}.observed_favorable_rate",
        ),
        predicted_favorable_rate=_parse_estimate(
            data["predicted_favorable_rate"],
            f"{path}.predicted_favorable_rate",
        ),
        confusion_matrix=_parse_confusion_matrix(
            data["confusion_matrix"],
            f"{path}.confusion_matrix",
        ),
        classification_accuracy=_parse_estimate(
            data["classification_accuracy"],
            f"{path}.classification_accuracy",
        ),
        sensitivity=_parse_estimate(data["sensitivity"], f"{path}.sensitivity"),
        specificity=_parse_estimate(data["specificity"], f"{path}.specificity"),
        positive_predictive_value=_parse_estimate(
            data["positive_predictive_value"],
            f"{path}.positive_predictive_value",
        ),
        negative_predictive_value=_parse_estimate(
            data["negative_predictive_value"],
            f"{path}.negative_predictive_value",
        ),
        brier_score=data["brier_score"],
        calibration_in_the_large=data["calibration_in_the_large"],
        expected_calibration_error=data["expected_calibration_error"],
        calibration_bins=tuple(
            _parse_calibration_bin(item, f"{path}.calibration_bins[{index}]")
            for index, item in enumerate(
                _sequence(data["calibration_bins"], f"{path}.calibration_bins")
            )
        ),
    )


def _parse_matched_comparison(
    value: Any,
    path: str,
) -> ClinicalMatchedOutcomeComparison:
    data = _record(
        value,
        path,
        {
            "policy_a",
            "policy_b",
            "shared_units",
            "shared_evaluable_units",
            "shared_indeterminate_units",
            "mean_brier_a",
            "mean_brier_b",
            "mean_brier_difference_b_minus_a",
            "policy_a_lower_brier_units",
            "equal_brier_units",
            "policy_b_lower_brier_units",
            "classification_disagreement_units",
        },
    )
    return ClinicalMatchedOutcomeComparison(
        policy_a=_parse_policy(data["policy_a"], f"{path}.policy_a"),
        policy_b=_parse_policy(data["policy_b"], f"{path}.policy_b"),
        shared_units=data["shared_units"],
        shared_evaluable_units=data["shared_evaluable_units"],
        shared_indeterminate_units=data["shared_indeterminate_units"],
        mean_brier_a=data["mean_brier_a"],
        mean_brier_b=data["mean_brier_b"],
        mean_brier_difference_b_minus_a=(data["mean_brier_difference_b_minus_a"]),
        policy_a_lower_brier_units=data["policy_a_lower_brier_units"],
        equal_brier_units=data["equal_brier_units"],
        policy_b_lower_brier_units=data["policy_b_lower_brier_units"],
        classification_disagreement_units=(data["classification_disagreement_units"]),
    )


def clinical_outcome_report_from_dict(
    value: Any,
) -> ClinicalOutcomeEvaluationReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_report_envelope",
        schema_version=CLINICAL_OUTCOME_REPORT_SCHEMA_VERSION,
        payload_field="report",
    )
    fields = {
        "protocol_id",
        "protocol_fingerprint",
        "cohort_id",
        "cohort_report_fingerprint",
        "outcome_manifest_fingerprint",
        "method_id",
        "generated_on",
        "outcome_unit_count",
        "evaluable_outcome_unit_count",
        "indeterminate_outcome_unit_count",
        "submission_count",
        "endpoint_status_counts",
        "safety_status_counts",
        "composite_status_counts",
        "policy_summaries",
        "matched_policy_comparisons",
        "baseline_outcome_source_overlap_count",
        "outcome_cross_unit_source_overlap_count",
        "outcome_cross_unit_trial_overlap_count",
        "outcome_units_source_disjoint",
        "outcome_units_trial_disjoint",
        "aggregate_outcomes_included",
        "unit_level_predictions_included",
        "unit_level_outcomes_included",
        "package_decisions_scored_as_outcomes",
        "calibration_status",
        "limitations",
    }
    data = _record(payload, "report", fields)
    report = ClinicalOutcomeEvaluationReport(
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        cohort_id=data["cohort_id"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        outcome_manifest_fingerprint=data["outcome_manifest_fingerprint"],
        method_id=data["method_id"],
        generated_on=_parse_date(data["generated_on"], "report.generated_on"),
        outcome_unit_count=data["outcome_unit_count"],
        evaluable_outcome_unit_count=data["evaluable_outcome_unit_count"],
        indeterminate_outcome_unit_count=data["indeterminate_outcome_unit_count"],
        submission_count=data["submission_count"],
        endpoint_status_counts=tuple(
            _parse_status_count(item, f"report.endpoint_status_counts[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["endpoint_status_counts"],
                    "report.endpoint_status_counts",
                )
            )
        ),
        safety_status_counts=tuple(
            _parse_status_count(item, f"report.safety_status_counts[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["safety_status_counts"],
                    "report.safety_status_counts",
                )
            )
        ),
        composite_status_counts=tuple(
            _parse_status_count(item, f"report.composite_status_counts[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["composite_status_counts"],
                    "report.composite_status_counts",
                )
            )
        ),
        policy_summaries=tuple(
            _parse_policy_metrics(item, f"report.policy_summaries[{index}]")
            for index, item in enumerate(
                _sequence(data["policy_summaries"], "report.policy_summaries")
            )
        ),
        matched_policy_comparisons=tuple(
            _parse_matched_comparison(
                item,
                f"report.matched_policy_comparisons[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["matched_policy_comparisons"],
                    "report.matched_policy_comparisons",
                )
            )
        ),
        baseline_outcome_source_overlap_count=(
            data["baseline_outcome_source_overlap_count"]
        ),
        outcome_cross_unit_source_overlap_count=(
            data["outcome_cross_unit_source_overlap_count"]
        ),
        outcome_cross_unit_trial_overlap_count=(
            data["outcome_cross_unit_trial_overlap_count"]
        ),
        outcome_units_source_disjoint=data["outcome_units_source_disjoint"],
        outcome_units_trial_disjoint=data["outcome_units_trial_disjoint"],
        aggregate_outcomes_included=data["aggregate_outcomes_included"],
        unit_level_predictions_included=data["unit_level_predictions_included"],
        unit_level_outcomes_included=data["unit_level_outcomes_included"],
        package_decisions_scored_as_outcomes=(
            data["package_decisions_scored_as_outcomes"]
        ),
        calibration_status=data["calibration_status"],
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
    )
    if report.fingerprint != integrity:
        raise RecordParseError("clinical outcome evaluation report integrity mismatch")
    return report


def clinical_outcome_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeEvaluationProtocol:
    return clinical_outcome_protocol_from_dict(
        _strict_json(payload, "clinical outcome protocol")
    )


def clinical_prediction_submission_from_json(
    payload: str,
) -> ClinicalPredictionSubmission:
    return clinical_prediction_submission_from_dict(
        _strict_json(payload, "clinical prediction submission")
    )


def clinical_outcome_manifest_from_json(payload: str) -> ClinicalOutcomeManifest:
    return clinical_outcome_manifest_from_dict(
        _strict_json(payload, "clinical outcome manifest")
    )


def clinical_outcome_report_from_json(
    payload: str,
) -> ClinicalOutcomeEvaluationReport:
    return clinical_outcome_report_from_dict(
        _strict_json(payload, "clinical outcome evaluation report")
    )
