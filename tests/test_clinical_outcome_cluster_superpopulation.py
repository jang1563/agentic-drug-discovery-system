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
    ClinicalOutcomeClusterCountRule,
    ClinicalOutcomeClusterSizeMethod,
    ClinicalOutcomeClusterSizeProfile,
    ClinicalOutcomeClusterSuperpopulationError,
    ClinicalOutcomeClusterSuperpopulationProtocol,
    ClinicalOutcomeClusterSuperpopulationSamplingModel,
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomeInformativeClusterSizeProtocol,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    RecordParseError,
    Stage,
    analyze_clinical_outcome_cluster_superpopulation,
    analyze_clinical_outcome_informative_cluster_size,
    clinical_outcome_cluster_superpopulation_protocol_envelope,
    clinical_outcome_cluster_superpopulation_protocol_from_dict,
    clinical_outcome_cluster_superpopulation_report_envelope,
    clinical_outcome_cluster_superpopulation_report_from_dict,
    clinical_outcome_cluster_superpopulation_report_from_json,
    clinical_outcome_cluster_superpopulation_summary,
    clinical_outcome_informative_cluster_size_protocol_envelope,
    clinical_outcome_informative_cluster_size_report_envelope,
    clinical_outcome_stress_protocol_envelope,
    validate_clinical_outcome_cluster_superpopulation_report,
)


REFERENCE_LOG_IMOR = -1.996553881874
SIZES = (96, 80, 64, 48, 32, 32)
INFORMATIVE_PROFILE = (0.75, 0.65, 0.55, 0.45, 0.35, 0.25)
ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env" / "specs"
PUBLIC_PROTOCOL = SPECS / "clinical_outcome_cluster_superpopulation_protocol.example.json"
PUBLIC_REPORT = SPECS / "clinical_outcome_cluster_superpopulation_report.example.json"
PUBLIC_SUMMARY = SPECS / "clinical_outcome_cluster_superpopulation_summary.example.json"
PUBLIC_EVIDENCE = ROOT / "docs" / "public_evidence_summary.json"


def _scenario(
    scenario_id: str,
    favorable_prevalence: float,
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=SIZES,
        dependence_blocks=tuple((index,) for index in range(len(SIZES))),
        favorable_prevalence=favorable_prevalence,
        dependence_block_intraclass_correlation=0.01,
        favorable_evaluable_probability=0.9,
        unfavorable_evaluable_probability=0.55,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.35,),
        policy_b_probability_pattern=(0.65,),
    )


def _stress_protocol() -> ClinicalOutcomeStressSimulationProtocol:
    informative_prevalence = round(
        sum(
            size * prevalence
            for size, prevalence in zip(SIZES, INFORMATIVE_PROFILE, strict=True)
        )
        / sum(SIZES),
        12,
    )
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="cluster-superpopulation-test-stress",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=100,
        random_seed=811,
        coverage_tolerance=0.4,
        minimum_interval_yield=0.4,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="test-g05-share25",
                minimum_evaluable_clusters=5,
                maximum_evaluable_cluster_fraction=0.25,
            ),
        ),
        scenarios=(
            _scenario("informative", informative_prevalence),
            _scenario("null", 0.5),
        ),
        metadata={"public_test": True},
    )


def _fixed_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    return ClinicalOutcomeInformativeClusterSizeProtocol(
        protocol_id="cluster-superpopulation-test-fixed",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        profiles=(
            ClinicalOutcomeClusterSizeProfile(
                "informative",
                INFORMATIVE_PROFILE,
            ),
            ClinicalOutcomeClusterSizeProfile("null", (0.5,) * len(SIZES)),
        ),
        methods=tuple(ClinicalOutcomeClusterSizeMethod),
        log_imor_grid=(REFERENCE_LOG_IMOR, 0.0),
        reference_log_imor=REFERENCE_LOG_IMOR,
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.4,
        minimum_interval_yield=0.4,
        maximum_absolute_bias=0.3,
        minimum_production_clusters=5,
        maximum_production_cluster_unit_fraction=0.25,
        maximum_standard_error_calibration_deviation=0.95,
        primary_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        direction_threshold=0.5,
        metadata={"public_test": True},
    )


def _superpopulation_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    fixed_protocol: ClinicalOutcomeInformativeClusterSizeProtocol,
    fixed_report,
) -> ClinicalOutcomeClusterSuperpopulationProtocol:
    return ClinicalOutcomeClusterSuperpopulationProtocol(
        protocol_id="cluster-superpopulation-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        fixed_profile_protocol_fingerprint=fixed_protocol.fingerprint,
        fixed_profile_report_fingerprint=fixed_report.fingerprint,
        sampling_model=(
            ClinicalOutcomeClusterSuperpopulationSamplingModel.UNIFORM_EMPIRICAL_TEMPLATE_WITH_REPLACEMENT
        ),
        cluster_count_rule=ClinicalOutcomeClusterCountRule.MATCH_TEMPLATE_COUNT,
        replicates=fixed_report.replicates,
        random_seed=812,
        methods=fixed_protocol.methods,
        log_imor_grid=fixed_protocol.log_imor_grid,
        reference_log_imor=fixed_protocol.reference_log_imor,
        confidence_level=fixed_protocol.confidence_level,
        monte_carlo_confidence_level=fixed_protocol.monte_carlo_confidence_level,
        coverage_tolerance=fixed_protocol.coverage_tolerance,
        minimum_interval_yield=fixed_protocol.minimum_interval_yield,
        maximum_absolute_bias=fixed_protocol.maximum_absolute_bias,
        minimum_production_clusters=fixed_protocol.minimum_production_clusters,
        maximum_production_cluster_unit_fraction=(
            fixed_protocol.maximum_production_cluster_unit_fraction
        ),
        maximum_standard_error_calibration_deviation=(
            fixed_protocol.maximum_standard_error_calibration_deviation
        ),
        primary_metric=fixed_protocol.primary_metric,
        direction_threshold=fixed_protocol.direction_threshold,
        metadata={"public_test": True, "post_hoc_design_filtering": False},
    )


def _scenario_result(report, scenario_id: str):
    return next(
        item for item in report.scenario_results if item.scenario_id == scenario_id
    )


class ClinicalOutcomeClusterSuperpopulationTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.stress_protocol = _stress_protocol()
        cls.fixed_protocol = _fixed_protocol(cls.stress_protocol)
        cls.fixed_report = analyze_clinical_outcome_informative_cluster_size(
            cls.fixed_protocol,
            cls.stress_protocol,
        )
        cls.protocol = _superpopulation_protocol(
            cls.stress_protocol,
            cls.fixed_protocol,
            cls.fixed_report,
        )
        cls.report = analyze_clinical_outcome_cluster_superpopulation(
            cls.protocol,
            cls.stress_protocol,
            cls.fixed_protocol,
            cls.fixed_report,
        )

    def test_empirical_template_sampling_preserves_every_known_truth(self) -> None:
        comparisons = [
            item
            for scenario in self.report.scenario_results
            for item in scenario.conditional_comparisons
        ]
        self.assertEqual(len(comparisons), 2 * 3 * 8 * 2)
        self.assertTrue(all(item.truth_difference == 0.0 for item in comparisons))
        informative = _scenario_result(self.report, "informative")
        self.assertGreater(
            informative.superpopulation_unit_weighted_favorable_prevalence,
            informative.superpopulation_cluster_balanced_favorable_prevalence,
        )
        self.assertTrue(informative.truth_direction_disagrees)

    def test_realized_design_is_diagnosed_without_post_hoc_filtering(self) -> None:
        informative = _scenario_result(self.report, "informative")
        design = informative.design_diagnostic
        self.assertGreater(design.dominant_cluster_rate.event_count, 0)
        self.assertEqual(design.dominant_cluster_rate.total_count, self.protocol.replicates)
        self.assertEqual(design.production_eligible_rate.total_count, self.protocol.replicates)
        self.assertFalse(self.report.post_hoc_design_filtering_included)
        for method in informative.method_results:
            for metric in method.metric_inference:
                for cell in metric.grid_inference:
                    self.assertEqual(cell.replicate_count, self.protocol.replicates)

    def test_dynamic_largest_cluster_denominators_handle_ties(self) -> None:
        informative = _scenario_result(self.report, "informative")
        design_unique = informative.design_diagnostic.unique_largest_cluster_rate
        self.assertGreater(design_unique.event_count, 0)
        self.assertLess(design_unique.event_count, design_unique.total_count)
        for diagnostic in informative.influence_diagnostics:
            unique = diagnostic.unique_largest_cluster_rate
            self.assertEqual(
                diagnostic.unique_largest_cluster_most_influential.total_count,
                unique.event_count,
            )
            expected_flip_total = (
                unique.event_count
                if diagnostic.largest_cluster_deletion_direction_flip_applicable
                else 0
            )
            self.assertEqual(
                diagnostic.largest_cluster_deletion_direction_flip.total_count,
                expected_flip_total,
            )

    def test_analysis_is_deterministic_and_full_replay_validates(self) -> None:
        rebuilt = analyze_clinical_outcome_cluster_superpopulation(
            self.protocol,
            self.stress_protocol,
            self.fixed_protocol,
            self.fixed_report,
        )
        self.assertEqual(rebuilt, self.report)
        self.assertEqual(
            validate_clinical_outcome_cluster_superpopulation_report(
                self.report,
                self.protocol,
                self.stress_protocol,
                self.fixed_protocol,
                self.fixed_report,
            ),
            (),
        )

    def test_exact_fingerprint_binding_rejects_another_reference(self) -> None:
        protocol = replace(
            self.protocol,
            fixed_profile_report_fingerprint="0" * 64,
        )
        with self.assertRaises(ClinicalOutcomeClusterSuperpopulationError):
            analyze_clinical_outcome_cluster_superpopulation(
                protocol,
                self.stress_protocol,
                self.fixed_protocol,
                self.fixed_report,
            )

    def test_strict_protocol_and_report_round_trip(self) -> None:
        protocol_envelope = clinical_outcome_cluster_superpopulation_protocol_envelope(
            self.protocol
        )
        report_envelope = clinical_outcome_cluster_superpopulation_report_envelope(
            self.report
        )
        self.assertEqual(
            clinical_outcome_cluster_superpopulation_protocol_from_dict(
                protocol_envelope
            ),
            self.protocol,
        )
        self.assertEqual(
            clinical_outcome_cluster_superpopulation_report_from_dict(report_envelope),
            self.report,
        )
        unknown = copy.deepcopy(report_envelope)
        unknown["report"]["unknown"] = True
        with self.assertRaises(RecordParseError):
            clinical_outcome_cluster_superpopulation_report_from_dict(unknown)
        tampered = copy.deepcopy(report_envelope)
        tampered["report"]["random_seed"] += 1
        with self.assertRaises(RecordParseError):
            clinical_outcome_cluster_superpopulation_report_from_dict(tampered)

    def test_semantic_crosslinks_reject_rehashed_nested_tampering(self) -> None:
        scenario = _scenario_result(self.report, "informative")
        comparison = scenario.conditional_comparisons[0]
        assert comparison.superpopulation_target_bias is not None
        assert comparison.fixed_profile_target_bias is not None
        changed_bias = round(comparison.superpopulation_target_bias + 0.01, 12)
        changed_comparison = replace(
            comparison,
            superpopulation_target_bias=changed_bias,
            target_bias_change=round(
                changed_bias - comparison.fixed_profile_target_bias,
                12,
            ),
        )
        with self.assertRaises(ValueError):
            replace(
                scenario,
                conditional_comparisons=(
                    changed_comparison,
                    *scenario.conditional_comparisons[1:],
                ),
            )
        with self.assertRaises(ValueError):
            replace(scenario, outcome_rng_stream_sha256="0" * 64)

    def test_summary_is_aggregate_and_machine_readable(self) -> None:
        summary = clinical_outcome_cluster_superpopulation_summary(self.report)
        self.assertEqual(summary["comparison_cell_count"], 96)
        self.assertFalse(summary["post_hoc_design_filtering_included"])
        self.assertFalse(summary["external_transportability_claimed"])
        serialized = json.dumps(
            clinical_outcome_cluster_superpopulation_report_envelope(self.report)
        )
        for forbidden in (
            "unit_records",
            "cluster_records",
            "replicate_records",
            "patient_id",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_cli_analyze_validate_and_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inputs = {
                "stress.json": clinical_outcome_stress_protocol_envelope(
                    self.stress_protocol
                ),
                "fixed-protocol.json": (
                    clinical_outcome_informative_cluster_size_protocol_envelope(
                        self.fixed_protocol
                    )
                ),
                "fixed-report.json": (
                    clinical_outcome_informative_cluster_size_report_envelope(
                        self.fixed_report
                    )
                ),
                "protocol.json": (
                    clinical_outcome_cluster_superpopulation_protocol_envelope(
                        self.protocol
                    )
                ),
            }
            for filename, payload in inputs.items():
                (root / filename).write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )
            output = root / "report.json"
            base = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
            ]
            analyzed = subprocess.run(
                [
                    *base,
                    "analyze-cluster-superpopulation",
                    "--protocol",
                    str(root / "protocol.json"),
                    "--stress-protocol",
                    str(root / "stress.json"),
                    "--fixed-profile-protocol",
                    str(root / "fixed-protocol.json"),
                    "--fixed-profile-report",
                    str(root / "fixed-report.json"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(analyzed.returncode, 0, analyzed.stderr)
            self.assertEqual(
                clinical_outcome_cluster_superpopulation_report_from_json(
                    output.read_text(encoding="utf-8")
                ),
                self.report,
            )
            validated = subprocess.run(
                [
                    *base,
                    "validate-cluster-superpopulation",
                    "--report",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["valid"])
            summarized = subprocess.run(
                [
                    *base,
                    "summarize-cluster-superpopulation",
                    "--report",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            self.assertEqual(
                json.loads(summarized.stdout),
                clinical_outcome_cluster_superpopulation_summary(self.report),
            )


class PublicClusterSuperpopulationArtifactTests(unittest.TestCase):
    def test_public_artifacts_match_strict_schemas_and_summary(self) -> None:
        for kind in ("protocol", "report", "summary"):
            stem = f"clinical_outcome_cluster_superpopulation_{kind}"
            schema = json.loads((SPECS / f"{stem}.schema.json").read_text())
            artifact = json.loads((SPECS / f"{stem}.example.json").read_text())
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(artifact)
        report = clinical_outcome_cluster_superpopulation_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        self.assertEqual(
            clinical_outcome_cluster_superpopulation_summary(report),
            json.loads(PUBLIC_SUMMARY.read_text()),
        )

    def test_public_result_locks_sampling_frame_finding(self) -> None:
        protocol = clinical_outcome_cluster_superpopulation_protocol_from_dict(
            json.loads(PUBLIC_PROTOCOL.read_text())
        )
        report = clinical_outcome_cluster_superpopulation_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        summary = clinical_outcome_cluster_superpopulation_summary(report)
        self.assertEqual(
            protocol.fingerprint,
            "50f8494d73d32452f02a15595bae3b39549bc13069a65211af4d03500c8bafa4",
        )
        self.assertEqual(
            report.fingerprint,
            "f9600e89c2e1f04800cdcc07e9ca573e76a13de26f05dbbeee8e745b53b94ef4",
        )
        self.assertEqual(summary["comparison_cell_count"], 600)
        self.assertEqual(
            summary["fixed_profile_standard_error_calibration_pass_count"],
            280,
        )
        self.assertEqual(
            summary["superpopulation_standard_error_calibration_pass_count"],
            600,
        )
        self.assertEqual(
            summary["standard_error_calibration_recovered_cell_count"],
            320,
        )
        self.assertEqual(summary["superpopulation_full_calibration_pass_count"], 520)
        evidence = json.loads(PUBLIC_EVIDENCE.read_text())[
            "clinical_cluster_superpopulation_synthetic"
        ]
        self.assertEqual(evidence["protocol_fingerprint"], protocol.fingerprint)
        self.assertEqual(evidence["report_fingerprint"], report.fingerprint)
        self.assertEqual(
            evidence["standard_error_calibration_recovered_cell_count"],
            summary["standard_error_calibration_recovered_cell_count"],
        )
        self.assertEqual(
            evidence["superpopulation_full_calibration_pass_count"],
            summary["superpopulation_full_calibration_pass_count"],
        )


if __name__ == "__main__":
    unittest.main()
