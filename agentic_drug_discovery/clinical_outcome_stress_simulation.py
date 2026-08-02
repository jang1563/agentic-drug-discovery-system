"""Prospective stress simulation for evaluability and dependence misspecification."""

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
    MAX_DESIGN_GATES,
    MAX_DESIGN_REPLICATES,
    MAX_DESIGN_SCENARIOS,
    MAX_DESIGN_UNITS_PER_SCENARIO,
    MAX_DESIGN_WORK_UNITS,
    MIN_DESIGN_REPLICATES,
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomeDesignMetricPerformance,
    ClinicalOutcomeDesignRate,
    ClinicalOutcomeDesignReplicateDiagnostics,
    ClinicalOutcomeDesignStatusCount,
    ClinicalOutcomeDesignStructure,
    _IID_MAXIMUM_CLUSTER_FRACTION,
    _METRIC_ORDER,
    _MetricAccumulator,
    _ReplicateDiagnosticAccumulator,
    _design_rate,
    _draw_beta_binomial_label,
    _metric_bounds,
    _metric_truths_for_prevalence,
    _metric_values,
    _parse_design_gate,
    _parse_design_metric_performance,
    _parse_design_rate,
    _parse_design_status_count,
    _parse_design_structure,
    _require_bool,
    _require_finite,
    _require_non_negative_int,
    _require_positive_int,
    _status_count_records,
    _tuple,
    _validate_status_counts,
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
from .clinical_outcome_uncertainty import (
    CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID,
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


CLINICAL_OUTCOME_STRESS_PROTOCOL_SCHEMA_VERSION = (
    "adds.clinical-outcome-stress-simulation-protocol.v1"
)
CLINICAL_OUTCOME_STRESS_REPORT_SCHEMA_VERSION = (
    "adds.clinical-outcome-stress-simulation-report.v1"
)
CLINICAL_OUTCOME_STRESS_SUMMARY_SCHEMA_VERSION = (
    "adds.clinical-outcome-stress-simulation-summary.v1"
)
CLINICAL_OUTCOME_STRESS_SIMULATION_METHOD_ID = (
    "adds.prospective-clinical-outcome-stress.informative-evaluability-dependence.v1"
)
CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID = (
    "adds.mt19937-block-polya-urn-informative-evaluability.v1"
)


class ClinicalOutcomeStressSimulationError(ValueError):
    """Raised when a prospective stress simulation cannot run safely."""


class ClinicalOutcomeStressAnalysisMode(str, Enum):
    NOMINAL_CLUSTERS = "nominal_clusters"
    DEPENDENCE_CLOSED_CLUSTERS = "dependence_closed_clusters"


class ClinicalOutcomeStressEstimandTarget(str, Enum):
    POPULATION = "population"
    EVALUABLE = "evaluable"


_ANALYSIS_MODE_ORDER = tuple(ClinicalOutcomeStressAnalysisMode)
_ESTIMAND_TARGET_ORDER = tuple(ClinicalOutcomeStressEstimandTarget)
_STATUS_ORDER = tuple(ClusterInferenceStatus)
_REQUIRED_LIMITATIONS = (
    (
        "The report is a synthetic prospective stress analysis; it contains no real "
        "clinical outcomes and does not validate a deployed policy or evidence board."
    ),
    (
        "Outcome-dependent evaluability is generated only from the simulated binary "
        "label and the two preregistered evaluability probabilities; the evaluable "
        "target is descriptive and is not a missing-data correction or causal estimand."
    ),
    (
        "The block Polya-urn generator assumes independent declared dependence blocks, "
        "exchangeable binary outcomes within each block, and one marginal prevalence "
        "and block-level intraclass correlation per scenario."
    ),
    (
        "Dependence-closed analysis uses the exact synthetic block partition; recovery "
        "under that oracle partition does not show that hidden dependence can be detected "
        "or repaired from observed clinical data."
    ),
    (
        "Nominal-cluster analysis intentionally misspecifies dependence when a block "
        "contains multiple nominal clusters; its failure is a stress signature, not an "
        "estimate of bias for an undeclared real-world dependence structure."
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
        "Passing a candidate gate for either estimand under declared scenarios is not a "
        "universal cluster minimum and does not automatically approve an uncertainty or "
        "missing-data protocol."
    ),
    (
        "Aggregate simulation results do not establish treatment efficacy, safety, "
        "clinical utility, policy superiority, transportability, or regulatory acceptability."
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressScenario(SerializableRecord):
    scenario_id: str
    stage: Stage
    endpoint_family: str
    nominal_cluster_sizes: tuple[int, ...]
    dependence_blocks: tuple[tuple[int, ...], ...]
    favorable_prevalence: float
    dependence_block_intraclass_correlation: float
    favorable_evaluable_probability: float
    unfavorable_evaluable_probability: float
    classification_threshold: float
    policy_a_probability_pattern: tuple[float, ...]
    policy_b_probability_pattern: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_instance(self.stage, Stage, "stage")
        _require_text(self.endpoint_family, "endpoint_family")
        sizes = _tuple(self.nominal_cluster_sizes, "nominal_cluster_sizes")
        object.__setattr__(self, "nominal_cluster_sizes", sizes)
        if len(sizes) < 2:
            raise ValueError("stress scenario requires at least two nominal clusters")
        for size in sizes:
            _require_positive_int(size, "nominal_cluster_sizes item")
        if sizes != tuple(sorted(sizes, reverse=True)):
            raise ValueError(
                "nominal_cluster_sizes must use canonical non-increasing order"
            )
        if sum(sizes) > MAX_DESIGN_UNITS_PER_SCENARIO:
            raise ValueError("stress scenario exceeds the unit limit")

        raw_blocks = _tuple(self.dependence_blocks, "dependence_blocks")
        blocks: list[tuple[int, ...]] = []
        for block_index, raw_block in enumerate(raw_blocks):
            block = _tuple(raw_block, f"dependence_blocks[{block_index}]")
            if not block:
                raise ValueError("dependence blocks cannot be empty")
            for nominal_index in block:
                _require_non_negative_int(
                    nominal_index,
                    "dependence_blocks item",
                )
                if nominal_index >= len(sizes):
                    raise ValueError("dependence block index exceeds nominal clusters")
            if block != tuple(sorted(block)) or len(block) != len(set(block)):
                raise ValueError(
                    "each dependence block must use unique increasing indices"
                )
            blocks.append(block)
        resolved_blocks = tuple(blocks)
        object.__setattr__(self, "dependence_blocks", resolved_blocks)
        if not resolved_blocks:
            raise ValueError("dependence_blocks cannot be empty")
        if tuple(block[0] for block in resolved_blocks) != tuple(
            sorted(block[0] for block in resolved_blocks)
        ):
            raise ValueError("dependence_blocks must use canonical order")
        flattened = tuple(index for block in resolved_blocks for index in block)
        if tuple(sorted(flattened)) != tuple(range(len(sizes))):
            raise ValueError(
                "dependence_blocks must partition every nominal cluster exactly once"
            )

        _require_probability(self.favorable_prevalence, "favorable_prevalence")
        if self.favorable_prevalence in (0.0, 1.0):
            raise ValueError(
                "favorable_prevalence must be strictly between zero and one"
            )
        _require_probability(
            self.dependence_block_intraclass_correlation,
            "dependence_block_intraclass_correlation",
        )
        if self.dependence_block_intraclass_correlation == 1.0:
            raise ValueError(
                "dependence_block_intraclass_correlation must be less than one"
            )
        for field_name in (
            "favorable_evaluable_probability",
            "unfavorable_evaluable_probability",
        ):
            _require_probability(getattr(self, field_name), field_name)
        if (
            self.favorable_evaluable_probability == 0.0
            and self.unfavorable_evaluable_probability == 0.0
        ):
            raise ValueError("at least one evaluability probability must be positive")
        if self.expected_evaluable_probability == 0.0:
            raise ValueError(
                "expected evaluability must be positive at reporting precision"
            )
        _require_probability(
            self.classification_threshold,
            "classification_threshold",
        )

        patterns: list[tuple[float, ...]] = []
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
        if any(size % pattern_length for size in sizes):
            raise ValueError(
                "each nominal cluster size must be divisible by the prediction-pattern length"
            )

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.stage.value, self.endpoint_family, self.scenario_id)

    @property
    def expected_evaluable_probability(self) -> float:
        prevalence = self.favorable_prevalence
        return _round_metric(
            prevalence * self.favorable_evaluable_probability
            + (1 - prevalence) * self.unfavorable_evaluable_probability
        )

    @property
    def evaluable_favorable_prevalence(self) -> float:
        numerator = self.favorable_prevalence * self.favorable_evaluable_probability
        denominator = self.expected_evaluable_probability
        return _round_metric(numerator / denominator)

    @property
    def outcome_dependent_evaluability(self) -> bool:
        return (
            self.favorable_evaluable_probability
            != self.unfavorable_evaluable_probability
        )

    @property
    def cross_nominal_cluster_dependence(self) -> bool:
        return any(len(block) > 1 for block in self.dependence_blocks)


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressMetricTruth(SerializableRecord):
    metric: ClinicalOutcomeDesignMetric
    population_value: float
    evaluable_value: float
    evaluable_minus_population: float

    def __post_init__(self) -> None:
        _require_instance(self.metric, ClinicalOutcomeDesignMetric, "metric")
        lower, upper = _metric_bounds(self.metric)
        for field_name in ("population_value", "evaluable_value"):
            _require_finite(
                getattr(self, field_name),
                field_name,
                minimum=lower,
                maximum=upper,
            )
        _require_finite(
            self.evaluable_minus_population,
            "evaluable_minus_population",
            minimum=-2.0,
            maximum=2.0,
        )
        if self.evaluable_minus_population != _round_metric(
            self.evaluable_value - self.population_value
        ):
            raise ValueError("metric estimand shift is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressScenarioTruth(SerializableRecord):
    population_favorable_prevalence: float
    expected_evaluable_probability: float
    evaluable_favorable_prevalence: float
    metric_truths: tuple[ClinicalOutcomeStressMetricTruth, ...]

    def __post_init__(self) -> None:
        _require_probability(
            self.population_favorable_prevalence,
            "population_favorable_prevalence",
        )
        if self.population_favorable_prevalence in (0.0, 1.0):
            raise ValueError(
                "population_favorable_prevalence must be strictly between zero and one"
            )
        _require_probability(
            self.expected_evaluable_probability,
            "expected_evaluable_probability",
        )
        if self.expected_evaluable_probability == 0.0:
            raise ValueError("expected_evaluable_probability must be positive")
        _require_probability(
            self.evaluable_favorable_prevalence,
            "evaluable_favorable_prevalence",
        )
        metric_truths = _tuple(self.metric_truths, "metric_truths")
        object.__setattr__(self, "metric_truths", metric_truths)
        for truth in metric_truths:
            _require_instance(
                truth,
                ClinicalOutcomeStressMetricTruth,
                "metric_truths item",
            )
        if tuple(item.metric for item in metric_truths) != _METRIC_ORDER:
            raise ValueError("metric_truths must exactly cover canonical metrics")


def _scenario_truth(
    scenario: ClinicalOutcomeStressScenario,
) -> ClinicalOutcomeStressScenarioTruth:
    population_truths = _metric_truths_for_prevalence(
        scenario.favorable_prevalence,
        scenario.classification_threshold,
        scenario.policy_a_probability_pattern,
        scenario.policy_b_probability_pattern,
    )
    evaluable_prevalence = scenario.evaluable_favorable_prevalence
    evaluable_truths = _metric_truths_for_prevalence(
        evaluable_prevalence,
        scenario.classification_threshold,
        scenario.policy_a_probability_pattern,
        scenario.policy_b_probability_pattern,
    )
    return ClinicalOutcomeStressScenarioTruth(
        population_favorable_prevalence=scenario.favorable_prevalence,
        expected_evaluable_probability=scenario.expected_evaluable_probability,
        evaluable_favorable_prevalence=evaluable_prevalence,
        metric_truths=tuple(
            ClinicalOutcomeStressMetricTruth(
                metric=metric,
                population_value=population_truths[metric],
                evaluable_value=evaluable_truths[metric],
                evaluable_minus_population=_round_metric(
                    evaluable_truths[metric] - population_truths[metric]
                ),
            )
            for metric in _METRIC_ORDER
        ),
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressSimulationProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    confidence_level: float
    monte_carlo_confidence_level: float
    replicates: int
    random_seed: int
    coverage_tolerance: float
    minimum_interval_yield: float
    analysis_modes: tuple[ClinicalOutcomeStressAnalysisMode, ...]
    estimand_targets: tuple[ClinicalOutcomeStressEstimandTarget, ...]
    gates: tuple[ClinicalOutcomeDesignGate, ...]
    scenarios: tuple[ClinicalOutcomeStressScenario, ...]
    simulation_method_id: str = CLINICAL_OUTCOME_STRESS_SIMULATION_METHOD_ID
    rng_method_id: str = CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID
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

        modes = _tuple(self.analysis_modes, "analysis_modes")
        object.__setattr__(self, "analysis_modes", modes)
        if modes != _ANALYSIS_MODE_ORDER:
            raise ValueError("analysis_modes must exactly cover canonical modes")
        targets = _tuple(self.estimand_targets, "estimand_targets")
        object.__setattr__(self, "estimand_targets", targets)
        if targets != _ESTIMAND_TARGET_ORDER:
            raise ValueError("estimand_targets must exactly cover canonical targets")

        gates = _tuple(self.gates, "gates")
        object.__setattr__(self, "gates", gates)
        if not gates or len(gates) > MAX_DESIGN_GATES:
            raise ValueError(
                f"gates must contain between one and {MAX_DESIGN_GATES} items"
            )
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
                ClinicalOutcomeStressScenario,
                "scenarios item",
            )
        if tuple(item.sort_key for item in scenarios) != tuple(
            sorted(item.sort_key for item in scenarios)
        ):
            raise ValueError("scenarios must use canonical order")
        if len({item.scenario_id for item in scenarios}) != len(scenarios):
            raise ValueError("scenario ids must be unique")
        work_units = self.replicates * sum(
            sum(item.nominal_cluster_sizes)
            * (1 + len(modes) * len(gates) * len(_METRIC_ORDER))
            for item in scenarios
        )
        if work_units > MAX_DESIGN_WORK_UNITS:
            raise ClinicalOutcomeStressSimulationError(
                "stress simulation exceeds the bounded work budget"
            )

        if self.simulation_method_id != CLINICAL_OUTCOME_STRESS_SIMULATION_METHOD_ID:
            raise ValueError("simulation_method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        if self.uncertainty_method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("uncertainty_method_id is unsupported")
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata) or _contains_hidden_outcome_metadata(
            metadata
        ):
            raise ValueError(
                "stress protocol metadata cannot contain evaluator outcomes"
            )
        object.__setattr__(self, "metadata", metadata)

    @property
    def coverage_target(self) -> float:
        return _round_metric(self.confidence_level - self.coverage_tolerance)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _structure_from_sizes(sizes: Sequence[int]) -> ClinicalOutcomeDesignStructure:
    resolved = tuple(sizes)
    total = sum(resolved)
    mean = total / len(resolved)
    variance = sum((size - mean) ** 2 for size in resolved) / len(resolved)
    return ClinicalOutcomeDesignStructure(
        cluster_count=len(resolved),
        total_units=total,
        minimum_cluster_size=min(resolved),
        maximum_cluster_size=max(resolved),
        mean_cluster_size=_round_metric(mean),
        cluster_size_coefficient_of_variation=_round_metric(math.sqrt(variance) / mean),
        maximum_cluster_fraction=_round_metric(max(resolved) / total),
        effective_cluster_count=_round_metric(
            total * total / sum(size * size for size in resolved)
        ),
    )


def _analysis_cluster_sizes(
    scenario: ClinicalOutcomeStressScenario,
    mode: ClinicalOutcomeStressAnalysisMode,
) -> tuple[int, ...]:
    if mode is ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS:
        return scenario.nominal_cluster_sizes
    return tuple(
        sum(scenario.nominal_cluster_sizes[index] for index in block)
        for block in scenario.dependence_blocks
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressTargetPerformance(SerializableRecord):
    target: ClinicalOutcomeStressEstimandTarget
    all_metric_coverage_targets_met: bool
    design_target_met: bool
    metric_performance: tuple[ClinicalOutcomeDesignMetricPerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.target,
            ClinicalOutcomeStressEstimandTarget,
            "target",
        )
        for field_name in (
            "all_metric_coverage_targets_met",
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
        if tuple(item.metric for item in metrics) != _METRIC_ORDER:
            raise ValueError("target metrics must exactly cover canonical metrics")


def _shared_estimate_signature(
    value: ClinicalOutcomeDesignMetricPerformance,
) -> tuple[Any, ...]:
    return (
        value.metric,
        value.replicate_count,
        value.point_estimate_count,
        value.interval_count,
        value.interval_yield,
        value.mean_estimate,
        value.empirical_standard_deviation,
        value.mean_reported_standard_error,
        value.mean_interval_width,
        value.mean_se_to_empirical_sd_ratio,
        value.status_counts,
    )


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressGatePerformance(SerializableRecord):
    gate: ClinicalOutcomeDesignGate
    replicate_count: int
    diagnostic_status_counts: tuple[ClinicalOutcomeDesignStatusCount, ...]
    diagnostic_interval_eligibility: ClinicalOutcomeDesignRate
    coverage_target: float
    minimum_interval_yield: float
    all_metric_yield_targets_met: bool
    target_performance: tuple[ClinicalOutcomeStressTargetPerformance, ...]

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
            raise ValueError("minimum_interval_yield must be positive")
        _require_bool(
            self.all_metric_yield_targets_met,
            "all_metric_yield_targets_met",
        )

        targets = _tuple(self.target_performance, "target_performance")
        object.__setattr__(self, "target_performance", targets)
        for target in targets:
            _require_instance(
                target,
                ClinicalOutcomeStressTargetPerformance,
                "target_performance item",
            )
            for metric in target.metric_performance:
                if metric.replicate_count != self.replicate_count:
                    raise ValueError("target metric replicate count is inconsistent")
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
        if tuple(item.target for item in targets) != _ESTIMAND_TARGET_ORDER:
            raise ValueError("target_performance must exactly cover canonical targets")

        population, evaluable = targets
        for population_metric, evaluable_metric in zip(
            population.metric_performance,
            evaluable.metric_performance,
            strict=True,
        ):
            if _shared_estimate_signature(
                population_metric
            ) != _shared_estimate_signature(evaluable_metric):
                raise ValueError("estimand targets must evaluate the same estimates")

        yield_met = all(
            item.interval_yield.lower is not None
            and item.interval_yield.lower >= self.minimum_interval_yield
            for item in population.metric_performance
        )
        if self.all_metric_yield_targets_met != yield_met:
            raise ValueError("interval-yield target flag is inconsistent")
        for target in targets:
            coverage_met = all(
                item.coverage.lower is not None
                and item.coverage.lower >= self.coverage_target
                for item in target.metric_performance
            )
            if target.all_metric_coverage_targets_met != coverage_met:
                raise ValueError("coverage target flag is inconsistent")
            if target.design_target_met != (coverage_met and yield_met):
                raise ValueError("design target flag is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressAnalysisPerformance(SerializableRecord):
    analysis_mode: ClinicalOutcomeStressAnalysisMode
    cluster_structure: ClinicalOutcomeDesignStructure
    replicate_diagnostics: ClinicalOutcomeDesignReplicateDiagnostics
    gate_performance: tuple[ClinicalOutcomeStressGatePerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.analysis_mode,
            ClinicalOutcomeStressAnalysisMode,
            "analysis_mode",
        )
        _require_instance(
            self.cluster_structure,
            ClinicalOutcomeDesignStructure,
            "cluster_structure",
        )
        _require_instance(
            self.replicate_diagnostics,
            ClinicalOutcomeDesignReplicateDiagnostics,
            "replicate_diagnostics",
        )
        diagnostics = self.replicate_diagnostics
        if (
            diagnostics.maximum_evaluable_units > self.cluster_structure.total_units
            or diagnostics.mean_evaluable_units > self.cluster_structure.total_units
            or diagnostics.maximum_evaluable_cluster_count
            > self.cluster_structure.cluster_count
            or diagnostics.mean_evaluable_cluster_count
            > self.cluster_structure.cluster_count
        ):
            raise ValueError("replicate diagnostics exceed the analysis structure")
        gates = _tuple(self.gate_performance, "gate_performance")
        object.__setattr__(self, "gate_performance", gates)
        if not gates:
            raise ValueError("analysis performance requires candidate gates")
        for gate in gates:
            _require_instance(
                gate,
                ClinicalOutcomeStressGatePerformance,
                "gate_performance item",
            )
            if gate.replicate_count != diagnostics.replicate_count:
                raise ValueError("gate replicate count is inconsistent")
            no_evaluable = next(
                item.count
                for item in gate.diagnostic_status_counts
                if item.status is ClusterInferenceStatus.NO_EVALUABLE_UNITS
            )
            if no_evaluable != diagnostics.no_evaluable_replicates:
                raise ValueError("gate no-evaluable count is inconsistent")
        if tuple(item.gate.sort_key for item in gates) != tuple(
            sorted(item.gate.sort_key for item in gates)
        ):
            raise ValueError("gate performance must use canonical order")
        if len({item.gate.gate_id for item in gates}) != len(gates):
            raise ValueError("analysis gate ids must be unique")


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressScenarioResult(SerializableRecord):
    scenario: ClinicalOutcomeStressScenario
    truth: ClinicalOutcomeStressScenarioTruth
    rng_stream_sha256: str
    outcome_rng_stream_sha256: str
    evaluability_rng_stream_sha256: str
    analysis_performance: tuple[ClinicalOutcomeStressAnalysisPerformance, ...]

    def __post_init__(self) -> None:
        _require_instance(self.scenario, ClinicalOutcomeStressScenario, "scenario")
        _require_instance(self.truth, ClinicalOutcomeStressScenarioTruth, "truth")
        if self.truth != _scenario_truth(self.scenario):
            raise ValueError("scenario truth is inconsistent")
        for field_name in (
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.outcome_rng_stream_sha256 != _substream_sha256(
            self.rng_stream_sha256,
            "outcomes",
        ):
            raise ValueError("outcome RNG substream is inconsistent")
        if self.evaluability_rng_stream_sha256 != _substream_sha256(
            self.rng_stream_sha256,
            "evaluability",
        ):
            raise ValueError("evaluability RNG substream is inconsistent")

        analyses = _tuple(self.analysis_performance, "analysis_performance")
        object.__setattr__(self, "analysis_performance", analyses)
        if tuple(item.analysis_mode for item in analyses) != _ANALYSIS_MODE_ORDER:
            raise ValueError("analysis_performance must exactly cover canonical modes")
        truth_by_metric = {item.metric: item for item in self.truth.metric_truths}
        gate_rosters: set[str] = set()
        for analysis in analyses:
            _require_instance(
                analysis,
                ClinicalOutcomeStressAnalysisPerformance,
                "analysis_performance item",
            )
            expected_structure = _structure_from_sizes(
                _analysis_cluster_sizes(self.scenario, analysis.analysis_mode)
            )
            if analysis.cluster_structure != expected_structure:
                raise ValueError("analysis cluster structure is inconsistent")
            gate_rosters.add(
                _sha256(tuple(item.gate for item in analysis.gate_performance))
            )
            for gate in analysis.gate_performance:
                for target in gate.target_performance:
                    expected_values = tuple(
                        (
                            truth_by_metric[metric].population_value
                            if target.target
                            is ClinicalOutcomeStressEstimandTarget.POPULATION
                            else truth_by_metric[metric].evaluable_value
                        )
                        for metric in _METRIC_ORDER
                    )
                    if (
                        tuple(item.true_value for item in target.metric_performance)
                        != expected_values
                    ):
                        raise ValueError("target metric truths are inconsistent")
        if len(gate_rosters) != 1:
            raise ValueError("analysis modes must evaluate the same gate roster")
        nominal_diagnostics = analyses[0].replicate_diagnostics
        closed_diagnostics = analyses[1].replicate_diagnostics
        if (
            nominal_diagnostics.replicate_count,
            nominal_diagnostics.no_evaluable_replicates,
            nominal_diagnostics.mean_evaluable_units,
            nominal_diagnostics.minimum_evaluable_units,
            nominal_diagnostics.maximum_evaluable_units,
        ) != (
            closed_diagnostics.replicate_count,
            closed_diagnostics.no_evaluable_replicates,
            closed_diagnostics.mean_evaluable_units,
            closed_diagnostics.minimum_evaluable_units,
            closed_diagnostics.maximum_evaluable_units,
        ):
            raise ValueError("analysis modes must share evaluable-unit realizations")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.scenario.sort_key


@dataclass(frozen=True, slots=True)
class ClinicalOutcomeStressSimulationReport(SerializableRecord):
    protocol_id: str
    protocol_fingerprint: str
    simulation_method_id: str
    rng_method_id: str
    uncertainty_method_id: str
    analysis_modes: tuple[ClinicalOutcomeStressAnalysisMode, ...]
    estimand_targets: tuple[ClinicalOutcomeStressEstimandTarget, ...]
    confidence_level: float
    monte_carlo_confidence_level: float
    replicates: int
    coverage_target: float
    minimum_interval_yield: float
    scenario_results: tuple[ClinicalOutcomeStressScenarioResult, ...]
    aggregate_simulation_only: bool
    replicate_level_records_included: bool
    unit_level_records_included: bool
    real_clinical_outcomes_included: bool
    automatic_gate_selection_included: bool
    automatic_missingness_correction_included: bool
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        _require_text(self.protocol_id, "protocol_id")
        _require_sha256(self.protocol_fingerprint, "protocol_fingerprint")
        if self.simulation_method_id != CLINICAL_OUTCOME_STRESS_SIMULATION_METHOD_ID:
            raise ValueError("simulation_method_id is unsupported")
        if self.rng_method_id != CLINICAL_OUTCOME_STRESS_RNG_METHOD_ID:
            raise ValueError("rng_method_id is unsupported")
        if self.uncertainty_method_id != CLINICAL_OUTCOME_UNCERTAINTY_METHOD_ID:
            raise ValueError("uncertainty_method_id is unsupported")
        modes = _tuple(self.analysis_modes, "analysis_modes")
        object.__setattr__(self, "analysis_modes", modes)
        if modes != _ANALYSIS_MODE_ORDER:
            raise ValueError("analysis_modes must exactly cover canonical modes")
        targets = _tuple(self.estimand_targets, "estimand_targets")
        object.__setattr__(self, "estimand_targets", targets)
        if targets != _ESTIMAND_TARGET_ORDER:
            raise ValueError("estimand_targets must exactly cover canonical targets")
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
            raise ValueError("minimum_interval_yield must be positive")
        _require_positive_int(self.replicates, "replicates")
        results = _tuple(self.scenario_results, "scenario_results")
        object.__setattr__(self, "scenario_results", results)
        if not results:
            raise ValueError("stress report requires scenario results")
        for result in results:
            _require_instance(
                result,
                ClinicalOutcomeStressScenarioResult,
                "scenario_results item",
            )
            for analysis in result.analysis_performance:
                if analysis.replicate_diagnostics.replicate_count != self.replicates:
                    raise ValueError("scenario replicate count is inconsistent")
                for gate in analysis.gate_performance:
                    if (
                        gate.coverage_target != self.coverage_target
                        or gate.minimum_interval_yield != self.minimum_interval_yield
                    ):
                        raise ValueError("scenario gate targets are inconsistent")
                    if gate.diagnostic_interval_eligibility.confidence_level != (
                        self.monte_carlo_confidence_level
                    ):
                        raise ValueError(
                            "diagnostic Monte Carlo confidence is inconsistent"
                        )
                    for target in gate.target_performance:
                        if any(
                            metric.coverage.confidence_level
                            != self.monte_carlo_confidence_level
                            or metric.interval_yield.confidence_level
                            != self.monte_carlo_confidence_level
                            for metric in target.metric_performance
                        ):
                            raise ValueError(
                                "metric Monte Carlo confidence is inconsistent"
                            )
        if tuple(item.sort_key for item in results) != tuple(
            sorted(item.sort_key for item in results)
        ):
            raise ValueError("scenario results must use canonical order")
        if len({item.scenario.scenario_id for item in results}) != len(results):
            raise ValueError("scenario result ids must be unique")
        gate_rosters = {
            _sha256(
                tuple(
                    item.gate
                    for item in result.analysis_performance[0].gate_performance
                )
            )
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
            "automatic_missingness_correction_included",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.aggregate_simulation_only:
            raise ValueError("stress report must remain aggregate")
        if (
            self.replicate_level_records_included
            or self.unit_level_records_included
            or self.real_clinical_outcomes_included
            or self.automatic_gate_selection_included
            or self.automatic_missingness_correction_included
        ):
            raise ValueError("stress report crossed its simulation claim boundary")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required stress limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _scenario_stream_sha256(
    protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
) -> str:
    return _sha256(
        {
            "random_seed": protocol.random_seed,
            "rng_method_id": protocol.rng_method_id,
            "scenario": scenario,
        }
    )


def _substream_sha256(root_sha256: str, stream_name: str) -> str:
    return _sha256(
        {
            "rng_stream_sha256": root_sha256,
            "stream_name": stream_name,
        }
    )


def _truth_values(
    truth: ClinicalOutcomeStressScenarioTruth,
    target: ClinicalOutcomeStressEstimandTarget,
) -> dict[ClinicalOutcomeDesignMetric, float]:
    return {
        item.metric: (
            item.population_value
            if target is ClinicalOutcomeStressEstimandTarget.POPULATION
            else item.evaluable_value
        )
        for item in truth.metric_truths
    }


def _simulate_scenario(
    protocol: ClinicalOutcomeStressSimulationProtocol,
    scenario: ClinicalOutcomeStressScenario,
) -> ClinicalOutcomeStressScenarioResult:
    stream_sha256 = _scenario_stream_sha256(protocol, scenario)
    outcome_stream_sha256 = _substream_sha256(stream_sha256, "outcomes")
    evaluability_stream_sha256 = _substream_sha256(
        stream_sha256,
        "evaluability",
    )
    outcome_rng = random.Random(int(outcome_stream_sha256, 16))
    evaluability_rng = random.Random(int(evaluability_stream_sha256, 16))
    truth = _scenario_truth(scenario)
    truths_by_target = {
        target: _truth_values(truth, target) for target in _ESTIMAND_TARGET_ORDER
    }

    unit_ids: list[str] = []
    unit_ids_by_nominal_cluster: list[list[str]] = []
    nominal_cluster_by_unit: dict[str, str] = {}
    closed_cluster_by_unit: dict[str, str] = {}
    prediction_by_unit: dict[str, tuple[float, float]] = {}
    block_by_nominal_cluster: dict[int, int] = {
        nominal_index: block_index
        for block_index, block in enumerate(scenario.dependence_blocks)
        for nominal_index in block
    }
    for nominal_index, cluster_size in enumerate(scenario.nominal_cluster_sizes):
        nominal_cluster_id = f"nominal-cluster-{nominal_index:06d}"
        closed_cluster_id = (
            f"dependence-block-{block_by_nominal_cluster[nominal_index]:06d}"
        )
        nominal_units: list[str] = []
        for within_cluster_index in range(cluster_size):
            unit_id = f"{nominal_cluster_id}:unit-{within_cluster_index:06d}"
            unit_ids.append(unit_id)
            nominal_units.append(unit_id)
            nominal_cluster_by_unit[unit_id] = nominal_cluster_id
            closed_cluster_by_unit[unit_id] = closed_cluster_id
            pattern_index = within_cluster_index % len(
                scenario.policy_a_probability_pattern
            )
            prediction_by_unit[unit_id] = (
                scenario.policy_a_probability_pattern[pattern_index],
                scenario.policy_b_probability_pattern[pattern_index],
            )
        unit_ids_by_nominal_cluster.append(nominal_units)
    resolved_unit_ids = tuple(unit_ids)
    cluster_by_mode = {
        ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS: nominal_cluster_by_unit,
        ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS: (
            closed_cluster_by_unit
        ),
    }
    accumulators = {
        mode: {
            gate.gate_id: {
                target: {metric: _MetricAccumulator() for metric in _METRIC_ORDER}
                for target in _ESTIMAND_TARGET_ORDER
            }
            for gate in protocol.gates
        }
        for mode in _ANALYSIS_MODE_ORDER
    }
    diagnostic_counts = {
        mode: {gate.gate_id: Counter() for gate in protocol.gates}
        for mode in _ANALYSIS_MODE_ORDER
    }
    replicate_diagnostics = {
        mode: _ReplicateDiagnosticAccumulator() for mode in _ANALYSIS_MODE_ORDER
    }

    prevalence = scenario.favorable_prevalence
    correlation = scenario.dependence_block_intraclass_correlation
    for _ in range(protocol.replicates):
        labels_by_unit: dict[str, float] = {}
        for block in scenario.dependence_blocks:
            successes = 0
            previous_count = 0
            for nominal_index in block:
                for unit_id in unit_ids_by_nominal_cluster[nominal_index]:
                    label = _draw_beta_binomial_label(
                        outcome_rng,
                        prevalence,
                        correlation,
                        successes,
                        previous_count,
                    )
                    labels_by_unit[unit_id] = label
                    successes += int(label)
                    previous_count += 1

        evaluable_unit_ids: set[str] = set()
        values: dict[
            ClinicalOutcomeDesignMetric,
            list[tuple[str, float]],
        ] = {metric: [] for metric in _METRIC_ORDER}
        for unit_id in resolved_unit_ids:
            label = labels_by_unit[unit_id]
            evaluable_probability = (
                scenario.favorable_evaluable_probability
                if label == 1.0
                else scenario.unfavorable_evaluable_probability
            )
            if evaluability_rng.random() >= evaluable_probability:
                continue
            evaluable_unit_ids.add(unit_id)
            probability_a, probability_b = prediction_by_unit[unit_id]
            metric_values = _metric_values(
                label,
                probability_a,
                probability_b,
                scenario.classification_threshold,
            )
            for metric, value in metric_values.items():
                values[metric].append((unit_id, value))

        for mode in _ANALYSIS_MODE_ORDER:
            cluster_by_unit = cluster_by_mode[mode]
            base_diagnostic = _cluster_diagnostic(
                resolved_unit_ids,
                evaluable_unit_ids,
                cluster_by_unit,
                minimum_clusters=2,
                maximum_fraction=_IID_MAXIMUM_CLUSTER_FRACTION,
            )
            replicate_diagnostics[mode].add(
                base_diagnostic.evaluable_units,
                base_diagnostic.evaluable_cluster_count,
                base_diagnostic.largest_evaluable_cluster_fraction,
            )
            for gate in protocol.gates:
                diagnostic = _cluster_diagnostic(
                    resolved_unit_ids,
                    evaluable_unit_ids,
                    cluster_by_unit,
                    minimum_clusters=gate.minimum_evaluable_clusters,
                    maximum_fraction=gate.maximum_evaluable_cluster_fraction,
                )
                diagnostic_counts[mode][gate.gate_id][diagnostic.status] += 1
                for metric in _METRIC_ORDER:
                    lower, upper = _metric_bounds(metric)
                    estimate = _cluster_robust_estimate(
                        tuple(
                            (cluster_by_unit[unit_id], value)
                            for unit_id, value in values[metric]
                        ),
                        diagnostic,
                        confidence_level=protocol.confidence_level,
                        lower_bound=lower,
                        upper_bound=upper,
                    )
                    for target in _ESTIMAND_TARGET_ORDER:
                        accumulators[mode][gate.gate_id][target][metric].add(
                            estimate,
                            truths_by_target[target][metric],
                        )

    analyses: list[ClinicalOutcomeStressAnalysisPerformance] = []
    for mode in _ANALYSIS_MODE_ORDER:
        gate_performance: list[ClinicalOutcomeStressGatePerformance] = []
        for gate in protocol.gates:
            target_performance: list[ClinicalOutcomeStressTargetPerformance] = []
            finalized_by_target: dict[
                ClinicalOutcomeStressEstimandTarget,
                tuple[ClinicalOutcomeDesignMetricPerformance, ...],
            ] = {}
            for target in _ESTIMAND_TARGET_ORDER:
                finalized = tuple(
                    accumulators[mode][gate.gate_id][target][metric].finalize(
                        metric,
                        truths_by_target[target][metric],
                        protocol.replicates,
                        protocol.monte_carlo_confidence_level,
                    )
                    for metric in _METRIC_ORDER
                )
                finalized_by_target[target] = finalized
            population_metrics = finalized_by_target[
                ClinicalOutcomeStressEstimandTarget.POPULATION
            ]
            yield_met = all(
                item.interval_yield.lower is not None
                and item.interval_yield.lower >= protocol.minimum_interval_yield
                for item in population_metrics
            )
            for target in _ESTIMAND_TARGET_ORDER:
                metrics = finalized_by_target[target]
                coverage_met = all(
                    item.coverage.lower is not None
                    and item.coverage.lower >= protocol.coverage_target
                    for item in metrics
                )
                target_performance.append(
                    ClinicalOutcomeStressTargetPerformance(
                        target=target,
                        all_metric_coverage_targets_met=coverage_met,
                        design_target_met=coverage_met and yield_met,
                        metric_performance=metrics,
                    )
                )
            counts = diagnostic_counts[mode][gate.gate_id]
            gate_performance.append(
                ClinicalOutcomeStressGatePerformance(
                    gate=gate,
                    replicate_count=protocol.replicates,
                    diagnostic_status_counts=_status_count_records(counts),
                    diagnostic_interval_eligibility=_design_rate(
                        counts[ClusterInferenceStatus.COMPUTED],
                        protocol.replicates,
                        protocol.monte_carlo_confidence_level,
                    ),
                    coverage_target=protocol.coverage_target,
                    minimum_interval_yield=protocol.minimum_interval_yield,
                    all_metric_yield_targets_met=yield_met,
                    target_performance=tuple(target_performance),
                )
            )
        analyses.append(
            ClinicalOutcomeStressAnalysisPerformance(
                analysis_mode=mode,
                cluster_structure=_structure_from_sizes(
                    _analysis_cluster_sizes(scenario, mode)
                ),
                replicate_diagnostics=replicate_diagnostics[mode].finalize(),
                gate_performance=tuple(gate_performance),
            )
        )
    return ClinicalOutcomeStressScenarioResult(
        scenario=scenario,
        truth=truth,
        rng_stream_sha256=stream_sha256,
        outcome_rng_stream_sha256=outcome_stream_sha256,
        evaluability_rng_stream_sha256=evaluability_stream_sha256,
        analysis_performance=tuple(analyses),
    )


def simulate_clinical_outcome_stress(
    protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomeStressSimulationReport:
    """Run deterministic aggregate estimand and dependence stress simulations."""

    _require_instance(
        protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "protocol",
    )
    return ClinicalOutcomeStressSimulationReport(
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        simulation_method_id=protocol.simulation_method_id,
        rng_method_id=protocol.rng_method_id,
        uncertainty_method_id=protocol.uncertainty_method_id,
        analysis_modes=protocol.analysis_modes,
        estimand_targets=protocol.estimand_targets,
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
        automatic_missingness_correction_included=False,
    )


def validate_clinical_outcome_stress_simulation_report(
    report: ClinicalOutcomeStressSimulationReport,
    protocol: ClinicalOutcomeStressSimulationProtocol,
) -> tuple[str, ...]:
    """Replay a stress simulation exactly and compare the aggregate report."""

    try:
        rebuilt = simulate_clinical_outcome_stress(protocol)
    except (ClinicalOutcomeStressSimulationError, TypeError, ValueError):
        return ("clinical_outcome_stress_simulation_recompile_failed",)
    if rebuilt != report:
        return ("recompiled_clinical_outcome_stress_simulation_report_mismatch",)
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


def _target_by_name(
    gate: ClinicalOutcomeStressGatePerformance,
) -> dict[ClinicalOutcomeStressEstimandTarget, ClinicalOutcomeStressTargetPerformance]:
    return {item.target: item for item in gate.target_performance}


def clinical_outcome_stress_simulation_summary(
    report: ClinicalOutcomeStressSimulationReport,
) -> dict[str, Any]:
    """Project a compact estimand-shift and dependence-closure comparison."""

    _require_instance(
        report,
        ClinicalOutcomeStressSimulationReport,
        "report",
    )
    target_met_counts: Counter[
        tuple[ClinicalOutcomeStressAnalysisMode, ClinicalOutcomeStressEstimandTarget]
    ] = Counter()
    scenario_summaries: list[dict[str, Any]] = []
    for result in report.scenario_results:
        analysis_summaries: list[dict[str, Any]] = []
        analyses_by_mode = {
            item.analysis_mode: item for item in result.analysis_performance
        }
        gates_by_mode = {
            mode: {item.gate.gate_id: item for item in analysis.gate_performance}
            for mode, analysis in analyses_by_mode.items()
        }
        for analysis in result.analysis_performance:
            gate_summaries: list[dict[str, Any]] = []
            target_met_gate_ids = {
                target.value: [] for target in _ESTIMAND_TARGET_ORDER
            }
            evaluable_not_population: list[str] = []
            for gate in analysis.gate_performance:
                targets = _target_by_name(gate)
                for target in _ESTIMAND_TARGET_ORDER:
                    target_result = targets[target]
                    if target_result.design_target_met:
                        target_met_gate_ids[target.value].append(gate.gate.gate_id)
                        target_met_counts[(analysis.analysis_mode, target)] += 1
                if (
                    targets[
                        ClinicalOutcomeStressEstimandTarget.EVALUABLE
                    ].design_target_met
                    and not targets[
                        ClinicalOutcomeStressEstimandTarget.POPULATION
                    ].design_target_met
                ):
                    evaluable_not_population.append(gate.gate.gate_id)
                gate_summaries.append(
                    {
                        "gate_id": gate.gate.gate_id,
                        "minimum_evaluable_clusters": (
                            gate.gate.minimum_evaluable_clusters
                        ),
                        "maximum_evaluable_cluster_fraction": (
                            gate.gate.maximum_evaluable_cluster_fraction
                        ),
                        "diagnostic_interval_eligibility": _rate_projection(
                            gate.diagnostic_interval_eligibility
                        ),
                        "diagnostic_status_counts": {
                            item.status.value: item.count
                            for item in gate.diagnostic_status_counts
                        },
                        "coverage_target": gate.coverage_target,
                        "minimum_interval_yield": gate.minimum_interval_yield,
                        "all_metric_yield_targets_met": (
                            gate.all_metric_yield_targets_met
                        ),
                        "estimand_targets": [
                            {
                                "estimand_target": target.target.value,
                                "all_metric_coverage_targets_met": (
                                    target.all_metric_coverage_targets_met
                                ),
                                "design_target_met": target.design_target_met,
                                "metrics": [
                                    _metric_projection(metric)
                                    for metric in target.metric_performance
                                ],
                            }
                            for target in gate.target_performance
                        ],
                    }
                )
            analysis_summaries.append(
                {
                    "analysis_mode": analysis.analysis_mode.value,
                    "cluster_structure": analysis.cluster_structure.to_dict(),
                    "replicate_diagnostics": (analysis.replicate_diagnostics.to_dict()),
                    "candidate_gates": gate_summaries,
                    "target_met_gate_ids": target_met_gate_ids,
                    "evaluable_not_population_target_met_gate_ids": (
                        evaluable_not_population
                    ),
                }
            )

        nominal_gates = gates_by_mode[
            ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS
        ]
        closed_gates = gates_by_mode[
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS
        ]
        closure_recovery: dict[str, list[str]] = {
            target.value: [] for target in _ESTIMAND_TARGET_ORDER
        }
        for gate_id, nominal_gate in nominal_gates.items():
            nominal_targets = _target_by_name(nominal_gate)
            closed_targets = _target_by_name(closed_gates[gate_id])
            for target in _ESTIMAND_TARGET_ORDER:
                if (
                    closed_targets[target].design_target_met
                    and not nominal_targets[target].design_target_met
                ):
                    closure_recovery[target.value].append(gate_id)
        scenario_summaries.append(
            {
                "scenario_id": result.scenario.scenario_id,
                "stage": result.scenario.stage.value,
                "endpoint_family": result.scenario.endpoint_family,
                "stressors": {
                    "outcome_dependent_evaluability": (
                        result.scenario.outcome_dependent_evaluability
                    ),
                    "cross_nominal_cluster_dependence": (
                        result.scenario.cross_nominal_cluster_dependence
                    ),
                    "nominal_cluster_count": len(result.scenario.nominal_cluster_sizes),
                    "dependence_block_count": len(result.scenario.dependence_blocks),
                    "favorable_evaluable_probability": (
                        result.scenario.favorable_evaluable_probability
                    ),
                    "unfavorable_evaluable_probability": (
                        result.scenario.unfavorable_evaluable_probability
                    ),
                    "dependence_block_intraclass_correlation": (
                        result.scenario.dependence_block_intraclass_correlation
                    ),
                },
                "truth": {
                    "population_favorable_prevalence": (
                        result.truth.population_favorable_prevalence
                    ),
                    "expected_evaluable_probability": (
                        result.truth.expected_evaluable_probability
                    ),
                    "evaluable_favorable_prevalence": (
                        result.truth.evaluable_favorable_prevalence
                    ),
                    "metric_truths": [
                        item.to_dict() for item in result.truth.metric_truths
                    ],
                },
                "analysis_results": analysis_summaries,
                "dependence_closure_recovery_gate_ids": closure_recovery,
            }
        )
    return {
        "schema_version": CLINICAL_OUTCOME_STRESS_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "protocol_id": report.protocol_id,
        "protocol_fingerprint": report.protocol_fingerprint,
        "simulation_method_id": report.simulation_method_id,
        "rng_method_id": report.rng_method_id,
        "uncertainty_method_id": report.uncertainty_method_id,
        "analysis_modes": [item.value for item in report.analysis_modes],
        "estimand_targets": [item.value for item in report.estimand_targets],
        "confidence_level": report.confidence_level,
        "monte_carlo_confidence_level": report.monte_carlo_confidence_level,
        "replicates": report.replicates,
        "coverage_target": report.coverage_target,
        "minimum_interval_yield": report.minimum_interval_yield,
        "scenario_count": len(report.scenario_results),
        "scenario_analysis_gate_count": sum(
            len(analysis.gate_performance)
            for result in report.scenario_results
            for analysis in result.analysis_performance
        ),
        "design_target_met_counts": [
            {
                "analysis_mode": mode.value,
                "estimand_target": target.value,
                "count": target_met_counts[(mode, target)],
            }
            for mode in _ANALYSIS_MODE_ORDER
            for target in _ESTIMAND_TARGET_ORDER
        ],
        "scenarios": scenario_summaries,
        "aggregate_simulation_only": report.aggregate_simulation_only,
        "replicate_level_records_included": (report.replicate_level_records_included),
        "unit_level_records_included": report.unit_level_records_included,
        "real_clinical_outcomes_included": (report.real_clinical_outcomes_included),
        "automatic_gate_selection_included": (report.automatic_gate_selection_included),
        "automatic_missingness_correction_included": (
            report.automatic_missingness_correction_included
        ),
    }


def clinical_outcome_stress_simulation_validation_summary(
    report: ClinicalOutcomeStressSimulationReport,
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
        **clinical_outcome_stress_simulation_summary(report),
        "validation": {
            "status": "valid" if not resolved_failures else "invalid",
            "scope": scope,
            "failure_codes": list(resolved_failures),
        },
    }


def clinical_outcome_stress_protocol_envelope(
    protocol: ClinicalOutcomeStressSimulationProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        ClinicalOutcomeStressSimulationProtocol,
        "protocol",
    )
    return {
        "schema_version": CLINICAL_OUTCOME_STRESS_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def clinical_outcome_stress_report_envelope(
    report: ClinicalOutcomeStressSimulationReport,
) -> dict[str, Any]:
    _require_instance(report, ClinicalOutcomeStressSimulationReport, "report")
    return {
        "schema_version": CLINICAL_OUTCOME_STRESS_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _check_integrity(value: SerializableRecord, integrity: str, label: str) -> None:
    fingerprint = getattr(value, "fingerprint", None)
    if fingerprint != integrity:
        raise RecordParseError(f"{label} integrity mismatch")


def _parse_stress_scenario(value: Any, path: str) -> ClinicalOutcomeStressScenario:
    data = _record(
        value,
        path,
        {
            "scenario_id",
            "stage",
            "endpoint_family",
            "nominal_cluster_sizes",
            "dependence_blocks",
            "favorable_prevalence",
            "dependence_block_intraclass_correlation",
            "favorable_evaluable_probability",
            "unfavorable_evaluable_probability",
            "classification_threshold",
            "policy_a_probability_pattern",
            "policy_b_probability_pattern",
        },
    )
    return ClinicalOutcomeStressScenario(
        scenario_id=data["scenario_id"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        endpoint_family=data["endpoint_family"],
        nominal_cluster_sizes=tuple(
            _sequence(data["nominal_cluster_sizes"], f"{path}.nominal_cluster_sizes")
        ),
        dependence_blocks=tuple(
            tuple(_sequence(block, f"{path}.dependence_blocks[{index}]"))
            for index, block in enumerate(
                _sequence(data["dependence_blocks"], f"{path}.dependence_blocks")
            )
        ),
        favorable_prevalence=data["favorable_prevalence"],
        dependence_block_intraclass_correlation=data[
            "dependence_block_intraclass_correlation"
        ],
        favorable_evaluable_probability=data["favorable_evaluable_probability"],
        unfavorable_evaluable_probability=data["unfavorable_evaluable_probability"],
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


def clinical_outcome_stress_protocol_from_dict(
    value: Any,
) -> ClinicalOutcomeStressSimulationProtocol:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_stress_protocol_envelope",
        schema_version=CLINICAL_OUTCOME_STRESS_PROTOCOL_SCHEMA_VERSION,
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
            "analysis_modes",
            "estimand_targets",
            "gates",
            "scenarios",
            "simulation_method_id",
            "rng_method_id",
            "uncertainty_method_id",
            "metadata",
        },
    )
    protocol = ClinicalOutcomeStressSimulationProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        confidence_level=data["confidence_level"],
        monte_carlo_confidence_level=data["monte_carlo_confidence_level"],
        replicates=data["replicates"],
        random_seed=data["random_seed"],
        coverage_tolerance=data["coverage_tolerance"],
        minimum_interval_yield=data["minimum_interval_yield"],
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
        estimand_targets=tuple(
            _parse_enum(
                ClinicalOutcomeStressEstimandTarget,
                item,
                f"protocol.estimand_targets[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["estimand_targets"], "protocol.estimand_targets")
            )
        ),
        gates=tuple(
            _parse_design_gate(item, f"protocol.gates[{index}]")
            for index, item in enumerate(_sequence(data["gates"], "protocol.gates"))
        ),
        scenarios=tuple(
            _parse_stress_scenario(item, f"protocol.scenarios[{index}]")
            for index, item in enumerate(
                _sequence(data["scenarios"], "protocol.scenarios")
            )
        ),
        simulation_method_id=data["simulation_method_id"],
        rng_method_id=data["rng_method_id"],
        uncertainty_method_id=data["uncertainty_method_id"],
        metadata=_mapping(data["metadata"], "protocol.metadata"),
    )
    _check_integrity(protocol, integrity, "stress simulation protocol")
    return protocol


def _parse_metric_truth(value: Any, path: str) -> ClinicalOutcomeStressMetricTruth:
    data = _record(
        value,
        path,
        {
            "metric",
            "population_value",
            "evaluable_value",
            "evaluable_minus_population",
        },
    )
    return ClinicalOutcomeStressMetricTruth(
        metric=_parse_enum(
            ClinicalOutcomeDesignMetric,
            data["metric"],
            f"{path}.metric",
        ),
        population_value=data["population_value"],
        evaluable_value=data["evaluable_value"],
        evaluable_minus_population=data["evaluable_minus_population"],
    )


def _parse_scenario_truth(
    value: Any,
    path: str,
) -> ClinicalOutcomeStressScenarioTruth:
    data = _record(
        value,
        path,
        {
            "population_favorable_prevalence",
            "expected_evaluable_probability",
            "evaluable_favorable_prevalence",
            "metric_truths",
        },
    )
    return ClinicalOutcomeStressScenarioTruth(
        population_favorable_prevalence=data["population_favorable_prevalence"],
        expected_evaluable_probability=data["expected_evaluable_probability"],
        evaluable_favorable_prevalence=data["evaluable_favorable_prevalence"],
        metric_truths=tuple(
            _parse_metric_truth(item, f"{path}.metric_truths[{index}]")
            for index, item in enumerate(
                _sequence(data["metric_truths"], f"{path}.metric_truths")
            )
        ),
    )


def _parse_target_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomeStressTargetPerformance:
    data = _record(
        value,
        path,
        {
            "target",
            "all_metric_coverage_targets_met",
            "design_target_met",
            "metric_performance",
        },
    )
    return ClinicalOutcomeStressTargetPerformance(
        target=_parse_enum(
            ClinicalOutcomeStressEstimandTarget,
            data["target"],
            f"{path}.target",
        ),
        all_metric_coverage_targets_met=data["all_metric_coverage_targets_met"],
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


def _parse_gate_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomeStressGatePerformance:
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
            "all_metric_yield_targets_met",
            "target_performance",
        },
    )
    return ClinicalOutcomeStressGatePerformance(
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
        all_metric_yield_targets_met=data["all_metric_yield_targets_met"],
        target_performance=tuple(
            _parse_target_performance(
                item,
                f"{path}.target_performance[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["target_performance"],
                    f"{path}.target_performance",
                )
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


def _parse_analysis_performance(
    value: Any,
    path: str,
) -> ClinicalOutcomeStressAnalysisPerformance:
    data = _record(
        value,
        path,
        {
            "analysis_mode",
            "cluster_structure",
            "replicate_diagnostics",
            "gate_performance",
        },
    )
    return ClinicalOutcomeStressAnalysisPerformance(
        analysis_mode=_parse_enum(
            ClinicalOutcomeStressAnalysisMode,
            data["analysis_mode"],
            f"{path}.analysis_mode",
        ),
        cluster_structure=_parse_design_structure(
            data["cluster_structure"],
            f"{path}.cluster_structure",
        ),
        replicate_diagnostics=_parse_replicate_diagnostics(
            data["replicate_diagnostics"],
            f"{path}.replicate_diagnostics",
        ),
        gate_performance=tuple(
            _parse_gate_performance(item, f"{path}.gate_performance[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["gate_performance"],
                    f"{path}.gate_performance",
                )
            )
        ),
    )


def _parse_scenario_result(
    value: Any,
    path: str,
) -> ClinicalOutcomeStressScenarioResult:
    data = _record(
        value,
        path,
        {
            "scenario",
            "truth",
            "rng_stream_sha256",
            "outcome_rng_stream_sha256",
            "evaluability_rng_stream_sha256",
            "analysis_performance",
        },
    )
    return ClinicalOutcomeStressScenarioResult(
        scenario=_parse_stress_scenario(data["scenario"], f"{path}.scenario"),
        truth=_parse_scenario_truth(data["truth"], f"{path}.truth"),
        rng_stream_sha256=data["rng_stream_sha256"],
        outcome_rng_stream_sha256=data["outcome_rng_stream_sha256"],
        evaluability_rng_stream_sha256=data["evaluability_rng_stream_sha256"],
        analysis_performance=tuple(
            _parse_analysis_performance(
                item,
                f"{path}.analysis_performance[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["analysis_performance"],
                    f"{path}.analysis_performance",
                )
            )
        ),
    )


def clinical_outcome_stress_report_from_dict(
    value: Any,
) -> ClinicalOutcomeStressSimulationReport:
    payload, integrity = _integrity_payload(
        value,
        path="clinical_outcome_stress_report_envelope",
        schema_version=CLINICAL_OUTCOME_STRESS_REPORT_SCHEMA_VERSION,
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
            "analysis_modes",
            "estimand_targets",
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
            "automatic_missingness_correction_included",
            "limitations",
        },
    )
    report = ClinicalOutcomeStressSimulationReport(
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        simulation_method_id=data["simulation_method_id"],
        rng_method_id=data["rng_method_id"],
        uncertainty_method_id=data["uncertainty_method_id"],
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
        estimand_targets=tuple(
            _parse_enum(
                ClinicalOutcomeStressEstimandTarget,
                item,
                f"report.estimand_targets[{index}]",
            )
            for index, item in enumerate(
                _sequence(data["estimand_targets"], "report.estimand_targets")
            )
        ),
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
        automatic_gate_selection_included=data["automatic_gate_selection_included"],
        automatic_missingness_correction_included=data[
            "automatic_missingness_correction_included"
        ],
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
    )
    _check_integrity(report, integrity, "stress simulation report")
    return report


def clinical_outcome_stress_protocol_from_json(
    payload: str,
) -> ClinicalOutcomeStressSimulationProtocol:
    return clinical_outcome_stress_protocol_from_dict(
        _strict_json(payload, "clinical outcome stress simulation protocol")
    )


def clinical_outcome_stress_report_from_json(
    payload: str,
) -> ClinicalOutcomeStressSimulationReport:
    return clinical_outcome_stress_report_from_dict(
        _strict_json(payload, "clinical outcome stress simulation report")
    )
