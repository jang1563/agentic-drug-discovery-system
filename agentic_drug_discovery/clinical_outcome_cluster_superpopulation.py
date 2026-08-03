"""Cluster-superpopulation calibration for informative cluster size."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from types import SimpleNamespace
from typing import Any

from .clinical_outcome_design_simulation import (
    MAX_DESIGN_WORK_UNITS,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomeDesignRate,
    _design_rate,
    _draw_beta_binomial_label,
    _METRIC_ORDER,
    _parse_design_rate,
    _require_bool,
    _require_finite,
    _require_non_negative_int,
    _require_optional_finite,
    _require_positive_int,
    _tuple,
)
from .clinical_outcome_evaluation import (
    _contains_hidden_outcome_metadata,
    _integrity_payload,
    _mapping,
    _parse_date,
    _parse_enum,
    _record,
    _round_metric,
    _sequence,
    _sha256,
    _strict_json,
)
from .clinical_outcome_informative_cluster_size import (
    ClinicalOutcomeClusterInfluenceBasis,
    ClinicalOutcomeClusterSizeCell,
    ClinicalOutcomeClusterSizeEstimand,
    ClinicalOutcomeClusterSizeMethod,
    ClinicalOutcomeClusterSizeMethodResult,
    ClinicalOutcomeClusterSizeMetricResult,
    ClinicalOutcomeClusterSizeProfile,
    ClinicalOutcomeClusterSizeStatus,
    ClinicalOutcomeInformativeClusterSizeProtocol,
    ClinicalOutcomeInformativeClusterSizeReport,
    ClinicalOutcomeInformativeClusterSizeScenarioResult,
    ClinicalOutcomeThresholdDirection,
    _CellAccumulator,
    _add_interval,
    _block_metric_estimates,
    _check_integrity,
    _cluster_balanced_estimates,
    _fail_method_cells,
    _finalize_cell,
    _influence_basis,
    _parse_method_result,
    _profile_truths,
    _rate_projection,
    _size_outcome_association,
    _target_estimand,
    _threshold_direction,
    _unit_weighted_estimates,
    validate_clinical_outcome_informative_cluster_size_report,
)
from .clinical_outcome_pattern_mixture import MAX_ABSOLUTE_LOG_IMOR, _true_log_imor
from .clinical_outcome_pattern_mixture_influence_calibration import (
    _delete_mj_estimate_and_variance,
    _delete_one_variance,
    _linear_quantile,
    _student_t_critical,
)
from .clinical_outcome_pattern_mixture_uncertainty import _scenario_layout
from .clinical_outcome_stress_simulation import (
    CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    _substream_sha256,
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


CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-cluster-superpopulation-protocol.v1"
)
CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-cluster-superpopulation-report.v1"
)
CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-cluster-superpopulation-summary.v1"
)
CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_METHOD_ID = (
    "adds.pattern-mixture.cluster-superpopulation-calibration.v1"
)


class ClinicalOutcomeClusterSuperpopulationError(ValueError):
    """Raised when a cluster-superpopulation study cannot run safely."""


class ClinicalOutcomeClusterSuperpopulationSamplingModel(str, Enum):
    UNIFORM_EMPIRICAL_TEMPLATE_WITH_REPLACEMENT = (
        "uniform_empirical_template_with_replacement"
    )


class ClinicalOutcomeClusterCountRule(str, Enum):
    MATCH_TEMPLATE_COUNT = "match_template_count"


_METHOD_ORDER = tuple(ClinicalOutcomeClusterSizeMethod)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic cluster-superpopulation study and contains no real "
        "clinical outcomes, dependence manifest, or deployed policy result."
    ),
    (
        "The sampling frame is the finite empirical support of each fixed-profile "
        "scenario; it is not an external clinical population and does not establish "
        "transportability."
    ),
    (
        "Clusters are sampled independently and uniformly with replacement, their sizes, "
        "prediction-stratum layouts, and favorable prevalences remain jointly attached to "
        "the sampled template, and each replicate keeps the template cluster count."
    ),
    (
        "Uniform empirical-template sampling preserves the fixed-profile unit-weighted and "
        "cluster-balanced known truths exactly, so the comparison isolates sampling-frame "
        "variance under this declared model rather than changing the estimand."
    ),
    (
        "Unit-weighted and cluster-balanced functionals answer different questions under "
        "informative cluster size; neither is selected automatically or preferred without "
        "a prospectively declared scientific estimand."
    ),
    (
        "The unit-weighted functional is estimated by a random-denominator ratio estimator, "
        "so finite-cluster bias is measured rather than assumed absent."
    ),
    (
        "No replicate is removed, reweighted, or selected after observing realized cluster "
        "dominance, support, direction, coverage, or calibration; production eligibility is "
        "reported only as an aggregate design diagnostic."
    ),
    (
        "Delete-mj changes the unequal-size jackknife calculation but does not convert the "
        "unit-weighted estimator into a cluster-balanced estimand."
    ),
    (
        "Influence diagnostics use method-specific scales, handle largest-cluster ties "
        "explicitly, and are comparable only within method; no replicate- or cluster-level "
        "records are exposed."
    ),
    (
        "Every interval remains conditional on one binary log-IMOR pattern-mixture "
        "functional; missing-data identification uncertainty and cluster-sampling "
        "uncertainty are reported separately rather than combined."
    ),
    (
        "Monte Carlo bounds quantify finite simulation error for rates, bias, and mean "
        "interval width; the SE-to-empirical-SD ratio is a point diagnostic."
    ),
    (
        "Passing this synthetic study does not establish efficacy, safety, benefit-risk, "
        "policy superiority, treatment utility, regulatory acceptability, or performance "
        "in a new sampling frame."
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    stress_protocol_fingerprint: str
    fixed_profile_protocol_fingerprint: str
    fixed_profile_report_fingerprint: str
    sampling_model: ClinicalOutcomeClusterSuperpopulationSamplingModel
    cluster_count_rule: ClinicalOutcomeClusterCountRule
    replicates: int
    random_seed: int
    methods: tuple[ClinicalOutcomeClusterSizeMethod, ...]
    log_imor_grid: tuple[float, ...]
    reference_log_imor: float
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_tolerance: float
    minimum_interval_yield: float
    maximum_absolute_bias: float
    minimum_production_clusters: int
    maximum_production_cluster_unit_fraction: float
    maximum_standard_error_calibration_deviation: float
    primary_metric: ClinicalOutcomeDesignMetric
    direction_threshold: float
    method_id: str = CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_METHOD_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        for field_name in (
            "stress_protocol_fingerprint",
            "fixed_profile_protocol_fingerprint",
            "fixed_profile_report_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_instance(
            self.sampling_model,
            ClinicalOutcomeClusterSuperpopulationSamplingModel,
            "sampling_model",
        )
        _require_instance(
            self.cluster_count_rule,
            ClinicalOutcomeClusterCountRule,
            "cluster_count_rule",
        )
        _require_positive_int(self.replicates, "replicates")
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")
        if not 0 <= self.random_seed <= 2**63 - 1:
            raise ValueError("random_seed falls outside the supported range")
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        for method in methods:
            _require_instance(method, ClinicalOutcomeClusterSizeMethod, "method")
        if methods != _METHOD_ORDER:
            raise ValueError("methods must exactly cover canonical estimand methods")
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        if not grid or grid != tuple(sorted(set(grid))):
            raise ValueError("log_imor_grid must be unique and increasing")
        for index, value in enumerate(grid):
            _require_finite(
                value,
                f"log_imor_grid[{index}]",
                minimum=-MAX_ABSOLUTE_LOG_IMOR,
                maximum=MAX_ABSOLUTE_LOG_IMOR,
            )
        _require_finite(
            self.reference_log_imor,
            "reference_log_imor",
            minimum=-MAX_ABSOLUTE_LOG_IMOR,
            maximum=MAX_ABSOLUTE_LOG_IMOR,
        )
        if self.reference_log_imor not in grid:
            raise ValueError("reference_log_imor must appear in log_imor_grid")
        for field_name in ("confidence_level", "monte_carlo_confidence_level"):
            value = getattr(self, field_name)
            _require_probability(value, field_name)
            if not 0.5 < value < 1.0:
                raise ValueError(f"{field_name} must be between 0.5 and 1")
        _require_probability(self.coverage_tolerance, "coverage_tolerance")
        if self.coverage_tolerance >= self.confidence_level:
            raise ValueError("coverage_tolerance must be smaller than confidence_level")
        _require_probability(self.minimum_interval_yield, "minimum_interval_yield")
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be positive")
        _require_finite(
            self.maximum_absolute_bias,
            "maximum_absolute_bias",
            minimum=0.0,
            maximum=1.0,
        )
        if self.maximum_absolute_bias == 0.0:
            raise ValueError("maximum_absolute_bias must be positive")
        _require_positive_int(
            self.minimum_production_clusters,
            "minimum_production_clusters",
        )
        if self.minimum_production_clusters < 3:
            raise ValueError("minimum_production_clusters must be at least three")
        _require_probability(
            self.maximum_production_cluster_unit_fraction,
            "maximum_production_cluster_unit_fraction",
        )
        if self.maximum_production_cluster_unit_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_production_cluster_unit_fraction must be strictly interior"
            )
        _require_finite(
            self.maximum_standard_error_calibration_deviation,
            "maximum_standard_error_calibration_deviation",
            minimum=0.0,
            maximum=1.0,
        )
        if self.maximum_standard_error_calibration_deviation == 0.0:
            raise ValueError(
                "maximum_standard_error_calibration_deviation must be positive"
            )
        _require_instance(self.primary_metric, ClinicalOutcomeDesignMetric, "primary_metric")
        if self.primary_metric is not ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE:
            raise ValueError(
                "v1 direction diagnostics require observed_favorable_rate as primary_metric"
            )
        _require_probability(self.direction_threshold, "direction_threshold")
        if self.method_id != CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_METHOD_ID:
            raise ValueError("method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(metadata):
            raise ValueError("protocol metadata cannot contain evaluator outcomes")
        object.__setattr__(self, "metadata", metadata)

    @property
    def coverage_target(self) -> float:
        return _round_metric(self.confidence_level - self.coverage_tolerance)

    @property
    def standard_error_calibration_lower(self) -> float:
        return _round_metric(1.0 - self.maximum_standard_error_calibration_deviation)

    @property
    def standard_error_calibration_upper(self) -> float:
        return _round_metric(1.0 + self.maximum_standard_error_calibration_deviation)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationDesignDiagnostic(SerializableRecord):
    replicate_count: int
    sampled_cluster_count: int
    template_type_count: int
    expected_cluster_size: float
    mean_realized_total_units: float
    minimum_realized_total_units: int
    maximum_realized_total_units: int
    mean_unique_template_types: float
    mean_maximum_cluster_fraction: float
    p95_maximum_cluster_fraction: float
    insufficient_cluster_rate: ClinicalOutcomeDesignRate
    dominant_cluster_rate: ClinicalOutcomeDesignRate
    production_eligible_rate: ClinicalOutcomeDesignRate
    unique_largest_cluster_rate: ClinicalOutcomeDesignRate

    def __post_init__(self) -> None:
        for field_name in (
            "replicate_count",
            "sampled_cluster_count",
            "template_type_count",
            "minimum_realized_total_units",
            "maximum_realized_total_units",
        ):
            _require_positive_int(getattr(self, field_name), field_name)
        if self.minimum_realized_total_units > self.maximum_realized_total_units:
            raise ValueError("realized total-unit bounds are inconsistent")
        for field_name in (
            "expected_cluster_size",
            "mean_realized_total_units",
            "mean_unique_template_types",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        if not 1.0 <= self.mean_unique_template_types <= self.template_type_count:
            raise ValueError("mean_unique_template_types is inconsistent")
        for field_name in (
            "mean_maximum_cluster_fraction",
            "p95_maximum_cluster_fraction",
        ):
            _require_probability(getattr(self, field_name), field_name)
        rates = (
            self.insufficient_cluster_rate,
            self.dominant_cluster_rate,
            self.production_eligible_rate,
            self.unique_largest_cluster_rate,
        )
        for value in rates:
            _require_instance(value, ClinicalOutcomeDesignRate, "design rate")
            if value.total_count != self.replicate_count:
                raise ValueError("design-rate denominator is inconsistent")
        if len({value.confidence_level for value in rates}) != 1:
            raise ValueError("design-rate confidence levels changed")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic(SerializableRecord):
    method: ClinicalOutcomeClusterSizeMethod
    basis: ClinicalOutcomeClusterInfluenceBasis
    primary_metric: ClinicalOutcomeDesignMetric
    reference_log_imor: float
    analyzable_replicate_count: int
    mean_maximum_absolute_influence: float | None
    p95_maximum_absolute_influence: float | None
    mean_maximum_absolute_influence_share: float | None
    unique_largest_cluster_rate: ClinicalOutcomeDesignRate
    unique_largest_cluster_most_influential: ClinicalOutcomeDesignRate
    largest_cluster_deletion_direction_flip_applicable: bool
    largest_cluster_deletion_direction_flip: ClinicalOutcomeDesignRate

    def __post_init__(self) -> None:
        _require_instance(self.method, ClinicalOutcomeClusterSizeMethod, "method")
        _require_instance(self.basis, ClinicalOutcomeClusterInfluenceBasis, "basis")
        if self.basis is not _influence_basis(self.method):
            raise ValueError("influence basis is inconsistent")
        _require_instance(self.primary_metric, ClinicalOutcomeDesignMetric, "primary_metric")
        _require_finite(self.reference_log_imor, "reference_log_imor")
        _require_non_negative_int(
            self.analyzable_replicate_count,
            "analyzable_replicate_count",
        )
        for field_name in (
            "mean_maximum_absolute_influence",
            "p95_maximum_absolute_influence",
            "mean_maximum_absolute_influence_share",
        ):
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
                maximum=(
                    1.0
                    if field_name == "mean_maximum_absolute_influence_share"
                    else None
                ),
            )
        summaries = (
            self.mean_maximum_absolute_influence,
            self.p95_maximum_absolute_influence,
            self.mean_maximum_absolute_influence_share,
        )
        if self.analyzable_replicate_count == 0 and any(
            value is not None for value in summaries
        ):
            raise ValueError("empty influence diagnostics require null summaries")
        if self.analyzable_replicate_count > 0 and any(
            value is None for value in summaries
        ):
            raise ValueError("analyzable influence diagnostics require summaries")
        rates = (
            self.unique_largest_cluster_rate,
            self.unique_largest_cluster_most_influential,
            self.largest_cluster_deletion_direction_flip,
        )
        for value in rates:
            _require_instance(value, ClinicalOutcomeDesignRate, "influence rate")
        if len({value.confidence_level for value in rates}) != 1:
            raise ValueError("influence-rate confidence levels changed")
        if self.unique_largest_cluster_rate.total_count != self.analyzable_replicate_count:
            raise ValueError("unique-largest rate denominator is inconsistent")
        unique_count = self.unique_largest_cluster_rate.event_count
        if self.unique_largest_cluster_most_influential.total_count != unique_count:
            raise ValueError("largest-cluster influence denominator is inconsistent")
        expected_applicable = (
            self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT
        )
        _require_bool(
            self.largest_cluster_deletion_direction_flip_applicable,
            "largest_cluster_deletion_direction_flip_applicable",
        )
        if self.largest_cluster_deletion_direction_flip_applicable != expected_applicable:
            raise ValueError("direction-flip applicability is inconsistent")
        expected_flip_total = unique_count if expected_applicable else 0
        if self.largest_cluster_deletion_direction_flip.total_count != expected_flip_total:
            raise ValueError("direction-flip denominator is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationComparisonCell(SerializableRecord):
    method: ClinicalOutcomeClusterSizeMethod
    target_estimand: ClinicalOutcomeClusterSizeEstimand
    metric: ClinicalOutcomeDesignMetric
    log_imor: float
    target_true_value: float
    fixed_profile_target_true_value: float
    truth_difference: float
    fixed_profile_target_bias: float | None
    superpopulation_target_bias: float | None
    target_bias_change: float | None
    fixed_profile_target_coverage: ClinicalOutcomeDesignRate
    superpopulation_target_coverage: ClinicalOutcomeDesignRate
    coverage_rate_change: float | None
    fixed_profile_standard_error_to_empirical_sd_ratio: float | None
    superpopulation_standard_error_to_empirical_sd_ratio: float | None
    standard_error_ratio_change: float | None
    fixed_profile_standard_error_calibration_target_met: bool
    superpopulation_standard_error_calibration_target_met: bool
    standard_error_calibration_recovered: bool
    fixed_profile_calibration_target_met: bool
    superpopulation_calibration_target_met: bool
    full_calibration_recovered: bool

    def __post_init__(self) -> None:
        _require_instance(self.method, ClinicalOutcomeClusterSizeMethod, "method")
        _require_instance(
            self.target_estimand,
            ClinicalOutcomeClusterSizeEstimand,
            "target_estimand",
        )
        if self.target_estimand is not _target_estimand(self.method):
            raise ValueError("comparison target estimand is inconsistent")
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        _require_finite(
            self.log_imor,
            "log_imor",
            minimum=-MAX_ABSOLUTE_LOG_IMOR,
            maximum=MAX_ABSOLUTE_LOG_IMOR,
        )
        for field_name in ("target_true_value", "fixed_profile_target_true_value"):
            _require_finite(getattr(self, field_name), field_name)
        expected_truth_difference = _round_metric(
            self.target_true_value - self.fixed_profile_target_true_value
        )
        if self.truth_difference != expected_truth_difference:
            raise ValueError("comparison truth difference is inconsistent")
        if self.truth_difference != 0.0:
            raise ValueError("empirical-template sampling must preserve known truth")
        optional_fields = (
            "fixed_profile_target_bias",
            "superpopulation_target_bias",
            "target_bias_change",
            "coverage_rate_change",
            "fixed_profile_standard_error_to_empirical_sd_ratio",
            "superpopulation_standard_error_to_empirical_sd_ratio",
            "standard_error_ratio_change",
        )
        for field_name in optional_fields:
            _require_optional_finite(getattr(self, field_name), field_name)
        expected_bias_change = (
            None
            if self.fixed_profile_target_bias is None
            or self.superpopulation_target_bias is None
            else _round_metric(
                self.superpopulation_target_bias - self.fixed_profile_target_bias
            )
        )
        if self.target_bias_change != expected_bias_change:
            raise ValueError("target-bias comparison is inconsistent")
        for value, field_name in (
            (self.fixed_profile_target_coverage, "fixed_profile_target_coverage"),
            (
                self.superpopulation_target_coverage,
                "superpopulation_target_coverage",
            ),
        ):
            _require_instance(value, ClinicalOutcomeDesignRate, field_name)
        expected_coverage_change = (
            None
            if self.fixed_profile_target_coverage.rate is None
            or self.superpopulation_target_coverage.rate is None
            else _round_metric(
                self.superpopulation_target_coverage.rate
                - self.fixed_profile_target_coverage.rate
            )
        )
        if self.coverage_rate_change != expected_coverage_change:
            raise ValueError("coverage comparison is inconsistent")
        expected_ratio_change = (
            None
            if self.fixed_profile_standard_error_to_empirical_sd_ratio is None
            or self.superpopulation_standard_error_to_empirical_sd_ratio is None
            else _round_metric(
                self.superpopulation_standard_error_to_empirical_sd_ratio
                - self.fixed_profile_standard_error_to_empirical_sd_ratio
            )
        )
        if self.standard_error_ratio_change != expected_ratio_change:
            raise ValueError("standard-error comparison is inconsistent")
        flag_names = (
            "fixed_profile_standard_error_calibration_target_met",
            "superpopulation_standard_error_calibration_target_met",
            "standard_error_calibration_recovered",
            "fixed_profile_calibration_target_met",
            "superpopulation_calibration_target_met",
            "full_calibration_recovered",
        )
        for field_name in flag_names:
            _require_bool(getattr(self, field_name), field_name)
        if self.standard_error_calibration_recovered != (
            not self.fixed_profile_standard_error_calibration_target_met
            and self.superpopulation_standard_error_calibration_target_met
        ):
            raise ValueError("standard-error recovery flag is inconsistent")
        if self.full_calibration_recovered != (
            not self.fixed_profile_calibration_target_met
            and self.superpopulation_calibration_target_met
        ):
            raise ValueError("full-calibration recovery flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationScenarioResult(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    true_log_imor: float
    fixed_profile_scenario_fingerprint: str
    template_cluster_sizes: tuple[int, ...]
    template_favorable_prevalences: tuple[float, ...]
    superpopulation_unit_weighted_favorable_prevalence: float
    superpopulation_cluster_balanced_favorable_prevalence: float
    favorable_prevalence_contrast_unit_minus_cluster: float
    size_outcome_covariance: float
    size_outcome_correlation: float | None
    unit_weighted_reference_direction: ClinicalOutcomeThresholdDirection
    cluster_balanced_reference_direction: ClinicalOutcomeThresholdDirection
    truth_direction_disagrees: bool
    design_diagnostic: ClinicalOutcomeClusterSuperpopulationDesignDiagnostic
    method_results: tuple[ClinicalOutcomeClusterSizeMethodResult, ...]
    conditional_comparisons: tuple[
        ClinicalOutcomeClusterSuperpopulationComparisonCell, ...
    ]
    influence_diagnostics: tuple[
        ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic, ...
    ]
    rng_stream_sha256: str
    template_sampling_rng_stream_sha256: str
    outcome_rng_stream_sha256: str
    evaluability_rng_stream_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        _require_finite(
            self.true_log_imor,
            "true_log_imor",
            minimum=-MAX_ABSOLUTE_LOG_IMOR,
            maximum=MAX_ABSOLUTE_LOG_IMOR,
        )
        _require_sha256(
            self.fixed_profile_scenario_fingerprint,
            "fixed_profile_scenario_fingerprint",
        )
        sizes = _tuple(self.template_cluster_sizes, "template_cluster_sizes")
        prevalences = _tuple(
            self.template_favorable_prevalences,
            "template_favorable_prevalences",
        )
        object.__setattr__(self, "template_cluster_sizes", sizes)
        object.__setattr__(self, "template_favorable_prevalences", prevalences)
        if not sizes or len(sizes) != len(prevalences):
            raise ValueError("template sizes and prevalences must be nonempty and matched")
        for size in sizes:
            _require_positive_int(size, "template cluster size")
        for prevalence in prevalences:
            _require_probability(prevalence, "template favorable prevalence")
            if prevalence in (0.0, 1.0):
                raise ValueError("template favorable prevalences must be strictly interior")
        for field_name in (
            "superpopulation_unit_weighted_favorable_prevalence",
            "superpopulation_cluster_balanced_favorable_prevalence",
        ):
            _require_probability(getattr(self, field_name), field_name)
        expected_contrast = _round_metric(
            self.superpopulation_unit_weighted_favorable_prevalence
            - self.superpopulation_cluster_balanced_favorable_prevalence
        )
        if self.favorable_prevalence_contrast_unit_minus_cluster != expected_contrast:
            raise ValueError("favorable-prevalence contrast is inconsistent")
        _require_finite(self.size_outcome_covariance, "size_outcome_covariance")
        _require_optional_finite(
            self.size_outcome_correlation,
            "size_outcome_correlation",
            minimum=-1.0,
            maximum=1.0,
        )
        expected_unit_prevalence = _round_metric(
            sum(
                size * prevalence
                for size, prevalence in zip(sizes, prevalences, strict=True)
            )
            / sum(sizes)
        )
        expected_cluster_prevalence = _round_metric(
            sum(prevalences) / len(prevalences)
        )
        if (
            self.superpopulation_unit_weighted_favorable_prevalence
            != expected_unit_prevalence
            or self.superpopulation_cluster_balanced_favorable_prevalence
            != expected_cluster_prevalence
        ):
            raise ValueError("superpopulation favorable prevalences are inconsistent")
        expected_covariance, expected_correlation = _size_outcome_association(
            sizes,
            prevalences,
        )
        if (
            self.size_outcome_covariance != expected_covariance
            or self.size_outcome_correlation != expected_correlation
        ):
            raise ValueError("size-outcome association is inconsistent")
        for value, field_name in (
            (self.unit_weighted_reference_direction, "unit_weighted_reference_direction"),
            (
                self.cluster_balanced_reference_direction,
                "cluster_balanced_reference_direction",
            ),
        ):
            _require_instance(value, ClinicalOutcomeThresholdDirection, field_name)
        _require_bool(self.truth_direction_disagrees, "truth_direction_disagrees")
        if self.truth_direction_disagrees != (
            self.unit_weighted_reference_direction
            is not self.cluster_balanced_reference_direction
        ):
            raise ValueError("truth-direction disagreement flag is inconsistent")
        _require_instance(
            self.design_diagnostic,
            ClinicalOutcomeClusterSuperpopulationDesignDiagnostic,
            "design_diagnostic",
        )
        if (
            self.design_diagnostic.sampled_cluster_count != len(sizes)
            or self.design_diagnostic.template_type_count != len(sizes)
            or self.design_diagnostic.expected_cluster_size
            != _round_metric(sum(sizes) / len(sizes))
        ):
            raise ValueError("design diagnostic template count is inconsistent")
        methods = _tuple(self.method_results, "method_results")
        object.__setattr__(self, "method_results", methods)
        for item in methods:
            _require_instance(item, ClinicalOutcomeClusterSizeMethodResult, "method result")
        if tuple(item.method for item in methods) != _METHOD_ORDER:
            raise ValueError("method_results must exactly cover canonical methods")
        comparisons = _tuple(self.conditional_comparisons, "conditional_comparisons")
        object.__setattr__(self, "conditional_comparisons", comparisons)
        for item in comparisons:
            _require_instance(
                item,
                ClinicalOutcomeClusterSuperpopulationComparisonCell,
                "comparison cell",
            )
        expected_keys = tuple(
            (cell.method, cell.metric, cell.log_imor)
            for method in methods
            for metric in method.metric_inference
            for cell in metric.grid_inference
        )
        actual_keys = tuple(
            (item.method, item.metric, item.log_imor) for item in comparisons
        )
        if actual_keys != expected_keys:
            raise ValueError("conditional comparisons do not cover method cells canonically")
        cell_by_key = {
            (cell.method, cell.metric, cell.log_imor): cell
            for method in methods
            for metric in method.metric_inference
            for cell in metric.grid_inference
        }
        for comparison in comparisons:
            cell = cell_by_key[
                (comparison.method, comparison.metric, comparison.log_imor)
            ]
            if (
                comparison.target_estimand is not cell.target_estimand
                or comparison.target_true_value != cell.target_true_value
                or comparison.superpopulation_target_bias != cell.target_bias
                or comparison.superpopulation_target_coverage != cell.target_coverage
                or comparison.superpopulation_standard_error_to_empirical_sd_ratio
                != cell.standard_error_to_empirical_sd_ratio
                or comparison.superpopulation_standard_error_calibration_target_met
                != cell.standard_error_calibration_target_met
                or comparison.superpopulation_calibration_target_met
                != cell.calibration_target_met
            ):
                raise ValueError("comparison does not match its superpopulation cell")
        diagnostics = _tuple(self.influence_diagnostics, "influence_diagnostics")
        object.__setattr__(self, "influence_diagnostics", diagnostics)
        for item in diagnostics:
            _require_instance(
                item,
                ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic,
                "influence diagnostic",
            )
        if tuple(item.method for item in diagnostics) != _METHOD_ORDER:
            raise ValueError("influence_diagnostics must exactly cover canonical methods")
        for field_name in (
            "rng_stream_sha256",
            "template_sampling_rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if (
            self.template_sampling_rng_stream_sha256
            != _substream_sha256(self.rng_stream_sha256, "template_sampling")
            or self.outcome_rng_stream_sha256
            != _substream_sha256(self.rng_stream_sha256, "outcomes")
            or self.evaluability_rng_stream_sha256
            != _substream_sha256(self.rng_stream_sha256, "evaluability")
        ):
            raise ValueError("scenario RNG substream binding is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSuperpopulationReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    stress_protocol_id: str
    stress_protocol_fingerprint: str
    fixed_profile_protocol_id: str
    fixed_profile_protocol_fingerprint: str
    fixed_profile_report_fingerprint: str
    method_id: str
    rng_method_id: str
    sampling_model: ClinicalOutcomeClusterSuperpopulationSamplingModel
    cluster_count_rule: ClinicalOutcomeClusterCountRule
    replicates: int
    random_seed: int
    methods: tuple[ClinicalOutcomeClusterSizeMethod, ...]
    log_imor_grid: tuple[float, ...]
    reference_log_imor: float
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_target: float
    minimum_interval_yield: float
    maximum_absolute_bias: float
    minimum_production_clusters: int
    maximum_production_cluster_unit_fraction: float
    standard_error_calibration_lower: float
    standard_error_calibration_upper: float
    primary_metric: ClinicalOutcomeDesignMetric
    direction_threshold: float
    scenario_results: tuple[ClinicalOutcomeClusterSuperpopulationScenarioResult, ...]
    aggregate_simulation_only: bool = True
    replicate_level_records_included: bool = False
    cluster_level_records_included: bool = False
    unit_level_records_included: bool = False
    real_clinical_outcomes_included: bool = False
    empirical_template_sampling_frame: bool = True
    iid_cluster_sampling_assumed: bool = True
    fixed_profile_known_truths_preserved: bool = True
    cluster_superpopulation_resampling_included: bool = True
    automatic_estimand_selection_included: bool = False
    post_hoc_design_filtering_included: bool = False
    dominant_cluster_override_allowed: bool = False
    external_transportability_claimed: bool = False
    identification_and_sampling_uncertainty_separated: bool = True
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in (
            "protocol_id",
            "stress_protocol_id",
            "fixed_profile_protocol_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "stress_protocol_fingerprint",
            "fixed_profile_protocol_fingerprint",
            "fixed_profile_report_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        _require_instance(
            self.sampling_model,
            ClinicalOutcomeClusterSuperpopulationSamplingModel,
            "sampling_model",
        )
        _require_instance(
            self.cluster_count_rule,
            ClinicalOutcomeClusterCountRule,
            "cluster_count_rule",
        )
        _require_positive_int(self.replicates, "replicates")
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")
        if not 0 <= self.random_seed <= 2**63 - 1:
            raise ValueError("random_seed falls outside the supported range")
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        if methods != _METHOD_ORDER:
            raise ValueError("methods changed")
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        if not grid or grid != tuple(sorted(set(grid))):
            raise ValueError("log_imor_grid must be unique and increasing")
        if self.reference_log_imor not in grid:
            raise ValueError("reference_log_imor is absent from grid")
        for field_name in (
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_target",
            "minimum_interval_yield",
            "maximum_production_cluster_unit_fraction",
            "direction_threshold",
        ):
            _require_probability(getattr(self, field_name), field_name)
        _require_finite(
            self.maximum_absolute_bias,
            "maximum_absolute_bias",
            minimum=0.0,
            maximum=1.0,
        )
        _require_positive_int(
            self.minimum_production_clusters,
            "minimum_production_clusters",
        )
        for field_name in (
            "standard_error_calibration_lower",
            "standard_error_calibration_upper",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        if not (
            self.standard_error_calibration_lower < 1.0
            < self.standard_error_calibration_upper
            and _round_metric(1.0 - self.standard_error_calibration_lower)
            == _round_metric(self.standard_error_calibration_upper - 1.0)
        ):
            raise ValueError("standard-error calibration bounds must be symmetric")
        _require_instance(self.primary_metric, ClinicalOutcomeDesignMetric, "primary_metric")
        scenarios = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", scenarios)
        if not scenarios:
            raise ValueError("scenario_results cannot be empty")
        for item in scenarios:
            _require_instance(
                item,
                ClinicalOutcomeClusterSuperpopulationScenarioResult,
                "scenario result",
            )
        if tuple(item.scenario_id for item in scenarios) != tuple(
            sorted(item.scenario_id for item in scenarios)
        ):
            raise ValueError("scenario_results must use increasing scenario-id order")
        if len({item.scenario_id for item in scenarios}) != len(scenarios):
            raise ValueError("scenario result ids must be unique")
        for scenario in scenarios:
            if scenario.true_log_imor != self.reference_log_imor:
                raise ValueError("scenario true log-IMOR changed")
            if scenario.design_diagnostic.replicate_count != self.replicates:
                raise ValueError("nested design replicate count changed")
            design = scenario.design_diagnostic
            expected_insufficient = (
                self.replicates
                if design.sampled_cluster_count < self.minimum_production_clusters
                else 0
            )
            if design.insufficient_cluster_rate.event_count != expected_insufficient:
                raise ValueError("realized insufficient-cluster rate is inconsistent")
            if expected_insufficient:
                if design.production_eligible_rate.event_count != 0:
                    raise ValueError("insufficient designs cannot be production eligible")
            elif (
                design.production_eligible_rate.event_count
                + design.dominant_cluster_rate.event_count
                != self.replicates
            ):
                raise ValueError("realized production eligibility is inconsistent")
            for method in scenario.method_results:
                for metric in method.metric_inference:
                    if tuple(cell.log_imor for cell in metric.grid_inference) != grid:
                        raise ValueError("nested log-IMOR grid changed")
                    for cell in metric.grid_inference:
                        if (
                            cell.replicate_count != self.replicates
                            or cell.maximum_absolute_bias != self.maximum_absolute_bias
                            or cell.coverage_target != self.coverage_target
                            or cell.minimum_interval_yield != self.minimum_interval_yield
                            or cell.standard_error_calibration_lower
                            != self.standard_error_calibration_lower
                            or cell.standard_error_calibration_upper
                            != self.standard_error_calibration_upper
                        ):
                            raise ValueError("nested calibration target changed")
                        if (
                            cell.interval_yield.confidence_level
                            != self.monte_carlo_confidence_level
                            or cell.target_coverage.confidence_level
                            != self.monte_carlo_confidence_level
                        ):
                            raise ValueError("nested Monte Carlo confidence level changed")
            primary_cells = {
                method.target_estimand: next(
                    cell
                    for metric in method.metric_inference
                    if metric.metric is self.primary_metric
                    for cell in metric.grid_inference
                    if cell.log_imor == self.reference_log_imor
                )
                for method in scenario.method_results
            }
            if (
                primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
                ].unit_weighted_true_value
                != scenario.superpopulation_unit_weighted_favorable_prevalence
                or primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED
                ].cluster_balanced_true_value
                != scenario.superpopulation_cluster_balanced_favorable_prevalence
            ):
                raise ValueError("reference truths do not recover profile prevalences")
            if scenario.unit_weighted_reference_direction is not _threshold_direction(
                primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
                ].target_true_value,
                self.direction_threshold,
            ) or scenario.cluster_balanced_reference_direction is not _threshold_direction(
                primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED
                ].target_true_value,
                self.direction_threshold,
            ):
                raise ValueError("scenario truth direction changed")
            for comparison in scenario.conditional_comparisons:
                if (
                    comparison.fixed_profile_target_coverage.confidence_level
                    != self.monte_carlo_confidence_level
                    or comparison.superpopulation_target_coverage.confidence_level
                    != self.monte_carlo_confidence_level
                ):
                    raise ValueError("comparison confidence level changed")
        boundary_fields = (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "cluster_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "empirical_template_sampling_frame",
            "iid_cluster_sampling_assumed",
            "fixed_profile_known_truths_preserved",
            "cluster_superpopulation_resampling_included",
            "automatic_estimand_selection_included",
            "post_hoc_design_filtering_included",
            "dominant_cluster_override_allowed",
            "external_transportability_claimed",
            "identification_and_sampling_uncertainty_separated",
        )
        for field_name in boundary_fields:
            _require_bool(getattr(self, field_name), field_name)
        if (
            not self.aggregate_simulation_only
            or self.replicate_level_records_included
            or self.cluster_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or not self.empirical_template_sampling_frame
            or not self.iid_cluster_sampling_assumed
            or not self.fixed_profile_known_truths_preserved
            or not self.cluster_superpopulation_resampling_included
            or self.automatic_estimand_selection_included
            or self.post_hoc_design_filtering_included
            or self.dominant_cluster_override_allowed
            or self.external_transportability_claimed
            or not self.identification_and_sampling_uncertainty_separated
        ):
            raise ValueError("cluster-superpopulation report crossed its claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


class _DesignAccumulator:
    def __init__(self) -> None:
        self.total_units: list[int] = []
        self.unique_template_counts: list[int] = []
        self.maximum_cluster_fractions: list[float] = []
        self.insufficient_count = 0
        self.dominant_count = 0
        self.eligible_count = 0
        self.unique_largest_count = 0

    def add(
        self,
        *,
        sampled_template_indices: Sequence[int],
        cluster_sizes: Sequence[int],
        minimum_production_clusters: int,
        maximum_production_cluster_unit_fraction: float,
    ) -> None:
        indices = tuple(sampled_template_indices)
        sizes = tuple(cluster_sizes)
        if not indices or len(indices) != len(sizes):
            raise ValueError("sampled template indices and cluster sizes must match")
        total = sum(sizes)
        maximum_fraction = max(sizes) / total
        insufficient = len(sizes) < minimum_production_clusters
        dominant = maximum_fraction > maximum_production_cluster_unit_fraction
        self.total_units.append(total)
        self.unique_template_counts.append(len(set(indices)))
        self.maximum_cluster_fractions.append(maximum_fraction)
        self.insufficient_count += int(insufficient)
        self.dominant_count += int(dominant)
        self.eligible_count += int(not insufficient and not dominant)
        self.unique_largest_count += int(sizes.count(max(sizes)) == 1)

    def finalize(
        self,
        *,
        template_sizes: Sequence[int],
        sampled_cluster_count: int,
        confidence_level: float,
    ) -> ClinicalOutcomeClusterSuperpopulationDesignDiagnostic:
        replicate_count = len(self.total_units)
        if replicate_count == 0:
            raise ValueError("design diagnostics require at least one replicate")
        return ClinicalOutcomeClusterSuperpopulationDesignDiagnostic(
            replicate_count=replicate_count,
            sampled_cluster_count=sampled_cluster_count,
            template_type_count=len(tuple(template_sizes)),
            expected_cluster_size=_round_metric(
                sum(template_sizes) / len(tuple(template_sizes))
            ),
            mean_realized_total_units=_round_metric(
                sum(self.total_units) / replicate_count
            ),
            minimum_realized_total_units=min(self.total_units),
            maximum_realized_total_units=max(self.total_units),
            mean_unique_template_types=_round_metric(
                sum(self.unique_template_counts) / replicate_count
            ),
            mean_maximum_cluster_fraction=_round_metric(
                sum(self.maximum_cluster_fractions) / replicate_count
            ),
            p95_maximum_cluster_fraction=_round_metric(
                _linear_quantile(self.maximum_cluster_fractions, 0.95)
            ),
            insufficient_cluster_rate=_design_rate(
                self.insufficient_count,
                replicate_count,
                confidence_level,
            ),
            dominant_cluster_rate=_design_rate(
                self.dominant_count,
                replicate_count,
                confidence_level,
            ),
            production_eligible_rate=_design_rate(
                self.eligible_count,
                replicate_count,
                confidence_level,
            ),
            unique_largest_cluster_rate=_design_rate(
                self.unique_largest_count,
                replicate_count,
                confidence_level,
            ),
        )


class _DynamicInfluenceAccumulator:
    def __init__(
        self,
        *,
        basis: ClinicalOutcomeClusterInfluenceBasis,
        direction_threshold: float,
    ) -> None:
        self.basis = basis
        self.direction_threshold = direction_threshold
        self.maximum_absolute_values: list[float] = []
        self.maximum_absolute_shares: list[float] = []
        self.unique_largest_count = 0
        self.largest_most_influential_count = 0
        self.direction_flip_count = 0

    def add(
        self,
        *,
        cluster_sizes: Sequence[int],
        influence_values: Sequence[float],
        full_estimate: float,
        leave_one_out_estimates: Sequence[float] | None,
    ) -> None:
        sizes = tuple(cluster_sizes)
        values = tuple(influence_values)
        if not values or len(values) != len(sizes):
            raise ValueError("influence values and cluster sizes must match")
        absolute = tuple(abs(value) for value in values)
        maximum = max(absolute)
        total = sum(absolute)
        self.maximum_absolute_values.append(maximum)
        self.maximum_absolute_shares.append(0.0 if total == 0.0 else maximum / total)
        maximum_size = max(sizes)
        if sizes.count(maximum_size) != 1:
            return
        largest_index = sizes.index(maximum_size)
        self.unique_largest_count += 1
        if absolute[largest_index] >= maximum - 1e-15:
            self.largest_most_influential_count += 1
        if self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT:
            if leave_one_out_estimates is None:
                raise ValueError("leave-one-out influence requires deleted estimates")
            if _threshold_direction(
                full_estimate,
                self.direction_threshold,
            ) is not _threshold_direction(
                leave_one_out_estimates[largest_index],
                self.direction_threshold,
            ):
                self.direction_flip_count += 1

    def finalize(
        self,
        *,
        method: ClinicalOutcomeClusterSizeMethod,
        primary_metric: ClinicalOutcomeDesignMetric,
        reference_log_imor: float,
        confidence_level: float,
    ) -> ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic:
        count = len(self.maximum_absolute_values)
        leave_one_out = (
            self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT
        )
        return ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic(
            method=method,
            basis=self.basis,
            primary_metric=primary_metric,
            reference_log_imor=reference_log_imor,
            analyzable_replicate_count=count,
            mean_maximum_absolute_influence=(
                None
                if count == 0
                else _round_metric(sum(self.maximum_absolute_values) / count)
            ),
            p95_maximum_absolute_influence=(
                None
                if count == 0
                else _round_metric(
                    _linear_quantile(self.maximum_absolute_values, 0.95)
                )
            ),
            mean_maximum_absolute_influence_share=(
                None
                if count == 0
                else _round_metric(sum(self.maximum_absolute_shares) / count)
            ),
            unique_largest_cluster_rate=_design_rate(
                self.unique_largest_count,
                count,
                confidence_level,
            ),
            unique_largest_cluster_most_influential=_design_rate(
                self.largest_most_influential_count,
                self.unique_largest_count,
                confidence_level,
            ),
            largest_cluster_deletion_direction_flip_applicable=leave_one_out,
            largest_cluster_deletion_direction_flip=_design_rate(
                self.direction_flip_count,
                self.unique_largest_count if leave_one_out else 0,
                confidence_level,
            ),
        )


def _scenario_stream_sha256(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
    profile: ClinicalOutcomeClusterSizeProfile,
) -> str:
    return _sha256(
        {
            "random_seed": protocol.random_seed,
            "rng_method_id": stress_protocol.rng_method_id,
            "method_id": protocol.method_id,
            "sampling_model": protocol.sampling_model,
            "cluster_count_rule": protocol.cluster_count_rule,
            "stress_protocol_fingerprint": stress_protocol.fingerprint,
            "fixed_profile_protocol_fingerprint": (
                protocol.fixed_profile_protocol_fingerprint
            ),
            "scenario": scenario,
            "profile": profile,
        }
    )


def _method_cells(
    method_result: ClinicalOutcomeClusterSizeMethodResult,
) -> dict[tuple[ClinicalOutcomeDesignMetric, float], ClinicalOutcomeClusterSizeCell]:
    return {
        (cell.metric, cell.log_imor): cell
        for metric in method_result.metric_inference
        for cell in metric.grid_inference
    }


def _comparison_cells(
    fixed_scenario: ClinicalOutcomeInformativeClusterSizeScenarioResult,
    superpopulation_methods: Sequence[ClinicalOutcomeClusterSizeMethodResult],
) -> tuple[ClinicalOutcomeClusterSuperpopulationComparisonCell, ...]:
    fixed_by_method = {item.method: item for item in fixed_scenario.method_results}
    comparisons: list[ClinicalOutcomeClusterSuperpopulationComparisonCell] = []
    for method_result in superpopulation_methods:
        fixed_cells = _method_cells(fixed_by_method[method_result.method])
        for metric_result in method_result.metric_inference:
            for cell in metric_result.grid_inference:
                fixed_cell = fixed_cells[(cell.metric, cell.log_imor)]
                comparisons.append(
                    ClinicalOutcomeClusterSuperpopulationComparisonCell(
                        method=cell.method,
                        target_estimand=cell.target_estimand,
                        metric=cell.metric,
                        log_imor=cell.log_imor,
                        target_true_value=cell.target_true_value,
                        fixed_profile_target_true_value=(
                            fixed_cell.target_true_value
                        ),
                        truth_difference=_round_metric(
                            cell.target_true_value - fixed_cell.target_true_value
                        ),
                        fixed_profile_target_bias=fixed_cell.target_bias,
                        superpopulation_target_bias=cell.target_bias,
                        target_bias_change=(
                            None
                            if fixed_cell.target_bias is None
                            or cell.target_bias is None
                            else _round_metric(
                                cell.target_bias - fixed_cell.target_bias
                            )
                        ),
                        fixed_profile_target_coverage=fixed_cell.target_coverage,
                        superpopulation_target_coverage=cell.target_coverage,
                        coverage_rate_change=(
                            None
                            if fixed_cell.target_coverage.rate is None
                            or cell.target_coverage.rate is None
                            else _round_metric(
                                cell.target_coverage.rate
                                - fixed_cell.target_coverage.rate
                            )
                        ),
                        fixed_profile_standard_error_to_empirical_sd_ratio=(
                            fixed_cell.standard_error_to_empirical_sd_ratio
                        ),
                        superpopulation_standard_error_to_empirical_sd_ratio=(
                            cell.standard_error_to_empirical_sd_ratio
                        ),
                        standard_error_ratio_change=(
                            None
                            if fixed_cell.standard_error_to_empirical_sd_ratio is None
                            or cell.standard_error_to_empirical_sd_ratio is None
                            else _round_metric(
                                cell.standard_error_to_empirical_sd_ratio
                                - fixed_cell.standard_error_to_empirical_sd_ratio
                            )
                        ),
                        fixed_profile_standard_error_calibration_target_met=(
                            fixed_cell.standard_error_calibration_target_met
                        ),
                        superpopulation_standard_error_calibration_target_met=(
                            cell.standard_error_calibration_target_met
                        ),
                        standard_error_calibration_recovered=(
                            not fixed_cell.standard_error_calibration_target_met
                            and cell.standard_error_calibration_target_met
                        ),
                        fixed_profile_calibration_target_met=(
                            fixed_cell.calibration_target_met
                        ),
                        superpopulation_calibration_target_met=(
                            cell.calibration_target_met
                        ),
                        full_calibration_recovered=(
                            not fixed_cell.calibration_target_met
                            and cell.calibration_target_met
                        ),
                    )
                )
    return tuple(comparisons)


def _validate_truth_preservation(
    fixed_scenario: ClinicalOutcomeInformativeClusterSizeScenarioResult,
    unit_truths: Mapping[float, Sequence[float]],
    cluster_truths: Mapping[float, Sequence[float]],
) -> None:
    for method in fixed_scenario.method_results:
        for metric_index, metric_result in enumerate(method.metric_inference):
            for cell in metric_result.grid_inference:
                if (
                    cell.unit_weighted_true_value
                    != unit_truths[cell.log_imor][metric_index]
                    or cell.cluster_balanced_true_value
                    != cluster_truths[cell.log_imor][metric_index]
                ):
                    raise ClinicalOutcomeClusterSuperpopulationError(
                        f"scenario {fixed_scenario.scenario_id!r} does not preserve "
                        "the fixed-profile known truths"
                    )


def _simulate_scenario(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
    profile: ClinicalOutcomeClusterSizeProfile,
    fixed_scenario: ClinicalOutcomeInformativeClusterSizeScenarioResult,
) -> ClinicalOutcomeClusterSuperpopulationScenarioResult:
    source_layout = _scenario_layout(scenario)
    mode = ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    template_totals = tuple(source_layout.group_stratum_totals_by_mode[mode])
    template_sizes = tuple(sum(row) for row in template_totals)
    cluster_count = len(template_sizes)
    unit_truths, cluster_truths = _profile_truths(
        scenario,
        source_layout,
        profile,
        protocol.log_imor_grid,
    )
    _validate_truth_preservation(fixed_scenario, unit_truths, cluster_truths)
    accumulators = {
        method: {
            metric: {
                log_imor: _CellAccumulator() for log_imor in protocol.log_imor_grid
            }
            for metric in _METRIC_ORDER
        }
        for method in protocol.methods
    }
    influence_accumulators = {
        method: _DynamicInfluenceAccumulator(
            basis=_influence_basis(method),
            direction_threshold=protocol.direction_threshold,
        )
        for method in protocol.methods
    }
    design_accumulator = _DesignAccumulator()
    stream_sha256 = _scenario_stream_sha256(
        protocol,
        stress_protocol,
        scenario,
        profile,
    )
    template_stream_sha256 = _substream_sha256(stream_sha256, "template_sampling")
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(stream_sha256, "evaluability")
    template_rng = random.Random(int(template_stream_sha256, 16))
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    student_critical = (
        None
        if cluster_count < 2
        else _student_t_critical(protocol.confidence_level, cluster_count - 1)
    )
    shift_index = {
        value: index for index, value in enumerate(protocol.log_imor_grid)
    }
    primary_metric_index = _METRIC_ORDER.index(protocol.primary_metric)
    reference_index = shift_index[protocol.reference_log_imor]
    unit_delete_one_method = (
        ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_ONE_STUDENT_T
    )
    unit_delete_mj_method = (
        ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_MJ_STUDENT_T
    )
    cluster_method = (
        ClinicalOutcomeClusterSizeMethod.CLUSTER_BALANCED_DELETE_ONE_STUDENT_T
    )

    for _ in range(protocol.replicates):
        sampled_indices = tuple(
            template_rng.randrange(cluster_count) for _ in range(cluster_count)
        )
        replicate_totals = tuple(template_totals[index] for index in sampled_indices)
        cluster_sizes = tuple(template_sizes[index] for index in sampled_indices)
        design_accumulator.add(
            sampled_template_indices=sampled_indices,
            cluster_sizes=cluster_sizes,
            minimum_production_clusters=protocol.minimum_production_clusters,
            maximum_production_cluster_unit_fraction=(
                protocol.maximum_production_cluster_unit_fraction
            ),
        )
        group_evaluable = [[0] * len(source_layout.prediction_strata) for _ in sampled_indices]
        group_favorable = [[0] * len(source_layout.prediction_strata) for _ in sampled_indices]
        for cluster_index, template_index in enumerate(sampled_indices):
            successes = 0
            previous_count = 0
            prevalence = profile.block_favorable_prevalences[template_index]
            for stratum_index, total in enumerate(replicate_totals[cluster_index]):
                for _ in range(total):
                    label = _draw_beta_binomial_label(
                        outcome_rng,
                        prevalence,
                        scenario.dependence_block_intraclass_correlation,
                        successes,
                        previous_count,
                    )
                    successes += int(label)
                    previous_count += 1
                    evaluable_probability = (
                        scenario.favorable_evaluable_probability
                        if label == 1.0
                        else scenario.unfavorable_evaluable_probability
                    )
                    if evaluability_rng.random() >= evaluable_probability:
                        continue
                    group_evaluable[cluster_index][stratum_index] += 1
                    group_favorable[cluster_index][stratum_index] += int(label)

        if cluster_count < 2:
            for method in protocol.methods:
                _fail_method_cells(
                    accumulators,
                    method,
                    ClinicalOutcomeClusterSizeStatus.INSUFFICIENT_SIMULATION_CLUSTERS,
                )
            continue
        replicate_layout = SimpleNamespace(
            prediction_strata=source_layout.prediction_strata,
            group_stratum_totals_by_mode={mode: replicate_totals},
        )
        block_status, block_estimates = _block_metric_estimates(
            layout=replicate_layout,
            scenario=scenario,
            group_evaluable=group_evaluable,
            group_favorable=group_favorable,
            shifts=protocol.log_imor_grid,
        )
        if block_status is not None:
            for method in protocol.methods:
                _fail_method_cells(accumulators, method, block_status)
            continue

        unit_full, unit_leaveout = _unit_weighted_estimates(
            block_estimates,
            cluster_sizes,
        )
        cluster_full, cluster_leaveout = _cluster_balanced_estimates(block_estimates)
        assert student_critical is not None
        for log_imor in protocol.log_imor_grid:
            log_index = shift_index[log_imor]
            for metric_index, metric in enumerate(_METRIC_ORDER):
                unit_estimate = unit_full[log_index][metric_index]
                unit_leaveout_values = tuple(
                    group[log_index][metric_index] for group in unit_leaveout
                )
                unit_delete_one_se = math.sqrt(
                    _delete_one_variance(unit_leaveout_values)
                )
                (
                    unit_delete_mj_estimate,
                    unit_delete_mj_variance,
                    _,
                    contributions,
                ) = _delete_mj_estimate_and_variance(
                    unit_estimate,
                    unit_leaveout_values,
                    cluster_sizes,
                )
                unit_delete_mj_se = math.sqrt(unit_delete_mj_variance)
                unit_delete_one_accumulator = accumulators[unit_delete_one_method][
                    metric
                ][log_imor]
                unit_delete_mj_accumulator = accumulators[unit_delete_mj_method][
                    metric
                ][log_imor]
                unit_delete_one_accumulator.add_point(unit_estimate)
                unit_delete_mj_accumulator.add_point(unit_delete_mj_estimate)

                cluster_estimate = cluster_full[log_index][metric_index]
                cluster_leaveout_values = tuple(
                    group[log_index][metric_index] for group in cluster_leaveout
                )
                cluster_se = math.sqrt(_delete_one_variance(cluster_leaveout_values))
                cluster_accumulator = accumulators[cluster_method][metric][log_imor]
                cluster_accumulator.add_point(cluster_estimate)

                if metric_index == primary_metric_index and log_index == reference_index:
                    influence_accumulators[unit_delete_one_method].add(
                        cluster_sizes=cluster_sizes,
                        influence_values=tuple(
                            value - unit_estimate for value in unit_leaveout_values
                        ),
                        full_estimate=unit_estimate,
                        leave_one_out_estimates=unit_leaveout_values,
                    )
                    influence_accumulators[unit_delete_mj_method].add(
                        cluster_sizes=cluster_sizes,
                        influence_values=contributions,
                        full_estimate=unit_delete_mj_estimate,
                        leave_one_out_estimates=None,
                    )
                    influence_accumulators[cluster_method].add(
                        cluster_sizes=cluster_sizes,
                        influence_values=tuple(
                            value - cluster_estimate
                            for value in cluster_leaveout_values
                        ),
                        full_estimate=cluster_estimate,
                        leave_one_out_estimates=cluster_leaveout_values,
                    )

                for accumulator, point_estimate, standard_error in (
                    (unit_delete_one_accumulator, unit_estimate, unit_delete_one_se),
                    (
                        unit_delete_mj_accumulator,
                        unit_delete_mj_estimate,
                        unit_delete_mj_se,
                    ),
                ):
                    if _round_metric(standard_error) == 0.0:
                        accumulator.add_failure(
                            ClinicalOutcomeClusterSizeStatus.ZERO_RESAMPLING_VARIANCE
                        )
                    else:
                        _add_interval(
                            accumulator,
                            metric=metric,
                            point_estimate=point_estimate,
                            standard_error=standard_error,
                            critical=student_critical,
                            target_truth=unit_truths[log_imor][metric_index],
                        )
                if _round_metric(cluster_se) == 0.0:
                    cluster_accumulator.add_failure(
                        ClinicalOutcomeClusterSizeStatus.ZERO_RESAMPLING_VARIANCE
                    )
                else:
                    _add_interval(
                        cluster_accumulator,
                        metric=metric,
                        point_estimate=cluster_estimate,
                        standard_error=cluster_se,
                        critical=student_critical,
                        target_truth=cluster_truths[log_imor][metric_index],
                    )

    method_results: list[ClinicalOutcomeClusterSizeMethodResult] = []
    for method in protocol.methods:
        metric_results: list[ClinicalOutcomeClusterSizeMetricResult] = []
        for metric_index, metric in enumerate(_METRIC_ORDER):
            cells = tuple(
                _finalize_cell(
                    protocol=protocol,
                    method=method,
                    metric=metric,
                    log_imor=log_imor,
                    unit_truth=unit_truths[log_imor][metric_index],
                    cluster_truth=cluster_truths[log_imor][metric_index],
                    accumulator=accumulators[method][metric][log_imor],
                    replicate_count=protocol.replicates,
                )
                for log_imor in protocol.log_imor_grid
            )
            metric_results.append(
                ClinicalOutcomeClusterSizeMetricResult(
                    metric=metric,
                    grid_inference=cells,
                    all_grid_calibration_targets_met=all(
                        cell.calibration_target_met for cell in cells
                    ),
                )
            )
        method_results.append(
            ClinicalOutcomeClusterSizeMethodResult(
                method=method,
                target_estimand=_target_estimand(method),
                metric_inference=tuple(metric_results),
                all_metric_calibration_targets_met=all(
                    item.all_grid_calibration_targets_met for item in metric_results
                ),
            )
        )

    total_template_units = sum(template_sizes)
    unit_prevalence = _round_metric(
        sum(
            size * prevalence
            for size, prevalence in zip(
                template_sizes,
                profile.block_favorable_prevalences,
                strict=True,
            )
        )
        / total_template_units
    )
    cluster_prevalence = _round_metric(
        sum(profile.block_favorable_prevalences) / cluster_count
    )
    covariance, correlation = _size_outcome_association(
        template_sizes,
        profile.block_favorable_prevalences,
    )
    unit_reference = unit_truths[protocol.reference_log_imor][primary_metric_index]
    cluster_reference = cluster_truths[protocol.reference_log_imor][primary_metric_index]
    unit_direction = _threshold_direction(unit_reference, protocol.direction_threshold)
    cluster_direction = _threshold_direction(
        cluster_reference,
        protocol.direction_threshold,
    )
    return ClinicalOutcomeClusterSuperpopulationScenarioResult(
        scenario_id=scenario.scenario_id,
        stage=scenario.stage,
        endpoint_family=scenario.endpoint_family,
        true_log_imor=_true_log_imor(scenario),
        fixed_profile_scenario_fingerprint=_sha256(fixed_scenario),
        template_cluster_sizes=template_sizes,
        template_favorable_prevalences=profile.block_favorable_prevalences,
        superpopulation_unit_weighted_favorable_prevalence=unit_prevalence,
        superpopulation_cluster_balanced_favorable_prevalence=cluster_prevalence,
        favorable_prevalence_contrast_unit_minus_cluster=_round_metric(
            unit_prevalence - cluster_prevalence
        ),
        size_outcome_covariance=covariance,
        size_outcome_correlation=correlation,
        unit_weighted_reference_direction=unit_direction,
        cluster_balanced_reference_direction=cluster_direction,
        truth_direction_disagrees=unit_direction is not cluster_direction,
        design_diagnostic=design_accumulator.finalize(
            template_sizes=template_sizes,
            sampled_cluster_count=cluster_count,
            confidence_level=protocol.monte_carlo_confidence_level,
        ),
        method_results=tuple(method_results),
        conditional_comparisons=_comparison_cells(
            fixed_scenario,
            method_results,
        ),
        influence_diagnostics=tuple(
            influence_accumulators[method].finalize(
                method=method,
                primary_metric=protocol.primary_metric,
                reference_log_imor=protocol.reference_log_imor,
                confidence_level=protocol.monte_carlo_confidence_level,
            )
            for method in protocol.methods
        ),
        rng_stream_sha256=stream_sha256,
        template_sampling_rng_stream_sha256=template_stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
    )


def _matching_settings(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    fixed_protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
) -> bool:
    fields = (
        "methods",
        "log_imor_grid",
        "reference_log_imor",
        "confidence_level",
        "monte_carlo_confidence_level",
        "coverage_tolerance",
        "minimum_interval_yield",
        "maximum_absolute_bias",
        "minimum_production_clusters",
        "maximum_production_cluster_unit_fraction",
        "maximum_standard_error_calibration_deviation",
        "primary_metric",
        "direction_threshold",
    )
    return all(getattr(protocol, field_name) == getattr(fixed_protocol, field_name) for field_name in fields)


def _validate_protocol_binding(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    fixed_protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    fixed_report: ClinicalOutcomeInformativeClusterSizeReport,
) -> tuple[
    dict[str, ClinicalOutcomeClusterSizeProfile],
    dict[str, ClinicalOutcomeInformativeClusterSizeScenarioResult],
]:
    if protocol.stress_protocol_fingerprint != stress_protocol.fingerprint:
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation protocol is not bound to the stress protocol"
        )
    if (
        protocol.fixed_profile_protocol_fingerprint != fixed_protocol.fingerprint
        or fixed_protocol.stress_protocol_fingerprint != stress_protocol.fingerprint
    ):
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation protocol is not bound to the fixed-profile protocol"
        )
    if (
        protocol.fixed_profile_report_fingerprint != fixed_report.fingerprint
        or fixed_report.protocol_fingerprint != fixed_protocol.fingerprint
        or fixed_report.stress_protocol_fingerprint != stress_protocol.fingerprint
        or fixed_report.protocol_id != fixed_protocol.protocol_id
        or fixed_report.stress_protocol_id != stress_protocol.protocol_id
    ):
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation protocol is not bound to the fixed-profile report"
        )
    if (
        protocol.replicates != fixed_report.replicates
        or fixed_report.replicates != stress_protocol.replicates
    ):
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation and fixed-profile replicate counts must match"
        )
    if not _matching_settings(protocol, fixed_protocol):
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation calibration settings changed from the fixed-profile protocol"
        )
    profiles = {item.scenario_id: item for item in fixed_protocol.profiles}
    fixed_scenarios = {item.scenario_id: item for item in fixed_report.scenario_results}
    stress_by_id = {
        item.scenario_id: item for item in stress_protocol.scenarios
    }
    stress_ids = tuple(sorted(stress_by_id))
    if tuple(sorted(profiles)) != stress_ids or tuple(sorted(fixed_scenarios)) != stress_ids:
        raise ClinicalOutcomeClusterSuperpopulationError(
            "fixed-profile inputs do not exactly cover stress scenarios"
        )
    fixed_report_fields = (
        (fixed_report.methods, fixed_protocol.methods),
        (fixed_report.log_imor_grid, fixed_protocol.log_imor_grid),
        (fixed_report.reference_log_imor, fixed_protocol.reference_log_imor),
        (fixed_report.confidence_level, fixed_protocol.confidence_level),
        (
            fixed_report.monte_carlo_confidence_level,
            fixed_protocol.monte_carlo_confidence_level,
        ),
        (fixed_report.coverage_target, fixed_protocol.coverage_target),
        (
            fixed_report.minimum_interval_yield,
            fixed_protocol.minimum_interval_yield,
        ),
        (fixed_report.maximum_absolute_bias, fixed_protocol.maximum_absolute_bias),
        (
            fixed_report.minimum_production_clusters,
            fixed_protocol.minimum_production_clusters,
        ),
        (
            fixed_report.maximum_production_cluster_unit_fraction,
            fixed_protocol.maximum_production_cluster_unit_fraction,
        ),
        (
            fixed_report.standard_error_calibration_lower,
            fixed_protocol.standard_error_calibration_lower,
        ),
        (
            fixed_report.standard_error_calibration_upper,
            fixed_protocol.standard_error_calibration_upper,
        ),
        (fixed_report.primary_metric, fixed_protocol.primary_metric),
        (fixed_report.direction_threshold, fixed_protocol.direction_threshold),
    )
    if any(actual != expected for actual, expected in fixed_report_fields):
        raise ClinicalOutcomeClusterSuperpopulationError(
            "fixed-profile report settings changed from its bound protocol"
        )
    for scenario_id in stress_ids:
        scenario = stress_by_id[scenario_id]
        profile = profiles[scenario_id]
        fixed_scenario = fixed_scenarios[scenario_id]
        template_count = len(
            _scenario_layout(scenario).group_stratum_totals_by_mode[
                ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
            ]
        )
        if (
            len(profile.block_favorable_prevalences) != template_count
            or fixed_scenario.block_favorable_prevalences
            != profile.block_favorable_prevalences
            or fixed_scenario.stage is not scenario.stage
            or fixed_scenario.endpoint_family != scenario.endpoint_family
            or fixed_scenario.true_log_imor != _true_log_imor(scenario)
        ):
            raise ClinicalOutcomeClusterSuperpopulationError(
                f"fixed-profile scenario {scenario_id!r} changed from its source inputs"
            )
    return profiles, fixed_scenarios


def _work_units(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> int:
    grid_metrics = len(protocol.log_imor_grid) * len(_METRIC_ORDER)
    total = 0
    for scenario in stress_protocol.scenarios:
        layout = _scenario_layout(scenario)
        template_totals = layout.group_stratum_totals_by_mode[
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
        ]
        sizes = tuple(sum(row) for row in template_totals)
        total += max(sizes) * len(sizes) + len(sizes) * grid_metrics * 6
    return protocol.replicates * total


def analyze_clinical_outcome_cluster_superpopulation(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    fixed_profile_protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    fixed_profile_report: ClinicalOutcomeInformativeClusterSizeReport,
) -> ClinicalOutcomeClusterSuperpopulationReport:
    """Compare conditional and empirical-template cluster-superpopulation inference."""

    _require_instance(
        protocol,
        ClinicalOutcomeClusterSuperpopulationProtocol,
        "protocol",
    )
    _require_instance(
        stress_protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "stress_protocol",
    )
    _require_instance(
        fixed_profile_protocol,
        ClinicalOutcomeInformativeClusterSizeProtocol,
        "fixed_profile_protocol",
    )
    _require_instance(
        fixed_profile_report,
        ClinicalOutcomeInformativeClusterSizeReport,
        "fixed_profile_report",
    )
    profiles, fixed_scenarios = _validate_protocol_binding(
        protocol,
        stress_protocol,
        fixed_profile_protocol,
        fixed_profile_report,
    )
    if _work_units(protocol, stress_protocol) > MAX_DESIGN_WORK_UNITS:
        raise ClinicalOutcomeClusterSuperpopulationError(
            "cluster-superpopulation study exceeds the bounded work budget"
        )
    scenario_results = tuple(
        _simulate_scenario(
            protocol,
            stress_protocol,
            scenario,
            profiles[scenario.scenario_id],
            fixed_scenarios[scenario.scenario_id],
        )
        for scenario in sorted(
            stress_protocol.scenarios,
            key=lambda item: item.scenario_id,
        )
    )
    return ClinicalOutcomeClusterSuperpopulationReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        stress_protocol_id=stress_protocol.protocol_id,
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        fixed_profile_protocol_id=fixed_profile_protocol.protocol_id,
        fixed_profile_protocol_fingerprint=fixed_profile_protocol.fingerprint,
        fixed_profile_report_fingerprint=fixed_profile_report.fingerprint,
        method_id=protocol.method_id,
        rng_method_id=stress_protocol.rng_method_id,
        sampling_model=protocol.sampling_model,
        cluster_count_rule=protocol.cluster_count_rule,
        replicates=protocol.replicates,
        random_seed=protocol.random_seed,
        methods=protocol.methods,
        log_imor_grid=protocol.log_imor_grid,
        reference_log_imor=protocol.reference_log_imor,
        confidence_level=protocol.confidence_level,
        monte_carlo_confidence_level=protocol.monte_carlo_confidence_level,
        coverage_target=protocol.coverage_target,
        minimum_interval_yield=protocol.minimum_interval_yield,
        maximum_absolute_bias=protocol.maximum_absolute_bias,
        minimum_production_clusters=protocol.minimum_production_clusters,
        maximum_production_cluster_unit_fraction=(
            protocol.maximum_production_cluster_unit_fraction
        ),
        standard_error_calibration_lower=protocol.standard_error_calibration_lower,
        standard_error_calibration_upper=protocol.standard_error_calibration_upper,
        primary_metric=protocol.primary_metric,
        direction_threshold=protocol.direction_threshold,
        scenario_results=scenario_results,
    )


def validate_clinical_outcome_cluster_superpopulation_report(
    report: ClinicalOutcomeClusterSuperpopulationReport,
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    fixed_profile_protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    fixed_profile_report: ClinicalOutcomeInformativeClusterSizeReport,
) -> tuple[str, ...]:
    """Replay both the bound conditional reference and superpopulation study."""

    fixed_failures = validate_clinical_outcome_informative_cluster_size_report(
        fixed_profile_report,
        fixed_profile_protocol,
        stress_protocol,
    )
    if fixed_failures:
        return ("fixed_profile_reference_replay_failed",)
    try:
        rebuilt = analyze_clinical_outcome_cluster_superpopulation(
            protocol,
            stress_protocol,
            fixed_profile_protocol,
            fixed_profile_report,
        )
    except (ClinicalOutcomeClusterSuperpopulationError, TypeError, ValueError):
        return ("cluster_superpopulation_replay_failed",)
    return () if rebuilt == report else ("cluster_superpopulation_report_mismatch",)


def clinical_outcome_cluster_superpopulation_summary(
    report: ClinicalOutcomeClusterSuperpopulationReport,
) -> dict[str, Any]:
    """Return a compact conditional-versus-superpopulation comparison."""

    _require_instance(
        report,
        ClinicalOutcomeClusterSuperpopulationReport,
        "report",
    )
    all_comparisons = tuple(
        comparison
        for scenario in report.scenario_results
        for comparison in scenario.conditional_comparisons
    )
    scenarios: list[dict[str, Any]] = []
    for scenario in report.scenario_results:
        methods: list[dict[str, Any]] = []
        for method_result in scenario.method_results:
            comparison = next(
                item
                for item in scenario.conditional_comparisons
                if item.method is method_result.method
                and item.metric is report.primary_metric
                and item.log_imor == report.reference_log_imor
            )
            diagnostic = next(
                item
                for item in scenario.influence_diagnostics
                if item.method is method_result.method
            )
            methods.append(
                {
                    "method": method_result.method.value,
                    "target_estimand": method_result.target_estimand.value,
                    "reference_target_truth": comparison.target_true_value,
                    "reference_truth_difference_from_fixed_profile": (
                        comparison.truth_difference
                    ),
                    "fixed_profile_target_bias": (
                        comparison.fixed_profile_target_bias
                    ),
                    "superpopulation_target_bias": (
                        comparison.superpopulation_target_bias
                    ),
                    "fixed_profile_target_coverage": _rate_projection(
                        comparison.fixed_profile_target_coverage
                    ),
                    "superpopulation_target_coverage": _rate_projection(
                        comparison.superpopulation_target_coverage
                    ),
                    "coverage_rate_change": comparison.coverage_rate_change,
                    "fixed_profile_standard_error_to_empirical_sd_ratio": (
                        comparison.fixed_profile_standard_error_to_empirical_sd_ratio
                    ),
                    "superpopulation_standard_error_to_empirical_sd_ratio": (
                        comparison.superpopulation_standard_error_to_empirical_sd_ratio
                    ),
                    "standard_error_ratio_change": (
                        comparison.standard_error_ratio_change
                    ),
                    "standard_error_calibration_recovered": (
                        comparison.standard_error_calibration_recovered
                    ),
                    "reference_superpopulation_calibration_target_met": (
                        comparison.superpopulation_calibration_target_met
                    ),
                    "all_superpopulation_metric_calibration_targets_met": (
                        method_result.all_metric_calibration_targets_met
                    ),
                    "influence_basis": diagnostic.basis.value,
                    "mean_maximum_absolute_influence": (
                        diagnostic.mean_maximum_absolute_influence
                    ),
                    "p95_maximum_absolute_influence": (
                        diagnostic.p95_maximum_absolute_influence
                    ),
                    "mean_maximum_absolute_influence_share": (
                        diagnostic.mean_maximum_absolute_influence_share
                    ),
                    "unique_largest_cluster_rate": _rate_projection(
                        diagnostic.unique_largest_cluster_rate
                    ),
                    "unique_largest_cluster_most_influential": _rate_projection(
                        diagnostic.unique_largest_cluster_most_influential
                    ),
                    "largest_cluster_deletion_direction_flip": _rate_projection(
                        diagnostic.largest_cluster_deletion_direction_flip
                    ),
                }
            )
        design = scenario.design_diagnostic
        scenarios.append(
            {
                "scenario_id": scenario.scenario_id,
                "template_cluster_count": len(scenario.template_cluster_sizes),
                "minimum_template_cluster_size": min(
                    scenario.template_cluster_sizes
                ),
                "maximum_template_cluster_size": max(
                    scenario.template_cluster_sizes
                ),
                "superpopulation_unit_weighted_favorable_prevalence": (
                    scenario.superpopulation_unit_weighted_favorable_prevalence
                ),
                "superpopulation_cluster_balanced_favorable_prevalence": (
                    scenario.superpopulation_cluster_balanced_favorable_prevalence
                ),
                "favorable_prevalence_contrast_unit_minus_cluster": (
                    scenario.favorable_prevalence_contrast_unit_minus_cluster
                ),
                "size_outcome_covariance": scenario.size_outcome_covariance,
                "size_outcome_correlation": scenario.size_outcome_correlation,
                "unit_weighted_reference_direction": (
                    scenario.unit_weighted_reference_direction.value
                ),
                "cluster_balanced_reference_direction": (
                    scenario.cluster_balanced_reference_direction.value
                ),
                "truth_direction_disagrees": scenario.truth_direction_disagrees,
                "mean_realized_total_units": design.mean_realized_total_units,
                "mean_unique_template_types": design.mean_unique_template_types,
                "mean_maximum_cluster_fraction": (
                    design.mean_maximum_cluster_fraction
                ),
                "p95_maximum_cluster_fraction": (
                    design.p95_maximum_cluster_fraction
                ),
                "dominant_cluster_rate": _rate_projection(
                    design.dominant_cluster_rate
                ),
                "production_eligible_rate": _rate_projection(
                    design.production_eligible_rate
                ),
                "methods": methods,
            }
        )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_SUMMARY_SCHEMA_VERSION
        ),
        "report_fingerprint": report.fingerprint,
        "protocol_fingerprint": report.protocol_fingerprint,
        "fixed_profile_protocol_fingerprint": (
            report.fixed_profile_protocol_fingerprint
        ),
        "fixed_profile_report_fingerprint": report.fixed_profile_report_fingerprint,
        "sampling_model": report.sampling_model.value,
        "cluster_count_rule": report.cluster_count_rule.value,
        "replicates": report.replicates,
        "primary_metric": report.primary_metric.value,
        "reference_log_imor": report.reference_log_imor,
        "direction_threshold": report.direction_threshold,
        "comparison_cell_count": len(all_comparisons),
        "fixed_profile_standard_error_calibration_pass_count": sum(
            item.fixed_profile_standard_error_calibration_target_met
            for item in all_comparisons
        ),
        "superpopulation_standard_error_calibration_pass_count": sum(
            item.superpopulation_standard_error_calibration_target_met
            for item in all_comparisons
        ),
        "standard_error_calibration_recovered_cell_count": sum(
            item.standard_error_calibration_recovered for item in all_comparisons
        ),
        "fixed_profile_full_calibration_pass_count": sum(
            item.fixed_profile_calibration_target_met for item in all_comparisons
        ),
        "superpopulation_full_calibration_pass_count": sum(
            item.superpopulation_calibration_target_met for item in all_comparisons
        ),
        "full_calibration_recovered_cell_count": sum(
            item.full_calibration_recovered for item in all_comparisons
        ),
        "fixed_profile_known_truths_preserved": (
            report.fixed_profile_known_truths_preserved
        ),
        "post_hoc_design_filtering_included": (
            report.post_hoc_design_filtering_included
        ),
        "external_transportability_claimed": (
            report.external_transportability_claimed
        ),
        "scenarios": scenarios,
    }


def clinical_outcome_cluster_superpopulation_validation_summary(
    report: ClinicalOutcomeClusterSuperpopulationReport,
    *,
    failures: Sequence[str] = (),
    scope: str = "integrity_and_aggregate_consistency",
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomeClusterSuperpopulationReport,
        "report",
    )
    _require_text(scope, "scope")
    resolved_failures = _tuple(failures, "failures")
    for failure in resolved_failures:
        _require_text(failure, "failure")
    if len(resolved_failures) != len(set(resolved_failures)):
        raise ValueError("failure codes must be unique")
    return {
        "schema_version": (
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_SUMMARY_SCHEMA_VERSION
        ),
        "valid": not resolved_failures,
        "scope": scope,
        "report_fingerprint": report.fingerprint,
        "protocol_fingerprint": report.protocol_fingerprint,
        "stress_protocol_fingerprint": report.stress_protocol_fingerprint,
        "fixed_profile_protocol_fingerprint": (
            report.fixed_profile_protocol_fingerprint
        ),
        "fixed_profile_report_fingerprint": report.fixed_profile_report_fingerprint,
        "failures": list(resolved_failures),
    }


def clinical_outcome_cluster_superpopulation_protocol_envelope(
    protocol: ClinicalOutcomeClusterSuperpopulationProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomeClusterSuperpopulationProtocol,
        "protocol",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_PROTOCOL_SCHEMA_VERSION
        ),
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_cluster_superpopulation_report_envelope(
    report: ClinicalOutcomeClusterSuperpopulationReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomeClusterSuperpopulationReport,
        "report",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _clinical_outcome_cluster_superpopulation_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeClusterSuperpopulationProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_cluster_superpopulation_protocol_envelope",
        schema_version=(
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_PROTOCOL_SCHEMA_VERSION
        ),
        payload_field="protocol",
    )
    fields = {
        "protocol_id",
        "version",
        "registered_on",
        "stress_protocol_fingerprint",
        "fixed_profile_protocol_fingerprint",
        "fixed_profile_report_fingerprint",
        "sampling_model",
        "cluster_count_rule",
        "replicates",
        "random_seed",
        "methods",
        "log_imor_grid",
        "reference_log_imor",
        "confidence_level",
        "monte_carlo_confidence_level",
        "coverage_tolerance",
        "minimum_interval_yield",
        "maximum_absolute_bias",
        "minimum_production_clusters",
        "maximum_production_cluster_unit_fraction",
        "maximum_standard_error_calibration_deviation",
        "primary_metric",
        "direction_threshold",
        "method_id",
        "metadata",
    }
    data = _record(payload, "protocol", fields)
    excluded = {
        "registered_on",
        "sampling_model",
        "cluster_count_rule",
        "methods",
        "log_imor_grid",
        "primary_metric",
        "metadata",
    }
    protocol = ClinicalOutcomeClusterSuperpopulationProtocol(
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        sampling_model=_parse_enum(
            ClinicalOutcomeClusterSuperpopulationSamplingModel,
            data["sampling_model"],
            "protocol.sampling_model",
        ),
        cluster_count_rule=_parse_enum(
            ClinicalOutcomeClusterCountRule,
            data["cluster_count_rule"],
            "protocol.cluster_count_rule",
        ),
        methods=tuple(
            _parse_enum(
                ClinicalOutcomeClusterSizeMethod,
                item,
                f"protocol.methods[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["methods"], "protocol.methods")
            )
        ),
        log_imor_grid=tuple(
            _sequence(data["log_imor_grid"], "protocol.log_imor_grid")
        ),
        primary_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["primary_metric"],
            "protocol.primary_metric",
        ),
        metadata=_mapping(data["metadata"], "protocol.metadata"),
        **{key: data[key] for key in fields if key not in excluded},
    )
    _check_integrity(protocol, integrity, "cluster-superpopulation protocol")
    return protocol


def clinical_outcome_cluster_superpopulation_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeClusterSuperpopulationProtocol:
    try:
        return _clinical_outcome_cluster_superpopulation_protocol_from_dict(value)
    except RecordParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordParseError(
            "cluster-superpopulation protocol violates its semantic contract"
        ) from exc


def _parse_design_diagnostic(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSuperpopulationDesignDiagnostic:
    fields = {
        "replicate_count",
        "sampled_cluster_count",
        "template_type_count",
        "expected_cluster_size",
        "mean_realized_total_units",
        "minimum_realized_total_units",
        "maximum_realized_total_units",
        "mean_unique_template_types",
        "mean_maximum_cluster_fraction",
        "p95_maximum_cluster_fraction",
        "insufficient_cluster_rate",
        "dominant_cluster_rate",
        "production_eligible_rate",
        "unique_largest_cluster_rate",
    }
    data = _record(value, path, fields)
    rate_fields = {
        "insufficient_cluster_rate",
        "dominant_cluster_rate",
        "production_eligible_rate",
        "unique_largest_cluster_rate",
    }
    return ClinicalOutcomeClusterSuperpopulationDesignDiagnostic(
        **{key: data[key] for key in fields if key not in rate_fields},
        **{
            key: _parse_design_rate(data[key], f"{path}.{key}")
            for key in rate_fields
        },
    )


def _parse_influence_diagnostic(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic:
    fields = {
        "method",
        "basis",
        "primary_metric",
        "reference_log_imor",
        "analyzable_replicate_count",
        "mean_maximum_absolute_influence",
        "p95_maximum_absolute_influence",
        "mean_maximum_absolute_influence_share",
        "unique_largest_cluster_rate",
        "unique_largest_cluster_most_influential",
        "largest_cluster_deletion_direction_flip_applicable",
        "largest_cluster_deletion_direction_flip",
    }
    data = _record(value, path, fields)
    excluded = {
        "method",
        "basis",
        "primary_metric",
        "unique_largest_cluster_rate",
        "unique_largest_cluster_most_influential",
        "largest_cluster_deletion_direction_flip",
    }
    return ClinicalOutcomeClusterSuperpopulationInfluenceDiagnostic(
        method=_parse_enum(
            ClinicalOutcomeClusterSizeMethod,
            data["method"],
            f"{path}.method",
        ),
        basis=_parse_enum(
            ClinicalOutcomeClusterInfluenceBasis,
            data["basis"],
            f"{path}.basis",
        ),
        primary_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["primary_metric"],
            f"{path}.primary_metric",
        ),
        unique_largest_cluster_rate=_parse_design_rate(
            data["unique_largest_cluster_rate"],
            f"{path}.unique_largest_cluster_rate",
        ),
        unique_largest_cluster_most_influential=_parse_design_rate(
            data["unique_largest_cluster_most_influential"],
            f"{path}.unique_largest_cluster_most_influential",
        ),
        largest_cluster_deletion_direction_flip=_parse_design_rate(
            data["largest_cluster_deletion_direction_flip"],
            f"{path}.largest_cluster_deletion_direction_flip",
        ),
        **{key: data[key] for key in fields if key not in excluded},
    )


def _parse_comparison_cell(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSuperpopulationComparisonCell:
    fields = {
        "method",
        "target_estimand",
        "metric",
        "log_imor",
        "target_true_value",
        "fixed_profile_target_true_value",
        "truth_difference",
        "fixed_profile_target_bias",
        "superpopulation_target_bias",
        "target_bias_change",
        "fixed_profile_target_coverage",
        "superpopulation_target_coverage",
        "coverage_rate_change",
        "fixed_profile_standard_error_to_empirical_sd_ratio",
        "superpopulation_standard_error_to_empirical_sd_ratio",
        "standard_error_ratio_change",
        "fixed_profile_standard_error_calibration_target_met",
        "superpopulation_standard_error_calibration_target_met",
        "standard_error_calibration_recovered",
        "fixed_profile_calibration_target_met",
        "superpopulation_calibration_target_met",
        "full_calibration_recovered",
    }
    data = _record(value, path, fields)
    excluded = {
        "method",
        "target_estimand",
        "metric",
        "fixed_profile_target_coverage",
        "superpopulation_target_coverage",
    }
    return ClinicalOutcomeClusterSuperpopulationComparisonCell(
        method=_parse_enum(
            ClinicalOutcomeClusterSizeMethod,
            data["method"],
            f"{path}.method",
        ),
        target_estimand=_parse_enum(
            ClinicalOutcomeClusterSizeEstimand,
            data["target_estimand"],
            f"{path}.target_estimand",
        ),
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        fixed_profile_target_coverage=_parse_design_rate(
            data["fixed_profile_target_coverage"],
            f"{path}.fixed_profile_target_coverage",
        ),
        superpopulation_target_coverage=_parse_design_rate(
            data["superpopulation_target_coverage"],
            f"{path}.superpopulation_target_coverage",
        ),
        **{key: data[key] for key in fields if key not in excluded},
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSuperpopulationScenarioResult:
    fields = {
        "scenario_id",
        "stage",
        "endpoint_family",
        "true_log_imor",
        "fixed_profile_scenario_fingerprint",
        "template_cluster_sizes",
        "template_favorable_prevalences",
        "superpopulation_unit_weighted_favorable_prevalence",
        "superpopulation_cluster_balanced_favorable_prevalence",
        "favorable_prevalence_contrast_unit_minus_cluster",
        "size_outcome_covariance",
        "size_outcome_correlation",
        "unit_weighted_reference_direction",
        "cluster_balanced_reference_direction",
        "truth_direction_disagrees",
        "design_diagnostic",
        "method_results",
        "conditional_comparisons",
        "influence_diagnostics",
        "rng_stream_sha256",
        "template_sampling_rng_stream_sha256",
        "outcome_rng_stream_sha256",
        "evaluability_rng_stream_sha256",
    }
    data = _record(value, path, fields)
    excluded = {
        "stage",
        "template_cluster_sizes",
        "template_favorable_prevalences",
        "unit_weighted_reference_direction",
        "cluster_balanced_reference_direction",
        "design_diagnostic",
        "method_results",
        "conditional_comparisons",
        "influence_diagnostics",
    }
    return ClinicalOutcomeClusterSuperpopulationScenarioResult(
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        template_cluster_sizes=tuple(
            _sequence(data["template_cluster_sizes"], f"{path}.template_cluster_sizes")
        ),
        template_favorable_prevalences=tuple(
            _sequence(
                data["template_favorable_prevalences"],
                f"{path}.template_favorable_prevalences",
            )
        ),
        unit_weighted_reference_direction=_parse_enum(
            ClinicalOutcomeThresholdDirection,
            data["unit_weighted_reference_direction"],
            f"{path}.unit_weighted_reference_direction",
        ),
        cluster_balanced_reference_direction=_parse_enum(
            ClinicalOutcomeThresholdDirection,
            data["cluster_balanced_reference_direction"],
            f"{path}.cluster_balanced_reference_direction",
        ),
        design_diagnostic=_parse_design_diagnostic(
            data["design_diagnostic"],
            f"{path}.design_diagnostic",
        ),
        method_results=tuple(
            _parse_method_result(item, f"{path}.method_results[{index}]")
            for index, item in enumerate(
                _sequence(data["method_results"], f"{path}.method_results")
            )
        ),
        conditional_comparisons=tuple(
            _parse_comparison_cell(
                item,
                f"{path}.conditional_comparisons[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["conditional_comparisons"],
                    f"{path}.conditional_comparisons",
                )
            )
        ),
        influence_diagnostics=tuple(
            _parse_influence_diagnostic(
                item,
                f"{path}.influence_diagnostics[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["influence_diagnostics"],
                    f"{path}.influence_diagnostics",
                )
            )
        ),
        **{key: data[key] for key in fields if key not in excluded},
    )


def _clinical_outcome_cluster_superpopulation_report_from_dict(
    value: Any,
) -> ClinicalOutcomeClusterSuperpopulationReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_cluster_superpopulation_report_envelope",
        schema_version=(
            CLINICAL_OUTCOME_CLUSTER_SUPERPOPULATION_REPORT_SCHEMA_VERSION
        ),
        payload_field="report",
    )
    fields = {
        "protocol_id",
        "protocol_fingerprint",
        "stress_protocol_id",
        "stress_protocol_fingerprint",
        "fixed_profile_protocol_id",
        "fixed_profile_protocol_fingerprint",
        "fixed_profile_report_fingerprint",
        "method_id",
        "rng_method_id",
        "sampling_model",
        "cluster_count_rule",
        "replicates",
        "random_seed",
        "methods",
        "log_imor_grid",
        "reference_log_imor",
        "confidence_level",
        "monte_carlo_confidence_level",
        "coverage_target",
        "minimum_interval_yield",
        "maximum_absolute_bias",
        "minimum_production_clusters",
        "maximum_production_cluster_unit_fraction",
        "standard_error_calibration_lower",
        "standard_error_calibration_upper",
        "primary_metric",
        "direction_threshold",
        "scenario_results",
        "aggregate_simulation_only",
        "replicate_level_records_included",
        "cluster_level_records_included",
        "unit_level_records_included",
        "real_clinical_outcomes_included",
        "empirical_template_sampling_frame",
        "iid_cluster_sampling_assumed",
        "fixed_profile_known_truths_preserved",
        "cluster_superpopulation_resampling_included",
        "automatic_estimand_selection_included",
        "post_hoc_design_filtering_included",
        "dominant_cluster_override_allowed",
        "external_transportability_claimed",
        "identification_and_sampling_uncertainty_separated",
        "limitations",
    }
    data = _record(payload, "report", fields)
    excluded = {
        "sampling_model",
        "cluster_count_rule",
        "methods",
        "log_imor_grid",
        "primary_metric",
        "scenario_results",
        "limitations",
    }
    report = ClinicalOutcomeClusterSuperpopulationReport(
        sampling_model=_parse_enum(
            ClinicalOutcomeClusterSuperpopulationSamplingModel,
            data["sampling_model"],
            "report.sampling_model",
        ),
        cluster_count_rule=_parse_enum(
            ClinicalOutcomeClusterCountRule,
            data["cluster_count_rule"],
            "report.cluster_count_rule",
        ),
        methods=tuple(
            _parse_enum(
                ClinicalOutcomeClusterSizeMethod,
                item,
                f"report.methods[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["methods"], "report.methods")
            )
        ),
        log_imor_grid=tuple(
            _sequence(data["log_imor_grid"], "report.log_imor_grid")
        ),
        primary_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["primary_metric"],
            "report.primary_metric",
        ),
        scenario_results=tuple(
            _parse_scenario_result(item, f"report.scenario_results[{index}]")
            for index, item in enumerate(
                _sequence(data["scenario_results"], "report.scenario_results")
            )
        ),
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
        **{key: data[key] for key in fields if key not in excluded},
    )
    _check_integrity(report, integrity, "cluster-superpopulation report")
    return report


def clinical_outcome_cluster_superpopulation_report_from_dict(
    value: Any,
) -> ClinicalOutcomeClusterSuperpopulationReport:
    try:
        return _clinical_outcome_cluster_superpopulation_report_from_dict(value)
    except RecordParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordParseError(
            "cluster-superpopulation report violates its semantic contract"
        ) from exc


def clinical_outcome_cluster_superpopulation_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeClusterSuperpopulationProtocol:
    return clinical_outcome_cluster_superpopulation_protocol_from_dict(
        _strict_json(payload, "cluster-superpopulation protocol")
    )


def clinical_outcome_cluster_superpopulation_report_from_json(
    payload: str,
) -> ClinicalOutcomeClusterSuperpopulationReport:
    return clinical_outcome_cluster_superpopulation_report_from_dict(
        _strict_json(payload, "cluster-superpopulation report")
    )
