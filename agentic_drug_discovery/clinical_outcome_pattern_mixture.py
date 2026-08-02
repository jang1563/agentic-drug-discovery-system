"""Preregistered pattern-mixture sensitivity analysis for binary outcomes."""

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
    _design_rate,
    _draw_beta_binomial_label,
    _METRIC_ORDER,
    _metric_bounds,
    _metric_values,
    _parse_design_rate,
    _require_bool,
    _require_finite,
    _require_non_negative_int,
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
from .clinical_outcome_stress_simulation import (
    CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    _scenario_stream_sha256,
    _scenario_truth,
    _substream_sha256,
    simulate_clinical_outcome_stress,
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


CLINICAL_OUTCOME_PATTERN_MIXTURE_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-protocol.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-report.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-pattern-mixture-summary.v1"
)
CLINICAL_OUTCOME_PATTERN_MIXTURE_METHOD_ID = (
    "adds.pattern-mixture.binary-log-imor-prediction-stratified.v1"
)
MAX_PATTERN_MIXTURE_GRID_POINTS = 33
MAX_ABSOLUTE_LOG_IMOR = 8.0


class ClinicalOutcomePatternMixtureError(ValueError):
    """Raised when a pattern-mixture analysis cannot run safely."""


class ClinicalOutcomePatternMixtureStatus(str, Enum):
    COMPUTED = "computed"
    EMPTY_REFERENCE_STRATUM = "empty_reference_stratum"
    DEGENERATE_REFERENCE_STRATUM = "degenerate_reference_stratum"


_STATUS_ORDER = tuple(ClinicalOutcomePatternMixtureStatus)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic prospective sensitivity analysis; it contains no "
        "real clinical outcomes and does not validate a deployed policy or evidence board."
    ),
    (
        "The log-IMOR sensitivity parameter is the log odds of a favorable outcome among "
        "unevaluable units minus the corresponding log odds among evaluable units."
    ),
    (
        "The log-IMOR grid is an identifying-assumption grid, not an estimate learned from "
        "the observed outcomes; real ranges require outcome-blind clinical elicitation."
    ),
    (
        "One common log-IMOR is applied within every preregistered policy-prediction stratum; "
        "effect modification of missingness beyond those strata is not modeled."
    ),
    (
        "Sensitivity envelopes contain point estimates across the declared grid and are not "
        "sampling-uncertainty intervals or confidence sets for a real population estimand."
    ),
    (
        "Monte Carlo inclusion rates evaluate repeated synthetic recovery; they are not "
        "frequentist coverage guarantees for a single clinical evidence board."
    ),
    (
        "Truth-aligned recovery uses the latent synthetic log-IMOR only as an evaluator-side "
        "diagnostic and never as an operationally available correction parameter."
    ),
    (
        "A replicate fails closed when a partially observed prediction stratum has no "
        "evaluable outcomes or only one observed outcome class."
    ),
    (
        "The inherited generator retains declared block dependence, but this v1 report adds "
        "no cluster-robust sampling interval around a sensitivity-adjusted estimate."
    ),
    (
        "Passing the preregistered synthetic targets does not establish treatment efficacy, "
        "safety, clinical utility, transportability, or regulatory acceptability."
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    stress_protocol_fingerprint: str
    log_imor_grid: tuple[float, ...]
    monte_carlo_confidence_level: float
    minimum_analyzable_rate: float
    maximum_mean_identification_width: float
    maximum_absolute_bias: float
    method_id: str = CLINICAL_OUTCOME_PATTERN_MIXTURE_METHOD_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        _require_sha256(
            self.stress_protocol_fingerprint,
            "stress_protocol_fingerprint",
        )
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        if not 3 <= len(grid) <= MAX_PATTERN_MIXTURE_GRID_POINTS:
            raise ValueError(
                "log_imor_grid must contain between 3 and "
                f"{MAX_PATTERN_MIXTURE_GRID_POINTS} values"
            )
        for value in grid:
            _require_finite(
                value,
                "log_imor_grid item",
                minimum=-MAX_ABSOLUTE_LOG_IMOR,
                maximum=MAX_ABSOLUTE_LOG_IMOR,
            )
        if grid != tuple(sorted(grid)) or len(grid) != len(set(grid)):
            raise ValueError("log_imor_grid must use unique increasing values")
        if 0.0 not in grid:
            raise ValueError("log_imor_grid must include the MAR reference value zero")
        _require_probability(
            self.monte_carlo_confidence_level,
            "monte_carlo_confidence_level",
        )
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError(
                "monte_carlo_confidence_level must be between 0.5 and 1"
            )
        _require_probability(self.minimum_analyzable_rate, "minimum_analyzable_rate")
        if self.minimum_analyzable_rate == 0.0:
            raise ValueError("minimum_analyzable_rate must be positive")
        _require_finite(
            self.maximum_mean_identification_width,
            "maximum_mean_identification_width",
            minimum=0.0,
            maximum=2.0,
        )
        if self.maximum_mean_identification_width == 0.0:
            raise ValueError("maximum_mean_identification_width must be positive")
        _require_finite(
            self.maximum_absolute_bias,
            "maximum_absolute_bias",
            minimum=0.0,
            maximum=2.0,
        )
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError(
                "pattern-mixture protocol metadata cannot contain evaluator outcomes"
            )
        object.__setattr__(self, "metadata", metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureStatusCount(SerializableRecord):
    status: ClinicalOutcomePatternMixtureStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(
            self.status,
            ClinicalOutcomePatternMixtureStatus,
            "status",
        )
        _require_non_negative_int(self.count, "count")


def _status_count_records(
    counts: Mapping[ClinicalOutcomePatternMixtureStatus, int],
) -> tuple[ClinicalOutcomePatternMixtureStatusCount, ...]:
    return tuple(
        ClinicalOutcomePatternMixtureStatusCount(
            status=status,
            count=counts.get(status, 0),
        )
        for status in _STATUS_ORDER
    )


def _validated_status_counts(
    values: Sequence[ClinicalOutcomePatternMixtureStatusCount],
    replicate_count: int,
) -> dict[ClinicalOutcomePatternMixtureStatus, int]:
    resolved = _tuple(values, "status_counts")
    for item in resolved:
        _require_instance(
            item,
            ClinicalOutcomePatternMixtureStatusCount,
            "status_counts item",
        )
    if tuple(item.status for item in resolved) != _STATUS_ORDER:
        raise ValueError("status_counts must exactly cover canonical statuses")
    if sum(item.count for item in resolved) != replicate_count:
        raise ValueError("status_counts do not sum to replicate_count")
    return {item.status: item.count for item in resolved}


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureGridPerformance(SerializableRecord):
    log_imor: float
    informative_missingness_odds_ratio: float
    population_true_value: float
    estimate_count: int
    mean_estimate: float | None
    population_bias: float | None
    population_root_mean_squared_error: float | None

    def __post_init__(self) -> None:
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
        if self.informative_missingness_odds_ratio == 0.0:
            raise ValueError("informative_missingness_odds_ratio must be positive")
        if self.informative_missingness_odds_ratio != _round_metric(
            math.exp(self.log_imor)
        ):
            raise ValueError("informative_missingness_odds_ratio is inconsistent")
        _require_finite(
            self.population_true_value,
            "population_true_value",
            minimum=-1.0,
            maximum=1.0,
        )
        _require_non_negative_int(self.estimate_count, "estimate_count")
        for field_name in (
            "mean_estimate",
            "population_bias",
            "population_root_mean_squared_error",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite(
                    value,
                    field_name,
                    minimum=(
                        0.0
                        if field_name == "population_root_mean_squared_error"
                        else -2.0
                    ),
                    maximum=2.0,
                )
        if self.estimate_count == 0:
            if any(
                value is not None
                for value in (
                    self.mean_estimate,
                    self.population_bias,
                    self.population_root_mean_squared_error,
                )
            ):
                raise ValueError("empty grid performance requires null estimates")
        else:
            if any(
                value is None
                for value in (
                    self.mean_estimate,
                    self.population_bias,
                    self.population_root_mean_squared_error,
                )
            ):
                raise ValueError("grid performance estimates cannot be null")
            assert self.mean_estimate is not None
            if self.population_bias != _round_metric(
                self.mean_estimate - self.population_true_value
            ):
                raise ValueError("grid population_bias is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureMetricPerformance(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    replicate_count: int
    analyzable_replicates: int
    population_true_value: float
    evaluable_true_value: float
    naive_mean_estimate: float | None
    naive_population_bias: float | None
    naive_population_root_mean_squared_error: float | None
    naive_evaluable_bias: float | None
    naive_evaluable_root_mean_squared_error: float | None
    truth_aligned_mean_estimate: float | None
    truth_aligned_population_bias: float | None
    truth_aligned_population_root_mean_squared_error: float | None
    sensitivity_envelope_inclusion: ClinicalOutcomeDesignRate
    mean_sensitivity_envelope_lower: float | None
    mean_sensitivity_envelope_upper: float | None
    mean_sensitivity_envelope_width: float | None
    population_truth_distance_to_mean_envelope: float | None
    maximum_absolute_bias: float
    maximum_mean_identification_width: float
    evaluable_calibration_met: bool
    truth_aligned_recovery_met: bool
    population_truth_recovered_by_mean_envelope: bool
    identification_target_met: bool
    grid_performance: tuple[ClinicalOutcomePatternMixtureGridPerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        _require_positive_int(self.replicate_count, "replicate_count")
        _require_non_negative_int(
            self.analyzable_replicates,
            "analyzable_replicates",
        )
        if self.analyzable_replicates > self.replicate_count:
            raise ValueError("analyzable_replicates exceeds replicate_count")
        lower, upper = _metric_bounds(self.metric)
        for field_name in ("population_true_value", "evaluable_true_value"):
            _require_finite(
                getattr(self, field_name),
                field_name,
                minimum=lower,
                maximum=upper,
            )
        for field_name in ("naive_mean_estimate", "truth_aligned_mean_estimate"):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite(value, field_name, minimum=lower, maximum=upper)
        for field_name in (
            "naive_population_bias",
            "naive_evaluable_bias",
            "truth_aligned_population_bias",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite(value, field_name, minimum=-2.0, maximum=2.0)
        for field_name in (
            "naive_population_root_mean_squared_error",
            "naive_evaluable_root_mean_squared_error",
            "truth_aligned_population_root_mean_squared_error",
            "mean_sensitivity_envelope_width",
            "population_truth_distance_to_mean_envelope",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite(value, field_name, minimum=0.0, maximum=2.0)
        for field_name in (
            "mean_sensitivity_envelope_lower",
            "mean_sensitivity_envelope_upper",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite(value, field_name, minimum=lower, maximum=upper)
        _require_instance(
            self.sensitivity_envelope_inclusion,
            ClinicalOutcomeDesignRate,
            "sensitivity_envelope_inclusion",
        )
        if (
            self.sensitivity_envelope_inclusion.total_count
            != self.analyzable_replicates
        ):
            raise ValueError("sensitivity envelope denominator is inconsistent")
        _require_finite(
            self.maximum_absolute_bias,
            "maximum_absolute_bias",
            minimum=0.0,
            maximum=2.0,
        )
        _require_finite(
            self.maximum_mean_identification_width,
            "maximum_mean_identification_width",
            minimum=0.0,
            maximum=2.0,
        )
        for field_name in (
            "evaluable_calibration_met",
            "truth_aligned_recovery_met",
            "population_truth_recovered_by_mean_envelope",
            "identification_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        grid = _tuple(self.grid_performance, "grid_performance")
        object.__setattr__(self, "grid_performance", grid)
        if not grid:
            raise ValueError("grid_performance cannot be empty")
        for item in grid:
            _require_instance(
                item,
                ClinicalOutcomePatternMixtureGridPerformance,
                "grid_performance item",
            )
            if item.population_true_value != self.population_true_value:
                raise ValueError("grid population truth is inconsistent")
            if item.estimate_count != self.analyzable_replicates:
                raise ValueError("grid estimate_count is inconsistent")
        if tuple(item.log_imor for item in grid) != tuple(
            sorted(item.log_imor for item in grid)
        ):
            raise ValueError("grid_performance must use canonical order")

        optional_values = (
            self.naive_mean_estimate,
            self.naive_population_bias,
            self.naive_population_root_mean_squared_error,
            self.naive_evaluable_bias,
            self.naive_evaluable_root_mean_squared_error,
            self.truth_aligned_mean_estimate,
            self.truth_aligned_population_bias,
            self.truth_aligned_population_root_mean_squared_error,
            self.mean_sensitivity_envelope_lower,
            self.mean_sensitivity_envelope_upper,
            self.mean_sensitivity_envelope_width,
            self.population_truth_distance_to_mean_envelope,
        )
        if self.analyzable_replicates == 0:
            if any(value is not None for value in optional_values):
                raise ValueError("zero analyzable replicates require null metrics")
            if any(
                (
                    self.evaluable_calibration_met,
                    self.truth_aligned_recovery_met,
                    self.population_truth_recovered_by_mean_envelope,
                    self.identification_target_met,
                )
            ):
                raise ValueError("empty metric performance cannot meet targets")
            return
        if any(value is None for value in optional_values):
            raise ValueError("analyzable metric performance cannot contain nulls")
        assert self.naive_mean_estimate is not None
        assert self.truth_aligned_mean_estimate is not None
        assert self.naive_evaluable_bias is not None
        assert self.truth_aligned_population_bias is not None
        assert self.mean_sensitivity_envelope_lower is not None
        assert self.mean_sensitivity_envelope_upper is not None
        assert self.mean_sensitivity_envelope_width is not None
        assert self.population_truth_distance_to_mean_envelope is not None
        if self.naive_population_bias != _round_metric(
            self.naive_mean_estimate - self.population_true_value
        ):
            raise ValueError("naive_population_bias is inconsistent")
        if self.naive_evaluable_bias != _round_metric(
            self.naive_mean_estimate - self.evaluable_true_value
        ):
            raise ValueError("naive_evaluable_bias is inconsistent")
        if self.truth_aligned_population_bias != _round_metric(
            self.truth_aligned_mean_estimate - self.population_true_value
        ):
            raise ValueError("truth_aligned_population_bias is inconsistent")
        expected_evaluable = abs(self.naive_evaluable_bias) <= self.maximum_absolute_bias
        expected_recovery = (
            abs(self.truth_aligned_population_bias) <= self.maximum_absolute_bias
        )
        grid_means = tuple(item.mean_estimate for item in grid)
        if any(value is None for value in grid_means):
            raise ValueError("analyzable grid means cannot be null")
        resolved_grid_means = tuple(float(value) for value in grid_means)
        expected_lower = _round_metric(min(resolved_grid_means))
        expected_upper = _round_metric(max(resolved_grid_means))
        expected_width = _round_metric(expected_upper - expected_lower)
        expected_distance = _round_metric(
            max(
                expected_lower - self.population_true_value,
                self.population_true_value - expected_upper,
                0.0,
            )
        )
        if (
            self.mean_sensitivity_envelope_lower != expected_lower
            or self.mean_sensitivity_envelope_upper != expected_upper
            or self.mean_sensitivity_envelope_width != expected_width
            or self.population_truth_distance_to_mean_envelope != expected_distance
        ):
            raise ValueError("mean sensitivity envelope is inconsistent")
        expected_mean_recovery = expected_distance <= self.maximum_absolute_bias
        expected_identification = (
            expected_mean_recovery
            and expected_width <= self.maximum_mean_identification_width
        )
        if self.evaluable_calibration_met != expected_evaluable:
            raise ValueError("evaluable_calibration_met is inconsistent")
        if self.truth_aligned_recovery_met != expected_recovery:
            raise ValueError("truth_aligned_recovery_met is inconsistent")
        if self.population_truth_recovered_by_mean_envelope != expected_mean_recovery:
            raise ValueError(
                "population_truth_recovered_by_mean_envelope is inconsistent"
            )
        if self.identification_target_met != expected_identification:
            raise ValueError("identification_target_met is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureScenarioResult(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    population_favorable_prevalence: float
    evaluable_favorable_prevalence: float
    expected_evaluable_probability: float
    true_log_imor: float
    true_informative_missingness_odds_ratio: float
    grid_brackets_true_log_imor: bool
    replicate_count: int
    status_counts: tuple[ClinicalOutcomePatternMixtureStatusCount, ...]
    analyzable_rate: ClinicalOutcomeDesignRate
    metric_performance: tuple[ClinicalOutcomePatternMixtureMetricPerformance, ...]
    analyzable_target_met: bool
    all_evaluable_calibration_targets_met: bool
    all_truth_aligned_recovery_targets_met: bool
    all_identification_targets_met: bool
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
        _require_finite(
            self.true_log_imor,
            "true_log_imor",
            minimum=-MAX_ABSOLUTE_LOG_IMOR,
            maximum=MAX_ABSOLUTE_LOG_IMOR,
        )
        _require_finite(
            self.true_informative_missingness_odds_ratio,
            "true_informative_missingness_odds_ratio",
            minimum=0.0,
        )
        if self.true_informative_missingness_odds_ratio != _round_metric(
            math.exp(self.true_log_imor)
        ):
            raise ValueError("true informative missingness odds ratio is inconsistent")
        _require_bool(
            self.grid_brackets_true_log_imor,
            "grid_brackets_true_log_imor",
        )
        _require_positive_int(self.replicate_count, "replicate_count")
        status_counts = _tuple(self.status_counts, "status_counts")
        object.__setattr__(self, "status_counts", status_counts)
        counts = _validated_status_counts(status_counts, self.replicate_count)
        _require_instance(
            self.analyzable_rate,
            ClinicalOutcomeDesignRate,
            "analyzable_rate",
        )
        if (
            self.analyzable_rate.event_count
            != counts[ClinicalOutcomePatternMixtureStatus.COMPUTED]
            or self.analyzable_rate.total_count != self.replicate_count
        ):
            raise ValueError("analyzable_rate is inconsistent with statuses")
        metrics = _tuple(self.metric_performance, "metric_performance")
        object.__setattr__(self, "metric_performance", metrics)
        for metric in metrics:
            _require_instance(
                metric,
                ClinicalOutcomePatternMixtureMetricPerformance,
                "metric_performance item",
            )
            if (
                metric.replicate_count != self.replicate_count
                or metric.analyzable_replicates != self.analyzable_rate.event_count
            ):
                raise ValueError("metric replicate counts are inconsistent")
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("metric_performance must cover canonical metrics")
        for field_name in (
            "analyzable_target_met",
            "all_evaluable_calibration_targets_met",
            "all_truth_aligned_recovery_targets_met",
            "all_identification_targets_met",
            "research_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        expected_evaluable = all(item.evaluable_calibration_met for item in metrics)
        expected_recovery = all(item.truth_aligned_recovery_met for item in metrics)
        expected_identification = all(
            item.identification_target_met for item in metrics
        )
        if self.all_evaluable_calibration_targets_met != expected_evaluable:
            raise ValueError("evaluable calibration target is inconsistent")
        if self.all_truth_aligned_recovery_targets_met != expected_recovery:
            raise ValueError("truth-aligned recovery target is inconsistent")
        if self.all_identification_targets_met != expected_identification:
            raise ValueError("identification target is inconsistent")
        expected_research = (
            self.grid_brackets_true_log_imor
            and self.analyzable_target_met
            and expected_evaluable
            and expected_recovery
            and expected_identification
        )
        if self.research_target_met != expected_research:
            raise ValueError("research_target_met is inconsistent")
        for field_name in (
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.stage.value, self.endpoint_family, self.scenario_id)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomePatternMixtureReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    stress_protocol_id: str
    stress_protocol_fingerprint: str
    stress_report_fingerprint: str
    method_id: str
    rng_method_id: str
    replicates: int
    log_imor_grid: tuple[float, ...]
    monte_carlo_confidence_level: float
    minimum_analyzable_rate: float
    maximum_mean_identification_width: float
    maximum_absolute_bias: float
    scenario_results: tuple[ClinicalOutcomePatternMixtureScenarioResult, ...]
    aggregate_simulation_only: bool = True
    replicate_level_records_included: bool = False
    unit_level_records_included: bool = False
    real_clinical_outcomes_included: bool = False
    automatic_missingness_correction_included: bool = False
    sampling_uncertainty_intervals_included: bool = False
    latent_truth_recovery_diagnostic_included: bool = True
    operational_estimate_uses_latent_truth: bool = False
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "stress_protocol_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "stress_protocol_fingerprint",
            "stress_report_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_OUTCOME_PATTERN_MIXTURE_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        _require_positive_int(self.replicates, "replicates")
        grid = _tuple(self.log_imor_grid, "log_imor_grid")
        object.__setattr__(self, "log_imor_grid", grid)
        if not 3 <= len(grid) <= MAX_PATTERN_MIXTURE_GRID_POINTS:
            raise ValueError(
                "report log_imor_grid must contain between 3 and "
                f"{MAX_PATTERN_MIXTURE_GRID_POINTS} values"
            )
        for value in grid:
            _require_finite(
                value,
                "report log_imor_grid item",
                minimum=-MAX_ABSOLUTE_LOG_IMOR,
                maximum=MAX_ABSOLUTE_LOG_IMOR,
            )
        if grid != tuple(sorted(grid)) or len(grid) != len(set(grid)):
            raise ValueError("report log_imor_grid must use canonical order")
        if 0.0 not in grid:
            raise ValueError("report log_imor_grid must include the MAR reference value zero")
        _require_probability(
            self.monte_carlo_confidence_level,
            "monte_carlo_confidence_level",
        )
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError(
                "monte_carlo_confidence_level must be between 0.5 and 1"
            )
        _require_probability(self.minimum_analyzable_rate, "minimum_analyzable_rate")
        if self.minimum_analyzable_rate == 0.0:
            raise ValueError("minimum_analyzable_rate must be positive")
        _require_finite(
            self.maximum_mean_identification_width,
            "maximum_mean_identification_width",
            minimum=0.0,
            maximum=2.0,
        )
        if self.maximum_mean_identification_width == 0.0:
            raise ValueError("maximum_mean_identification_width must be positive")
        _require_finite(
            self.maximum_absolute_bias,
            "maximum_absolute_bias",
            minimum=0.0,
            maximum=2.0,
        )
        results = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", results)
        if not results:
            raise ValueError("scenario_results cannot be empty")
        for result in results:
            _require_instance(
                result,
                ClinicalOutcomePatternMixtureScenarioResult,
                "scenario_results item",
            )
            if result.replicate_count != self.replicates:
                raise ValueError("scenario replicate_count is inconsistent")
            if (
                result.analyzable_rate.confidence_level
                != self.monte_carlo_confidence_level
            ):
                raise ValueError("scenario analyzable confidence level is inconsistent")
            expected_analyzable_target = (
                result.analyzable_rate.lower is not None
                and result.analyzable_rate.lower >= self.minimum_analyzable_rate
            )
            if result.analyzable_target_met != expected_analyzable_target:
                raise ValueError("scenario analyzable target is inconsistent")
            expected_grid_bracket = (
                grid[0] <= result.true_log_imor <= grid[-1]
            )
            if result.grid_brackets_true_log_imor != expected_grid_bracket:
                raise ValueError("scenario true log-IMOR bracket is inconsistent")
            for metric in result.metric_performance:
                if tuple(item.log_imor for item in metric.grid_performance) != grid:
                    raise ValueError("scenario sensitivity grid is inconsistent")
                if (
                    metric.sensitivity_envelope_inclusion.confidence_level
                    != self.monte_carlo_confidence_level
                ):
                    raise ValueError(
                        "scenario sensitivity confidence level is inconsistent"
                    )
                if metric.maximum_absolute_bias != self.maximum_absolute_bias:
                    raise ValueError("scenario absolute-bias threshold is inconsistent")
                if (
                    metric.maximum_mean_identification_width
                    != self.maximum_mean_identification_width
                ):
                    raise ValueError(
                        "scenario identification-width threshold is inconsistent"
                    )
        if tuple(item.sort_key for item in results) != tuple(
            sorted(item.sort_key for item in results)
        ):
            raise ValueError("scenario_results must use canonical order")
        if len({item.scenario_id for item in results}) != len(results):
            raise ValueError("scenario result ids must be unique")
        for field_name in (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "automatic_missingness_correction_included",
            "sampling_uncertainty_intervals_included",
            "latent_truth_recovery_diagnostic_included",
            "operational_estimate_uses_latent_truth",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.aggregate_simulation_only:
            raise ValueError("pattern-mixture report must remain aggregate")
        if (
            self.replicate_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or self.automatic_missingness_correction_included
            or self.sampling_uncertainty_intervals_included
            or self.operational_estimate_uses_latent_truth
            or not self.latent_truth_recovery_diagnostic_included
        ):
            raise ValueError("pattern-mixture report crossed its claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required pattern-mixture limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


class _PointAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.squared_error_total = 0.0

    def add(self, value: float, truth: float) -> None:
        self.count += 1
        self.total += value
        self.squared_error_total += (value - truth) ** 2

    def finalize(self, truth: float) -> tuple[float | None, float | None, float | None]:
        if self.count == 0:
            return None, None, None
        mean = _round_metric(self.total / self.count)
        return (
            mean,
            _round_metric(mean - truth),
            _round_metric(math.sqrt(self.squared_error_total / self.count)),
        )


class _MetricAccumulator:
    def __init__(self, grid: Sequence[float]) -> None:
        self.naive_population = _PointAccumulator()
        self.naive_evaluable = _PointAccumulator()
        self.truth_aligned = _PointAccumulator()
        self.grid = {value: _PointAccumulator() for value in grid}
        self.inclusion_count = 0

    def add(
        self,
        *,
        naive: float,
        truth_aligned: float,
        grid_values: Mapping[float, float],
        population_truth: float,
        evaluable_truth: float,
    ) -> None:
        self.naive_population.add(naive, population_truth)
        self.naive_evaluable.add(naive, evaluable_truth)
        self.truth_aligned.add(truth_aligned, population_truth)
        for log_imor, value in grid_values.items():
            self.grid[log_imor].add(value, population_truth)
        lower = min(grid_values.values())
        upper = max(grid_values.values())
        if lower - 1e-12 <= population_truth <= upper + 1e-12:
            self.inclusion_count += 1


def _odds_shift_probability(probability: float, log_imor: float) -> float:
    multiplier = math.exp(log_imor)
    denominator = 1.0 - probability + multiplier * probability
    return multiplier * probability / denominator


def _expected_metric_value(
    metric: ClinicalOutcomeDesignMetric,
    prevalence: float,
    probability_a: float,
    probability_b: float,
    classification_threshold: float,
) -> float:
    unfavorable = _metric_values(
        0.0,
        probability_a,
        probability_b,
        classification_threshold,
    )[metric]
    favorable = _metric_values(
        1.0,
        probability_a,
        probability_b,
        classification_threshold,
    )[metric]
    return (1.0 - prevalence) * unfavorable + prevalence * favorable


def _true_log_imor(scenario: ClinicalOutcomeStressScenario) -> float:
    favorable = scenario.favorable_evaluable_probability
    unfavorable = scenario.unfavorable_evaluable_probability
    if not 0.0 < favorable < 1.0 or not 0.0 < unfavorable < 1.0:
        raise ClinicalOutcomePatternMixtureError(
            f"scenario {scenario.scenario_id!r} requires strictly interior "
            "evaluability probabilities for finite log-IMOR sensitivity"
        )
    odds_ratio = unfavorable * (1.0 - favorable) / (
        favorable * (1.0 - unfavorable)
    )
    log_imor = math.log(odds_ratio)
    if abs(log_imor) > MAX_ABSOLUTE_LOG_IMOR:
        raise ClinicalOutcomePatternMixtureError(
            f"scenario {scenario.scenario_id!r} true log-IMOR exceeds the bounded range"
        )
    return _round_metric(log_imor)


def _scenario_work_units(
    protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> int:
    return stress_protocol.replicates * sum(
        sum(scenario.nominal_cluster_sizes)
        + len(
            set(
                zip(
                    scenario.policy_a_probability_pattern,
                    scenario.policy_b_probability_pattern,
                    strict=True,
                )
            )
        )
        * (len(protocol.log_imor_grid) + 1)
        * len(_METRIC_ORDER)
        for scenario in stress_protocol.scenarios
    )


def _simulate_scenario(
    protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
) -> ClinicalOutcomePatternMixtureScenarioResult:
    stream_sha256 = _scenario_stream_sha256(stress_protocol, scenario)
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(stream_sha256, "evaluability")
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    truth = _scenario_truth(scenario)
    population_truth = {
        item.metric: item.population_value for item in truth.metric_truths
    }
    evaluable_truth = {
        item.metric: item.evaluable_value for item in truth.metric_truths
    }
    true_log_imor = _true_log_imor(scenario)

    unit_indices_by_nominal_cluster: list[list[int]] = []
    stratum_index_by_unit: list[int] = []
    prediction_pattern = tuple(
        zip(
            scenario.policy_a_probability_pattern,
            scenario.policy_b_probability_pattern,
            strict=True,
        )
    )
    prediction_strata = tuple(dict.fromkeys(prediction_pattern))
    stratum_index_by_prediction = {
        prediction: index for index, prediction in enumerate(prediction_strata)
    }
    pattern_length = len(prediction_pattern)
    stratum_totals = [0] * len(prediction_strata)
    next_unit = 0
    for cluster_size in scenario.nominal_cluster_sizes:
        cluster_units: list[int] = []
        for within_cluster_index in range(cluster_size):
            cluster_units.append(next_unit)
            pattern_index = within_cluster_index % pattern_length
            stratum_index = stratum_index_by_prediction[
                prediction_pattern[pattern_index]
            ]
            stratum_index_by_unit.append(stratum_index)
            stratum_totals[stratum_index] += 1
            next_unit += 1
        unit_indices_by_nominal_cluster.append(cluster_units)
    unit_count = next_unit

    accumulators = {
        metric: _MetricAccumulator(protocol.log_imor_grid)
        for metric in _METRIC_ORDER
    }
    status_counts: Counter[ClinicalOutcomePatternMixtureStatus] = Counter()
    prevalence = scenario.favorable_prevalence
    correlation = scenario.dependence_block_intraclass_correlation

    for _ in range(stress_protocol.replicates):
        labels = [0.0] * unit_count
        for block in scenario.dependence_blocks:
            successes = 0
            previous_count = 0
            for nominal_index in block:
                for unit_index in unit_indices_by_nominal_cluster[nominal_index]:
                    label = _draw_beta_binomial_label(
                        outcome_rng,
                        prevalence,
                        correlation,
                        successes,
                        previous_count,
                    )
                    labels[unit_index] = label
                    successes += int(label)
                    previous_count += 1

        stratum_evaluable = [0] * len(prediction_strata)
        stratum_favorable = [0] * len(prediction_strata)
        naive_metric_totals = {metric: 0.0 for metric in _METRIC_ORDER}
        evaluable_count = 0
        for unit_index, label in enumerate(labels):
            evaluable_probability = (
                scenario.favorable_evaluable_probability
                if label == 1.0
                else scenario.unfavorable_evaluable_probability
            )
            if evaluability_rng.random() >= evaluable_probability:
                continue
            stratum_index = stratum_index_by_unit[unit_index]
            stratum_evaluable[stratum_index] += 1
            stratum_favorable[stratum_index] += int(label)
            evaluable_count += 1
            metric_values = _metric_values(
                label,
                prediction_strata[stratum_index][0],
                prediction_strata[stratum_index][1],
                scenario.classification_threshold,
            )
            for metric, value in metric_values.items():
                naive_metric_totals[metric] += value

        if any(value == 0 for value in stratum_evaluable):
            status_counts[
                ClinicalOutcomePatternMixtureStatus.EMPTY_REFERENCE_STRATUM
            ] += 1
            continue
        if any(
            evaluable < total and favorable in (0, evaluable)
            for total, evaluable, favorable in zip(
                stratum_totals,
                stratum_evaluable,
                stratum_favorable,
                strict=True,
            )
        ):
            status_counts[
                ClinicalOutcomePatternMixtureStatus.DEGENERATE_REFERENCE_STRATUM
            ] += 1
            continue

        estimates_by_shift: dict[
            float,
            dict[ClinicalOutcomeDesignMetric, float],
        ] = {}
        for log_imor in (*protocol.log_imor_grid, true_log_imor):
            if log_imor in estimates_by_shift:
                continue
            estimates = {metric: 0.0 for metric in _METRIC_ORDER}
            for pattern_index, (probability_a, probability_b) in enumerate(
                prediction_strata
            ):
                total = stratum_totals[pattern_index]
                evaluable = stratum_evaluable[pattern_index]
                favorable = stratum_favorable[pattern_index]
                observed_prevalence = favorable / evaluable
                missing_prevalence = _odds_shift_probability(
                    observed_prevalence,
                    log_imor,
                )
                population_prevalence = (
                    evaluable * observed_prevalence
                    + (total - evaluable) * missing_prevalence
                ) / total
                weight = total / unit_count
                for metric in _METRIC_ORDER:
                    estimates[metric] += weight * _expected_metric_value(
                        metric,
                        population_prevalence,
                        probability_a,
                        probability_b,
                        scenario.classification_threshold,
                    )
            estimates_by_shift[log_imor] = {
                metric: _round_metric(value) for metric, value in estimates.items()
            }

        for metric in _METRIC_ORDER:
            accumulators[metric].add(
                naive=_round_metric(naive_metric_totals[metric] / evaluable_count),
                truth_aligned=estimates_by_shift[true_log_imor][metric],
                grid_values={
                    log_imor: estimates_by_shift[log_imor][metric]
                    for log_imor in protocol.log_imor_grid
                },
                population_truth=population_truth[metric],
                evaluable_truth=evaluable_truth[metric],
            )
        status_counts[ClinicalOutcomePatternMixtureStatus.COMPUTED] += 1

    analyzable_count = status_counts[
        ClinicalOutcomePatternMixtureStatus.COMPUTED
    ]
    metrics: list[ClinicalOutcomePatternMixtureMetricPerformance] = []
    for metric in _METRIC_ORDER:
        accumulator = accumulators[metric]
        naive_population = accumulator.naive_population.finalize(
            population_truth[metric]
        )
        naive_evaluable = accumulator.naive_evaluable.finalize(
            evaluable_truth[metric]
        )
        truth_aligned = accumulator.truth_aligned.finalize(
            population_truth[metric]
        )
        inclusion = _design_rate(
            accumulator.inclusion_count,
            analyzable_count,
            protocol.monte_carlo_confidence_level,
        )
        evaluable_met = (
            naive_evaluable[1] is not None
            and abs(naive_evaluable[1]) <= protocol.maximum_absolute_bias
        )
        recovery_met = (
            truth_aligned[1] is not None
            and abs(truth_aligned[1]) <= protocol.maximum_absolute_bias
        )
        grid_performance_items: list[
            ClinicalOutcomePatternMixtureGridPerformance
        ] = []
        for log_imor in protocol.log_imor_grid:
            mean_estimate, population_bias, population_rmse = accumulator.grid[
                log_imor
            ].finalize(population_truth[metric])
            grid_performance_items.append(
                ClinicalOutcomePatternMixtureGridPerformance(
                    log_imor=log_imor,
                    informative_missingness_odds_ratio=_round_metric(
                        math.exp(log_imor)
                    ),
                    population_true_value=population_truth[metric],
                    estimate_count=analyzable_count,
                    mean_estimate=mean_estimate,
                    population_bias=population_bias,
                    population_root_mean_squared_error=population_rmse,
                )
            )
        grid_performance = tuple(grid_performance_items)
        grid_means = tuple(
            item.mean_estimate
            for item in grid_performance
            if item.mean_estimate is not None
        )
        if analyzable_count == 0:
            mean_lower = mean_upper = mean_width = truth_distance = None
            mean_recovery = identification_met = False
        else:
            mean_lower = _round_metric(min(grid_means))
            mean_upper = _round_metric(max(grid_means))
            mean_width = _round_metric(mean_upper - mean_lower)
            truth_distance = _round_metric(
                max(
                    mean_lower - population_truth[metric],
                    population_truth[metric] - mean_upper,
                    0.0,
                )
            )
            mean_recovery = truth_distance <= protocol.maximum_absolute_bias
            identification_met = (
                mean_recovery
                and mean_width <= protocol.maximum_mean_identification_width
            )
        metrics.append(
            ClinicalOutcomePatternMixtureMetricPerformance(
                metric=metric,
                replicate_count=stress_protocol.replicates,
                analyzable_replicates=analyzable_count,
                population_true_value=population_truth[metric],
                evaluable_true_value=evaluable_truth[metric],
                naive_mean_estimate=naive_population[0],
                naive_population_bias=naive_population[1],
                naive_population_root_mean_squared_error=naive_population[2],
                naive_evaluable_bias=naive_evaluable[1],
                naive_evaluable_root_mean_squared_error=naive_evaluable[2],
                truth_aligned_mean_estimate=truth_aligned[0],
                truth_aligned_population_bias=truth_aligned[1],
                truth_aligned_population_root_mean_squared_error=truth_aligned[2],
                sensitivity_envelope_inclusion=inclusion,
                mean_sensitivity_envelope_lower=mean_lower,
                mean_sensitivity_envelope_upper=mean_upper,
                mean_sensitivity_envelope_width=mean_width,
                population_truth_distance_to_mean_envelope=truth_distance,
                maximum_absolute_bias=protocol.maximum_absolute_bias,
                maximum_mean_identification_width=(
                    protocol.maximum_mean_identification_width
                ),
                evaluable_calibration_met=evaluable_met,
                truth_aligned_recovery_met=recovery_met,
                population_truth_recovered_by_mean_envelope=mean_recovery,
                identification_target_met=identification_met,
                grid_performance=grid_performance,
            )
        )

    analyzable_rate = _design_rate(
        analyzable_count,
        stress_protocol.replicates,
        protocol.monte_carlo_confidence_level,
    )
    analyzable_target_met = (
        analyzable_rate.lower is not None
        and analyzable_rate.lower >= protocol.minimum_analyzable_rate
    )
    grid_brackets = (
        protocol.log_imor_grid[0]
        <= true_log_imor
        <= protocol.log_imor_grid[-1]
    )
    all_evaluable = all(item.evaluable_calibration_met for item in metrics)
    all_recovery = all(item.truth_aligned_recovery_met for item in metrics)
    all_identification = all(item.identification_target_met for item in metrics)
    return ClinicalOutcomePatternMixtureScenarioResult(
        scenario_id=scenario.scenario_id,
        stage=scenario.stage,
        endpoint_family=scenario.endpoint_family,
        population_favorable_prevalence=truth.population_favorable_prevalence,
        evaluable_favorable_prevalence=truth.evaluable_favorable_prevalence,
        expected_evaluable_probability=truth.expected_evaluable_probability,
        true_log_imor=true_log_imor,
        true_informative_missingness_odds_ratio=_round_metric(
            math.exp(true_log_imor)
        ),
        grid_brackets_true_log_imor=grid_brackets,
        replicate_count=stress_protocol.replicates,
        status_counts=_status_count_records(status_counts),
        analyzable_rate=analyzable_rate,
        metric_performance=tuple(metrics),
        analyzable_target_met=analyzable_target_met,
        all_evaluable_calibration_targets_met=all_evaluable,
        all_truth_aligned_recovery_targets_met=all_recovery,
        all_identification_targets_met=all_identification,
        research_target_met=(
            grid_brackets
            and analyzable_target_met
            and all_evaluable
            and all_recovery
            and all_identification
        ),
        rng_stream_sha256=stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
    )


def analyze_clinical_outcome_pattern_mixture(
    protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomePatternMixtureReport:
    """Run a deterministic aggregate pattern-mixture recovery analysis."""

    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureProtocol,
        "protocol",
    )
    _require_instance(
        stress_protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "stress_protocol",
    )
    if protocol.stress_protocol_fingerprint != stress_protocol.fingerprint:
        raise ClinicalOutcomePatternMixtureError(
            "pattern-mixture protocol is not bound to the stress protocol"
        )
    if _scenario_work_units(protocol, stress_protocol) > MAX_DESIGN_WORK_UNITS:
        raise ClinicalOutcomePatternMixtureError(
            "pattern-mixture analysis exceeds the bounded work budget"
        )
    stress_report = simulate_clinical_outcome_stress(stress_protocol)
    return ClinicalOutcomePatternMixtureReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        stress_protocol_id=stress_protocol.protocol_id,
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        stress_report_fingerprint=stress_report.fingerprint,
        method_id=protocol.method_id,
        rng_method_id=stress_protocol.rng_method_id,
        replicates=stress_protocol.replicates,
        log_imor_grid=protocol.log_imor_grid,
        monte_carlo_confidence_level=protocol.monte_carlo_confidence_level,
        minimum_analyzable_rate=protocol.minimum_analyzable_rate,
        maximum_mean_identification_width=(
            protocol.maximum_mean_identification_width
        ),
        maximum_absolute_bias=protocol.maximum_absolute_bias,
        scenario_results=tuple(
            _simulate_scenario(protocol, stress_protocol, scenario)
            for scenario in stress_protocol.scenarios
        ),
    )


def validate_clinical_outcome_pattern_mixture_report(
    report: ClinicalOutcomePatternMixtureReport,
    protocol: ClinicalOutcomePatternMixtureProtocol,
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> tuple[str, ...]:
    """Replay a pattern-mixture analysis exactly and compare the report."""

    try:
        rebuilt = analyze_clinical_outcome_pattern_mixture(
            protocol,
            stress_protocol,
        )
    except (ClinicalOutcomePatternMixtureError, TypeError, ValueError):
        return ("pattern_mixture_replay_failed",)
    return () if rebuilt == report else ("pattern_mixture_report_mismatch",)


def _rate_projection(value: ClinicalOutcomeDesignRate) -> dict[str, Any]:
    return {
        "event_count": value.event_count,
        "total_count": value.total_count,
        "rate": value.rate,
        "lower": value.lower,
        "upper": value.upper,
    }


def clinical_outcome_pattern_mixture_summary(
    report: ClinicalOutcomePatternMixtureReport,
) -> dict[str, Any]:
    """Return a compact human- and machine-readable sensitivity summary."""

    _require_instance(
        report,
        ClinicalOutcomePatternMixtureReport,
        "report",
    )
    return {
        "schema_version": CLINICAL_OUTCOME_PATTERN_MIXTURE_SUMMARY_SCHEMA_VERSION,
        "protocol_id": report.protocol_id,
        "protocol_fingerprint": report.protocol_fingerprint,
        "report_fingerprint": report.fingerprint,
        "stress_protocol_id": report.stress_protocol_id,
        "stress_protocol_fingerprint": report.stress_protocol_fingerprint,
        "stress_report_fingerprint": report.stress_report_fingerprint,
        "method_id": report.method_id,
        "replicates": report.replicates,
        "log_imor_grid": list(report.log_imor_grid),
        "targets": {
            "minimum_analyzable_rate": report.minimum_analyzable_rate,
            "maximum_mean_identification_width": (
                report.maximum_mean_identification_width
            ),
            "maximum_absolute_bias": report.maximum_absolute_bias,
        },
        "all_scenarios_research_targets_met": all(
            result.research_target_met for result in report.scenario_results
        ),
        "scenarios": [
            {
                "scenario_id": result.scenario_id,
                "stage": result.stage.value,
                "endpoint_family": result.endpoint_family,
                "population_favorable_prevalence": (
                    result.population_favorable_prevalence
                ),
                "evaluable_favorable_prevalence": (
                    result.evaluable_favorable_prevalence
                ),
                "true_log_imor": result.true_log_imor,
                "true_informative_missingness_odds_ratio": (
                    result.true_informative_missingness_odds_ratio
                ),
                "grid_brackets_true_log_imor": (
                    result.grid_brackets_true_log_imor
                ),
                "analyzable_rate": _rate_projection(result.analyzable_rate),
                "analyzable_target_met": result.analyzable_target_met,
                "all_evaluable_calibration_targets_met": (
                    result.all_evaluable_calibration_targets_met
                ),
                "all_truth_aligned_recovery_targets_met": (
                    result.all_truth_aligned_recovery_targets_met
                ),
                "all_identification_targets_met": (
                    result.all_identification_targets_met
                ),
                "research_target_met": result.research_target_met,
                "metrics": [
                    {
                        "metric": metric.metric.value,
                        "naive_population_bias": metric.naive_population_bias,
                        "naive_evaluable_bias": metric.naive_evaluable_bias,
                        "truth_aligned_population_bias": (
                            metric.truth_aligned_population_bias
                        ),
                        "sensitivity_envelope_inclusion": _rate_projection(
                            metric.sensitivity_envelope_inclusion
                        ),
                        "mean_sensitivity_envelope_lower": (
                            metric.mean_sensitivity_envelope_lower
                        ),
                        "mean_sensitivity_envelope_upper": (
                            metric.mean_sensitivity_envelope_upper
                        ),
                        "mean_sensitivity_envelope_width": (
                            metric.mean_sensitivity_envelope_width
                        ),
                        "population_truth_distance_to_mean_envelope": (
                            metric.population_truth_distance_to_mean_envelope
                        ),
                        "evaluable_calibration_met": (
                            metric.evaluable_calibration_met
                        ),
                        "truth_aligned_recovery_met": (
                            metric.truth_aligned_recovery_met
                        ),
                        "population_truth_recovered_by_mean_envelope": (
                            metric.population_truth_recovered_by_mean_envelope
                        ),
                        "identification_target_met": (
                            metric.identification_target_met
                        ),
                    }
                    for metric in result.metric_performance
                ],
            }
            for result in report.scenario_results
        ],
        "claim_boundary": {
            "aggregate_simulation_only": report.aggregate_simulation_only,
            "real_clinical_outcomes_included": (
                report.real_clinical_outcomes_included
            ),
            "automatic_missingness_correction_included": (
                report.automatic_missingness_correction_included
            ),
            "sampling_uncertainty_intervals_included": (
                report.sampling_uncertainty_intervals_included
            ),
            "operational_estimate_uses_latent_truth": (
                report.operational_estimate_uses_latent_truth
            ),
        },
    }


def clinical_outcome_pattern_mixture_validation_summary(
    report: ClinicalOutcomePatternMixtureReport,
    *,
    failures: Sequence[str] = (),
    scope: str,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureReport,
        "report",
    )
    _require_text(scope, "scope")
    resolved_failures = tuple(str(item) for item in failures)
    return {
        "schema_version": (
            "adds.clinical-outcome-pattern-mixture-validation-summary.v1"
        ),
        "valid": not resolved_failures,
        "scope": scope,
        "report_fingerprint": report.fingerprint,
        "failures": list(resolved_failures),
    }


def clinical_outcome_pattern_mixture_protocol_envelope(
    protocol: ClinicalOutcomePatternMixtureProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomePatternMixtureProtocol,
        "protocol",
    )
    return {
        "schema_version": CLINICAL_OUTCOME_PATTERN_MIXTURE_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_pattern_mixture_report_envelope(
    report: ClinicalOutcomePatternMixtureReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        ClinicalOutcomePatternMixtureReport,
        "report",
    )
    return {
        "schema_version": CLINICAL_OUTCOME_PATTERN_MIXTURE_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    if _sha256(value) != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def clinical_outcome_pattern_mixture_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_protocol_envelope",
        schema_version=CLINICAL_OUTCOME_PATTERN_MIXTURE_PROTOCOL_SCHEMA_VERSION,
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
            "log_imor_grid",
            "monte_carlo_confidence_level",
            "minimum_analyzable_rate",
            "maximum_mean_identification_width",
            "maximum_absolute_bias",
            "method_id",
            "metadata",
        },
    )
    protocol = ClinicalOutcomePatternMixtureProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        stress_protocol_fingerprint=data["stress_protocol_fingerprint"],
        log_imor_grid=tuple(
            _sequence(data["log_imor_grid"], "protocol.log_imor_grid")
        ),
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        minimum_analyzable_rate=data["minimum_analyzable_rate"],
        maximum_mean_identification_width=(
            data["maximum_mean_identification_width"]
        ),
        maximum_absolute_bias=data["maximum_absolute_bias"],
        method_id=data["method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "pattern-mixture protocol")
    return protocol


def _parse_status_count(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomePatternMixtureStatusCount(
        status=_parse_enum(
            ClinicalOutcomePatternMixtureStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_grid_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureGridPerformance:
    data = _record(
        value,
        path,
        {
            "log_imor",
            "informative_missingness_odds_ratio",
            "population_true_value",
            "estimate_count",
            "mean_estimate",
            "population_bias",
            "population_root_mean_squared_error",
        },
    )
    return ClinicalOutcomePatternMixtureGridPerformance(**data)


def _parse_metric_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureMetricPerformance:
    data = _record(
        value,
        path,
        {
            "metric",
            "replicate_count",
            "analyzable_replicates",
            "population_true_value",
            "evaluable_true_value",
            "naive_mean_estimate",
            "naive_population_bias",
            "naive_population_root_mean_squared_error",
            "naive_evaluable_bias",
            "naive_evaluable_root_mean_squared_error",
            "truth_aligned_mean_estimate",
            "truth_aligned_population_bias",
            "truth_aligned_population_root_mean_squared_error",
            "sensitivity_envelope_inclusion",
            "mean_sensitivity_envelope_lower",
            "mean_sensitivity_envelope_upper",
            "mean_sensitivity_envelope_width",
            "population_truth_distance_to_mean_envelope",
            "maximum_absolute_bias",
            "maximum_mean_identification_width",
            "evaluable_calibration_met",
            "truth_aligned_recovery_met",
            "population_truth_recovered_by_mean_envelope",
            "identification_target_met",
            "grid_performance",
        },
    )
    return ClinicalOutcomePatternMixtureMetricPerformance(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        replicate_count=data["replicate_count"],
        analyzable_replicates=data["analyzable_replicates"],
        population_true_value=data["population_true_value"],
        evaluable_true_value=data["evaluable_true_value"],
        naive_mean_estimate=data["naive_mean_estimate"],
        naive_population_bias=data["naive_population_bias"],
        naive_population_root_mean_squared_error=(
            data["naive_population_root_mean_squared_error"]
        ),
        naive_evaluable_bias=data["naive_evaluable_bias"],
        naive_evaluable_root_mean_squared_error=(
            data["naive_evaluable_root_mean_squared_error"]
        ),
        truth_aligned_mean_estimate=data["truth_aligned_mean_estimate"],
        truth_aligned_population_bias=data["truth_aligned_population_bias"],
        truth_aligned_population_root_mean_squared_error=(
            data["truth_aligned_population_root_mean_squared_error"]
        ),
        sensitivity_envelope_inclusion=_parse_design_rate(
            data["sensitivity_envelope_inclusion"],
            f"{path}.sensitivity_envelope_inclusion",
        ),
        mean_sensitivity_envelope_lower=data["mean_sensitivity_envelope_lower"],
        mean_sensitivity_envelope_upper=data["mean_sensitivity_envelope_upper"],
        mean_sensitivity_envelope_width=(
            data["mean_sensitivity_envelope_width"]
        ),
        population_truth_distance_to_mean_envelope=(
            data["population_truth_distance_to_mean_envelope"]
        ),
        maximum_absolute_bias=data["maximum_absolute_bias"],
        maximum_mean_identification_width=(
            data["maximum_mean_identification_width"]
        ),
        evaluable_calibration_met=data["evaluable_calibration_met"],
        truth_aligned_recovery_met=data["truth_aligned_recovery_met"],
        population_truth_recovered_by_mean_envelope=(
            data["population_truth_recovered_by_mean_envelope"]
        ),
        identification_target_met=data["identification_target_met"],
        grid_performance=tuple(
            _parse_grid_performance(item, f"{path}.grid_performance[{index}]")
            for index, item in enumerate(
                _sequence(data["grid_performance"], f"{path}.grid_performance")
            )
        ),
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomePatternMixtureScenarioResult:
    data = _record(
        value,
        path,
        {
            "scenario_id",
            "stage",
            "endpoint_family",
            "population_favorable_prevalence",
            "evaluable_favorable_prevalence",
            "expected_evaluable_probability",
            "true_log_imor",
            "true_informative_missingness_odds_ratio",
            "grid_brackets_true_log_imor",
            "replicate_count",
            "status_counts",
            "analyzable_rate",
            "metric_performance",
            "analyzable_target_met",
            "all_evaluable_calibration_targets_met",
            "all_truth_aligned_recovery_targets_met",
            "all_identification_targets_met",
            "research_target_met",
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        },
    )
    return ClinicalOutcomePatternMixtureScenarioResult(
        scenario_id=data["scenario_id"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        endpoint_family=data["endpoint_family"],
        population_favorable_prevalence=data["population_favorable_prevalence"],
        evaluable_favorable_prevalence=data["evaluable_favorable_prevalence"],
        expected_evaluable_probability=data["expected_evaluable_probability"],
        true_log_imor=data["true_log_imor"],
        true_informative_missingness_odds_ratio=(
            data["true_informative_missingness_odds_ratio"]
        ),
        grid_brackets_true_log_imor=data["grid_brackets_true_log_imor"],
        replicate_count=data["replicate_count"],
        status_counts=tuple(
            _parse_status_count(item, f"{path}.status_counts[{index}]")
            for index, item in enumerate(
                _sequence(data["status_counts"], f"{path}.status_counts")
            )
        ),
        analyzable_rate=_parse_design_rate(
            data["analyzable_rate"],
            f"{path}.analyzable_rate",
        ),
        metric_performance=tuple(
            _parse_metric_performance(item, f"{path}.metric_performance[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["metric_performance"],
                    f"{path}.metric_performance",
                )
            )
        ),
        analyzable_target_met=data["analyzable_target_met"],
        all_evaluable_calibration_targets_met=(
            data["all_evaluable_calibration_targets_met"]
        ),
        all_truth_aligned_recovery_targets_met=(
            data["all_truth_aligned_recovery_targets_met"]
        ),
        all_identification_targets_met=data["all_identification_targets_met"],
        research_target_met=data["research_target_met"],
        rng_stream_sha256=data["rng_stream_sha256"],
        outcome_rng_stream_sha256=data["outcome_rng_stream_sha256"],
        evaluability_rng_stream_sha256=data["evaluability_rng_stream_sha256"],
    )


def clinical_outcome_pattern_mixture_report_from_dict(
    value: Any,
) -> ClinicalOutcomePatternMixtureReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_pattern_mixture_report_envelope",
        schema_version=CLINICAL_OUTCOME_PATTERN_MIXTURE_REPORT_SCHEMA_VERSION,
        payload_field="report",
    )
    data = _record(
        payload,
        "report",
        {
            "protocol_id",
            "protocol_fingerprint",
            "stress_protocol_id",
            "stress_protocol_fingerprint",
            "stress_report_fingerprint",
            "method_id",
            "rng_method_id",
            "replicates",
            "log_imor_grid",
            "monte_carlo_confidence_level",
            "minimum_analyzable_rate",
            "maximum_mean_identification_width",
            "maximum_absolute_bias",
            "scenario_results",
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "automatic_missingness_correction_included",
            "sampling_uncertainty_intervals_included",
            "latent_truth_recovery_diagnostic_included",
            "operational_estimate_uses_latent_truth",
            "limitations",
        },
    )
    report = ClinicalOutcomePatternMixtureReport(
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        stress_protocol_id=data["stress_protocol_id"],
        stress_protocol_fingerprint=data["stress_protocol_fingerprint"],
        stress_report_fingerprint=data["stress_report_fingerprint"],
        method_id=data["method_id"],
        rng_method_id=data["rng_method_id"],
        replicates=data["replicates"],
        log_imor_grid=tuple(
            _sequence(data["log_imor_grid"], "report.log_imor_grid")
        ),
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        minimum_analyzable_rate=data["minimum_analyzable_rate"],
        maximum_mean_identification_width=(
            data["maximum_mean_identification_width"]
        ),
        maximum_absolute_bias=data["maximum_absolute_bias"],
        scenario_results=tuple(
            _parse_scenario_result(item, f"report.scenario_results[{index}]")
            for index, item in enumerate(
                _sequence(data["scenario_results"], "report.scenario_results")
            )
        ),
        aggregate_simulation_only=data["aggregate_simulation_only"],
        replicate_level_records_included=(
            data["replicate_level_records_included"]
        ),
        unit_level_records_included=data["unit_level_records_included"],
        real_clinical_outcomes_included=data["real_clinical_outcomes_included"],
        automatic_missingness_correction_included=(
            data["automatic_missingness_correction_included"]
        ),
        sampling_uncertainty_intervals_included=(
            data["sampling_uncertainty_intervals_included"]
        ),
        latent_truth_recovery_diagnostic_included=(
            data["latent_truth_recovery_diagnostic_included"]
        ),
        operational_estimate_uses_latent_truth=(
            data["operational_estimate_uses_latent_truth"]
        ),
        limitations=tuple(
            _sequence(data["limitations"], "report.limitations")
        ),
    )
    _check_integrity(report, integrity, "pattern-mixture report")
    return report


def clinical_outcome_pattern_mixture_protocol_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureProtocol:
    return clinical_outcome_pattern_mixture_protocol_from_dict(
        _strict_json(payload, "pattern-mixture protocol")
    )


def clinical_outcome_pattern_mixture_report_from_json(
    payload: str,
) -> ClinicalOutcomePatternMixtureReport:
    return clinical_outcome_pattern_mixture_report_from_dict(
        _strict_json(payload, "pattern-mixture report")
    )
