from __future__ import annotations

import copy
import json
import random
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
    ClinicalOutcomeDesignScenario,
    ClinicalOutcomeDesignSimulationError,
    ClinicalOutcomeDesignSimulationProtocol,
    ClusterInferenceStatus,
    RecordParseError,
    Stage,
    clinical_outcome_design_protocol_envelope,
    clinical_outcome_design_protocol_from_dict,
    clinical_outcome_design_protocol_from_json,
    clinical_outcome_design_report_envelope,
    clinical_outcome_design_report_from_dict,
    clinical_outcome_design_report_from_json,
    clinical_outcome_design_simulation_summary,
    clinical_outcome_design_simulation_validation_summary,
    simulate_clinical_outcome_uncertainty_design,
    validate_clinical_outcome_design_simulation_report,
)
from agentic_drug_discovery.clinical_outcome_design_simulation import (
    _draw_beta_binomial_label,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
PROTOCOL_SCHEMA = SPECS / "clinical_outcome_design_simulation_protocol.schema.json"
PROTOCOL_EXAMPLE = SPECS / "clinical_outcome_design_simulation_protocol.example.json"
REPORT_SCHEMA = SPECS / "clinical_outcome_design_simulation_report.schema.json"
REPORT_EXAMPLE = SPECS / "clinical_outcome_design_simulation_report.example.json"
SUMMARY_SCHEMA = SPECS / "clinical_outcome_design_simulation_summary.schema.json"


def _protocol(
    *,
    protocol_id: str = "synthetic-design-test",
    replicates: int = 100,
    random_seed: int = 17,
    gates: tuple[ClinicalOutcomeDesignGate, ...] | None = None,
    scenarios: tuple[ClinicalOutcomeDesignScenario, ...] | None = None,
) -> ClinicalOutcomeDesignSimulationProtocol:
    return ClinicalOutcomeDesignSimulationProtocol(
        protocol_id=protocol_id,
        version="1.0.0",
        registered_on=date(2026, 8, 2),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=replicates,
        random_seed=random_seed,
        coverage_tolerance=0.08,
        minimum_interval_yield=0.8,
        gates=gates
        or (
            ClinicalOutcomeDesignGate(
                gate_id="candidate-g04-share50",
                minimum_evaluable_clusters=4,
                maximum_evaluable_cluster_fraction=0.5,
            ),
        ),
        scenarios=scenarios
        or (
            ClinicalOutcomeDesignScenario(
                scenario_id="balanced-eight",
                stage=Stage.CLINICAL_STRATEGY,
                endpoint_family="composite_benefit_risk",
                cluster_sizes=(4,) * 8,
                favorable_prevalence=0.4,
                intracluster_correlation=0.1,
                evaluable_probability=1.0,
                classification_threshold=0.5,
                policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
                policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
            ),
        ),
        metadata={"public_example": True},
    )


def _status_count(values, status: ClusterInferenceStatus) -> int:
    return next(item.count for item in values if item.status is status)


class ClinicalOutcomeDesignSimulationTests(unittest.TestCase):
    maxDiff = None

    def test_polya_urn_generator_recovers_declared_marginal_and_icc(self) -> None:
        prevalence = 0.3
        correlation = 0.25
        rng = random.Random(918273)
        pairs: list[tuple[float, float]] = []
        for _ in range(40_000):
            first = _draw_beta_binomial_label(rng, prevalence, correlation, 0, 0)
            second = _draw_beta_binomial_label(
                rng,
                prevalence,
                correlation,
                int(first),
                1,
            )
            pairs.append((first, second))

        mean_first = sum(first for first, _ in pairs) / len(pairs)
        mean_second = sum(second for _, second in pairs) / len(pairs)
        cross_mean = sum(first * second for first, second in pairs) / len(pairs)
        empirical_correlation = (
            cross_mean - mean_first * mean_second
        ) / (
            (mean_first * (1 - mean_first) * mean_second * (1 - mean_second))
            ** 0.5
        )

        self.assertAlmostEqual(mean_first, prevalence, delta=0.01)
        self.assertAlmostEqual(mean_second, prevalence, delta=0.01)
        self.assertAlmostEqual(empirical_correlation, correlation, delta=0.02)

    def test_examples_schemas_analytic_truths_and_replay_are_synchronized(self) -> None:
        protocol_payload = json.loads(PROTOCOL_EXAMPLE.read_text())
        report_payload = json.loads(REPORT_EXAMPLE.read_text())
        protocol_schema = json.loads(PROTOCOL_SCHEMA.read_text())
        report_schema = json.loads(REPORT_SCHEMA.read_text())
        summary_schema = json.loads(SUMMARY_SCHEMA.read_text())
        Draft202012Validator(
            protocol_schema,
            format_checker=FormatChecker(),
        ).validate(protocol_payload)
        Draft202012Validator(
            report_schema,
            format_checker=FormatChecker(),
        ).validate(report_payload)

        protocol = clinical_outcome_design_protocol_from_json(
            PROTOCOL_EXAMPLE.read_text()
        )
        report = clinical_outcome_design_report_from_json(REPORT_EXAMPLE.read_text())
        self.assertEqual(
            clinical_outcome_design_protocol_envelope(protocol),
            protocol_payload,
        )
        self.assertEqual(clinical_outcome_design_report_envelope(report), report_payload)
        self.assertEqual(
            simulate_clinical_outcome_uncertainty_design(protocol),
            report,
        )
        self.assertEqual(
            validate_clinical_outcome_design_simulation_report(report, protocol),
            (),
        )

        summary = clinical_outcome_design_simulation_summary(report)
        validation = clinical_outcome_design_simulation_validation_summary(report)
        validator = Draft202012Validator(
            summary_schema,
            format_checker=FormatChecker(),
        )
        validator.validate(summary)
        validator.validate(validation)
        invalid_summary = copy.deepcopy(summary)
        invalid_summary["scenarios"][0]["iid_reference"]["metrics"][0][
            "root_mean_squared_error"
        ] = -0.1
        self.assertTrue(list(validator.iter_errors(invalid_summary)))
        self.assertEqual(summary["scenario_count"], 3)
        self.assertEqual(summary["scenario_gate_pair_count"], 6)
        self.assertEqual(summary["target_met_scenario_gate_pair_count"], 2)
        self.assertFalse(summary["automatic_gate_selection_included"])

        first = report.scenario_results[0]
        truth_by_metric = {
            item.metric: item.true_value for item in first.iid_metric_performance
        }
        self.assertEqual(
            truth_by_metric,
            {
                ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE: 0.35,
                ClinicalOutcomeDesignMetric.POLICY_A_BRIER_SCORE: 0.3,
                ClinicalOutcomeDesignMetric.POLICY_B_BRIER_SCORE: 0.34,
                ClinicalOutcomeDesignMetric.POLICY_A_CALIBRATION_IN_THE_LARGE: 0.15,
                ClinicalOutcomeDesignMetric.POLICY_B_CALIBRATION_IN_THE_LARGE: 0.25,
                ClinicalOutcomeDesignMetric.POLICY_A_CLASSIFICATION_ACCURACY: 0.5,
                ClinicalOutcomeDesignMetric.POLICY_B_CLASSIFICATION_ACCURACY: 0.425,
                ClinicalOutcomeDesignMetric.BRIER_DIFFERENCE_B_MINUS_A: 0.04,
            },
        )
        serialized = json.dumps(report_payload, sort_keys=True)
        self.assertNotIn("cluster-000000", serialized)
        self.assertNotIn(":unit-", serialized)
        self.assertFalse(report.replicate_level_records_included)
        self.assertFalse(report.unit_level_records_included)
        self.assertFalse(report.real_clinical_outcomes_included)

    def test_high_icc_exposes_iid_undercoverage_and_cr1_recovers_width(self) -> None:
        scenario = ClinicalOutcomeDesignScenario(
            scenario_id="high-icc",
            stage=Stage.CLINICAL_STRATEGY,
            endpoint_family="composite_benefit_risk",
            cluster_sizes=(8,) * 30,
            favorable_prevalence=0.4,
            intracluster_correlation=0.2,
            evaluable_probability=1.0,
            classification_threshold=0.5,
            policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
            policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
        )
        protocol = _protocol(
            protocol_id="high-icc-coverage",
            replicates=400,
            random_seed=1122,
            gates=(
                ClinicalOutcomeDesignGate(
                    gate_id="candidate-g20-share10",
                    minimum_evaluable_clusters=20,
                    maximum_evaluable_cluster_fraction=0.1,
                ),
            ),
            scenarios=(scenario,),
        )
        report = simulate_clinical_outcome_uncertainty_design(protocol)
        result = report.scenario_results[0]
        iid = result.iid_metric_performance[0]
        clustered = result.gate_performance[0].metric_performance[0]

        self.assertEqual(iid.metric, ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE)
        self.assertLess(iid.coverage.rate, 0.85)
        self.assertGreater(clustered.coverage.rate, 0.93)
        self.assertGreater(clustered.coverage.rate, iid.coverage.rate + 0.12)
        self.assertGreater(clustered.mean_interval_width, iid.mean_interval_width)
        self.assertGreater(clustered.mean_se_to_empirical_sd_ratio, 0.85)
        self.assertLess(iid.mean_se_to_empirical_sd_ratio, 0.75)
        self.assertTrue(result.gate_performance[0].design_target_met)
        self.assertEqual(
            validate_clinical_outcome_design_simulation_report(report, protocol),
            (),
        )
        self.assertEqual(
            simulate_clinical_outcome_uncertainty_design(protocol).fingerprint,
            report.fingerprint,
        )

    def test_scenario_stream_is_stable_when_roster_and_gates_expand(self) -> None:
        base_protocol = _protocol(
            protocol_id="stream-stability-base",
            random_seed=321,
        )
        base_scenario = base_protocol.scenarios[0]
        expanded_protocol = _protocol(
            protocol_id="stream-stability-expanded",
            random_seed=321,
            gates=(
                base_protocol.gates[0],
                ClinicalOutcomeDesignGate(
                    gate_id="candidate-g08-share25",
                    minimum_evaluable_clusters=8,
                    maximum_evaluable_cluster_fraction=0.25,
                ),
            ),
            scenarios=(
                base_scenario,
                replace(
                    base_scenario,
                    scenario_id="later-regulatory-scenario",
                    stage=Stage.REGULATORY_POSTMARKET,
                ),
            ),
        )

        base_result = simulate_clinical_outcome_uncertainty_design(
            base_protocol
        ).scenario_results[0]
        expanded_result = simulate_clinical_outcome_uncertainty_design(
            expanded_protocol
        ).scenario_results[0]

        self.assertEqual(base_result.rng_stream_sha256, expanded_result.rng_stream_sha256)
        self.assertEqual(base_result.replicate_diagnostics, expanded_result.replicate_diagnostics)
        self.assertEqual(base_result.iid_metric_performance, expanded_result.iid_metric_performance)
        self.assertEqual(base_result.gate_performance[0], expanded_result.gate_performance[0])

    def test_cluster_floor_dominance_and_empty_attrition_are_distinct(self) -> None:
        gates = (
            ClinicalOutcomeDesignGate(
                gate_id="candidate-g04-share50",
                minimum_evaluable_clusters=4,
                maximum_evaluable_cluster_fraction=0.5,
            ),
            ClinicalOutcomeDesignGate(
                gate_id="candidate-g08-share25",
                minimum_evaluable_clusters=8,
                maximum_evaluable_cluster_fraction=0.25,
            ),
        )
        common = {
            "stage": Stage.CLINICAL_STRATEGY,
            "endpoint_family": "composite_benefit_risk",
            "favorable_prevalence": 0.4,
            "intracluster_correlation": 0.1,
            "evaluable_probability": 1.0,
            "classification_threshold": 0.5,
            "policy_a_probability_pattern": (0.2, 0.4, 0.6, 0.8),
            "policy_b_probability_pattern": (0.3, 0.5, 0.7, 0.9),
        }
        scenarios = (
            ClinicalOutcomeDesignScenario(
                scenario_id="balanced-eight",
                cluster_sizes=(4,) * 8,
                **common,
            ),
            ClinicalOutcomeDesignScenario(
                scenario_id="balanced-six",
                cluster_sizes=(4,) * 6,
                **common,
            ),
            ClinicalOutcomeDesignScenario(
                scenario_id="dominant-eight",
                cluster_sizes=(20,) + (4,) * 7,
                **common,
            ),
        )
        report = simulate_clinical_outcome_uncertainty_design(
            _protocol(gates=gates, scenarios=scenarios)
        )
        by_id = {item.scenario.scenario_id: item for item in report.scenario_results}
        six_strict = by_id["balanced-six"].gate_performance[1]
        eight_strict = by_id["balanced-eight"].gate_performance[1]
        dominant_strict = by_id["dominant-eight"].gate_performance[1]
        self.assertEqual(
            _status_count(
                six_strict.diagnostic_status_counts,
                ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
            ),
            100,
        )
        self.assertEqual(eight_strict.diagnostic_interval_eligibility.event_count, 100)
        self.assertEqual(
            _status_count(
                dominant_strict.diagnostic_status_counts,
                ClusterInferenceStatus.DOMINANT_CLUSTER,
            ),
            100,
        )
        self.assertEqual(six_strict.metric_performance[0].interval_count, 0)
        self.assertEqual(dominant_strict.metric_performance[0].interval_count, 0)

        empty_scenario = ClinicalOutcomeDesignScenario(
            scenario_id="mcar-near-empty",
            stage=Stage.CLINICAL_STRATEGY,
            endpoint_family="composite_benefit_risk",
            cluster_sizes=(2, 2),
            favorable_prevalence=0.4,
            intracluster_correlation=0.1,
            evaluable_probability=1e-12,
            classification_threshold=0.5,
            policy_a_probability_pattern=(0.2, 0.8),
            policy_b_probability_pattern=(0.3, 0.7),
        )
        empty = simulate_clinical_outcome_uncertainty_design(
            _protocol(
                protocol_id="near-empty-mcar",
                random_seed=5,
                gates=(
                    ClinicalOutcomeDesignGate(
                        gate_id="candidate-g02-share90",
                        minimum_evaluable_clusters=2,
                        maximum_evaluable_cluster_fraction=0.9,
                    ),
                ),
                scenarios=(empty_scenario,),
            )
        ).scenario_results[0]
        self.assertEqual(empty.replicate_diagnostics.no_evaluable_replicates, 100)
        metric = empty.iid_metric_performance[0]
        self.assertEqual(metric.point_estimate_count, 0)
        self.assertIsNone(metric.mean_estimate)
        self.assertIsNone(metric.coverage.rate)
        self.assertEqual(
            _status_count(
                metric.status_counts,
                ClusterInferenceStatus.NO_EVALUABLE_UNITS,
            ),
            100,
        )

    def test_strict_readers_reject_tampering_nonfinite_and_unbounded_work(self) -> None:
        protocol_payload = json.loads(PROTOCOL_EXAMPLE.read_text())
        report_payload = json.loads(REPORT_EXAMPLE.read_text())

        tampered = copy.deepcopy(protocol_payload)
        tampered["protocol"]["unexpected"] = True
        with self.assertRaises(RecordParseError):
            clinical_outcome_design_protocol_from_dict(tampered)

        tampered = copy.deepcopy(protocol_payload)
        tampered["protocol"]["random_seed"] += 1
        with self.assertRaises(RecordParseError):
            clinical_outcome_design_protocol_from_dict(tampered)

        tampered_report = copy.deepcopy(report_payload)
        tampered_report["report"]["scenario_results"][0][
            "iid_metric_performance"
        ][0]["true_value"] = 0.36
        tampered_report["integrity_sha256"] = "0" * 64
        with self.assertRaises((RecordParseError, ValueError)):
            clinical_outcome_design_report_from_dict(tampered_report)

        duplicate = '{"schema_version":"x","schema_version":"y"}'
        with self.assertRaises(RecordParseError):
            clinical_outcome_design_protocol_from_json(duplicate)
        nonfinite = PROTOCOL_EXAMPLE.read_text().replace(
            '"confidence_level": 0.95',
            '"confidence_level": NaN',
            1,
        )
        with self.assertRaises(RecordParseError):
            clinical_outcome_design_protocol_from_json(nonfinite)

        with self.assertRaises(ValueError):
            ClinicalOutcomeDesignScenario(
                scenario_id="bad-pattern",
                stage=Stage.CLINICAL_STRATEGY,
                endpoint_family="x",
                cluster_sizes=(3, 2),
                favorable_prevalence=0.4,
                intracluster_correlation=0.1,
                evaluable_probability=0.9,
                classification_threshold=0.5,
                policy_a_probability_pattern=(0.2, 0.8),
                policy_b_probability_pattern=(0.3, 0.7),
            )

        huge = ClinicalOutcomeDesignScenario(
            scenario_id="bounded-work",
            stage=Stage.CLINICAL_STRATEGY,
            endpoint_family="x",
            cluster_sizes=(50_000, 50_000),
            favorable_prevalence=0.4,
            intracluster_correlation=0.1,
            evaluable_probability=0.9,
            classification_threshold=0.5,
            policy_a_probability_pattern=(0.2,),
            policy_b_probability_pattern=(0.3,),
        )
        with self.assertRaises(ClinicalOutcomeDesignSimulationError):
            _protocol(
                gates=(
                    ClinicalOutcomeDesignGate("g2-share50", 2, 0.5),
                    ClinicalOutcomeDesignGate("g2-share60", 2, 0.6),
                ),
                scenarios=(huge,),
            )

        protocol = clinical_outcome_design_protocol_from_json(
            PROTOCOL_EXAMPLE.read_text()
        )
        report = clinical_outcome_design_report_from_json(REPORT_EXAMPLE.read_text())
        changed = replace(protocol, random_seed=protocol.random_seed + 1)
        self.assertEqual(
            validate_clinical_outcome_design_simulation_report(report, changed),
            ("recompiled_clinical_outcome_design_simulation_report_mismatch",),
        )

    def test_cli_simulate_validate_summarize_and_atomic_output(self) -> None:
        protocol = _protocol()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = root / "protocol.json"
            report_path = root / "report.json"
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_design_protocol_envelope(protocol),
                    indent=2,
                    sort_keys=True,
                )
            )
            command = (
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
                "simulate-uncertainty-design",
                "--protocol",
                str(protocol_path),
                "--output",
                str(report_path),
            )
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(report_path.is_file())
            validation = json.loads(completed.stdout)
            self.assertEqual(validation["validation"]["status"], "valid")
            original = report_path.read_bytes()

            refused = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(report_path.read_bytes(), original)

            for extra in (
                (),
                ("--protocol", str(protocol_path)),
            ):
                validated = subprocess.run(
                    (
                        sys.executable,
                        "-m",
                        "agentic_drug_discovery.clinical_decision_cli",
                        "validate-uncertainty-design",
                        "--report",
                        str(report_path),
                        *extra,
                    ),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(validated.returncode, 0, validated.stderr)
                self.assertEqual(
                    json.loads(validated.stdout)["validation"]["status"],
                    "valid",
                )

            summarized = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize-uncertainty-design",
                    "--report",
                    str(report_path),
                ),
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            summary = json.loads(summarized.stdout)
            self.assertEqual(summary["scenario_count"], 1)
            self.assertNotIn("validation", summary)

            forced = subprocess.run(
                (*command, "--force"),
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)


if __name__ == "__main__":
    unittest.main()
