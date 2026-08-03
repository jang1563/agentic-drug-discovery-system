"""Informative-cluster-size estimand and influence calibration."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from .clinical_outcome_design_simulation import (
    MAX_DESIGN_WORK_UNITS,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomeDesignRate,
    ClinicalOutcomeDesignStructure,
    _design_rate,
    _draw_beta_binomial_label,
    _METRIC_ORDER,
    _metric_bounds,
    _parse_design_rate,
    _parse_design_structure,
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
from .clinical_outcome_pattern_mixture import (
    MAX_ABSOLUTE_LOG_IMOR,
    _expected_metric_value,
    _odds_shift_probability,
    _true_log_imor,
)
from .clinical_outcome_pattern_mixture_influence_calibration import (
    _delete_mj_estimate_and_variance,
    _delete_one_variance,
    _linear_quantile,
    _student_t_critical,
)
from .clinical_outcome_pattern_mixture_uncertainty import (
    _mc_mean_bounds,
    _mc_nonnegative_mean_bounds,
    _scenario_layout,
    _support_status,
)
from .clinical_outcome_stress_simulation import (
    CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    _scenario_stream_sha256,
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


CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-informative-cluster-size-protocol.v1"
)
CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-informative-cluster-size-report.v1"
)
CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-informative-cluster-size-summary.v1"
)
CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_METHOD_ID = (
    "adds.pattern-mixture.informative-cluster-size-estimands.v1"
)


class ClinicalOutcomeInformativeClusterSizeError(ValueError):
    """Raised when an informative-cluster-size study cannot run safely."""


class ClinicalOutcomeClusterSizeEstimand(str, Enum):
    UNIT_WEIGHTED = "unit_weighted"
    CLUSTER_BALANCED = "cluster_balanced"


class ClinicalOutcomeClusterSizeMethod(str, Enum):
    UNIT_WEIGHTED_DELETE_ONE_STUDENT_T = "unit_weighted_delete_one_student_t"
    UNIT_WEIGHTED_DELETE_MJ_STUDENT_T = "unit_weighted_delete_mj_student_t"
    CLUSTER_BALANCED_DELETE_ONE_STUDENT_T = (
        "cluster_balanced_delete_one_student_t"
    )


class ClinicalOutcomeClusterSizeStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_SIMULATION_CLUSTERS = "insufficient_simulation_clusters"
    CLUSTER_EMPTY_REFERENCE_STRATUM = "cluster_empty_reference_stratum"
    CLUSTER_DEGENERATE_REFERENCE_STRATUM = "cluster_degenerate_reference_stratum"
    ZERO_RESAMPLING_VARIANCE = "zero_resampling_variance"


class ClinicalOutcomeClusterInfluenceBasis(str, Enum):
    LEAVE_ONE_OUT_SHIFT = "leave_one_out_shift"
    PSEUDOVALUE_CONTRIBUTION = "pseudovalue_contribution"


class ClinicalOutcomeThresholdDirection(str, Enum):
    BELOW = "below"
    AT = "at"
    ABOVE = "above"


_METHOD_ORDER = tuple(ClinicalOutcomeClusterSizeMethod)
_STATUS_ORDER = tuple(ClinicalOutcomeClusterSizeStatus)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic informative-cluster-size study and contains no real "
        "clinical outcomes, dependence manifest, or deployed policy result."
    ),
    (
        "Unit-weighted and cluster-balanced functionals answer different questions when "
        "cluster size is associated with the outcome distribution; neither is universally "
        "preferred without a prospectively declared scientific estimand."
    ),
    (
        "Delete-mj adjusts the unequal-group jackknife calculation for the unit-weighted "
        "estimator; it does not convert that estimator into a cluster-balanced functional."
    ),
    (
        "Every interval remains conditional on one fixed binary log-IMOR model functional; "
        "sampling and missing-data identification uncertainty are not combined."
    ),
    (
        "All estimators require support within every analysis cluster because the shared "
        "pattern-mixture functional is evaluated block by block; sparse blocks can lower "
        "interval yield."
    ),
    (
        "Influence diagnostics use method-specific leave-one-out shifts or pseudovalue "
        "contributions and retain only aggregate maxima, shares, and event rates; their absolute "
        "scales are not interchangeable and no replicate-, cluster-, or unit-level records are "
        "exposed."
    ),
    (
        "A dominant-cluster stress result is diagnostic only and cannot override the "
        "preregistered production eligibility hard stop."
    ),
    (
        "The simulation assumes independent top-level dependence blocks, correctly declared "
        "block membership, and a synthetic block-specific prevalence profile."
    ),
    (
        "Block-specific prevalence profiles remain fixed across replicates, so standard-error "
        "calibration targets repeated outcomes conditional on those blocks rather than a "
        "superpopulation that resamples new clusters."
    ),
    (
        "Monte Carlo bounds quantify finite simulation error for rates, bias, and mean interval "
        "width; the SE-to-empirical-SD ratio is a point diagnostic, and neither validates one "
        "future clinical board, endpoint family, safety definition, or elicited log-IMOR range."
    ),
    (
        "Passing synthetic targets does not establish efficacy, safety, benefit-risk, policy "
        "superiority, transportability, treatment utility, or regulatory acceptability."
    ),
)


def _target_estimand(
    method: ClinicalOutcomeClusterSizeMethod,
) -> ClinicalOutcomeClusterSizeEstimand:
    if method is ClinicalOutcomeClusterSizeMethod.CLUSTER_BALANCED_DELETE_ONE_STUDENT_T:
        return ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED
    return ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED


def _influence_basis(
    method: ClinicalOutcomeClusterSizeMethod,
) -> ClinicalOutcomeClusterInfluenceBasis:
    if method is ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_MJ_STUDENT_T:
        return ClinicalOutcomeClusterInfluenceBasis.PSEUDOVALUE_CONTRIBUTION
    return ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT


def _threshold_direction(
    value: float,
    threshold: float,
) -> ClinicalOutcomeThresholdDirection:
    if abs(value - threshold) <= 1e-12:
        return ClinicalOutcomeThresholdDirection.AT
    if value < threshold:
        return ClinicalOutcomeThresholdDirection.BELOW
    return ClinicalOutcomeThresholdDirection.ABOVE


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSizeProfile(SerializableRecord):
    scenario_id: str
    block_favorable_prevalences: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        values = _tuple(
            self.block_favorable_prevalences,
            "block_favorable_prevalences",
        )
        object.__setattr__(self, "block_favorable_prevalences", values)
        if not values:
            raise ValueError("cluster-size profile requires at least one block")
        for index, value in enumerate(values):
            _require_probability(value, f"block_favorable_prevalences[{index}]")
            if value in (0.0, 1.0):
                raise ValueError("block favorable prevalences must be strictly interior")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeInformativeClusterSizeProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    stress_protocol_fingerprint: str
    profiles: tuple[ClinicalOutcomeClusterSizeProfile, ...]
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
    method_id: str = CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_METHOD_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        _require_sha256(
            self.stress_protocol_fingerprint,
            "stress_protocol_fingerprint",
        )
        profiles = _tuple(self.profiles, "profiles")
        object.__setattr__(self, "profiles", profiles)
        if not profiles:
            raise ValueError("profiles cannot be empty")
        for profile in profiles:
            _require_instance(profile, ClinicalOutcomeClusterSizeProfile, "profile")
        if tuple(item.scenario_id for item in profiles) != tuple(
            sorted(item.scenario_id for item in profiles)
        ):
            raise ValueError("profiles must use increasing scenario-id order")
        if len({item.scenario_id for item in profiles}) != len(profiles):
            raise ValueError("profile scenario ids must be unique")
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        for method in methods:
            _require_instance(
                method,
                ClinicalOutcomeClusterSizeMethod,
                "method",
            )
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
        _require_instance(
            self.primary_metric,
            ClinicalOutcomeDesignMetric,
            "primary_metric",
        )
        if self.primary_metric is not ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE:
            raise ValueError(
                "v1 direction diagnostics require observed_favorable_rate as primary_metric"
            )
        _require_probability(self.direction_threshold, "direction_threshold")
        if self.method_id != CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
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
class ClinicalOutcomeClusterSizeStatusCount(SerializableRecord):
    status: ClinicalOutcomeClusterSizeStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(self.status, ClinicalOutcomeClusterSizeStatus, "status")
        _require_non_negative_int(self.count, "count")


def _status_count_records(
    counts: Mapping[ClinicalOutcomeClusterSizeStatus, int],
) -> tuple[ClinicalOutcomeClusterSizeStatusCount, ...]:
    return tuple(
        ClinicalOutcomeClusterSizeStatusCount(status=status, count=counts.get(status, 0))
        for status in _STATUS_ORDER
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSizeCell(SerializableRecord):
    method: ClinicalOutcomeClusterSizeMethod
    target_estimand: ClinicalOutcomeClusterSizeEstimand
    metric: ClinicalOutcomeDesignMetric
    log_imor: float
    informative_missingness_odds_ratio: float
    unit_weighted_true_value: float
    cluster_balanced_true_value: float
    estimand_contrast_unit_minus_cluster: float
    target_true_value: float
    alternate_true_value: float
    replicate_count: int
    point_estimate_count: int
    interval_count: int
    covered_count: int
    interval_yield: ClinicalOutcomeDesignRate
    target_coverage: ClinicalOutcomeDesignRate
    mean_estimate: float | None
    target_bias: float | None
    alternate_estimand_bias: float | None
    empirical_standard_deviation: float | None
    monte_carlo_bias_lower: float | None
    monte_carlo_bias_upper: float | None
    monte_carlo_absolute_bias_upper: float | None
    root_mean_squared_reported_standard_error: float | None
    mean_reported_standard_error: float | None
    mean_interval_width: float | None
    interval_width_empirical_standard_deviation: float | None
    mean_interval_width_monte_carlo_lower: float | None
    mean_interval_width_monte_carlo_upper: float | None
    standard_error_to_empirical_sd_ratio: float | None
    maximum_absolute_bias: float
    coverage_target: float
    minimum_interval_yield: float
    standard_error_calibration_lower: float
    standard_error_calibration_upper: float
    bias_target_met: bool
    interval_yield_target_met: bool
    coverage_target_met: bool
    standard_error_calibration_target_met: bool
    calibration_target_met: bool
    status_counts: tuple[ClinicalOutcomeClusterSizeStatusCount, ...]

    def __post_init__(self) -> None:
        _require_instance(self.method, ClinicalOutcomeClusterSizeMethod, "method")
        _require_instance(
            self.target_estimand,
            ClinicalOutcomeClusterSizeEstimand,
            "target_estimand",
        )
        if self.target_estimand is not _target_estimand(self.method):
            raise ValueError("method target estimand is inconsistent")
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        lower, upper = _metric_bounds(self.metric)
        _require_finite(
            self.log_imor,
            "log_imor",
            minimum=-MAX_ABSOLUTE_LOG_IMOR,
            maximum=MAX_ABSOLUTE_LOG_IMOR,
        )
        _require_finite(
            self.informative_missingness_odds_ratio,
            "informative_missingness_odds_ratio",
            minimum=0.0,
        )
        if self.informative_missingness_odds_ratio != _round_metric(
            math.exp(self.log_imor)
        ):
            raise ValueError("informative missingness odds ratio is inconsistent")
        for field_name in (
            "unit_weighted_true_value",
            "cluster_balanced_true_value",
            "target_true_value",
            "alternate_true_value",
        ):
            _require_finite(
                getattr(self, field_name),
                field_name,
                minimum=lower,
                maximum=upper,
            )
        contrast = _round_metric(
            self.unit_weighted_true_value - self.cluster_balanced_true_value
        )
        if self.estimand_contrast_unit_minus_cluster != contrast:
            raise ValueError("estimand contrast is inconsistent")
        expected_target = (
            self.unit_weighted_true_value
            if self.target_estimand is ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
            else self.cluster_balanced_true_value
        )
        expected_alternate = (
            self.cluster_balanced_true_value
            if self.target_estimand is ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
            else self.unit_weighted_true_value
        )
        if (
            self.target_true_value != expected_target
            or self.alternate_true_value != expected_alternate
        ):
            raise ValueError("target and alternate truths are inconsistent")
        _require_positive_int(self.replicate_count, "replicate_count")
        for field_name in ("point_estimate_count", "interval_count", "covered_count"):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if not (
            self.covered_count
            <= self.interval_count
            <= self.point_estimate_count
            <= self.replicate_count
        ):
            raise ValueError("cell counts are inconsistent")
        for value, field_name in (
            (self.interval_yield, "interval_yield"),
            (self.target_coverage, "target_coverage"),
        ):
            _require_instance(value, ClinicalOutcomeDesignRate, field_name)
        if (
            self.interval_yield.event_count != self.interval_count
            or self.interval_yield.total_count != self.replicate_count
        ):
            raise ValueError("interval-yield denominator is inconsistent")
        if (
            self.target_coverage.event_count != self.covered_count
            or self.target_coverage.total_count != self.interval_count
            or self.target_coverage.confidence_level
            != self.interval_yield.confidence_level
        ):
            raise ValueError("target-coverage denominator is inconsistent")
        optional_nonnegative = {
            "empirical_standard_deviation",
            "monte_carlo_absolute_bias_upper",
            "root_mean_squared_reported_standard_error",
            "mean_reported_standard_error",
            "mean_interval_width",
            "interval_width_empirical_standard_deviation",
            "mean_interval_width_monte_carlo_lower",
            "mean_interval_width_monte_carlo_upper",
            "standard_error_to_empirical_sd_ratio",
        }
        optional_fields = (
            "mean_estimate",
            "target_bias",
            "alternate_estimand_bias",
            "empirical_standard_deviation",
            "monte_carlo_bias_lower",
            "monte_carlo_bias_upper",
            "monte_carlo_absolute_bias_upper",
            "root_mean_squared_reported_standard_error",
            "mean_reported_standard_error",
            "mean_interval_width",
            "interval_width_empirical_standard_deviation",
            "mean_interval_width_monte_carlo_lower",
            "mean_interval_width_monte_carlo_upper",
            "standard_error_to_empirical_sd_ratio",
        )
        for field_name in optional_fields:
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=0.0 if field_name in optional_nonnegative else None,
            )
        if self.mean_estimate is not None and not lower <= self.mean_estimate <= upper:
            raise ValueError("mean_estimate falls outside the metric scale")
        if self.point_estimate_count == 0:
            if any(
                getattr(self, field_name) is not None
                for field_name in (
                    "mean_estimate",
                    "target_bias",
                    "alternate_estimand_bias",
                    "empirical_standard_deviation",
                    "monte_carlo_bias_lower",
                    "monte_carlo_bias_upper",
                    "monte_carlo_absolute_bias_upper",
                )
            ):
                raise ValueError("empty point estimates require null summaries")
        else:
            if self.mean_estimate is None:
                raise ValueError("point estimates require a mean")
            if self.target_bias != _round_metric(
                self.mean_estimate - self.target_true_value
            ):
                raise ValueError("target bias is inconsistent")
            if self.alternate_estimand_bias != _round_metric(
                self.mean_estimate - self.alternate_true_value
            ):
                raise ValueError("alternate-estimand bias is inconsistent")
            if (self.point_estimate_count == 1) != (
                self.empirical_standard_deviation is None
            ):
                raise ValueError("empirical standard deviation is inconsistent")
            bias_bounds = _mc_mean_bounds(
                self.target_bias,
                self.empirical_standard_deviation,
                self.point_estimate_count,
                self.interval_yield.confidence_level,
            )
            if (self.monte_carlo_bias_lower, self.monte_carlo_bias_upper) != bias_bounds:
                raise ValueError("Monte Carlo bias bounds are inconsistent")
            expected_abs = (
                None
                if bias_bounds[0] is None
                else _round_metric(max(abs(bias_bounds[0]), abs(bias_bounds[1])))
            )
            if self.monte_carlo_absolute_bias_upper != expected_abs:
                raise ValueError("Monte Carlo absolute-bias bound is inconsistent")
        statuses = _tuple(self.status_counts, "status_counts")
        object.__setattr__(self, "status_counts", statuses)
        for item in statuses:
            _require_instance(
                item,
                ClinicalOutcomeClusterSizeStatusCount,
                "status count",
            )
        if tuple(item.status for item in statuses) != _STATUS_ORDER:
            raise ValueError("status_counts must exactly cover canonical statuses")
        if sum(item.count for item in statuses) != self.replicate_count:
            raise ValueError("status counts do not sum to replicate_count")
        if next(
            item.count
            for item in statuses
            if item.status is ClinicalOutcomeClusterSizeStatus.COMPUTED
        ) != self.interval_count:
            raise ValueError("computed status count is inconsistent")
        expected_point_count = self.interval_count + next(
            item.count
            for item in statuses
            if item.status is ClinicalOutcomeClusterSizeStatus.ZERO_RESAMPLING_VARIANCE
        )
        if self.point_estimate_count != expected_point_count:
            raise ValueError("point-estimate status count is inconsistent")
        if self.interval_count == 0:
            if any(
                getattr(self, field_name) is not None
                for field_name in (
                    "root_mean_squared_reported_standard_error",
                    "mean_reported_standard_error",
                    "mean_interval_width",
                    "interval_width_empirical_standard_deviation",
                    "mean_interval_width_monte_carlo_lower",
                    "mean_interval_width_monte_carlo_upper",
                    "standard_error_to_empirical_sd_ratio",
                )
            ):
                raise ValueError("empty intervals require null uncertainty summaries")
        else:
            if any(
                getattr(self, field_name) is None
                for field_name in (
                    "root_mean_squared_reported_standard_error",
                    "mean_reported_standard_error",
                    "mean_interval_width",
                )
            ):
                raise ValueError("computed intervals require uncertainty summaries")
            if (self.interval_count == 1) != (
                self.interval_width_empirical_standard_deviation is None
            ):
                raise ValueError("interval-width deviation is inconsistent")
            width_bounds = _mc_nonnegative_mean_bounds(
                self.mean_interval_width,
                self.interval_width_empirical_standard_deviation,
                self.interval_count,
                self.interval_yield.confidence_level,
            )
            if (
                self.mean_interval_width_monte_carlo_lower,
                self.mean_interval_width_monte_carlo_upper,
            ) != width_bounds:
                raise ValueError("Monte Carlo interval-width bounds are inconsistent")
        expected_ratio = (
            None
            if self.root_mean_squared_reported_standard_error is None
            or self.empirical_standard_deviation in (None, 0.0)
            else _round_metric(
                self.root_mean_squared_reported_standard_error
                / self.empirical_standard_deviation
            )
        )
        if self.standard_error_to_empirical_sd_ratio != expected_ratio:
            raise ValueError("standard-error calibration ratio is inconsistent")
        for field_name in (
            "maximum_absolute_bias",
            "coverage_target",
            "minimum_interval_yield",
            "standard_error_calibration_lower",
            "standard_error_calibration_upper",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        expected_bias_met = (
            self.monte_carlo_absolute_bias_upper is not None
            and self.monte_carlo_absolute_bias_upper <= self.maximum_absolute_bias
        )
        expected_yield_met = (
            self.interval_yield.lower is not None
            and self.interval_yield.lower >= self.minimum_interval_yield
        )
        expected_coverage_met = (
            self.target_coverage.lower is not None
            and self.target_coverage.lower >= self.coverage_target
        )
        expected_se_met = (
            self.standard_error_to_empirical_sd_ratio is not None
            and self.standard_error_calibration_lower
            <= self.standard_error_to_empirical_sd_ratio
            <= self.standard_error_calibration_upper
        )
        flags = (
            (self.bias_target_met, expected_bias_met),
            (self.interval_yield_target_met, expected_yield_met),
            (self.coverage_target_met, expected_coverage_met),
            (self.standard_error_calibration_target_met, expected_se_met),
        )
        for actual, expected in flags:
            _require_bool(actual, "calibration target flag")
            if actual != expected:
                raise ValueError("cell calibration target flag is inconsistent")
        expected_all = all(expected for _, expected in flags)
        _require_bool(self.calibration_target_met, "calibration_target_met")
        if self.calibration_target_met != expected_all:
            raise ValueError("cell calibration target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSizeMetricResult(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    grid_inference: tuple[ClinicalOutcomeClusterSizeCell, ...]
    all_grid_calibration_targets_met: bool

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        grid = _tuple(self.grid_inference, "grid_inference")
        object.__setattr__(self, "grid_inference", grid)
        if not grid:
            raise ValueError("grid_inference cannot be empty")
        for item in grid:
            _require_instance(item, ClinicalOutcomeClusterSizeCell, "grid cell")
        if any(item.metric is not self.metric for item in grid):
            raise ValueError("grid metric is inconsistent")
        if len({item.method for item in grid}) != 1 or len(
            {item.target_estimand for item in grid}
        ) != 1:
            raise ValueError("grid method or target estimand changed")
        if tuple(item.log_imor for item in grid) != tuple(
            sorted({item.log_imor for item in grid})
        ):
            raise ValueError("grid inference must be unique and increasing")
        _require_bool(
            self.all_grid_calibration_targets_met,
            "all_grid_calibration_targets_met",
        )
        if self.all_grid_calibration_targets_met != all(
            item.calibration_target_met for item in grid
        ):
            raise ValueError("all-grid calibration flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterSizeMethodResult(SerializableRecord):
    method: ClinicalOutcomeClusterSizeMethod
    target_estimand: ClinicalOutcomeClusterSizeEstimand
    metric_inference: tuple[ClinicalOutcomeClusterSizeMetricResult, ...]
    all_metric_calibration_targets_met: bool

    def __post_init__(self) -> None:
        _require_instance(self.method, ClinicalOutcomeClusterSizeMethod, "method")
        _require_instance(
            self.target_estimand,
            ClinicalOutcomeClusterSizeEstimand,
            "target_estimand",
        )
        if self.target_estimand is not _target_estimand(self.method):
            raise ValueError("method target estimand is inconsistent")
        metrics = _tuple(self.metric_inference, "metric_inference")
        object.__setattr__(self, "metric_inference", metrics)
        for item in metrics:
            _require_instance(
                item,
                ClinicalOutcomeClusterSizeMetricResult,
                "metric result",
            )
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("metric_inference must exactly cover canonical metrics")
        if any(
            cell.method is not self.method
            or cell.target_estimand is not self.target_estimand
            for metric in metrics
            for cell in metric.grid_inference
        ):
            raise ValueError("nested method or target estimand is inconsistent")
        _require_bool(
            self.all_metric_calibration_targets_met,
            "all_metric_calibration_targets_met",
        )
        if self.all_metric_calibration_targets_met != all(
            item.all_grid_calibration_targets_met for item in metrics
        ):
            raise ValueError("all-metric calibration flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeClusterInfluenceDiagnostic(SerializableRecord):
    method: ClinicalOutcomeClusterSizeMethod
    basis: ClinicalOutcomeClusterInfluenceBasis
    primary_metric: ClinicalOutcomeDesignMetric
    reference_log_imor: float
    analyzable_replicate_count: int
    mean_maximum_absolute_influence: float | None
    p95_maximum_absolute_influence: float | None
    mean_maximum_absolute_influence_share: float | None
    unique_largest_block_available: bool
    unique_largest_block_most_influential: ClinicalOutcomeDesignRate
    largest_block_deletion_direction_flip_applicable: bool
    largest_block_deletion_direction_flip: ClinicalOutcomeDesignRate

    def __post_init__(self) -> None:
        _require_instance(self.method, ClinicalOutcomeClusterSizeMethod, "method")
        _require_instance(self.basis, ClinicalOutcomeClusterInfluenceBasis, "basis")
        if self.basis is not _influence_basis(self.method):
            raise ValueError("influence basis is inconsistent")
        _require_instance(
            self.primary_metric,
            ClinicalOutcomeDesignMetric,
            "primary_metric",
        )
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
        if self.analyzable_replicate_count == 0:
            if any(
                getattr(self, field_name) is not None
                for field_name in (
                    "mean_maximum_absolute_influence",
                    "p95_maximum_absolute_influence",
                    "mean_maximum_absolute_influence_share",
                )
            ):
                raise ValueError("empty influence diagnostics require null summaries")
        elif any(
            getattr(self, field_name) is None
            for field_name in (
                "mean_maximum_absolute_influence",
                "p95_maximum_absolute_influence",
                "mean_maximum_absolute_influence_share",
            )
        ):
            raise ValueError("analyzable influence diagnostics require summaries")
        for field_name in (
            "unique_largest_block_available",
            "largest_block_deletion_direction_flip_applicable",
        ):
            _require_bool(getattr(self, field_name), field_name)
        for value, field_name in (
            (
                self.unique_largest_block_most_influential,
                "unique_largest_block_most_influential",
            ),
            (
                self.largest_block_deletion_direction_flip,
                "largest_block_deletion_direction_flip",
            ),
        ):
            _require_instance(value, ClinicalOutcomeDesignRate, field_name)
        if (
            self.unique_largest_block_most_influential.confidence_level
            != self.largest_block_deletion_direction_flip.confidence_level
        ):
            raise ValueError("influence rate confidence levels are inconsistent")
        largest_denominator = (
            self.analyzable_replicate_count
            if self.unique_largest_block_available
            else 0
        )
        if self.unique_largest_block_most_influential.total_count != largest_denominator:
            raise ValueError("largest-block influence denominator is inconsistent")
        expected_flip_applicable = (
            self.unique_largest_block_available
            and self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT
        )
        if (
            self.largest_block_deletion_direction_flip_applicable
            != expected_flip_applicable
        ):
            raise ValueError("largest-block direction-flip applicability is inconsistent")
        flip_denominator = (
            self.analyzable_replicate_count if expected_flip_applicable else 0
        )
        if self.largest_block_deletion_direction_flip.total_count != flip_denominator:
            raise ValueError("largest-block direction-flip denominator is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeInformativeClusterSizeScenarioResult(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    true_log_imor: float
    analysis_structure: ClinicalOutcomeDesignStructure
    block_favorable_prevalences: tuple[float, ...]
    unit_weighted_favorable_prevalence: float
    cluster_balanced_favorable_prevalence: float
    favorable_prevalence_contrast_unit_minus_cluster: float
    size_outcome_covariance: float
    size_outcome_correlation: float | None
    unit_weighted_reference_direction: ClinicalOutcomeThresholdDirection
    cluster_balanced_reference_direction: ClinicalOutcomeThresholdDirection
    truth_direction_disagrees: bool
    production_eligible: bool
    production_ineligibility_reasons: tuple[str, ...]
    method_results: tuple[ClinicalOutcomeClusterSizeMethodResult, ...]
    influence_diagnostics: tuple[ClinicalOutcomeClusterInfluenceDiagnostic, ...]
    dominant_cluster_hard_stop_preserved: bool
    rng_stream_sha256: str
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
        _require_instance(
            self.analysis_structure,
            ClinicalOutcomeDesignStructure,
            "analysis_structure",
        )
        prevalences = _tuple(
            self.block_favorable_prevalences,
            "block_favorable_prevalences",
        )
        object.__setattr__(self, "block_favorable_prevalences", prevalences)
        if len(prevalences) != self.analysis_structure.cluster_count:
            raise ValueError("block prevalence count is inconsistent")
        for value in prevalences:
            _require_probability(value, "block favorable prevalence")
            if value in (0.0, 1.0):
                raise ValueError("block favorable prevalences must be strictly interior")
        for field_name in (
            "unit_weighted_favorable_prevalence",
            "cluster_balanced_favorable_prevalence",
        ):
            _require_probability(getattr(self, field_name), field_name)
        expected_contrast = _round_metric(
            self.unit_weighted_favorable_prevalence
            - self.cluster_balanced_favorable_prevalence
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
        reasons = _tuple(
            self.production_ineligibility_reasons,
            "production_ineligibility_reasons",
        )
        object.__setattr__(self, "production_ineligibility_reasons", reasons)
        allowed_reasons = ("insufficient_clusters", "dominant_cluster")
        if reasons != tuple(reason for reason in allowed_reasons if reason in reasons):
            raise ValueError("production ineligibility reasons are not canonical")
        _require_bool(self.production_eligible, "production_eligible")
        if self.production_eligible != (not reasons):
            raise ValueError("production eligibility is inconsistent")
        methods = _tuple(self.method_results, "method_results")
        object.__setattr__(self, "method_results", methods)
        for item in methods:
            _require_instance(
                item,
                ClinicalOutcomeClusterSizeMethodResult,
                "method result",
            )
        if tuple(item.method for item in methods) != _METHOD_ORDER:
            raise ValueError("method_results must exactly cover canonical methods")
        reference_method = methods[0]
        for method in methods[1:]:
            for reference_metric, metric in zip(
                reference_method.metric_inference,
                method.metric_inference,
                strict=True,
            ):
                for reference_cell, cell in zip(
                    reference_metric.grid_inference,
                    metric.grid_inference,
                    strict=True,
                ):
                    if (
                        cell.log_imor != reference_cell.log_imor
                        or cell.unit_weighted_true_value
                        != reference_cell.unit_weighted_true_value
                        or cell.cluster_balanced_true_value
                        != reference_cell.cluster_balanced_true_value
                    ):
                        raise ValueError("method-specific truth values changed")
        diagnostics = _tuple(self.influence_diagnostics, "influence_diagnostics")
        object.__setattr__(self, "influence_diagnostics", diagnostics)
        for item in diagnostics:
            _require_instance(
                item,
                ClinicalOutcomeClusterInfluenceDiagnostic,
                "influence diagnostic",
            )
        if tuple(item.method for item in diagnostics) != _METHOD_ORDER:
            raise ValueError("influence_diagnostics must exactly cover canonical methods")
        _require_bool(
            self.dominant_cluster_hard_stop_preserved,
            "dominant_cluster_hard_stop_preserved",
        )
        dominant = "dominant_cluster" in reasons
        if self.dominant_cluster_hard_stop_preserved != (
            not dominant or not self.production_eligible
        ):
            raise ValueError("dominant-cluster hard stop is inconsistent")
        for field_name in (
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeInformativeClusterSizeReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    stress_protocol_id: str
    stress_protocol_fingerprint: str
    method_id: str
    rng_method_id: str
    replicates: int
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
    scenario_results: tuple[ClinicalOutcomeInformativeClusterSizeScenarioResult, ...]
    aggregate_simulation_only: bool = True
    replicate_level_records_included: bool = False
    cluster_level_records_included: bool = False
    unit_level_records_included: bool = False
    real_clinical_outcomes_included: bool = False
    automatic_estimand_selection_included: bool = False
    delete_mj_estimand_correction_claimed: bool = False
    dominant_cluster_override_allowed: bool = False
    fixed_block_profiles_across_replicates: bool = True
    cluster_superpopulation_resampling_included: bool = False
    identification_and_sampling_uncertainty_separated: bool = True
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "stress_protocol_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in ("protocol_fingerprint", "stress_protocol_fingerprint"):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        _require_positive_int(self.replicates, "replicates")
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        for method in methods:
            _require_instance(
                method,
                ClinicalOutcomeClusterSizeMethod,
                "method",
            )
        if methods != _METHOD_ORDER:
            raise ValueError("methods changed")
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
        if not 0.5 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError(
                "monte_carlo_confidence_level must be between 0.5 and 1"
            )
        if not 0.0 < self.coverage_target < self.confidence_level:
            raise ValueError("coverage_target must be positive and below confidence_level")
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
        if self.maximum_production_cluster_unit_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_production_cluster_unit_fraction must be strictly interior"
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
            raise ValueError(
                "standard-error calibration bounds must be symmetric around one"
            )
        _require_instance(self.primary_metric, ClinicalOutcomeDesignMetric, "primary_metric")
        if self.primary_metric is not ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE:
            raise ValueError(
                "v1 direction diagnostics require observed_favorable_rate as primary_metric"
            )
        scenarios = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", scenarios)
        if not scenarios:
            raise ValueError("scenario_results cannot be empty")
        for item in scenarios:
            _require_instance(
                item,
                ClinicalOutcomeInformativeClusterSizeScenarioResult,
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
            expected_reasons: list[str] = []
            if scenario.analysis_structure.cluster_count < self.minimum_production_clusters:
                expected_reasons.append("insufficient_clusters")
            if (
                scenario.analysis_structure.maximum_cluster_fraction
                > self.maximum_production_cluster_unit_fraction
            ):
                expected_reasons.append("dominant_cluster")
            if scenario.production_ineligibility_reasons != tuple(expected_reasons):
                raise ValueError("scenario production eligibility changed")
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
            for diagnostic in scenario.influence_diagnostics:
                primary_method = next(
                    method
                    for method in scenario.method_results
                    if method.method is diagnostic.method
                )
                primary_metric = next(
                    metric
                    for metric in primary_method.metric_inference
                    if metric.metric is self.primary_metric
                )
                primary_cell = next(
                    cell
                    for cell in primary_metric.grid_inference
                    if cell.log_imor == self.reference_log_imor
                )
                if (
                    diagnostic.primary_metric is not self.primary_metric
                    or diagnostic.reference_log_imor != self.reference_log_imor
                    or diagnostic.analyzable_replicate_count
                    != primary_cell.point_estimate_count
                    or diagnostic.unique_largest_block_most_influential.confidence_level
                    != self.monte_carlo_confidence_level
                    or diagnostic.largest_block_deletion_direction_flip.confidence_level
                    != self.monte_carlo_confidence_level
                ):
                    raise ValueError("nested influence diagnostic contract changed")
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
                != scenario.unit_weighted_favorable_prevalence
                or primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED
                ].cluster_balanced_true_value
                != scenario.cluster_balanced_favorable_prevalence
            ):
                raise ValueError("reference truths do not recover profile prevalences")
            if scenario.unit_weighted_reference_direction is not _threshold_direction(
                primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
                ].unit_weighted_true_value,
                self.direction_threshold,
            ) or scenario.cluster_balanced_reference_direction is not _threshold_direction(
                primary_cells[
                    ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED
                ].cluster_balanced_true_value,
                self.direction_threshold,
            ):
                raise ValueError("scenario truth direction changed")
        boundary_fields = (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "cluster_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "automatic_estimand_selection_included",
            "delete_mj_estimand_correction_claimed",
            "dominant_cluster_override_allowed",
            "fixed_block_profiles_across_replicates",
            "cluster_superpopulation_resampling_included",
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
            or self.automatic_estimand_selection_included
            or self.delete_mj_estimand_correction_claimed
            or self.dominant_cluster_override_allowed
            or not self.fixed_block_profiles_across_replicates
            or self.cluster_superpopulation_resampling_included
            or not self.identification_and_sampling_uncertainty_separated
        ):
            raise ValueError("informative-cluster-size report crossed its claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


class _MomentAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.squared_total = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.squared_total += value * value

    def mean(self) -> float | None:
        return None if self.count == 0 else _round_metric(self.total / self.count)

    def sample_standard_deviation(self) -> float | None:
        if self.count < 2:
            return None
        numerator = self.squared_total - self.total * self.total / self.count
        return _round_metric(math.sqrt(max(0.0, numerator) / (self.count - 1)))

    def root_mean_square(self) -> float | None:
        if self.count == 0:
            return None
        return _round_metric(math.sqrt(self.squared_total / self.count))


class _CellAccumulator:
    def __init__(self) -> None:
        self.points = _MomentAccumulator()
        self.standard_errors = _MomentAccumulator()
        self.widths = _MomentAccumulator()
        self.covered = 0
        self.status_counts: Counter[ClinicalOutcomeClusterSizeStatus] = Counter()

    def add_point(self, value: float) -> None:
        self.points.add(value)

    def add_failure(self, status: ClinicalOutcomeClusterSizeStatus) -> None:
        self.status_counts[status] += 1

    def add_interval(
        self,
        *,
        standard_error: float,
        width: float,
        covered: bool,
    ) -> None:
        self.standard_errors.add(standard_error)
        self.widths.add(width)
        self.covered += int(covered)
        self.status_counts[ClinicalOutcomeClusterSizeStatus.COMPUTED] += 1


class _InfluenceAccumulator:
    def __init__(
        self,
        *,
        basis: ClinicalOutcomeClusterInfluenceBasis,
        unique_largest_index: int | None,
        direction_threshold: float,
    ) -> None:
        self.basis = basis
        self.unique_largest_index = unique_largest_index
        self.direction_threshold = direction_threshold
        self.maximum_absolute_values: list[float] = []
        self.maximum_absolute_shares = _MomentAccumulator()
        self.largest_most_influential_count = 0
        self.direction_flip_count = 0

    def add(
        self,
        *,
        influence_values: Sequence[float],
        full_estimate: float,
        leave_one_out_estimates: Sequence[float] | None,
    ) -> None:
        values = tuple(influence_values)
        if not values:
            raise ValueError("influence values cannot be empty")
        absolute = tuple(abs(value) for value in values)
        maximum = max(absolute)
        total = sum(absolute)
        self.maximum_absolute_values.append(maximum)
        self.maximum_absolute_shares.add(0.0 if total == 0.0 else maximum / total)
        if self.unique_largest_index is not None:
            if absolute[self.unique_largest_index] >= maximum - 1e-15:
                self.largest_most_influential_count += 1
            if self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT:
                if leave_one_out_estimates is None:
                    raise ValueError("leave-one-out influence requires deleted estimates")
                if _threshold_direction(
                    full_estimate,
                    self.direction_threshold,
                ) is not _threshold_direction(
                    leave_one_out_estimates[self.unique_largest_index],
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
    ) -> ClinicalOutcomeClusterInfluenceDiagnostic:
        count = len(self.maximum_absolute_values)
        mean_maximum = (
            None
            if count == 0
            else _round_metric(sum(self.maximum_absolute_values) / count)
        )
        p95_maximum = (
            None
            if count == 0
            else _round_metric(_linear_quantile(self.maximum_absolute_values, 0.95))
        )
        largest_total = count if self.unique_largest_index is not None else 0
        flip_applicable = (
            self.unique_largest_index is not None
            and self.basis is ClinicalOutcomeClusterInfluenceBasis.LEAVE_ONE_OUT_SHIFT
        )
        return ClinicalOutcomeClusterInfluenceDiagnostic(
            method=method,
            basis=self.basis,
            primary_metric=primary_metric,
            reference_log_imor=reference_log_imor,
            analyzable_replicate_count=count,
            mean_maximum_absolute_influence=mean_maximum,
            p95_maximum_absolute_influence=p95_maximum,
            mean_maximum_absolute_influence_share=(
                self.maximum_absolute_shares.mean()
            ),
            unique_largest_block_available=self.unique_largest_index is not None,
            unique_largest_block_most_influential=_design_rate(
                self.largest_most_influential_count,
                largest_total,
                confidence_level,
            ),
            largest_block_deletion_direction_flip_applicable=flip_applicable,
            largest_block_deletion_direction_flip=_design_rate(
                self.direction_flip_count,
                count if flip_applicable else 0,
                confidence_level,
            ),
        )


def _cluster_support_status(value: Any) -> ClinicalOutcomeClusterSizeStatus:
    if getattr(value, "value", None) == "empty_reference_stratum":
        return ClinicalOutcomeClusterSizeStatus.CLUSTER_EMPTY_REFERENCE_STRATUM
    if getattr(value, "value", None) == "degenerate_reference_stratum":
        return ClinicalOutcomeClusterSizeStatus.CLUSTER_DEGENERATE_REFERENCE_STRATUM
    raise ClinicalOutcomeInformativeClusterSizeError(
        "cluster support status must describe a full cluster"
    )


def _profile_truths(
    scenario: ClinicalOutcomeStressScenario,
    layout: Any,
    profile: ClinicalOutcomeClusterSizeProfile,
    shifts: Sequence[float],
) -> tuple[dict[float, tuple[float, ...]], dict[float, tuple[float, ...]]]:
    mode = ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    group_totals = layout.group_stratum_totals_by_mode[mode]
    block_sizes = tuple(sum(row) for row in group_totals)
    block_truths: list[dict[float, tuple[float, ...]]] = []
    for block_index, prevalence in enumerate(profile.block_favorable_prevalences):
        expected_evaluable = (
            prevalence * scenario.favorable_evaluable_probability
            + (1.0 - prevalence) * scenario.unfavorable_evaluable_probability
        )
        evaluable_prevalence = (
            prevalence * scenario.favorable_evaluable_probability
            / expected_evaluable
        )
        shift_truths: dict[float, tuple[float, ...]] = {}
        for log_imor in shifts:
            missing_prevalence = _odds_shift_probability(
                evaluable_prevalence,
                log_imor,
            )
            model_prevalence = (
                expected_evaluable * evaluable_prevalence
                + (1.0 - expected_evaluable) * missing_prevalence
            )
            metric_values = [0.0] * len(_METRIC_ORDER)
            block_size = block_sizes[block_index]
            for stratum_index, (probability_a, probability_b) in enumerate(
                layout.prediction_strata
            ):
                weight = group_totals[block_index][stratum_index] / block_size
                for metric_index, metric in enumerate(_METRIC_ORDER):
                    metric_values[metric_index] += weight * _expected_metric_value(
                        metric,
                        model_prevalence,
                        probability_a,
                        probability_b,
                        scenario.classification_threshold,
                    )
            shift_truths[log_imor] = tuple(metric_values)
        block_truths.append(shift_truths)
    total_units = sum(block_sizes)
    unit_truths: dict[float, tuple[float, ...]] = {}
    cluster_truths: dict[float, tuple[float, ...]] = {}
    for log_imor in shifts:
        unit_truths[log_imor] = tuple(
            _round_metric(
                sum(
                    size / total_units * block_truths[index][log_imor][metric_index]
                    for index, size in enumerate(block_sizes)
                )
            )
            for metric_index in range(len(_METRIC_ORDER))
        )
        cluster_truths[log_imor] = tuple(
            _round_metric(
                sum(
                    block[log_imor][metric_index] for block in block_truths
                )
                / len(block_truths)
            )
            for metric_index in range(len(_METRIC_ORDER))
        )
    return unit_truths, cluster_truths


def _block_metric_estimates(
    *,
    layout: Any,
    scenario: ClinicalOutcomeStressScenario,
    group_evaluable: Sequence[Sequence[int]],
    group_favorable: Sequence[Sequence[int]],
    shifts: Sequence[float],
) -> tuple[
    ClinicalOutcomeClusterSizeStatus | None,
    tuple[tuple[tuple[float, ...], ...], ...],
]:
    mode = ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    group_totals = layout.group_stratum_totals_by_mode[mode]
    block_results: list[tuple[tuple[float, ...], ...]] = []
    for block_index, totals in enumerate(group_totals):
        support = _support_status(
            totals,
            group_evaluable[block_index],
            group_favorable[block_index],
            leave_one_out=False,
        )
        if support is not None:
            return _cluster_support_status(support), ()
        block_size = sum(totals)
        shift_results: list[tuple[float, ...]] = []
        for log_imor in shifts:
            estimates = [0.0] * len(_METRIC_ORDER)
            for stratum_index, (probability_a, probability_b) in enumerate(
                layout.prediction_strata
            ):
                total = totals[stratum_index]
                observed = group_evaluable[block_index][stratum_index]
                favorable = group_favorable[block_index][stratum_index]
                missing_prevalence = _odds_shift_probability(
                    favorable / observed,
                    log_imor,
                )
                population_prevalence = (
                    favorable + (total - observed) * missing_prevalence
                ) / total
                weight = total / block_size
                for metric_index, metric in enumerate(_METRIC_ORDER):
                    estimates[metric_index] += weight * _expected_metric_value(
                        metric,
                        population_prevalence,
                        probability_a,
                        probability_b,
                        scenario.classification_threshold,
                    )
            shift_results.append(tuple(estimates))
        block_results.append(tuple(shift_results))
    return None, tuple(block_results)


def _cluster_balanced_estimates(
    block_estimates: Sequence[Sequence[Sequence[float]]],
) -> tuple[
    tuple[tuple[float, ...], ...],
    tuple[tuple[tuple[float, ...], ...], ...],
]:
    blocks = tuple(block_estimates)
    block_count = len(blocks)
    shift_count = len(blocks[0])
    metric_count = len(blocks[0][0])
    full = tuple(
        tuple(
            sum(block[shift_index][metric_index] for block in blocks) / block_count
            for metric_index in range(metric_count)
        )
        for shift_index in range(shift_count)
    )
    leaveout = tuple(
        tuple(
            tuple(
                sum(
                    block[shift_index][metric_index]
                    for index, block in enumerate(blocks)
                    if index != removed_index
                )
                / (block_count - 1)
                for metric_index in range(metric_count)
            )
            for shift_index in range(shift_count)
        )
        for removed_index in range(block_count)
    )
    return full, leaveout


def _unit_weighted_estimates(
    block_estimates: Sequence[Sequence[Sequence[float]]],
    cluster_sizes: Sequence[int],
) -> tuple[
    tuple[tuple[float, ...], ...],
    tuple[tuple[tuple[float, ...], ...], ...],
]:
    blocks = tuple(block_estimates)
    sizes = tuple(cluster_sizes)
    if len(blocks) != len(sizes) or len(blocks) < 2:
        raise ValueError("unit-weighted estimates require matched blocks and sizes")
    total_units = sum(sizes)
    shift_count = len(blocks[0])
    metric_count = len(blocks[0][0])
    full = tuple(
        tuple(
            sum(
                size / total_units * block[shift_index][metric_index]
                for size, block in zip(sizes, blocks, strict=True)
            )
            for metric_index in range(metric_count)
        )
        for shift_index in range(shift_count)
    )
    leaveout = tuple(
        tuple(
            tuple(
                sum(
                    size * block[shift_index][metric_index]
                    for index, (size, block) in enumerate(
                        zip(sizes, blocks, strict=True)
                    )
                    if index != removed_index
                )
                / (total_units - sizes[removed_index])
                for metric_index in range(metric_count)
            )
            for shift_index in range(shift_count)
        )
        for removed_index in range(len(blocks))
    )
    return full, leaveout


def _add_interval(
    accumulator: _CellAccumulator,
    *,
    metric: ClinicalOutcomeDesignMetric,
    point_estimate: float,
    standard_error: float,
    critical: float,
    target_truth: float,
) -> None:
    lower, upper = _metric_bounds(metric)
    interval_lower = max(lower, point_estimate - critical * standard_error)
    interval_upper = min(upper, point_estimate + critical * standard_error)
    accumulator.add_interval(
        standard_error=standard_error,
        width=interval_upper - interval_lower,
        covered=(
            interval_lower - 1e-12 <= target_truth <= interval_upper + 1e-12
        ),
    )


def _finalize_cell(
    *,
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    method: ClinicalOutcomeClusterSizeMethod,
    metric: ClinicalOutcomeDesignMetric,
    log_imor: float,
    unit_truth: float,
    cluster_truth: float,
    accumulator: _CellAccumulator,
    replicate_count: int,
) -> ClinicalOutcomeClusterSizeCell:
    target = _target_estimand(method)
    target_truth = (
        unit_truth
        if target is ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
        else cluster_truth
    )
    alternate_truth = (
        cluster_truth
        if target is ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
        else unit_truth
    )
    mean_estimate = accumulator.points.mean()
    empirical_sd = accumulator.points.sample_standard_deviation()
    target_bias = (
        None
        if mean_estimate is None
        else _round_metric(mean_estimate - target_truth)
    )
    alternate_bias = (
        None
        if mean_estimate is None
        else _round_metric(mean_estimate - alternate_truth)
    )
    bias_bounds = _mc_mean_bounds(
        target_bias,
        empirical_sd,
        accumulator.points.count,
        protocol.monte_carlo_confidence_level,
    )
    absolute_bias_upper = (
        None
        if bias_bounds[0] is None
        else _round_metric(max(abs(bias_bounds[0]), abs(bias_bounds[1])))
    )
    interval_count = accumulator.standard_errors.count
    interval_yield = _design_rate(
        interval_count,
        replicate_count,
        protocol.monte_carlo_confidence_level,
    )
    coverage = _design_rate(
        accumulator.covered,
        interval_count,
        protocol.monte_carlo_confidence_level,
    )
    rms_se = accumulator.standard_errors.root_mean_square()
    mean_se = accumulator.standard_errors.mean()
    mean_width = accumulator.widths.mean()
    width_sd = accumulator.widths.sample_standard_deviation()
    width_bounds = _mc_nonnegative_mean_bounds(
        mean_width,
        width_sd,
        accumulator.widths.count,
        protocol.monte_carlo_confidence_level,
    )
    se_ratio = (
        None
        if rms_se is None or empirical_sd in (None, 0.0)
        else _round_metric(rms_se / empirical_sd)
    )
    bias_met = (
        absolute_bias_upper is not None
        and absolute_bias_upper <= protocol.maximum_absolute_bias
    )
    yield_met = (
        interval_yield.lower is not None
        and interval_yield.lower >= protocol.minimum_interval_yield
    )
    coverage_met = (
        coverage.lower is not None and coverage.lower >= protocol.coverage_target
    )
    se_met = (
        se_ratio is not None
        and protocol.standard_error_calibration_lower
        <= se_ratio
        <= protocol.standard_error_calibration_upper
    )
    return ClinicalOutcomeClusterSizeCell(
        method=method,
        target_estimand=target,
        metric=metric,
        log_imor=log_imor,
        informative_missingness_odds_ratio=_round_metric(math.exp(log_imor)),
        unit_weighted_true_value=unit_truth,
        cluster_balanced_true_value=cluster_truth,
        estimand_contrast_unit_minus_cluster=_round_metric(
            unit_truth - cluster_truth
        ),
        target_true_value=target_truth,
        alternate_true_value=alternate_truth,
        replicate_count=replicate_count,
        point_estimate_count=accumulator.points.count,
        interval_count=interval_count,
        covered_count=accumulator.covered,
        interval_yield=interval_yield,
        target_coverage=coverage,
        mean_estimate=mean_estimate,
        target_bias=target_bias,
        alternate_estimand_bias=alternate_bias,
        empirical_standard_deviation=empirical_sd,
        monte_carlo_bias_lower=bias_bounds[0],
        monte_carlo_bias_upper=bias_bounds[1],
        monte_carlo_absolute_bias_upper=absolute_bias_upper,
        root_mean_squared_reported_standard_error=rms_se,
        mean_reported_standard_error=mean_se,
        mean_interval_width=mean_width,
        interval_width_empirical_standard_deviation=width_sd,
        mean_interval_width_monte_carlo_lower=width_bounds[0],
        mean_interval_width_monte_carlo_upper=width_bounds[1],
        standard_error_to_empirical_sd_ratio=se_ratio,
        maximum_absolute_bias=protocol.maximum_absolute_bias,
        coverage_target=protocol.coverage_target,
        minimum_interval_yield=protocol.minimum_interval_yield,
        standard_error_calibration_lower=protocol.standard_error_calibration_lower,
        standard_error_calibration_upper=protocol.standard_error_calibration_upper,
        bias_target_met=bias_met,
        interval_yield_target_met=yield_met,
        coverage_target_met=coverage_met,
        standard_error_calibration_target_met=se_met,
        calibration_target_met=bias_met and yield_met and coverage_met and se_met,
        status_counts=_status_count_records(accumulator.status_counts),
    )


def _fail_method_cells(
    accumulators: Mapping[
        ClinicalOutcomeClusterSizeMethod,
        Mapping[ClinicalOutcomeDesignMetric, Mapping[float, _CellAccumulator]],
    ],
    method: ClinicalOutcomeClusterSizeMethod,
    status: ClinicalOutcomeClusterSizeStatus,
) -> None:
    for metric in _METRIC_ORDER:
        for accumulator in accumulators[method][metric].values():
            accumulator.add_failure(status)


def _production_ineligibility_reasons(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    structure: ClinicalOutcomeDesignStructure,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if structure.cluster_count < protocol.minimum_production_clusters:
        reasons.append("insufficient_clusters")
    if (
        structure.maximum_cluster_fraction
        > protocol.maximum_production_cluster_unit_fraction
    ):
        reasons.append("dominant_cluster")
    return tuple(reasons)


def _size_outcome_association(
    sizes: Sequence[int],
    prevalences: Sequence[float],
) -> tuple[float, float | None]:
    size_mean = sum(sizes) / len(sizes)
    prevalence_mean = sum(prevalences) / len(prevalences)
    covariance = sum(
        (size - size_mean) * (prevalence - prevalence_mean)
        for size, prevalence in zip(sizes, prevalences, strict=True)
    ) / len(sizes)
    size_variance = sum((size - size_mean) ** 2 for size in sizes) / len(sizes)
    prevalence_variance = (
        sum((value - prevalence_mean) ** 2 for value in prevalences)
        / len(prevalences)
    )
    correlation = (
        None
        if size_variance == 0.0 or prevalence_variance == 0.0
        else covariance / math.sqrt(size_variance * prevalence_variance)
    )
    return _round_metric(covariance), (
        None if correlation is None else _round_metric(correlation)
    )


def _simulate_scenario(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
    profile: ClinicalOutcomeClusterSizeProfile,
) -> ClinicalOutcomeInformativeClusterSizeScenarioResult:
    layout = _scenario_layout(scenario)
    mode = ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    structure = layout.structure_by_mode[mode]
    cluster_sizes = tuple(
        sum(row) for row in layout.group_stratum_totals_by_mode[mode]
    )
    unit_truths, cluster_truths = _profile_truths(
        scenario,
        layout,
        profile,
        protocol.log_imor_grid,
    )
    accumulators = {
        method: {
            metric: {
                log_imor: _CellAccumulator() for log_imor in protocol.log_imor_grid
            }
            for metric in _METRIC_ORDER
        }
        for method in protocol.methods
    }
    maximum_size = max(cluster_sizes)
    unique_largest_index = (
        cluster_sizes.index(maximum_size)
        if len(cluster_sizes) >= 2 and cluster_sizes.count(maximum_size) == 1
        else None
    )
    influence_accumulators = {
        method: _InfluenceAccumulator(
            basis=_influence_basis(method),
            unique_largest_index=unique_largest_index,
            direction_threshold=protocol.direction_threshold,
        )
        for method in protocol.methods
    }
    stream_sha256 = _scenario_stream_sha256(stress_protocol, scenario)
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(stream_sha256, "evaluability")
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    student_critical = (
        None
        if structure.cluster_count < 2
        else _student_t_critical(
            protocol.confidence_level,
            structure.cluster_count - 1,
        )
    )
    shift_index = {
        value: index for index, value in enumerate(protocol.log_imor_grid)
    }
    primary_metric_index = _METRIC_ORDER.index(protocol.primary_metric)
    reference_index = shift_index[protocol.reference_log_imor]

    for _ in range(stress_protocol.replicates):
        labels = [0.0] * layout.unit_count
        for block_index, block in enumerate(scenario.dependence_blocks):
            successes = 0
            previous_count = 0
            prevalence = profile.block_favorable_prevalences[block_index]
            for nominal_index in block:
                for unit_index in layout.unit_indices_by_nominal_cluster[nominal_index]:
                    label = _draw_beta_binomial_label(
                        outcome_rng,
                        prevalence,
                        scenario.dependence_block_intraclass_correlation,
                        successes,
                        previous_count,
                    )
                    labels[unit_index] = label
                    successes += int(label)
                    previous_count += 1

        group_evaluable = [
            [0] * len(layout.prediction_strata)
            for _ in layout.group_stratum_totals_by_mode[mode]
        ]
        group_favorable = [
            [0] * len(layout.prediction_strata)
            for _ in layout.group_stratum_totals_by_mode[mode]
        ]
        for unit_index, label in enumerate(labels):
            evaluable_probability = (
                scenario.favorable_evaluable_probability
                if label == 1.0
                else scenario.unfavorable_evaluable_probability
            )
            if evaluability_rng.random() >= evaluable_probability:
                continue
            stratum_index = layout.stratum_index_by_unit[unit_index]
            group_index = layout.unit_group_by_mode[mode][unit_index]
            favorable = int(label)
            group_evaluable[group_index][stratum_index] += 1
            group_favorable[group_index][stratum_index] += favorable

        unit_delete_one_method = (
            ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_ONE_STUDENT_T
        )
        unit_delete_mj_method = (
            ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_MJ_STUDENT_T
        )
        cluster_method = (
            ClinicalOutcomeClusterSizeMethod.CLUSTER_BALANCED_DELETE_ONE_STUDENT_T
        )
        if structure.cluster_count < 2:
            for method in protocol.methods:
                _fail_method_cells(
                    accumulators,
                    method,
                    ClinicalOutcomeClusterSizeStatus.INSUFFICIENT_SIMULATION_CLUSTERS,
                )
            continue

        block_status, block_estimates = _block_metric_estimates(
            layout=layout,
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
                unit_delete_one_variance = _delete_one_variance(
                    unit_leaveout_values
                )
                unit_delete_one_se = math.sqrt(unit_delete_one_variance)
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
                cluster_variance = _delete_one_variance(cluster_leaveout_values)
                cluster_se = math.sqrt(cluster_variance)
                cluster_accumulator = accumulators[cluster_method][metric][log_imor]
                cluster_accumulator.add_point(cluster_estimate)

                if (
                    metric_index == primary_metric_index
                    and log_index == reference_index
                ):
                    influence_accumulators[unit_delete_one_method].add(
                        influence_values=tuple(
                            value - unit_estimate for value in unit_leaveout_values
                        ),
                        full_estimate=unit_estimate,
                        leave_one_out_estimates=unit_leaveout_values,
                    )
                    influence_accumulators[unit_delete_mj_method].add(
                        influence_values=contributions,
                        full_estimate=unit_delete_mj_estimate,
                        leave_one_out_estimates=None,
                    )
                    influence_accumulators[cluster_method].add(
                        influence_values=tuple(
                            value - cluster_estimate
                            for value in cluster_leaveout_values
                        ),
                        full_estimate=cluster_estimate,
                        leave_one_out_estimates=cluster_leaveout_values,
                    )

                for accumulator, point_estimate, standard_error in (
                    (
                        unit_delete_one_accumulator,
                        unit_estimate,
                        unit_delete_one_se,
                    ),
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
                    replicate_count=stress_protocol.replicates,
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

    total_units = sum(cluster_sizes)
    unit_prevalence = _round_metric(
        sum(
            size / total_units * prevalence
            for size, prevalence in zip(
                cluster_sizes,
                profile.block_favorable_prevalences,
                strict=True,
            )
        )
    )
    cluster_prevalence = _round_metric(
        sum(profile.block_favorable_prevalences) / len(cluster_sizes)
    )
    covariance, correlation = _size_outcome_association(
        cluster_sizes,
        profile.block_favorable_prevalences,
    )
    unit_reference = unit_truths[protocol.reference_log_imor][primary_metric_index]
    cluster_reference = cluster_truths[protocol.reference_log_imor][
        primary_metric_index
    ]
    unit_direction = _threshold_direction(
        unit_reference,
        protocol.direction_threshold,
    )
    cluster_direction = _threshold_direction(
        cluster_reference,
        protocol.direction_threshold,
    )
    reasons = _production_ineligibility_reasons(protocol, structure)
    production_eligible = not reasons
    return ClinicalOutcomeInformativeClusterSizeScenarioResult(
        scenario_id=scenario.scenario_id,
        stage=scenario.stage,
        endpoint_family=scenario.endpoint_family,
        true_log_imor=_true_log_imor(scenario),
        analysis_structure=structure,
        block_favorable_prevalences=profile.block_favorable_prevalences,
        unit_weighted_favorable_prevalence=unit_prevalence,
        cluster_balanced_favorable_prevalence=cluster_prevalence,
        favorable_prevalence_contrast_unit_minus_cluster=_round_metric(
            unit_prevalence - cluster_prevalence
        ),
        size_outcome_covariance=covariance,
        size_outcome_correlation=correlation,
        unit_weighted_reference_direction=unit_direction,
        cluster_balanced_reference_direction=cluster_direction,
        truth_direction_disagrees=unit_direction is not cluster_direction,
        production_eligible=production_eligible,
        production_ineligibility_reasons=reasons,
        method_results=tuple(method_results),
        influence_diagnostics=tuple(
            influence_accumulators[method].finalize(
                method=method,
                primary_metric=protocol.primary_metric,
                reference_log_imor=protocol.reference_log_imor,
                confidence_level=protocol.monte_carlo_confidence_level,
            )
            for method in protocol.methods
        ),
        dominant_cluster_hard_stop_preserved=(
            "dominant_cluster" not in reasons or not production_eligible
        ),
        rng_stream_sha256=stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
    )


def _work_units(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> int:
    grid_metrics = len(protocol.log_imor_grid) * len(_METRIC_ORDER)
    return stress_protocol.replicates * sum(
        sum(scenario.nominal_cluster_sizes)
        + len(scenario.dependence_blocks) * grid_metrics * 6
        for scenario in stress_protocol.scenarios
    )


def _validate_protocol_binding(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> dict[str, ClinicalOutcomeClusterSizeProfile]:
    if protocol.stress_protocol_fingerprint != stress_protocol.fingerprint:
        raise ClinicalOutcomeInformativeClusterSizeError(
            "informative-cluster-size protocol is not bound to the stress protocol"
        )
    scenario_by_id = {
        scenario.scenario_id: scenario for scenario in stress_protocol.scenarios
    }
    profile_by_id = {profile.scenario_id: profile for profile in protocol.profiles}
    if tuple(sorted(profile_by_id)) != tuple(sorted(scenario_by_id)):
        raise ClinicalOutcomeInformativeClusterSizeError(
            "profiles must exactly cover stress-protocol scenarios"
        )
    for scenario_id, scenario in scenario_by_id.items():
        profile = profile_by_id[scenario_id]
        if len(profile.block_favorable_prevalences) != len(
            scenario.dependence_blocks
        ):
            raise ClinicalOutcomeInformativeClusterSizeError(
                f"profile {scenario_id!r} does not match dependence-block count"
            )
        layout = _scenario_layout(scenario)
        block_sizes = tuple(
            sum(row)
            for row in layout.group_stratum_totals_by_mode[
                ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
            ]
        )
        weighted_prevalence = _round_metric(
            sum(
                size * prevalence
                for size, prevalence in zip(
                    block_sizes,
                    profile.block_favorable_prevalences,
                    strict=True,
                )
            )
            / sum(block_sizes)
        )
        if weighted_prevalence != scenario.favorable_prevalence:
            raise ClinicalOutcomeInformativeClusterSizeError(
                f"profile {scenario_id!r} is inconsistent with the stress scenario's "
                "unit-weighted favorable prevalence"
            )
        if _true_log_imor(scenario) != protocol.reference_log_imor:
            raise ClinicalOutcomeInformativeClusterSizeError(
                f"scenario {scenario_id!r} does not share the reference true log-IMOR"
            )
    return profile_by_id


def analyze_clinical_outcome_informative_cluster_size(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomeInformativeClusterSizeReport:
    """Replay a bound known-truth study of informative cluster size."""

    _require_instance(
        protocol,
        ClinicalOutcomeInformativeClusterSizeProtocol,
        "protocol",
    )
    _require_instance(
        stress_protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "stress_protocol",
    )
    profiles = _validate_protocol_binding(protocol, stress_protocol)
    if _work_units(protocol, stress_protocol) > MAX_DESIGN_WORK_UNITS:
        raise ClinicalOutcomeInformativeClusterSizeError(
            "informative-cluster-size study exceeds the bounded work budget"
        )
    scenario_results = tuple(
        _simulate_scenario(
            protocol,
            stress_protocol,
            scenario,
            profiles[scenario.scenario_id],
        )
        for scenario in sorted(
            stress_protocol.scenarios,
            key=lambda item: item.scenario_id,
        )
    )
    return ClinicalOutcomeInformativeClusterSizeReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        stress_protocol_id=stress_protocol.protocol_id,
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        method_id=protocol.method_id,
        rng_method_id=stress_protocol.rng_method_id,
        replicates=stress_protocol.replicates,
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


def validate_clinical_outcome_informative_cluster_size_report(
    report: ClinicalOutcomeInformativeClusterSizeReport,
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> tuple[str, ...]:
    """Replay all private simulation inputs and compare the aggregate report."""

    try:
        rebuilt = analyze_clinical_outcome_informative_cluster_size(
            protocol,
            stress_protocol,
        )
    except (ClinicalOutcomeInformativeClusterSizeError, TypeError, ValueError):
        return ("informative_cluster_size_replay_failed",)
    return () if rebuilt == report else ("informative_cluster_size_report_mismatch",)


def _method_reference_cell(
    result: ClinicalOutcomeClusterSizeMethodResult,
    metric: ClinicalOutcomeDesignMetric,
    reference_log_imor: float,
) -> ClinicalOutcomeClusterSizeCell:
    metric_result = next(
        item for item in result.metric_inference if item.metric is metric
    )
    return next(
        item
        for item in metric_result.grid_inference
        if item.log_imor == reference_log_imor
    )


def _rate_projection(value: ClinicalOutcomeDesignRate) -> dict[str, Any]:
    return {
        "event_count": value.event_count,
        "total_count": value.total_count,
        "rate": value.rate,
        "lower": value.lower,
        "upper": value.upper,
    }


def clinical_outcome_informative_cluster_size_summary(
    report: ClinicalOutcomeInformativeClusterSizeReport,
) -> dict[str, Any]:
    """Return a compact estimand and influence comparison."""

    _require_instance(
        report,
        ClinicalOutcomeInformativeClusterSizeReport,
        "report",
    )
    scenarios: list[dict[str, Any]] = []
    for scenario in report.scenario_results:
        methods: list[dict[str, Any]] = []
        for method in scenario.method_results:
            cell = _method_reference_cell(
                method,
                report.primary_metric,
                report.reference_log_imor,
            )
            diagnostic = next(
                item
                for item in scenario.influence_diagnostics
                if item.method is method.method
            )
            methods.append(
                {
                    "method": method.method.value,
                    "target_estimand": method.target_estimand.value,
                    "reference_target_truth": cell.target_true_value,
                    "reference_alternate_truth": cell.alternate_true_value,
                    "reference_mean_estimate": cell.mean_estimate,
                    "reference_target_bias": cell.target_bias,
                    "reference_alternate_estimand_bias": (
                        cell.alternate_estimand_bias
                    ),
                    "reference_interval_yield": _rate_projection(
                        cell.interval_yield
                    ),
                    "reference_target_coverage": _rate_projection(
                        cell.target_coverage
                    ),
                    "reference_standard_error_to_empirical_sd_ratio": (
                        cell.standard_error_to_empirical_sd_ratio
                    ),
                    "reference_calibration_target_met": (
                        cell.calibration_target_met
                    ),
                    "all_metric_calibration_targets_met": (
                        method.all_metric_calibration_targets_met
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
                    "unique_largest_block_most_influential": _rate_projection(
                        diagnostic.unique_largest_block_most_influential
                    ),
                    "largest_block_deletion_direction_flip": _rate_projection(
                        diagnostic.largest_block_deletion_direction_flip
                    ),
                }
            )
        scenarios.append(
            {
                "scenario_id": scenario.scenario_id,
                "cluster_count": scenario.analysis_structure.cluster_count,
                "minimum_cluster_size": (
                    scenario.analysis_structure.minimum_cluster_size
                ),
                "maximum_cluster_size": (
                    scenario.analysis_structure.maximum_cluster_size
                ),
                "maximum_cluster_fraction": (
                    scenario.analysis_structure.maximum_cluster_fraction
                ),
                "unit_weighted_favorable_prevalence": (
                    scenario.unit_weighted_favorable_prevalence
                ),
                "cluster_balanced_favorable_prevalence": (
                    scenario.cluster_balanced_favorable_prevalence
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
                "production_eligible": scenario.production_eligible,
                "production_ineligibility_reasons": list(
                    scenario.production_ineligibility_reasons
                ),
                "methods": methods,
            }
        )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_SUMMARY_SCHEMA_VERSION
        ),
        "report_fingerprint": report.fingerprint,
        "primary_metric": report.primary_metric.value,
        "reference_log_imor": report.reference_log_imor,
        "direction_threshold": report.direction_threshold,
        "automatic_estimand_selection_included": (
            report.automatic_estimand_selection_included
        ),
        "delete_mj_estimand_correction_claimed": (
            report.delete_mj_estimand_correction_claimed
        ),
        "fixed_block_profiles_across_replicates": (
            report.fixed_block_profiles_across_replicates
        ),
        "cluster_superpopulation_resampling_included": (
            report.cluster_superpopulation_resampling_included
        ),
        "scenarios": scenarios,
    }


def clinical_outcome_informative_cluster_size_validation_summary(
    report: ClinicalOutcomeInformativeClusterSizeReport,
    *,
    failures: Sequence[str] = (),
    scope: str = "integrity_and_aggregate_consistency",
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomeInformativeClusterSizeReport,
        "report",
    )
    _require_text(scope, "scope")
    resolved_failures = tuple(failures)
    for failure in resolved_failures:
        _require_text(failure, "failure")
    return {
        "schema_version": (
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_SUMMARY_SCHEMA_VERSION
        ),
        "valid": not resolved_failures,
        "scope": scope,
        "report_fingerprint": report.fingerprint,
        "protocol_fingerprint": report.protocol_fingerprint,
        "stress_protocol_fingerprint": report.stress_protocol_fingerprint,
        "failures": list(resolved_failures),
    }


def clinical_outcome_informative_cluster_size_protocol_envelope(
    protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomeInformativeClusterSizeProtocol,
        "protocol",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_PROTOCOL_SCHEMA_VERSION
        ),
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_informative_cluster_size_report_envelope(
    report: ClinicalOutcomeInformativeClusterSizeReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomeInformativeClusterSizeReport,
        "report",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    if _sha256(value) != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def _parse_profile(value: Any, path: str) -> ClinicalOutcomeClusterSizeProfile:
    data = _record(
        value,
        path,
        {"scenario_id", "block_favorable_prevalences"},
    )
    return ClinicalOutcomeClusterSizeProfile(
        scenario_id=data["scenario_id"],
        block_favorable_prevalences=tuple(
            _sequence(
                data["block_favorable_prevalences"],
                f"{path}.block_favorable_prevalences",
            )
        ),
    )


def _clinical_outcome_informative_cluster_size_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_informative_cluster_size_protocol_envelope",
        schema_version=(
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_PROTOCOL_SCHEMA_VERSION
        ),
        payload_field="protocol",
    )
    fields = {
        "protocol_id",
        "version",
        "registered_on",
        "stress_protocol_fingerprint",
        "profiles",
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
    protocol = ClinicalOutcomeInformativeClusterSizeProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        stress_protocol_fingerprint=data["stress_protocol_fingerprint"],
        profiles=tuple(
            _parse_profile(item, f"protocol.profiles[{index}]")
            for index, item in enumerate(
                _sequence(data["profiles"], "protocol.profiles")
            )
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
        reference_log_imor=data["reference_log_imor"],
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        coverage_tolerance=data["coverage_tolerance"],
        minimum_interval_yield=data["minimum_interval_yield"],
        maximum_absolute_bias=data["maximum_absolute_bias"],
        minimum_production_clusters=data["minimum_production_clusters"],
        maximum_production_cluster_unit_fraction=data[
            "maximum_production_cluster_unit_fraction"
        ],
        maximum_standard_error_calibration_deviation=data[
            "maximum_standard_error_calibration_deviation"
        ],
        primary_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["primary_metric"],
            "protocol.primary_metric",
        ),
        direction_threshold=data["direction_threshold"],
        method_id=data["method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "informative-cluster-size protocol")
    return protocol


def clinical_outcome_informative_cluster_size_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    try:
        return _clinical_outcome_informative_cluster_size_protocol_from_dict(value)
    except RecordParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordParseError(
            "informative-cluster-size protocol violates its semantic contract"
        ) from exc


def _parse_status_count(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSizeStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomeClusterSizeStatusCount(
        status=_parse_enum(
            ClinicalOutcomeClusterSizeStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_cell(value: Any, path: str) -> ClinicalOutcomeClusterSizeCell:
    fields = {
        "method",
        "target_estimand",
        "metric",
        "log_imor",
        "informative_missingness_odds_ratio",
        "unit_weighted_true_value",
        "cluster_balanced_true_value",
        "estimand_contrast_unit_minus_cluster",
        "target_true_value",
        "alternate_true_value",
        "replicate_count",
        "point_estimate_count",
        "interval_count",
        "covered_count",
        "interval_yield",
        "target_coverage",
        "mean_estimate",
        "target_bias",
        "alternate_estimand_bias",
        "empirical_standard_deviation",
        "monte_carlo_bias_lower",
        "monte_carlo_bias_upper",
        "monte_carlo_absolute_bias_upper",
        "root_mean_squared_reported_standard_error",
        "mean_reported_standard_error",
        "mean_interval_width",
        "interval_width_empirical_standard_deviation",
        "mean_interval_width_monte_carlo_lower",
        "mean_interval_width_monte_carlo_upper",
        "standard_error_to_empirical_sd_ratio",
        "maximum_absolute_bias",
        "coverage_target",
        "minimum_interval_yield",
        "standard_error_calibration_lower",
        "standard_error_calibration_upper",
        "bias_target_met",
        "interval_yield_target_met",
        "coverage_target_met",
        "standard_error_calibration_target_met",
        "calibration_target_met",
        "status_counts",
    }
    data = _record(value, path, fields)
    excluded = {
        "method",
        "target_estimand",
        "metric",
        "interval_yield",
        "target_coverage",
        "status_counts",
    }
    return ClinicalOutcomeClusterSizeCell(
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
        interval_yield=_parse_design_rate(
            data["interval_yield"],
            f"{path}.interval_yield",
        ),
        target_coverage=_parse_design_rate(
            data["target_coverage"],
            f"{path}.target_coverage",
        ),
        status_counts=tuple(
            _parse_status_count(item, f"{path}.status_counts[{index}]")
            for index, item in enumerate(
                _sequence(data["status_counts"], f"{path}.status_counts")
            )
        ),
        **{key: data[key] for key in fields if key not in excluded},
    )


def _parse_metric_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSizeMetricResult:
    data = _record(
        value,
        path,
        {"metric", "grid_inference", "all_grid_calibration_targets_met"},
    )
    return ClinicalOutcomeClusterSizeMetricResult(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        grid_inference=tuple(
            _parse_cell(item, f"{path}.grid_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["grid_inference"], f"{path}.grid_inference")
            )
        ),
        all_grid_calibration_targets_met=data["all_grid_calibration_targets_met"],
    )


def _parse_method_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterSizeMethodResult:
    data = _record(
        value,
        path,
        {
            "method",
            "target_estimand",
            "metric_inference",
            "all_metric_calibration_targets_met",
        },
    )
    return ClinicalOutcomeClusterSizeMethodResult(
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
        metric_inference=tuple(
            _parse_metric_result(item, f"{path}.metric_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["metric_inference"], f"{path}.metric_inference")
            )
        ),
        all_metric_calibration_targets_met=data[
            "all_metric_calibration_targets_met"
        ],
    )


def _parse_influence_diagnostic(
    value: Any,
    path: str,
) -> ClinicalOutcomeClusterInfluenceDiagnostic:
    fields = {
        "method",
        "basis",
        "primary_metric",
        "reference_log_imor",
        "analyzable_replicate_count",
        "mean_maximum_absolute_influence",
        "p95_maximum_absolute_influence",
        "mean_maximum_absolute_influence_share",
        "unique_largest_block_available",
        "unique_largest_block_most_influential",
        "largest_block_deletion_direction_flip_applicable",
        "largest_block_deletion_direction_flip",
    }
    data = _record(value, path, fields)
    excluded = {
        "method",
        "basis",
        "primary_metric",
        "unique_largest_block_most_influential",
        "largest_block_deletion_direction_flip",
    }
    return ClinicalOutcomeClusterInfluenceDiagnostic(
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
        unique_largest_block_most_influential=_parse_design_rate(
            data["unique_largest_block_most_influential"],
            f"{path}.unique_largest_block_most_influential",
        ),
        largest_block_deletion_direction_flip=_parse_design_rate(
            data["largest_block_deletion_direction_flip"],
            f"{path}.largest_block_deletion_direction_flip",
        ),
        **{key: data[key] for key in fields if key not in excluded},
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeInformativeClusterSizeScenarioResult:
    fields = {
        "scenario_id",
        "stage",
        "endpoint_family",
        "true_log_imor",
        "analysis_structure",
        "block_favorable_prevalences",
        "unit_weighted_favorable_prevalence",
        "cluster_balanced_favorable_prevalence",
        "favorable_prevalence_contrast_unit_minus_cluster",
        "size_outcome_covariance",
        "size_outcome_correlation",
        "unit_weighted_reference_direction",
        "cluster_balanced_reference_direction",
        "truth_direction_disagrees",
        "production_eligible",
        "production_ineligibility_reasons",
        "method_results",
        "influence_diagnostics",
        "dominant_cluster_hard_stop_preserved",
        "rng_stream_sha256",
        "outcome_rng_stream_sha256",
        "evaluability_rng_stream_sha256",
    }
    data = _record(value, path, fields)
    excluded = {
        "stage",
        "analysis_structure",
        "block_favorable_prevalences",
        "unit_weighted_reference_direction",
        "cluster_balanced_reference_direction",
        "production_ineligibility_reasons",
        "method_results",
        "influence_diagnostics",
    }
    return ClinicalOutcomeInformativeClusterSizeScenarioResult(
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        analysis_structure=_parse_design_structure(
            data["analysis_structure"],
            f"{path}.analysis_structure",
        ),
        block_favorable_prevalences=tuple(
            _sequence(
                data["block_favorable_prevalences"],
                f"{path}.block_favorable_prevalences",
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
        production_ineligibility_reasons=tuple(
            _sequence(
                data["production_ineligibility_reasons"],
                f"{path}.production_ineligibility_reasons",
            )
        ),
        method_results=tuple(
            _parse_method_result(item, f"{path}.method_results[{index}]")
            for index, item in enumerate(
                _sequence(data["method_results"], f"{path}.method_results")
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


def _clinical_outcome_informative_cluster_size_report_from_dict(
    value: Any,
) -> ClinicalOutcomeInformativeClusterSizeReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_informative_cluster_size_report_envelope",
        schema_version=(
            CLINICAL_OUTCOME_INFORMATIVE_CLUSTER_SIZE_REPORT_SCHEMA_VERSION
        ),
        payload_field="report",
    )
    fields = {
        "protocol_id",
        "protocol_fingerprint",
        "stress_protocol_id",
        "stress_protocol_fingerprint",
        "method_id",
        "rng_method_id",
        "replicates",
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
        "automatic_estimand_selection_included",
        "delete_mj_estimand_correction_claimed",
        "dominant_cluster_override_allowed",
        "fixed_block_profiles_across_replicates",
        "cluster_superpopulation_resampling_included",
        "identification_and_sampling_uncertainty_separated",
        "limitations",
    }
    data = _record(payload, "report", fields)
    excluded = {
        "methods",
        "log_imor_grid",
        "primary_metric",
        "scenario_results",
        "limitations",
    }
    report = ClinicalOutcomeInformativeClusterSizeReport(
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
    _check_integrity(report, integrity, "informative-cluster-size report")
    return report


def clinical_outcome_informative_cluster_size_report_from_dict(
    value: Any,
) -> ClinicalOutcomeInformativeClusterSizeReport:
    try:
        return _clinical_outcome_informative_cluster_size_report_from_dict(value)
    except RecordParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RecordParseError(
            "informative-cluster-size report violates its semantic contract"
        ) from exc


def clinical_outcome_informative_cluster_size_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    return clinical_outcome_informative_cluster_size_protocol_from_dict(
        _strict_json(payload, "informative-cluster-size protocol")
    )


def clinical_outcome_informative_cluster_size_report_from_json(
    payload: str,
) -> ClinicalOutcomeInformativeClusterSizeReport:
    return clinical_outcome_informative_cluster_size_report_from_dict(
        _strict_json(payload, "informative-cluster-size report")
    )
