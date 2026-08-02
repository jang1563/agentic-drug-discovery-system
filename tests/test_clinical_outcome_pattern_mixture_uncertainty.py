from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery import (
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomePatternMixtureJackknifeStatus,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomePatternMixtureUncertaintyError,
    ClinicalOutcomePatternMixtureUncertaintyProtocol,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    RecordParseError,
    Stage,
    analyze_clinical_outcome_pattern_mixture,
    analyze_clinical_outcome_pattern_mixture_uncertainty,
    clinical_outcome_pattern_mixture_protocol_envelope,
    clinical_outcome_pattern_mixture_protocol_from_json,
    clinical_outcome_pattern_mixture_uncertainty_protocol_envelope,
    clinical_outcome_pattern_mixture_uncertainty_protocol_from_dict,
    clinical_outcome_pattern_mixture_uncertainty_protocol_from_json,
    clinical_outcome_pattern_mixture_uncertainty_report_envelope,
    clinical_outcome_pattern_mixture_uncertainty_report_from_dict,
    clinical_outcome_pattern_mixture_uncertainty_report_from_json,
    clinical_outcome_pattern_mixture_uncertainty_summary,
    clinical_outcome_stress_protocol_envelope,
    clinical_outcome_stress_protocol_from_json,
    validate_clinical_outcome_pattern_mixture_uncertainty_report,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
PROTOCOL_SCHEMA = (
    SPECS / "clinical_outcome_pattern_mixture_uncertainty_protocol.schema.json"
)
PROTOCOL_EXAMPLE = (
    SPECS / "clinical_outcome_pattern_mixture_uncertainty_protocol.example.json"
)
REPORT_SCHEMA = (
    SPECS / "clinical_outcome_pattern_mixture_uncertainty_report.schema.json"
)
REPORT_EXAMPLE = (
    SPECS / "clinical_outcome_pattern_mixture_uncertainty_report.example.json"
)
SUMMARY_SCHEMA = (
    SPECS / "clinical_outcome_pattern_mixture_uncertainty_summary.schema.json"
)
PATTERN_PROTOCOL_EXAMPLE = (
    SPECS / "clinical_outcome_pattern_mixture_protocol.example.json"
)
STRESS_PROTOCOL_EXAMPLE = (
    SPECS / "clinical_outcome_stress_simulation_protocol.example.json"
)


def _scenario(
    *,
    scenario_id: str = "hidden-linkage",
    cluster_count: int = 8,
    cluster_size: int = 8,
    linked: bool = True,
    prevalence: float = 0.4,
    favorable_evaluable_probability: float = 0.9,
    unfavorable_evaluable_probability: float = 0.45,
) -> ClinicalOutcomeStressScenario:
    blocks = (
        tuple((index, index + 1) for index in range(0, cluster_count, 2))
        if linked
        else tuple((index,) for index in range(cluster_count))
    )
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=(cluster_size,) * cluster_count,
        dependence_blocks=blocks,
        favorable_prevalence=prevalence,
        dependence_block_intraclass_correlation=0.15,
        favorable_evaluable_probability=favorable_evaluable_probability,
        unfavorable_evaluable_probability=unfavorable_evaluable_probability,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
        policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
    )


def _stress_protocol(
    scenario: ClinicalOutcomeStressScenario,
    *,
    random_seed: int = 73,
) -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="pattern-mixture-jackknife-stress-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=100,
        random_seed=random_seed,
        coverage_tolerance=0.2,
        minimum_interval_yield=0.5,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="test-g04-share40",
                minimum_evaluable_clusters=4,
                maximum_evaluable_cluster_fraction=0.4,
            ),
        ),
        scenarios=(scenario,),
        metadata={"public_test": True},
    )


def _pattern_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    *,
    minimum_analyzable_rate: float = 0.2,
) -> ClinicalOutcomePatternMixtureProtocol:
    return ClinicalOutcomePatternMixtureProtocol(
        protocol_id="pattern-mixture-jackknife-pattern-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        log_imor_grid=(-4.0, -2.397895272798, 0.0, 4.0),
        monte_carlo_confidence_level=0.95,
        minimum_analyzable_rate=minimum_analyzable_rate,
        maximum_mean_identification_width=1.0,
        maximum_absolute_bias=0.2,
        metadata={"public_test": True},
    )


def _uncertainty_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    pattern_report,
    *,
    minimum_clusters: int = 4,
    maximum_cluster_unit_fraction: float = 0.3,
) -> ClinicalOutcomePatternMixtureUncertaintyProtocol:
    return ClinicalOutcomePatternMixtureUncertaintyProtocol(
        protocol_id="pattern-mixture-jackknife-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        pattern_mixture_protocol_fingerprint=pattern_protocol.fingerprint,
        pattern_mixture_report_fingerprint=pattern_report.fingerprint,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.2,
        minimum_interval_yield=0.5,
        minimum_clusters=minimum_clusters,
        maximum_cluster_unit_fraction=maximum_cluster_unit_fraction,
        maximum_standard_error_calibration_deviation=0.5,
        closure_anchor_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        minimum_hidden_linkage_coverage_gain=0.0,
        minimum_hidden_linkage_standard_error_ratio=1.0,
        metadata={"public_test": True},
    )


def _mode(result, mode: ClinicalOutcomeStressAnalysisMode):
    return next(item for item in result.mode_inference if item.analysis_mode is mode)


def _metric(mode, metric: ClinicalOutcomeDesignMetric):
    return next(item for item in mode.metric_inference if item.metric is metric)


def _status_count(grid, status: ClinicalOutcomePatternMixtureJackknifeStatus) -> int:
    return next(item.count for item in grid.status_counts if item.status is status)


class ClinicalOutcomePatternMixtureUncertaintyTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.public_stress_protocol = clinical_outcome_stress_protocol_from_json(
            STRESS_PROTOCOL_EXAMPLE.read_text()
        )
        cls.public_pattern_protocol = (
            clinical_outcome_pattern_mixture_protocol_from_json(
                PATTERN_PROTOCOL_EXAMPLE.read_text()
            )
        )
        cls.public_protocol = (
            clinical_outcome_pattern_mixture_uncertainty_protocol_from_json(
                PROTOCOL_EXAMPLE.read_text()
            )
        )
        cls.public_report = (
            clinical_outcome_pattern_mixture_uncertainty_report_from_json(
                REPORT_EXAMPLE.read_text()
            )
        )
        cls.small_stress = _stress_protocol(_scenario())
        cls.small_pattern = _pattern_protocol(cls.small_stress)
        cls.small_pattern_report = analyze_clinical_outcome_pattern_mixture(
            cls.small_pattern,
            cls.small_stress,
        )

    def test_public_schemas_summary_and_exact_replay_are_synchronized(self) -> None:
        Draft202012Validator(
            json.loads(PROTOCOL_SCHEMA.read_text()),
            format_checker=FormatChecker(),
        ).validate(json.loads(PROTOCOL_EXAMPLE.read_text()))
        Draft202012Validator(
            json.loads(REPORT_SCHEMA.read_text()),
            format_checker=FormatChecker(),
        ).validate(json.loads(REPORT_EXAMPLE.read_text()))
        summary = clinical_outcome_pattern_mixture_uncertainty_summary(
            self.public_report
        )
        Draft202012Validator(json.loads(SUMMARY_SCHEMA.read_text())).validate(summary)

        rebuilt = analyze_clinical_outcome_pattern_mixture_uncertainty(
            self.public_protocol,
            self.public_pattern_protocol,
            self.public_stress_protocol,
        )
        self.assertEqual(rebuilt, self.public_report)
        self.assertEqual(
            self.public_protocol.fingerprint,
            "9152583c61349513987ef45d6553d9e2157b723dcc57e9640a26d8d4c498bea4",
        )
        self.assertEqual(
            rebuilt.fingerprint,
            "931b7bb9cc06f1949085e9763bb2f93671a8a29547c1036cc31d0245cc02b045",
        )
        self.assertTrue(summary["all_scenarios_research_targets_met"])

    def test_dependence_closure_recovers_grid_calibration(self) -> None:
        for result in self.public_report.scenario_inference[:2]:
            nominal = _mode(
                result,
                ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS,
            )
            closed = _mode(
                result,
                ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
            )
            self.assertFalse(nominal.all_metric_research_targets_met)
            self.assertTrue(closed.all_metric_research_targets_met)
            closed_grid = [
                grid
                for metric in closed.metric_inference
                for grid in metric.grid_inference
            ]
            self.assertTrue(
                all(
                    item.model_functional_coverage.lower
                    >= self.public_report.coverage_target
                    for item in closed_grid
                )
            )
            anchor = next(
                item
                for item in result.closure_comparison
                if item.closure_response_target_required
            )
            self.assertIs(
                anchor.metric,
                ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
            )
            self.assertGreaterEqual(
                anchor.dependence_closed_minus_nominal_coverage,
                self.public_report.minimum_hidden_linkage_coverage_gain,
            )
            self.assertGreaterEqual(
                anchor.dependence_closed_to_nominal_standard_error_ratio,
                self.public_report.minimum_hidden_linkage_standard_error_ratio,
            )

    def test_independent_scenario_has_exact_mode_equivalence(self) -> None:
        result = self.public_report.scenario_inference[2]
        self.assertFalse(result.hidden_linkage_declared)
        self.assertTrue(
            all(
                item.closure_response_target_required
                and item.exact_equivalence_expected
                and item.exact_equivalence_met
                for item in result.closure_comparison
            )
        )
        nominal = _mode(result, ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS)
        closed = _mode(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        )
        self.assertEqual(nominal.metric_inference, closed.metric_inference)

    def test_model_functional_and_population_coverage_are_separated(self) -> None:
        result = self.public_report.scenario_inference[0]
        closed = _mode(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        )
        favorable = _metric(
            closed,
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        wrong_shift = favorable.grid_inference[-1]
        self.assertNotEqual(
            wrong_shift.model_functional_true_value,
            wrong_shift.population_true_value,
        )
        self.assertNotEqual(
            wrong_shift.model_functional_coverage,
            wrong_shift.population_truth_coverage,
        )
        truth = favorable.truth_aligned_inference
        self.assertEqual(truth.model_functional_true_value, truth.population_true_value)
        self.assertEqual(
            truth.model_functional_coverage, truth.population_truth_coverage
        )

    def test_continuous_monte_carlo_bounds_and_prior_curve_binding(self) -> None:
        for result in self.public_report.scenario_inference:
            closed = _mode(
                result,
                ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
            )
            for metric in closed.metric_inference:
                for grid in metric.grid_inference:
                    self.assertEqual(
                        grid.mean_estimate,
                        grid.prior_pattern_mixture_mean_estimate,
                    )
                    self.assertIsNotNone(grid.monte_carlo_bias_lower)
                    self.assertIsNotNone(grid.monte_carlo_bias_upper)
                    self.assertLessEqual(
                        grid.monte_carlo_absolute_bias_upper,
                        self.public_report.maximum_absolute_bias,
                    )
                    self.assertTrue(grid.bias_target_met)

    def test_cluster_count_and_dominance_gates_fail_closed(self) -> None:
        insufficient_protocol = _uncertainty_protocol(
            self.small_stress,
            self.small_pattern,
            self.small_pattern_report,
            minimum_clusters=9,
        )
        insufficient = analyze_clinical_outcome_pattern_mixture_uncertainty(
            insufficient_protocol,
            self.small_pattern,
            self.small_stress,
        ).scenario_inference[0]
        for mode in insufficient.mode_inference:
            grid = mode.metric_inference[0].grid_inference[0]
            self.assertEqual(grid.interval_count, 0)
            self.assertGreater(grid.point_estimate_count, 0)
            self.assertGreater(
                _status_count(
                    grid,
                    ClinicalOutcomePatternMixtureJackknifeStatus.INSUFFICIENT_CLUSTERS,
                ),
                0,
            )

        dominant_protocol = _uncertainty_protocol(
            self.small_stress,
            self.small_pattern,
            self.small_pattern_report,
            maximum_cluster_unit_fraction=0.2,
        )
        dominant = analyze_clinical_outcome_pattern_mixture_uncertainty(
            dominant_protocol,
            self.small_pattern,
            self.small_stress,
        ).scenario_inference[0]
        nominal = _mode(dominant, ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS)
        closed = _mode(
            dominant,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        )
        self.assertGreater(
            nominal.metric_inference[0].grid_inference[0].interval_count, 0
        )
        closed_grid = closed.metric_inference[0].grid_inference[0]
        self.assertEqual(closed_grid.interval_count, 0)
        self.assertGreater(
            _status_count(
                closed_grid,
                ClinicalOutcomePatternMixtureJackknifeStatus.DOMINANT_CLUSTER,
            ),
            0,
        )

    def test_leave_one_out_reference_support_failure_is_explicit(self) -> None:
        sparse_stress = _stress_protocol(
            _scenario(
                scenario_id="sparse-leaveout",
                cluster_count=4,
                cluster_size=4,
                linked=False,
                prevalence=0.5,
                favorable_evaluable_probability=0.55,
                unfavorable_evaluable_probability=0.55,
            ),
            random_seed=91,
        )
        sparse_pattern = _pattern_protocol(
            sparse_stress,
            minimum_analyzable_rate=0.01,
        )
        sparse_pattern_report = analyze_clinical_outcome_pattern_mixture(
            sparse_pattern,
            sparse_stress,
        )
        sparse_protocol = _uncertainty_protocol(
            sparse_stress,
            sparse_pattern,
            sparse_pattern_report,
            minimum_clusters=3,
            maximum_cluster_unit_fraction=0.4,
        )
        report = analyze_clinical_outcome_pattern_mixture_uncertainty(
            sparse_protocol,
            sparse_pattern,
            sparse_stress,
        )
        grid = (
            report.scenario_inference[0]
            .mode_inference[0]
            .metric_inference[0]
            .grid_inference[0]
        )
        leaveout_failures = sum(
            _status_count(grid, status)
            for status in (
                ClinicalOutcomePatternMixtureJackknifeStatus.LEAVE_ONE_OUT_EMPTY_REFERENCE_STRATUM,
                ClinicalOutcomePatternMixtureJackknifeStatus.LEAVE_ONE_OUT_DEGENERATE_REFERENCE_STRATUM,
            )
        )
        self.assertGreater(leaveout_failures, 0)
        self.assertLess(grid.interval_count, grid.point_estimate_count)

    def test_exact_bindings_replay_and_claim_tamper_fail_closed(self) -> None:
        other_stress = replace(self.small_stress, random_seed=74)
        protocol = _uncertainty_protocol(
            self.small_stress,
            self.small_pattern,
            self.small_pattern_report,
        )
        with self.assertRaisesRegex(
            ClinicalOutcomePatternMixtureUncertaintyError,
            "not bound",
        ):
            analyze_clinical_outcome_pattern_mixture_uncertainty(
                protocol,
                self.small_pattern,
                other_stress,
            )
        report = analyze_clinical_outcome_pattern_mixture_uncertainty(
            protocol,
            self.small_pattern,
            self.small_stress,
        )
        self.assertEqual(
            validate_clinical_outcome_pattern_mixture_uncertainty_report(
                report,
                protocol,
                self.small_pattern,
                self.small_stress,
            ),
            (),
        )
        with self.assertRaisesRegex(ValueError, "claim boundary"):
            replace(report, automatic_dependence_closure_included=True)
        with self.assertRaisesRegex(ValueError, "nested calibration target"):
            replace(report, minimum_interval_yield=0.99)
        grid = (
            report.scenario_inference[0]
            .mode_inference[0]
            .metric_inference[0]
            .grid_inference[0]
        )
        with self.assertRaisesRegex(ValueError, "interval-width bounds"):
            replace(
                grid,
                interval_width_empirical_standard_deviation=(
                    grid.interval_width_empirical_standard_deviation + 0.001
                ),
            )
        with self.assertRaisesRegex(ValueError, "calibration ratio"):
            replace(
                grid,
                standard_error_to_empirical_sd_ratio=(
                    grid.standard_error_to_empirical_sd_ratio + 0.001
                ),
            )
        scenario = report.scenario_inference[0]
        comparison = scenario.closure_comparison[0]
        changed_comparison = replace(
            comparison,
            exact_equivalence_met=not comparison.exact_equivalence_met,
        )
        with self.assertRaisesRegex(ValueError, "comparison changed"):
            replace(
                scenario,
                closure_comparison=(
                    changed_comparison,
                    *scenario.closure_comparison[1:],
                ),
            )

    def test_round_trip_unknown_fields_integrity_and_privacy(self) -> None:
        protocol_envelope = (
            clinical_outcome_pattern_mixture_uncertainty_protocol_envelope(
                self.public_protocol
            )
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_uncertainty_protocol_from_dict(
                protocol_envelope
            ),
            self.public_protocol,
        )
        report_envelope = clinical_outcome_pattern_mixture_uncertainty_report_envelope(
            self.public_report
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_uncertainty_report_from_dict(
                report_envelope
            ),
            self.public_report,
        )
        bad_integrity = copy.deepcopy(report_envelope)
        bad_integrity["integrity_sha256"] = "0" * 64
        with self.assertRaisesRegex(RecordParseError, "integrity mismatch"):
            clinical_outcome_pattern_mixture_uncertainty_report_from_dict(bad_integrity)
        unknown = copy.deepcopy(report_envelope)
        unknown["report"]["unexpected"] = True
        with self.assertRaisesRegex(RecordParseError, "unknown fields"):
            clinical_outcome_pattern_mixture_uncertainty_report_from_dict(unknown)
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_outcome_pattern_mixture_uncertainty_protocol_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )
        payload = json.dumps(report_envelope, sort_keys=True)
        self.assertNotIn("unit_id", payload)
        self.assertNotIn("cluster_id", payload)
        self.assertNotIn("labels_by_unit", payload)

    def test_cli_analyze_validate_and_summarize(self) -> None:
        protocol = _uncertainty_protocol(
            self.small_stress,
            self.small_pattern,
            self.small_pattern_report,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            protocol_path = temporary / "uncertainty_protocol.json"
            pattern_path = temporary / "pattern_protocol.json"
            stress_path = temporary / "stress_protocol.json"
            report_path = temporary / "uncertainty_report.json"
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_pattern_mixture_uncertainty_protocol_envelope(
                        protocol
                    )
                )
            )
            pattern_path.write_text(
                json.dumps(
                    clinical_outcome_pattern_mixture_protocol_envelope(
                        self.small_pattern
                    )
                )
            )
            stress_path.write_text(
                json.dumps(clinical_outcome_stress_protocol_envelope(self.small_stress))
            )
            analyze = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "analyze-pattern-mixture-uncertainty",
                    "--protocol",
                    str(protocol_path),
                    "--pattern-mixture-protocol",
                    str(pattern_path),
                    "--stress-protocol",
                    str(stress_path),
                    "--output",
                    str(report_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(analyze.returncode, 0, analyze.stderr)
            self.assertTrue(json.loads(analyze.stdout)["valid"])
            validate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "validate-pattern-mixture-uncertainty",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertEqual(
                json.loads(validate.stdout)["scope"],
                "integrity_and_aggregate_consistency",
            )
            summarize = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize-pattern-mixture-uncertainty",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(summarize.returncode, 0, summarize.stderr)
            self.assertEqual(
                json.loads(summarize.stdout)["schema_version"],
                "adds.clinical-outcome-pattern-mixture-uncertainty-summary.v1",
            )


if __name__ == "__main__":
    unittest.main()
