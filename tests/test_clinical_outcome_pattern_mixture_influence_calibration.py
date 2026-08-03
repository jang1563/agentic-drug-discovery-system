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
    ClinicalOutcomePatternMixtureInfluenceError,
    ClinicalOutcomePatternMixtureInfluenceProtocol,
    ClinicalOutcomePatternMixtureIntervalMethod,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    RecordParseError,
    Stage,
    analyze_clinical_outcome_pattern_mixture,
    analyze_clinical_outcome_pattern_mixture_influence_calibration,
    clinical_outcome_pattern_mixture_influence_calibration_summary,
    clinical_outcome_pattern_mixture_influence_protocol_envelope,
    clinical_outcome_pattern_mixture_influence_protocol_from_dict,
    clinical_outcome_pattern_mixture_influence_protocol_from_json,
    clinical_outcome_pattern_mixture_influence_report_envelope,
    clinical_outcome_pattern_mixture_influence_report_from_dict,
    clinical_outcome_pattern_mixture_influence_report_from_json,
    clinical_outcome_pattern_mixture_protocol_envelope,
    clinical_outcome_pattern_mixture_protocol_from_json,
    clinical_outcome_pattern_mixture_report_from_json,
    clinical_outcome_stress_protocol_envelope,
    clinical_outcome_stress_protocol_from_json,
    validate_clinical_outcome_pattern_mixture_influence_calibration_report,
)
from agentic_drug_discovery.clinical_outcome_pattern_mixture_influence_calibration import (
    _delete_mj_estimate_and_variance,
    _delete_one_variance,
    _linear_quantile,
    _student_t_cdf,
    _student_t_critical,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env" / "specs"
PUBLIC_STRESS_PROTOCOL = (
    SPECS / "clinical_outcome_pattern_mixture_influence_stress_protocol.example.json"
)
PUBLIC_PATTERN_PROTOCOL = (
    SPECS / "clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json"
)
PUBLIC_PATTERN_REPORT = (
    SPECS / "clinical_outcome_pattern_mixture_influence_pattern_report.example.json"
)
PUBLIC_PROTOCOL = (
    SPECS / "clinical_outcome_pattern_mixture_influence_protocol.example.json"
)
PUBLIC_REPORT = SPECS / "clinical_outcome_pattern_mixture_influence_report.example.json"
PUBLIC_SUMMARY = (
    SPECS / "clinical_outcome_pattern_mixture_influence_summary.example.json"
)


def _scenario(
    scenario_id: str,
    cluster_sizes: tuple[int, ...],
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=cluster_sizes,
        dependence_blocks=tuple((index,) for index in range(len(cluster_sizes))),
        favorable_prevalence=0.42,
        dependence_block_intraclass_correlation=0.15,
        favorable_evaluable_probability=0.9,
        unfavorable_evaluable_probability=0.55,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
        policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
    )


def _stress_protocol() -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="pattern-mixture-influence-stress-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=100,
        random_seed=197,
        coverage_tolerance=0.25,
        minimum_interval_yield=0.5,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="test-g08-share25",
                minimum_evaluable_clusters=8,
                maximum_evaluable_cluster_fraction=0.25,
            ),
        ),
        scenarios=(
            _scenario("balanced-eight", (8,) * 8),
            _scenario("dominant-cluster", (32,) + (8,) * 7),
            _scenario("unequal-eight", (16, 12, 12, 8, 8, 8, 4, 4)),
        ),
        metadata={"public_test": True},
    )


def _pattern_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomePatternMixtureProtocol:
    return ClinicalOutcomePatternMixtureProtocol(
        protocol_id="pattern-mixture-influence-pattern-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        log_imor_grid=(-1.0, 0.0, 1.0),
        monte_carlo_confidence_level=0.95,
        minimum_analyzable_rate=0.2,
        maximum_mean_identification_width=1.0,
        maximum_absolute_bias=0.2,
        metadata={"public_test": True},
    )


def _influence_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    pattern_report,
) -> ClinicalOutcomePatternMixtureInfluenceProtocol:
    return ClinicalOutcomePatternMixtureInfluenceProtocol(
        protocol_id="pattern-mixture-influence-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        pattern_mixture_protocol_fingerprint=pattern_protocol.fingerprint,
        pattern_mixture_report_fingerprint=pattern_report.fingerprint,
        methods=tuple(ClinicalOutcomePatternMixtureIntervalMethod),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.3,
        minimum_interval_yield=0.4,
        minimum_production_clusters=8,
        maximum_production_cluster_unit_fraction=0.25,
        maximum_standard_error_calibration_deviation=0.8,
        multiplier_draws=99,
        multiplier_seed=199,
        primary_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        metadata={"public_test": True},
    )


def _scenario_result(report, scenario_id: str):
    return next(
        item for item in report.scenario_results if item.scenario_id == scenario_id
    )


class ClinicalOutcomePatternMixtureInfluenceCalibrationTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.stress_protocol = _stress_protocol()
        cls.pattern_protocol = _pattern_protocol(cls.stress_protocol)
        cls.pattern_report = analyze_clinical_outcome_pattern_mixture(
            cls.pattern_protocol,
            cls.stress_protocol,
        )
        cls.protocol = _influence_protocol(
            cls.stress_protocol,
            cls.pattern_protocol,
            cls.pattern_report,
        )
        cls.report = analyze_clinical_outcome_pattern_mixture_influence_calibration(
            cls.protocol,
            cls.pattern_protocol,
            cls.stress_protocol,
        )

    def test_student_t_critical_values_match_reference_values(self) -> None:
        self.assertAlmostEqual(_student_t_critical(0.95, 1), 12.706204736, places=9)
        self.assertAlmostEqual(_student_t_critical(0.95, 7), 2.364624252, places=9)
        self.assertAlmostEqual(_student_t_critical(0.95, 11), 2.200985160, places=9)

    def test_nonfinite_distribution_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            _student_t_cdf(float("nan"), 7)
        with self.assertRaises(ValueError):
            _linear_quantile((0.1, float("nan"), 0.9), 0.5)

    def test_delete_mj_reduces_to_equal_group_jackknife_variance(self) -> None:
        full = 0.51
        leaveout = (0.48, 0.5, 0.53, 0.55)
        estimate, variance, pseudovalues, contributions = (
            _delete_mj_estimate_and_variance(full, leaveout, (8, 8, 8, 8))
        )
        self.assertAlmostEqual(variance, _delete_one_variance(leaveout), places=14)
        self.assertAlmostEqual(sum(contributions), 0.0, places=14)
        self.assertEqual(len(pseudovalues), 4)
        self.assertAlmostEqual(estimate, 4 * full - 3 * sum(leaveout) / 4, places=14)

    def test_delete_mj_uses_unequal_group_pseudovalue_weights(self) -> None:
        full = 0.5
        leaveout = (0.44, 0.49, 0.54)
        sizes = (20, 10, 5)
        estimate, variance, pseudovalues, contributions = (
            _delete_mj_estimate_and_variance(full, leaveout, sizes)
        )
        expected_pseudovalues = tuple(
            (35 / size) * full - (35 / size - 1) * value
            for size, value in zip(sizes, leaveout, strict=True)
        )
        expected_estimate = sum(
            size / 35 * value
            for size, value in zip(sizes, expected_pseudovalues, strict=True)
        )
        self.assertEqual(pseudovalues, expected_pseudovalues)
        self.assertAlmostEqual(estimate, expected_estimate, places=14)
        self.assertGreater(variance, 0.0)
        self.assertAlmostEqual(sum(contributions), 0.0, places=14)

    def test_replay_invariants_and_production_hard_stop(self) -> None:
        balanced = _scenario_result(self.report, "balanced-eight")
        dominant = _scenario_result(self.report, "dominant-cluster")
        unequal = _scenario_result(self.report, "unequal-eight")
        self.assertTrue(balanced.student_t_coverage_noninferior_to_normal_all_cells)
        self.assertTrue(balanced.equal_size_delete_mj_standard_error_equivalence_met)
        self.assertTrue(balanced.production_eligible)
        self.assertFalse(unequal.equal_cluster_sizes)
        self.assertTrue(unequal.production_eligible)
        self.assertFalse(dominant.production_eligible)
        self.assertEqual(
            dominant.production_ineligibility_reasons,
            ("dominant_cluster",),
        )
        self.assertTrue(dominant.dominant_cluster_hard_stop_preserved)

    def test_multiplier_seed_does_not_change_analytic_methods(self) -> None:
        changed = replace(self.protocol, multiplier_seed=211)
        changed_report = analyze_clinical_outcome_pattern_mixture_influence_calibration(
            changed,
            self.pattern_protocol,
            self.stress_protocol,
        )
        for original, rebuilt in zip(
            self.report.scenario_results,
            changed_report.scenario_results,
            strict=True,
        ):
            self.assertEqual(
                original.outcome_rng_stream_sha256, rebuilt.outcome_rng_stream_sha256
            )
            self.assertEqual(
                original.evaluability_rng_stream_sha256,
                rebuilt.evaluability_rng_stream_sha256,
            )
            self.assertNotEqual(
                original.multiplier_rng_stream_sha256,
                rebuilt.multiplier_rng_stream_sha256,
            )
            self.assertEqual(original.method_results[:3], rebuilt.method_results[:3])

    def test_protocol_report_round_trip_and_strict_tamper_rejection(self) -> None:
        protocol_envelope = (
            clinical_outcome_pattern_mixture_influence_protocol_envelope(self.protocol)
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_influence_protocol_from_dict(
                protocol_envelope
            ),
            self.protocol,
        )
        report_envelope = clinical_outcome_pattern_mixture_influence_report_envelope(
            self.report
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_influence_report_from_dict(
                report_envelope
            ),
            self.report,
        )
        unknown = copy.deepcopy(report_envelope)
        unknown["report"]["unknown"] = True
        with self.assertRaises(RecordParseError):
            clinical_outcome_pattern_mixture_influence_report_from_dict(unknown)
        tampered = copy.deepcopy(report_envelope)
        tampered["report"]["dominant_cluster_override_allowed"] = True
        with self.assertRaises(ValueError):
            clinical_outcome_pattern_mixture_influence_report_from_dict(tampered)
        with self.assertRaises(ValueError):
            replace(
                self.report,
                maximum_production_cluster_unit_fraction=0.1,
            )

    def test_bound_inputs_and_full_replay_validation(self) -> None:
        self.assertEqual(
            validate_clinical_outcome_pattern_mixture_influence_calibration_report(
                self.report,
                self.protocol,
                self.pattern_protocol,
                self.stress_protocol,
            ),
            (),
        )
        with self.assertRaises(ClinicalOutcomePatternMixtureInfluenceError):
            analyze_clinical_outcome_pattern_mixture_influence_calibration(
                replace(self.protocol, stress_protocol_fingerprint="0" * 64),
                self.pattern_protocol,
                self.stress_protocol,
            )

    def test_summary_is_compact_and_method_explicit(self) -> None:
        summary = clinical_outcome_pattern_mixture_influence_calibration_summary(
            self.report
        )
        self.assertEqual(
            summary["methods"],
            [item.value for item in ClinicalOutcomePatternMixtureIntervalMethod],
        )
        self.assertEqual(
            summary["primary_metric"],
            ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE.value,
        )
        self.assertFalse(
            summary["claim_boundary"]["automatic_method_selection_included"]
        )
        self.assertTrue(
            summary["claim_boundary"]["multiplier_method_experimental_only"]
        )

    def test_cli_calibrate_validate_and_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stress_path = root / "stress.json"
            pattern_path = root / "pattern.json"
            protocol_path = root / "influence.json"
            report_path = root / "report.json"
            stress_path.write_text(
                json.dumps(self.stress_protocol_envelope),
                encoding="utf-8",
            )
            pattern_path.write_text(
                json.dumps(self.pattern_protocol_envelope),
                encoding="utf-8",
            )
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_pattern_mixture_influence_protocol_envelope(
                        self.protocol
                    )
                ),
                encoding="utf-8",
            )
            calibrated = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "calibrate-pattern-mixture-influence",
                    "--protocol",
                    str(protocol_path),
                    "--pattern-mixture-protocol",
                    str(pattern_path),
                    "--stress-protocol",
                    str(stress_path),
                    "--output",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(calibrated.returncode, 0, calibrated.stderr)
            validated = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "validate-pattern-mixture-influence",
                    "--report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["valid"])
            summarized = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize-pattern-mixture-influence",
                    "--report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            self.assertEqual(
                json.loads(summarized.stdout)["report_fingerprint"],
                self.report.fingerprint,
            )

    def test_public_artifact_chain_validates_and_replays_exactly(self) -> None:
        schema_examples = (
            (
                "clinical_outcome_stress_simulation_protocol.schema.json",
                PUBLIC_STRESS_PROTOCOL,
            ),
            (
                "clinical_outcome_pattern_mixture_protocol.schema.json",
                PUBLIC_PATTERN_PROTOCOL,
            ),
            (
                "clinical_outcome_pattern_mixture_report.schema.json",
                PUBLIC_PATTERN_REPORT,
            ),
            (
                "clinical_outcome_pattern_mixture_influence_protocol.schema.json",
                PUBLIC_PROTOCOL,
            ),
            (
                "clinical_outcome_pattern_mixture_influence_report.schema.json",
                PUBLIC_REPORT,
            ),
            (
                "clinical_outcome_pattern_mixture_influence_summary.schema.json",
                PUBLIC_SUMMARY,
            ),
        )
        for schema_name, example_path in schema_examples:
            validator = Draft202012Validator(
                json.loads((SPECS / schema_name).read_text(encoding="utf-8")),
                format_checker=FormatChecker(),
            )
            validator.validate(json.loads(example_path.read_text(encoding="utf-8")))

        stress = clinical_outcome_stress_protocol_from_json(
            PUBLIC_STRESS_PROTOCOL.read_text(encoding="utf-8")
        )
        pattern = clinical_outcome_pattern_mixture_protocol_from_json(
            PUBLIC_PATTERN_PROTOCOL.read_text(encoding="utf-8")
        )
        pattern_report = clinical_outcome_pattern_mixture_report_from_json(
            PUBLIC_PATTERN_REPORT.read_text(encoding="utf-8")
        )
        protocol = clinical_outcome_pattern_mixture_influence_protocol_from_json(
            PUBLIC_PROTOCOL.read_text(encoding="utf-8")
        )
        report = clinical_outcome_pattern_mixture_influence_report_from_json(
            PUBLIC_REPORT.read_text(encoding="utf-8")
        )
        self.assertEqual(pattern.stress_protocol_fingerprint, stress.fingerprint)
        self.assertEqual(protocol.stress_protocol_fingerprint, stress.fingerprint)
        self.assertEqual(
            protocol.pattern_mixture_protocol_fingerprint,
            pattern.fingerprint,
        )
        self.assertEqual(
            protocol.pattern_mixture_report_fingerprint,
            pattern_report.fingerprint,
        )
        self.assertEqual(
            analyze_clinical_outcome_pattern_mixture(pattern, stress),
            pattern_report,
        )
        self.assertEqual(
            analyze_clinical_outcome_pattern_mixture_influence_calibration(
                protocol,
                pattern,
                stress,
            ),
            report,
        )
        self.assertEqual(
            clinical_outcome_pattern_mixture_influence_calibration_summary(report),
            json.loads(PUBLIC_SUMMARY.read_text(encoding="utf-8")),
        )

    def test_public_schemas_match_runtime_multiplier_and_dominance_bounds(self) -> None:
        protocol_validator = Draft202012Validator(
            json.loads(
                (
                    SPECS
                    / "clinical_outcome_pattern_mixture_influence_protocol.schema.json"
                ).read_text(encoding="utf-8")
            )
        )
        invalid_protocol = json.loads(PUBLIC_PROTOCOL.read_text(encoding="utf-8"))
        invalid_protocol["protocol"]["multiplier_draws"] = 100
        self.assertFalse(protocol_validator.is_valid(invalid_protocol))

        report_validator = Draft202012Validator(
            json.loads(
                (
                    SPECS
                    / "clinical_outcome_pattern_mixture_influence_report.schema.json"
                ).read_text(encoding="utf-8")
            )
        )
        invalid_report = json.loads(PUBLIC_REPORT.read_text(encoding="utf-8"))
        invalid_report["report"]["maximum_production_cluster_unit_fraction"] = 1.0
        self.assertFalse(report_validator.is_valid(invalid_report))

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.report

    @property
    def stress_protocol_envelope(self):
        return clinical_outcome_stress_protocol_envelope(self.stress_protocol)

    @property
    def pattern_protocol_envelope(self):
        return clinical_outcome_pattern_mixture_protocol_envelope(self.pattern_protocol)


if __name__ == "__main__":
    unittest.main()
