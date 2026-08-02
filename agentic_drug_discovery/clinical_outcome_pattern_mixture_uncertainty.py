"""Cluster-jackknife sampling uncertainty for pattern-mixture curves."""

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
    _metric_values,
    _parse_design_structure,
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
from .clinical_outcome_pattern_mixture import (
    ClinicalOutcomePatternMixtureMetricPerformance,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomePatternMixtureReport,
    _expected_metric_value,
    _odds_shift_probability,
    _true_log_imor,
    analyze_clinical_outcome_pattern_mixture,
)
from .clinical_outcome_stress_simulation import (
    CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    _scenario_stream_sha256,
    _scenario_truth,
    _structure_from_sizes,
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


CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-uncertainty-protocol.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-uncertainty-report.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-uncertainty-summary.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_METHOD_ID = (
    "adds.pattern-mixture.dependence-block-delete-one-jackknife.v1"
)


class ClinicalOutcomePatternMixtureUncertaintyError(ValueError):
    """Raised when pattern-mixture sampling inference cannot run safely."""


class ClinicalOutcomePatternMixtureJackknifeStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_CLUSTERS = "insufficient_clusters"
    DOMINANT_CLUSTER = "dominant_cluster"
    EMPTY_REFERENCE_STRATUM = "empty_reference_stratum"
    DEGENERATE_REFERENCE_STRATUM = "degenerate_reference_stratum"
    LEAVE_ONE_OUT_EMPTY_REFERENCE_STRATUM = "leave_one_out_empty_reference_stratum"
    LEAVE_ONE_OUT_DEGENERATE_REFERENCE_STRATUM = (
        "leave_one_out_degenerate_reference_stratum"
    )
    ZERO_JACKKNIFE_VARIANCE = "zero_jackknife_variance"


_STATUS_ORDER = tuple(ClinicalOutcomePatternMixtureJackknifeStatus)
_ANALYSIS_MODE_ORDER = tuple(ClinicalOutcomeStressAnalysisMode)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic prospective sampling-calibration study; it contains "
        "no real clinical outcomes and does not validate a deployed policy or evidence board."
    ),
    (
        "Each interval is conditional on one fixed binary log-IMOR identifying assumption; "
        "sampling uncertainty and missing-data identification uncertainty remain separate."
    ),
    (
        "Grid coverage targets the model functional induced by each fixed log-IMOR; coverage "
        "of the population truth is a valid recovery diagnostic only at the latent true shift."
    ),
    (
        "Dependence-closed blocks are evaluator-declared synthetic oracle structure and are "
        "never inferred automatically from outcomes, identifiers, or reported performance."
    ),
    (
        "The delete-one-cluster jackknife assumes independent top-level analysis clusters "
        "and can be unreliable with too few, highly influential, or misspecified clusters."
    ),
    (
        "Normal critical values preserve parity with the production CR1 contract; the "
        "intervals are not exact small-sample or randomization-based confidence intervals."
    ),
    (
        "Cluster dominance is screened using enrolled-unit share, which is transparent and "
        "outcome blind but is not a complete influence diagnostic for nonlinear estimators."
    ),
    (
        "Inference fails closed when the full sample or any leave-one-cluster-out sample "
        "cannot support the preregistered prediction-stratified pattern-mixture estimator."
    ),
    (
        "Monte Carlo Wilson bounds and continuous-statistic bounds quantify finite simulation "
        "error; they do not guarantee coverage for one future clinical evidence board."
    ),
    (
        "Passing the synthetic targets does not establish treatment efficacy, safety, clinical "
        "utility, transportability, a real log-IMOR range, or regulatory acceptability."
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureUncertaintyProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    stress_protocol_fingerprint: str
    pattern_mixture_protocol_fingerprint: str
    pattern_mixture_report_fingerprint: str
    analysis_modes: tuple[ClinicalOutcomeStressAnalysisMode, ...]
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_tolerance: float
    minimum_interval_yield: float
    minimum_clusters: int
    maximum_cluster_unit_fraction: float
    maximum_standard_error_calibration_deviation: float
    closure_anchor_metric: ClinicalOutcomeDesignMetric
    minimum_hidden_linkage_coverage_gain: float
    minimum_hidden_linkage_standard_error_ratio: float
    method_id: str = CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_METHOD_ID
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
        modes = _tuple(self.analysis_modes, "analysis_modes")
        object.__setattr__(self, "analysis_modes", modes)
        for mode in modes:
            _require_instance(
                mode, ClinicalOutcomeStressAnalysisMode, "analysis_modes item"
            )
        if modes != _ANALYSIS_MODE_ORDER:
            raise ValueError(
                "analysis_modes must exactly compare nominal and dependence-closed clusters"
            )
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
        _require_positive_int(self.minimum_clusters, "minimum_clusters")
        if self.minimum_clusters < 3:
            raise ValueError("minimum_clusters must be at least three")
        _require_probability(
            self.maximum_cluster_unit_fraction,
            "maximum_cluster_unit_fraction",
        )
        if self.maximum_cluster_unit_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_cluster_unit_fraction must be strictly between zero and one"
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
            self.closure_anchor_metric,
            ClinicalOutcomeDesignMetric,
            "closure_anchor_metric",
        )
        _require_probability(
            self.minimum_hidden_linkage_coverage_gain,
            "minimum_hidden_linkage_coverage_gain",
        )
        _require_finite(
            self.minimum_hidden_linkage_standard_error_ratio,
            "minimum_hidden_linkage_standard_error_ratio",
            minimum=1.0,
            maximum=4.0,
        )
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_METHOD_ID:
            raise ValueError("method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError(
                "pattern-mixture uncertainty protocol metadata cannot contain evaluator outcomes"
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
class ClinicalOutcomePatternMixtureJackknifeStatusCount(SerializableRecord):
    status: ClinicalOutcomePatternMixtureJackknifeStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(
            self.status,
            ClinicalOutcomePatternMixtureJackknifeStatus,
            "status",
        )
        _require_non_negative_int(self.count, "count")


def _status_count_records(
    counts: Mapping[ClinicalOutcomePatternMixtureJackknifeStatus, int],
) -> tuple[ClinicalOutcomePatternMixtureJackknifeStatusCount, ...]:
    return tuple(
        ClinicalOutcomePatternMixtureJackknifeStatusCount(
            status=status,
            count=counts.get(status, 0),
        )
        for status in _STATUS_ORDER
    )


def _validated_status_counts(
    values: Sequence[ClinicalOutcomePatternMixtureJackknifeStatusCount],
    replicate_count: int,
) -> dict[ClinicalOutcomePatternMixtureJackknifeStatus, int]:
    resolved = _tuple(values, "status_counts")
    for item in resolved:
        _require_instance(
            item,
            ClinicalOutcomePatternMixtureJackknifeStatusCount,
            "status_counts item",
        )
    if tuple(item.status for item in resolved) != _STATUS_ORDER:
        raise ValueError("status_counts must exactly cover canonical statuses")
    if sum(item.count for item in resolved) != replicate_count:
        raise ValueError("status counts do not sum to replicate_count")
    return {item.status: item.count for item in resolved}


def _mc_mean_bounds(
    mean: float | None,
    standard_deviation: float | None,
    count: int,
    confidence_level: float,
) -> tuple[float | None, float | None]:
    if mean is None or standard_deviation is None or count < 2:
        return None, None
    critical = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    half_width = critical * standard_deviation / math.sqrt(count)
    return (
        _round_metric(mean - half_width),
        _round_metric(mean + half_width),
    )


def _mc_nonnegative_mean_bounds(
    mean: float | None,
    standard_deviation: float | None,
    count: int,
    confidence_level: float,
) -> tuple[float | None, float | None]:
    lower, upper = _mc_mean_bounds(
        mean,
        standard_deviation,
        count,
        confidence_level,
    )
    if lower is None:
        return None, None
    assert upper is not None
    return _round_metric(max(0.0, lower)), upper


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureGridInference(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    log_imor: float
    informative_missingness_odds_ratio: float
    model_functional_true_value: float
    population_true_value: float
    replicate_count: int
    point_estimate_count: int
    interval_count: int
    model_functional_covered_count: int
    population_truth_covered_count: int
    interval_yield: ClinicalOutcomeDesignRate
    model_functional_coverage: ClinicalOutcomeDesignRate
    population_truth_coverage: ClinicalOutcomeDesignRate
    prior_pattern_mixture_mean_estimate: float | None
    mean_estimate: float | None
    model_functional_bias: float | None
    empirical_standard_deviation: float | None
    monte_carlo_bias_lower: float | None
    monte_carlo_bias_upper: float | None
    monte_carlo_absolute_bias_upper: float | None
    root_mean_squared_jackknife_standard_error: float | None
    mean_jackknife_standard_error: float | None
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
    model_functional_coverage_target_met: bool
    standard_error_calibration_target_met: bool
    calibration_target_met: bool
    status_counts: tuple[ClinicalOutcomePatternMixtureJackknifeStatusCount, ...]

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        lower_bound, upper_bound = _metric_bounds(self.metric)
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
        for field_name in ("model_functional_true_value", "population_true_value"):
            _require_finite(
                getattr(self, field_name),
                field_name,
                minimum=lower_bound,
                maximum=upper_bound,
            )
        _require_positive_int(self.replicate_count, "replicate_count")
        for field_name in (
            "point_estimate_count",
            "interval_count",
            "model_functional_covered_count",
            "population_truth_covered_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.point_estimate_count > self.replicate_count:
            raise ValueError("point_estimate_count exceeds replicate_count")
        if self.interval_count > self.point_estimate_count:
            raise ValueError("interval_count exceeds point_estimate_count")
        if (
            max(
                self.model_functional_covered_count,
                self.population_truth_covered_count,
            )
            > self.interval_count
        ):
            raise ValueError("covered count exceeds interval_count")
        for value, field_name in (
            (self.interval_yield, "interval_yield"),
            (self.model_functional_coverage, "model_functional_coverage"),
            (self.population_truth_coverage, "population_truth_coverage"),
        ):
            _require_instance(value, ClinicalOutcomeDesignRate, field_name)
        if (
            self.interval_yield.event_count != self.interval_count
            or self.interval_yield.total_count != self.replicate_count
        ):
            raise ValueError("interval_yield denominator is inconsistent")
        for rate, count, label in (
            (
                self.model_functional_coverage,
                self.model_functional_covered_count,
                "model_functional_coverage",
            ),
            (
                self.population_truth_coverage,
                self.population_truth_covered_count,
                "population_truth_coverage",
            ),
        ):
            if rate.event_count != count or rate.total_count != self.interval_count:
                raise ValueError(f"{label} denominator is inconsistent")
            if rate.confidence_level != self.interval_yield.confidence_level:
                raise ValueError(f"{label} confidence level is inconsistent")
        for field_name in (
            "prior_pattern_mixture_mean_estimate",
            "mean_estimate",
            "model_functional_bias",
            "empirical_standard_deviation",
            "monte_carlo_bias_lower",
            "monte_carlo_bias_upper",
            "monte_carlo_absolute_bias_upper",
            "root_mean_squared_jackknife_standard_error",
            "mean_jackknife_standard_error",
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
                    "root_mean_squared_jackknife_standard_error",
                    "mean_jackknife_standard_error",
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
        for field_name in (
            "prior_pattern_mixture_mean_estimate",
            "mean_estimate",
        ):
            value = getattr(self, field_name)
            if value is not None and not lower_bound <= value <= upper_bound:
                raise ValueError(f"{field_name} falls outside the metric scale")
        if self.point_estimate_count == 0:
            if any(
                value is not None
                for value in (
                    self.prior_pattern_mixture_mean_estimate,
                    self.mean_estimate,
                    self.model_functional_bias,
                    self.empirical_standard_deviation,
                    self.monte_carlo_bias_lower,
                    self.monte_carlo_bias_upper,
                    self.monte_carlo_absolute_bias_upper,
                )
            ):
                raise ValueError("empty point estimates require null point summaries")
        else:
            if (
                self.mean_estimate is None
                or self.prior_pattern_mixture_mean_estimate is None
            ):
                raise ValueError("point estimates require synchronized means")
            if self.mean_estimate != self.prior_pattern_mixture_mean_estimate:
                raise ValueError(
                    "point mean does not match the bound pattern-mixture report"
                )
            expected_bias = _round_metric(
                self.mean_estimate - self.model_functional_true_value
            )
            if self.model_functional_bias != expected_bias:
                raise ValueError("model_functional_bias is inconsistent")
            if self.point_estimate_count == 1:
                if self.empirical_standard_deviation is not None:
                    raise ValueError(
                        "one point estimate requires null empirical deviation"
                    )
            elif self.empirical_standard_deviation is None:
                raise ValueError("multiple point estimates require empirical deviation")
            expected_bounds = _mc_mean_bounds(
                self.model_functional_bias,
                self.empirical_standard_deviation,
                self.point_estimate_count,
                self.interval_yield.confidence_level,
            )
            if (
                self.monte_carlo_bias_lower,
                self.monte_carlo_bias_upper,
            ) != expected_bounds:
                raise ValueError("Monte Carlo bias bounds are inconsistent")
            expected_absolute = (
                None
                if expected_bounds[0] is None
                else _round_metric(
                    max(abs(expected_bounds[0]), abs(expected_bounds[1]))
                )
            )
            if self.monte_carlo_absolute_bias_upper != expected_absolute:
                raise ValueError("Monte Carlo absolute-bias bound is inconsistent")
        status_counts = _tuple(self.status_counts, "status_counts")
        object.__setattr__(self, "status_counts", status_counts)
        counts = _validated_status_counts(status_counts, self.replicate_count)
        if (
            counts[ClinicalOutcomePatternMixtureJackknifeStatus.COMPUTED]
            != self.interval_count
        ):
            raise ValueError("computed status count is inconsistent")
        if self.interval_count == 0:
            if any(
                value is not None
                for value in (
                    self.root_mean_squared_jackknife_standard_error,
                    self.mean_jackknife_standard_error,
                    self.mean_interval_width,
                    self.interval_width_empirical_standard_deviation,
                    self.mean_interval_width_monte_carlo_lower,
                    self.mean_interval_width_monte_carlo_upper,
                    self.standard_error_to_empirical_sd_ratio,
                )
            ):
                raise ValueError("empty intervals require null interval summaries")
        else:
            if any(
                value is None
                for value in (
                    self.root_mean_squared_jackknife_standard_error,
                    self.mean_jackknife_standard_error,
                    self.mean_interval_width,
                )
            ):
                raise ValueError("computed intervals require standard-error summaries")
            if self.interval_count == 1:
                if self.interval_width_empirical_standard_deviation is not None:
                    raise ValueError(
                        "one interval requires null interval-width deviation"
                    )
            elif self.interval_width_empirical_standard_deviation is None:
                raise ValueError("multiple intervals require interval-width deviation")
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
                raise ValueError("Monte Carlo interval-width bounds are inconsistent")
        expected_se_ratio = (
            None
            if self.root_mean_squared_jackknife_standard_error is None
            or self.empirical_standard_deviation in (None, 0.0)
            else _round_metric(
                self.root_mean_squared_jackknife_standard_error
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
        if not (
            self.standard_error_calibration_lower
            <= self.standard_error_calibration_upper
        ):
            raise ValueError("standard-error calibration bounds are inconsistent")
        for field_name in (
            "bias_target_met",
            "interval_yield_target_met",
            "model_functional_coverage_target_met",
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
            or self.model_functional_coverage_target_met != expected_coverage_met
            or self.standard_error_calibration_target_met != expected_se_met
        ):
            raise ValueError("grid inference target flag is inconsistent")
        if self.calibration_target_met != (
            expected_bias_met
            and expected_yield_met
            and expected_coverage_met
            and expected_se_met
        ):
            raise ValueError("grid calibration target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureMetricInference(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    grid_inference: tuple[ClinicalOutcomePatternMixtureGridInference, ...]
    truth_aligned_inference: ClinicalOutcomePatternMixtureGridInference
    all_grid_calibration_targets_met: bool
    truth_aligned_population_coverage_target_met: bool
    research_target_met: bool

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        grid = _tuple(self.grid_inference, "grid_inference")
        object.__setattr__(self, "grid_inference", grid)
        if not grid:
            raise ValueError("grid_inference cannot be empty")
        for item in grid:
            _require_instance(
                item, ClinicalOutcomePatternMixtureGridInference, "grid item"
            )
            if item.metric is not self.metric:
                raise ValueError("grid metric is inconsistent")
        if tuple(item.log_imor for item in grid) != tuple(
            sorted(item.log_imor for item in grid)
        ):
            raise ValueError("grid inference must use canonical log-IMOR order")
        if len({item.log_imor for item in grid}) != len(grid):
            raise ValueError("grid inference cannot contain duplicate log-IMOR values")
        _require_instance(
            self.truth_aligned_inference,
            ClinicalOutcomePatternMixtureGridInference,
            "truth_aligned_inference",
        )
        if self.truth_aligned_inference.metric is not self.metric:
            raise ValueError("truth-aligned metric is inconsistent")
        if (
            self.truth_aligned_inference.model_functional_true_value
            != self.truth_aligned_inference.population_true_value
        ):
            raise ValueError(
                "truth-aligned model functional must equal population truth"
            )
        matching_grid = tuple(
            item
            for item in grid
            if item.log_imor == self.truth_aligned_inference.log_imor
        )
        if matching_grid and matching_grid[0] != self.truth_aligned_inference:
            raise ValueError("truth-aligned inference changed at its grid value")
        for field_name in (
            "all_grid_calibration_targets_met",
            "truth_aligned_population_coverage_target_met",
            "research_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        all_grid = all(item.calibration_target_met for item in grid)
        truth_coverage = (
            self.truth_aligned_inference.population_truth_coverage.lower is not None
            and self.truth_aligned_inference.population_truth_coverage.lower
            >= self.truth_aligned_inference.coverage_target
        )
        if self.all_grid_calibration_targets_met != all_grid:
            raise ValueError("all-grid calibration flag is inconsistent")
        if self.truth_aligned_population_coverage_target_met != truth_coverage:
            raise ValueError("truth-aligned coverage flag is inconsistent")
        if self.research_target_met != (
            all_grid
            and truth_coverage
            and self.truth_aligned_inference.calibration_target_met
        ):
            raise ValueError("metric research target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureModeInference(SerializableRecord):
    analysis_mode: ClinicalOutcomeStressAnalysisMode
    analysis_structure: ClinicalOutcomeDesignStructure
    replicate_count: int
    metric_inference: tuple[ClinicalOutcomePatternMixtureMetricInference, ...]
    all_metric_research_targets_met: bool

    def __post_init__(self) -> None:
        _require_instance(
            self.analysis_mode,
            ClinicalOutcomeStressAnalysisMode,
            "analysis_mode",
        )
        _require_instance(
            self.analysis_structure,
            ClinicalOutcomeDesignStructure,
            "analysis_structure",
        )
        _require_positive_int(self.replicate_count, "replicate_count")
        metrics = _tuple(self.metric_inference, "metric_inference")
        object.__setattr__(self, "metric_inference", metrics)
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("metric_inference must exactly cover canonical metrics")
        for item in metrics:
            _require_instance(
                item, ClinicalOutcomePatternMixtureMetricInference, "metric item"
            )
            if any(
                grid.replicate_count != self.replicate_count
                for grid in (*item.grid_inference, item.truth_aligned_inference)
            ):
                raise ValueError("metric replicate count is inconsistent")
        _require_bool(
            self.all_metric_research_targets_met, "all_metric_research_targets_met"
        )
        if self.all_metric_research_targets_met != all(
            item.research_target_met for item in metrics
        ):
            raise ValueError("mode research target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureClosureComparison(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    true_log_imor: float
    nominal_model_functional_coverage: float | None
    dependence_closed_model_functional_coverage: float | None
    dependence_closed_minus_nominal_coverage: float | None
    dependence_closed_to_nominal_standard_error_ratio: float | None
    minimum_hidden_linkage_coverage_gain: float
    minimum_hidden_linkage_standard_error_ratio: float
    closure_response_target_required: bool
    exact_equivalence_expected: bool
    exact_equivalence_met: bool
    closure_response_target_met: bool

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        _require_finite(self.true_log_imor, "true_log_imor")
        for field_name in (
            "nominal_model_functional_coverage",
            "dependence_closed_model_functional_coverage",
        ):
            _require_optional_finite(
                getattr(self, field_name), field_name, minimum=0.0, maximum=1.0
            )
        _require_optional_finite(
            self.dependence_closed_minus_nominal_coverage,
            "dependence_closed_minus_nominal_coverage",
            minimum=-1.0,
            maximum=1.0,
        )
        _require_optional_finite(
            self.dependence_closed_to_nominal_standard_error_ratio,
            "dependence_closed_to_nominal_standard_error_ratio",
            minimum=0.0,
        )
        _require_probability(
            self.minimum_hidden_linkage_coverage_gain,
            "minimum_hidden_linkage_coverage_gain",
        )
        _require_finite(
            self.minimum_hidden_linkage_standard_error_ratio,
            "minimum_hidden_linkage_standard_error_ratio",
            minimum=1.0,
        )
        for field_name in (
            "closure_response_target_required",
            "exact_equivalence_expected",
            "exact_equivalence_met",
            "closure_response_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if (
            self.nominal_model_functional_coverage is None
            or self.dependence_closed_model_functional_coverage is None
        ):
            expected_gain = None
        else:
            expected_gain = _round_metric(
                self.dependence_closed_model_functional_coverage
                - self.nominal_model_functional_coverage
            )
        if self.dependence_closed_minus_nominal_coverage != expected_gain:
            raise ValueError("coverage gain is inconsistent")
        if self.exact_equivalence_expected:
            expected_response = self.exact_equivalence_met
        elif not self.closure_response_target_required:
            expected_response = True
        else:
            expected_response = (
                expected_gain is not None
                and expected_gain >= self.minimum_hidden_linkage_coverage_gain
                and self.dependence_closed_to_nominal_standard_error_ratio is not None
                and self.dependence_closed_to_nominal_standard_error_ratio
                >= self.minimum_hidden_linkage_standard_error_ratio
            )
        if self.closure_response_target_met != expected_response:
            raise ValueError("closure response target is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureScenarioInference(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    population_favorable_prevalence: float
    evaluable_favorable_prevalence: float
    expected_evaluable_probability: float
    true_log_imor: float
    true_informative_missingness_odds_ratio: float
    hidden_linkage_declared: bool
    mode_inference: tuple[ClinicalOutcomePatternMixtureModeInference, ...]
    closure_comparison: tuple[ClinicalOutcomePatternMixtureClosureComparison, ...]
    dependence_closed_all_research_targets_met: bool
    all_closure_response_targets_met: bool
    research_target_met: bool
    rng_stream_sha256: str
    outcome_rng_stream_sha256: str
    evaluability_rng_stream_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        for field_name in (
            "population_favorable_prevalence",
            "evaluable_favorable_prevalence",
            "expected_evaluable_probability",
        ):
            _require_probability(getattr(self, field_name), field_name)
        _require_finite(self.true_log_imor, "true_log_imor")
        _require_finite(
            self.true_informative_missingness_odds_ratio,
            "true_informative_missingness_odds_ratio",
            minimum=0.0,
        )
        if self.true_informative_missingness_odds_ratio != _round_metric(
            math.exp(self.true_log_imor)
        ):
            raise ValueError("true missingness odds ratio is inconsistent")
        _require_bool(self.hidden_linkage_declared, "hidden_linkage_declared")
        modes = _tuple(self.mode_inference, "mode_inference")
        object.__setattr__(self, "mode_inference", modes)
        if tuple(item.analysis_mode for item in modes) != _ANALYSIS_MODE_ORDER:
            raise ValueError("mode_inference must exactly cover canonical modes")
        comparisons = _tuple(self.closure_comparison, "closure_comparison")
        object.__setattr__(self, "closure_comparison", comparisons)
        if tuple(item.metric for item in comparisons) != _METRIC_ORDER:
            raise ValueError("closure_comparison must exactly cover canonical metrics")
        if any(item.true_log_imor != self.true_log_imor for item in comparisons):
            raise ValueError("comparison true log-IMOR is inconsistent")
        nominal = next(
            item
            for item in modes
            if item.analysis_mode is ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS
        )
        closed = next(
            item
            for item in modes
            if item.analysis_mode
            is ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
        )
        for metric_index, comparison in enumerate(comparisons):
            nominal_metric = nominal.metric_inference[metric_index]
            closed_metric = closed.metric_inference[metric_index]
            nominal_truth = nominal_metric.truth_aligned_inference
            closed_truth = closed_metric.truth_aligned_inference
            if (
                nominal_truth.log_imor != self.true_log_imor
                or closed_truth.log_imor != self.true_log_imor
            ):
                raise ValueError("truth-aligned log-IMOR is inconsistent")
            nominal_coverage = nominal_truth.model_functional_coverage.rate
            closed_coverage = closed_truth.model_functional_coverage.rate
            nominal_rms = nominal_truth.root_mean_squared_jackknife_standard_error
            closed_rms = closed_truth.root_mean_squared_jackknife_standard_error
            expected_se_ratio = (
                None
                if nominal_rms in (None, 0.0) or closed_rms is None
                else _round_metric(closed_rms / nominal_rms)
            )
            if (
                comparison.nominal_model_functional_coverage != nominal_coverage
                or comparison.dependence_closed_model_functional_coverage
                != closed_coverage
                or comparison.dependence_closed_to_nominal_standard_error_ratio
                != expected_se_ratio
                or comparison.exact_equivalence_met != (nominal_metric == closed_metric)
            ):
                raise ValueError("closure comparison changed from mode inference")
        if any(
            item.exact_equivalence_expected == self.hidden_linkage_declared
            for item in comparisons
        ):
            raise ValueError("comparison equivalence expectation is inconsistent")
        required_count = sum(
            item.closure_response_target_required for item in comparisons
        )
        if self.hidden_linkage_declared and required_count != 1:
            raise ValueError(
                "hidden linkage requires exactly one closure anchor metric"
            )
        if not self.hidden_linkage_declared and required_count != len(comparisons):
            raise ValueError("independent scenarios require exact metric equivalence")
        for field_name in (
            "dependence_closed_all_research_targets_met",
            "all_closure_response_targets_met",
            "research_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        closed = next(
            item
            for item in modes
            if item.analysis_mode
            is ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
        )
        expected_closed = closed.all_metric_research_targets_met
        expected_response = all(
            item.closure_response_target_met for item in comparisons
        )
        if self.dependence_closed_all_research_targets_met != expected_closed:
            raise ValueError("dependence-closed target flag is inconsistent")
        if self.all_closure_response_targets_met != expected_response:
            raise ValueError("closure response flag is inconsistent")
        if self.research_target_met != (expected_closed and expected_response):
            raise ValueError("scenario research target is inconsistent")
        for field_name in (
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureUncertaintyReport(SerializableRecord):
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
    replicates: int
    log_imor_grid: tuple[float, ...]
    analysis_modes: tuple[ClinicalOutcomeStressAnalysisMode, ...]
    confidence_level: float
    monte_carlo_confidence_level: float
    coverage_target: float
    minimum_interval_yield: float
    minimum_clusters: int
    maximum_cluster_unit_fraction: float
    maximum_absolute_bias: float
    standard_error_calibration_lower: float
    standard_error_calibration_upper: float
    closure_anchor_metric: ClinicalOutcomeDesignMetric
    minimum_hidden_linkage_coverage_gain: float
    minimum_hidden_linkage_standard_error_ratio: float
    scenario_inference: tuple[ClinicalOutcomePatternMixtureScenarioInference, ...]
    aggregate_simulation_only: bool = True
    replicate_level_records_included: bool = False
    cluster_level_records_included: bool = False
    unit_level_records_included: bool = False
    real_clinical_outcomes_included: bool = False
    sampling_uncertainty_intervals_included: bool = True
    automatic_dependence_closure_included: bool = False
    latent_truth_used_for_operational_grid: bool = False
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
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        _require_positive_int(self.replicates, "replicates")
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        if not grid:
            raise ValueError("log_imor_grid cannot be empty")
        for log_imor in grid:
            _require_finite(log_imor, "log_imor_grid item")
        if grid != tuple(sorted(set(grid))):
            raise ValueError("log_imor_grid must be unique and increasing")
        modes = _tuple(self.analysis_modes, "analysis_modes")
        object.__setattr__(self, "analysis_modes", modes)
        if modes != _ANALYSIS_MODE_ORDER:
            raise ValueError("analysis_modes changed")
        for field_name in (
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_target",
            "minimum_interval_yield",
            "maximum_cluster_unit_fraction",
            "minimum_hidden_linkage_coverage_gain",
        ):
            _require_probability(getattr(self, field_name), field_name)
        if not 0.5 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError("monte_carlo_confidence_level must be between 0.5 and 1")
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be positive")
        if self.maximum_cluster_unit_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_cluster_unit_fraction must be strictly between zero and one"
            )
        _require_positive_int(self.minimum_clusters, "minimum_clusters")
        if self.minimum_clusters < 3:
            raise ValueError("minimum_clusters must be at least three")
        for field_name in (
            "maximum_absolute_bias",
            "standard_error_calibration_lower",
            "standard_error_calibration_upper",
            "minimum_hidden_linkage_standard_error_ratio",
        ):
            _require_finite(getattr(self, field_name), field_name, minimum=0.0)
        if (
            self.standard_error_calibration_lower
            > self.standard_error_calibration_upper
        ):
            raise ValueError("standard-error calibration bounds are inconsistent")
        if self.minimum_hidden_linkage_standard_error_ratio < 1.0:
            raise ValueError(
                "minimum_hidden_linkage_standard_error_ratio must be at least one"
            )
        _require_instance(
            self.closure_anchor_metric,
            ClinicalOutcomeDesignMetric,
            "closure_anchor_metric",
        )
        scenarios = _tuple(self.scenario_inference, "scenario_inference")
        object.__setattr__(self, "scenario_inference", scenarios)
        if not scenarios:
            raise ValueError("scenario_inference cannot be empty")
        for item in scenarios:
            _require_instance(
                item,
                ClinicalOutcomePatternMixtureScenarioInference,
                "scenario item",
            )
            if item.hidden_linkage_declared:
                required_metric = next(
                    comparison.metric
                    for comparison in item.closure_comparison
                    if comparison.closure_response_target_required
                )
                if required_metric is not self.closure_anchor_metric:
                    raise ValueError("scenario closure anchor metric changed")
            for mode in item.mode_inference:
                if mode.replicate_count != self.replicates:
                    raise ValueError("scenario replicate count is inconsistent")
                for metric in mode.metric_inference:
                    if (
                        tuple(grid_item.log_imor for grid_item in metric.grid_inference)
                        != self.log_imor_grid
                    ):
                        raise ValueError("scenario log-IMOR grid changed")
                    for grid_item in (
                        *metric.grid_inference,
                        metric.truth_aligned_inference,
                    ):
                        if (
                            grid_item.interval_yield.confidence_level
                            != self.monte_carlo_confidence_level
                            or grid_item.maximum_absolute_bias
                            != self.maximum_absolute_bias
                            or grid_item.coverage_target != self.coverage_target
                            or grid_item.minimum_interval_yield
                            != self.minimum_interval_yield
                            or grid_item.standard_error_calibration_lower
                            != self.standard_error_calibration_lower
                            or grid_item.standard_error_calibration_upper
                            != self.standard_error_calibration_upper
                        ):
                            raise ValueError("nested calibration target changed")
            for comparison in item.closure_comparison:
                if (
                    comparison.minimum_hidden_linkage_coverage_gain
                    != self.minimum_hidden_linkage_coverage_gain
                    or comparison.minimum_hidden_linkage_standard_error_ratio
                    != self.minimum_hidden_linkage_standard_error_ratio
                ):
                    raise ValueError("nested closure target changed")
        if tuple(item.scenario_id for item in scenarios) != tuple(
            sorted(item.scenario_id for item in scenarios)
        ):
            raise ValueError("scenario_inference must use canonical order")
        for field_name in (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "cluster_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "sampling_uncertainty_intervals_included",
            "automatic_dependence_closure_included",
            "latent_truth_used_for_operational_grid",
            "identification_and_sampling_uncertainty_separated",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if (
            not self.aggregate_simulation_only
            or self.replicate_level_records_included
            or self.cluster_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or not self.sampling_uncertainty_intervals_included
            or self.automatic_dependence_closure_included
            or self.latent_truth_used_for_operational_grid
            or not self.identification_and_sampling_uncertainty_separated
        ):
            raise ValueError(
                "pattern-mixture uncertainty report crossed its claim boundary"
            )
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required pattern-mixture uncertainty limitations changed")

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
        return _round_metric(math.sqrt(max(numerator, 0.0) / (self.count - 1)))

    def root_mean_square(self) -> float | None:
        if self.count == 0:
            return None
        return _round_metric(math.sqrt(self.squared_total / self.count))


class _GridAccumulator:
    def __init__(self) -> None:
        self.points = _MomentAccumulator()
        self.standard_errors = _MomentAccumulator()
        self.widths = _MomentAccumulator()
        self.model_covered = 0
        self.population_covered = 0
        self.status_counts: Counter[ClinicalOutcomePatternMixtureJackknifeStatus] = (
            Counter()
        )

    def add_point(self, value: float) -> None:
        self.points.add(value)

    def add_failure(self, status: ClinicalOutcomePatternMixtureJackknifeStatus) -> None:
        self.status_counts[status] += 1

    def add_interval(
        self,
        *,
        standard_error: float,
        width: float,
        model_covered: bool,
        population_covered: bool,
    ) -> None:
        self.standard_errors.add(standard_error)
        self.widths.add(width)
        self.model_covered += int(model_covered)
        self.population_covered += int(population_covered)
        self.status_counts[ClinicalOutcomePatternMixtureJackknifeStatus.COMPUTED] += 1


@dataclass(frozen=True, slots=True)
class _ScenarioLayout:
    prediction_strata: tuple[tuple[float, float], ...]
    unit_indices_by_nominal_cluster: tuple[tuple[int, ...], ...]
    stratum_index_by_unit: tuple[int, ...]
    stratum_totals: tuple[int, ...]
    unit_group_by_mode: Mapping[ClinicalOutcomeStressAnalysisMode, tuple[int, ...]]
    group_stratum_totals_by_mode: Mapping[
        ClinicalOutcomeStressAnalysisMode,
        tuple[tuple[int, ...], ...],
    ]
    structure_by_mode: Mapping[
        ClinicalOutcomeStressAnalysisMode, ClinicalOutcomeDesignStructure
    ]

    @property
    def unit_count(self) -> int:
        return len(self.stratum_index_by_unit)


def _scenario_layout(scenario: ClinicalOutcomeStressScenario) -> _ScenarioLayout:
    prediction_pattern = tuple(
        zip(
            scenario.policy_a_probability_pattern,
            scenario.policy_b_probability_pattern,
            strict=True,
        )
    )
    prediction_strata = tuple(dict.fromkeys(prediction_pattern))
    stratum_by_prediction = {
        prediction: index for index, prediction in enumerate(prediction_strata)
    }
    unit_indices_by_nominal_cluster: list[tuple[int, ...]] = []
    stratum_index_by_unit: list[int] = []
    for cluster_size in scenario.nominal_cluster_sizes:
        cluster_units: list[int] = []
        for within_cluster_index in range(cluster_size):
            cluster_units.append(len(stratum_index_by_unit))
            stratum_index_by_unit.append(
                stratum_by_prediction[
                    prediction_pattern[within_cluster_index % len(prediction_pattern)]
                ]
            )
        unit_indices_by_nominal_cluster.append(tuple(cluster_units))
    stratum_totals = tuple(
        stratum_index_by_unit.count(index) for index in range(len(prediction_strata))
    )
    nominal_group_by_unit = [0] * len(stratum_index_by_unit)
    for nominal_index, unit_indices in enumerate(unit_indices_by_nominal_cluster):
        for unit_index in unit_indices:
            nominal_group_by_unit[unit_index] = nominal_index
    block_by_nominal_cluster = {
        nominal_index: block_index
        for block_index, block in enumerate(scenario.dependence_blocks)
        for nominal_index in block
    }
    closed_group_by_unit = tuple(
        block_by_nominal_cluster[nominal_group_by_unit[unit_index]]
        for unit_index in range(len(stratum_index_by_unit))
    )
    unit_groups = {
        ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS: tuple(
            nominal_group_by_unit
        ),
        ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS: closed_group_by_unit,
    }
    group_totals: dict[
        ClinicalOutcomeStressAnalysisMode,
        tuple[tuple[int, ...], ...],
    ] = {}
    structures: dict[
        ClinicalOutcomeStressAnalysisMode, ClinicalOutcomeDesignStructure
    ] = {}
    for mode, group_by_unit in unit_groups.items():
        group_count = max(group_by_unit) + 1
        rows = [[0] * len(prediction_strata) for _ in range(group_count)]
        for unit_index, group_index in enumerate(group_by_unit):
            rows[group_index][stratum_index_by_unit[unit_index]] += 1
        resolved = tuple(tuple(row) for row in rows)
        group_totals[mode] = resolved
        structures[mode] = _structure_from_sizes(tuple(sum(row) for row in resolved))
    return _ScenarioLayout(
        prediction_strata=prediction_strata,
        unit_indices_by_nominal_cluster=tuple(unit_indices_by_nominal_cluster),
        stratum_index_by_unit=tuple(stratum_index_by_unit),
        stratum_totals=stratum_totals,
        unit_group_by_mode=unit_groups,
        group_stratum_totals_by_mode=group_totals,
        structure_by_mode=structures,
    )


def _support_status(
    totals: Sequence[int],
    evaluable: Sequence[int],
    favorable: Sequence[int],
    *,
    leave_one_out: bool,
) -> ClinicalOutcomePatternMixtureJackknifeStatus | None:
    if any(
        total == 0 or observed == 0
        for total, observed in zip(totals, evaluable, strict=True)
    ):
        return (
            ClinicalOutcomePatternMixtureJackknifeStatus.LEAVE_ONE_OUT_EMPTY_REFERENCE_STRATUM
            if leave_one_out
            else ClinicalOutcomePatternMixtureJackknifeStatus.EMPTY_REFERENCE_STRATUM
        )
    if any(
        observed < total and successes in (0, observed)
        for total, observed, successes in zip(totals, evaluable, favorable, strict=True)
    ):
        return (
            ClinicalOutcomePatternMixtureJackknifeStatus.LEAVE_ONE_OUT_DEGENERATE_REFERENCE_STRATUM
            if leave_one_out
            else ClinicalOutcomePatternMixtureJackknifeStatus.DEGENERATE_REFERENCE_STRATUM
        )
    return None


def _full_metric_estimates(
    layout: _ScenarioLayout,
    evaluable: Sequence[int],
    favorable: Sequence[int],
    shifts: Sequence[float],
    scenario: ClinicalOutcomeStressScenario,
) -> dict[float, tuple[float, ...]]:
    result: dict[float, tuple[float, ...]] = {}
    for log_imor in shifts:
        estimates = {metric: 0.0 for metric in _METRIC_ORDER}
        for stratum_index, (probability_a, probability_b) in enumerate(
            layout.prediction_strata
        ):
            total = layout.stratum_totals[stratum_index]
            observed = evaluable[stratum_index]
            successes = favorable[stratum_index]
            observed_prevalence = successes / observed
            missing_prevalence = _odds_shift_probability(observed_prevalence, log_imor)
            population_prevalence = (
                successes + (total - observed) * missing_prevalence
            ) / total
            weight = total / layout.unit_count
            for metric in _METRIC_ORDER:
                estimates[metric] += weight * _expected_metric_value(
                    metric,
                    population_prevalence,
                    probability_a,
                    probability_b,
                    scenario.classification_threshold,
                )
        result[log_imor] = tuple(
            _round_metric(estimates[metric]) for metric in _METRIC_ORDER
        )
    return result


def _leave_one_out_metric_estimates(
    *,
    layout: _ScenarioLayout,
    scenario: ClinicalOutcomeStressScenario,
    mode: ClinicalOutcomeStressAnalysisMode,
    evaluable: Sequence[int],
    favorable: Sequence[int],
    group_evaluable: Sequence[Sequence[int]],
    group_favorable: Sequence[Sequence[int]],
    shifts: Sequence[float],
) -> tuple[
    ClinicalOutcomePatternMixtureJackknifeStatus | None,
    tuple[tuple[tuple[float, ...], ...], ...],
]:
    metric_zero: list[tuple[float, ...]] = []
    metric_slope: list[tuple[float, ...]] = []
    for probability_a, probability_b in layout.prediction_strata:
        values_zero = _metric_values(
            0.0,
            probability_a,
            probability_b,
            scenario.classification_threshold,
        )
        values_one = _metric_values(
            1.0,
            probability_a,
            probability_b,
            scenario.classification_threshold,
        )
        metric_zero.append(tuple(values_zero[metric] for metric in _METRIC_ORDER))
        metric_slope.append(
            tuple(values_one[metric] - values_zero[metric] for metric in _METRIC_ORDER)
        )
    leaveout_results: list[tuple[tuple[float, ...], ...]] = []
    group_totals = layout.group_stratum_totals_by_mode[mode]
    for group_index, removed_totals in enumerate(group_totals):
        totals = tuple(
            total - removed
            for total, removed in zip(
                layout.stratum_totals, removed_totals, strict=True
            )
        )
        observed = tuple(
            total - removed
            for total, removed in zip(
                evaluable,
                group_evaluable[group_index],
                strict=True,
            )
        )
        successes = tuple(
            total - removed
            for total, removed in zip(
                favorable,
                group_favorable[group_index],
                strict=True,
            )
        )
        support = _support_status(
            totals,
            observed,
            successes,
            leave_one_out=True,
        )
        if support is not None:
            return support, ()
        remaining_units = sum(totals)
        shift_results: list[tuple[float, ...]] = []
        for log_imor in shifts:
            estimates = [0.0] * len(_METRIC_ORDER)
            for stratum_index in range(len(layout.prediction_strata)):
                total = totals[stratum_index]
                reference = observed[stratum_index]
                reference_favorable = successes[stratum_index]
                missing_prevalence = _odds_shift_probability(
                    reference_favorable / reference,
                    log_imor,
                )
                population_prevalence = (
                    reference_favorable + (total - reference) * missing_prevalence
                ) / total
                weight = total / remaining_units
                intercepts = metric_zero[stratum_index]
                slopes = metric_slope[stratum_index]
                for metric_index in range(len(_METRIC_ORDER)):
                    estimates[metric_index] += weight * (
                        intercepts[metric_index]
                        + slopes[metric_index] * population_prevalence
                    )
            shift_results.append(tuple(estimates))
        leaveout_results.append(tuple(shift_results))
    return None, tuple(leaveout_results)


def _model_functional_truths(
    scenario: ClinicalOutcomeStressScenario,
    layout: _ScenarioLayout,
    shifts: Sequence[float],
) -> tuple[dict[float, tuple[float, ...]], tuple[float, ...]]:
    truth = _scenario_truth(scenario)
    population_truth = tuple(
        next(
            item.population_value
            for item in truth.metric_truths
            if item.metric is metric
        )
        for metric in _METRIC_ORDER
    )
    model_truths: dict[float, tuple[float, ...]] = {}
    for log_imor in shifts:
        missing_prevalence = _odds_shift_probability(
            truth.evaluable_favorable_prevalence,
            log_imor,
        )
        model_prevalence = (
            truth.expected_evaluable_probability * truth.evaluable_favorable_prevalence
            + (1.0 - truth.expected_evaluable_probability) * missing_prevalence
        )
        estimates = {metric: 0.0 for metric in _METRIC_ORDER}
        for stratum_index, (probability_a, probability_b) in enumerate(
            layout.prediction_strata
        ):
            weight = layout.stratum_totals[stratum_index] / layout.unit_count
            for metric in _METRIC_ORDER:
                estimates[metric] += weight * _expected_metric_value(
                    metric,
                    model_prevalence,
                    probability_a,
                    probability_b,
                    scenario.classification_threshold,
                )
        model_truths[log_imor] = tuple(
            _round_metric(estimates[metric]) for metric in _METRIC_ORDER
        )
    return model_truths, population_truth


def _mode_design_status(
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    structure: ClinicalOutcomeDesignStructure,
) -> ClinicalOutcomePatternMixtureJackknifeStatus | None:
    if structure.cluster_count < protocol.minimum_clusters:
        return ClinicalOutcomePatternMixtureJackknifeStatus.INSUFFICIENT_CLUSTERS
    if structure.maximum_cluster_fraction > protocol.maximum_cluster_unit_fraction:
        return ClinicalOutcomePatternMixtureJackknifeStatus.DOMINANT_CLUSTER
    return None


def _prior_metric(
    result: Any,
    metric: ClinicalOutcomeDesignMetric,
) -> ClinicalOutcomePatternMixtureMetricPerformance:
    return next(item for item in result.metric_performance if item.metric is metric)


def _finalize_grid_inference(
    *,
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    metric: ClinicalOutcomeDesignMetric,
    log_imor: float,
    model_truth: float,
    population_truth: float,
    prior_mean: float | None,
    accumulator: _GridAccumulator,
    replicate_count: int,
) -> ClinicalOutcomePatternMixtureGridInference:
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
    model_coverage = _design_rate(
        accumulator.model_covered,
        interval_count,
        protocol.monte_carlo_confidence_level,
    )
    population_coverage = _design_rate(
        accumulator.population_covered,
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
        and absolute_bias_upper <= pattern_protocol.maximum_absolute_bias
    )
    yield_met = (
        interval_yield.lower is not None
        and interval_yield.lower >= protocol.minimum_interval_yield
    )
    coverage_met = (
        model_coverage.lower is not None
        and model_coverage.lower >= protocol.coverage_target
    )
    se_met = (
        se_ratio is not None
        and protocol.standard_error_calibration_lower
        <= se_ratio
        <= protocol.standard_error_calibration_upper
    )
    return ClinicalOutcomePatternMixtureGridInference(
        metric=metric,
        log_imor=log_imor,
        informative_missingness_odds_ratio=_round_metric(math.exp(log_imor)),
        model_functional_true_value=model_truth,
        population_true_value=population_truth,
        replicate_count=replicate_count,
        point_estimate_count=accumulator.points.count,
        interval_count=interval_count,
        model_functional_covered_count=accumulator.model_covered,
        population_truth_covered_count=accumulator.population_covered,
        interval_yield=interval_yield,
        model_functional_coverage=model_coverage,
        population_truth_coverage=population_coverage,
        prior_pattern_mixture_mean_estimate=prior_mean,
        mean_estimate=mean_estimate,
        model_functional_bias=bias,
        empirical_standard_deviation=empirical_sd,
        monte_carlo_bias_lower=bias_bounds[0],
        monte_carlo_bias_upper=bias_bounds[1],
        monte_carlo_absolute_bias_upper=absolute_bias_upper,
        root_mean_squared_jackknife_standard_error=rms_se,
        mean_jackknife_standard_error=mean_se,
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
        model_functional_coverage_target_met=coverage_met,
        standard_error_calibration_target_met=se_met,
        calibration_target_met=bias_met and yield_met and coverage_met and se_met,
        status_counts=_status_count_records(accumulator.status_counts),
    )


def _simulate_scenario(
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    pattern_report: ClinicalOutcomePatternMixtureReport,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
) -> ClinicalOutcomePatternMixtureScenarioInference:
    layout = _scenario_layout(scenario)
    true_log_imor = _true_log_imor(scenario)
    shifts = tuple(dict.fromkeys((*pattern_protocol.log_imor_grid, true_log_imor)))
    model_truths, population_truth = _model_functional_truths(scenario, layout, shifts)
    true_model_truth = model_truths[true_log_imor]
    if true_model_truth != population_truth:
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            f"scenario {scenario.scenario_id!r} truth-aligned model functional changed"
        )
    accumulators = {
        mode: {
            metric: {
                "grid": {
                    shift: _GridAccumulator()
                    for shift in pattern_protocol.log_imor_grid
                },
                "truth": _GridAccumulator(),
            }
            for metric in _METRIC_ORDER
        }
        for mode in protocol.analysis_modes
    }
    stream_sha256 = _scenario_stream_sha256(stress_protocol, scenario)
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(stream_sha256, "evaluability")
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    design_status = {
        mode: _mode_design_status(protocol, layout.structure_by_mode[mode])
        for mode in protocol.analysis_modes
    }
    critical = NormalDist().inv_cdf(0.5 + protocol.confidence_level / 2.0)

    for _ in range(stress_protocol.replicates):
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
        group_evaluable = {
            mode: [
                [0] * len(layout.prediction_strata)
                for _ in layout.group_stratum_totals_by_mode[mode]
            ]
            for mode in protocol.analysis_modes
        }
        group_favorable = {
            mode: [
                [0] * len(layout.prediction_strata)
                for _ in layout.group_stratum_totals_by_mode[mode]
            ]
            for mode in protocol.analysis_modes
        }
        for unit_index, label in enumerate(labels):
            evaluable_probability = (
                scenario.favorable_evaluable_probability
                if label == 1.0
                else scenario.unfavorable_evaluable_probability
            )
            if evaluability_rng.random() >= evaluable_probability:
                continue
            stratum_index = layout.stratum_index_by_unit[unit_index]
            favorable = int(label)
            stratum_evaluable[stratum_index] += 1
            stratum_favorable[stratum_index] += favorable
            for mode in protocol.analysis_modes:
                group_index = layout.unit_group_by_mode[mode][unit_index]
                group_evaluable[mode][group_index][stratum_index] += 1
                group_favorable[mode][group_index][stratum_index] += favorable

        full_support = _support_status(
            layout.stratum_totals,
            stratum_evaluable,
            stratum_favorable,
            leave_one_out=False,
        )
        if full_support is not None:
            for mode in protocol.analysis_modes:
                for metric in _METRIC_ORDER:
                    for accumulator in (
                        *accumulators[mode][metric]["grid"].values(),
                        accumulators[mode][metric]["truth"],
                    ):
                        accumulator.add_failure(full_support)
            continue

        full_estimates = _full_metric_estimates(
            layout,
            stratum_evaluable,
            stratum_favorable,
            shifts,
            scenario,
        )
        for mode in protocol.analysis_modes:
            for metric_index, metric in enumerate(_METRIC_ORDER):
                for log_imor in pattern_protocol.log_imor_grid:
                    accumulators[mode][metric]["grid"][log_imor].add_point(
                        full_estimates[log_imor][metric_index]
                    )
                accumulators[mode][metric]["truth"].add_point(
                    full_estimates[true_log_imor][metric_index]
                )
            if design_status[mode] is not None:
                assert design_status[mode] is not None
                for metric in _METRIC_ORDER:
                    for accumulator in (
                        *accumulators[mode][metric]["grid"].values(),
                        accumulators[mode][metric]["truth"],
                    ):
                        accumulator.add_failure(design_status[mode])
                continue
            leaveout_status, leaveout_estimates = _leave_one_out_metric_estimates(
                layout=layout,
                scenario=scenario,
                mode=mode,
                evaluable=stratum_evaluable,
                favorable=stratum_favorable,
                group_evaluable=group_evaluable[mode],
                group_favorable=group_favorable[mode],
                shifts=shifts,
            )
            if leaveout_status is not None:
                for metric in _METRIC_ORDER:
                    for accumulator in (
                        *accumulators[mode][metric]["grid"].values(),
                        accumulators[mode][metric]["truth"],
                    ):
                        accumulator.add_failure(leaveout_status)
                continue
            group_count = len(leaveout_estimates)
            shift_index = {shift: index for index, shift in enumerate(shifts)}
            for log_imor in shifts:
                log_index = shift_index[log_imor]
                for metric_index, metric in enumerate(_METRIC_ORDER):
                    leaveout_values = tuple(
                        group[log_index][metric_index] for group in leaveout_estimates
                    )
                    leaveout_mean = sum(leaveout_values) / group_count
                    variance = (
                        (group_count - 1)
                        / group_count
                        * sum((value - leaveout_mean) ** 2 for value in leaveout_values)
                    )
                    standard_error = math.sqrt(max(variance, 0.0))
                    target_accumulators: list[_GridAccumulator] = []
                    if log_imor in pattern_protocol.log_imor_grid:
                        target_accumulators.append(
                            accumulators[mode][metric]["grid"][log_imor]
                        )
                    if log_imor == true_log_imor:
                        target_accumulators.append(accumulators[mode][metric]["truth"])
                    if _round_metric(standard_error) == 0.0:
                        for accumulator in target_accumulators:
                            accumulator.add_failure(
                                ClinicalOutcomePatternMixtureJackknifeStatus.ZERO_JACKKNIFE_VARIANCE
                            )
                        continue
                    point_estimate = full_estimates[log_imor][metric_index]
                    lower_bound, upper_bound = _metric_bounds(metric)
                    interval_lower = max(
                        lower_bound,
                        point_estimate - critical * standard_error,
                    )
                    interval_upper = min(
                        upper_bound,
                        point_estimate + critical * standard_error,
                    )
                    model_truth = model_truths[log_imor][metric_index]
                    population_value = population_truth[metric_index]
                    width = interval_upper - interval_lower
                    for accumulator in target_accumulators:
                        accumulator.add_interval(
                            standard_error=standard_error,
                            width=width,
                            model_covered=(
                                interval_lower - 1e-12
                                <= model_truth
                                <= interval_upper + 1e-12
                            ),
                            population_covered=(
                                interval_lower - 1e-12
                                <= population_value
                                <= interval_upper + 1e-12
                            ),
                        )

    prior_scenario = next(
        item
        for item in pattern_report.scenario_results
        if item.scenario_id == scenario.scenario_id
    )
    modes: list[ClinicalOutcomePatternMixtureModeInference] = []
    for mode in protocol.analysis_modes:
        metrics: list[ClinicalOutcomePatternMixtureMetricInference] = []
        for metric_index, metric in enumerate(_METRIC_ORDER):
            prior = _prior_metric(prior_scenario, metric)
            prior_grid = {
                item.log_imor: item.mean_estimate for item in prior.grid_performance
            }
            grid_inference = tuple(
                _finalize_grid_inference(
                    protocol=protocol,
                    pattern_protocol=pattern_protocol,
                    metric=metric,
                    log_imor=log_imor,
                    model_truth=model_truths[log_imor][metric_index],
                    population_truth=population_truth[metric_index],
                    prior_mean=prior_grid[log_imor],
                    accumulator=accumulators[mode][metric]["grid"][log_imor],
                    replicate_count=stress_protocol.replicates,
                )
                for log_imor in pattern_protocol.log_imor_grid
            )
            truth_inference = _finalize_grid_inference(
                protocol=protocol,
                pattern_protocol=pattern_protocol,
                metric=metric,
                log_imor=true_log_imor,
                model_truth=true_model_truth[metric_index],
                population_truth=population_truth[metric_index],
                prior_mean=prior.truth_aligned_mean_estimate,
                accumulator=accumulators[mode][metric]["truth"],
                replicate_count=stress_protocol.replicates,
            )
            all_grid = all(item.calibration_target_met for item in grid_inference)
            truth_coverage = (
                truth_inference.population_truth_coverage.lower is not None
                and truth_inference.population_truth_coverage.lower
                >= protocol.coverage_target
            )
            metrics.append(
                ClinicalOutcomePatternMixtureMetricInference(
                    metric=metric,
                    grid_inference=grid_inference,
                    truth_aligned_inference=truth_inference,
                    all_grid_calibration_targets_met=all_grid,
                    truth_aligned_population_coverage_target_met=truth_coverage,
                    research_target_met=(
                        all_grid
                        and truth_coverage
                        and truth_inference.calibration_target_met
                    ),
                )
            )
        modes.append(
            ClinicalOutcomePatternMixtureModeInference(
                analysis_mode=mode,
                analysis_structure=layout.structure_by_mode[mode],
                replicate_count=stress_protocol.replicates,
                metric_inference=tuple(metrics),
                all_metric_research_targets_met=all(
                    item.research_target_met for item in metrics
                ),
            )
        )

    nominal = next(
        item
        for item in modes
        if item.analysis_mode is ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS
    )
    closed = next(
        item
        for item in modes
        if item.analysis_mode
        is ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
    )
    hidden_linkage = any(len(block) > 1 for block in scenario.dependence_blocks)
    comparisons: list[ClinicalOutcomePatternMixtureClosureComparison] = []
    for metric_index, metric in enumerate(_METRIC_ORDER):
        nominal_metric = nominal.metric_inference[metric_index]
        closed_metric = closed.metric_inference[metric_index]
        nominal_truth = nominal_metric.truth_aligned_inference
        closed_truth = closed_metric.truth_aligned_inference
        nominal_coverage = nominal_truth.model_functional_coverage.rate
        closed_coverage = closed_truth.model_functional_coverage.rate
        coverage_gain = (
            None
            if nominal_coverage is None or closed_coverage is None
            else _round_metric(closed_coverage - nominal_coverage)
        )
        nominal_rms = nominal_truth.root_mean_squared_jackknife_standard_error
        closed_rms = closed_truth.root_mean_squared_jackknife_standard_error
        se_ratio = (
            None
            if nominal_rms in (None, 0.0) or closed_rms is None
            else _round_metric(closed_rms / nominal_rms)
        )
        equivalence_expected = not hidden_linkage
        equivalence_met = nominal_metric == closed_metric
        response_required = (
            equivalence_expected or metric is protocol.closure_anchor_metric
        )
        response_met = (
            equivalence_met
            if equivalence_expected
            else True
            if not response_required
            else (
                coverage_gain is not None
                and coverage_gain >= protocol.minimum_hidden_linkage_coverage_gain
                and se_ratio is not None
                and se_ratio >= protocol.minimum_hidden_linkage_standard_error_ratio
            )
        )
        comparisons.append(
            ClinicalOutcomePatternMixtureClosureComparison(
                metric=metric,
                true_log_imor=true_log_imor,
                nominal_model_functional_coverage=nominal_coverage,
                dependence_closed_model_functional_coverage=closed_coverage,
                dependence_closed_minus_nominal_coverage=coverage_gain,
                dependence_closed_to_nominal_standard_error_ratio=se_ratio,
                minimum_hidden_linkage_coverage_gain=(
                    protocol.minimum_hidden_linkage_coverage_gain
                ),
                minimum_hidden_linkage_standard_error_ratio=(
                    protocol.minimum_hidden_linkage_standard_error_ratio
                ),
                closure_response_target_required=response_required,
                exact_equivalence_expected=equivalence_expected,
                exact_equivalence_met=equivalence_met,
                closure_response_target_met=response_met,
            )
        )
    truth = _scenario_truth(scenario)
    closed_targets = closed.all_metric_research_targets_met
    response_targets = all(item.closure_response_target_met for item in comparisons)
    return ClinicalOutcomePatternMixtureScenarioInference(
        scenario_id=scenario.scenario_id,
        stage=scenario.stage,
        endpoint_family=scenario.endpoint_family,
        population_favorable_prevalence=truth.population_favorable_prevalence,
        evaluable_favorable_prevalence=truth.evaluable_favorable_prevalence,
        expected_evaluable_probability=truth.expected_evaluable_probability,
        true_log_imor=true_log_imor,
        true_informative_missingness_odds_ratio=_round_metric(math.exp(true_log_imor)),
        hidden_linkage_declared=hidden_linkage,
        mode_inference=tuple(modes),
        closure_comparison=tuple(comparisons),
        dependence_closed_all_research_targets_met=closed_targets,
        all_closure_response_targets_met=response_targets,
        research_target_met=closed_targets and response_targets,
        rng_stream_sha256=stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
    )


def _work_units(
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> int:
    return stress_protocol.replicates * sum(
        sum(scenario.nominal_cluster_sizes)
        + sum(
            (
                len(scenario.nominal_cluster_sizes)
                if mode is ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS
                else len(scenario.dependence_blocks)
            )
            * (len(pattern_protocol.log_imor_grid) + 1)
            * len(
                set(
                    zip(
                        scenario.policy_a_probability_pattern,
                        scenario.policy_b_probability_pattern,
                        strict=True,
                    )
                )
            )
            * len(_METRIC_ORDER)
            for mode in protocol.analysis_modes
        )
        for scenario in stress_protocol.scenarios
    )


def analyze_clinical_outcome_pattern_mixture_uncertainty(
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    pattern_mixture_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomePatternMixtureUncertaintyReport:
    """Replay a bound sensitivity study and add cluster-jackknife intervals."""

    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureUncertaintyProtocol,
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
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            "uncertainty protocol is not bound to the stress protocol"
        )
    if (
        protocol.pattern_mixture_protocol_fingerprint
        != pattern_mixture_protocol.fingerprint
    ):
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            "uncertainty protocol is not bound to the pattern-mixture protocol"
        )
    if (
        pattern_mixture_protocol.stress_protocol_fingerprint
        != stress_protocol.fingerprint
    ):
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            "pattern-mixture and stress protocols are not mutually bound"
        )
    if (
        _work_units(protocol, pattern_mixture_protocol, stress_protocol)
        > MAX_DESIGN_WORK_UNITS
    ):
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            "pattern-mixture uncertainty analysis exceeds the bounded work budget"
        )
    pattern_report = analyze_clinical_outcome_pattern_mixture(
        pattern_mixture_protocol,
        stress_protocol,
    )
    if protocol.pattern_mixture_report_fingerprint != pattern_report.fingerprint:
        raise ClinicalOutcomePatternMixtureUncertaintyError(
            "uncertainty protocol is not bound to the replayed pattern-mixture report"
        )
    return ClinicalOutcomePatternMixtureUncertaintyReport(
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
        replicates=stress_protocol.replicates,
        log_imor_grid=pattern_mixture_protocol.log_imor_grid,
        analysis_modes=protocol.analysis_modes,
        confidence_level=protocol.confidence_level,
        monte_carlo_confidence_level=protocol.monte_carlo_confidence_level,
        coverage_target=protocol.coverage_target,
        minimum_interval_yield=protocol.minimum_interval_yield,
        minimum_clusters=protocol.minimum_clusters,
        maximum_cluster_unit_fraction=protocol.maximum_cluster_unit_fraction,
        maximum_absolute_bias=pattern_mixture_protocol.maximum_absolute_bias,
        standard_error_calibration_lower=protocol.standard_error_calibration_lower,
        standard_error_calibration_upper=protocol.standard_error_calibration_upper,
        closure_anchor_metric=protocol.closure_anchor_metric,
        minimum_hidden_linkage_coverage_gain=(
            protocol.minimum_hidden_linkage_coverage_gain
        ),
        minimum_hidden_linkage_standard_error_ratio=(
            protocol.minimum_hidden_linkage_standard_error_ratio
        ),
        scenario_inference=tuple(
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


def validate_clinical_outcome_pattern_mixture_uncertainty_report(
    report: ClinicalOutcomePatternMixtureUncertaintyReport,
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
    pattern_mixture_protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> tuple[str, ...]:
    """Replay the complete seeded jackknife study and compare the report."""

    try:
        rebuilt = analyze_clinical_outcome_pattern_mixture_uncertainty(
            protocol,
            pattern_mixture_protocol,
            stress_protocol,
        )
    except (ClinicalOutcomePatternMixtureUncertaintyError, TypeError, ValueError):
        return ("pattern_mixture_uncertainty_replay_failed",)
    return () if rebuilt == report else ("pattern_mixture_uncertainty_report_mismatch",)


def _rate_projection(value: ClinicalOutcomeDesignRate) -> dict[str, Any]:
    return {
        "event_count": value.event_count,
        "total_count": value.total_count,
        "rate": value.rate,
        "lower": value.lower,
        "upper": value.upper,
    }


def clinical_outcome_pattern_mixture_uncertainty_summary(
    report: ClinicalOutcomePatternMixtureUncertaintyReport,
) -> dict[str, Any]:
    """Return compact calibration, closure, and claim-boundary diagnostics."""

    _require_instance(
        report,
        ClinicalOutcomePatternMixtureUncertaintyReport,
        "report",
    )
    scenarios = []
    for scenario in report.scenario_inference:
        modes = []
        for mode in scenario.mode_inference:
            grid_items = [
                grid
                for metric in mode.metric_inference
                for grid in metric.grid_inference
            ]
            coverage_lowers = [
                item.model_functional_coverage.lower
                for item in grid_items
                if item.model_functional_coverage.lower is not None
            ]
            yield_lowers = [
                item.interval_yield.lower
                for item in grid_items
                if item.interval_yield.lower is not None
            ]
            se_ratios = [
                item.standard_error_to_empirical_sd_ratio
                for item in grid_items
                if item.standard_error_to_empirical_sd_ratio is not None
            ]
            modes.append(
                {
                    "analysis_mode": mode.analysis_mode.value,
                    "analysis_cluster_count": mode.analysis_structure.cluster_count,
                    "maximum_cluster_unit_fraction": (
                        mode.analysis_structure.maximum_cluster_fraction
                    ),
                    "minimum_grid_model_functional_coverage_lower": (
                        None if not coverage_lowers else min(coverage_lowers)
                    ),
                    "minimum_grid_interval_yield_lower": (
                        None if not yield_lowers else min(yield_lowers)
                    ),
                    "standard_error_calibration_ratio_range": {
                        "minimum": None if not se_ratios else min(se_ratios),
                        "maximum": None if not se_ratios else max(se_ratios),
                    },
                    "all_metric_research_targets_met": (
                        mode.all_metric_research_targets_met
                    ),
                    "truth_aligned_metrics": [
                        {
                            "metric": metric.metric.value,
                            "interval_yield": _rate_projection(
                                metric.truth_aligned_inference.interval_yield
                            ),
                            "model_functional_coverage": _rate_projection(
                                metric.truth_aligned_inference.model_functional_coverage
                            ),
                            "population_truth_coverage": _rate_projection(
                                metric.truth_aligned_inference.population_truth_coverage
                            ),
                            "standard_error_to_empirical_sd_ratio": (
                                metric.truth_aligned_inference.standard_error_to_empirical_sd_ratio
                            ),
                            "research_target_met": metric.research_target_met,
                        }
                        for metric in mode.metric_inference
                    ],
                }
            )
        scenarios.append(
            {
                "scenario_id": scenario.scenario_id,
                "stage": scenario.stage.value,
                "endpoint_family": scenario.endpoint_family,
                "true_log_imor": scenario.true_log_imor,
                "hidden_linkage_declared": scenario.hidden_linkage_declared,
                "modes": modes,
                "closure_comparisons": [
                    {
                        "metric": item.metric.value,
                        "dependence_closed_minus_nominal_coverage": (
                            item.dependence_closed_minus_nominal_coverage
                        ),
                        "dependence_closed_to_nominal_standard_error_ratio": (
                            item.dependence_closed_to_nominal_standard_error_ratio
                        ),
                        "closure_response_target_required": (
                            item.closure_response_target_required
                        ),
                        "exact_equivalence_expected": item.exact_equivalence_expected,
                        "exact_equivalence_met": item.exact_equivalence_met,
                        "closure_response_target_met": (
                            item.closure_response_target_met
                        ),
                    }
                    for item in scenario.closure_comparison
                ],
                "dependence_closed_all_research_targets_met": (
                    scenario.dependence_closed_all_research_targets_met
                ),
                "all_closure_response_targets_met": (
                    scenario.all_closure_response_targets_met
                ),
                "research_target_met": scenario.research_target_met,
            }
        )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_SUMMARY_SCHEMA_VERSION
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
        "replicates": report.replicates,
        "log_imor_grid": list(report.log_imor_grid),
        "targets": {
            "confidence_level": report.confidence_level,
            "coverage_target": report.coverage_target,
            "minimum_interval_yield": report.minimum_interval_yield,
            "minimum_clusters": report.minimum_clusters,
            "maximum_cluster_unit_fraction": report.maximum_cluster_unit_fraction,
            "maximum_absolute_bias": report.maximum_absolute_bias,
            "standard_error_calibration_lower": (
                report.standard_error_calibration_lower
            ),
            "standard_error_calibration_upper": (
                report.standard_error_calibration_upper
            ),
            "closure_anchor_metric": report.closure_anchor_metric.value,
            "minimum_hidden_linkage_coverage_gain": (
                report.minimum_hidden_linkage_coverage_gain
            ),
            "minimum_hidden_linkage_standard_error_ratio": (
                report.minimum_hidden_linkage_standard_error_ratio
            ),
        },
        "all_scenarios_research_targets_met": all(
            item.research_target_met for item in report.scenario_inference
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
            "sampling_uncertainty_intervals_included": (
                report.sampling_uncertainty_intervals_included
            ),
            "automatic_dependence_closure_included": (
                report.automatic_dependence_closure_included
            ),
            "latent_truth_used_for_operational_grid": (
                report.latent_truth_used_for_operational_grid
            ),
            "identification_and_sampling_uncertainty_separated": (
                report.identification_and_sampling_uncertainty_separated
            ),
        },
    }


def clinical_outcome_pattern_mixture_uncertainty_validation_summary(
    report: ClinicalOutcomePatternMixtureUncertaintyReport,
    *,
    failures: Sequence[str] = (),
    scope: str,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureUncertaintyReport,
        "report",
    )
    _require_text(scope, "scope")
    resolved_failures = tuple(str(item) for item in failures)
    return {
        "schema_version": (
            "adds.clinical-outcome-pattern-mixture-uncertainty-validation-summary.v1"
        ),
        "valid": not resolved_failures,
        "scope": scope,
        "report_fingerprint": report.fingerprint,
        "failures": list(resolved_failures),
    }


def clinical_outcome_pattern_mixture_uncertainty_protocol_envelope(
    protocol: ClinicalOutcomePatternMixtureUncertaintyProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureUncertaintyProtocol,
        "protocol",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION
        ),
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_pattern_mixture_uncertainty_report_envelope(
    report: ClinicalOutcomePatternMixtureUncertaintyReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureUncertaintyReport,
        "report",
    )
    return {
        "schema_version": (
            CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    if _sha256(value) != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def clinical_outcome_pattern_mixture_uncertainty_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureUncertaintyProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_uncertainty_protocol_envelope",
        schema_version=(
            CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_PROTOCOL_SCHEMA_VERSION
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
            "analysis_modes",
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_tolerance",
            "minimum_interval_yield",
            "minimum_clusters",
            "maximum_cluster_unit_fraction",
            "maximum_standard_error_calibration_deviation",
            "closure_anchor_metric",
            "minimum_hidden_linkage_coverage_gain",
            "minimum_hidden_linkage_standard_error_ratio",
            "method_id",
            "metadata",
        },
    )
    protocol = ClinicalOutcomePatternMixtureUncertaintyProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        stress_protocol_fingerprint=data["stress_protocol_fingerprint"],
        pattern_mixture_protocol_fingerprint=(
            data["pattern_mixture_protocol_fingerprint"]
        ),
        pattern_mixture_report_fingerprint=data["pattern_mixture_report_fingerprint"],
        analysis_modes=tuple(
            _parse_enum(
                ClinicalOutcomeStressAnalysisMode,
                item,
                f"protocol.analysis_modes[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["analysis_modes"], "protocol.analysis_modes")
            )
        ),
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        coverage_tolerance=data["coverage_tolerance"],
        minimum_interval_yield=data["minimum_interval_yield"],
        minimum_clusters=data["minimum_clusters"],
        maximum_cluster_unit_fraction=data["maximum_cluster_unit_fraction"],
        maximum_standard_error_calibration_deviation=(
            data["maximum_standard_error_calibration_deviation"]
        ),
        closure_anchor_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["closure_anchor_metric"],
            "protocol.closure_anchor_metric",
        ),
        minimum_hidden_linkage_coverage_gain=(
            data["minimum_hidden_linkage_coverage_gain"]
        ),
        minimum_hidden_linkage_standard_error_ratio=(
            data["minimum_hidden_linkage_standard_error_ratio"]
        ),
        method_id=data["method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "pattern-mixture uncertainty protocol")
    return protocol


def _parse_status_count(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureJackknifeStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomePatternMixtureJackknifeStatusCount(
        status=_parse_enum(
            ClinicalOutcomePatternMixtureJackknifeStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_grid_inference(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureGridInference:
    fields = {
        "metric",
        "log_imor",
        "informative_missingness_odds_ratio",
        "model_functional_true_value",
        "population_true_value",
        "replicate_count",
        "point_estimate_count",
        "interval_count",
        "model_functional_covered_count",
        "population_truth_covered_count",
        "interval_yield",
        "model_functional_coverage",
        "population_truth_coverage",
        "prior_pattern_mixture_mean_estimate",
        "mean_estimate",
        "model_functional_bias",
        "empirical_standard_deviation",
        "monte_carlo_bias_lower",
        "monte_carlo_bias_upper",
        "monte_carlo_absolute_bias_upper",
        "root_mean_squared_jackknife_standard_error",
        "mean_jackknife_standard_error",
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
        "model_functional_coverage_target_met",
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
            "metric",
            "interval_yield",
            "model_functional_coverage",
            "population_truth_coverage",
            "status_counts",
        }
    }
    return ClinicalOutcomePatternMixtureGridInference(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        interval_yield=_parse_design_rate(
            data["interval_yield"], f"{path}.interval_yield"
        ),
        model_functional_coverage=_parse_design_rate(
            data["model_functional_coverage"],
            f"{path}.model_functional_coverage",
        ),
        population_truth_coverage=_parse_design_rate(
            data["population_truth_coverage"],
            f"{path}.population_truth_coverage",
        ),
        status_counts=tuple(
            _parse_status_count(item, f"{path}.status_counts[{index}]")
            for index, item in enumerate(
                _sequence(data["status_counts"], f"{path}.status_counts")
            )
        ),
        **scalar,
    )


def _parse_metric_inference(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureMetricInference:
    data = _record(
        value,
        path,
        {
            "metric",
            "grid_inference",
            "truth_aligned_inference",
            "all_grid_calibration_targets_met",
            "truth_aligned_population_coverage_target_met",
            "research_target_met",
        },
    )
    return ClinicalOutcomePatternMixtureMetricInference(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        grid_inference=tuple(
            _parse_grid_inference(item, f"{path}.grid_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["grid_inference"], f"{path}.grid_inference")
            )
        ),
        truth_aligned_inference=_parse_grid_inference(
            data["truth_aligned_inference"],
            f"{path}.truth_aligned_inference",
        ),
        all_grid_calibration_targets_met=data["all_grid_calibration_targets_met"],
        truth_aligned_population_coverage_target_met=(
            data["truth_aligned_population_coverage_target_met"]
        ),
        research_target_met=data["research_target_met"],
    )


def _parse_mode_inference(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureModeInference:
    data = _record(
        value,
        path,
        {
            "analysis_mode",
            "analysis_structure",
            "replicate_count",
            "metric_inference",
            "all_metric_research_targets_met",
        },
    )
    return ClinicalOutcomePatternMixtureModeInference(
        analysis_mode=_parse_enum(
            ClinicalOutcomeStressAnalysisMode,
            data["analysis_mode"],
            f"{path}.analysis_mode",
        ),
        analysis_structure=_parse_design_structure(
            data["analysis_structure"],
            f"{path}.analysis_structure",
        ),
        replicate_count=data["replicate_count"],
        metric_inference=tuple(
            _parse_metric_inference(item, f"{path}.metric_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["metric_inference"], f"{path}.metric_inference")
            )
        ),
        all_metric_research_targets_met=data["all_metric_research_targets_met"],
    )


def _parse_closure_comparison(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureClosureComparison:
    data = _record(
        value,
        path,
        {
            "metric",
            "true_log_imor",
            "nominal_model_functional_coverage",
            "dependence_closed_model_functional_coverage",
            "dependence_closed_minus_nominal_coverage",
            "dependence_closed_to_nominal_standard_error_ratio",
            "minimum_hidden_linkage_coverage_gain",
            "minimum_hidden_linkage_standard_error_ratio",
            "closure_response_target_required",
            "exact_equivalence_expected",
            "exact_equivalence_met",
            "closure_response_target_met",
        },
    )
    return ClinicalOutcomePatternMixtureClosureComparison(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data.pop("metric"),
            f"{path}.metric",
        ),
        **data,
    )


def _parse_scenario_inference(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureScenarioInference:
    fields = {
        "scenario_id",
        "stage",
        "endpoint_family",
        "population_favorable_prevalence",
        "evaluable_favorable_prevalence",
        "expected_evaluable_probability",
        "true_log_imor",
        "true_informative_missingness_odds_ratio",
        "hidden_linkage_declared",
        "mode_inference",
        "closure_comparison",
        "dependence_closed_all_research_targets_met",
        "all_closure_response_targets_met",
        "research_target_met",
        "rng_stream_sha256",
        "outcome_rng_stream_sha256",
        "evaluability_rng_stream_sha256",
    }
    data = _record(value, path, fields)
    scalar = {
        key: data[key]
        for key in fields
        if key not in {"stage", "mode_inference", "closure_comparison"}
    }
    return ClinicalOutcomePatternMixtureScenarioInference(
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        mode_inference=tuple(
            _parse_mode_inference(item, f"{path}.mode_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["mode_inference"], f"{path}.mode_inference")
            )
        ),
        closure_comparison=tuple(
            _parse_closure_comparison(item, f"{path}.closure_comparison[{index}]")
            for index, item in enumerate(
                _sequence(data["closure_comparison"], f"{path}.closure_comparison")
            )
        ),
        **scalar,
    )


def clinical_outcome_pattern_mixture_uncertainty_report_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureUncertaintyReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_uncertainty_report_envelope",
        schema_version=(
            CLINICAL_OUTCOME_PATTERN_MIXTURE_UNCERTAINTY_REPORT_SCHEMA_VERSION
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
        "replicates",
        "log_imor_grid",
        "analysis_modes",
        "confidence_level",
        "monte_carlo_confidence_level",
        "coverage_target",
        "minimum_interval_yield",
        "minimum_clusters",
        "maximum_cluster_unit_fraction",
        "maximum_absolute_bias",
        "standard_error_calibration_lower",
        "standard_error_calibration_upper",
        "closure_anchor_metric",
        "minimum_hidden_linkage_coverage_gain",
        "minimum_hidden_linkage_standard_error_ratio",
        "scenario_inference",
        "aggregate_simulation_only",
        "replicate_level_records_included",
        "cluster_level_records_included",
        "unit_level_records_included",
        "real_clinical_outcomes_included",
        "sampling_uncertainty_intervals_included",
        "automatic_dependence_closure_included",
        "latent_truth_used_for_operational_grid",
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
            "analysis_modes",
            "closure_anchor_metric",
            "scenario_inference",
            "limitations",
        }
    }
    report = ClinicalOutcomePatternMixtureUncertaintyReport(
        log_imor_grid=tuple(_sequence(data["log_imor_grid"], "report.log_imor_grid")),
        analysis_modes=tuple(
            _parse_enum(
                ClinicalOutcomeStressAnalysisMode,
                item,
                f"report.analysis_modes[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["analysis_modes"], "report.analysis_modes")
            )
        ),
        closure_anchor_metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["closure_anchor_metric"],
            "report.closure_anchor_metric",
        ),
        scenario_inference=tuple(
            _parse_scenario_inference(item, f"report.scenario_inference[{index}]")
            for index, item in enumerate(
                _sequence(data["scenario_inference"], "report.scenario_inference")
            )
        ),
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
        **scalar,
    )
    _check_integrity(report, integrity, "pattern-mixture uncertainty report")
    return report


def clinical_outcome_pattern_mixture_uncertainty_protocol_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureUncertaintyProtocol:
    return clinical_outcome_pattern_mixture_uncertainty_protocol_from_dict(
        _strict_json(payload, "pattern-mixture uncertainty protocol")
    )


def clinical_outcome_pattern_mixture_uncertainty_report_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureUncertaintyReport:
    return clinical_outcome_pattern_mixture_uncertainty_report_from_dict(
        _strict_json(payload, "pattern-mixture uncertainty report")
    )
