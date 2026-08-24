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
    ClinicalOutcomeClusterSizeEstimand,
    ClinicalOutcomeClusterSizeMethod,
    ClinicalOutcomeClusterSizeProfile,
    ClinicalOutcomeClusterSizeStatus,
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomeInformativeClusterSizeError,
    ClinicalOutcomeInformativeClusterSizeProtocol,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    RecordParseError,
    Stage,
    analyze_clinical_outcome_informative_cluster_size,
    clinical_outcome_informative_cluster_size_protocol_envelope,
    clinical_outcome_informative_cluster_size_protocol_from_dict,
    clinical_outcome_informative_cluster_size_protocol_from_json,
    clinical_outcome_informative_cluster_size_report_envelope,
    clinical_outcome_informative_cluster_size_report_from_dict,
    clinical_outcome_informative_cluster_size_report_from_json,
    clinical_outcome_informative_cluster_size_summary,
    clinical_outcome_stress_protocol_envelope,
    clinical_outcome_stress_protocol_from_json,
    validate_clinical_outcome_informative_cluster_size_report,
)


REFERENCE_LOG_IMOR = -1.996553881874
UNEQUAL_SIZES = (96, 80, 80, 64, 64, 48, 32, 32)
INFORMATIVE_PROFILE = (0.75, 0.65, 0.65, 0.5, 0.5, 0.35, 0.25, 0.25)
ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env" / "specs"
PUBLIC_STRESS_PROTOCOL = (
    SPECS / "clinical_outcome_informative_cluster_size_stress_protocol.example.json"
)
PUBLIC_PROTOCOL = (
    SPECS / "clinical_outcome_informative_cluster_size_protocol.example.json"
)
PUBLIC_REPORT = (
    SPECS / "clinical_outcome_informative_cluster_size_report.example.json"
)
PUBLIC_SUMMARY = (
    SPECS / "clinical_outcome_informative_cluster_size_summary.example.json"
)
PUBLIC_EVIDENCE = ROOT / "docs" / "public_evidence_summary.json"


def _scenario(
    scenario_id: str,
    cluster_sizes: tuple[int, ...],
    favorable_prevalence: float,
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=cluster_sizes,
        dependence_blocks=tuple((index,) for index in range(len(cluster_sizes))),
        favorable_prevalence=favorable_prevalence,
        dependence_block_intraclass_correlation=0.02,
        favorable_evaluable_probability=0.9,
        unfavorable_evaluable_probability=0.55,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.35,),
        policy_b_probability_pattern=(0.65,),
    )


def _stress_protocol() -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="informative-cluster-size-test-stress",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=100,
        random_seed=211,
        coverage_tolerance=0.3,
        minimum_interval_yield=0.5,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="test-g06-share30",
                minimum_evaluable_clusters=6,
                maximum_evaluable_cluster_fraction=0.3,
            ),
        ),
        scenarios=(
            _scenario(
                "dominant-informative",
                (256,) + (64,) * 7,
                0.559090909091,
            ),
            _scenario("informative", UNEQUAL_SIZES, 0.55),
            _scenario("null", UNEQUAL_SIZES, 0.5),
        ),
        metadata={"public_test": True},
    )


def _study_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    return ClinicalOutcomeInformativeClusterSizeProtocol(
        protocol_id="informative-cluster-size-test",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        profiles=(
            ClinicalOutcomeClusterSizeProfile(
                "dominant-informative",
                (0.75,) + (0.45,) * 7,
            ),
            ClinicalOutcomeClusterSizeProfile(
                "informative",
                INFORMATIVE_PROFILE,
            ),
            ClinicalOutcomeClusterSizeProfile("null", (0.5,) * 8),
        ),
        methods=tuple(ClinicalOutcomeClusterSizeMethod),
        log_imor_grid=(REFERENCE_LOG_IMOR, 0.0),
        reference_log_imor=REFERENCE_LOG_IMOR,
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.3,
        minimum_interval_yield=0.5,
        maximum_absolute_bias=0.2,
        minimum_production_clusters=6,
        maximum_production_cluster_unit_fraction=0.3,
        maximum_standard_error_calibration_deviation=0.9,
        primary_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        direction_threshold=0.5,
        metadata={"public_test": True},
    )


def _scenario_result(report, scenario_id: str):
    return next(
        item for item in report.scenario_results if item.scenario_id == scenario_id
    )


def _reference_cell(result, method: ClinicalOutcomeClusterSizeMethod):
    method_result = next(item for item in result.method_results if item.method is method)
    metric_result = next(
        item
        for item in method_result.metric_inference
        if item.metric is ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE
    )
    return next(
        item
        for item in metric_result.grid_inference
        if item.log_imor == REFERENCE_LOG_IMOR
    )


class ClinicalOutcomeInformativeClusterSizeTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.stress_protocol = _stress_protocol()
        cls.protocol = _study_protocol(cls.stress_protocol)
        cls.report = analyze_clinical_outcome_informative_cluster_size(
            cls.protocol,
            cls.stress_protocol,
        )

    def test_null_profile_collapses_estimands(self) -> None:
        result = _scenario_result(self.report, "null")
        self.assertEqual(result.unit_weighted_favorable_prevalence, 0.5)
        self.assertEqual(result.cluster_balanced_favorable_prevalence, 0.5)
        self.assertEqual(result.favorable_prevalence_contrast_unit_minus_cluster, 0.0)
        self.assertFalse(result.truth_direction_disagrees)
        for method in ClinicalOutcomeClusterSizeMethod:
            cell = _reference_cell(result, method)
            self.assertEqual(cell.unit_weighted_true_value, 0.5)
            self.assertEqual(cell.cluster_balanced_true_value, 0.5)

    def test_informative_profile_separates_estimands_and_directions(self) -> None:
        result = _scenario_result(self.report, "informative")
        self.assertEqual(result.unit_weighted_favorable_prevalence, 0.55)
        self.assertEqual(result.cluster_balanced_favorable_prevalence, 0.4875)
        self.assertEqual(result.favorable_prevalence_contrast_unit_minus_cluster, 0.0625)
        self.assertTrue(result.truth_direction_disagrees)
        for method in ClinicalOutcomeClusterSizeMethod:
            cell = _reference_cell(result, method)
            self.assertLess(abs(cell.target_bias), abs(cell.alternate_estimand_bias))

    def test_delete_mj_does_not_change_the_estimand(self) -> None:
        result = _scenario_result(self.report, "informative")
        cell = _reference_cell(
            result,
            ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_MJ_STUDENT_T,
        )
        self.assertIs(
            cell.target_estimand,
            ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED,
        )
        self.assertEqual(cell.target_true_value, 0.55)
        self.assertEqual(cell.alternate_true_value, 0.4875)
        self.assertFalse(self.report.delete_mj_estimand_correction_claimed)

    def test_methods_share_one_block_functional_before_weighting(self) -> None:
        balanced = _scenario_result(self.report, "null")
        balanced_cells = [
            tuple(
                cell.mean_estimate
                for metric in method.metric_inference
                for cell in metric.grid_inference
            )
            for method in balanced.method_results
        ]
        self.assertEqual(balanced_cells[0], balanced_cells[1])

        informative = _scenario_result(self.report, "informative")
        unit_methods = tuple(
            method
            for method in informative.method_results
            if method.target_estimand is ClinicalOutcomeClusterSizeEstimand.UNIT_WEIGHTED
        )
        self.assertEqual(len(unit_methods), 2)
        for left_metric, right_metric in zip(
            unit_methods[0].metric_inference,
            unit_methods[1].metric_inference,
            strict=True,
        ):
            for left, right in zip(
                left_metric.grid_inference,
                right_metric.grid_inference,
                strict=True,
            ):
                self.assertEqual(left.mean_estimate, right.mean_estimate)
                self.assertEqual(left.unit_weighted_true_value, right.target_true_value)

    def test_status_contract_is_block_scoped(self) -> None:
        self.assertEqual(
            tuple(item.value for item in ClinicalOutcomeClusterSizeStatus),
            (
                "computed",
                "insufficient_simulation_clusters",
                "cluster_empty_reference_stratum",
                "cluster_degenerate_reference_stratum",
                "zero_resampling_variance",
            ),
        )

    def test_cluster_balanced_method_targets_equal_block_weight(self) -> None:
        result = _scenario_result(self.report, "informative")
        cell = _reference_cell(
            result,
            ClinicalOutcomeClusterSizeMethod.CLUSTER_BALANCED_DELETE_ONE_STUDENT_T,
        )
        self.assertIs(
            cell.target_estimand,
            ClinicalOutcomeClusterSizeEstimand.CLUSTER_BALANCED,
        )
        self.assertEqual(cell.target_true_value, 0.4875)
        self.assertEqual(cell.alternate_true_value, 0.55)

    def test_dominant_cluster_remains_production_ineligible(self) -> None:
        result = _scenario_result(self.report, "dominant-informative")
        self.assertFalse(result.production_eligible)
        self.assertEqual(result.production_ineligibility_reasons, ("dominant_cluster",))
        self.assertTrue(result.dominant_cluster_hard_stop_preserved)
        self.assertTrue(result.truth_direction_disagrees)

    def test_single_dependence_block_is_reported_as_non_analyzable(self) -> None:
        scenario = replace(
            _scenario("single-block", (64, 64), 0.5),
            dependence_blocks=((0, 1),),
        )
        stress_protocol = replace(
            self.stress_protocol,
            protocol_id="informative-cluster-size-single-block-stress",
            scenarios=(scenario,),
        )
        protocol = replace(
            self.protocol,
            protocol_id="informative-cluster-size-single-block",
            stress_protocol_fingerprint=stress_protocol.fingerprint,
            profiles=(
                ClinicalOutcomeClusterSizeProfile("single-block", (0.5,)),
            ),
        )

        report = analyze_clinical_outcome_informative_cluster_size(
            protocol,
            stress_protocol,
        )
        for name, envelope in (
            (
                "protocol",
                clinical_outcome_informative_cluster_size_protocol_envelope(
                    protocol
                ),
            ),
            (
                "report",
                clinical_outcome_informative_cluster_size_report_envelope(report),
            ),
            (
                "summary",
                clinical_outcome_informative_cluster_size_summary(report),
            ),
        ):
            schema = json.loads(
                (
                    SPECS
                    / f"clinical_outcome_informative_cluster_size_{name}.schema.json"
                ).read_text()
            )
            Draft202012Validator(schema).validate(envelope)
        result = report.scenario_results[0]
        self.assertEqual(result.analysis_structure.cluster_count, 1)
        self.assertEqual(
            result.production_ineligibility_reasons,
            ("insufficient_clusters", "dominant_cluster"),
        )
        for method in result.method_results:
            for metric in method.metric_inference:
                for cell in metric.grid_inference:
                    self.assertEqual(cell.point_estimate_count, 0)
                    counts = {item.status: item.count for item in cell.status_counts}
                    self.assertEqual(
                        counts[
                            ClinicalOutcomeClusterSizeStatus.INSUFFICIENT_SIMULATION_CLUSTERS
                        ],
                        stress_protocol.replicates,
                    )
        for diagnostic in result.influence_diagnostics:
            self.assertEqual(diagnostic.analyzable_replicate_count, 0)
            self.assertFalse(diagnostic.unique_largest_block_available)
            self.assertFalse(
                diagnostic.largest_block_deletion_direction_flip_applicable
            )

    def test_influence_diagnostics_are_aggregate_and_method_specific(self) -> None:
        result = _scenario_result(self.report, "informative")
        diagnostics = {item.method: item for item in result.influence_diagnostics}
        for diagnostic in diagnostics.values():
            self.assertGreater(diagnostic.analyzable_replicate_count, 90)
            self.assertTrue(diagnostic.unique_largest_block_available)
            self.assertIsNotNone(diagnostic.p95_maximum_absolute_influence)
        delete_mj = diagnostics[
            ClinicalOutcomeClusterSizeMethod.UNIT_WEIGHTED_DELETE_MJ_STUDENT_T
        ]
        self.assertFalse(delete_mj.largest_block_deletion_direction_flip_applicable)
        self.assertEqual(
            delete_mj.largest_block_deletion_direction_flip.total_count,
            0,
        )

    def test_protocol_and_report_round_trip_strictly(self) -> None:
        protocol_envelope = clinical_outcome_informative_cluster_size_protocol_envelope(
            self.protocol
        )
        self.assertEqual(
            clinical_outcome_informative_cluster_size_protocol_from_dict(
                protocol_envelope
            ),
            self.protocol,
        )
        self.assertEqual(
            clinical_outcome_informative_cluster_size_protocol_from_json(
                json.dumps(protocol_envelope)
            ),
            self.protocol,
        )
        report_envelope = clinical_outcome_informative_cluster_size_report_envelope(
            self.report
        )
        self.assertEqual(
            clinical_outcome_informative_cluster_size_report_from_dict(report_envelope),
            self.report,
        )
        self.assertEqual(
            clinical_outcome_informative_cluster_size_report_from_json(
                json.dumps(report_envelope)
            ),
            self.report,
        )

    def test_unknown_and_tampered_fields_fail_closed(self) -> None:
        envelope = clinical_outcome_informative_cluster_size_report_envelope(
            self.report
        )
        unknown = copy.deepcopy(envelope)
        unknown["report"]["unexpected"] = True
        with self.assertRaises(RecordParseError):
            clinical_outcome_informative_cluster_size_report_from_dict(unknown)
        tampered = copy.deepcopy(envelope)
        tampered["report"]["direction_threshold"] = 0.49
        with self.assertRaises(RecordParseError):
            clinical_outcome_informative_cluster_size_report_from_dict(tampered)

    def test_records_reject_stringly_typed_methods(self) -> None:
        string_methods = tuple(item.value for item in self.protocol.methods)
        with self.assertRaises((TypeError, ValueError)):
            replace(self.protocol, methods=string_methods)
        with self.assertRaises((TypeError, ValueError)):
            replace(self.report, methods=string_methods)

    def test_exact_replay_and_changed_seed_detection(self) -> None:
        self.assertEqual(
            validate_clinical_outcome_informative_cluster_size_report(
                self.report,
                self.protocol,
                self.stress_protocol,
            ),
            (),
        )
        changed_stress = replace(self.stress_protocol, random_seed=212)
        self.assertEqual(
            validate_clinical_outcome_informative_cluster_size_report(
                self.report,
                self.protocol,
                changed_stress,
            ),
            ("informative_cluster_size_replay_failed",),
        )

    def test_profile_marginal_must_match_bound_stress_scenario(self) -> None:
        profiles = list(self.protocol.profiles)
        profiles[1] = replace(
            profiles[1],
            block_favorable_prevalences=(0.7,) * 8,
        )
        invalid = replace(self.protocol, profiles=tuple(profiles))
        with self.assertRaises(ClinicalOutcomeInformativeClusterSizeError):
            analyze_clinical_outcome_informative_cluster_size(
                invalid,
                self.stress_protocol,
            )

    def test_summary_retains_estimand_and_claim_boundaries(self) -> None:
        summary = clinical_outcome_informative_cluster_size_summary(self.report)
        self.assertFalse(summary["automatic_estimand_selection_included"])
        self.assertFalse(summary["delete_mj_estimand_correction_claimed"])
        self.assertTrue(summary["fixed_block_profiles_across_replicates"])
        self.assertFalse(summary["cluster_superpopulation_resampling_included"])
        informative = next(
            item for item in summary["scenarios"] if item["scenario_id"] == "informative"
        )
        self.assertTrue(informative["truth_direction_disagrees"])
        self.assertEqual(
            {item["target_estimand"] for item in informative["methods"]},
            {"unit_weighted", "cluster_balanced"},
        )

    def test_public_artifacts_validate_against_schemas_and_parse(self) -> None:
        stress_schema = json.loads(
            (
                SPECS / "clinical_outcome_stress_simulation_protocol.schema.json"
            ).read_text()
        )
        Draft202012Validator.check_schema(stress_schema)
        Draft202012Validator(
            stress_schema,
            format_checker=FormatChecker(),
        ).validate(json.loads(PUBLIC_STRESS_PROTOCOL.read_text()))
        for name, artifact in (
            ("protocol", PUBLIC_PROTOCOL),
            ("report", PUBLIC_REPORT),
            ("summary", PUBLIC_SUMMARY),
        ):
            schema = json.loads(
                (
                    SPECS
                    / f"clinical_outcome_informative_cluster_size_{name}.schema.json"
                ).read_text()
            )
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(json.loads(artifact.read_text()))
        protocol = clinical_outcome_informative_cluster_size_protocol_from_json(
            PUBLIC_PROTOCOL.read_text()
        )
        report = clinical_outcome_informative_cluster_size_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        self.assertEqual(report.protocol_fingerprint, protocol.fingerprint)
        self.assertEqual(
            clinical_outcome_informative_cluster_size_summary(report),
            json.loads(PUBLIC_SUMMARY.read_text()),
        )

    def test_public_report_replays_exactly(self) -> None:
        stress_protocol = clinical_outcome_stress_protocol_from_json(
            PUBLIC_STRESS_PROTOCOL.read_text()
        )
        protocol = clinical_outcome_informative_cluster_size_protocol_from_json(
            PUBLIC_PROTOCOL.read_text()
        )
        report = clinical_outcome_informative_cluster_size_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        self.assertEqual(
            validate_clinical_outcome_informative_cluster_size_report(
                report,
                protocol,
                stress_protocol,
            ),
            (),
        )

    def test_public_profiles_reverse_direction_symmetrically(self) -> None:
        report = clinical_outcome_informative_cluster_size_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        benefit = _scenario_result(report, "unequal-informative-benefit-12")
        harm = _scenario_result(report, "unequal-informative-harm-12")
        self.assertEqual(
            benefit.favorable_prevalence_contrast_unit_minus_cluster,
            -harm.favorable_prevalence_contrast_unit_minus_cluster,
        )
        self.assertTrue(benefit.truth_direction_disagrees)
        self.assertTrue(harm.truth_direction_disagrees)
        self.assertEqual(benefit.unit_weighted_reference_direction.value, "above")
        self.assertEqual(
            benefit.cluster_balanced_reference_direction.value,
            "below",
        )
        self.assertEqual(harm.unit_weighted_reference_direction.value, "below")
        self.assertEqual(
            harm.cluster_balanced_reference_direction.value,
            "above",
        )
        for scenario in (benefit, harm):
            for method in ClinicalOutcomeClusterSizeMethod:
                cell = _reference_cell(scenario, method)
                self.assertLess(
                    abs(cell.target_bias),
                    abs(cell.alternate_estimand_bias),
                )

    def test_public_evidence_ledger_matches_report(self) -> None:
        stress_protocol = clinical_outcome_stress_protocol_from_json(
            PUBLIC_STRESS_PROTOCOL.read_text()
        )
        protocol = clinical_outcome_informative_cluster_size_protocol_from_json(
            PUBLIC_PROTOCOL.read_text()
        )
        report = clinical_outcome_informative_cluster_size_report_from_json(
            PUBLIC_REPORT.read_text()
        )
        entry = json.loads(PUBLIC_EVIDENCE.read_text())[
            "clinical_informative_cluster_size_synthetic"
        ]
        cells = tuple(
            cell
            for scenario in report.scenario_results
            for method in scenario.method_results
            for metric in method.metric_inference
            for cell in metric.grid_inference
        )
        reference_cells = tuple(
            cell
            for cell in cells
            if cell.metric is report.primary_metric
            and cell.log_imor == report.reference_log_imor
        )
        informative_eligible_ids = {
            scenario.scenario_id
            for scenario in report.scenario_results
            if scenario.production_eligible and scenario.truth_direction_disagrees
        }
        null_ids = {
            scenario.scenario_id
            for scenario in report.scenario_results
            if scenario.size_outcome_covariance == 0.0
        }
        cells_by_scenario = {
            scenario.scenario_id: tuple(
                cell
                for method in scenario.method_results
                for metric in method.metric_inference
                for cell in metric.grid_inference
            )
            for scenario in report.scenario_results
        }
        informative_reference = tuple(
            cell
            for scenario in report.scenario_results
            if scenario.scenario_id in informative_eligible_ids
            for method in scenario.method_results
            for cell in (
                _reference_cell(scenario, method.method),
            )
        )
        null_reference = tuple(
            cell
            for scenario in report.scenario_results
            if scenario.scenario_id in null_ids
            for method in scenario.method_results
            for cell in (
                _reference_cell(scenario, method.method),
            )
        )

        self.assertEqual(entry["protocol_fingerprint"], protocol.fingerprint)
        self.assertEqual(entry["report_fingerprint"], report.fingerprint)
        self.assertEqual(
            entry["stress_protocol_fingerprint"],
            stress_protocol.fingerprint,
        )
        self.assertEqual(entry["replicates_per_scenario"], report.replicates)
        self.assertEqual(entry["scenario_count"], len(report.scenario_results))
        self.assertEqual(entry["method_grid_metric_cells"], len(cells))
        self.assertEqual(
            entry["production_eligible_scenario_count"],
            sum(item.production_eligible for item in report.scenario_results),
        )
        self.assertEqual(
            entry["truth_direction_disagreement_scenario_count"],
            sum(item.truth_direction_disagrees for item in report.scenario_results),
        )
        self.assertEqual(
            entry["maximum_all_cell_absolute_own_target_bias"],
            max(abs(cell.target_bias) for cell in cells),
        )
        self.assertEqual(
            entry["maximum_reference_absolute_own_target_bias"],
            max(abs(cell.target_bias) for cell in reference_cells),
        )
        self.assertEqual(
            entry[
                "eligible_informative_reference_absolute_alternate_estimand_bias_range"
            ],
            [
                min(abs(cell.alternate_estimand_bias) for cell in informative_reference),
                max(abs(cell.alternate_estimand_bias) for cell in informative_reference),
            ],
        )
        self.assertEqual(
            entry["null_reference_standard_error_calibration_ratio_range"],
            [
                min(
                    cell.standard_error_to_empirical_sd_ratio
                    for cell in null_reference
                ),
                max(
                    cell.standard_error_to_empirical_sd_ratio
                    for cell in null_reference
                ),
            ],
        )
        self.assertEqual(
            entry[
                "eligible_informative_reference_standard_error_calibration_ratio_range"
            ],
            [
                min(
                    cell.standard_error_to_empirical_sd_ratio
                    for cell in informative_reference
                ),
                max(
                    cell.standard_error_to_empirical_sd_ratio
                    for cell in informative_reference
                ),
            ],
        )
        self.assertEqual(
            entry["standard_error_calibration_failure_cell_count"],
            sum(not cell.standard_error_calibration_target_met for cell in cells),
        )
        self.assertEqual(
            entry["all_cell_bias_yield_and_coverage_targets_met"],
            all(
                cell.bias_target_met
                and cell.interval_yield_target_met
                and cell.coverage_target_met
                for cell in cells
            ),
        )
        self.assertEqual(
            entry["all_null_all_cell_targets_met"],
            all(
                cell.calibration_target_met
                for scenario_id in null_ids
                for cell in cells_by_scenario[scenario_id]
            ),
        )
        self.assertEqual(
            entry["all_eligible_informative_all_cell_targets_met"],
            all(
                cell.calibration_target_met
                for scenario_id in informative_eligible_ids
                for cell in cells_by_scenario[scenario_id]
            ),
        )
        for field_name in (
            "automatic_estimand_selection_included",
            "delete_mj_estimand_correction_claimed",
            "fixed_block_profiles_across_replicates",
            "cluster_superpopulation_resampling_included",
            "dominant_cluster_override_allowed",
        ):
            self.assertEqual(entry[field_name], getattr(report, field_name))

    def test_report_contains_no_private_granularity_keys(self) -> None:
        forbidden = {
            "unit_id",
            "cluster_id",
            "block_id",
            "replicate_id",
            "labels",
            "outcomes",
            "evaluable_labels",
        }

        def walk(value) -> None:
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(json.loads(PUBLIC_REPORT.read_text()))

    def test_cli_analyze_validate_and_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = root / "protocol.json"
            stress_path = root / "stress.json"
            report_path = root / "report.json"
            protocol_path.write_text(
                json.dumps(
                    clinical_outcome_informative_cluster_size_protocol_envelope(
                        self.protocol
                    )
                )
            )
            stress_path.write_text(
                json.dumps(clinical_outcome_stress_protocol_envelope(self.stress_protocol))
            )
            base = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
            ]
            analyzed = subprocess.run(
                [
                    *base,
                    "analyze-informative-cluster-size",
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
            self.assertEqual(analyzed.returncode, 0, analyzed.stderr)
            self.assertEqual(
                clinical_outcome_informative_cluster_size_report_from_json(
                    report_path.read_text()
                ),
                self.report,
            )
            validated = subprocess.run(
                [
                    *base,
                    "validate-informative-cluster-size",
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
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["valid"])
            summarized = subprocess.run(
                [
                    *base,
                    "summarize-informative-cluster-size",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            self.assertEqual(
                json.loads(summarized.stdout),
                clinical_outcome_informative_cluster_size_summary(self.report),
            )


if __name__ == "__main__":
    unittest.main()
