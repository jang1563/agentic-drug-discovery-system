from __future__ import annotations

import copy
import json
import math
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
    ClinicalOutcomePatternMixtureError,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomePatternMixtureStatus,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    RecordParseError,
    Stage,
    analyze_clinical_outcome_pattern_mixture,
    clinical_outcome_pattern_mixture_protocol_envelope,
    clinical_outcome_pattern_mixture_protocol_from_dict,
    clinical_outcome_pattern_mixture_protocol_from_json,
    clinical_outcome_pattern_mixture_report_envelope,
    clinical_outcome_pattern_mixture_report_from_dict,
    clinical_outcome_pattern_mixture_report_from_json,
    clinical_outcome_pattern_mixture_summary,
    clinical_outcome_stress_protocol_from_json,
    validate_clinical_outcome_pattern_mixture_report,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
PROTOCOL_SCHEMA = SPECS / "clinical_outcome_pattern_mixture_protocol.schema.json"
PROTOCOL_EXAMPLE = SPECS / "clinical_outcome_pattern_mixture_protocol.example.json"
REPORT_SCHEMA = SPECS / "clinical_outcome_pattern_mixture_report.schema.json"
REPORT_EXAMPLE = SPECS / "clinical_outcome_pattern_mixture_report.example.json"
SUMMARY_SCHEMA = SPECS / "clinical_outcome_pattern_mixture_summary.schema.json"
STRESS_PROTOCOL_EXAMPLE = (
    SPECS / "clinical_outcome_stress_simulation_protocol.example.json"
)


def _scenario(
    *,
    scenario_id: str = "informative",
    prevalence: float = 0.4,
    favorable_evaluable_probability: float = 0.9,
    unfavorable_evaluable_probability: float = 0.4,
    cluster_count: int = 8,
    cluster_size: int = 8,
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=(cluster_size,) * cluster_count,
        dependence_blocks=tuple((index,) for index in range(cluster_count)),
        favorable_prevalence=prevalence,
        dependence_block_intraclass_correlation=0.1,
        favorable_evaluable_probability=favorable_evaluable_probability,
        unfavorable_evaluable_probability=unfavorable_evaluable_probability,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
        policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
    )


def _stress_protocol(
    *,
    scenarios: tuple[ClinicalOutcomeStressScenario, ...] | None = None,
    replicates: int = 100,
    random_seed: int = 41,
) -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="pattern-mixture-stress-test",
        version="1.0.0",
        registered_on=date(2026, 8, 2),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=replicates,
        random_seed=random_seed,
        coverage_tolerance=0.1,
        minimum_interval_yield=0.5,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="candidate-g04-share50",
                minimum_evaluable_clusters=4,
                maximum_evaluable_cluster_fraction=0.5,
            ),
        ),
        scenarios=scenarios or (_scenario(),),
        metadata={"public_test": True},
    )


def _protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    *,
    grid: tuple[float, ...] = (-4.0, -2.197224577336, -1.0, 0.0, 1.0, 4.0),
    minimum_analyzable_rate: float = 0.5,
    maximum_absolute_bias: float = 0.08,
) -> ClinicalOutcomePatternMixtureProtocol:
    return ClinicalOutcomePatternMixtureProtocol(
        protocol_id="pattern-mixture-test",
        version="1.0.0",
        registered_on=date(2026, 8, 2),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        log_imor_grid=grid,
        monte_carlo_confidence_level=0.95,
        minimum_analyzable_rate=minimum_analyzable_rate,
        maximum_mean_identification_width=0.8,
        maximum_absolute_bias=maximum_absolute_bias,
        metadata={"public_test": True},
    )


def _metric(result, metric: ClinicalOutcomeDesignMetric):
    return next(item for item in result.metric_performance if item.metric is metric)


def _status_count(result, status: ClinicalOutcomePatternMixtureStatus) -> int:
    return next(item.count for item in result.status_counts if item.status is status)


class ClinicalOutcomePatternMixtureTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.public_stress_protocol = clinical_outcome_stress_protocol_from_json(
            STRESS_PROTOCOL_EXAMPLE.read_text()
        )
        cls.public_protocol = clinical_outcome_pattern_mixture_protocol_from_json(
            PROTOCOL_EXAMPLE.read_text()
        )
        cls.public_report = clinical_outcome_pattern_mixture_report_from_json(
            REPORT_EXAMPLE.read_text()
        )

    def test_examples_schemas_summary_and_exact_replay_are_synchronized(self) -> None:
        Draft202012Validator(
            json.loads(PROTOCOL_SCHEMA.read_text()),
            format_checker=FormatChecker(),
        ).validate(json.loads(PROTOCOL_EXAMPLE.read_text()))
        Draft202012Validator(
            json.loads(REPORT_SCHEMA.read_text()),
            format_checker=FormatChecker(),
        ).validate(json.loads(REPORT_EXAMPLE.read_text()))
        summary = clinical_outcome_pattern_mixture_summary(self.public_report)
        Draft202012Validator(json.loads(SUMMARY_SCHEMA.read_text())).validate(summary)

        rebuilt = analyze_clinical_outcome_pattern_mixture(
            self.public_protocol,
            self.public_stress_protocol,
        )
        self.assertEqual(rebuilt, self.public_report)
        self.assertEqual(
            self.public_protocol.fingerprint,
            "0ff618274428cdd9db271b0f361bfa18c9334852bbcbc3f4bc0af1405f2ea3e2",
        )
        self.assertEqual(
            rebuilt.fingerprint,
            "6a9376fb5c64fb449ee0972ea95430db780dfa6d830bf065b5996cb71092094f",
        )
        self.assertTrue(summary["all_scenarios_research_targets_met"])

    def test_informative_evaluability_separates_estimand_and_recovers_truth(self) -> None:
        stress_protocol = _stress_protocol()
        report = analyze_clinical_outcome_pattern_mixture(
            _protocol(stress_protocol),
            stress_protocol,
        )
        result = report.scenario_results[0]
        favorable = _metric(
            result,
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        expected_imor = 0.4 * 0.1 / (0.9 * 0.6)
        self.assertEqual(
            result.true_informative_missingness_odds_ratio,
            round(expected_imor, 12),
        )
        self.assertEqual(result.true_log_imor, round(math.log(expected_imor), 12))
        observed_prevalence = result.evaluable_favorable_prevalence
        odds_multiplier = math.exp(result.true_log_imor)
        missing_prevalence = (
            odds_multiplier * observed_prevalence
            / (1.0 - observed_prevalence + odds_multiplier * observed_prevalence)
        )
        analytically_recovered_prevalence = (
            result.expected_evaluable_probability * observed_prevalence
            + (1.0 - result.expected_evaluable_probability) * missing_prevalence
        )
        self.assertAlmostEqual(
            analytically_recovered_prevalence,
            result.population_favorable_prevalence,
            places=11,
        )
        self.assertTrue(result.grid_brackets_true_log_imor)
        self.assertGreater(abs(favorable.naive_population_bias), 0.1)
        self.assertLess(abs(favorable.naive_evaluable_bias), 0.08)
        self.assertLess(abs(favorable.truth_aligned_population_bias), 0.08)
        self.assertTrue(favorable.population_truth_recovered_by_mean_envelope)
        self.assertTrue(result.research_target_met)

        favorable_curve = tuple(
            item.mean_estimate for item in favorable.grid_performance
        )
        self.assertTrue(all(value is not None for value in favorable_curve))
        self.assertEqual(favorable_curve, tuple(sorted(favorable_curve)))

    def test_repeated_prediction_pairs_are_analyzed_as_one_stratum(self) -> None:
        repeated = replace(
            _scenario(cluster_count=2, cluster_size=4),
            policy_a_probability_pattern=(0.4, 0.4, 0.4, 0.4),
            policy_b_probability_pattern=(0.6, 0.6, 0.6, 0.6),
        )
        stress_protocol = _stress_protocol(
            scenarios=(repeated,),
            replicates=100,
            random_seed=19,
        )
        result = analyze_clinical_outcome_pattern_mixture(
            _protocol(stress_protocol, minimum_analyzable_rate=0.1),
            stress_protocol,
        ).scenario_results[0]
        self.assertEqual(
            _status_count(result, ClinicalOutcomePatternMixtureStatus.COMPUTED),
            83,
        )
        self.assertEqual(
            _status_count(
                result,
                ClinicalOutcomePatternMixtureStatus.EMPTY_REFERENCE_STRATUM,
            ),
            0,
        )
        self.assertEqual(
            _status_count(
                result,
                ClinicalOutcomePatternMixtureStatus.DEGENERATE_REFERENCE_STRATUM,
            ),
            17,
        )

    def test_grid_excluding_true_shift_fails_population_identification_only(self) -> None:
        stress_protocol = _stress_protocol()
        report = analyze_clinical_outcome_pattern_mixture(
            _protocol(stress_protocol, grid=(0.0, 0.5, 1.0)),
            stress_protocol,
        )
        result = report.scenario_results[0]
        favorable = _metric(
            result,
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        self.assertFalse(result.grid_brackets_true_log_imor)
        self.assertTrue(result.all_evaluable_calibration_targets_met)
        self.assertTrue(result.all_truth_aligned_recovery_targets_met)
        self.assertFalse(favorable.population_truth_recovered_by_mean_envelope)
        self.assertFalse(result.research_target_met)

    def test_mcar_reference_has_zero_log_imor_and_aligned_estimands(self) -> None:
        stress_protocol = _stress_protocol(
            scenarios=(
                _scenario(
                    scenario_id="mcar",
                    favorable_evaluable_probability=0.7,
                    unfavorable_evaluable_probability=0.7,
                ),
            )
        )
        result = analyze_clinical_outcome_pattern_mixture(
            _protocol(stress_protocol),
            stress_protocol,
        ).scenario_results[0]
        favorable = _metric(
            result,
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        self.assertEqual(result.true_log_imor, 0.0)
        self.assertEqual(result.true_informative_missingness_odds_ratio, 1.0)
        self.assertEqual(favorable.population_true_value, favorable.evaluable_true_value)
        self.assertEqual(
            favorable.naive_population_bias,
            favorable.naive_evaluable_bias,
        )

    def test_partial_strata_with_one_observed_class_fail_closed(self) -> None:
        stress_protocol = _stress_protocol(
            scenarios=(
                _scenario(
                    scenario_id="sparse",
                    prevalence=0.01,
                    favorable_evaluable_probability=0.7,
                    unfavorable_evaluable_probability=0.7,
                    cluster_count=2,
                    cluster_size=4,
                ),
            )
        )
        result = analyze_clinical_outcome_pattern_mixture(
            _protocol(stress_protocol, minimum_analyzable_rate=1.0),
            stress_protocol,
        ).scenario_results[0]
        self.assertGreater(
            _status_count(
                result,
                ClinicalOutcomePatternMixtureStatus.DEGENERATE_REFERENCE_STRATUM,
            ),
            0,
        )
        self.assertLess(result.analyzable_rate.rate, 1.0)
        self.assertFalse(result.analyzable_target_met)
        self.assertFalse(result.research_target_met)

    def test_boundary_evaluability_is_rejected_for_finite_log_imor(self) -> None:
        stress_protocol = _stress_protocol(
            scenarios=(
                _scenario(
                    favorable_evaluable_probability=1.0,
                    unfavorable_evaluable_probability=0.5,
                ),
            )
        )
        with self.assertRaisesRegex(
            ClinicalOutcomePatternMixtureError,
            "strictly interior evaluability probabilities",
        ):
            analyze_clinical_outcome_pattern_mixture(
                _protocol(stress_protocol),
                stress_protocol,
            )

    def test_protocol_requires_canonical_grid_mar_reference_and_safe_metadata(self) -> None:
        stress_protocol = _stress_protocol()
        with self.assertRaisesRegex(ValueError, "unique increasing"):
            _protocol(stress_protocol, grid=(0.0, -1.0, 1.0))
        with self.assertRaisesRegex(ValueError, "MAR reference"):
            _protocol(stress_protocol, grid=(-2.0, -1.0, 1.0))
        with self.assertRaisesRegex(ValueError, "evaluator outcomes"):
            replace(_protocol(stress_protocol), metadata={"hidden_label": "x"})

    def test_exact_stress_binding_and_workflow_replay_fail_closed(self) -> None:
        stress_protocol = _stress_protocol()
        protocol = _protocol(stress_protocol)
        other_stress_protocol = replace(stress_protocol, random_seed=42)
        with self.assertRaisesRegex(
            ClinicalOutcomePatternMixtureError,
            "not bound",
        ):
            analyze_clinical_outcome_pattern_mixture(
                protocol,
                other_stress_protocol,
            )
        report = analyze_clinical_outcome_pattern_mixture(
            protocol,
            stress_protocol,
        )
        self.assertEqual(
            validate_clinical_outcome_pattern_mixture_report(
                report,
                protocol,
                stress_protocol,
            ),
            (),
        )
        self.assertEqual(
            validate_clinical_outcome_pattern_mixture_report(
                report,
                protocol,
                other_stress_protocol,
            ),
            ("pattern_mixture_replay_failed",),
        )

    def test_round_trip_integrity_unknown_fields_and_claim_tamper(self) -> None:
        envelope = clinical_outcome_pattern_mixture_report_envelope(
            self.public_report
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_report_from_dict(envelope),
            self.public_report,
        )
        bad_integrity = copy.deepcopy(envelope)
        bad_integrity["integrity_sha256"] = "0" * 64
        with self.assertRaisesRegex(RecordParseError, "integrity mismatch"):
            clinical_outcome_pattern_mixture_report_from_dict(bad_integrity)
        unknown = copy.deepcopy(envelope)
        unknown["report"]["unexpected"] = True
        with self.assertRaisesRegex(RecordParseError, "unknown fields"):
            clinical_outcome_pattern_mixture_report_from_dict(unknown)
        claim_tamper = copy.deepcopy(envelope)
        claim_tamper["report"]["operational_estimate_uses_latent_truth"] = True
        with self.assertRaisesRegex(ValueError, "claim boundary"):
            clinical_outcome_pattern_mixture_report_from_dict(claim_tamper)
        with self.assertRaisesRegex(ValueError, "analyzable target"):
            replace(self.public_report, minimum_analyzable_rate=1.0)

    def test_protocol_round_trip_and_duplicate_json_keys(self) -> None:
        envelope = clinical_outcome_pattern_mixture_protocol_envelope(
            self.public_protocol
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_protocol_from_dict(envelope),
            self.public_protocol,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_outcome_pattern_mixture_protocol_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )

    def test_report_is_aggregate_and_contains_no_unit_or_cluster_roster(self) -> None:
        payload = json.dumps(
            clinical_outcome_pattern_mixture_report_envelope(self.public_report),
            sort_keys=True,
        )
        self.assertNotIn("unit_id", payload)
        self.assertNotIn("cluster_id", payload)
        self.assertNotIn("labels_by_unit", payload)
        self.assertFalse(self.public_report.unit_level_records_included)
        self.assertFalse(self.public_report.replicate_level_records_included)
        self.assertFalse(self.public_report.operational_estimate_uses_latent_truth)

    def test_cli_analyze_validate_and_summarize(self) -> None:
        stress_protocol = _stress_protocol()
        protocol = _protocol(stress_protocol)
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            protocol_path = temporary / "protocol.json"
            stress_path = temporary / "stress.json"
            report_path = temporary / "report.json"
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_pattern_mixture_protocol_envelope(protocol)
                )
            )
            from agentic_drug_discovery import clinical_outcome_stress_protocol_envelope

            stress_path.write_text(
                json.dumps(clinical_outcome_stress_protocol_envelope(stress_protocol))
            )
            analyze = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "analyze-pattern-mixture",
                    "--protocol",
                    str(protocol_path),
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
                    "validate-pattern-mixture",
                    "--report",
                    str(report_path),
                    "--protocol",
                    str(protocol_path),
                    "--stress-protocol",
                    str(stress_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertEqual(
                json.loads(validate.stdout)["scope"],
                "full_protocol_and_seeded_stress_replay",
            )
            summarize = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize-pattern-mixture",
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
                "adds.clinical-outcome-pattern-mixture-summary.v1",
            )


if __name__ == "__main__":
    unittest.main()
