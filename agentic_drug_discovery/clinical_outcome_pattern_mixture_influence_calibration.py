"""Unequal-cluster influence calibration for pattern-mixture intervals."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from statistics import NormalDist
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
    ClinicalOutcomePatternMixtureMetricPerformance,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomePatternMixtureReport,
    _true_log_imor,
    analyze_clinical_outcome_pattern_mixture,
)
from .clinical_outcome_pattern_mixture_uncertainty import (
    _full_metric_estimates,
    _leave_one_out_metric_estimates,
    _mc_mean_bounds,
    _mc_nonnegative_mean_bounds,
    _model_functional_truths,
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


CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-influence-calibration-protocol.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-influence-calibration-report.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-influence-calibration-summary.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_METHOD_ID = (
    "adds.pattern-mixture.unequal-cluster-influence-calibration.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_WEBB_MULTIPLIER_ID = (
    "adds.delete-mj.webb-six-point-variance-matched.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_QUANTILE_METHOD_ID = "adds.linear-interpolation-r7.v1"


class ClinicalOutcomePatternMixtureInfluenceError(ValueError):
    """Raised when unequal-cluster calibration cannot run safely."""


class ClinicalOutcomePatternMixtureIntervalMethod(str, Enum):
    DELETE_ONE_NORMAL = "delete_one_normal"
    DELETE_ONE_STUDENT_T = "delete_one_student_t"
    DELETE_MJ_STUDENT_T = "delete_mj_student_t"
    DELETE_MJ_WEBB_MULTIPLIER = "delete_mj_webb_multiplier"


class ClinicalOutcomePatternMixtureInfluenceStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_SIMULATION_CLUSTERS = "insufficient_simulation_clusters"
    EMPTY_REFERENCE_STRATUM = "empty_reference_stratum"
    DEGENERATE_REFERENCE_STRATUM = "degenerate_reference_stratum"
    LEAVE_ONE_OUT_EMPTY_REFERENCE_STRATUM = "leave_one_out_empty_reference_stratum"
    LEAVE_ONE_OUT_DEGENERATE_REFERENCE_STRATUM = (
        "leave_one_out_degenerate_reference_stratum"
    )
    ZERO_RESAMPLING_VARIANCE = "zero_resampling_variance"
    INVALID_MULTIPLIER_DISPERSION = "invalid_multiplier_dispersion"


_METHOD_ORDER = tuple(ClinicalOutcomePatternMixtureIntervalMethod)
_STATUS_ORDER = tuple(ClinicalOutcomePatternMixtureInfluenceStatus)
_WEBB_SIX_POINT_WEIGHTS = (
    -math.sqrt(1.5),
    -1.0,
    -math.sqrt(0.5),
    math.sqrt(0.5),
    1.0,
    math.sqrt(1.5),
)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic unequal-cluster calibration study and contains no real "
        "clinical outcomes, dependence manifest, or deployed policy result."
    ),
    (
        "Every interval remains conditional on one fixed binary log-IMOR model functional; "
        "sampling and missing-data identification uncertainty are not combined."
    ),
    (
        "The delete-mj method is a group-size pseudovalue jackknife for independent unequal "
        "groups; it is not the inverse-variance weighted condition-mean estimator."
    ),
    (
        "The Webb calculation is a variance-matched one-step multiplier over delete-mj "
        "pseudovalue influence contributions, not a regression residual wild-cluster bootstrap."
    ),
    (
        "Multiplier intervals are experimental, use a finite preregistered draw count, and are "
        "excluded from operational method recommendations and pass gates."
    ),
    (
        "Student-t critical values use analysis-cluster degrees of freedom G minus one and do "
        "not establish exact finite-sample coverage for the nonlinear estimator."
    ),
    (
        "Stress-only intervals are still computed for production-ineligible dominant clusters "
        "solely to diagnose failure; no method may override the dominance hard stop."
    ),
    (
        "Cluster-size adjustment cannot repair incorrect dependence blocks, informative cluster "
        "inclusion, non-nested dependence, cluster loss, or outcome adjudication error."
    ),
    (
        "Monte Carlo bounds quantify finite simulation error and do not validate one future "
        "clinical board, endpoint family, safety definition, or elicited log-IMOR range."
    ),
    (
        "Passing synthetic targets does not establish efficacy, safety, benefit-risk, policy "
        "superiority, transportability, treatment utility, or regulatory acceptability."
    ),
)


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    _require_positive_int(degrees_of_freedom, "degrees_of_freedom")
    if math.isnan(value):
        raise ValueError("Student-t argument must not be NaN")
    if not math.isfinite(value):
        return 0.0 if value < 0.0 else 1.0
    if value == 0.0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    beta = _regularized_incomplete_beta(
        degrees_of_freedom / 2.0,
        0.5,
        x,
    )
    return 1.0 - 0.5 * beta if value > 0.0 else 0.5 * beta


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 300
    epsilon = 3.0e-14
    floor = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < floor:
        d = floor
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        doubled = 2 * iteration
        numerator = iteration * (b - iteration) * x / ((qam + doubled) * (a + doubled))
        d = 1.0 + numerator * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + numerator / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        result *= d * c
        numerator = -(
            (a + iteration) * (qab + iteration) * x / ((a + doubled) * (qap + doubled))
        )
        d = 1.0 + numerator * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + numerator / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= epsilon:
            return result
    raise ClinicalOutcomePatternMixtureInfluenceError(
        "Student-t incomplete-beta calculation did not converge"
    )


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if not 0.0 <= x <= 1.0:
        raise ValueError("incomplete-beta argument falls outside [0, 1]")
    if x in (0.0, 1.0):
        return x
    factor = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        result = factor * _beta_continued_fraction(a, b, x) / a
    else:
        result = 1.0 - factor * _beta_continued_fraction(b, a, 1.0 - x) / b
    return min(1.0, max(0.0, result))


def _student_t_critical(confidence_level: float, degrees_of_freedom: int) -> float:
    _require_probability(confidence_level, "confidence_level")
    if not 0.5 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0.5 and 1")
    _require_positive_int(degrees_of_freedom, "degrees_of_freedom")
    target = 0.5 + confidence_level / 2.0
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < target:
        upper *= 2.0
        if upper > 1_000_000.0:
            raise ClinicalOutcomePatternMixtureInfluenceError(
                "Student-t critical-value search did not bracket the target"
            )
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, degrees_of_freedom) < target:
            lower = midpoint
        else:
            upper = midpoint
    return _round_metric((lower + upper) / 2.0)


def _linear_quantile(values: Sequence[float], probability: float) -> float:
    _require_probability(probability, "probability")
    resolved = tuple(values)
    for index, value in enumerate(resolved):
        _require_finite(value, f"quantile values[{index}]")
    ordered = tuple(sorted(resolved))
    if not ordered:
        raise ValueError("quantile values cannot be empty")
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + fraction * (
        ordered[upper_index] - ordered[lower_index]
    )


def _delete_one_variance(values: Sequence[float]) -> float:
    resolved = tuple(values)
    if len(resolved) < 2:
        raise ValueError("delete-one variance requires at least two replicates")
    for index, value in enumerate(resolved):
        _require_finite(value, f"delete-one values[{index}]")
    mean = sum(resolved) / len(resolved)
    return max(
        0.0,
        (len(resolved) - 1)
        / len(resolved)
        * sum((value - mean) ** 2 for value in resolved),
    )


def _delete_mj_estimate_and_variance(
    full_estimate: float,
    leave_one_out_estimates: Sequence[float],
    cluster_sizes: Sequence[int],
) -> tuple[float, float, tuple[float, ...], tuple[float, ...]]:
    leaveout = tuple(leave_one_out_estimates)
    sizes = tuple(cluster_sizes)
    if len(leaveout) != len(sizes) or len(sizes) < 2:
        raise ValueError("delete-mj inputs require matched independent clusters")
    _require_finite(full_estimate, "full_estimate")
    for index, value in enumerate(leaveout):
        _require_finite(value, f"leave_one_out_estimates[{index}]")
    for index, size in enumerate(sizes):
        _require_positive_int(size, f"cluster_sizes[{index}]")
    total_units = sum(sizes)
    if total_units <= max(sizes):
        raise ValueError("delete-mj requires units outside every deleted cluster")
    h_values = tuple(total_units / size for size in sizes)
    pseudovalues = tuple(
        h_value * full_estimate - (h_value - 1.0) * leaveout_estimate
        for h_value, leaveout_estimate in zip(
            h_values,
            leaveout,
            strict=True,
        )
    )
    estimate = sum(
        size / total_units * pseudovalue
        for size, pseudovalue in zip(sizes, pseudovalues, strict=True)
    )
    variance = sum(
        (pseudovalue - estimate) ** 2 / (h_value - 1.0)
        for pseudovalue, h_value in zip(pseudovalues, h_values, strict=True)
    ) / len(sizes)
    contributions = tuple(
        size / total_units * (pseudovalue - estimate)
        for size, pseudovalue in zip(sizes, pseudovalues, strict=True)
    )
    return estimate, max(0.0, variance), pseudovalues, contributions


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    stress_protocol_fingerprint: str
    pattern_mixture_protocol_fingerprint: str
    pattern_mixture_report_fingerprint: str
    methods: tuple[ClinicalOutcomePatternMixtureIntervalMethod, ...]
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_tolerance: float
    minimum_interval_yield: float
    minimum_production_clusters: int
    maximum_production_cluster_unit_fraction: float
    maximum_standard_error_calibration_deviation: float
    multiplier_draws: int
    multiplier_seed: int
    primary_metric: ClinicalOutcomeDesignMetric
    method_id: str = CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_METHOD_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        for field_name in (
            "stress_protocol_fingerprint",
            "pattern_mixture_protocol_fingerprint",
            "pattern_mixture_report_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        if methods != _METHOD_ORDER:
            raise ValueError("methods must exactly cover canonical influence methods")
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
                "maximum_production_cluster_unit_fraction must be strictly between zero and one"
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
        _require_positive_int(self.multiplier_draws, "multiplier_draws")
        if not 99 <= self.multiplier_draws <= 9_999:
            raise ValueError("multiplier_draws must be between 99 and 9999")
        if self.multiplier_draws % 2 == 0:
            raise ValueError("multiplier_draws must be odd")
        if isinstance(self.multiplier_seed, bool) or not isinstance(
            self.multiplier_seed, int
        ):
            raise TypeError("multiplier_seed must be an integer")
        if not 0 <= self.multiplier_seed <= 2**63 - 1:
            raise ValueError("multiplier_seed falls outside the supported range")
        _require_instance(
            self.primary_metric,
            ClinicalOutcomeDesignMetric,
            "primary_metric",
        )
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError(
                "influence protocol metadata cannot contain evaluator outcomes"
            )
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
class ClinicalOutcomePatternMixtureInfluenceStatusCount(SerializableRecord):
    status: ClinicalOutcomePatternMixtureInfluenceStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(
            self.status,
            ClinicalOutcomePatternMixtureInfluenceStatus,
            "status",
        )
        _require_non_negative_int(self.count, "count")


def _status_count_records(
    counts: Mapping[ClinicalOutcomePatternMixtureInfluenceStatus, int],
) -> tuple[ClinicalOutcomePatternMixtureInfluenceStatusCount, ...]:
    return tuple(
        ClinicalOutcomePatternMixtureInfluenceStatusCount(
            status=status,
            count=counts.get(status, 0),
        )
        for status in _STATUS_ORDER
    )


def _validated_status_counts(
    values: Sequence[ClinicalOutcomePatternMixtureInfluenceStatusCount],
    replicate_count: int,
) -> dict[ClinicalOutcomePatternMixtureInfluenceStatus, int]:
    resolved = _tuple(values, "status_counts")
    for item in resolved:
        _require_instance(
            item,
            ClinicalOutcomePatternMixtureInfluenceStatusCount,
            "status count",
        )
    if tuple(item.status for item in resolved) != _STATUS_ORDER:
        raise ValueError("status_counts must exactly cover canonical statuses")
    if sum(item.count for item in resolved) != replicate_count:
        raise ValueError("status counts do not sum to replicate_count")
    return {item.status: item.count for item in resolved}


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceCell(SerializableRecord):
    method: ClinicalOutcomePatternMixtureIntervalMethod
    metric: ClinicalOutcomeDesignMetric
    log_imor: float
    informative_missingness_odds_ratio: float
    model_functional_true_value: float
    replicate_count: int
    point_estimate_count: int
    interval_count: int
    covered_count: int
    interval_yield: ClinicalOutcomeDesignRate
    model_functional_coverage: ClinicalOutcomeDesignRate
    prior_pattern_mixture_mean_estimate: float | None
    mean_estimate: float | None
    mean_minus_prior_pattern_mixture: float | None
    model_functional_bias: float | None
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
    status_counts: tuple[ClinicalOutcomePatternMixtureInfluenceStatusCount, ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.method,
            ClinicalOutcomePatternMixtureIntervalMethod,
            "method",
        )
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        metric_lower, metric_upper = _metric_bounds(self.metric)
        _require_finite(self.log_imor, "log_imor")
        _require_finite(
            self.informative_missingness_odds_ratio,
            "informative_missingness_odds_ratio",
            minimum=0.0,
        )
        if self.informative_missingness_odds_ratio != _round_metric(
            math.exp(self.log_imor)
        ):
            raise ValueError("informative missingness odds ratio is inconsistent")
        _require_finite(
            self.model_functional_true_value,
            "model_functional_true_value",
            minimum=metric_lower,
            maximum=metric_upper,
        )
        _require_positive_int(self.replicate_count, "replicate_count")
        for field_name in (
            "point_estimate_count",
            "interval_count",
            "covered_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if not (
            self.covered_count
            <= self.interval_count
            <= self.point_estimate_count
            <= self.replicate_count
        ):
            raise ValueError("cell counts are inconsistent")
        for rate, field_name in (
            (self.interval_yield, "interval_yield"),
            (self.model_functional_coverage, "model_functional_coverage"),
        ):
            _require_instance(rate, ClinicalOutcomeDesignRate, field_name)
        if (
            self.interval_yield.event_count != self.interval_count
            or self.interval_yield.total_count != self.replicate_count
        ):
            raise ValueError("interval-yield denominator is inconsistent")
        if (
            self.model_functional_coverage.event_count != self.covered_count
            or self.model_functional_coverage.total_count != self.interval_count
            or self.model_functional_coverage.confidence_level
            != self.interval_yield.confidence_level
        ):
            raise ValueError("coverage denominator is inconsistent")
        for field_name in (
            "prior_pattern_mixture_mean_estimate",
            "mean_estimate",
            "mean_minus_prior_pattern_mixture",
            "model_functional_bias",
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
        ):
            minimum = (
                0.0
                if field_name
                in {
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
                else None
            )
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=minimum,
            )
        for field_name in ("prior_pattern_mixture_mean_estimate", "mean_estimate"):
            value = getattr(self, field_name)
            if value is not None and not metric_lower <= value <= metric_upper:
                raise ValueError(f"{field_name} falls outside the metric scale")
        if self.point_estimate_count == 0:
            point_fields = (
                self.prior_pattern_mixture_mean_estimate,
                self.mean_estimate,
                self.mean_minus_prior_pattern_mixture,
                self.model_functional_bias,
                self.empirical_standard_deviation,
                self.monte_carlo_bias_lower,
                self.monte_carlo_bias_upper,
                self.monte_carlo_absolute_bias_upper,
            )
            if any(value is not None for value in point_fields):
                raise ValueError("empty point estimates require null point summaries")
        else:
            if (
                self.mean_estimate is None
                or self.prior_pattern_mixture_mean_estimate is None
            ):
                raise ValueError(
                    "point estimates require synchronized prior and current means"
                )
            expected_prior_difference = _round_metric(
                self.mean_estimate - self.prior_pattern_mixture_mean_estimate
            )
            if self.mean_minus_prior_pattern_mixture != expected_prior_difference:
                raise ValueError("point-report mean difference is inconsistent")
            if (
                self.method
                in {
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
                }
                and self.mean_estimate != self.prior_pattern_mixture_mean_estimate
            ):
                raise ValueError(
                    "delete-one full-estimator mean changed from point report"
                )
            expected_bias = _round_metric(
                self.mean_estimate - self.model_functional_true_value
            )
            if self.model_functional_bias != expected_bias:
                raise ValueError("model-functional bias is inconsistent")
            if self.point_estimate_count == 1:
                if self.empirical_standard_deviation is not None:
                    raise ValueError(
                        "one point estimate requires null empirical deviation"
                    )
            elif self.empirical_standard_deviation is None:
                raise ValueError("multiple point estimates require empirical deviation")
            expected_bias_bounds = _mc_mean_bounds(
                self.model_functional_bias,
                self.empirical_standard_deviation,
                self.point_estimate_count,
                self.interval_yield.confidence_level,
            )
            if (
                self.monte_carlo_bias_lower,
                self.monte_carlo_bias_upper,
            ) != expected_bias_bounds:
                raise ValueError("Monte Carlo bias bounds are inconsistent")
            expected_absolute_bias = (
                None
                if expected_bias_bounds[0] is None
                else _round_metric(
                    max(abs(expected_bias_bounds[0]), abs(expected_bias_bounds[1]))
                )
            )
            if self.monte_carlo_absolute_bias_upper != expected_absolute_bias:
                raise ValueError("Monte Carlo absolute-bias bound is inconsistent")
        counts = _validated_status_counts(self.status_counts, self.replicate_count)
        object.__setattr__(
            self, "status_counts", _tuple(self.status_counts, "status_counts")
        )
        if (
            counts[ClinicalOutcomePatternMixtureInfluenceStatus.COMPUTED]
            != self.interval_count
        ):
            raise ValueError("computed status count is inconsistent")
        if self.interval_count == 0:
            interval_fields = (
                self.root_mean_squared_reported_standard_error,
                self.mean_reported_standard_error,
                self.mean_interval_width,
                self.interval_width_empirical_standard_deviation,
                self.mean_interval_width_monte_carlo_lower,
                self.mean_interval_width_monte_carlo_upper,
                self.standard_error_to_empirical_sd_ratio,
            )
            if any(value is not None for value in interval_fields):
                raise ValueError("empty intervals require null interval summaries")
        else:
            if any(
                value is None
                for value in (
                    self.root_mean_squared_reported_standard_error,
                    self.mean_reported_standard_error,
                    self.mean_interval_width,
                )
            ):
                raise ValueError("computed intervals require uncertainty summaries")
            if self.interval_count == 1:
                if self.interval_width_empirical_standard_deviation is not None:
                    raise ValueError("one interval requires null width deviation")
            elif self.interval_width_empirical_standard_deviation is None:
                raise ValueError("multiple intervals require width deviation")
            expected_width_bounds = _mc_nonnegative_mean_bounds(
                self.mean_interval_width,
                self.interval_width_empirical_standard_deviation,
                self.interval_count,
                self.interval_yield.confidence_level,
            )
            if (
                self.mean_interval_width_monte_carlo_lower,
                self.mean_interval_width_monte_carlo_upper,
            ) != expected_width_bounds:
                raise ValueError("Monte Carlo width bounds are inconsistent")
        expected_se_ratio = (
            None
            if self.root_mean_squared_reported_standard_error is None
            or self.empirical_standard_deviation in (None, 0.0)
            else _round_metric(
                self.root_mean_squared_reported_standard_error
                / self.empirical_standard_deviation
            )
        )
        if self.standard_error_to_empirical_sd_ratio != expected_se_ratio:
            raise ValueError("standard-error calibration ratio is inconsistent")
        for field_name in (
            "maximum_absolute_bias",
            "coverage_target",
            "minimum_interval_yield",
            "standard_error_calibration_lower",
            "standard_error_calibration_upper",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        if (
            self.standard_error_calibration_lower
            > self.standard_error_calibration_upper
        ):
            raise ValueError("standard-error calibration bounds are inconsistent")
        for field_name in (
            "bias_target_met",
            "interval_yield_target_met",
            "coverage_target_met",
            "standard_error_calibration_target_met",
            "calibration_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        expected_bias_met = (
            self.monte_carlo_absolute_bias_upper is not None
            and self.monte_carlo_absolute_bias_upper <= self.maximum_absolute_bias
        )
        expected_yield_met = (
            self.interval_yield.lower is not None
            and self.interval_yield.lower >= self.minimum_interval_yield
        )
        expected_coverage_met = (
            self.model_functional_coverage.lower is not None
            and self.model_functional_coverage.lower >= self.coverage_target
        )
        expected_se_met = (
            self.standard_error_to_empirical_sd_ratio is not None
            and self.standard_error_calibration_lower
            <= self.standard_error_to_empirical_sd_ratio
            <= self.standard_error_calibration_upper
        )
        if (
            self.bias_target_met != expected_bias_met
            or self.interval_yield_target_met != expected_yield_met
            or self.coverage_target_met != expected_coverage_met
            or self.standard_error_calibration_target_met != expected_se_met
        ):
            raise ValueError("cell target flag is inconsistent")
        if self.calibration_target_met != (
            expected_bias_met
            and expected_yield_met
            and expected_coverage_met
            and expected_se_met
        ):
            raise ValueError("cell calibration target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceMetric(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    grid_inference: tuple[ClinicalOutcomePatternMixtureInfluenceCell, ...]
    all_grid_calibration_targets_met: bool

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        grid = _tuple(self.grid_inference, "grid_inference")
        object.__setattr__(self, "grid_inference", grid)
        if not grid:
            raise ValueError("grid_inference cannot be empty")
        for item in grid:
            _require_instance(
                item,
                ClinicalOutcomePatternMixtureInfluenceCell,
                "grid inference item",
            )
        if any(item.metric is not self.metric for item in grid):
            raise ValueError("grid metric is inconsistent")
        if len({item.log_imor for item in grid}) != len(grid):
            raise ValueError("grid inference cannot contain duplicate log-IMOR values")
        if tuple(item.log_imor for item in grid) != tuple(
            sorted(item.log_imor for item in grid)
        ):
            raise ValueError("grid inference must use increasing log-IMOR order")
        methods = {item.method for item in grid}
        if len(methods) != 1:
            raise ValueError("metric inference cannot mix interval methods")
        _require_bool(
            self.all_grid_calibration_targets_met,
            "all_grid_calibration_targets_met",
        )
        if self.all_grid_calibration_targets_met != all(
            item.calibration_target_met for item in grid
        ):
            raise ValueError("all-grid calibration flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceMethodResult(SerializableRecord):
    method: ClinicalOutcomePatternMixtureIntervalMethod
    metric_inference: tuple[ClinicalOutcomePatternMixtureInfluenceMetric, ...]
    all_metric_calibration_targets_met: bool
    operational_candidate: bool
    experimental_only: bool

    def __post_init__(self) -> None:
        _require_instance(
            self.method,
            ClinicalOutcomePatternMixtureIntervalMethod,
            "method",
        )
        metrics = _tuple(self.metric_inference, "metric_inference")
        object.__setattr__(self, "metric_inference", metrics)
        for item in metrics:
            _require_instance(
                item,
                ClinicalOutcomePatternMixtureInfluenceMetric,
                "metric inference item",
            )
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("metric_inference must exactly cover canonical metrics")
        if any(
            cell.method is not self.method
            for metric in metrics
            for cell in metric.grid_inference
        ):
            raise ValueError("nested interval method is inconsistent")
        for field_name in (
            "all_metric_calibration_targets_met",
            "operational_candidate",
            "experimental_only",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if self.all_metric_calibration_targets_met != all(
            item.all_grid_calibration_targets_met for item in metrics
        ):
            raise ValueError("all-metric calibration flag is inconsistent")
        expected_experimental = (
            self.method
            is ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER
        )
        if self.experimental_only != expected_experimental:
            raise ValueError("experimental method flag is inconsistent")
        expected_candidate = self.method in {
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
        }
        if self.operational_candidate != expected_candidate:
            raise ValueError("operational candidate flag is inconsistent")


def _method_result(
    values: Sequence[ClinicalOutcomePatternMixtureInfluenceMethodResult],
    method: ClinicalOutcomePatternMixtureIntervalMethod,
) -> ClinicalOutcomePatternMixtureInfluenceMethodResult:
    return next(item for item in values if item.method is method)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceScenarioResult(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    true_log_imor: float
    analysis_structure: ClinicalOutcomeDesignStructure
    equal_cluster_sizes: bool
    production_eligible: bool
    production_ineligibility_reasons: tuple[str, ...]
    method_results: tuple[ClinicalOutcomePatternMixtureInfluenceMethodResult, ...]
    student_t_coverage_noninferior_to_normal_all_cells: bool
    equal_size_delete_mj_standard_error_equivalence_expected: bool
    equal_size_delete_mj_standard_error_equivalence_met: bool
    student_t_candidate_target_met: bool
    delete_mj_sensitivity_target_met: bool
    webb_experimental_target_met: bool
    dominant_cluster_hard_stop_preserved: bool
    research_target_met: bool
    rng_stream_sha256: str
    outcome_rng_stream_sha256: str
    evaluability_rng_stream_sha256: str
    multiplier_rng_stream_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        _require_finite(self.true_log_imor, "true_log_imor")
        _require_instance(
            self.analysis_structure,
            ClinicalOutcomeDesignStructure,
            "analysis_structure",
        )
        for field_name in (
            "equal_cluster_sizes",
            "production_eligible",
            "student_t_coverage_noninferior_to_normal_all_cells",
            "equal_size_delete_mj_standard_error_equivalence_expected",
            "equal_size_delete_mj_standard_error_equivalence_met",
            "student_t_candidate_target_met",
            "delete_mj_sensitivity_target_met",
            "webb_experimental_target_met",
            "dominant_cluster_hard_stop_preserved",
            "research_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        expected_equal = (
            self.analysis_structure.minimum_cluster_size
            == self.analysis_structure.maximum_cluster_size
        )
        if self.equal_cluster_sizes != expected_equal:
            raise ValueError("equal-cluster-size flag is inconsistent")
        reasons = _tuple(
            self.production_ineligibility_reasons,
            "production_ineligibility_reasons",
        )
        object.__setattr__(self, "production_ineligibility_reasons", reasons)
        allowed_reasons = ("insufficient_clusters", "dominant_cluster")
        if any(reason not in allowed_reasons for reason in reasons):
            raise ValueError("production ineligibility reason is unsupported")
        if reasons != tuple(reason for reason in allowed_reasons if reason in reasons):
            raise ValueError("production ineligibility reasons are not canonical")
        if self.production_eligible != (not reasons):
            raise ValueError("production eligibility is inconsistent")
        methods = _tuple(self.method_results, "method_results")
        object.__setattr__(self, "method_results", methods)
        for item in methods:
            _require_instance(
                item,
                ClinicalOutcomePatternMixtureInfluenceMethodResult,
                "method result item",
            )
        if tuple(item.method for item in methods) != _METHOD_ORDER:
            raise ValueError("method_results must exactly cover canonical methods")
        baseline = _method_result(
            methods,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
        )
        student_t = _method_result(
            methods,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
        )
        delete_mj = _method_result(
            methods,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
        )
        webb = _method_result(
            methods,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER,
        )
        noninferior = True
        se_equivalent = True
        for metric_index in range(len(_METRIC_ORDER)):
            baseline_metric = baseline.metric_inference[metric_index]
            student_metric = student_t.metric_inference[metric_index]
            delete_mj_metric = delete_mj.metric_inference[metric_index]
            for grid_index in range(len(baseline_metric.grid_inference)):
                baseline_cell = baseline_metric.grid_inference[grid_index]
                student_cell = student_metric.grid_inference[grid_index]
                delete_mj_cell = delete_mj_metric.grid_inference[grid_index]
                if (
                    baseline_cell.log_imor != student_cell.log_imor
                    or baseline_cell.log_imor != delete_mj_cell.log_imor
                ):
                    raise ValueError("cross-method grid changed")
                if (
                    baseline_cell.point_estimate_count
                    != student_cell.point_estimate_count
                    or baseline_cell.interval_count != student_cell.interval_count
                    or baseline_cell.mean_estimate != student_cell.mean_estimate
                    or baseline_cell.root_mean_squared_reported_standard_error
                    != student_cell.root_mean_squared_reported_standard_error
                    or baseline_cell.mean_reported_standard_error
                    != student_cell.mean_reported_standard_error
                ):
                    raise ValueError("Student-t method changed delete-one estimates")
                noninferior = noninferior and (
                    student_cell.covered_count >= baseline_cell.covered_count
                )
                se_equivalent = se_equivalent and (
                    student_cell.interval_count == delete_mj_cell.interval_count
                    and student_cell.root_mean_squared_reported_standard_error
                    == delete_mj_cell.root_mean_squared_reported_standard_error
                    and student_cell.mean_reported_standard_error
                    == delete_mj_cell.mean_reported_standard_error
                )
        if self.student_t_coverage_noninferior_to_normal_all_cells != noninferior:
            raise ValueError("Student-t coverage comparison is inconsistent")
        if (
            self.equal_size_delete_mj_standard_error_equivalence_expected
            != expected_equal
        ):
            raise ValueError("equal-size equivalence expectation is inconsistent")
        expected_equivalence_met = se_equivalent if expected_equal else False
        if (
            self.equal_size_delete_mj_standard_error_equivalence_met
            != expected_equivalence_met
        ):
            raise ValueError("equal-size standard-error equivalence is inconsistent")
        if self.student_t_candidate_target_met != (
            student_t.all_metric_calibration_targets_met and noninferior
        ):
            raise ValueError("Student-t candidate target is inconsistent")
        if self.delete_mj_sensitivity_target_met != (
            delete_mj.all_metric_calibration_targets_met
            and (not expected_equal or expected_equivalence_met)
        ):
            raise ValueError("delete-mj sensitivity target is inconsistent")
        if self.webb_experimental_target_met != webb.all_metric_calibration_targets_met:
            raise ValueError("Webb experimental target is inconsistent")
        dominant = "dominant_cluster" in reasons
        if self.dominant_cluster_hard_stop_preserved != (
            not dominant or not self.production_eligible
        ):
            raise ValueError("dominant-cluster hard stop is inconsistent")
        expected_research_target = (
            self.student_t_candidate_target_met
            and self.delete_mj_sensitivity_target_met
            and (not expected_equal or expected_equivalence_met)
            if self.production_eligible
            else self.dominant_cluster_hard_stop_preserved
        )
        if self.research_target_met != expected_research_target:
            raise ValueError("scenario research target is inconsistent")
        for field_name in (
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
            "multiplier_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureInfluenceReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    stress_protocol_id: str
    stress_protocol_fingerprint: str
    stress_report_fingerprint: str
    pattern_mixture_protocol_id: str
    pattern_mixture_protocol_fingerprint: str
    pattern_mixture_report_fingerprint: str
    method_id: str
    rng_method_id: str
    multiplier_method_id: str
    quantile_method_id: str
    replicates: int
    log_imor_grid: tuple[float, ...]
    methods: tuple[ClinicalOutcomePatternMixtureIntervalMethod, ...]
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_target: float
    minimum_interval_yield: float
    minimum_production_clusters: int
    maximum_production_cluster_unit_fraction: float
    maximum_absolute_bias: float
    standard_error_calibration_lower: float
    standard_error_calibration_upper: float
    multiplier_draws: int
    multiplier_seed: int
    primary_metric: ClinicalOutcomeDesignMetric
    scenario_results: tuple[ClinicalOutcomePatternMixtureInfluenceScenarioResult, ...]
    aggregate_simulation_only: bool = True
    replicate_level_records_included: bool = False
    cluster_level_records_included: bool = False
    unit_level_records_included: bool = False
    real_clinical_outcomes_included: bool = False
    stress_only_ineligible_intervals_operational: bool = False
    dominant_cluster_override_allowed: bool = False
    automatic_method_selection_included: bool = False
    regression_wild_cluster_bootstrap_claimed: bool = False
    multiplier_method_experimental_only: bool = True
    identification_and_sampling_uncertainty_separated: bool = True
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in (
            "protocol_id",
            "stress_protocol_id",
            "pattern_mixture_protocol_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "stress_protocol_fingerprint",
            "stress_report_fingerprint",
            "pattern_mixture_protocol_fingerprint",
            "pattern_mixture_report_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        if (
            self.multiplier_method_id
            != CLINICAL_OUTCOME_PATTERN_MIXTURE_WEBB_MULTIPLIER_ID
        ):
            raise ValueError("multiplier_method_id is unsupported")
        if (
            self.quantile_method_id
            != CLINICAL_OUTCOME_PATTERN_MIXTURE_QUANTILE_METHOD_ID
        ):
            raise ValueError("quantile_method_id is unsupported")
        _require_positive_int(self.replicates, "replicates")
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        for item in grid:
            _require_finite(item, "log_imor_grid item")
        if not grid or grid != tuple(sorted(set(grid))):
            raise ValueError("log_imor_grid must be unique and increasing")
        methods = _tuple(self.methods, "methods")
        object.__setattr__(self, "methods", methods)
        if methods != _METHOD_ORDER:
            raise ValueError("methods changed")
        for field_name in (
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_target",
            "minimum_interval_yield",
            "maximum_production_cluster_unit_fraction",
        ):
            _require_probability(getattr(self, field_name), field_name)
        if not 0.5 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError("monte_carlo_confidence_level must be between 0.5 and 1")
        if self.coverage_target > self.confidence_level:
            raise ValueError("coverage_target cannot exceed confidence_level")
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be positive")
        _require_positive_int(
            self.minimum_production_clusters,
            "minimum_production_clusters",
        )
        if self.minimum_production_clusters < 3:
            raise ValueError("minimum_production_clusters must be at least three")
        if self.maximum_production_cluster_unit_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_production_cluster_unit_fraction must be strictly between zero and one"
            )
        _require_finite(
            self.maximum_absolute_bias, "maximum_absolute_bias", minimum=0.0
        )
        for field_name in (
            "standard_error_calibration_lower",
            "standard_error_calibration_upper",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        if (
            self.standard_error_calibration_lower
            > self.standard_error_calibration_upper
        ):
            raise ValueError("standard-error calibration bounds are inconsistent")
        if not (
            self.standard_error_calibration_lower
            < 1.0
            < self.standard_error_calibration_upper
            and _round_metric(
                self.standard_error_calibration_lower
                + self.standard_error_calibration_upper
            )
            == 2.0
        ):
            raise ValueError(
                "standard-error calibration bounds must be symmetric around one"
            )
        _require_positive_int(self.multiplier_draws, "multiplier_draws")
        if not 99 <= self.multiplier_draws <= 9_999:
            raise ValueError("multiplier_draws must be between 99 and 9999")
        if self.multiplier_draws % 2 == 0:
            raise ValueError("multiplier_draws must be odd")
        if isinstance(self.multiplier_seed, bool) or not isinstance(
            self.multiplier_seed, int
        ):
            raise TypeError("multiplier_seed must be an integer")
        if not 0 <= self.multiplier_seed <= 2**63 - 1:
            raise ValueError("multiplier_seed falls outside the supported range")
        _require_instance(
            self.primary_metric, ClinicalOutcomeDesignMetric, "primary_metric"
        )
        scenarios = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", scenarios)
        if not scenarios:
            raise ValueError("scenario_results cannot be empty")
        for scenario in scenarios:
            _require_instance(
                scenario,
                ClinicalOutcomePatternMixtureInfluenceScenarioResult,
                "scenario result item",
            )
        if tuple(item.scenario_id for item in scenarios) != tuple(
            sorted(item.scenario_id for item in scenarios)
        ):
            raise ValueError("scenario_results must use canonical order")
        for scenario in scenarios:
            expected_reasons: list[str] = []
            if (
                scenario.analysis_structure.cluster_count
                < self.minimum_production_clusters
            ):
                expected_reasons.append("insufficient_clusters")
            if (
                scenario.analysis_structure.maximum_cluster_fraction
                > self.maximum_production_cluster_unit_fraction
            ):
                expected_reasons.append("dominant_cluster")
            if scenario.production_ineligibility_reasons != tuple(expected_reasons):
                raise ValueError(
                    "scenario production eligibility changed from report thresholds"
                )
            for method in scenario.method_results:
                for metric in method.metric_inference:
                    if tuple(item.log_imor for item in metric.grid_inference) != grid:
                        raise ValueError("nested log-IMOR grid changed")
                    for cell in metric.grid_inference:
                        if (
                            cell.replicate_count != self.replicates
                            or cell.interval_yield.confidence_level
                            != self.monte_carlo_confidence_level
                            or cell.maximum_absolute_bias != self.maximum_absolute_bias
                            or cell.coverage_target != self.coverage_target
                            or cell.minimum_interval_yield
                            != self.minimum_interval_yield
                            or cell.standard_error_calibration_lower
                            != self.standard_error_calibration_lower
                            or cell.standard_error_calibration_upper
                            != self.standard_error_calibration_upper
                        ):
                            raise ValueError("nested calibration target changed")
        for field_name in (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "cluster_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "stress_only_ineligible_intervals_operational",
            "dominant_cluster_override_allowed",
            "automatic_method_selection_included",
            "regression_wild_cluster_bootstrap_claimed",
            "multiplier_method_experimental_only",
            "identification_and_sampling_uncertainty_separated",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if (
            not self.aggregate_simulation_only
            or self.replicate_level_records_included
            or self.cluster_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or self.stress_only_ineligible_intervals_operational
            or self.dominant_cluster_override_allowed
            or self.automatic_method_selection_included
            or self.regression_wild_cluster_bootstrap_claimed
            or not self.multiplier_method_experimental_only
            or not self.identification_and_sampling_uncertainty_separated
        ):
            raise ValueError("influence calibration report crossed its claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required influence calibration limitations changed")

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
        self.status_counts: Counter[ClinicalOutcomePatternMixtureInfluenceStatus] = (
            Counter()
        )

    def add_point(self, value: float) -> None:
        self.points.add(value)

    def add_failure(self, status: ClinicalOutcomePatternMixtureInfluenceStatus) -> None:
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
        self.status_counts[ClinicalOutcomePatternMixtureInfluenceStatus.COMPUTED] += 1


def _mapped_support_status(value: Any) -> ClinicalOutcomePatternMixtureInfluenceStatus:
    try:
        return ClinicalOutcomePatternMixtureInfluenceStatus(value.value)
    except (AttributeError, ValueError) as exc:
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "pattern-mixture support status is not recognized"
        ) from exc


def _production_ineligibility_reasons(
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
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


def _prior_metric(
    result: Any,
    metric: ClinicalOutcomeDesignMetric,
) -> ClinicalOutcomePatternMixtureMetricPerformance:
    return next(item for item in result.metric_performance if item.metric is metric)


def _finalize_cell(
    *,
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    method: ClinicalOutcomePatternMixtureIntervalMethod,
    metric: ClinicalOutcomeDesignMetric,
    log_imor: float,
    model_truth: float,
    prior_mean: float | None,
    accumulator: _CellAccumulator,
    replicate_count: int,
) -> ClinicalOutcomePatternMixtureInfluenceCell:
    mean_estimate = accumulator.points.mean()
    empirical_sd = accumulator.points.sample_standard_deviation()
    bias = None if mean_estimate is None else _round_metric(mean_estimate - model_truth)
    bias_bounds = _mc_mean_bounds(
        bias,
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
    synchronized_prior = None if mean_estimate is None else prior_mean
    mean_minus_prior = (
        None
        if mean_estimate is None or synchronized_prior is None
        else _round_metric(mean_estimate - synchronized_prior)
    )
    bias_met = (
        absolute_bias_upper is not None
        and absolute_bias_upper <= pattern_protocol.maximum_absolute_bias
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
    return ClinicalOutcomePatternMixtureInfluenceCell(
        method=method,
        metric=metric,
        log_imor=log_imor,
        informative_missingness_odds_ratio=_round_metric(math.exp(log_imor)),
        model_functional_true_value=model_truth,
        replicate_count=replicate_count,
        point_estimate_count=accumulator.points.count,
        interval_count=interval_count,
        covered_count=accumulator.covered,
        interval_yield=interval_yield,
        model_functional_coverage=coverage,
        prior_pattern_mixture_mean_estimate=synchronized_prior,
        mean_estimate=mean_estimate,
        mean_minus_prior_pattern_mixture=mean_minus_prior,
        model_functional_bias=bias,
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
        maximum_absolute_bias=pattern_protocol.maximum_absolute_bias,
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


def _add_interval(
    accumulator: _CellAccumulator,
    *,
    metric: ClinicalOutcomeDesignMetric,
    point_estimate: float,
    standard_error: float,
    lower_offset: float,
    upper_offset: float,
    model_truth: float,
) -> None:
    lower_bound, upper_bound = _metric_bounds(metric)
    interval_lower = max(lower_bound, point_estimate + lower_offset)
    interval_upper = min(upper_bound, point_estimate + upper_offset)
    accumulator.add_interval(
        standard_error=standard_error,
        width=interval_upper - interval_lower,
        covered=(interval_lower - 1e-12 <= model_truth <= interval_upper + 1e-12),
    )


def _webb_weight_rows(
    multiplier_stream_sha256: str,
    replicate_index: int,
    draw_count: int,
    cluster_count: int,
) -> tuple[tuple[float, ...], ...]:
    replicate_stream = _substream_sha256(
        multiplier_stream_sha256,
        f"replicate:{replicate_index}",
    )
    rng = random.Random(int(replicate_stream, 16))
    return tuple(
        tuple(rng.choice(_WEBB_SIX_POINT_WEIGHTS) for _ in range(cluster_count))
        for _ in range(draw_count)
    )


def _simulate_scenario(
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    pattern_report: ClinicalOutcomePatternMixtureReport,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
) -> ClinicalOutcomePatternMixtureInfluenceScenarioResult:
    layout = _scenario_layout(scenario)
    mode = ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    structure = layout.structure_by_mode[mode]
    cluster_sizes = tuple(sum(row) for row in layout.group_stratum_totals_by_mode[mode])
    model_truths, _ = _model_functional_truths(
        scenario,
        layout,
        pattern_protocol.log_imor_grid,
    )
    accumulators = {
        method: {
            metric: {
                log_imor: _CellAccumulator()
                for log_imor in pattern_protocol.log_imor_grid
            }
            for metric in _METRIC_ORDER
        }
        for method in protocol.methods
    }
    stream_sha256 = _scenario_stream_sha256(stress_protocol, scenario)
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(stream_sha256, "evaluability")
    multiplier_stream_sha256 = _substream_sha256(
        stream_sha256,
        (
            f"{CLINICAL_OUTCOME_PATTERN_MIXTURE_WEBB_MULTIPLIER_ID}:"
            f"seed:{protocol.multiplier_seed}:draws:{protocol.multiplier_draws}"
        ),
    )
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    normal_critical = NormalDist().inv_cdf(0.5 + protocol.confidence_level / 2.0)
    student_critical = (
        None
        if structure.cluster_count < 2
        else _student_t_critical(
            protocol.confidence_level,
            structure.cluster_count - 1,
        )
    )
    shift_index = {
        log_imor: index for index, log_imor in enumerate(pattern_protocol.log_imor_grid)
    }

    for replicate_index in range(stress_protocol.replicates):
        labels = [0.0] * layout.unit_count
        for block in scenario.dependence_blocks:
            successes = 0
            previous_count = 0
            for nominal_index in block:
                for unit_index in layout.unit_indices_by_nominal_cluster[nominal_index]:
                    label = _draw_beta_binomial_label(
                        outcome_rng,
                        scenario.favorable_prevalence,
                        scenario.dependence_block_intraclass_correlation,
                        successes,
                        previous_count,
                    )
                    labels[unit_index] = label
                    successes += int(label)
                    previous_count += 1

        stratum_evaluable = [0] * len(layout.prediction_strata)
        stratum_favorable = [0] * len(layout.prediction_strata)
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
            stratum_evaluable[stratum_index] += 1
            stratum_favorable[stratum_index] += favorable
            group_evaluable[group_index][stratum_index] += 1
            group_favorable[group_index][stratum_index] += favorable

        full_support = _support_status(
            layout.stratum_totals,
            stratum_evaluable,
            stratum_favorable,
            leave_one_out=False,
        )
        if full_support is not None:
            status = _mapped_support_status(full_support)
            for method in protocol.methods:
                for metric in _METRIC_ORDER:
                    for accumulator in accumulators[method][metric].values():
                        accumulator.add_failure(status)
            continue

        full_estimates = _full_metric_estimates(
            layout,
            stratum_evaluable,
            stratum_favorable,
            pattern_protocol.log_imor_grid,
            scenario,
        )
        for method in (
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
        ):
            for metric_index, metric in enumerate(_METRIC_ORDER):
                for log_imor in pattern_protocol.log_imor_grid:
                    accumulators[method][metric][log_imor].add_point(
                        full_estimates[log_imor][metric_index]
                    )

        if structure.cluster_count < 2:
            for method in protocol.methods:
                for metric in _METRIC_ORDER:
                    for accumulator in accumulators[method][metric].values():
                        accumulator.add_failure(
                            ClinicalOutcomePatternMixtureInfluenceStatus.INSUFFICIENT_SIMULATION_CLUSTERS
                        )
            continue

        leaveout_status, leaveout_estimates = _leave_one_out_metric_estimates(
            layout=layout,
            scenario=scenario,
            mode=mode,
            evaluable=stratum_evaluable,
            favorable=stratum_favorable,
            group_evaluable=group_evaluable,
            group_favorable=group_favorable,
            shifts=pattern_protocol.log_imor_grid,
        )
        if leaveout_status is not None:
            status = _mapped_support_status(leaveout_status)
            for method in protocol.methods:
                for metric in _METRIC_ORDER:
                    for accumulator in accumulators[method][metric].values():
                        accumulator.add_failure(status)
            continue

        webb_rows = _webb_weight_rows(
            multiplier_stream_sha256,
            replicate_index,
            protocol.multiplier_draws,
            structure.cluster_count,
        )
        assert student_critical is not None
        for log_imor in pattern_protocol.log_imor_grid:
            log_index = shift_index[log_imor]
            for metric_index, metric in enumerate(_METRIC_ORDER):
                full_estimate = full_estimates[log_imor][metric_index]
                leaveout_values = tuple(
                    group[log_index][metric_index] for group in leaveout_estimates
                )
                delete_one_variance = _delete_one_variance(leaveout_values)
                delete_one_se = math.sqrt(delete_one_variance)
                (
                    delete_mj_estimate,
                    delete_mj_variance,
                    _,
                    contributions,
                ) = _delete_mj_estimate_and_variance(
                    full_estimate,
                    leaveout_values,
                    cluster_sizes,
                )
                delete_mj_se = math.sqrt(delete_mj_variance)
                model_truth = model_truths[log_imor][metric_index]
                for method in (
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER,
                ):
                    accumulators[method][metric][log_imor].add_point(delete_mj_estimate)

                if _round_metric(delete_one_se) == 0.0:
                    for method in (
                        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
                        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
                    ):
                        accumulators[method][metric][log_imor].add_failure(
                            ClinicalOutcomePatternMixtureInfluenceStatus.ZERO_RESAMPLING_VARIANCE
                        )
                else:
                    for method, critical in (
                        (
                            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
                            normal_critical,
                        ),
                        (
                            ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
                            student_critical,
                        ),
                    ):
                        _add_interval(
                            accumulators[method][metric][log_imor],
                            metric=metric,
                            point_estimate=full_estimate,
                            standard_error=delete_one_se,
                            lower_offset=-critical * delete_one_se,
                            upper_offset=critical * delete_one_se,
                            model_truth=model_truth,
                        )

                if _round_metric(delete_mj_se) == 0.0:
                    for method in (
                        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
                        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER,
                    ):
                        accumulators[method][metric][log_imor].add_failure(
                            ClinicalOutcomePatternMixtureInfluenceStatus.ZERO_RESAMPLING_VARIANCE
                        )
                    continue

                _add_interval(
                    accumulators[
                        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T
                    ][metric][log_imor],
                    metric=metric,
                    point_estimate=delete_mj_estimate,
                    standard_error=delete_mj_se,
                    lower_offset=-student_critical * delete_mj_se,
                    upper_offset=student_critical * delete_mj_se,
                    model_truth=model_truth,
                )
                raw_dispersion = sum(value * value for value in contributions)
                webb_accumulator = accumulators[
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER
                ][metric][log_imor]
                if not math.isfinite(raw_dispersion) or raw_dispersion <= 0.0:
                    webb_accumulator.add_failure(
                        ClinicalOutcomePatternMixtureInfluenceStatus.INVALID_MULTIPLIER_DISPERSION
                    )
                    continue
                scale = math.sqrt(delete_mj_variance / raw_dispersion)
                draws = tuple(
                    scale
                    * sum(
                        weight * contribution
                        for weight, contribution in zip(
                            weights,
                            contributions,
                            strict=True,
                        )
                    )
                    for weights in webb_rows
                )
                alpha = 1.0 - protocol.confidence_level
                lower_quantile = _linear_quantile(draws, alpha / 2.0)
                upper_quantile = _linear_quantile(draws, 1.0 - alpha / 2.0)
                _add_interval(
                    webb_accumulator,
                    metric=metric,
                    point_estimate=delete_mj_estimate,
                    standard_error=delete_mj_se,
                    lower_offset=-upper_quantile,
                    upper_offset=-lower_quantile,
                    model_truth=model_truth,
                )

    prior_scenario = next(
        item
        for item in pattern_report.scenario_results
        if item.scenario_id == scenario.scenario_id
    )
    method_results: list[ClinicalOutcomePatternMixtureInfluenceMethodResult] = []
    for method in protocol.methods:
        metric_results: list[ClinicalOutcomePatternMixtureInfluenceMetric] = []
        for metric_index, metric in enumerate(_METRIC_ORDER):
            prior = _prior_metric(prior_scenario, metric)
            prior_grid = {
                item.log_imor: item.mean_estimate for item in prior.grid_performance
            }
            cells = tuple(
                _finalize_cell(
                    protocol=protocol,
                    pattern_protocol=pattern_protocol,
                    method=method,
                    metric=metric,
                    log_imor=log_imor,
                    model_truth=model_truths[log_imor][metric_index],
                    prior_mean=prior_grid[log_imor],
                    accumulator=accumulators[method][metric][log_imor],
                    replicate_count=stress_protocol.replicates,
                )
                for log_imor in pattern_protocol.log_imor_grid
            )
            metric_results.append(
                ClinicalOutcomePatternMixtureInfluenceMetric(
                    metric=metric,
                    grid_inference=cells,
                    all_grid_calibration_targets_met=all(
                        cell.calibration_target_met for cell in cells
                    ),
                )
            )
        method_results.append(
            ClinicalOutcomePatternMixtureInfluenceMethodResult(
                method=method,
                metric_inference=tuple(metric_results),
                all_metric_calibration_targets_met=all(
                    item.all_grid_calibration_targets_met for item in metric_results
                ),
                operational_candidate=method
                in {
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
                    ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
                },
                experimental_only=method
                is ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER,
            )
        )

    baseline = _method_result(
        method_results,
        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_NORMAL,
    )
    student = _method_result(
        method_results,
        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_ONE_STUDENT_T,
    )
    delete_mj = _method_result(
        method_results,
        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_STUDENT_T,
    )
    noninferior = all(
        student.metric_inference[metric_index].grid_inference[grid_index].covered_count
        >= baseline.metric_inference[metric_index]
        .grid_inference[grid_index]
        .covered_count
        for metric_index in range(len(_METRIC_ORDER))
        for grid_index in range(len(pattern_protocol.log_imor_grid))
    )
    equal_cluster_sizes = (
        structure.minimum_cluster_size == structure.maximum_cluster_size
    )
    equal_size_equivalence = equal_cluster_sizes and all(
        student.metric_inference[metric_index]
        .grid_inference[grid_index]
        .root_mean_squared_reported_standard_error
        == delete_mj.metric_inference[metric_index]
        .grid_inference[grid_index]
        .root_mean_squared_reported_standard_error
        and student.metric_inference[metric_index]
        .grid_inference[grid_index]
        .mean_reported_standard_error
        == delete_mj.metric_inference[metric_index]
        .grid_inference[grid_index]
        .mean_reported_standard_error
        for metric_index in range(len(_METRIC_ORDER))
        for grid_index in range(len(pattern_protocol.log_imor_grid))
    )
    reasons = _production_ineligibility_reasons(protocol, structure)
    production_eligible = not reasons
    student_target = student.all_metric_calibration_targets_met and noninferior
    delete_mj_target = delete_mj.all_metric_calibration_targets_met and (
        not equal_cluster_sizes or equal_size_equivalence
    )
    webb = _method_result(
        method_results,
        ClinicalOutcomePatternMixtureIntervalMethod.DELETE_MJ_WEBB_MULTIPLIER,
    )
    dominant_hard_stop = "dominant_cluster" not in reasons or not production_eligible
    return ClinicalOutcomePatternMixtureInfluenceScenarioResult(
        scenario_id=scenario.scenario_id,
        stage=scenario.stage,
        endpoint_family=scenario.endpoint_family,
        true_log_imor=_true_log_imor(scenario),
        analysis_structure=structure,
        equal_cluster_sizes=equal_cluster_sizes,
        production_eligible=production_eligible,
        production_ineligibility_reasons=reasons,
        method_results=tuple(method_results),
        student_t_coverage_noninferior_to_normal_all_cells=noninferior,
        equal_size_delete_mj_standard_error_equivalence_expected=equal_cluster_sizes,
        equal_size_delete_mj_standard_error_equivalence_met=equal_size_equivalence,
        student_t_candidate_target_met=student_target,
        delete_mj_sensitivity_target_met=delete_mj_target,
        webb_experimental_target_met=webb.all_metric_calibration_targets_met,
        dominant_cluster_hard_stop_preserved=dominant_hard_stop,
        research_target_met=(
            student_target and delete_mj_target
            if production_eligible
            else dominant_hard_stop
        ),
        rng_stream_sha256=stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
        multiplier_rng_stream_sha256=multiplier_stream_sha256,
    )


def _work_units(
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> int:
    grid_metric_count = len(pattern_protocol.log_imor_grid) * len(_METRIC_ORDER)
    return stress_protocol.replicates * sum(
        sum(scenario.nominal_cluster_sizes)
        + len(scenario.dependence_blocks)
        * grid_metric_count
        * (4 + protocol.multiplier_draws)
        for scenario in stress_protocol.scenarios
    )


def analyze_clinical_outcome_pattern_mixture_influence_calibration(
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
    pattern_mixture_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomePatternMixtureInfluenceReport:
    """Replay a bound sensitivity study and compare unequal-cluster intervals."""

    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureInfluenceProtocol,
        "protocol",
    )
    _require_instance(
        pattern_mixture_protocol,
        ClinicalOutcomePatternMixtureProtocol,
        "pattern_mixture_protocol",
    )
    _require_instance(
        stress_protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "stress_protocol",
    )
    if protocol.stress_protocol_fingerprint != stress_protocol.fingerprint:
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "influence protocol is not bound to the stress protocol"
        )
    if (
        protocol.pattern_mixture_protocol_fingerprint
        != pattern_mixture_protocol.fingerprint
    ):
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "influence protocol is not bound to the pattern-mixture protocol"
        )
    if (
        pattern_mixture_protocol.stress_protocol_fingerprint
        != stress_protocol.fingerprint
    ):
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "pattern-mixture and stress protocols are not mutually bound"
        )
    if (
        _work_units(protocol, pattern_mixture_protocol, stress_protocol)
        > MAX_DESIGN_WORK_UNITS
    ):
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "influence calibration exceeds the bounded work budget"
        )
    pattern_report = analyze_clinical_outcome_pattern_mixture(
        pattern_mixture_protocol,
        stress_protocol,
    )
    if protocol.pattern_mixture_report_fingerprint != pattern_report.fingerprint:
        raise ClinicalOutcomePatternMixtureInfluenceError(
            "influence protocol is not bound to the replayed pattern-mixture report"
        )
    return ClinicalOutcomePatternMixtureInfluenceReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        stress_protocol_id=stress_protocol.protocol_id,
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        stress_report_fingerprint=pattern_report.stress_report_fingerprint,
        pattern_mixture_protocol_id=pattern_mixture_protocol.protocol_id,
        pattern_mixture_protocol_fingerprint=pattern_mixture_protocol.fingerprint,
        pattern_mixture_report_fingerprint=pattern_report.fingerprint,
        method_id=protocol.method_id,
        rng_method_id=stress_protocol.rng_method_id,
        multiplier_method_id=CLINICAL_OUTCOME_PATTERN_MIXTURE_WEBB_MULTIPLIER_ID,
        quantile_method_id=CLINICAL_OUTCOME_PATTERN_MIXTURE_QUANTILE_METHOD_ID,
        replicates=stress_protocol.replicates,
        log_imor_grid=pattern_mixture_protocol.log_imor_grid,
        methods=protocol.methods,
        confidence_level=protocol.confidence_level,
        monte_carlo_confidence_level=protocol.monte_carlo_confidence_level,
        coverage_target=protocol.coverage_target,
        minimum_interval_yield=protocol.minimum_interval_yield,
        minimum_production_clusters=protocol.minimum_production_clusters,
        maximum_production_cluster_unit_fraction=(
            protocol.maximum_production_cluster_unit_fraction
        ),
        maximum_absolute_bias=pattern_mixture_protocol.maximum_absolute_bias,
        standard_error_calibration_lower=protocol.standard_error_calibration_lower,
        standard_error_calibration_upper=protocol.standard_error_calibration_upper,
        multiplier_draws=protocol.multiplier_draws,
        multiplier_seed=protocol.multiplier_seed,
        primary_metric=protocol.primary_metric,
        scenario_results=tuple(
            _simulate_scenario(
                protocol,
                pattern_mixture_protocol,
                pattern_report,
                stress_protocol,
                scenario,
            )
            for scenario in stress_protocol.scenarios
        ),
    )


def validate_clinical_outcome_pattern_mixture_influence_calibration_report(
    report: ClinicalOutcomePatternMixtureInfluenceReport,
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
    pattern_mixture_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> tuple[str, ...]:
    """Replay the complete seeded calibration and compare the aggregate report."""

    try:
        rebuilt = analyze_clinical_outcome_pattern_mixture_influence_calibration(
            protocol,
            pattern_mixture_protocol,
            stress_protocol,
        )
    except (ClinicalOutcomePatternMixtureInfluenceError, TypeError, ValueError):
        return ("pattern_mixture_influence_calibration_replay_failed",)
    return (
        ()
        if rebuilt == report
        else ("pattern_mixture_influence_calibration_report_mismatch",)
    )


def _rate_projection(value: ClinicalOutcomeDesignRate) -> dict[str, Any]:
    return {
        "event_count": value.event_count,
        "total_count": value.total_count,
        "rate": value.rate,
        "lower": value.lower,
        "upper": value.upper,
    }


def clinical_outcome_pattern_mixture_influence_calibration_summary(
    report: ClinicalOutcomePatternMixtureInfluenceReport,
) -> dict[str, Any]:
    """Return compact method comparisons and production-eligibility diagnostics."""

    _require_instance(
        report,
        ClinicalOutcomePatternMixtureInfluenceReport,
        "report",
    )
    scenarios: list[dict[str, Any]] = []
    for scenario in report.scenario_results:
        methods: list[dict[str, Any]] = []
        for method in scenario.method_results:
            cells = [
                cell
                for metric in method.metric_inference
                for cell in metric.grid_inference
            ]
            coverage_lowers = [
                cell.model_functional_coverage.lower
                for cell in cells
                if cell.model_functional_coverage.lower is not None
            ]
            yield_lowers = [
                cell.interval_yield.lower
                for cell in cells
                if cell.interval_yield.lower is not None
            ]
            se_ratios = [
                cell.standard_error_to_empirical_sd_ratio
                for cell in cells
                if cell.standard_error_to_empirical_sd_ratio is not None
            ]
            primary = next(
                item
                for item in method.metric_inference
                if item.metric is report.primary_metric
            )
            methods.append(
                {
                    "method": method.method.value,
                    "operational_candidate": method.operational_candidate,
                    "experimental_only": method.experimental_only,
                    "minimum_coverage_lower": (
                        None if not coverage_lowers else min(coverage_lowers)
                    ),
                    "minimum_interval_yield_lower": (
                        None if not yield_lowers else min(yield_lowers)
                    ),
                    "standard_error_calibration_ratio_range": {
                        "minimum": None if not se_ratios else min(se_ratios),
                        "maximum": None if not se_ratios else max(se_ratios),
                    },
                    "all_metric_calibration_targets_met": (
                        method.all_metric_calibration_targets_met
                    ),
                    "primary_metric_grid": [
                        {
                            "log_imor": cell.log_imor,
                            "mean_estimate": cell.mean_estimate,
                            "mean_minus_prior_pattern_mixture": (
                                cell.mean_minus_prior_pattern_mixture
                            ),
                            "interval_yield": _rate_projection(cell.interval_yield),
                            "model_functional_coverage": _rate_projection(
                                cell.model_functional_coverage
                            ),
                            "standard_error_to_empirical_sd_ratio": (
                                cell.standard_error_to_empirical_sd_ratio
                            ),
                            "calibration_target_met": cell.calibration_target_met,
                        }
                        for cell in primary.grid_inference
                    ],
                }
            )
        scenarios.append(
            {
                "scenario_id": scenario.scenario_id,
                "stage": scenario.stage.value,
                "endpoint_family": scenario.endpoint_family,
                "analysis_cluster_count": scenario.analysis_structure.cluster_count,
                "minimum_cluster_size": (
                    scenario.analysis_structure.minimum_cluster_size
                ),
                "maximum_cluster_size": (
                    scenario.analysis_structure.maximum_cluster_size
                ),
                "maximum_cluster_unit_fraction": (
                    scenario.analysis_structure.maximum_cluster_fraction
                ),
                "equal_cluster_sizes": scenario.equal_cluster_sizes,
                "production_eligible": scenario.production_eligible,
                "production_ineligibility_reasons": list(
                    scenario.production_ineligibility_reasons
                ),
                "methods": methods,
                "student_t_coverage_noninferior_to_normal_all_cells": (
                    scenario.student_t_coverage_noninferior_to_normal_all_cells
                ),
                "equal_size_delete_mj_standard_error_equivalence_expected": (
                    scenario.equal_size_delete_mj_standard_error_equivalence_expected
                ),
                "equal_size_delete_mj_standard_error_equivalence_met": (
                    scenario.equal_size_delete_mj_standard_error_equivalence_met
                ),
                "student_t_candidate_target_met": (
                    scenario.student_t_candidate_target_met
                ),
                "delete_mj_sensitivity_target_met": (
                    scenario.delete_mj_sensitivity_target_met
                ),
                "webb_experimental_target_met": (scenario.webb_experimental_target_met),
                "dominant_cluster_hard_stop_preserved": (
                    scenario.dominant_cluster_hard_stop_preserved
                ),
                "research_target_met": scenario.research_target_met,
            }
        )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_SUMMARY_SCHEMA_VERSION
        ),
        "protocol_id": report.protocol_id,
        "protocol_fingerprint": report.protocol_fingerprint,
        "report_fingerprint": report.fingerprint,
        "stress_protocol_id": report.stress_protocol_id,
        "stress_protocol_fingerprint": report.stress_protocol_fingerprint,
        "stress_report_fingerprint": report.stress_report_fingerprint,
        "pattern_mixture_protocol_id": report.pattern_mixture_protocol_id,
        "pattern_mixture_protocol_fingerprint": (
            report.pattern_mixture_protocol_fingerprint
        ),
        "pattern_mixture_report_fingerprint": (
            report.pattern_mixture_report_fingerprint
        ),
        "method_id": report.method_id,
        "methods": [item.value for item in report.methods],
        "replicates": report.replicates,
        "log_imor_grid": list(report.log_imor_grid),
        "primary_metric": report.primary_metric.value,
        "targets": {
            "confidence_level": report.confidence_level,
            "coverage_target": report.coverage_target,
            "minimum_interval_yield": report.minimum_interval_yield,
            "minimum_production_clusters": report.minimum_production_clusters,
            "maximum_production_cluster_unit_fraction": (
                report.maximum_production_cluster_unit_fraction
            ),
            "maximum_absolute_bias": report.maximum_absolute_bias,
            "standard_error_calibration_lower": (
                report.standard_error_calibration_lower
            ),
            "standard_error_calibration_upper": (
                report.standard_error_calibration_upper
            ),
        },
        "all_production_eligible_scenarios_research_targets_met": all(
            scenario.research_target_met
            for scenario in report.scenario_results
            if scenario.production_eligible
        ),
        "all_dominant_cluster_hard_stops_preserved": all(
            scenario.dominant_cluster_hard_stop_preserved
            for scenario in report.scenario_results
        ),
        "scenarios": scenarios,
        "claim_boundary": {
            "aggregate_simulation_only": report.aggregate_simulation_only,
            "replicate_level_records_included": (
                report.replicate_level_records_included
            ),
            "cluster_level_records_included": report.cluster_level_records_included,
            "unit_level_records_included": report.unit_level_records_included,
            "real_clinical_outcomes_included": report.real_clinical_outcomes_included,
            "stress_only_ineligible_intervals_operational": (
                report.stress_only_ineligible_intervals_operational
            ),
            "dominant_cluster_override_allowed": (
                report.dominant_cluster_override_allowed
            ),
            "automatic_method_selection_included": (
                report.automatic_method_selection_included
            ),
            "regression_wild_cluster_bootstrap_claimed": (
                report.regression_wild_cluster_bootstrap_claimed
            ),
            "multiplier_method_experimental_only": (
                report.multiplier_method_experimental_only
            ),
            "identification_and_sampling_uncertainty_separated": (
                report.identification_and_sampling_uncertainty_separated
            ),
        },
    }


def clinical_outcome_pattern_mixture_influence_calibration_validation_summary(
    report: ClinicalOutcomePatternMixtureInfluenceReport,
    *,
    failures: Sequence[str] = (),
    scope: str,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureInfluenceReport,
        "report",
    )
    _require_text(scope, "scope")
    resolved_failures = tuple(str(item) for item in failures)
    return {
        "schema_version": (
            "adds.clinical-outcome-pattern-mixture-influence-calibration-"
            "validation-summary.v1"
        ),
        "valid": not resolved_failures,
        "scope": scope,
        "report_fingerprint": report.fingerprint,
        "failures": list(resolved_failures),
    }


def clinical_outcome_pattern_mixture_influence_protocol_envelope(
    protocol: ClinicalOutcomePatternMixtureInfluenceProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureInfluenceProtocol,
        "protocol",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_PROTOCOL_SCHEMA_VERSION
        ),
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_pattern_mixture_influence_report_envelope(
    report: ClinicalOutcomePatternMixtureInfluenceReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureInfluenceReport,
        "report",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    if _sha256(value) != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def clinical_outcome_pattern_mixture_influence_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureInfluenceProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_influence_protocol_envelope",
        schema_version=(
            CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_PROTOCOL_SCHEMA_VERSION
        ),
        payload_field="protocol",
    )
    data = _record(
        payload,
        "protocol",
        {
            "protocol_id",
            "version",
            "registered_on",
            "stress_protocol_fingerprint",
            "pattern_mixture_protocol_fingerprint",
            "pattern_mixture_report_fingerprint",
            "methods",
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_tolerance",
            "minimum_interval_yield",
            "minimum_production_clusters",
            "maximum_production_cluster_unit_fraction",
            "maximum_standard_error_calibration_deviation",
            "multiplier_draws",
            "multiplier_seed",
            "primary_metric",
            "method_id",
            "metadata",
        },
    )
    protocol = ClinicalOutcomePatternMixtureInfluenceProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        stress_protocol_fingerprint=data["stress_protocol_fingerprint"],
        pattern_mixture_protocol_fingerprint=(
            data["pattern_mixture_protocol_fingerprint"]
        ),
        pattern_mixture_report_fingerprint=data["pattern_mixture_report_fingerprint"],
        methods=tuple(
            _parse_enum(
                ClinicalOutcomePatternMixtureIntervalMethod,
                item,
                f"protocol.methods[{index}]",
            )
            for index, item in enumerate(_sequence(data["methods"], "protocol.methods"))
        ),
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        coverage_tolerance=data["coverage_tolerance"],
        minimum_interval_yield=data["minimum_interval_yield"],
        minimum_production_clusters=data["minimum_production_clusters"],
        maximum_production_cluster_unit_fraction=data[
            "maximum_production_cluster_unit_fraction"
        ],
        maximum_standard_error_calibration_deviation=data[
            "maximum_standard_error_calibration_deviation"
        ],
        multiplier_draws=data["multiplier_draws"],
        multiplier_seed=data["multiplier_seed"],
        primary_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["primary_metric"],
            "protocol.primary_metric",
        ),
        method_id=data["method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "pattern-mixture influence protocol")
    return protocol


def _parse_status_count(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureInfluenceStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomePatternMixtureInfluenceStatusCount(
        status=_parse_enum(
            ClinicalOutcomePatternMixtureInfluenceStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_cell(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureInfluenceCell:
    fields = {
        "method",
        "metric",
        "log_imor",
        "informative_missingness_odds_ratio",
        "model_functional_true_value",
        "replicate_count",
        "point_estimate_count",
        "interval_count",
        "covered_count",
        "interval_yield",
        "model_functional_coverage",
        "prior_pattern_mixture_mean_estimate",
        "mean_estimate",
        "mean_minus_prior_pattern_mixture",
        "model_functional_bias",
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
    scalar = {
        key: data[key]
        for key in fields
        if key
        not in {
            "method",
            "metric",
            "interval_yield",
            "model_functional_coverage",
            "status_counts",
        }
    }
    return ClinicalOutcomePatternMixtureInfluenceCell(
        method=_parse_enum(
            ClinicalOutcomePatternMixtureIntervalMethod,
            data["method"],
            f"{path}.method",
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
        model_functional_coverage=_parse_design_rate(
            data["model_functional_coverage"],
            f"{path}.model_functional_coverage",
        ),
        status_counts=tuple(
            _parse_status_count(item, f"{path}.status_counts[{index}]")
            for index, item in enumerate(
                _sequence(data["status_counts"], f"{path}.status_counts")
            )
        ),
        **scalar,
    )


def _parse_metric(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureInfluenceMetric:
    data = _record(
        value,
        path,
        {
            "metric",
            "grid_inference",
            "all_grid_calibration_targets_met",
        },
    )
    return ClinicalOutcomePatternMixtureInfluenceMetric(
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
) -> ClinicalOutcomePatternMixtureInfluenceMethodResult:
    data = _record(
        value,
        path,
        {
            "method",
            "metric_inference",
            "all_metric_calibration_targets_met",
            "operational_candidate",
            "experimental_only",
        },
    )
    return ClinicalOutcomePatternMixtureInfluenceMethodResult(
        method=_parse_enum(
            ClinicalOutcomePatternMixtureIntervalMethod,
            data["method"],
            f"{path}.method",
        ),
        metric_inference=tuple(
            _parse_metric(item, f"{path}.metric_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["metric_inference"], f"{path}.metric_inference")
            )
        ),
        all_metric_calibration_targets_met=data["all_metric_calibration_targets_met"],
        operational_candidate=data["operational_candidate"],
        experimental_only=data["experimental_only"],
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureInfluenceScenarioResult:
    fields = {
        "scenario_id",
        "stage",
        "endpoint_family",
        "true_log_imor",
        "analysis_structure",
        "equal_cluster_sizes",
        "production_eligible",
        "production_ineligibility_reasons",
        "method_results",
        "student_t_coverage_noninferior_to_normal_all_cells",
        "equal_size_delete_mj_standard_error_equivalence_expected",
        "equal_size_delete_mj_standard_error_equivalence_met",
        "student_t_candidate_target_met",
        "delete_mj_sensitivity_target_met",
        "webb_experimental_target_met",
        "dominant_cluster_hard_stop_preserved",
        "research_target_met",
        "rng_stream_sha256",
        "outcome_rng_stream_sha256",
        "evaluability_rng_stream_sha256",
        "multiplier_rng_stream_sha256",
    }
    data = _record(value, path, fields)
    scalar = {
        key: data[key]
        for key in fields
        if key
        not in {
            "stage",
            "analysis_structure",
            "production_ineligibility_reasons",
            "method_results",
        }
    }
    return ClinicalOutcomePatternMixtureInfluenceScenarioResult(
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        analysis_structure=_parse_design_structure(
            data["analysis_structure"],
            f"{path}.analysis_structure",
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
        **scalar,
    )


def clinical_outcome_pattern_mixture_influence_report_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureInfluenceReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_influence_report_envelope",
        schema_version=(
            CLINICAL_OUTCOME_PATTERN_MIXTURE_INFLUENCE_REPORT_SCHEMA_VERSION
        ),
        payload_field="report",
    )
    fields = {
        "protocol_id",
        "protocol_fingerprint",
        "stress_protocol_id",
        "stress_protocol_fingerprint",
        "stress_report_fingerprint",
        "pattern_mixture_protocol_id",
        "pattern_mixture_protocol_fingerprint",
        "pattern_mixture_report_fingerprint",
        "method_id",
        "rng_method_id",
        "multiplier_method_id",
        "quantile_method_id",
        "replicates",
        "log_imor_grid",
        "methods",
        "confidence_level",
        "monte_carlo_confidence_level",
        "coverage_target",
        "minimum_interval_yield",
        "minimum_production_clusters",
        "maximum_production_cluster_unit_fraction",
        "maximum_absolute_bias",
        "standard_error_calibration_lower",
        "standard_error_calibration_upper",
        "multiplier_draws",
        "multiplier_seed",
        "primary_metric",
        "scenario_results",
        "aggregate_simulation_only",
        "replicate_level_records_included",
        "cluster_level_records_included",
        "unit_level_records_included",
        "real_clinical_outcomes_included",
        "stress_only_ineligible_intervals_operational",
        "dominant_cluster_override_allowed",
        "automatic_method_selection_included",
        "regression_wild_cluster_bootstrap_claimed",
        "multiplier_method_experimental_only",
        "identification_and_sampling_uncertainty_separated",
        "limitations",
    }
    data = _record(payload, "report", fields)
    scalar = {
        key: data[key]
        for key in fields
        if key
        not in {
            "log_imor_grid",
            "methods",
            "primary_metric",
            "scenario_results",
            "limitations",
        }
    }
    report = ClinicalOutcomePatternMixtureInfluenceReport(
        log_imor_grid=tuple(_sequence(data["log_imor_grid"], "report.log_imor_grid")),
        methods=tuple(
            _parse_enum(
                ClinicalOutcomePatternMixtureIntervalMethod,
                item,
                f"report.methods[{index}]",
            )
            for index, item in enumerate(_sequence(data["methods"], "report.methods"))
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
        **scalar,
    )
    _check_integrity(report, integrity, "pattern-mixture influence report")
    return report


def clinical_outcome_pattern_mixture_influence_protocol_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureInfluenceProtocol:
    return clinical_outcome_pattern_mixture_influence_protocol_from_dict(
        _strict_json(payload, "pattern-mixture influence protocol")
    )


def clinical_outcome_pattern_mixture_influence_report_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureInfluenceReport:
    return clinical_outcome_pattern_mixture_influence_report_from_dict(
        _strict_json(payload, "pattern-mixture influence report")
    )
