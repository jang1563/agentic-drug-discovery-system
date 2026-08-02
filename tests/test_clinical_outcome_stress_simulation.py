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
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationError,
    ClinicalOutcomeStressSimulationProtocol,
    ClusterInferenceStatus,
    RecordParseError,
    Stage,
    clinical_outcome_stress_protocol_envelope,
    clinical_outcome_stress_protocol_from_dict,
    clinical_outcome_stress_protocol_from_json,
    clinical_outcome_stress_report_envelope,
    clinical_outcome_stress_report_from_dict,
    clinical_outcome_stress_report_from_json,
    clinical_outcome_stress_simulation_summary,
    simulate_clinical_outcome_stress,
    validate_clinical_outcome_stress_simulation_report,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
PROTOCOL_SCHEMA = SPECS / "clinical_outcome_stress_simulation_protocol.schema.json"
PROTOCOL_EXAMPLE = SPECS / "clinical_outcome_stress_simulation_protocol.example.json"
REPORT_SCHEMA = SPECS / "clinical_outcome_stress_simulation_report.schema.json"
REPORT_EXAMPLE = SPECS / "clinical_outcome_stress_simulation_report.example.json"
SUMMARY_SCHEMA = SPECS / "clinical_outcome_stress_simulation_summary.schema.json"


def _singleton_blocks(count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index,) for index in range(count))


def _paired_blocks(count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index, index + 1) for index in range(0, count, 2))


def _scenario(
    *,
    scenario_id: str = "synthetic-stress",
    cluster_count: int = 8,
    cluster_size: int = 4,
    dependence_blocks: tuple[tuple[int, ...], ...] | None = None,
    prevalence: float = 0.4,
    correlation: float = 0.1,
    favorable_evaluable_probability: float = 0.9,
    unfavorable_evaluable_probability: float = 0.5,
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=(cluster_size,) * cluster_count,
        dependence_blocks=dependence_blocks or _singleton_blocks(cluster_count),
        favorable_prevalence=prevalence,
        dependence_block_intraclass_correlation=correlation,
        favorable_evaluable_probability=favorable_evaluable_probability,
        unfavorable_evaluable_probability=unfavorable_evaluable_probability,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
        policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
    )


def _protocol(
    *,
    protocol_id: str = "synthetic-stress-test",
    replicates: int = 100,
    random_seed: int = 19,
    gates: tuple[ClinicalOutcomeDesignGate, ...] | None = None,
    scenarios: tuple[ClinicalOutcomeStressScenario, ...] | None = None,
) -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id=protocol_id,
        version="1.0.0",
        registered_on=date(2026, 8, 2),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=replicates,
        random_seed=random_seed,
        coverage_tolerance=0.08,
        minimum_interval_yield=0.5,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=gates
        or (
            ClinicalOutcomeDesignGate(
                gate_id="candidate-g04-share50",
                minimum_evaluable_clusters=4,
                maximum_evaluable_cluster_fraction=0.5,
            ),
        ),
        scenarios=scenarios or (_scenario(),),
        metadata={"public_example": True},
    )


def _scenario_result(report, scenario_id: str):
    return next(
        item for item in report.scenario_results if item.scenario.scenario_id == scenario_id
    )


def _analysis(result, mode: ClinicalOutcomeStressAnalysisMode):
    return next(item for item in result.analysis_performance if item.analysis_mode is mode)


def _target(gate, target: ClinicalOutcomeStressEstimandTarget):
    return next(item for item in gate.target_performance if item.target is target)


def _metric(target, metric: ClinicalOutcomeDesignMetric):
    return next(item for item in target.metric_performance if item.metric is metric)


def _status_count(values, status: ClusterInferenceStatus) -> int:
    return next(item.count for item in values if item.status is status)


class ClinicalOutcomeStressSimulationTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.public_protocol = clinical_outcome_stress_protocol_from_json(
            PROTOCOL_EXAMPLE.read_text()
        )
        cls.public_report = clinical_outcome_stress_report_from_json(
            REPORT_EXAMPLE.read_text()
        )

    def test_examples_schemas_truths_and_exact_replay_are_synchronized(self) -> None:
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
        summary = clinical_outcome_stress_simulation_summary(self.public_report)
        Draft202012Validator(summary_schema).validate(summary)

        rebuilt = simulate_clinical_outcome_stress(self.public_protocol)
        self.assertEqual(rebuilt, self.public_report)
        self.assertEqual(
            rebuilt.fingerprint,
            "e9fc814c2432434bb3b7b739fa35abd55177116fe6086bfb30a386dc920ef19d",
        )
        self.assertEqual(
            validate_clinical_outcome_stress_simulation_report(
                self.public_report,
                self.public_protocol,
            ),
            (),
        )

    def test_analytic_evaluable_truth_and_identical_estimates(self) -> None:
        scenario = _scenario(
            prevalence=0.4,
            favorable_evaluable_probability=0.8,
            unfavorable_evaluable_probability=0.2,
        )
        self.assertEqual(scenario.expected_evaluable_probability, 0.44)
        self.assertEqual(scenario.evaluable_favorable_prevalence, 0.727272727273)
        result = simulate_clinical_outcome_stress(
            _protocol(scenarios=(scenario,))
        ).scenario_results[0]
        observed_truth = result.truth.metric_truths[0]
        self.assertEqual(observed_truth.population_value, 0.4)
        self.assertEqual(observed_truth.evaluable_value, 0.727272727273)
        self.assertEqual(observed_truth.evaluable_minus_population, 0.327272727273)

        gate = result.analysis_performance[0].gate_performance[0]
        population = _metric(
            _target(gate, ClinicalOutcomeStressEstimandTarget.POPULATION),
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        evaluable = _metric(
            _target(gate, ClinicalOutcomeStressEstimandTarget.EVALUABLE),
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        self.assertEqual(population.mean_estimate, evaluable.mean_estimate)
        self.assertEqual(population.interval_yield, evaluable.interval_yield)
        self.assertEqual(population.status_counts, evaluable.status_counts)
        self.assertNotEqual(population.bias, evaluable.bias)
        self.assertNotEqual(population.coverage, evaluable.coverage)

    def test_informative_evaluability_changes_estimand_not_cluster_mode(self) -> None:
        result = _scenario_result(
            self.public_report,
            "informative-evaluability-independent-nominal",
        )
        self.assertTrue(result.scenario.outcome_dependent_evaluability)
        self.assertFalse(result.scenario.cross_nominal_cluster_dependence)
        self.assertEqual(result.truth.population_favorable_prevalence, 0.35)
        self.assertEqual(result.truth.evaluable_favorable_prevalence, 0.518518518519)

        nominal = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS,
        )
        closed = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        )
        self.assertEqual(nominal.gate_performance, closed.gate_performance)
        for gate in nominal.gate_performance:
            self.assertFalse(
                _target(
                    gate,
                    ClinicalOutcomeStressEstimandTarget.POPULATION,
                ).design_target_met
            )
            self.assertTrue(
                _target(
                    gate,
                    ClinicalOutcomeStressEstimandTarget.EVALUABLE,
                ).design_target_met
            )

    def test_dependence_closure_recovers_hidden_linkage_under_mcar(self) -> None:
        result = _scenario_result(self.public_report, "hidden-linkage-mcar")
        self.assertFalse(result.scenario.outcome_dependent_evaluability)
        self.assertTrue(result.scenario.cross_nominal_cluster_dependence)
        self.assertEqual(result.truth.population_favorable_prevalence, 0.35)
        self.assertEqual(result.truth.evaluable_favorable_prevalence, 0.35)

        nominal_gate = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS,
        ).gate_performance[0]
        closed_gate = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        ).gate_performance[0]
        for target in ClinicalOutcomeStressEstimandTarget:
            self.assertFalse(_target(nominal_gate, target).design_target_met)
            self.assertTrue(_target(closed_gate, target).design_target_met)

        nominal_metric = _metric(
            _target(nominal_gate, ClinicalOutcomeStressEstimandTarget.POPULATION),
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        closed_metric = _metric(
            _target(closed_gate, ClinicalOutcomeStressEstimandTarget.POPULATION),
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        )
        self.assertEqual(nominal_metric.mean_estimate, closed_metric.mean_estimate)
        self.assertLess(
            nominal_metric.mean_reported_standard_error,
            closed_metric.mean_reported_standard_error,
        )
        self.assertLess(nominal_metric.coverage.rate, 0.87)
        self.assertGreater(closed_metric.coverage.rate, 0.9)

    def test_combined_stress_requires_closure_but_retains_population_bias(self) -> None:
        result = _scenario_result(
            self.public_report,
            "combined-informative-hidden-linkage",
        )
        nominal_gate = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS,
        ).gate_performance[0]
        closed_gate = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        ).gate_performance[0]
        self.assertFalse(
            _target(
                nominal_gate,
                ClinicalOutcomeStressEstimandTarget.POPULATION,
            ).design_target_met
        )
        self.assertFalse(
            _target(
                nominal_gate,
                ClinicalOutcomeStressEstimandTarget.EVALUABLE,
            ).design_target_met
        )
        self.assertFalse(
            _target(
                closed_gate,
                ClinicalOutcomeStressEstimandTarget.POPULATION,
            ).design_target_met
        )
        self.assertTrue(
            _target(
                closed_gate,
                ClinicalOutcomeStressEstimandTarget.EVALUABLE,
            ).design_target_met
        )

        summary = clinical_outcome_stress_simulation_summary(self.public_report)
        scenario_summary = next(
            item
            for item in summary["scenarios"]
            if item["scenario_id"] == "combined-informative-hidden-linkage"
        )
        self.assertEqual(
            scenario_summary["dependence_closure_recovery_gate_ids"]["population"],
            [],
        )
        self.assertEqual(
            scenario_summary["dependence_closure_recovery_gate_ids"]["evaluable"],
            ["exploratory-g08-share25", "balanced-g12-share15"],
        )

    def test_exact_partitions_modes_targets_and_claim_boundaries_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            replace(_scenario(), dependence_blocks=((0, 1), (1, 2), (3, 4, 5, 6, 7)))
        with self.assertRaises(ValueError):
            replace(_scenario(), dependence_blocks=((1, 0),) + _singleton_blocks(6))
        with self.assertRaises(ValueError):
            replace(_scenario(), dependence_blocks=((0, 8),) + _singleton_blocks(6))
        with self.assertRaises(ValueError):
            replace(_scenario(), dependence_blocks=_singleton_blocks(7))
        with self.assertRaises(ValueError):
            replace(
                _scenario(),
                favorable_evaluable_probability=0.0,
                unfavorable_evaluable_probability=0.0,
            )
        with self.assertRaises(ValueError):
            replace(
                _scenario(),
                favorable_evaluable_probability=1e-20,
                unfavorable_evaluable_probability=1e-20,
            )
        with self.assertRaises(ValueError):
            replace(
                _protocol(),
                analysis_modes=(ClinicalOutcomeStressAnalysisMode.NOMINAL_CLUSTERS,),
            )
        with self.assertRaises(ValueError):
            replace(
                _protocol(),
                estimand_targets=(ClinicalOutcomeStressEstimandTarget.POPULATION,),
            )
        with self.assertRaises(ValueError):
            replace(_protocol(), metadata={"outcome_labels": [1, 0]})
        with self.assertRaises(ValueError):
            replace(
                self.public_report,
                automatic_missingness_correction_included=True,
            )

    def test_oracle_closure_with_one_block_withholds_intervals(self) -> None:
        scenario = _scenario(
            cluster_count=4,
            dependence_blocks=((0, 1, 2, 3),),
            favorable_evaluable_probability=1.0,
            unfavorable_evaluable_probability=1.0,
        )
        result = simulate_clinical_outcome_stress(
            _protocol(
                gates=(ClinicalOutcomeDesignGate("candidate-g02-share90", 2, 0.9),),
                scenarios=(scenario,),
            )
        ).scenario_results[0]
        closed_gate = _analysis(
            result,
            ClinicalOutcomeStressAnalysisMode.DEPENDENCE_CLOSED_CLUSTERS,
        ).gate_performance[0]
        self.assertEqual(
            _status_count(
                closed_gate.diagnostic_status_counts,
                ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
            ),
            100,
        )
        self.assertEqual(
            closed_gate.diagnostic_interval_eligibility.event_count,
            0,
        )
        for target in closed_gate.target_performance:
            self.assertEqual(target.metric_performance[0].interval_count, 0)
            self.assertFalse(target.design_target_met)

    def test_strict_readers_reject_tampering_duplicates_nonfinite_and_work_overflow(
        self,
    ) -> None:
        protocol_payload = json.loads(PROTOCOL_EXAMPLE.read_text())
        report_payload = json.loads(REPORT_EXAMPLE.read_text())

        tampered = copy.deepcopy(protocol_payload)
        tampered["protocol"]["unexpected"] = True
        with self.assertRaises(RecordParseError):
            clinical_outcome_stress_protocol_from_dict(tampered)

        tampered = copy.deepcopy(protocol_payload)
        tampered["protocol"]["random_seed"] += 1
        with self.assertRaises(RecordParseError):
            clinical_outcome_stress_protocol_from_dict(tampered)

        tampered_report = copy.deepcopy(report_payload)
        tampered_report["report"]["scenario_results"][0]["truth"][
            "evaluable_favorable_prevalence"
        ] = 0.5
        tampered_report["integrity_sha256"] = "0" * 64
        with self.assertRaises((RecordParseError, ValueError)):
            clinical_outcome_stress_report_from_dict(tampered_report)

        tampered_report = copy.deepcopy(report_payload)
        tampered_report["report"]["scenario_results"][0][
            "outcome_rng_stream_sha256"
        ] = "0" * 64
        tampered_report["integrity_sha256"] = "0" * 64
        with self.assertRaises((RecordParseError, ValueError)):
            clinical_outcome_stress_report_from_dict(tampered_report)

        duplicate = '{"schema_version":"x","schema_version":"y"}'
        with self.assertRaises(RecordParseError):
            clinical_outcome_stress_protocol_from_json(duplicate)
        nonfinite = PROTOCOL_EXAMPLE.read_text().replace(
            '"confidence_level": 0.95',
            '"confidence_level": NaN',
            1,
        )
        with self.assertRaises(RecordParseError):
            clinical_outcome_stress_protocol_from_json(nonfinite)

        huge = ClinicalOutcomeStressScenario(
            scenario_id="bounded-work",
            stage=Stage.CLINICAL_STRATEGY,
            endpoint_family="x",
            nominal_cluster_sizes=(50_000, 50_000),
            dependence_blocks=((0,), (1,)),
            favorable_prevalence=0.4,
            dependence_block_intraclass_correlation=0.1,
            favorable_evaluable_probability=0.9,
            unfavorable_evaluable_probability=0.9,
            classification_threshold=0.5,
            policy_a_probability_pattern=(0.2,),
            policy_b_probability_pattern=(0.3,),
        )
        with self.assertRaises(ClinicalOutcomeStressSimulationError):
            _protocol(scenarios=(huge,))

        changed = replace(
            self.public_protocol,
            random_seed=self.public_protocol.random_seed + 1,
        )
        self.assertEqual(
            validate_clinical_outcome_stress_simulation_report(
                self.public_report,
                changed,
            ),
            ("recompiled_clinical_outcome_stress_simulation_report_mismatch",),
        )

    def test_aggregate_envelopes_exclude_unit_and_replicate_records(self) -> None:
        protocol_envelope = clinical_outcome_stress_protocol_envelope(
            self.public_protocol
        )
        report_envelope = clinical_outcome_stress_report_envelope(self.public_report)
        serialized_protocol = json.dumps(protocol_envelope, sort_keys=True)
        serialized_report = json.dumps(report_envelope, sort_keys=True)
        for forbidden in (
            "evidence_unit_id",
            "replicate_records",
            "unit_records",
            "automatic_gate_selection",
        ):
            self.assertNotIn(forbidden, serialized_protocol)
        self.assertNotIn("evidence_unit_id", serialized_report)
        self.assertNotIn("replicate_records", serialized_report)
        self.assertNotIn("unit_records", serialized_report)
        self.assertFalse(self.public_report.replicate_level_records_included)
        self.assertFalse(self.public_report.unit_level_records_included)
        self.assertFalse(self.public_report.real_clinical_outcomes_included)
        self.assertFalse(self.public_report.automatic_gate_selection_included)
        self.assertFalse(
            self.public_report.automatic_missingness_correction_included
        )

    def test_cli_simulate_validate_summarize_and_atomic_output(self) -> None:
        protocol = _protocol()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = root / "protocol.json"
            report_path = root / "report.json"
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_stress_protocol_envelope(protocol),
                    indent=2,
                    sort_keys=True,
                )
            )
            command = (
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
                "simulate-uncertainty-stress",
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
            self.assertEqual(
                json.loads(completed.stdout)["validation"]["status"],
                "valid",
            )
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

            for extra in ((), ("--protocol", str(protocol_path))):
                validated = subprocess.run(
                    (
                        sys.executable,
                        "-m",
                        "agentic_drug_discovery.clinical_decision_cli",
                        "validate-uncertainty-stress",
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
                    "summarize-uncertainty-stress",
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
