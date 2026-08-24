"""Dependence-aware uncertainty for preregistered clinical outcome boards."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from itertools import combinations
from statistics import NormalDist
from typing import Any

from .clinical_cohort import ClinicalCohortPolicyIdentity, ClinicalCohortReport
from .clinical_outcome_evaluation import (
    ClinicalOutcomeEvaluationProtocol,
    ClinicalOutcomeEvaluationReport,
    ClinicalOutcomeManifest,
    ClinicalOutcomeStatus,
    ClinicalPredictionSubmission,
    _contains_hidden_outcome_metadata,
    _integrity_payload,
    _mapping,
    _parse_date,
    _parse_enum,
    _parse_policy,
    _record,
    _round_metric,
    _sequence,
    _sha256,
    _strict_json,
    evaluate_clinical_outcomes,
)
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
)
from .serialization import RecordParseError


CLINICAL_OUTCOME_DEPENDENCE_MANIFEST_SCHEMA_VERSION = (
    "adds.clinical-outcome-dependence-manifest.v1"
)
CLINICAL_OUTCOME_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-uncertainty-protocol.v1"
)
CLINICAL_OUTCOME_UNCERTAINTY_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-uncertainty-report.v1"
)
CLINICAL_OUTCOME_UNCERTAINTY_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-uncertainty-summary.v1"
)
CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID = (
    "adds.cluster-robust-clinical-outcome-uncertainty.cr1.v1"
)
CLINICAL_OUTCOME_STRATIFICATION_DIMENSIONS = ("stage", "endpoint_family")


class ClinicalOutcomeUncertaintyError(ValueError):
    """Raised when dependence-aware clinical evaluation cannot proceed safely."""


class ClusterInferenceStatus(str, Enum):
    COMPUTED = "cluster_robust_interval_computed"
    NO_EVALUABLE_UNITS = "not_estimable_no_evaluable_units"
    INSUFFICIENT_CLUSTERS = "not_estimable_insufficient_clusters"
    DOMINANT_CLUSTER = "not_estimable_dominant_cluster"
    ZERO_CLUSTER_VARIANCE = "not_estimable_zero_cluster_variance"


_REQUIRED_LIMITATIONS = (
    (
        "Cluster assignments are preregistered evaluator commitments; hashes and "
        "known-overlap checks do not prove that clusters are mutually independent."
    ),
    (
        "CR1 intervals allow arbitrary dependence within declared clusters but rely "
        "on asymptotic independence, bounded influence, and adequate count across clusters."
    ),
    (
        "Intervals are withheld when evaluable clusters are too few, one cluster exceeds "
        "the preregistered share limit, or observed cluster uncertainty is zero at the "
        "12-decimal reporting precision."
    ),
    (
        "Stage-by-endpoint strata are fixed from package identity before outcome access; "
        "small strata remain visible as attrition and are not pooled post hoc."
    ),
    (
        "Paired policy intervals preserve shared units and cluster covariance; repeated "
        "policies are not treated as independent clinical observations."
    ),
    (
        "No cluster-robust interval is reported for fixed-bin expected calibration error, "
        "which is retained only in the bound base outcome report."
    ),
    (
        "Aggregate uncertainty does not establish calibration transportability, policy "
        "superiority, treatment efficacy, safety, clinical utility, or acceptability."
    ),
)


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


def _require_optional_finite(
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


def _stratum_id(stage: Stage, endpoint_family: str) -> str:
    return _sha256(
        {
            "stage": stage.value,
            "endpoint_family": endpoint_family,
        }
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDependenceAssignment(SerializableRecord):
    evidence_unit_id: str
    cluster_id: str
    assignment_basis_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_unit_id, "evidence_unit_id")
        _require_sha256(self.cluster_id, "cluster_id")
        _require_sha256(self.assignment_basis_sha256, "assignment_basis_sha256")

    @property
    def sort_key(self) -> str:
        return self.evidence_unit_id


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDependenceManifest(SerializableRecord):
    manifest_id: str
    registered_on: date
    cohort_report_fingerprint: str
    construction_policy_sha256: str
    independence_attestation_sha256: str
    assignments: tuple[ClinicalOutcomeDependenceAssignment, ...]

    def __post_init__(self) -> None:
        _require_text(self.manifest_id, "manifest_id")
        _require_date(self.registered_on, "registered_on")
        for field_name in (
            "cohort_report_fingerprint",
            "construction_policy_sha256",
            "independence_attestation_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        assignments = _tuple(self.assignments, "assignments")
        object.__setattr__(self, "assignments", assignments)
        if not assignments:
            raise ValueError("dependence manifest must not be empty")
        for assignment in assignments:
            _require_instance(
                assignment,
                ClinicalOutcomeDependenceAssignment,
                "assignments item",
            )
        if tuple(item.sort_key for item in assignments) != tuple(
            sorted(item.sort_key for item in assignments)
        ):
            raise ValueError("dependence assignments must use canonical unit order")
        if len({item.evidence_unit_id for item in assignments}) != len(assignments):
            raise ValueError("dependence evidence-unit ids must be unique")
        basis_by_cluster: dict[str, str] = {}
        cluster_by_basis: dict[str, str] = {}
        for assignment in assignments:
            prior_basis = basis_by_cluster.setdefault(
                assignment.cluster_id,
                assignment.assignment_basis_sha256,
            )
            if prior_basis != assignment.assignment_basis_sha256:
                raise ValueError("one cluster must use one assignment-basis commitment")
            prior_cluster = cluster_by_basis.setdefault(
                assignment.assignment_basis_sha256,
                assignment.cluster_id,
            )
            if prior_cluster != assignment.cluster_id:
                raise ValueError(
                    "one assignment-basis commitment cannot name two clusters"
                )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeUncertaintyProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    outcome_protocol_id: str
    outcome_protocol_fingerprint: str
    cohort_report_fingerprint: str
    dependence_manifest_fingerprint: str
    confidence_level: float
    minimum_clusters_overall: int
    minimum_clusters_per_stratum: int
    maximum_evaluable_cluster_fraction: float
    method_id: str = CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID
    finite_cluster_correction_required: bool = True
    paired_cluster_covariance_required: bool = True
    stratification_dimensions: tuple[str, ...] = (
        CLINICAL_OUTCOME_STRATIFICATION_DIMENSIONS
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version", "outcome_protocol_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        for field_name in (
            "outcome_protocol_fingerprint",
            "cohort_report_fingerprint",
            "dependence_manifest_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        _require_positive_int(self.minimum_clusters_overall, "minimum_clusters_overall")
        _require_positive_int(
            self.minimum_clusters_per_stratum,
            "minimum_clusters_per_stratum",
        )
        if self.minimum_clusters_overall < 2:
            raise ValueError("minimum_clusters_overall must be at least two")
        if self.minimum_clusters_per_stratum < 2:
            raise ValueError("minimum_clusters_per_stratum must be at least two")
        _require_probability(
            self.maximum_evaluable_cluster_fraction,
            "maximum_evaluable_cluster_fraction",
        )
        if self.maximum_evaluable_cluster_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_evaluable_cluster_fraction must be strictly between zero and one"
            )
        if self.method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("method_id is unsupported")
        for field_name in (
            "finite_cluster_correction_required",
            "paired_cluster_covariance_required",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")
        dimensions = _tuple(self.stratification_dimensions, "stratification_dimensions")
        object.__setattr__(self, "stratification_dimensions", dimensions)
        if dimensions != CLINICAL_OUTCOME_STRATIFICATION_DIMENSIONS:
            raise ValueError("stratification_dimensions are unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError("uncertainty protocol metadata cannot contain outcomes")
        object.__setattr__(self, "metadata", metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterDiagnostic(SerializableRecord):
    total_units: int
    evaluable_units: int
    indeterminate_units: int
    cluster_count: int
    evaluable_cluster_count: int
    clusters_without_evaluable_units: int
    largest_evaluable_cluster_size: int
    largest_evaluable_cluster_fraction: float | None
    effective_evaluable_cluster_count: float | None
    minimum_required_clusters: int
    maximum_allowed_cluster_fraction: float
    requirement_met: bool
    status: ClusterInferenceStatus

    def __post_init__(self) -> None:
        _require_positive_int(self.total_units, "total_units")
        for field_name in (
            "evaluable_units",
            "indeterminate_units",
            "cluster_count",
            "evaluable_cluster_count",
            "clusters_without_evaluable_units",
            "largest_evaluable_cluster_size",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.evaluable_units + self.indeterminate_units != self.total_units:
            raise ValueError("cluster diagnostic attrition is inconsistent")
        if self.cluster_count < 1:
            raise ValueError("cluster_count must be positive")
        if self.cluster_count > self.total_units:
            raise ValueError("cluster_count exceeds total units")
        if (
            self.evaluable_cluster_count + self.clusters_without_evaluable_units
            != self.cluster_count
        ):
            raise ValueError("cluster diagnostic cluster counts are inconsistent")
        if self.clusters_without_evaluable_units > self.indeterminate_units:
            raise ValueError("empty evaluable clusters exceed indeterminate units")
        if self.evaluable_cluster_count > self.evaluable_units:
            raise ValueError("evaluable clusters exceed evaluable units")
        if self.evaluable_units == 0 and self.evaluable_cluster_count != 0:
            raise ValueError("empty evaluation requires zero evaluable clusters")
        if self.evaluable_units > 0 and self.evaluable_cluster_count == 0:
            raise ValueError("evaluable units require an evaluable cluster")
        if self.largest_evaluable_cluster_size > self.evaluable_units:
            raise ValueError("largest cluster exceeds evaluable units")
        _require_optional_finite(
            self.largest_evaluable_cluster_fraction,
            "largest_evaluable_cluster_fraction",
            minimum=0.0,
            maximum=1.0,
        )
        _require_optional_finite(
            self.effective_evaluable_cluster_count,
            "effective_evaluable_cluster_count",
            minimum=1.0,
        )
        _require_positive_int(
            self.minimum_required_clusters, "minimum_required_clusters"
        )
        if self.minimum_required_clusters < 2:
            raise ValueError("minimum_required_clusters must be at least two")
        _require_probability(
            self.maximum_allowed_cluster_fraction,
            "maximum_allowed_cluster_fraction",
        )
        if self.maximum_allowed_cluster_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_allowed_cluster_fraction must be strictly between zero and one"
            )
        _require_bool(self.requirement_met, "requirement_met")
        _require_instance(self.status, ClusterInferenceStatus, "status")
        if self.evaluable_units == 0:
            if (
                self.largest_evaluable_cluster_size != 0
                or self.largest_evaluable_cluster_fraction is not None
                or self.effective_evaluable_cluster_count is not None
            ):
                raise ValueError("empty diagnostics require null cluster-size metrics")
            raw_fraction = None
        else:
            if (
                self.largest_evaluable_cluster_size < 1
                or self.largest_evaluable_cluster_fraction is None
                or self.effective_evaluable_cluster_count is None
            ):
                raise ValueError("evaluable diagnostics require cluster-size metrics")
            if self.largest_evaluable_cluster_size < math.ceil(
                self.evaluable_units / self.evaluable_cluster_count
            ):
                raise ValueError("largest evaluable cluster is smaller than average")
            if self.largest_evaluable_cluster_size > (
                self.evaluable_units - self.evaluable_cluster_count + 1
            ):
                raise ValueError("largest evaluable cluster size is impossible")
            raw_fraction = self.largest_evaluable_cluster_size / self.evaluable_units
            if self.largest_evaluable_cluster_fraction != _round_metric(raw_fraction):
                raise ValueError("largest evaluable cluster fraction is inconsistent")
            assert self.effective_evaluable_cluster_count is not None
            if self.effective_evaluable_cluster_count > self.evaluable_cluster_count:
                raise ValueError("effective cluster count exceeds observed clusters")
        expected_status = _diagnostic_status(
            evaluable_units=self.evaluable_units,
            evaluable_cluster_count=self.evaluable_cluster_count,
            largest_fraction=raw_fraction,
            minimum_clusters=self.minimum_required_clusters,
            maximum_fraction=self.maximum_allowed_cluster_fraction,
        )
        if self.status is not expected_status:
            raise ValueError("cluster diagnostic status is inconsistent")
        if self.requirement_met != (self.status is ClusterInferenceStatus.COMPUTED):
            raise ValueError("cluster diagnostic requirement flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalClusterRobustEstimate(SerializableRecord):
    estimate: float | None
    standard_error: float | None
    lower: float | None
    upper: float | None
    confidence_level: float
    unit_count: int
    cluster_count: int
    status: ClusterInferenceStatus

    def __post_init__(self) -> None:
        for field_name in ("estimate", "standard_error", "lower", "upper"):
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=(0.0 if field_name == "standard_error" else -1.0),
                maximum=(None if field_name == "standard_error" else 1.0),
            )
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        _require_non_negative_int(self.unit_count, "unit_count")
        _require_non_negative_int(self.cluster_count, "cluster_count")
        if self.cluster_count > self.unit_count:
            raise ValueError("estimate cluster count exceeds unit count")
        _require_instance(self.status, ClusterInferenceStatus, "status")
        interval = (self.standard_error, self.lower, self.upper)
        if self.unit_count == 0:
            if self.estimate is not None or any(
                value is not None for value in interval
            ):
                raise ValueError("empty estimates require null values")
            if self.cluster_count != 0:
                raise ValueError("empty estimates require zero clusters")
            if self.status is not ClusterInferenceStatus.NO_EVALUABLE_UNITS:
                raise ValueError("empty estimate status is inconsistent")
            return
        if self.estimate is None or self.cluster_count < 1:
            raise ValueError("non-empty estimates require a point and clusters")
        if self.status is ClusterInferenceStatus.COMPUTED:
            if any(value is None for value in interval):
                raise ValueError("estimable metrics require interval values")
            assert self.standard_error is not None
            assert self.lower is not None
            assert self.upper is not None
            if self.standard_error <= 0.0:
                raise ValueError("estimable metrics require positive standard error")
            if not self.lower <= self.estimate <= self.upper:
                raise ValueError(
                    "cluster-robust interval does not contain its estimate"
                )
        elif any(value is not None for value in interval):
            raise ValueError("non-estimable metrics require null uncertainty values")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeUncertaintyPolicyMetrics(SerializableRecord):
    policy: ClinicalCohortPolicyIdentity
    submission_id: str
    submission_fingerprint: str
    total_units: int
    evaluable_units: int
    indeterminate_units: int
    observed_favorable_rate: ClinicalClusterRobustEstimate
    brier_score: ClinicalClusterRobustEstimate
    calibration_in_the_large: ClinicalClusterRobustEstimate
    classification_accuracy: ClinicalClusterRobustEstimate

    def __post_init__(self) -> None:
        _require_instance(self.policy, ClinicalCohortPolicyIdentity, "policy")
        _require_text(self.submission_id, "submission_id")
        _require_sha256(self.submission_fingerprint, "submission_fingerprint")
        _require_positive_int(self.total_units, "total_units")
        _require_non_negative_int(self.evaluable_units, "evaluable_units")
        _require_non_negative_int(self.indeterminate_units, "indeterminate_units")
        if self.evaluable_units + self.indeterminate_units != self.total_units:
            raise ValueError("policy uncertainty attrition is inconsistent")
        metrics = (
            self.observed_favorable_rate,
            self.brier_score,
            self.calibration_in_the_large,
            self.classification_accuracy,
        )
        for metric in metrics:
            _require_instance(metric, ClinicalClusterRobustEstimate, "policy metric")
            if metric.unit_count != self.evaluable_units:
                raise ValueError(
                    "policy uncertainty metric denominator is inconsistent"
                )
        if len({metric.cluster_count for metric in metrics}) != 1:
            raise ValueError("policy uncertainty metrics must share cluster count")
        _require_metric_range(self.observed_favorable_rate, 0.0, 1.0)
        _require_metric_range(self.brier_score, 0.0, 1.0)
        _require_metric_range(self.calibration_in_the_large, -1.0, 1.0)
        _require_metric_range(self.classification_accuracy, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class ClinicalMatchedOutcomeUncertainty(SerializableRecord):
    policy_a: ClinicalCohortPolicyIdentity
    policy_b: ClinicalCohortPolicyIdentity
    shared_units: int
    shared_evaluable_units: int
    shared_indeterminate_units: int
    brier_difference_b_minus_a: ClinicalClusterRobustEstimate

    def __post_init__(self) -> None:
        _require_instance(self.policy_a, ClinicalCohortPolicyIdentity, "policy_a")
        _require_instance(self.policy_b, ClinicalCohortPolicyIdentity, "policy_b")
        if self.policy_a.sort_key >= self.policy_b.sort_key:
            raise ValueError("matched uncertainty policies must use canonical order")
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
            raise ValueError("matched uncertainty attrition is inconsistent")
        _require_instance(
            self.brier_difference_b_minus_a,
            ClinicalClusterRobustEstimate,
            "brier_difference_b_minus_a",
        )
        if self.brier_difference_b_minus_a.unit_count != self.shared_evaluable_units:
            raise ValueError("paired Brier denominator is inconsistent")
        _require_metric_range(self.brier_difference_b_minus_a, -1.0, 1.0)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStratumUncertainty(SerializableRecord):
    stratum_id: str
    stage: Stage
    endpoint_family: str
    cluster_diagnostic: ClinicalOutcomeClusterDiagnostic
    policy_summaries: tuple[ClinicalOutcomeUncertaintyPolicyMetrics, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.stratum_id, "stratum_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        if self.stratum_id != _stratum_id(self.stage, self.endpoint_family):
            raise ValueError("stratum_id does not match stage and endpoint family")
        _require_instance(
            self.cluster_diagnostic,
            ClinicalOutcomeClusterDiagnostic,
            "cluster_diagnostic",
        )
        summaries = _tuple(self.policy_summaries, "policy_summaries")
        object.__setattr__(self, "policy_summaries", summaries)
        if not summaries:
            raise ValueError("stratum uncertainty requires policy summaries")
        for summary in summaries:
            _require_instance(
                summary,
                ClinicalOutcomeUncertaintyPolicyMetrics,
                "policy_summaries item",
            )
            if (
                summary.total_units != self.cluster_diagnostic.total_units
                or summary.evaluable_units != self.cluster_diagnostic.evaluable_units
                or summary.indeterminate_units
                != self.cluster_diagnostic.indeterminate_units
            ):
                raise ValueError("stratum policy attrition is inconsistent")
            _validate_metrics_against_diagnostic(
                summary,
                self.cluster_diagnostic,
            )
        if tuple(item.policy.sort_key for item in summaries) != tuple(
            sorted(item.policy.sort_key for item in summaries)
        ):
            raise ValueError("stratum policies must use canonical order")
        if len({item.policy.policy_fingerprint for item in summaries}) != len(
            summaries
        ):
            raise ValueError("stratum policy identities must be unique")
        if len({item.submission_id for item in summaries}) != len(summaries):
            raise ValueError("stratum submission ids must be unique")
        if len({item.submission_fingerprint for item in summaries}) != len(summaries):
            raise ValueError("stratum submission fingerprints must be unique")
        if any(
            item.observed_favorable_rate != summaries[0].observed_favorable_rate
            for item in summaries[1:]
        ):
            raise ValueError("stratum policies must share one observed favorable rate")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.stage.value, self.endpoint_family, self.stratum_id)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeUncertaintyReport(SerializableRecord):
    uncertainty_protocol_id: str
    uncertainty_protocol_fingerprint: str
    outcome_protocol_id: str
    outcome_protocol_fingerprint: str
    cohort_id: str
    cohort_report_fingerprint: str
    outcome_report_fingerprint: str
    outcome_manifest_fingerprint: str
    dependence_manifest_fingerprint: str
    method_id: str
    generated_on: date
    known_dependence_link_count: int
    overall_cluster_diagnostic: ClinicalOutcomeClusterDiagnostic
    policy_summaries: tuple[ClinicalOutcomeUncertaintyPolicyMetrics, ...]
    stratum_summaries: tuple[ClinicalOutcomeStratumUncertainty, ...]
    matched_policy_comparisons: tuple[ClinicalMatchedOutcomeUncertainty, ...]
    aggregate_outcomes_included: bool
    cluster_assignments_included: bool
    unit_level_predictions_included: bool
    unit_level_outcomes_included: bool
    ece_cluster_interval_included: bool
    policy_superiority_test_included: bool
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in (
            "uncertainty_protocol_id",
            "outcome_protocol_id",
            "cohort_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "uncertainty_protocol_fingerprint",
            "outcome_protocol_fingerprint",
            "cohort_report_fingerprint",
            "outcome_report_fingerprint",
            "outcome_manifest_fingerprint",
            "dependence_manifest_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("method_id is unsupported")
        _require_date(self.generated_on, "generated_on")
        _require_non_negative_int(
            self.known_dependence_link_count,
            "known_dependence_link_count",
        )
        _require_instance(
            self.overall_cluster_diagnostic,
            ClinicalOutcomeClusterDiagnostic,
            "overall_cluster_diagnostic",
        )
        summaries = _tuple(self.policy_summaries, "policy_summaries")
        object.__setattr__(self, "policy_summaries", summaries)
        if not summaries:
            raise ValueError("uncertainty report requires policy summaries")
        for summary in summaries:
            _require_instance(
                summary,
                ClinicalOutcomeUncertaintyPolicyMetrics,
                "policy_summaries item",
            )
            if (
                summary.total_units != self.overall_cluster_diagnostic.total_units
                or summary.evaluable_units
                != self.overall_cluster_diagnostic.evaluable_units
                or summary.indeterminate_units
                != self.overall_cluster_diagnostic.indeterminate_units
            ):
                raise ValueError("overall policy attrition is inconsistent")
            _validate_metrics_against_diagnostic(
                summary,
                self.overall_cluster_diagnostic,
            )
        if tuple(item.policy.sort_key for item in summaries) != tuple(
            sorted(item.policy.sort_key for item in summaries)
        ):
            raise ValueError("overall policies must use canonical order")
        policy_fingerprints = tuple(
            item.policy.policy_fingerprint for item in summaries
        )
        if len(policy_fingerprints) != len(set(policy_fingerprints)):
            raise ValueError("overall policy identities must be unique")
        if len({item.submission_id for item in summaries}) != len(summaries):
            raise ValueError("overall submission ids must be unique")
        if len({item.submission_fingerprint for item in summaries}) != len(summaries):
            raise ValueError("overall submission fingerprints must be unique")
        if any(
            item.observed_favorable_rate != summaries[0].observed_favorable_rate
            for item in summaries[1:]
        ):
            raise ValueError("policies must share one observed favorable rate")
        overall_confidence_levels = {
            metric.confidence_level
            for summary in summaries
            for metric in (
                summary.observed_favorable_rate,
                summary.brier_score,
                summary.calibration_in_the_large,
                summary.classification_accuracy,
            )
        }
        if len(overall_confidence_levels) != 1:
            raise ValueError("overall metrics must share one confidence level")
        strata = _tuple(self.stratum_summaries, "stratum_summaries")
        object.__setattr__(self, "stratum_summaries", strata)
        if not strata:
            raise ValueError("uncertainty report requires strata")
        for stratum in strata:
            _require_instance(
                stratum,
                ClinicalOutcomeStratumUncertainty,
                "stratum_summaries item",
            )
        if tuple(item.sort_key for item in strata) != tuple(
            sorted(item.sort_key for item in strata)
        ):
            raise ValueError("stratum summaries must use canonical order")
        if len({item.stratum_id for item in strata}) != len(strata):
            raise ValueError("stratum ids must be unique")
        if len(
            {item.cluster_diagnostic.minimum_required_clusters for item in strata}
        ) != 1:
            raise ValueError("strata must share one cluster minimum")
        if sum(item.cluster_diagnostic.total_units for item in strata) != (
            self.overall_cluster_diagnostic.total_units
        ):
            raise ValueError("stratum units do not sum to the overall cohort")
        if sum(item.cluster_diagnostic.evaluable_units for item in strata) != (
            self.overall_cluster_diagnostic.evaluable_units
        ):
            raise ValueError("stratum evaluable units do not sum to the overall cohort")
        for stratum in strata:
            if (
                stratum.cluster_diagnostic.cluster_count
                > self.overall_cluster_diagnostic.cluster_count
                or stratum.cluster_diagnostic.evaluable_cluster_count
                > self.overall_cluster_diagnostic.evaluable_cluster_count
            ):
                raise ValueError("stratum cluster counts exceed the overall cohort")
            if (
                tuple(
                    item.policy.policy_fingerprint for item in stratum.policy_summaries
                )
                != policy_fingerprints
            ):
                raise ValueError("strata must contain the same policy roster")
            for stratum_summary, overall_summary in zip(
                stratum.policy_summaries,
                summaries,
                strict=True,
            ):
                if (
                    stratum_summary.submission_id != overall_summary.submission_id
                    or stratum_summary.submission_fingerprint
                    != overall_summary.submission_fingerprint
                ):
                    raise ValueError("stratum submission binding is inconsistent")
            stratum_confidence_levels = {
                metric.confidence_level
                for summary in stratum.policy_summaries
                for metric in (
                    summary.observed_favorable_rate,
                    summary.brier_score,
                    summary.calibration_in_the_large,
                    summary.classification_accuracy,
                )
            }
            if stratum_confidence_levels != overall_confidence_levels:
                raise ValueError("strata must share the overall confidence level")
            if (
                stratum.cluster_diagnostic.maximum_allowed_cluster_fraction
                != self.overall_cluster_diagnostic.maximum_allowed_cluster_fraction
            ):
                raise ValueError("strata must share the overall cluster-share limit")
        comparisons = _tuple(
            self.matched_policy_comparisons,
            "matched_policy_comparisons",
        )
        object.__setattr__(self, "matched_policy_comparisons", comparisons)
        for comparison in comparisons:
            _require_instance(
                comparison,
                ClinicalMatchedOutcomeUncertainty,
                "matched_policy_comparisons item",
            )
        expected_pairs = tuple(
            (left.policy.sort_key, right.policy.sort_key)
            for left, right in combinations(summaries, 2)
        )
        observed_pairs = tuple(
            (item.policy_a.sort_key, item.policy_b.sort_key) for item in comparisons
        )
        if observed_pairs != expected_pairs:
            raise ValueError("paired uncertainty must exactly cover policy pairs")
        for comparison in comparisons:
            if (
                comparison.shared_units != self.overall_cluster_diagnostic.total_units
                or comparison.shared_evaluable_units
                != self.overall_cluster_diagnostic.evaluable_units
                or comparison.shared_indeterminate_units
                != self.overall_cluster_diagnostic.indeterminate_units
            ):
                raise ValueError("paired uncertainty attrition is inconsistent")
            if comparison.brier_difference_b_minus_a.cluster_count != (
                self.overall_cluster_diagnostic.evaluable_cluster_count
            ):
                raise ValueError("paired uncertainty cluster count is inconsistent")
            if self.overall_cluster_diagnostic.status is not (
                ClusterInferenceStatus.COMPUTED
            ) and comparison.brier_difference_b_minus_a.status is not (
                self.overall_cluster_diagnostic.status
            ):
                raise ValueError("paired uncertainty status is inconsistent")
            if self.overall_cluster_diagnostic.status is (
                ClusterInferenceStatus.COMPUTED
            ) and comparison.brier_difference_b_minus_a.status not in {
                ClusterInferenceStatus.COMPUTED,
                ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE,
            }:
                raise ValueError("paired uncertainty status is inconsistent")
            if {
                comparison.brier_difference_b_minus_a.confidence_level
            } != overall_confidence_levels:
                raise ValueError("paired uncertainty confidence level is inconsistent")
        summaries_by_policy = {
            item.policy.policy_fingerprint: item for item in summaries
        }
        for comparison in comparisons:
            summary_a = summaries_by_policy[comparison.policy_a.policy_fingerprint]
            summary_b = summaries_by_policy[comparison.policy_b.policy_fingerprint]
            estimate_a = summary_a.brier_score.estimate
            estimate_b = summary_b.brier_score.estimate
            paired_estimate = comparison.brier_difference_b_minus_a.estimate
            expected_difference = (
                None
                if estimate_a is None or estimate_b is None
                else _round_metric(estimate_b - estimate_a)
            )
            if (
                paired_estimate is None
                and expected_difference is not None
                or paired_estimate is not None
                and expected_difference is None
                or paired_estimate is not None
                and expected_difference is not None
                and not math.isclose(
                    paired_estimate,
                    expected_difference,
                    rel_tol=0.0,
                    abs_tol=2e-12,
                )
            ):
                raise ValueError("paired Brier point estimate is inconsistent")
        for field_name in (
            "aggregate_outcomes_included",
            "cluster_assignments_included",
            "unit_level_predictions_included",
            "unit_level_outcomes_included",
            "ece_cluster_interval_included",
            "policy_superiority_test_included",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.aggregate_outcomes_included:
            raise ValueError("uncertainty report requires aggregate outcomes")
        if (
            self.cluster_assignments_included
            or self.unit_level_predictions_included
            or self.unit_level_outcomes_included
            or self.ece_cluster_interval_included
            or self.policy_superiority_test_included
        ):
            raise ValueError("uncertainty report crossed its aggregate claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required uncertainty limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _require_metric_range(
    metric: ClinicalClusterRobustEstimate,
    minimum: float,
    maximum: float,
) -> None:
    for field_name in ("estimate", "lower", "upper"):
        value = getattr(metric, field_name)
        if value is not None and not minimum <= value <= maximum:
            raise ValueError(f"metric {field_name} falls outside its scale")


def _validate_metrics_against_diagnostic(
    summary: ClinicalOutcomeUncertaintyPolicyMetrics,
    diagnostic: ClinicalOutcomeClusterDiagnostic,
) -> None:
    metrics = (
        summary.observed_favorable_rate,
        summary.brier_score,
        summary.calibration_in_the_large,
        summary.classification_accuracy,
    )
    for metric in metrics:
        expected_clusters = diagnostic.evaluable_cluster_count
        if metric.cluster_count != expected_clusters:
            raise ValueError("policy metric cluster count is inconsistent")
        if diagnostic.status is not ClusterInferenceStatus.COMPUTED:
            if metric.status is not diagnostic.status:
                raise ValueError("policy metric cluster status is inconsistent")
        elif metric.status not in {
            ClusterInferenceStatus.COMPUTED,
            ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE,
        }:
            raise ValueError("policy metric status is inconsistent")
    confidence_levels = {metric.confidence_level for metric in metrics}
    if len(confidence_levels) != 1:
        raise ValueError("policy metric confidence levels are inconsistent")


def _diagnostic_status(
    *,
    evaluable_units: int,
    evaluable_cluster_count: int,
    largest_fraction: float | None,
    minimum_clusters: int,
    maximum_fraction: float,
) -> ClusterInferenceStatus:
    if evaluable_units == 0:
        return ClusterInferenceStatus.NO_EVALUABLE_UNITS
    if evaluable_cluster_count < minimum_clusters:
        return ClusterInferenceStatus.INSUFFICIENT_CLUSTERS
    assert largest_fraction is not None
    if largest_fraction > maximum_fraction:
        return ClusterInferenceStatus.DOMINANT_CLUSTER
    return ClusterInferenceStatus.COMPUTED


def _cluster_diagnostic(
    unit_ids: Sequence[str],
    evaluable_unit_ids: set[str],
    cluster_by_unit: Mapping[str, str],
    *,
    minimum_clusters: int,
    maximum_fraction: float,
) -> ClinicalOutcomeClusterDiagnostic:
    resolved_units = tuple(unit_ids)
    clusters = {cluster_by_unit[unit_id] for unit_id in resolved_units}
    evaluable_sizes: dict[str, int] = defaultdict(int)
    for unit_id in resolved_units:
        if unit_id in evaluable_unit_ids:
            evaluable_sizes[cluster_by_unit[unit_id]] += 1
    evaluable_units = sum(evaluable_sizes.values())
    evaluable_clusters = len(evaluable_sizes)
    largest = max(evaluable_sizes.values(), default=0)
    raw_fraction = None if evaluable_units == 0 else largest / evaluable_units
    fraction = None if raw_fraction is None else _round_metric(raw_fraction)
    effective = (
        None
        if evaluable_units == 0
        else _round_metric(
            evaluable_units
            * evaluable_units
            / sum(size * size for size in evaluable_sizes.values())
        )
    )
    status = _diagnostic_status(
        evaluable_units=evaluable_units,
        evaluable_cluster_count=evaluable_clusters,
        largest_fraction=raw_fraction,
        minimum_clusters=minimum_clusters,
        maximum_fraction=maximum_fraction,
    )
    return ClinicalOutcomeClusterDiagnostic(
        total_units=len(resolved_units),
        evaluable_units=evaluable_units,
        indeterminate_units=len(resolved_units) - evaluable_units,
        cluster_count=len(clusters),
        evaluable_cluster_count=evaluable_clusters,
        clusters_without_evaluable_units=len(clusters) - evaluable_clusters,
        largest_evaluable_cluster_size=largest,
        largest_evaluable_cluster_fraction=fraction,
        effective_evaluable_cluster_count=effective,
        minimum_required_clusters=minimum_clusters,
        maximum_allowed_cluster_fraction=maximum_fraction,
        requirement_met=status is ClusterInferenceStatus.COMPUTED,
        status=status,
    )


def _cluster_robust_estimate(
    values: Sequence[tuple[str, float]],
    diagnostic: ClinicalOutcomeClusterDiagnostic,
    *,
    confidence_level: float,
    lower_bound: float,
    upper_bound: float,
) -> ClinicalClusterRobustEstimate:
    resolved = tuple(values)
    if not resolved:
        return ClinicalClusterRobustEstimate(
            estimate=None,
            standard_error=None,
            lower=None,
            upper=None,
            confidence_level=confidence_level,
            unit_count=0,
            cluster_count=0,
            status=ClusterInferenceStatus.NO_EVALUABLE_UNITS,
        )
    raw_estimate = sum(value for _, value in resolved) / len(resolved)
    estimate = _round_metric(raw_estimate)
    cluster_values: dict[str, list[float]] = defaultdict(list)
    for cluster_id, value in resolved:
        cluster_values[cluster_id].append(value)
    if diagnostic.status is not ClusterInferenceStatus.COMPUTED:
        return ClinicalClusterRobustEstimate(
            estimate=estimate,
            standard_error=None,
            lower=None,
            upper=None,
            confidence_level=confidence_level,
            unit_count=len(resolved),
            cluster_count=len(cluster_values),
            status=diagnostic.status,
        )
    cluster_count = len(cluster_values)
    centered_cluster_sums = tuple(
        sum(value - raw_estimate for value in cluster)
        for cluster in cluster_values.values()
    )
    variance = (
        cluster_count
        / (cluster_count - 1)
        * sum(value * value for value in centered_cluster_sums)
        / (len(resolved) * len(resolved))
    )
    standard_error = math.sqrt(variance)
    reported_standard_error = _round_metric(standard_error)
    if reported_standard_error == 0.0:
        return ClinicalClusterRobustEstimate(
            estimate=estimate,
            standard_error=None,
            lower=None,
            upper=None,
            confidence_level=confidence_level,
            unit_count=len(resolved),
            cluster_count=cluster_count,
            status=ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE,
        )
    critical = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    lower = max(lower_bound, raw_estimate - critical * standard_error)
    upper = min(upper_bound, raw_estimate + critical * standard_error)
    return ClinicalClusterRobustEstimate(
        estimate=estimate,
        standard_error=reported_standard_error,
        lower=_round_metric(lower),
        upper=_round_metric(upper),
        confidence_level=confidence_level,
        unit_count=len(resolved),
        cluster_count=cluster_count,
        status=ClusterInferenceStatus.COMPUTED,
    )


def _known_dependence_links(
    cohort_report: ClinicalCohortReport,
    outcome_manifest: ClinicalOutcomeManifest,
) -> set[tuple[str, str]]:
    units_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for package in cohort_report.packages:
        unit_id = package.evidence_unit_id
        units_by_key[("program", package.program_id)].add(unit_id)
        for source_hash in package.source_content_hashes:
            units_by_key[("baseline_source", source_hash)].add(unit_id)
        for trial_id in package.trial_ids:
            units_by_key[("baseline_trial", trial_id)].add(unit_id)
    for assessment in outcome_manifest.assessments:
        for source in assessment.sources:
            units_by_key[("outcome_source", source.source_content_sha256)].add(
                assessment.evidence_unit_id
            )
            if source.trial_id is not None:
                units_by_key[("outcome_trial", source.trial_id)].add(
                    assessment.evidence_unit_id
                )
    links: set[tuple[str, str]] = set()
    for unit_ids in units_by_key.values():
        if len(unit_ids) < 2:
            continue
        for left, right in combinations(sorted(unit_ids), 2):
            links.add((left, right))
    return links


def _validate_inputs(
    uncertainty_protocol: ClinicalOutcomeUncertaintyProtocol,
    dependence_manifest: ClinicalOutcomeDependenceManifest,
    outcome_protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
    outcome_report: ClinicalOutcomeEvaluationReport,
) -> tuple[
    tuple[ClinicalPredictionSubmission, ...],
    dict[str, str],
    int,
]:
    for value, expected, field_name in (
        (
            uncertainty_protocol,
            ClinicalOutcomeUncertaintyProtocol,
            "uncertainty_protocol",
        ),
        (
            dependence_manifest,
            ClinicalOutcomeDependenceManifest,
            "dependence_manifest",
        ),
        (outcome_protocol, ClinicalOutcomeEvaluationProtocol, "outcome_protocol"),
        (cohort_report, ClinicalCohortReport, "cohort_report"),
        (outcome_manifest, ClinicalOutcomeManifest, "outcome_manifest"),
        (outcome_report, ClinicalOutcomeEvaluationReport, "outcome_report"),
    ):
        _require_instance(value, expected, field_name)
    resolved_submissions = _tuple(submissions, "submissions")
    if not resolved_submissions:
        raise ClinicalOutcomeUncertaintyError(
            "uncertainty evaluation requires submissions"
        )
    for submission in resolved_submissions:
        _require_instance(submission, ClinicalPredictionSubmission, "submissions item")
    rebuilt_outcome_report = evaluate_clinical_outcomes(
        outcome_protocol,
        cohort_report,
        resolved_submissions,
        outcome_manifest,
    )
    if rebuilt_outcome_report != outcome_report:
        raise ClinicalOutcomeUncertaintyError(
            "bound clinical outcome report does not reproduce"
        )
    if (
        uncertainty_protocol.outcome_protocol_id != outcome_protocol.protocol_id
        or uncertainty_protocol.outcome_protocol_fingerprint
        != outcome_protocol.fingerprint
    ):
        raise ClinicalOutcomeUncertaintyError(
            "uncertainty protocol outcome binding does not match"
        )
    if (
        uncertainty_protocol.cohort_report_fingerprint != cohort_report.fingerprint
        or dependence_manifest.cohort_report_fingerprint != cohort_report.fingerprint
    ):
        raise ClinicalOutcomeUncertaintyError(
            "uncertainty cohort binding does not match"
        )
    if (
        uncertainty_protocol.dependence_manifest_fingerprint
        != dependence_manifest.fingerprint
    ):
        raise ClinicalOutcomeUncertaintyError(
            "dependence manifest commitment does not match"
        )
    earliest_submission = min(item.submitted_on for item in resolved_submissions)
    if not (
        outcome_protocol.registered_on
        <= dependence_manifest.registered_on
        <= uncertainty_protocol.registered_on
        <= earliest_submission
        <= outcome_protocol.prediction_deadline
    ):
        raise ClinicalOutcomeUncertaintyError(
            "dependence protocol and manifest were not frozen before submission"
        )
    expected_units = {item.evidence_unit_id for item in cohort_report.packages}
    assignment_by_unit = {
        item.evidence_unit_id: item.cluster_id
        for item in dependence_manifest.assignments
    }
    if set(assignment_by_unit) != expected_units:
        raise ClinicalOutcomeUncertaintyError(
            "dependence assignments do not exactly cover cohort evidence units"
        )
    known_links = _known_dependence_links(cohort_report, outcome_manifest)
    if any(
        assignment_by_unit[left] != assignment_by_unit[right]
        for left, right in known_links
    ):
        raise ClinicalOutcomeUncertaintyError(
            "known program, trial, or source dependence was split across clusters"
        )
    return (
        tuple(sorted(resolved_submissions, key=lambda item: item.policy.sort_key)),
        assignment_by_unit,
        len(known_links),
    )


def _policy_metrics(
    submission: ClinicalPredictionSubmission,
    unit_ids: Sequence[str],
    outcomes_by_unit: Mapping[str, Any],
    cluster_by_unit: Mapping[str, str],
    diagnostic: ClinicalOutcomeClusterDiagnostic,
    outcome_protocol: ClinicalOutcomeEvaluationProtocol,
    uncertainty_protocol: ClinicalOutcomeUncertaintyProtocol,
) -> ClinicalOutcomeUncertaintyPolicyMetrics:
    predictions = {
        item.evidence_unit_id: item.favorable_probability
        for item in submission.predictions
    }
    observed: list[tuple[str, float]] = []
    brier: list[tuple[str, float]] = []
    calibration: list[tuple[str, float]] = []
    accuracy: list[tuple[str, float]] = []
    for unit_id in unit_ids:
        status = outcomes_by_unit[unit_id].composite_status
        if status is ClinicalOutcomeStatus.INDETERMINATE:
            continue
        label = float(status is ClinicalOutcomeStatus.FAVORABLE)
        probability = predictions[unit_id]
        cluster_id = cluster_by_unit[unit_id]
        observed.append((cluster_id, label))
        brier.append((cluster_id, (probability - label) ** 2))
        calibration.append((cluster_id, probability - label))
        accuracy.append(
            (
                cluster_id,
                float(
                    (probability >= outcome_protocol.classification_threshold)
                    == bool(label)
                ),
            )
        )
    kwargs = {
        "diagnostic": diagnostic,
        "confidence_level": uncertainty_protocol.confidence_level,
    }
    return ClinicalOutcomeUncertaintyPolicyMetrics(
        policy=submission.policy,
        submission_id=submission.submission_id,
        submission_fingerprint=submission.fingerprint,
        total_units=len(unit_ids),
        evaluable_units=len(observed),
        indeterminate_units=len(unit_ids) - len(observed),
        observed_favorable_rate=_cluster_robust_estimate(
            observed,
            lower_bound=0.0,
            upper_bound=1.0,
            **kwargs,
        ),
        brier_score=_cluster_robust_estimate(
            brier,
            lower_bound=0.0,
            upper_bound=1.0,
            **kwargs,
        ),
        calibration_in_the_large=_cluster_robust_estimate(
            calibration,
            lower_bound=-1.0,
            upper_bound=1.0,
            **kwargs,
        ),
        classification_accuracy=_cluster_robust_estimate(
            accuracy,
            lower_bound=0.0,
            upper_bound=1.0,
            **kwargs,
        ),
    )


def _paired_metrics(
    submission_a: ClinicalPredictionSubmission,
    submission_b: ClinicalPredictionSubmission,
    unit_ids: Sequence[str],
    outcomes_by_unit: Mapping[str, Any],
    cluster_by_unit: Mapping[str, str],
    diagnostic: ClinicalOutcomeClusterDiagnostic,
    uncertainty_protocol: ClinicalOutcomeUncertaintyProtocol,
) -> ClinicalMatchedOutcomeUncertainty:
    predictions_a = {
        item.evidence_unit_id: item.favorable_probability
        for item in submission_a.predictions
    }
    predictions_b = {
        item.evidence_unit_id: item.favorable_probability
        for item in submission_b.predictions
    }
    differences: list[tuple[str, float]] = []
    for unit_id in unit_ids:
        status = outcomes_by_unit[unit_id].composite_status
        if status is ClinicalOutcomeStatus.INDETERMINATE:
            continue
        label = float(status is ClinicalOutcomeStatus.FAVORABLE)
        loss_a = (predictions_a[unit_id] - label) ** 2
        loss_b = (predictions_b[unit_id] - label) ** 2
        differences.append((cluster_by_unit[unit_id], loss_b - loss_a))
    return ClinicalMatchedOutcomeUncertainty(
        policy_a=submission_a.policy,
        policy_b=submission_b.policy,
        shared_units=len(unit_ids),
        shared_evaluable_units=len(differences),
        shared_indeterminate_units=len(unit_ids) - len(differences),
        brier_difference_b_minus_a=_cluster_robust_estimate(
            differences,
            diagnostic,
            confidence_level=uncertainty_protocol.confidence_level,
            lower_bound=-1.0,
            upper_bound=1.0,
        ),
    )


def evaluate_clinical_outcome_uncertainty(
    uncertainty_protocol: ClinicalOutcomeUncertaintyProtocol,
    dependence_manifest: ClinicalOutcomeDependenceManifest,
    outcome_protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
    outcome_report: ClinicalOutcomeEvaluationReport,
) -> ClinicalOutcomeUncertaintyReport:
    """Compute aggregate CR1 intervals while preserving evaluator-only assignments."""

    ordered_submissions, cluster_by_unit, known_link_count = _validate_inputs(
        uncertainty_protocol,
        dependence_manifest,
        outcome_protocol,
        cohort_report,
        submissions,
        outcome_manifest,
        outcome_report,
    )
    outcomes_by_unit = {
        item.evidence_unit_id: item for item in outcome_manifest.assessments
    }
    unit_ids = tuple(sorted(outcomes_by_unit))
    evaluable_unit_ids = {
        unit_id
        for unit_id, outcome in outcomes_by_unit.items()
        if outcome.composite_status is not ClinicalOutcomeStatus.INDETERMINATE
    }
    overall_diagnostic = _cluster_diagnostic(
        unit_ids,
        evaluable_unit_ids,
        cluster_by_unit,
        minimum_clusters=uncertainty_protocol.minimum_clusters_overall,
        maximum_fraction=uncertainty_protocol.maximum_evaluable_cluster_fraction,
    )
    policy_summaries = tuple(
        _policy_metrics(
            submission,
            unit_ids,
            outcomes_by_unit,
            cluster_by_unit,
            overall_diagnostic,
            outcome_protocol,
            uncertainty_protocol,
        )
        for submission in ordered_submissions
    )
    units_by_stratum: dict[tuple[Stage, str], list[str]] = defaultdict(list)
    for unit_id in unit_ids:
        outcome = outcomes_by_unit[unit_id]
        units_by_stratum[(outcome.stage, outcome.endpoint_family)].append(unit_id)
    strata = []
    for (stage, endpoint_family), stratum_units in sorted(
        units_by_stratum.items(),
        key=lambda item: (item[0][0].value, item[0][1]),
    ):
        resolved_units = tuple(sorted(stratum_units))
        diagnostic = _cluster_diagnostic(
            resolved_units,
            evaluable_unit_ids,
            cluster_by_unit,
            minimum_clusters=uncertainty_protocol.minimum_clusters_per_stratum,
            maximum_fraction=uncertainty_protocol.maximum_evaluable_cluster_fraction,
        )
        strata.append(
            ClinicalOutcomeStratumUncertainty(
                stratum_id=_stratum_id(stage, endpoint_family),
                stage=stage,
                endpoint_family=endpoint_family,
                cluster_diagnostic=diagnostic,
                policy_summaries=tuple(
                    _policy_metrics(
                        submission,
                        resolved_units,
                        outcomes_by_unit,
                        cluster_by_unit,
                        diagnostic,
                        outcome_protocol,
                        uncertainty_protocol,
                    )
                    for submission in ordered_submissions
                ),
            )
        )
    comparisons = tuple(
        _paired_metrics(
            submission_a,
            submission_b,
            unit_ids,
            outcomes_by_unit,
            cluster_by_unit,
            overall_diagnostic,
            uncertainty_protocol,
        )
        for submission_a, submission_b in combinations(ordered_submissions, 2)
    )
    return ClinicalOutcomeUncertaintyReport(
        uncertainty_protocol_id=uncertainty_protocol.protocol_id,
        uncertainty_protocol_fingerprint=uncertainty_protocol.fingerprint,
        outcome_protocol_id=outcome_protocol.protocol_id,
        outcome_protocol_fingerprint=outcome_protocol.fingerprint,
        cohort_id=cohort_report.cohort_id,
        cohort_report_fingerprint=cohort_report.fingerprint,
        outcome_report_fingerprint=outcome_report.fingerprint,
        outcome_manifest_fingerprint=outcome_manifest.fingerprint,
        dependence_manifest_fingerprint=dependence_manifest.fingerprint,
        method_id=CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID,
        generated_on=outcome_report.generated_on,
        known_dependence_link_count=known_link_count,
        overall_cluster_diagnostic=overall_diagnostic,
        policy_summaries=policy_summaries,
        stratum_summaries=tuple(strata),
        matched_policy_comparisons=comparisons,
        aggregate_outcomes_included=True,
        cluster_assignments_included=False,
        unit_level_predictions_included=False,
        unit_level_outcomes_included=False,
        ece_cluster_interval_included=False,
        policy_superiority_test_included=False,
    )


def validate_clinical_outcome_uncertainty_report(
    report: ClinicalOutcomeUncertaintyReport,
    uncertainty_protocol: ClinicalOutcomeUncertaintyProtocol,
    dependence_manifest: ClinicalOutcomeDependenceManifest,
    outcome_protocol: ClinicalOutcomeEvaluationProtocol,
    cohort_report: ClinicalCohortReport,
    submissions: Sequence[ClinicalPredictionSubmission],
    outcome_manifest: ClinicalOutcomeManifest,
    outcome_report: ClinicalOutcomeEvaluationReport,
) -> tuple[str, ...]:
    """Replay all private inputs and compare the aggregate report exactly."""

    try:
        rebuilt = evaluate_clinical_outcome_uncertainty(
            uncertainty_protocol,
            dependence_manifest,
            outcome_protocol,
            cohort_report,
            submissions,
            outcome_manifest,
            outcome_report,
        )
    except (ClinicalOutcomeUncertaintyError, TypeError, ValueError):
        return ("clinical_outcome_uncertainty_recompile_failed",)
    if rebuilt != report:
        return ("recompiled_clinical_outcome_uncertainty_report_mismatch",)
    return ()


def clinical_outcome_uncertainty_summary(
    report: ClinicalOutcomeUncertaintyReport,
) -> dict[str, Any]:
    """Return a compact aggregate projection without assignments or unit labels."""

    _require_instance(report, ClinicalOutcomeUncertaintyReport, "report")
    diagnostic = report.overall_cluster_diagnostic

    def diagnostic_projection(
        value: ClinicalOutcomeClusterDiagnostic,
    ) -> dict[str, Any]:
        return {
            "cluster_status": value.status.value,
            "outcome_units": {
                "total": value.total_units,
                "evaluable": value.evaluable_units,
                "indeterminate": value.indeterminate_units,
            },
            "clusters": {
                "total": value.cluster_count,
                "evaluable": value.evaluable_cluster_count,
                "without_evaluable_units": value.clusters_without_evaluable_units,
                "largest_evaluable_size": value.largest_evaluable_cluster_size,
                "largest_evaluable_fraction": (
                    value.largest_evaluable_cluster_fraction
                ),
                "effective_evaluable_count": value.effective_evaluable_cluster_count,
                "minimum_required": value.minimum_required_clusters,
                "maximum_allowed_fraction": (
                    value.maximum_allowed_cluster_fraction
                ),
                "requirement_met": value.requirement_met,
            },
        }

    def policy_projection(
        value: ClinicalOutcomeUncertaintyPolicyMetrics,
    ) -> dict[str, Any]:
        return {
            "policy_id": value.policy.policy_id,
            "policy_version": value.policy.policy_version,
            "policy_fingerprint": value.policy.policy_fingerprint,
            "observed_favorable_rate": value.observed_favorable_rate.to_dict(),
            "brier_score": value.brier_score.to_dict(),
            "calibration_in_the_large": value.calibration_in_the_large.to_dict(),
            "classification_accuracy": value.classification_accuracy.to_dict(),
        }

    return {
        "schema_version": CLINICAL_OUTCOME_UNCERTAINTY_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "uncertainty_protocol_id": report.uncertainty_protocol_id,
        "outcome_protocol_id": report.outcome_protocol_id,
        "cohort_id": report.cohort_id,
        **diagnostic_projection(diagnostic),
        "known_dependence_link_count": report.known_dependence_link_count,
        "policy_summaries": [policy_projection(item) for item in report.policy_summaries],
        "strata": [
            {
                "stratum_id": item.stratum_id,
                "stage": item.stage.value,
                "endpoint_family": item.endpoint_family,
                **diagnostic_projection(item.cluster_diagnostic),
                "policy_summaries": [
                    policy_projection(summary) for summary in item.policy_summaries
                ],
            }
            for item in report.stratum_summaries
        ],
        "stratum_count": len(report.stratum_summaries),
        "matched_policy_comparisons": [
            {
                "policy_a": item.policy_a.to_dict(),
                "policy_b": item.policy_b.to_dict(),
                "shared_outcome_units": {
                    "total": item.shared_units,
                    "evaluable": item.shared_evaluable_units,
                    "indeterminate": item.shared_indeterminate_units,
                },
                "brier_difference_b_minus_a": (
                    item.brier_difference_b_minus_a.to_dict()
                ),
            }
            for item in report.matched_policy_comparisons
        ],
        "matched_policy_comparison_count": len(report.matched_policy_comparisons),
        "aggregate_outcomes_included": report.aggregate_outcomes_included,
        "cluster_assignments_included": report.cluster_assignments_included,
        "unit_level_predictions_included": report.unit_level_predictions_included,
        "unit_level_outcomes_included": report.unit_level_outcomes_included,
        "ece_cluster_interval_included": report.ece_cluster_interval_included,
        "policy_superiority_test_included": report.policy_superiority_test_included,
    }


def clinical_outcome_uncertainty_validation_summary(
    report: ClinicalOutcomeUncertaintyReport,
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
        **clinical_outcome_uncertainty_summary(report),
        "validation": {
            "status": "valid" if not resolved_failures else "invalid",
            "scope": scope,
            "failure_codes": list(resolved_failures),
        },
    }


def clinical_outcome_dependence_manifest_envelope(
    manifest: ClinicalOutcomeDependenceManifest,
) -> dict[str, Any]:
    _require_instance(manifest, ClinicalOutcomeDependenceManifest, "manifest")
    return {
        "schema_version": CLINICAL_OUTCOME_DEPENDENCE_MANIFEST_SCHEMA_VERSION,
        "integrity_sha256": manifest.fingerprint,
        "manifest": manifest.to_dict(),
    }


def clinical_outcome_uncertainty_protocol_envelope(
    protocol: ClinicalOutcomeUncertaintyProtocol,
) -> dict[str, Any]:
    _require_instance(protocol, ClinicalOutcomeUncertaintyProtocol, "protocol")
    return {
        "schema_version": CLINICAL_OUTCOME_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_uncertainty_report_envelope(
    report: ClinicalOutcomeUncertaintyReport,
) -> dict[str, Any]:
    _require_instance(report, ClinicalOutcomeUncertaintyReport, "report")
    return {
        "schema_version": CLINICAL_OUTCOME_UNCERTAINTY_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    fingerprint = getattr(value, "fingerprint", None)
    if fingerprint != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def _parse_dependence_assignment(
    value: Any,
    path: str,
) -> ClinicalOutcomeDependenceAssignment:
    data = _record(
        value,
        path,
        {"evidence_unit_id", "cluster_id", "assignment_basis_sha256"},
    )
    return ClinicalOutcomeDependenceAssignment(
        evidence_unit_id=data["evidence_unit_id"],
        cluster_id=data["cluster_id"],
        assignment_basis_sha256=data["assignment_basis_sha256"],
    )


def clinical_outcome_dependence_manifest_from_dict(
    value: Any,
) -> ClinicalOutcomeDependenceManifest:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_dependence_manifest_envelope",
        schema_version=CLINICAL_OUTCOME_DEPENDENCE_MANIFEST_SCHEMA_VERSION,
        payload_field="manifest",
    )
    data = _record(
        payload,
        "manifest",
        {
            "manifest_id",
            "registered_on",
            "cohort_report_fingerprint",
            "construction_policy_sha256",
            "independence_attestation_sha256",
            "assignments",
        },
    )
    manifest = ClinicalOutcomeDependenceManifest(
        manifest_id=data["manifest_id"],
        registered_on=_parse_date(data["registered_on"], "manifest.registered_on"),
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        construction_policy_sha256=data["construction_policy_sha256"],
        independence_attestation_sha256=data["independence_attestation_sha256"],
        assignments=tuple(
            _parse_dependence_assignment(item, f"manifest.assignments[{index}]")
            for index, item in enumerate(
                _sequence(data["assignments"], "manifest.assignments")
            )
        ),
    )
    _check_integrity(manifest, integrity, "dependence manifest")
    return manifest


def clinical_outcome_uncertainty_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeUncertaintyProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_uncertainty_protocol_envelope",
        schema_version=CLINICAL_OUTCOME_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION,
        payload_field="protocol",
    )
    data = _record(
        payload,
        "protocol",
        {
            "protocol_id",
            "version",
            "registered_on",
            "outcome_protocol_id",
            "outcome_protocol_fingerprint",
            "cohort_report_fingerprint",
            "dependence_manifest_fingerprint",
            "confidence_level",
            "minimum_clusters_overall",
            "minimum_clusters_per_stratum",
            "maximum_evaluable_cluster_fraction",
            "method_id",
            "finite_cluster_correction_required",
            "paired_cluster_covariance_required",
            "stratification_dimensions",
            "metadata",
        },
    )
    protocol = ClinicalOutcomeUncertaintyProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        outcome_protocol_id=data["outcome_protocol_id"],
        outcome_protocol_fingerprint=data["outcome_protocol_fingerprint"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        dependence_manifest_fingerprint=data["dependence_manifest_fingerprint"],
        confidence_level=data["confidence_level"],
        minimum_clusters_overall=data["minimum_clusters_overall"],
        minimum_clusters_per_stratum=data["minimum_clusters_per_stratum"],
        maximum_evaluable_cluster_fraction=data["maximum_evaluable_cluster_fraction"],
        method_id=data["method_id"],
        finite_cluster_correction_required=data["finite_cluster_correction_required"],
        paired_cluster_covariance_required=data["paired_cluster_covariance_required"],
        stratification_dimensions=tuple(
            _sequence(
                data["stratification_dimensions"],
                "protocol.stratification_dimensions",
            )
        ),
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "uncertainty protocol")
    return protocol


def _parse_cluster_diagnostic(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterDiagnostic:
    data = _record(
        value,
        path,
        {
            "total_units",
            "evaluable_units",
            "indeterminate_units",
            "cluster_count",
            "evaluable_cluster_count",
            "clusters_without_evaluable_units",
            "largest_evaluable_cluster_size",
            "largest_evaluable_cluster_fraction",
            "effective_evaluable_cluster_count",
            "minimum_required_clusters",
            "maximum_allowed_cluster_fraction",
            "requirement_met",
            "status",
        },
    )
    return ClinicalOutcomeClusterDiagnostic(
        total_units=data["total_units"],
        evaluable_units=data["evaluable_units"],
        indeterminate_units=data["indeterminate_units"],
        cluster_count=data["cluster_count"],
        evaluable_cluster_count=data["evaluable_cluster_count"],
        clusters_without_evaluable_units=data["clusters_without_evaluable_units"],
        largest_evaluable_cluster_size=data["largest_evaluable_cluster_size"],
        largest_evaluable_cluster_fraction=data["largest_evaluable_cluster_fraction"],
        effective_evaluable_cluster_count=data["effective_evaluable_cluster_count"],
        minimum_required_clusters=data["minimum_required_clusters"],
        maximum_allowed_cluster_fraction=data["maximum_allowed_cluster_fraction"],
        requirement_met=data["requirement_met"],
        status=_parse_enum(ClusterInferenceStatus, data["status"], f"{path}.status"),
    )


def _parse_cluster_estimate(
    value: Any,
    path: str,
) -> ClinicalClusterRobustEstimate:
    data = _record(
        value,
        path,
        {
            "estimate",
            "standard_error",
            "lower",
            "upper",
            "confidence_level",
            "unit_count",
            "cluster_count",
            "status",
        },
    )
    return ClinicalClusterRobustEstimate(
        estimate=data["estimate"],
        standard_error=data["standard_error"],
        lower=data["lower"],
        upper=data["upper"],
        confidence_level=data["confidence_level"],
        unit_count=data["unit_count"],
        cluster_count=data["cluster_count"],
        status=_parse_enum(ClusterInferenceStatus, data["status"], f"{path}.status"),
    )


def _parse_policy_metrics(
    value: Any,
    path: str,
) -> ClinicalOutcomeUncertaintyPolicyMetrics:
    data = _record(
        value,
        path,
        {
            "policy",
            "submission_id",
            "submission_fingerprint",
            "total_units",
            "evaluable_units",
            "indeterminate_units",
            "observed_favorable_rate",
            "brier_score",
            "calibration_in_the_large",
            "classification_accuracy",
        },
    )
    return ClinicalOutcomeUncertaintyPolicyMetrics(
        policy=_parse_policy(data["policy"], f"{path}.policy"),
        submission_id=data["submission_id"],
        submission_fingerprint=data["submission_fingerprint"],
        total_units=data["total_units"],
        evaluable_units=data["evaluable_units"],
        indeterminate_units=data["indeterminate_units"],
        observed_favorable_rate=_parse_cluster_estimate(
            data["observed_favorable_rate"],
            f"{path}.observed_favorable_rate",
        ),
        brier_score=_parse_cluster_estimate(
            data["brier_score"],
            f"{path}.brier_score",
        ),
        calibration_in_the_large=_parse_cluster_estimate(
            data["calibration_in_the_large"],
            f"{path}.calibration_in_the_large",
        ),
        classification_accuracy=_parse_cluster_estimate(
            data["classification_accuracy"],
            f"{path}.classification_accuracy",
        ),
    )


def _parse_matched_uncertainty(
    value: Any,
    path: str,
) -> ClinicalMatchedOutcomeUncertainty:
    data = _record(
        value,
        path,
        {
            "policy_a",
            "policy_b",
            "shared_units",
            "shared_evaluable_units",
            "shared_indeterminate_units",
            "brier_difference_b_minus_a",
        },
    )
    return ClinicalMatchedOutcomeUncertainty(
        policy_a=_parse_policy(data["policy_a"], f"{path}.policy_a"),
        policy_b=_parse_policy(data["policy_b"], f"{path}.policy_b"),
        shared_units=data["shared_units"],
        shared_evaluable_units=data["shared_evaluable_units"],
        shared_indeterminate_units=data["shared_indeterminate_units"],
        brier_difference_b_minus_a=_parse_cluster_estimate(
            data["brier_difference_b_minus_a"],
            f"{path}.brier_difference_b_minus_a",
        ),
    )


def _parse_stratum_uncertainty(
    value: Any,
    path: str,
) -> ClinicalOutcomeStratumUncertainty:
    data = _record(
        value,
        path,
        {
            "stratum_id",
            "stage",
            "endpoint_family",
            "cluster_diagnostic",
            "policy_summaries",
        },
    )
    return ClinicalOutcomeStratumUncertainty(
        stratum_id=data["stratum_id"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        endpoint_family=data["endpoint_family"],
        cluster_diagnostic=_parse_cluster_diagnostic(
            data["cluster_diagnostic"],
            f"{path}.cluster_diagnostic",
        ),
        policy_summaries=tuple(
            _parse_policy_metrics(item, f"{path}.policy_summaries[{index}]")
            for index, item in enumerate(
                _sequence(data["policy_summaries"], f"{path}.policy_summaries")
            )
        ),
    )


def clinical_outcome_uncertainty_report_from_dict(
    value: Any,
) -> ClinicalOutcomeUncertaintyReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_uncertainty_report_envelope",
        schema_version=CLINICAL_OUTCOME_UNCERTAINTY_REPORT_SCHEMA_VERSION,
        payload_field="report",
    )
    data = _record(
        payload,
        "report",
        {
            "uncertainty_protocol_id",
            "uncertainty_protocol_fingerprint",
            "outcome_protocol_id",
            "outcome_protocol_fingerprint",
            "cohort_id",
            "cohort_report_fingerprint",
            "outcome_report_fingerprint",
            "outcome_manifest_fingerprint",
            "dependence_manifest_fingerprint",
            "method_id",
            "generated_on",
            "known_dependence_link_count",
            "overall_cluster_diagnostic",
            "policy_summaries",
            "stratum_summaries",
            "matched_policy_comparisons",
            "aggregate_outcomes_included",
            "cluster_assignments_included",
            "unit_level_predictions_included",
            "unit_level_outcomes_included",
            "ece_cluster_interval_included",
            "policy_superiority_test_included",
            "limitations",
        },
    )
    report = ClinicalOutcomeUncertaintyReport(
        uncertainty_protocol_id=data["uncertainty_protocol_id"],
        uncertainty_protocol_fingerprint=data["uncertainty_protocol_fingerprint"],
        outcome_protocol_id=data["outcome_protocol_id"],
        outcome_protocol_fingerprint=data["outcome_protocol_fingerprint"],
        cohort_id=data["cohort_id"],
        cohort_report_fingerprint=data["cohort_report_fingerprint"],
        outcome_report_fingerprint=data["outcome_report_fingerprint"],
        outcome_manifest_fingerprint=data["outcome_manifest_fingerprint"],
        dependence_manifest_fingerprint=data["dependence_manifest_fingerprint"],
        method_id=data["method_id"],
        generated_on=_parse_date(data["generated_on"], "report.generated_on"),
        known_dependence_link_count=data["known_dependence_link_count"],
        overall_cluster_diagnostic=_parse_cluster_diagnostic(
            data["overall_cluster_diagnostic"],
            "report.overall_cluster_diagnostic",
        ),
        policy_summaries=tuple(
            _parse_policy_metrics(item, f"report.policy_summaries[{index}]")
            for index, item in enumerate(
                _sequence(data["policy_summaries"], "report.policy_summaries")
            )
        ),
        stratum_summaries=tuple(
            _parse_stratum_uncertainty(item, f"report.stratum_summaries[{index}]")
            for index, item in enumerate(
                _sequence(data["stratum_summaries"], "report.stratum_summaries")
            )
        ),
        matched_policy_comparisons=tuple(
            _parse_matched_uncertainty(
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
        aggregate_outcomes_included=data["aggregate_outcomes_included"],
        cluster_assignments_included=data["cluster_assignments_included"],
        unit_level_predictions_included=data["unit_level_predictions_included"],
        unit_level_outcomes_included=data["unit_level_outcomes_included"],
        ece_cluster_interval_included=data["ece_cluster_interval_included"],
        policy_superiority_test_included=data["policy_superiority_test_included"],
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
    )
    _check_integrity(report, integrity, "uncertainty report")
    return report


def clinical_outcome_dependence_manifest_from_json(
    payload: str,
) -> ClinicalOutcomeDependenceManifest:
    return clinical_outcome_dependence_manifest_from_dict(
        _strict_json(payload, "clinical outcome dependence manifest")
    )


def clinical_outcome_uncertainty_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeUncertaintyProtocol:
    return clinical_outcome_uncertainty_protocol_from_dict(
        _strict_json(payload, "clinical outcome uncertainty protocol")
    )


def clinical_outcome_uncertainty_report_from_json(
    payload: str,
) -> ClinicalOutcomeUncertaintyReport:
    return clinical_outcome_uncertainty_report_from_dict(
        _strict_json(payload, "clinical outcome uncertainty report")
    )
