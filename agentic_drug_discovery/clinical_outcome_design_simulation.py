"""Prospective design simulation for clustered clinical outcome boards."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

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
    _wilson_interval,
)
from .clinical_outcome_uncertainty import (
    CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID,
    ClinicalClusterRobustEstimate,
    ClusterInferenceStatus,
    _cluster_diagnostic,
    _cluster_robust_estimate,
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


CLINICAL_OUTCOME_DESIGN_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-design-simulation-protocol.v1"
)
CLINICAL_OUTCOME_DESIGN_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-design-simulation-report.v1"
)
CLINICAL_OUTCOME_DESIGN_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-design-simulation-summary.v1"
)
CLINICAL_OUTCOME_DESIGN_SIMULATION_METHOD_ID = (
    "adds.prospective-clinical-outcome-design.beta-binomial.v1"
)
CLINICAL_OUTCOME_DESIGN_RNG_METHOD_ID = "adds.mt19937-polya-urn.v1"
CLINICAL_OUTCOME_IID_REFERENCE_METHOD_ID = "adds.iid-unit-normal-reference.v1"

MAX_DESIGN_SCENARIOS = 128
MAX_DESIGN_GATES = 64
MAX_DESIGN_REPLICATES = 100_000
MAX_DESIGN_UNITS_PER_SCENARIO = 100_000
MAX_DESIGN_WORK_UNITS = 100_000_000
MIN_DESIGN_REPLICATES = 100
_IID_MAXIMUM_CLUSTER_FRACTION = 0.999999999999


class ClinicalOutcomeDesignSimulationError(ValueError):
    """Raised when a prospective uncertainty-design simulation cannot run safely."""


class ClinicalOutcomeDesignMetric(str, Enum):
    OBSERVED_FAVORABLE_RATE = "observed_favorable_rate"
    POLICY_A_BRIER_SCORE = "policy_a_brier_score"
    POLICY_B_BRIER_SCORE = "policy_b_brier_score"
    POLICY_A_CALIBRATION_IN_THE_LARGE = (
        "policy_a_calibration_in_the_large"
    )
    POLICY_B_CALIBRATION_IN_THE_LARGE = (
        "policy_b_calibration_in_the_large"
    )
    POLICY_A_CLASSIFICATION_ACCURACY = "policy_a_classification_accuracy"
    POLICY_B_CLASSIFICATION_ACCURACY = "policy_b_classification_accuracy"
    BRIER_DIFFERENCE_B_MINUS_A = "brier_difference_b_minus_a"


_METRIC_ORDER = tuple(ClinicalOutcomeDesignMetric)
_STATUS_ORDER = tuple(ClusterInferenceStatus)
_SIGNED_METRICS = {
    ClinicalOutcomeDesignMetric.POLICY_A_CALIBRATION_IN_THE_LARGE,
    ClinicalOutcomeDesignMetric.POLICY_B_CALIBRATION_IN_THE_LARGE,
    ClinicalOutcomeDesignMetric.BRIER_DIFFERENCE_B_MINUS_A,
}
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic prospective design analysis; it contains no real "
        "clinical outcomes and does not validate a deployed policy or evidence board."
    ),
    (
        "The beta-binomial Polya-urn generator assumes independent top-level clusters, "
        "exchangeable binary outcomes within each cluster, and one declared marginal "
        "prevalence and intracluster correlation per scenario."
    ),
    (
        "Evaluability is missing completely at random in this v1 generator; informative "
        "missingness, adjudication error, cross-cluster dependence, and multi-way "
        "dependence require separate stress scenarios or methods."
    ),
    (
        "Prediction patterns are fixed before simulated outcomes and are intended to "
        "exercise additive estimators, paired covariance, and clipping; they do not model "
        "clinical discrimination or policy learning."
    ),
    (
        "Empirical coverage and interval-yield estimates have finite Monte Carlo error; "
        "the report retains Wilson bounds and evaluates design targets against their "
        "lower bounds."
    ),
    (
        "Passing a candidate gate under declared scenarios is not a universal cluster "
        "minimum or dominance threshold and does not automatically approve an uncertainty "
        "protocol."
    ),
    (
        "The IID unit-as-cluster interval is a diagnostic reference only and is not an "
        "acceptable replacement when dependence clusters are present."
    ),
    (
        "Aggregate simulation results do not establish treatment efficacy, safety, "
        "clinical utility, policy superiority, transportability, or regulatory acceptability."
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


def _require_finite(
    value: float,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if value is None:
        raise TypeError(f"{field_name} must be numeric")
    _require_optional_finite(
        value,
        field_name,
        minimum=minimum,
        maximum=maximum,
    )


def _metric_bounds(metric: ClinicalOutcomeDesignMetric) -> tuple[float, float]:
    return (-1.0, 1.0) if metric in _SIGNED_METRICS else (0.0, 1.0)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignScenario(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    cluster_sizes: tuple[int, ...]
    favorable_prevalence: float
    intracluster_correlation: float
    evaluable_probability: float
    classification_threshold: float
    policy_a_probability_pattern: tuple[float, ...]
    policy_b_probability_pattern: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        cluster_sizes = _tuple(self.cluster_sizes, "cluster_sizes")
        object.__setattr__(self, "cluster_sizes", cluster_sizes)
        if len(cluster_sizes) < 2:
            raise ValueError("design scenario requires at least two clusters")
        for size in cluster_sizes:
            _require_positive_int(size, "cluster_sizes item")
        if cluster_sizes != tuple(sorted(cluster_sizes, reverse=True)):
            raise ValueError("cluster_sizes must use canonical non-increasing order")
        if sum(cluster_sizes) > MAX_DESIGN_UNITS_PER_SCENARIO:
            raise ValueError("design scenario exceeds the unit limit")
        _require_probability(self.favorable_prevalence, "favorable_prevalence")
        if self.favorable_prevalence in (0.0, 1.0):
            raise ValueError("favorable_prevalence must be strictly between zero and one")
        _require_probability(
            self.intracluster_correlation,
            "intracluster_correlation",
        )
        if self.intracluster_correlation == 1.0:
            raise ValueError("intracluster_correlation must be less than one")
        _require_probability(self.evaluable_probability, "evaluable_probability")
        if self.evaluable_probability == 0.0:
            raise ValueError("evaluable_probability must be greater than zero")
        _require_probability(
            self.classification_threshold,
            "classification_threshold",
        )
        patterns = []
        for field_name in (
            "policy_a_probability_pattern",
            "policy_b_probability_pattern",
        ):
            pattern = _tuple(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, pattern)
            if not pattern or len(pattern) > 64:
                raise ValueError(f"{field_name} must contain between one and 64 values")
            for probability in pattern:
                _require_probability(probability, f"{field_name} item")
            patterns.append(pattern)
        if len(patterns[0]) != len(patterns[1]):
            raise ValueError("policy probability patterns must have equal length")
        pattern_length = len(patterns[0])
        if any(size % pattern_length for size in cluster_sizes):
            raise ValueError(
                "each cluster size must be divisible by the prediction-pattern length"
            )

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.stage.value, self.endpoint_family, self.scenario_id)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignGate(SerializableRecord):
    gate_id: str
    minimum_evaluable_clusters: int
    maximum_evaluable_cluster_fraction: float

    def __post_init__(self) -> None:
        _require_text(self.gate_id, "gate_id")
        _require_positive_int(
            self.minimum_evaluable_clusters,
            "minimum_evaluable_clusters",
        )
        if self.minimum_evaluable_clusters < 2:
            raise ValueError("minimum_evaluable_clusters must be at least two")
        _require_probability(
            self.maximum_evaluable_cluster_fraction,
            "maximum_evaluable_cluster_fraction",
        )
        if self.maximum_evaluable_cluster_fraction in (0.0, 1.0):
            raise ValueError(
                "maximum_evaluable_cluster_fraction must be strictly between zero and one"
            )

    @property
    def sort_key(self) -> tuple[int, float, str]:
        return (
            self.minimum_evaluable_clusters,
            self.maximum_evaluable_cluster_fraction,
            self.gate_id,
        )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignSimulationProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    confidence_level: float
    monte_carlo_confidence_level: float
    replicates: int
    random_seed: int
    coverage_tolerance: float
    minimum_interval_yield: float
    gates: tuple[ClinicalOutcomeDesignGate, ...]
    scenarios: tuple[ClinicalOutcomeDesignScenario, ...]
    simulation_method_id: str = CLINICAL_OUTCOME_DESIGN_SIMULATION_METHOD_ID
    rng_method_id: str = CLINICAL_OUTCOME_DESIGN_RNG_METHOD_ID
    uncertainty_method_id: str = CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("protocol_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        for field_name in ("confidence_level", "monte_carlo_confidence_level"):
            value = getattr(self, field_name)
            _require_probability(value, field_name)
            if not 0.5 < float(value) < 1.0:
                raise ValueError(f"{field_name} must be between 0.5 and 1")
        _require_positive_int(self.replicates, "replicates")
        if not MIN_DESIGN_REPLICATES <= self.replicates <= MAX_DESIGN_REPLICATES:
            raise ValueError(
                f"replicates must be between {MIN_DESIGN_REPLICATES} and "
                f"{MAX_DESIGN_REPLICATES}"
            )
        _require_non_negative_int(self.random_seed, "random_seed")
        if self.random_seed > 2**63 - 1:
            raise ValueError("random_seed must fit in a signed 64-bit integer")
        _require_probability(self.coverage_tolerance, "coverage_tolerance")
        if self.coverage_tolerance >= self.confidence_level:
            raise ValueError("coverage_tolerance must be smaller than confidence_level")
        _require_probability(self.minimum_interval_yield, "minimum_interval_yield")
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be greater than zero")
        gates = _tuple(self.gates, "gates")
        object.__setattr__(self, "gates", gates)
        if not gates or len(gates) > MAX_DESIGN_GATES:
            raise ValueError(f"gates must contain between one and {MAX_DESIGN_GATES} items")
        for gate in gates:
            _require_instance(gate, ClinicalOutcomeDesignGate, "gates item")
        if tuple(item.sort_key for item in gates) != tuple(
            sorted(item.sort_key for item in gates)
        ):
            raise ValueError("gates must use canonical order")
        if len({item.gate_id for item in gates}) != len(gates):
            raise ValueError("gate ids must be unique")
        if len(
            {
                (
                    item.minimum_evaluable_clusters,
                    item.maximum_evaluable_cluster_fraction,
                )
                for item in gates
            }
        ) != len(gates):
            raise ValueError("gate settings must be unique")
        scenarios = _tuple(self.scenarios, "scenarios")
        object.__setattr__(self, "scenarios", scenarios)
        if not scenarios or len(scenarios) > MAX_DESIGN_SCENARIOS:
            raise ValueError(
                f"scenarios must contain between one and {MAX_DESIGN_SCENARIOS} items"
            )
        for scenario in scenarios:
            _require_instance(
                scenario,
                ClinicalOutcomeDesignScenario,
                "scenarios item",
            )
        if tuple(item.sort_key for item in scenarios) != tuple(
            sorted(item.sort_key for item in scenarios)
        ):
            raise ValueError("scenarios must use canonical order")
        if len({item.scenario_id for item in scenarios}) != len(scenarios):
            raise ValueError("scenario ids must be unique")
        work_units = self.replicates * sum(
            sum(item.cluster_sizes) * (1 + len(_METRIC_ORDER) * len(gates))
            for item in scenarios
        )
        if work_units > MAX_DESIGN_WORK_UNITS:
            raise ClinicalOutcomeDesignSimulationError(
                "design simulation exceeds the bounded work budget"
            )
        if self.simulation_method_id != CLINICAL_OUTCOME_DESIGN_SIMULATION_METHOD_ID:
            raise ValueError("simulation_method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_DESIGN_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        if self.uncertainty_method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("uncertainty_method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError("design protocol metadata cannot contain evaluator outcomes")
        object.__setattr__(self, "metadata", metadata)

    @property
    def coverage_target(self) -> float:
        return _round_metric(self.confidence_level - self.coverage_tolerance)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignStructure(SerializableRecord):
    cluster_count: int
    total_units: int
    minimum_cluster_size: int
    maximum_cluster_size: int
    mean_cluster_size: float
    cluster_size_coefficient_of_variation: float
    maximum_cluster_fraction: float
    effective_cluster_count: float

    def __post_init__(self) -> None:
        for field_name in (
            "cluster_count",
            "total_units",
            "minimum_cluster_size",
            "maximum_cluster_size",
        ):
            _require_positive_int(getattr(self, field_name), field_name)
        if self.cluster_count > self.total_units:
            raise ValueError("cluster_count exceeds total_units")
        if not self.minimum_cluster_size <= self.maximum_cluster_size:
            raise ValueError("cluster-size extrema are inconsistent")
        _require_finite(
            self.mean_cluster_size,
            "mean_cluster_size",
            minimum=1.0,
        )
        _require_finite(
            self.cluster_size_coefficient_of_variation,
            "cluster_size_coefficient_of_variation",
            minimum=0.0,
        )
        _require_finite(
            self.maximum_cluster_fraction,
            "maximum_cluster_fraction",
            minimum=0.0,
            maximum=1.0,
        )
        _require_finite(
            self.effective_cluster_count,
            "effective_cluster_count",
            minimum=1.0,
            maximum=float(self.cluster_count),
        )


def _design_structure(
    scenario: ClinicalOutcomeDesignScenario,
) -> ClinicalOutcomeDesignStructure:
    sizes = scenario.cluster_sizes
    total = sum(sizes)
    mean = total / len(sizes)
    variance = sum((size - mean) ** 2 for size in sizes) / len(sizes)
    return ClinicalOutcomeDesignStructure(
        cluster_count=len(sizes),
        total_units=total,
        minimum_cluster_size=min(sizes),
        maximum_cluster_size=max(sizes),
        mean_cluster_size=_round_metric(mean),
        cluster_size_coefficient_of_variation=_round_metric(
            math.sqrt(variance) / mean
        ),
        maximum_cluster_fraction=_round_metric(max(sizes) / total),
        effective_cluster_count=_round_metric(
            total * total / sum(size * size for size in sizes)
        ),
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignRate(SerializableRecord):
    event_count: int
    total_count: int
    rate: float | None
    lower: float | None
    upper: float | None
    confidence_level: float

    def __post_init__(self) -> None:
        _require_non_negative_int(self.event_count, "event_count")
        _require_non_negative_int(self.total_count, "total_count")
        if self.event_count > self.total_count:
            raise ValueError("event_count exceeds total_count")
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        for field_name in ("rate", "lower", "upper"):
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
                maximum=1.0,
            )
        if self.total_count == 0:
            if any(value is not None for value in (self.rate, self.lower, self.upper)):
                raise ValueError("empty rates require null estimates and bounds")
            return
        expected_rate = _round_metric(self.event_count / self.total_count)
        expected_lower, expected_upper = _wilson_interval(
            self.event_count,
            self.total_count,
            self.confidence_level,
        )
        if (
            self.rate != expected_rate
            or self.lower != expected_lower
            or self.upper != expected_upper
        ):
            raise ValueError("rate estimate or Wilson bounds are inconsistent")


def _design_rate(
    event_count: int,
    total_count: int,
    confidence_level: float,
) -> ClinicalOutcomeDesignRate:
    if total_count == 0:
        rate = lower = upper = None
    else:
        rate = _round_metric(event_count / total_count)
        lower, upper = _wilson_interval(event_count, total_count, confidence_level)
    return ClinicalOutcomeDesignRate(
        event_count=event_count,
        total_count=total_count,
        rate=rate,
        lower=lower,
        upper=upper,
        confidence_level=confidence_level,
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignStatusCount(SerializableRecord):
    status: ClusterInferenceStatus
    count: int

    def __post_init__(self) -> None:
        _require_instance(self.status, ClusterInferenceStatus, "status")
        _require_non_negative_int(self.count, "count")


def _status_count_records(
    counts: Mapping[ClusterInferenceStatus, int],
) -> tuple[ClinicalOutcomeDesignStatusCount, ...]:
    return tuple(
        ClinicalOutcomeDesignStatusCount(status=status, count=counts.get(status, 0))
        for status in _STATUS_ORDER
    )


def _validate_status_counts(
    values: Sequence[ClinicalOutcomeDesignStatusCount],
    replicate_count: int,
) -> dict[ClusterInferenceStatus, int]:
    resolved = _tuple(values, "status_counts")
    for item in resolved:
        _require_instance(item, ClinicalOutcomeDesignStatusCount, "status_counts item")
    if tuple(item.status for item in resolved) != _STATUS_ORDER:
        raise ValueError("status_counts must exactly cover canonical statuses")
    if sum(item.count for item in resolved) != replicate_count:
        raise ValueError("status counts do not sum to replicate_count")
    return {item.status: item.count for item in resolved}


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignMetricPerformance(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    true_value: float
    replicate_count: int
    point_estimate_count: int
    interval_count: int
    covered_interval_count: int
    interval_yield: ClinicalOutcomeDesignRate
    coverage: ClinicalOutcomeDesignRate
    mean_estimate: float | None
    bias: float | None
    root_mean_squared_error: float | None
    empirical_standard_deviation: float | None
    mean_reported_standard_error: float | None
    mean_interval_width: float | None
    mean_se_to_empirical_sd_ratio: float | None
    status_counts: tuple[ClinicalOutcomeDesignStatusCount, ...]

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        lower_bound, upper_bound = _metric_bounds(self.metric)
        _require_finite(
            self.true_value,
            "true_value",
            minimum=lower_bound,
            maximum=upper_bound,
        )
        _require_positive_int(self.replicate_count, "replicate_count")
        for field_name in (
            "point_estimate_count",
            "interval_count",
            "covered_interval_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.point_estimate_count > self.replicate_count:
            raise ValueError("point_estimate_count exceeds replicate_count")
        if self.interval_count > self.point_estimate_count:
            raise ValueError("interval_count exceeds point_estimate_count")
        if self.covered_interval_count > self.interval_count:
            raise ValueError("covered_interval_count exceeds interval_count")
        for value, field_name in (
            (self.interval_yield, "interval_yield"),
            (self.coverage, "coverage"),
        ):
            _require_instance(value, ClinicalOutcomeDesignRate, field_name)
        if (
            self.interval_yield.event_count != self.interval_count
            or self.interval_yield.total_count != self.replicate_count
        ):
            raise ValueError("interval_yield denominator is inconsistent")
        if (
            self.coverage.event_count != self.covered_interval_count
            or self.coverage.total_count != self.interval_count
            or self.coverage.confidence_level != self.interval_yield.confidence_level
        ):
            raise ValueError("coverage denominator is inconsistent")
        for field_name in (
            "mean_estimate",
            "bias",
            "root_mean_squared_error",
            "empirical_standard_deviation",
            "mean_reported_standard_error",
            "mean_interval_width",
            "mean_se_to_empirical_sd_ratio",
        ):
            minimum = (
                0.0
                if field_name
                in {
                    "root_mean_squared_error",
                    "empirical_standard_deviation",
                    "mean_reported_standard_error",
                    "mean_interval_width",
                    "mean_se_to_empirical_sd_ratio",
                }
                else None
            )
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=minimum,
            )
        if self.mean_estimate is not None and not (
            lower_bound <= self.mean_estimate <= upper_bound
        ):
            raise ValueError("mean_estimate falls outside the metric scale")
        status_counts = _tuple(self.status_counts, "status_counts")
        object.__setattr__(self, "status_counts", status_counts)
        counts = _validate_status_counts(status_counts, self.replicate_count)
        if self.point_estimate_count != (
            self.replicate_count
            - counts[ClusterInferenceStatus.NO_EVALUABLE_UNITS]
        ):
            raise ValueError("point_estimate_count is inconsistent with statuses")
        if self.interval_count != counts[ClusterInferenceStatus.COMPUTED]:
            raise ValueError("interval_count is inconsistent with statuses")
        if self.point_estimate_count == 0:
            if any(
                value is not None
                for value in (
                    self.mean_estimate,
                    self.bias,
                    self.root_mean_squared_error,
                    self.empirical_standard_deviation,
                )
            ):
                raise ValueError("empty point estimates require null aggregate metrics")
        else:
            if any(
                value is None
                for value in (
                    self.mean_estimate,
                    self.bias,
                    self.root_mean_squared_error,
                )
            ):
                raise ValueError("point estimates require aggregate error metrics")
            assert self.mean_estimate is not None
            if self.bias != _round_metric(self.mean_estimate - self.true_value):
                raise ValueError("bias is inconsistent with mean_estimate and truth")
            if self.point_estimate_count == 1:
                if self.empirical_standard_deviation is not None:
                    raise ValueError("one point estimate requires null empirical deviation")
            elif self.empirical_standard_deviation is None:
                raise ValueError("multiple point estimates require empirical deviation")
        if self.interval_count == 0:
            if any(
                value is not None
                for value in (
                    self.mean_reported_standard_error,
                    self.mean_interval_width,
                    self.mean_se_to_empirical_sd_ratio,
                )
            ):
                raise ValueError("empty intervals require null interval aggregates")
        else:
            if (
                self.mean_reported_standard_error is None
                or self.mean_interval_width is None
            ):
                raise ValueError("reported intervals require width and standard error")
            expected_ratio = (
                None
                if self.empirical_standard_deviation in (None, 0.0)
                else _round_metric(
                    self.mean_reported_standard_error
                    / self.empirical_standard_deviation
                )
            )
            if self.mean_se_to_empirical_sd_ratio != expected_ratio:
                raise ValueError("standard-error calibration ratio is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignReplicateDiagnostics(SerializableRecord):
    replicate_count: int
    no_evaluable_replicates: int
    mean_evaluable_units: float
    minimum_evaluable_units: int
    maximum_evaluable_units: int
    mean_evaluable_cluster_count: float
    minimum_evaluable_cluster_count: int
    maximum_evaluable_cluster_count: int
    mean_largest_evaluable_cluster_fraction: float | None
    maximum_largest_evaluable_cluster_fraction: float | None

    def __post_init__(self) -> None:
        _require_positive_int(self.replicate_count, "replicate_count")
        for field_name in (
            "no_evaluable_replicates",
            "minimum_evaluable_units",
            "maximum_evaluable_units",
            "minimum_evaluable_cluster_count",
            "maximum_evaluable_cluster_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.no_evaluable_replicates > self.replicate_count:
            raise ValueError("no_evaluable_replicates exceeds replicate_count")
        if self.minimum_evaluable_units > self.maximum_evaluable_units:
            raise ValueError("evaluable-unit extrema are inconsistent")
        if self.minimum_evaluable_cluster_count > self.maximum_evaluable_cluster_count:
            raise ValueError("evaluable-cluster extrema are inconsistent")
        for field_name in (
            "mean_evaluable_units",
            "mean_evaluable_cluster_count",
        ):
            _require_finite(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
            )
        for field_name in (
            "mean_largest_evaluable_cluster_fraction",
            "maximum_largest_evaluable_cluster_fraction",
        ):
            _require_optional_finite(
                getattr(self, field_name),
                field_name,
                minimum=0.0,
                maximum=1.0,
            )
        if self.no_evaluable_replicates == self.replicate_count:
            if (
                self.mean_largest_evaluable_cluster_fraction is not None
                or self.maximum_largest_evaluable_cluster_fraction is not None
            ):
                raise ValueError("empty replicates require null largest-cluster metrics")
        elif (
            self.mean_largest_evaluable_cluster_fraction is None
            or self.maximum_largest_evaluable_cluster_fraction is None
        ):
            raise ValueError("evaluable replicates require largest-cluster metrics")
        if self.no_evaluable_replicates > 0 and (
            self.minimum_evaluable_units != 0
            or self.minimum_evaluable_cluster_count != 0
        ):
            raise ValueError("no-evaluable replicates require zero minima")
        if self.no_evaluable_replicates == self.replicate_count and (
            self.maximum_evaluable_units != 0
            or self.maximum_evaluable_cluster_count != 0
            or self.mean_evaluable_units != 0.0
            or self.mean_evaluable_cluster_count != 0.0
        ):
            raise ValueError("all-empty replicate diagnostics are inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignGatePerformance(SerializableRecord):
    gate: ClinicalOutcomeDesignGate
    replicate_count: int
    diagnostic_status_counts: tuple[ClinicalOutcomeDesignStatusCount, ...]
    diagnostic_interval_eligibility: ClinicalOutcomeDesignRate
    coverage_target: float
    minimum_interval_yield: float
    all_metric_coverage_targets_met: bool
    all_metric_yield_targets_met: bool
    design_target_met: bool
    metric_performance: tuple[ClinicalOutcomeDesignMetricPerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(self.gate, ClinicalOutcomeDesignGate, "gate")
        _require_positive_int(self.replicate_count, "replicate_count")
        statuses = _tuple(self.diagnostic_status_counts, "diagnostic_status_counts")
        object.__setattr__(self, "diagnostic_status_counts", statuses)
        counts = _validate_status_counts(statuses, self.replicate_count)
        if counts[ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE] != 0:
            raise ValueError("diagnostics cannot report zero cluster variance")
        _require_instance(
            self.diagnostic_interval_eligibility,
            ClinicalOutcomeDesignRate,
            "diagnostic_interval_eligibility",
        )
        if (
            self.diagnostic_interval_eligibility.event_count
            != counts[ClusterInferenceStatus.COMPUTED]
            or self.diagnostic_interval_eligibility.total_count != self.replicate_count
        ):
            raise ValueError("diagnostic interval eligibility is inconsistent")
        for field_name in ("coverage_target", "minimum_interval_yield"):
            _require_probability(getattr(self, field_name), field_name)
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be greater than zero")
        for field_name in (
            "all_metric_coverage_targets_met",
            "all_metric_yield_targets_met",
            "design_target_met",
        ):
            _require_bool(getattr(self, field_name), field_name)
        metrics = _tuple(self.metric_performance, "metric_performance")
        object.__setattr__(self, "metric_performance", metrics)
        for metric in metrics:
            _require_instance(
                metric,
                ClinicalOutcomeDesignMetricPerformance,
                "metric_performance item",
            )
            if metric.replicate_count != self.replicate_count:
                raise ValueError("gate metric replicate count is inconsistent")
            metric_counts = {
                item.status: item.count for item in metric.status_counts
            }
            for status in (
                ClusterInferenceStatus.NO_EVALUABLE_UNITS,
                ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
                ClusterInferenceStatus.DOMINANT_CLUSTER,
            ):
                if metric_counts[status] != counts[status]:
                    raise ValueError("metric diagnostic statuses are inconsistent")
            if (
                metric_counts[ClusterInferenceStatus.COMPUTED]
                + metric_counts[ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE]
                != counts[ClusterInferenceStatus.COMPUTED]
            ):
                raise ValueError("metric interval statuses are inconsistent")
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("gate metrics must exactly cover canonical metrics")
        coverage_met = all(
            item.coverage.lower is not None
            and item.coverage.lower >= self.coverage_target
            for item in metrics
        )
        yield_met = all(
            item.interval_yield.lower is not None
            and item.interval_yield.lower >= self.minimum_interval_yield
            for item in metrics
        )
        if self.all_metric_coverage_targets_met != coverage_met:
            raise ValueError("coverage target flag is inconsistent")
        if self.all_metric_yield_targets_met != yield_met:
            raise ValueError("interval-yield target flag is inconsistent")
        if self.design_target_met != (coverage_met and yield_met):
            raise ValueError("design target flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignScenarioResult(SerializableRecord):
    scenario: ClinicalOutcomeDesignScenario
    structure: ClinicalOutcomeDesignStructure
    rng_stream_sha256: str
    replicate_diagnostics: ClinicalOutcomeDesignReplicateDiagnostics
    iid_reference_method_id: str
    iid_metric_performance: tuple[ClinicalOutcomeDesignMetricPerformance, ...]
    gate_performance: tuple[ClinicalOutcomeDesignGatePerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(self.scenario, ClinicalOutcomeDesignScenario, "scenario")
        _require_instance(self.structure, ClinicalOutcomeDesignStructure, "structure")
        if self.structure != _design_structure(self.scenario):
            raise ValueError("scenario structure is inconsistent")
        _require_sha256(self.rng_stream_sha256, "rng_stream_sha256")
        _require_instance(
            self.replicate_diagnostics,
            ClinicalOutcomeDesignReplicateDiagnostics,
            "replicate_diagnostics",
        )
        if self.iid_reference_method_id != CLINICAL_OUTCOME_IID_REFERENCE_METHOD_ID:
            raise ValueError("iid_reference_method_id is unsupported")
        iid_metrics = _tuple(self.iid_metric_performance, "iid_metric_performance")
        object.__setattr__(self, "iid_metric_performance", iid_metrics)
        for metric in iid_metrics:
            _require_instance(
                metric,
                ClinicalOutcomeDesignMetricPerformance,
                "iid_metric_performance item",
            )
            if metric.replicate_count != self.replicate_diagnostics.replicate_count:
                raise ValueError("IID metric replicate count is inconsistent")
        if tuple(item.metric for item in iid_metrics) != _METRIC_ORDER:
            raise ValueError("IID metrics must exactly cover canonical metrics")
        expected_truths = _metric_truths(self.scenario)
        if tuple(item.true_value for item in iid_metrics) != tuple(
            expected_truths[metric] for metric in _METRIC_ORDER
        ):
            raise ValueError("scenario metric truths are inconsistent")
        diagnostics = self.replicate_diagnostics
        if (
            diagnostics.maximum_evaluable_units > self.structure.total_units
            or diagnostics.mean_evaluable_units > self.structure.total_units
            or diagnostics.maximum_evaluable_cluster_count
            > self.structure.cluster_count
            or diagnostics.mean_evaluable_cluster_count
            > self.structure.cluster_count
        ):
            raise ValueError("replicate diagnostics exceed the declared design")
        iid_no_evaluable = {
            next(
                count.count
                for count in item.status_counts
                if count.status is ClusterInferenceStatus.NO_EVALUABLE_UNITS
            )
            for item in iid_metrics
        }
        if iid_no_evaluable != {
            self.replicate_diagnostics.no_evaluable_replicates
        }:
            raise ValueError("IID no-evaluable counts are inconsistent")
        gates = _tuple(self.gate_performance, "gate_performance")
        object.__setattr__(self, "gate_performance", gates)
        if not gates:
            raise ValueError("scenario result requires gate performance")
        for gate in gates:
            _require_instance(
                gate,
                ClinicalOutcomeDesignGatePerformance,
                "gate_performance item",
            )
            if gate.replicate_count != self.replicate_diagnostics.replicate_count:
                raise ValueError("gate replicate count is inconsistent")
            gate_no_evaluable = next(
                item.count
                for item in gate.diagnostic_status_counts
                if item.status is ClusterInferenceStatus.NO_EVALUABLE_UNITS
            )
            if gate_no_evaluable != diagnostics.no_evaluable_replicates:
                raise ValueError("gate no-evaluable count is inconsistent")
            if tuple(item.true_value for item in gate.metric_performance) != tuple(
                item.true_value for item in iid_metrics
            ):
                raise ValueError("gate and IID metric truths are inconsistent")
        if tuple(item.gate.sort_key for item in gates) != tuple(
            sorted(item.gate.sort_key for item in gates)
        ):
            raise ValueError("gate performance must use canonical order")
        if len({item.gate.gate_id for item in gates}) != len(gates):
            raise ValueError("scenario gate ids must be unique")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.scenario.sort_key


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeDesignSimulationReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    simulation_method_id: str
    rng_method_id: str
    uncertainty_method_id: str
    iid_reference_method_id: str
    confidence_level: float
    monte_carlo_confidence_level: float
    replicates: int
    coverage_target: float
    minimum_interval_yield: float
    scenario_results: tuple[ClinicalOutcomeDesignScenarioResult, ...]
    aggregate_simulation_only: bool
    replicate_level_records_included: bool
    unit_level_records_included: bool
    real_clinical_outcomes_included: bool
    automatic_gate_selection_included: bool
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        _require_text(self.protocol_id, "protocol_id")
        _require_sha256(self.protocol_fingerprint, "protocol_fingerprint")
        if self.simulation_method_id != CLINICAL_OUTCOME_DESIGN_SIMULATION_METHOD_ID:
            raise ValueError("simulation_method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_DESIGN_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        if self.uncertainty_method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("uncertainty_method_id is unsupported")
        if self.iid_reference_method_id != CLINICAL_OUTCOME_IID_REFERENCE_METHOD_ID:
            raise ValueError("iid_reference_method_id is unsupported")
        for field_name in (
            "confidence_level",
            "monte_carlo_confidence_level",
            "coverage_target",
            "minimum_interval_yield",
        ):
            _require_probability(getattr(self, field_name), field_name)
        if not 0.5 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if not 0.5 < self.monte_carlo_confidence_level < 1.0:
            raise ValueError("monte_carlo_confidence_level must be between 0.5 and 1")
        if self.coverage_target > self.confidence_level:
            raise ValueError("coverage_target exceeds confidence_level")
        if self.minimum_interval_yield == 0.0:
            raise ValueError("minimum_interval_yield must be greater than zero")
        _require_positive_int(self.replicates, "replicates")
        results = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", results)
        if not results:
            raise ValueError("design report requires scenario results")
        for result in results:
            _require_instance(
                result,
                ClinicalOutcomeDesignScenarioResult,
                "scenario_results item",
            )
            if result.replicate_diagnostics.replicate_count != self.replicates:
                raise ValueError("scenario replicate count is inconsistent")
            for gate in result.gate_performance:
                if (
                    gate.coverage_target != self.coverage_target
                    or gate.minimum_interval_yield != self.minimum_interval_yield
                ):
                    raise ValueError("scenario gate targets are inconsistent")
                if gate.diagnostic_interval_eligibility.confidence_level != (
                    self.monte_carlo_confidence_level
                ):
                    raise ValueError("diagnostic Monte Carlo confidence is inconsistent")
                if any(
                    metric.coverage.confidence_level
                    != self.monte_carlo_confidence_level
                    or metric.interval_yield.confidence_level
                    != self.monte_carlo_confidence_level
                    for metric in gate.metric_performance
                ):
                    raise ValueError("gate Monte Carlo confidence is inconsistent")
            if any(
                metric.coverage.confidence_level
                != self.monte_carlo_confidence_level
                or metric.interval_yield.confidence_level
                != self.monte_carlo_confidence_level
                for metric in result.iid_metric_performance
            ):
                raise ValueError("IID Monte Carlo confidence is inconsistent")
        if tuple(item.sort_key for item in results) != tuple(
            sorted(item.sort_key for item in results)
        ):
            raise ValueError("scenario results must use canonical order")
        if len({item.scenario.scenario_id for item in results}) != len(results):
            raise ValueError("scenario result ids must be unique")
        gate_rosters = {
            _sha256(tuple(item.gate for item in result.gate_performance))
            for result in results
        }
        if len(gate_rosters) != 1:
            raise ValueError("all scenarios must evaluate the same gate roster")
        for field_name in (
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "automatic_gate_selection_included",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.aggregate_simulation_only:
            raise ValueError("design report must remain aggregate")
        if (
            self.replicate_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or self.automatic_gate_selection_included
        ):
            raise ValueError("design report crossed its simulation claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required design limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _metric_truths(
    scenario: ClinicalOutcomeDesignScenario,
) -> dict[ClinicalOutcomeDesignMetric, float]:
    prevalence = scenario.favorable_prevalence
    threshold = scenario.classification_threshold
    pattern_a = scenario.policy_a_probability_pattern
    pattern_b = scenario.policy_b_probability_pattern
    pattern_length = len(pattern_a)

    def average(values: Sequence[float]) -> float:
        return sum(values) / len(values)

    brier_a = average(
        tuple(probability**2 - 2 * prevalence * probability + prevalence for probability in pattern_a)
    )
    brier_b = average(
        tuple(probability**2 - 2 * prevalence * probability + prevalence for probability in pattern_b)
    )
    accuracy_a = average(
        tuple(
            prevalence if probability >= threshold else 1 - prevalence
            for probability in pattern_a
        )
    )
    accuracy_b = average(
        tuple(
            prevalence if probability >= threshold else 1 - prevalence
            for probability in pattern_b
        )
    )
    paired_difference = sum(
        probability_b**2
        - probability_a**2
        - 2 * prevalence * (probability_b - probability_a)
        for probability_a, probability_b in zip(pattern_a, pattern_b, strict=True)
    ) / pattern_length
    return {
        ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE: _round_metric(
            prevalence
        ),
        ClinicalOutcomeDesignMetric.POLICY_A_BRIER_SCORE: _round_metric(brier_a),
        ClinicalOutcomeDesignMetric.POLICY_B_BRIER_SCORE: _round_metric(brier_b),
        ClinicalOutcomeDesignMetric.POLICY_A_CALIBRATION_IN_THE_LARGE: (
            _round_metric(average(pattern_a) - prevalence)
        ),
        ClinicalOutcomeDesignMetric.POLICY_B_CALIBRATION_IN_THE_LARGE: (
            _round_metric(average(pattern_b) - prevalence)
        ),
        ClinicalOutcomeDesignMetric.POLICY_A_CLASSIFICATION_ACCURACY: (
            _round_metric(accuracy_a)
        ),
        ClinicalOutcomeDesignMetric.POLICY_B_CLASSIFICATION_ACCURACY: (
            _round_metric(accuracy_b)
        ),
        ClinicalOutcomeDesignMetric.BRIER_DIFFERENCE_B_MINUS_A: _round_metric(
            paired_difference
        ),
    }


class _MetricAccumulator:
    def __init__(self) -> None:
        self.status_counts: Counter[ClusterInferenceStatus] = Counter()
        self.point_count = 0
        self.point_mean = 0.0
        self.point_m2 = 0.0
        self.squared_error_sum = 0.0
        self.interval_count = 0
        self.covered_count = 0
        self.standard_error_sum = 0.0
        self.interval_width_sum = 0.0

    def add(
        self,
        estimate: ClinicalClusterRobustEstimate,
        true_value: float,
    ) -> None:
        self.status_counts[estimate.status] += 1
        if estimate.estimate is not None:
            self.point_count += 1
            delta = estimate.estimate - self.point_mean
            self.point_mean += delta / self.point_count
            self.point_m2 += delta * (estimate.estimate - self.point_mean)
            self.squared_error_sum += (estimate.estimate - true_value) ** 2
        if estimate.status is ClusterInferenceStatus.COMPUTED:
            assert estimate.standard_error is not None
            assert estimate.lower is not None
            assert estimate.upper is not None
            self.interval_count += 1
            self.covered_count += int(
                estimate.lower <= true_value <= estimate.upper
            )
            self.standard_error_sum += estimate.standard_error
            self.interval_width_sum += estimate.upper - estimate.lower

    def finalize(
        self,
        metric: ClinicalOutcomeDesignMetric,
        true_value: float,
        replicate_count: int,
        monte_carlo_confidence_level: float,
    ) -> ClinicalOutcomeDesignMetricPerformance:
        if self.point_count == 0:
            mean_estimate = bias = rmse = empirical_sd = None
        else:
            mean_estimate = _round_metric(self.point_mean)
            bias = _round_metric(mean_estimate - true_value)
            rmse = _round_metric(
                math.sqrt(self.squared_error_sum / self.point_count)
            )
            empirical_sd = (
                None
                if self.point_count == 1
                else _round_metric(
                    math.sqrt(max(0.0, self.point_m2) / (self.point_count - 1))
                )
            )
        if self.interval_count == 0:
            mean_standard_error = mean_width = se_ratio = None
        else:
            mean_standard_error = _round_metric(
                self.standard_error_sum / self.interval_count
            )
            mean_width = _round_metric(self.interval_width_sum / self.interval_count)
            se_ratio = (
                None
                if empirical_sd in (None, 0.0)
                else _round_metric(mean_standard_error / empirical_sd)
            )
        return ClinicalOutcomeDesignMetricPerformance(
            metric=metric,
            true_value=true_value,
            replicate_count=replicate_count,
            point_estimate_count=self.point_count,
            interval_count=self.interval_count,
            covered_interval_count=self.covered_count,
            interval_yield=_design_rate(
                self.interval_count,
                replicate_count,
                monte_carlo_confidence_level,
            ),
            coverage=_design_rate(
                self.covered_count,
                self.interval_count,
                monte_carlo_confidence_level,
            ),
            mean_estimate=mean_estimate,
            bias=bias,
            root_mean_squared_error=rmse,
            empirical_standard_deviation=empirical_sd,
            mean_reported_standard_error=mean_standard_error,
            mean_interval_width=mean_width,
            mean_se_to_empirical_sd_ratio=se_ratio,
            status_counts=_status_count_records(self.status_counts),
        )


class _ReplicateDiagnosticAccumulator:
    def __init__(self) -> None:
        self.replicates = 0
        self.no_evaluable = 0
        self.evaluable_unit_sum = 0
        self.evaluable_unit_min: int | None = None
        self.evaluable_unit_max = 0
        self.evaluable_cluster_sum = 0
        self.evaluable_cluster_min: int | None = None
        self.evaluable_cluster_max = 0
        self.largest_fraction_sum = 0.0
        self.largest_fraction_count = 0
        self.largest_fraction_max: float | None = None

    def add(self, evaluable_units: int, evaluable_clusters: int, largest: float | None) -> None:
        self.replicates += 1
        self.no_evaluable += int(evaluable_units == 0)
        self.evaluable_unit_sum += evaluable_units
        self.evaluable_unit_min = (
            evaluable_units
            if self.evaluable_unit_min is None
            else min(self.evaluable_unit_min, evaluable_units)
        )
        self.evaluable_unit_max = max(self.evaluable_unit_max, evaluable_units)
        self.evaluable_cluster_sum += evaluable_clusters
        self.evaluable_cluster_min = (
            evaluable_clusters
            if self.evaluable_cluster_min is None
            else min(self.evaluable_cluster_min, evaluable_clusters)
        )
        self.evaluable_cluster_max = max(
            self.evaluable_cluster_max,
            evaluable_clusters,
        )
        if largest is not None:
            self.largest_fraction_sum += largest
            self.largest_fraction_count += 1
            self.largest_fraction_max = (
                largest
                if self.largest_fraction_max is None
                else max(self.largest_fraction_max, largest)
            )

    def finalize(self) -> ClinicalOutcomeDesignReplicateDiagnostics:
        assert self.replicates > 0
        assert self.evaluable_unit_min is not None
        assert self.evaluable_cluster_min is not None
        mean_largest = (
            None
            if self.largest_fraction_count == 0
            else _round_metric(
                self.largest_fraction_sum / self.largest_fraction_count
            )
        )
        return ClinicalOutcomeDesignReplicateDiagnostics(
            replicate_count=self.replicates,
            no_evaluable_replicates=self.no_evaluable,
            mean_evaluable_units=_round_metric(
                self.evaluable_unit_sum / self.replicates
            ),
            minimum_evaluable_units=self.evaluable_unit_min,
            maximum_evaluable_units=self.evaluable_unit_max,
            mean_evaluable_cluster_count=_round_metric(
                self.evaluable_cluster_sum / self.replicates
            ),
            minimum_evaluable_cluster_count=self.evaluable_cluster_min,
            maximum_evaluable_cluster_count=self.evaluable_cluster_max,
            mean_largest_evaluable_cluster_fraction=mean_largest,
            maximum_largest_evaluable_cluster_fraction=(
                None
                if self.largest_fraction_max is None
                else _round_metric(self.largest_fraction_max)
            ),
        )


def _metric_values(
    label: float,
    probability_a: float,
    probability_b: float,
    classification_threshold: float,
) -> dict[ClinicalOutcomeDesignMetric, float]:
    brier_a = (probability_a - label) ** 2
    brier_b = (probability_b - label) ** 2
    return {
        ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE: label,
        ClinicalOutcomeDesignMetric.POLICY_A_BRIER_SCORE: brier_a,
        ClinicalOutcomeDesignMetric.POLICY_B_BRIER_SCORE: brier_b,
        ClinicalOutcomeDesignMetric.POLICY_A_CALIBRATION_IN_THE_LARGE: (
            probability_a - label
        ),
        ClinicalOutcomeDesignMetric.POLICY_B_CALIBRATION_IN_THE_LARGE: (
            probability_b - label
        ),
        ClinicalOutcomeDesignMetric.POLICY_A_CLASSIFICATION_ACCURACY: float(
            (probability_a >= classification_threshold) == bool(label)
        ),
        ClinicalOutcomeDesignMetric.POLICY_B_CLASSIFICATION_ACCURACY: float(
            (probability_b >= classification_threshold) == bool(label)
        ),
        ClinicalOutcomeDesignMetric.BRIER_DIFFERENCE_B_MINUS_A: brier_b - brier_a,
    }


def _scenario_stream_sha256(
    protocol: ClinicalOutcomeDesignSimulationProtocol,
    scenario: ClinicalOutcomeDesignScenario,
) -> str:
    return _sha256(
        {
            "random_seed": protocol.random_seed,
            "rng_method_id": protocol.rng_method_id,
            "scenario": scenario,
        }
    )


def _draw_beta_binomial_label(
    rng: random.Random,
    prevalence: float,
    correlation: float,
    successes: int,
    previous_count: int,
) -> float:
    predictive_probability = (
        prevalence * (1 - correlation) + correlation * successes
    ) / (1 - correlation + correlation * previous_count)
    return float(rng.random() < predictive_probability)


def _simulate_scenario(
    protocol: ClinicalOutcomeDesignSimulationProtocol,
    scenario: ClinicalOutcomeDesignScenario,
) -> ClinicalOutcomeDesignScenarioResult:
    stream_sha256 = _scenario_stream_sha256(protocol, scenario)
    rng = random.Random(int(stream_sha256, 16))
    truths = _metric_truths(scenario)
    structure = _design_structure(scenario)
    unit_ids: list[str] = []
    cluster_by_unit: dict[str, str] = {}
    prediction_by_unit: dict[str, tuple[float, float]] = {}
    for cluster_index, cluster_size in enumerate(scenario.cluster_sizes):
        cluster_id = f"cluster-{cluster_index:06d}"
        for unit_index in range(cluster_size):
            unit_id = f"{cluster_id}:unit-{unit_index:06d}"
            unit_ids.append(unit_id)
            cluster_by_unit[unit_id] = cluster_id
            pattern_index = unit_index % len(
                scenario.policy_a_probability_pattern
            )
            prediction_by_unit[unit_id] = (
                scenario.policy_a_probability_pattern[pattern_index],
                scenario.policy_b_probability_pattern[pattern_index],
            )
    resolved_unit_ids = tuple(unit_ids)
    iid_cluster_by_unit = {unit_id: unit_id for unit_id in resolved_unit_ids}
    iid_accumulators = {metric: _MetricAccumulator() for metric in _METRIC_ORDER}
    gate_metric_accumulators = {
        gate.gate_id: {metric: _MetricAccumulator() for metric in _METRIC_ORDER}
        for gate in protocol.gates
    }
    gate_diagnostic_counts = {
        gate.gate_id: Counter() for gate in protocol.gates
    }
    replicate_diagnostics = _ReplicateDiagnosticAccumulator()

    prevalence = scenario.favorable_prevalence
    correlation = scenario.intracluster_correlation
    for _ in range(protocol.replicates):
        evaluable_unit_ids: set[str] = set()
        values: dict[
            ClinicalOutcomeDesignMetric,
            list[tuple[str, str, float]],
        ] = {metric: [] for metric in _METRIC_ORDER}
        unit_offset = 0
        for cluster_index, cluster_size in enumerate(scenario.cluster_sizes):
            successes = 0
            cluster_id = f"cluster-{cluster_index:06d}"
            for within_cluster_index in range(cluster_size):
                label = _draw_beta_binomial_label(
                    rng,
                    prevalence,
                    correlation,
                    successes,
                    within_cluster_index,
                )
                successes += int(label)
                unit_id = resolved_unit_ids[unit_offset]
                unit_offset += 1
                evaluable = (
                    True
                    if scenario.evaluable_probability == 1.0
                    else rng.random() < scenario.evaluable_probability
                )
                if not evaluable:
                    continue
                evaluable_unit_ids.add(unit_id)
                probability_a, probability_b = prediction_by_unit[unit_id]
                for metric, value in _metric_values(
                    label,
                    probability_a,
                    probability_b,
                    scenario.classification_threshold,
                ).items():
                    values[metric].append((unit_id, cluster_id, value))

        base_diagnostic = _cluster_diagnostic(
            resolved_unit_ids,
            evaluable_unit_ids,
            cluster_by_unit,
            minimum_clusters=2,
            maximum_fraction=_IID_MAXIMUM_CLUSTER_FRACTION,
        )
        replicate_diagnostics.add(
            base_diagnostic.evaluable_units,
            base_diagnostic.evaluable_cluster_count,
            base_diagnostic.largest_evaluable_cluster_fraction,
        )
        iid_diagnostic = _cluster_diagnostic(
            resolved_unit_ids,
            evaluable_unit_ids,
            iid_cluster_by_unit,
            minimum_clusters=2,
            maximum_fraction=_IID_MAXIMUM_CLUSTER_FRACTION,
        )
        for metric in _METRIC_ORDER:
            lower_bound, upper_bound = _metric_bounds(metric)
            estimate = _cluster_robust_estimate(
                tuple((unit_id, value) for unit_id, _, value in values[metric]),
                iid_diagnostic,
                confidence_level=protocol.confidence_level,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
            iid_accumulators[metric].add(estimate, truths[metric])

        for gate in protocol.gates:
            diagnostic = _cluster_diagnostic(
                resolved_unit_ids,
                evaluable_unit_ids,
                cluster_by_unit,
                minimum_clusters=gate.minimum_evaluable_clusters,
                maximum_fraction=gate.maximum_evaluable_cluster_fraction,
            )
            gate_diagnostic_counts[gate.gate_id][diagnostic.status] += 1
            for metric in _METRIC_ORDER:
                lower_bound, upper_bound = _metric_bounds(metric)
                estimate = _cluster_robust_estimate(
                    tuple(
                        (cluster_id, value)
                        for _, cluster_id, value in values[metric]
                    ),
                    diagnostic,
                    confidence_level=protocol.confidence_level,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                gate_metric_accumulators[gate.gate_id][metric].add(
                    estimate,
                    truths[metric],
                )

    iid_performance = tuple(
        iid_accumulators[metric].finalize(
            metric,
            truths[metric],
            protocol.replicates,
            protocol.monte_carlo_confidence_level,
        )
        for metric in _METRIC_ORDER
    )
    gate_performance = []
    for gate in protocol.gates:
        metrics = tuple(
            gate_metric_accumulators[gate.gate_id][metric].finalize(
                metric,
                truths[metric],
                protocol.replicates,
                protocol.monte_carlo_confidence_level,
            )
            for metric in _METRIC_ORDER
        )
        coverage_met = all(
            item.coverage.lower is not None
            and item.coverage.lower >= protocol.coverage_target
            for item in metrics
        )
        yield_met = all(
            item.interval_yield.lower is not None
            and item.interval_yield.lower >= protocol.minimum_interval_yield
            for item in metrics
        )
        diagnostic_counts = gate_diagnostic_counts[gate.gate_id]
        gate_performance.append(
            ClinicalOutcomeDesignGatePerformance(
                gate=gate,
                replicate_count=protocol.replicates,
                diagnostic_status_counts=_status_count_records(diagnostic_counts),
                diagnostic_interval_eligibility=_design_rate(
                    diagnostic_counts[ClusterInferenceStatus.COMPUTED],
                    protocol.replicates,
                    protocol.monte_carlo_confidence_level,
                ),
                coverage_target=protocol.coverage_target,
                minimum_interval_yield=protocol.minimum_interval_yield,
                all_metric_coverage_targets_met=coverage_met,
                all_metric_yield_targets_met=yield_met,
                design_target_met=coverage_met and yield_met,
                metric_performance=metrics,
            )
        )
    return ClinicalOutcomeDesignScenarioResult(
        scenario=scenario,
        structure=structure,
        rng_stream_sha256=stream_sha256,
        replicate_diagnostics=replicate_diagnostics.finalize(),
        iid_reference_method_id=CLINICAL_OUTCOME_IID_REFERENCE_METHOD_ID,
        iid_metric_performance=iid_performance,
        gate_performance=tuple(gate_performance),
    )


def simulate_clinical_outcome_uncertainty_design(
    protocol: ClinicalOutcomeDesignSimulationProtocol,
) -> ClinicalOutcomeDesignSimulationReport:
    """Run a deterministic aggregate simulation over preregistered design scenarios."""

    _require_instance(
        protocol,
        ClinicalOutcomeDesignSimulationProtocol,
        "protocol",
    )
    return ClinicalOutcomeDesignSimulationReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        simulation_method_id=protocol.simulation_method_id,
        rng_method_id=protocol.rng_method_id,
        uncertainty_method_id=protocol.uncertainty_method_id,
        iid_reference_method_id=CLINICAL_OUTCOME_IID_REFERENCE_METHOD_ID,
        confidence_level=protocol.confidence_level,
        monte_carlo_confidence_level=protocol.monte_carlo_confidence_level,
        replicates=protocol.replicates,
        coverage_target=protocol.coverage_target,
        minimum_interval_yield=protocol.minimum_interval_yield,
        scenario_results=tuple(
            _simulate_scenario(protocol, scenario) for scenario in protocol.scenarios
        ),
        aggregate_simulation_only=True,
        replicate_level_records_included=False,
        unit_level_records_included=False,
        real_clinical_outcomes_included=False,
        automatic_gate_selection_included=False,
    )


def validate_clinical_outcome_design_simulation_report(
    report: ClinicalOutcomeDesignSimulationReport,
    protocol: ClinicalOutcomeDesignSimulationProtocol,
) -> tuple[str, ...]:
    """Replay a design simulation exactly and compare the aggregate report."""

    try:
        rebuilt = simulate_clinical_outcome_uncertainty_design(protocol)
    except (ClinicalOutcomeDesignSimulationError, TypeError, ValueError):
        return ("clinical_outcome_design_simulation_recompile_failed",)
    if rebuilt != report:
        return ("recompiled_clinical_outcome_design_simulation_report_mismatch",)
    return ()


def _rate_projection(value: ClinicalOutcomeDesignRate) -> dict[str, Any]:
    return {
        "events": value.event_count,
        "total": value.total_count,
        "rate": value.rate,
        "lower": value.lower,
        "upper": value.upper,
    }


def _metric_projection(
    value: ClinicalOutcomeDesignMetricPerformance,
) -> dict[str, Any]:
    return {
        "metric": value.metric.value,
        "true_value": value.true_value,
        "coverage": _rate_projection(value.coverage),
        "interval_yield": _rate_projection(value.interval_yield),
        "mean_estimate": value.mean_estimate,
        "bias": value.bias,
        "root_mean_squared_error": value.root_mean_squared_error,
        "empirical_standard_deviation": value.empirical_standard_deviation,
        "mean_reported_standard_error": value.mean_reported_standard_error,
        "mean_interval_width": value.mean_interval_width,
        "mean_se_to_empirical_sd_ratio": value.mean_se_to_empirical_sd_ratio,
        "status_counts": {
            item.status.value: item.count for item in value.status_counts
        },
    }


def clinical_outcome_design_simulation_summary(
    report: ClinicalOutcomeDesignSimulationReport,
) -> dict[str, Any]:
    """Return a compact human- and machine-readable design projection."""

    _require_instance(report, ClinicalOutcomeDesignSimulationReport, "report")
    scenario_summaries = []
    target_met_pair_count = 0
    for result in report.scenario_results:
        target_met_pair_count += sum(
            item.design_target_met for item in result.gate_performance
        )
        scenario_summaries.append(
            {
                "scenario_id": result.scenario.scenario_id,
                "stage": result.scenario.stage.value,
                "endpoint_family": result.scenario.endpoint_family,
                "data_generating_parameters": {
                    "favorable_prevalence": (
                        result.scenario.favorable_prevalence
                    ),
                    "intracluster_correlation": (
                        result.scenario.intracluster_correlation
                    ),
                    "evaluable_probability": (
                        result.scenario.evaluable_probability
                    ),
                    "classification_threshold": (
                        result.scenario.classification_threshold
                    ),
                    "policy_a_probability_pattern": list(
                        result.scenario.policy_a_probability_pattern
                    ),
                    "policy_b_probability_pattern": list(
                        result.scenario.policy_b_probability_pattern
                    ),
                },
                "cluster_design": result.structure.to_dict(),
                "replicate_diagnostics": result.replicate_diagnostics.to_dict(),
                "iid_reference": {
                    "method_id": result.iid_reference_method_id,
                    "metrics": [
                        _metric_projection(item)
                        for item in result.iid_metric_performance
                    ],
                },
                "candidate_gates": [
                    {
                        "gate_id": item.gate.gate_id,
                        "minimum_evaluable_clusters": (
                            item.gate.minimum_evaluable_clusters
                        ),
                        "maximum_evaluable_cluster_fraction": (
                            item.gate.maximum_evaluable_cluster_fraction
                        ),
                        "diagnostic_interval_eligibility": _rate_projection(
                            item.diagnostic_interval_eligibility
                        ),
                        "diagnostic_status_counts": {
                            count.status.value: count.count
                            for count in item.diagnostic_status_counts
                        },
                        "coverage_target": item.coverage_target,
                        "minimum_interval_yield": item.minimum_interval_yield,
                        "all_metric_coverage_targets_met": (
                            item.all_metric_coverage_targets_met
                        ),
                        "all_metric_yield_targets_met": (
                            item.all_metric_yield_targets_met
                        ),
                        "design_target_met": item.design_target_met,
                        "metrics": [
                            _metric_projection(metric)
                            for metric in item.metric_performance
                        ],
                    }
                    for item in result.gate_performance
                ],
                "target_met_gate_ids": [
                    item.gate.gate_id
                    for item in result.gate_performance
                    if item.design_target_met
                ],
            }
        )
    return {
        "schema_version": CLINICAL_OUTCOME_DESIGN_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "protocol_id": report.protocol_id,
        "protocol_fingerprint": report.protocol_fingerprint,
        "simulation_method_id": report.simulation_method_id,
        "rng_method_id": report.rng_method_id,
        "uncertainty_method_id": report.uncertainty_method_id,
        "iid_reference_method_id": report.iid_reference_method_id,
        "confidence_level": report.confidence_level,
        "monte_carlo_confidence_level": report.monte_carlo_confidence_level,
        "replicates": report.replicates,
        "coverage_target": report.coverage_target,
        "minimum_interval_yield": report.minimum_interval_yield,
        "scenario_count": len(report.scenario_results),
        "scenario_gate_pair_count": sum(
            len(item.gate_performance) for item in report.scenario_results
        ),
        "target_met_scenario_gate_pair_count": target_met_pair_count,
        "scenarios": scenario_summaries,
        "aggregate_simulation_only": report.aggregate_simulation_only,
        "replicate_level_records_included": (
            report.replicate_level_records_included
        ),
        "unit_level_records_included": report.unit_level_records_included,
        "real_clinical_outcomes_included": (
            report.real_clinical_outcomes_included
        ),
        "automatic_gate_selection_included": (
            report.automatic_gate_selection_included
        ),
    }


def clinical_outcome_design_simulation_validation_summary(
    report: ClinicalOutcomeDesignSimulationReport,
    *,
    failures: Sequence[str] = (),
    scope: str = "integrity_and_aggregate_consistency",
) -> dict[str, Any]:
    resolved_failures = _tuple(failures, "failures")
    for failure in resolved_failures:
        _require_text(failure, "failure code")
    if len(resolved_failures) != len(set(resolved_failures)):
        raise ValueError("failure codes must be unique")
    _require_text(scope, "scope")
    return {
        **clinical_outcome_design_simulation_summary(report),
        "validation": {
            "status": "valid" if not resolved_failures else "invalid",
            "scope": scope,
            "failure_codes": list(resolved_failures),
        },
    }


def clinical_outcome_design_protocol_envelope(
    protocol: ClinicalOutcomeDesignSimulationProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomeDesignSimulationProtocol,
        "protocol",
    )
    return {
        "schema_version": CLINICAL_OUTCOME_DESIGN_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_design_report_envelope(
    report: ClinicalOutcomeDesignSimulationReport,
) -> dict[str, Any]:
    _require_instance(report, ClinicalOutcomeDesignSimulationReport, "report")
    return {
        "schema_version": CLINICAL_OUTCOME_DESIGN_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    fingerprint = getattr(value, "fingerprint", None)
    if fingerprint != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def _parse_design_gate(value: Any, path: str) -> ClinicalOutcomeDesignGate:
    data = _record(
        value,
        path,
        {
            "gate_id",
            "minimum_evaluable_clusters",
            "maximum_evaluable_cluster_fraction",
        },
    )
    return ClinicalOutcomeDesignGate(
        gate_id=data["gate_id"],
        minimum_evaluable_clusters=data["minimum_evaluable_clusters"],
        maximum_evaluable_cluster_fraction=data[
            "maximum_evaluable_cluster_fraction"
        ],
    )


def _parse_design_scenario(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignScenario:
    data = _record(
        value,
        path,
        {
            "scenario_id",
            "stage",
            "endpoint_family",
            "cluster_sizes",
            "favorable_prevalence",
            "intracluster_correlation",
            "evaluable_probability",
            "classification_threshold",
            "policy_a_probability_pattern",
            "policy_b_probability_pattern",
        },
    )
    return ClinicalOutcomeDesignScenario(
        scenario_id=data["scenario_id"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        endpoint_family=data["endpoint_family"],
        cluster_sizes=tuple(
            _sequence(data["cluster_sizes"], f"{path}.cluster_sizes")
        ),
        favorable_prevalence=data["favorable_prevalence"],
        intracluster_correlation=data["intracluster_correlation"],
        evaluable_probability=data["evaluable_probability"],
        classification_threshold=data["classification_threshold"],
        policy_a_probability_pattern=tuple(
            _sequence(
                data["policy_a_probability_pattern"],
                f"{path}.policy_a_probability_pattern",
            )
        ),
        policy_b_probability_pattern=tuple(
            _sequence(
                data["policy_b_probability_pattern"],
                f"{path}.policy_b_probability_pattern",
            )
        ),
    )


def clinical_outcome_design_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeDesignSimulationProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_design_protocol_envelope",
        schema_version=CLINICAL_OUTCOME_DESIGN_PROTOCOL_SCHEMA_VERSION,
        payload_field="protocol",
    )
    data = _record(
        payload,
        "protocol",
        {
            "protocol_id",
            "version",
            "registered_on",
            "confidence_level",
            "monte_carlo_confidence_level",
            "replicates",
            "random_seed",
            "coverage_tolerance",
            "minimum_interval_yield",
            "gates",
            "scenarios",
            "simulation_method_id",
            "rng_method_id",
            "uncertainty_method_id",
            "metadata",
        },
    )
    protocol = ClinicalOutcomeDesignSimulationProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        replicates=data["replicates"],
        random_seed=data["random_seed"],
        coverage_tolerance=data["coverage_tolerance"],
        minimum_interval_yield=data["minimum_interval_yield"],
        gates=tuple(
            _parse_design_gate(item, f"protocol.gates[{index}]")
            for index, item in enumerate(
                _sequence(data["gates"], "protocol.gates")
            )
        ),
        scenarios=tuple(
            _parse_design_scenario(item, f"protocol.scenarios[{index}]")
            for index, item in enumerate(
                _sequence(data["scenarios"], "protocol.scenarios")
            )
        ),
        simulation_method_id=data["simulation_method_id"],
        rng_method_id=data["rng_method_id"],
        uncertainty_method_id=data["uncertainty_method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "design simulation protocol")
    return protocol


def _parse_design_structure(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignStructure:
    data = _record(
        value,
        path,
        {
            "cluster_count",
            "total_units",
            "minimum_cluster_size",
            "maximum_cluster_size",
            "mean_cluster_size",
            "cluster_size_coefficient_of_variation",
            "maximum_cluster_fraction",
            "effective_cluster_count",
        },
    )
    return ClinicalOutcomeDesignStructure(**data)


def _parse_design_rate(value: Any, path: str) -> ClinicalOutcomeDesignRate:
    data = _record(
        value,
        path,
        {
            "event_count",
            "total_count",
            "rate",
            "lower",
            "upper",
            "confidence_level",
        },
    )
    return ClinicalOutcomeDesignRate(**data)


def _parse_design_status_count(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignStatusCount:
    data = _record(value, path, {"status", "count"})
    return ClinicalOutcomeDesignStatusCount(
        status=_parse_enum(
            ClusterInferenceStatus,
            data["status"],
            f"{path}.status",
        ),
        count=data["count"],
    )


def _parse_design_metric_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignMetricPerformance:
    data = _record(
        value,
        path,
        {
            "metric",
            "true_value",
            "replicate_count",
            "point_estimate_count",
            "interval_count",
            "covered_interval_count",
            "interval_yield",
            "coverage",
            "mean_estimate",
            "bias",
            "root_mean_squared_error",
            "empirical_standard_deviation",
            "mean_reported_standard_error",
            "mean_interval_width",
            "mean_se_to_empirical_sd_ratio",
            "status_counts",
        },
    )
    return ClinicalOutcomeDesignMetricPerformance(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        true_value=data["true_value"],
        replicate_count=data["replicate_count"],
        point_estimate_count=data["point_estimate_count"],
        interval_count=data["interval_count"],
        covered_interval_count=data["covered_interval_count"],
        interval_yield=_parse_design_rate(
            data["interval_yield"],
            f"{path}.interval_yield",
        ),
        coverage=_parse_design_rate(data["coverage"], f"{path}.coverage"),
        mean_estimate=data["mean_estimate"],
        bias=data["bias"],
        root_mean_squared_error=data["root_mean_squared_error"],
        empirical_standard_deviation=data["empirical_standard_deviation"],
        mean_reported_standard_error=data["mean_reported_standard_error"],
        mean_interval_width=data["mean_interval_width"],
        mean_se_to_empirical_sd_ratio=data[
            "mean_se_to_empirical_sd_ratio"
        ],
        status_counts=tuple(
            _parse_design_status_count(item, f"{path}.status_counts[{index}]")
            for index, item in enumerate(
                _sequence(data["status_counts"], f"{path}.status_counts")
            )
        ),
    )


def _parse_replicate_diagnostics(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignReplicateDiagnostics:
    data = _record(
        value,
        path,
        {
            "replicate_count",
            "no_evaluable_replicates",
            "mean_evaluable_units",
            "minimum_evaluable_units",
            "maximum_evaluable_units",
            "mean_evaluable_cluster_count",
            "minimum_evaluable_cluster_count",
            "maximum_evaluable_cluster_count",
            "mean_largest_evaluable_cluster_fraction",
            "maximum_largest_evaluable_cluster_fraction",
        },
    )
    return ClinicalOutcomeDesignReplicateDiagnostics(**data)


def _parse_gate_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignGatePerformance:
    data = _record(
        value,
        path,
        {
            "gate",
            "replicate_count",
            "diagnostic_status_counts",
            "diagnostic_interval_eligibility",
            "coverage_target",
            "minimum_interval_yield",
            "all_metric_coverage_targets_met",
            "all_metric_yield_targets_met",
            "design_target_met",
            "metric_performance",
        },
    )
    return ClinicalOutcomeDesignGatePerformance(
        gate=_parse_design_gate(data["gate"], f"{path}.gate"),
        replicate_count=data["replicate_count"],
        diagnostic_status_counts=tuple(
            _parse_design_status_count(
                item,
                f"{path}.diagnostic_status_counts[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["diagnostic_status_counts"],
                    f"{path}.diagnostic_status_counts",
                )
            )
        ),
        diagnostic_interval_eligibility=_parse_design_rate(
            data["diagnostic_interval_eligibility"],
            f"{path}.diagnostic_interval_eligibility",
        ),
        coverage_target=data["coverage_target"],
        minimum_interval_yield=data["minimum_interval_yield"],
        all_metric_coverage_targets_met=data[
            "all_metric_coverage_targets_met"
        ],
        all_metric_yield_targets_met=data["all_metric_yield_targets_met"],
        design_target_met=data["design_target_met"],
        metric_performance=tuple(
            _parse_design_metric_performance(
                item,
                f"{path}.metric_performance[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["metric_performance"],
                    f"{path}.metric_performance",
                )
            )
        ),
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeDesignScenarioResult:
    data = _record(
        value,
        path,
        {
            "scenario",
            "structure",
            "rng_stream_sha256",
            "replicate_diagnostics",
            "iid_reference_method_id",
            "iid_metric_performance",
            "gate_performance",
        },
    )
    return ClinicalOutcomeDesignScenarioResult(
        scenario=_parse_design_scenario(data["scenario"], f"{path}.scenario"),
        structure=_parse_design_structure(data["structure"], f"{path}.structure"),
        rng_stream_sha256=data["rng_stream_sha256"],
        replicate_diagnostics=_parse_replicate_diagnostics(
            data["replicate_diagnostics"],
            f"{path}.replicate_diagnostics",
        ),
        iid_reference_method_id=data["iid_reference_method_id"],
        iid_metric_performance=tuple(
            _parse_design_metric_performance(
                item,
                f"{path}.iid_metric_performance[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["iid_metric_performance"],
                    f"{path}.iid_metric_performance",
                )
            )
        ),
        gate_performance=tuple(
            _parse_gate_performance(
                item,
                f"{path}.gate_performance[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["gate_performance"],
                    f"{path}.gate_performance",
                )
            )
        ),
    )


def clinical_outcome_design_report_from_dict(
    value: Any,
) -> ClinicalOutcomeDesignSimulationReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_design_report_envelope",
        schema_version=CLINICAL_OUTCOME_DESIGN_REPORT_SCHEMA_VERSION,
        payload_field="report",
    )
    data = _record(
        payload,
        "report",
        {
            "protocol_id",
            "protocol_fingerprint",
            "simulation_method_id",
            "rng_method_id",
            "uncertainty_method_id",
            "iid_reference_method_id",
            "confidence_level",
            "monte_carlo_confidence_level",
            "replicates",
            "coverage_target",
            "minimum_interval_yield",
            "scenario_results",
            "aggregate_simulation_only",
            "replicate_level_records_included",
            "unit_level_records_included",
            "real_clinical_outcomes_included",
            "automatic_gate_selection_included",
            "limitations",
        },
    )
    report = ClinicalOutcomeDesignSimulationReport(
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        simulation_method_id=data["simulation_method_id"],
        rng_method_id=data["rng_method_id"],
        uncertainty_method_id=data["uncertainty_method_id"],
        iid_reference_method_id=data["iid_reference_method_id"],
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        replicates=data["replicates"],
        coverage_target=data["coverage_target"],
        minimum_interval_yield=data["minimum_interval_yield"],
        scenario_results=tuple(
            _parse_scenario_result(item, f"report.scenario_results[{index}]")
            for index, item in enumerate(
                _sequence(data["scenario_results"], "report.scenario_results")
            )
        ),
        aggregate_simulation_only=data["aggregate_simulation_only"],
        replicate_level_records_included=data["replicate_level_records_included"],
        unit_level_records_included=data["unit_level_records_included"],
        real_clinical_outcomes_included=data["real_clinical_outcomes_included"],
        automatic_gate_selection_included=data[
            "automatic_gate_selection_included"
        ],
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
    )
    _check_integrity(report, integrity, "design simulation report")
    return report


def clinical_outcome_design_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeDesignSimulationProtocol:
    return clinical_outcome_design_protocol_from_dict(
        _strict_json(payload, "clinical outcome design simulation protocol")
    )


def clinical_outcome_design_report_from_json(
    payload: str,
) -> ClinicalOutcomeDesignSimulationReport:
    return clinical_outcome_design_report_from_dict(
        _strict_json(payload, "clinical outcome design simulation report")
    )
