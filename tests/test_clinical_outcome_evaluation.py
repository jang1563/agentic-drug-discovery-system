from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    ClinicalCohortManifest,
    ClinicalCohortPackageBinding,
    ClinicalFavorableOutcomePrediction,
    ClinicalOutcomeAssessment,
    ClinicalOutcomeDomain,
    ClinicalOutcomeEvaluationError,
    ClinicalOutcomeEvaluationProtocol,
    ClinicalOutcomeManifest,
    ClinicalOutcomeSource,
    ClinicalOutcomeStatus,
    ClinicalPredictionSubmission,
    RecordParseError,
    clinical_cohort_report_from_json,
    clinical_outcome_evaluation_summary,
    clinical_outcome_manifest_envelope,
    clinical_outcome_manifest_from_dict,
    clinical_outcome_manifest_from_json,
    clinical_outcome_protocol_envelope,
    clinical_outcome_protocol_from_dict,
    clinical_outcome_protocol_from_json,
    clinical_outcome_report_envelope,
    clinical_outcome_report_from_dict,
    clinical_outcome_report_from_json,
    clinical_prediction_submission_envelope,
    clinical_prediction_submission_from_dict,
    clinical_prediction_submission_from_json,
    evaluate_clinical_outcomes,
    validate_clinical_outcome_evaluation_report,
)
from agentic_drug_discovery.clinical_cohort import _aggregate_diagnostics


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
COHORT_REPORT_EXAMPLE = SPECS / "clinical_evidence_cohort_report.example.json"
PROTOCOL_SCHEMA = SPECS / "clinical_outcome_evaluation_protocol.schema.json"
PROTOCOL_EXAMPLE = SPECS / "clinical_outcome_evaluation_protocol.example.json"
SUBMISSION_SCHEMA = SPECS / "clinical_prediction_submission.schema.json"
SUBMISSION_EXAMPLE = SPECS / "clinical_prediction_submission.example.json"
RELAXED_SUBMISSION_EXAMPLE = (
    SPECS / "clinical_prediction_submission.relaxed.example.json"
)
OUTCOME_SCHEMA = SPECS / "clinical_outcome_manifest.schema.json"
OUTCOME_EXAMPLE = SPECS / "clinical_outcome_manifest.example.json"
REPORT_SCHEMA = SPECS / "clinical_outcome_evaluation_report.schema.json"
REPORT_EXAMPLE = SPECS / "clinical_outcome_evaluation_report.example.json"
SUMMARY_SCHEMA = SPECS / "clinical_outcome_evaluation_summary.schema.json"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence_unit_id(program_id: str, synthesis_fingerprint: str) -> str:
    payload = json.dumps(
        {
            "program_id": program_id,
            "synthesis_fingerprint": synthesis_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _synthetic_artifacts():
    cohort_report = clinical_cohort_report_from_json(
        COHORT_REPORT_EXAMPLE.read_text(encoding="utf-8")
    )
    protocol = ClinicalOutcomeEvaluationProtocol(
        protocol_id="synthetic-clinical-outcome-evaluation",
        version="1.0.0",
        registered_on=date(2025, 1, 3),
        cohort_id=cohort_report.cohort_id,
        cohort_specification_sha256=(cohort_report.cohort_specification_sha256),
        cohort_report_fingerprint=cohort_report.fingerprint,
        prediction_deadline=date(2025, 1, 4),
        outcome_window_start=date(2025, 1, 5),
        outcome_window_end=date(2025, 1, 30),
        endpoint_harmonization_policy_sha256=_digest(
            "synthetic endpoint harmonization policy"
        ),
        safety_harmonization_policy_sha256=_digest(
            "synthetic safety harmonization policy"
        ),
        outcome_definition_sha256=_digest(
            "synthetic favorable composite benefit-risk outcome definition"
        ),
        label_guidance_sha256=_digest("synthetic outcome label guidance"),
        exclusion_rules_sha256=_digest("synthetic outcome exclusion rules"),
        curator_roster_commitment=_digest("synthetic blinded curator roster"),
        minimum_independent_curators=2,
        minimum_evaluable_units=1,
        classification_threshold=0.5,
        calibration_bin_edges=(0.0, 0.25, 0.5, 0.75, 1.0),
        confidence_level=0.95,
        metadata={"dataset_scope": "synthetic contract test only"},
    )
    probabilities = {
        "synthetic-clinical-workflow-policy": 0.3,
        "synthetic-relaxed-clinical-workflow-policy": 0.8,
    }
    submissions = tuple(
        ClinicalPredictionSubmission(
            submission_id=f"{diagnostic.policy.policy_id}:submission:v1",
            protocol_id=protocol.protocol_id,
            protocol_fingerprint=protocol.fingerprint,
            cohort_report_fingerprint=cohort_report.fingerprint,
            policy=diagnostic.policy,
            submitted_on=date(2025, 1, 4),
            predictions=(
                ClinicalFavorableOutcomePrediction(
                    package_id=diagnostic.package_id,
                    package_integrity_sha256=diagnostic.integrity_sha256,
                    evidence_unit_id=diagnostic.evidence_unit_id,
                    favorable_probability=probabilities[diagnostic.policy.policy_id],
                ),
            ),
            metadata={"forecast_scope": "synthetic package-bound probability"},
        )
        for diagnostic in cohort_report.packages
    )
    diagnostic = cohort_report.packages[0]
    assessment = ClinicalOutcomeAssessment(
        evidence_unit_id=diagnostic.evidence_unit_id,
        program_id=diagnostic.program_id,
        disease_id=diagnostic.disease_id,
        candidate_id=diagnostic.candidate_id,
        intervention_id=diagnostic.intervention_id,
        endpoint_mapping_id=diagnostic.endpoint_mapping_id,
        endpoint_family=diagnostic.endpoint_family,
        stage=diagnostic.stage,
        assessment_date=date(2025, 1, 30),
        endpoint_status=ClinicalOutcomeStatus.FAVORABLE,
        safety_status=ClinicalOutcomeStatus.FAVORABLE,
        composite_status=ClinicalOutcomeStatus.FAVORABLE,
        sources=(
            ClinicalOutcomeSource(
                source_id="synthetic-post-cutoff-clinical-source",
                source_version="2025-01-10",
                source_content_sha256=_digest(
                    "synthetic post-cutoff endpoint and safety source"
                ),
                available_on=date(2025, 1, 10),
                domains=(
                    ClinicalOutcomeDomain.ENDPOINT,
                    ClinicalOutcomeDomain.SAFETY,
                ),
                trial_id="NCT00000001",
            ),
        ),
        endpoint_assessment_sha256=_digest("synthetic blinded endpoint assessment"),
        safety_assessment_sha256=_digest("synthetic blinded safety assessment"),
        adjudication_sha256=_digest("synthetic independent adjudication"),
        independent_curator_count=2,
    )
    outcome_manifest = ClinicalOutcomeManifest(
        manifest_id="synthetic-clinical-outcomes:v1",
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        cohort_report_fingerprint=cohort_report.fingerprint,
        curator_roster_commitment=protocol.curator_roster_commitment,
        frozen_on=date(2025, 1, 31),
        assessments=(assessment,),
    )
    report = evaluate_clinical_outcomes(
        protocol,
        cohort_report,
        submissions,
        outcome_manifest,
    )
    return cohort_report, protocol, submissions, outcome_manifest, report


class ClinicalOutcomeEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.cohort_report,
            cls.protocol,
            cls.submissions,
            cls.outcome_manifest,
            cls.report,
        ) = _synthetic_artifacts()

    def test_schema_examples_and_compiler_output_are_synchronized(self) -> None:
        schema_paths = (
            PROTOCOL_SCHEMA,
            SUBMISSION_SCHEMA,
            OUTCOME_SCHEMA,
            REPORT_SCHEMA,
            SUMMARY_SCHEMA,
        )
        schemas = [
            json.loads(path.read_text(encoding="utf-8")) for path in schema_paths
        ]
        for schema in schemas:
            Draft202012Validator.check_schema(schema)

        protocol_example = json.loads(PROTOCOL_EXAMPLE.read_text(encoding="utf-8"))
        submission_examples = tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in (SUBMISSION_EXAMPLE, RELAXED_SUBMISSION_EXAMPLE)
        )
        outcome_example = json.loads(OUTCOME_EXAMPLE.read_text(encoding="utf-8"))
        report_example = json.loads(REPORT_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator(schemas[0]).validate(protocol_example)
        for submission in submission_examples:
            Draft202012Validator(schemas[1]).validate(submission)
        Draft202012Validator(schemas[2]).validate(outcome_example)
        Draft202012Validator(schemas[3]).validate(report_example)
        Draft202012Validator(schemas[4]).validate(
            clinical_outcome_evaluation_summary(self.report)
        )

        self.assertEqual(
            protocol_example,
            clinical_outcome_protocol_envelope(self.protocol),
        )
        self.assertEqual(
            submission_examples,
            tuple(
                clinical_prediction_submission_envelope(item)
                for item in self.submissions
            ),
        )
        self.assertEqual(
            outcome_example,
            clinical_outcome_manifest_envelope(self.outcome_manifest),
        )
        self.assertEqual(report_example, clinical_outcome_report_envelope(self.report))

    def test_probability_metrics_and_paired_policy_comparison(self) -> None:
        summaries = {
            item.policy.policy_id: item for item in self.report.policy_summaries
        }
        strict = summaries["synthetic-clinical-workflow-policy"]
        relaxed = summaries["synthetic-relaxed-clinical-workflow-policy"]
        self.assertEqual(strict.brier_score, 0.49)
        self.assertEqual(relaxed.brier_score, 0.04)
        self.assertEqual(strict.classification_accuracy.estimate, 0.0)
        self.assertEqual(relaxed.classification_accuracy.estimate, 1.0)
        self.assertEqual(strict.calibration_in_the_large, -0.7)
        self.assertEqual(relaxed.calibration_in_the_large, -0.2)
        self.assertEqual(
            self.report.calibration_status,
            "preregistered_outcome_calibration_estimable",
        )
        self.assertTrue(self.report.aggregate_outcomes_included)
        self.assertFalse(self.report.unit_level_predictions_included)
        self.assertFalse(self.report.unit_level_outcomes_included)
        self.assertFalse(self.report.package_decisions_scored_as_outcomes)

        comparison = self.report.matched_policy_comparisons[0]
        self.assertEqual(comparison.shared_evaluable_units, 1)
        self.assertEqual(comparison.policy_b_lower_brier_units, 1)
        self.assertEqual(comparison.mean_brier_difference_b_minus_a, -0.45)
        self.assertEqual(comparison.classification_disagreement_units, 1)
        self.assertEqual(
            validate_clinical_outcome_evaluation_report(
                self.report,
                self.protocol,
                self.cohort_report,
                self.submissions,
                self.outcome_manifest,
            ),
            (),
        )

    def test_indeterminate_outcome_retains_attrition_and_null_metrics(self) -> None:
        assessment = replace(
            self.outcome_manifest.assessments[0],
            endpoint_status=ClinicalOutcomeStatus.INDETERMINATE,
            composite_status=ClinicalOutcomeStatus.INDETERMINATE,
        )
        manifest = replace(self.outcome_manifest, assessments=(assessment,))
        report = evaluate_clinical_outcomes(
            self.protocol,
            self.cohort_report,
            self.submissions,
            manifest,
        )
        self.assertEqual(report.evaluable_outcome_unit_count, 0)
        self.assertEqual(report.indeterminate_outcome_unit_count, 1)
        self.assertEqual(
            report.calibration_status,
            "not_estimable_insufficient_evaluable_units",
        )
        for summary in report.policy_summaries:
            self.assertEqual(summary.evaluable_units, 0)
            self.assertIsNone(summary.brier_score)
            self.assertIsNone(summary.classification_accuracy.estimate)
            self.assertFalse(summary.evaluation_requirement_met)

    def test_multi_unit_calibration_attrition_and_outcome_overlap(self) -> None:
        diagnostics = []
        for unit_index in range(3):
            program_id = f"synthetic-program-{unit_index}"
            synthesis_fingerprint = _digest(f"synthetic-synthesis-{unit_index}")
            unit_id = _evidence_unit_id(program_id, synthesis_fingerprint)
            for base in self.cohort_report.packages:
                diagnostics.append(
                    replace(
                        base,
                        package_id=f"{base.package_id}:unit-{unit_index}",
                        program_id=program_id,
                        integrity_sha256=_digest(
                            f"{base.package_id}:unit-{unit_index}:package"
                        ),
                        synthesis_id=f"synthetic-synthesis-{unit_index}",
                        synthesis_fingerprint=synthesis_fingerprint,
                        evidence_unit_id=unit_id,
                        candidate_id=f"synthetic-candidate-{unit_index}",
                        intervention_id=f"synthetic-intervention-{unit_index}",
                        trial_ids=(
                            f"NCT{unit_index:08d}1",
                            f"NCT{unit_index:08d}2",
                        ),
                        source_content_hashes=tuple(
                            sorted(
                                (
                                    _digest(f"baseline-{unit_index}-a"),
                                    _digest(f"baseline-{unit_index}-b"),
                                )
                            )
                        ),
                    )
                )
        ordered = tuple(sorted(diagnostics, key=lambda item: item.sort_key))
        cohort_specification = _digest("synthetic three-unit cohort")
        manifest = ClinicalCohortManifest(
            cohort_id="synthetic-three-unit-clinical-outcomes",
            cohort_specification_sha256=cohort_specification,
            package_bindings=tuple(
                sorted(
                    (
                        ClinicalCohortPackageBinding(
                            package_id=item.package_id,
                            program_id=item.program_id,
                            integrity_sha256=item.integrity_sha256,
                        )
                        for item in ordered
                    ),
                    key=lambda item: (item.program_id, item.package_id),
                )
            ),
        )
        aggregate = _aggregate_diagnostics(ordered)
        cohort_report = replace(
            self.cohort_report,
            cohort_id=manifest.cohort_id,
            cohort_specification_sha256=cohort_specification,
            manifest_fingerprint=manifest.fingerprint,
            package_count=6,
            program_count=3,
            evidence_unit_count=3,
            packages=ordered,
            decisions=aggregate["decisions"],
            dimensions=aggregate["dimensions"],
            gaps=aggregate["gaps"],
            actions=aggregate["actions"],
            policy_strata=aggregate["policy_strata"],
            matched_policy_comparisons=aggregate["matched_policy_comparisons"],
            provenance_overlaps=aggregate["provenance_overlaps"],
            evidence_units_source_disjoint=aggregate["evidence_units_source_disjoint"],
            evidence_units_trial_disjoint=aggregate["evidence_units_trial_disjoint"],
        )
        protocol = replace(
            self.protocol,
            cohort_id=cohort_report.cohort_id,
            cohort_specification_sha256=cohort_report.cohort_specification_sha256,
            cohort_report_fingerprint=cohort_report.fingerprint,
            minimum_evaluable_units=2,
        )
        probabilities = {
            "synthetic-clinical-workflow-policy": (0.2, 0.7, 0.4),
            "synthetic-relaxed-clinical-workflow-policy": (0.8, 0.6, 0.5),
        }
        unit_index_by_id = {
            item.evidence_unit_id: int(item.program_id.rsplit("-", 1)[1])
            for item in cohort_report.packages
        }
        submissions = []
        for policy in sorted(
            {item.policy for item in cohort_report.packages},
            key=lambda item: item.sort_key,
        ):
            policy_packages = tuple(
                sorted(
                    (item for item in cohort_report.packages if item.policy == policy),
                    key=lambda item: (item.evidence_unit_id, item.package_id),
                )
            )
            submissions.append(
                ClinicalPredictionSubmission(
                    submission_id=f"{policy.policy_id}:three-unit:v1",
                    protocol_id=protocol.protocol_id,
                    protocol_fingerprint=protocol.fingerprint,
                    cohort_report_fingerprint=cohort_report.fingerprint,
                    policy=policy,
                    submitted_on=protocol.prediction_deadline,
                    predictions=tuple(
                        ClinicalFavorableOutcomePrediction(
                            package_id=item.package_id,
                            package_integrity_sha256=item.integrity_sha256,
                            evidence_unit_id=item.evidence_unit_id,
                            favorable_probability=probabilities[policy.policy_id][
                                unit_index_by_id[item.evidence_unit_id]
                            ],
                        )
                        for item in policy_packages
                    ),
                )
            )
        status_pairs = (
            (
                ClinicalOutcomeStatus.FAVORABLE,
                ClinicalOutcomeStatus.FAVORABLE,
            ),
            (
                ClinicalOutcomeStatus.UNFAVORABLE,
                ClinicalOutcomeStatus.FAVORABLE,
            ),
            (
                ClinicalOutcomeStatus.INDETERMINATE,
                ClinicalOutcomeStatus.FAVORABLE,
            ),
        )
        assessments = []
        for unit_index in range(3):
            diagnostic = next(
                item
                for item in cohort_report.packages
                if item.program_id == f"synthetic-program-{unit_index}"
            )
            endpoint_status, safety_status = status_pairs[unit_index]
            composite_status = (
                ClinicalOutcomeStatus.UNFAVORABLE
                if ClinicalOutcomeStatus.UNFAVORABLE in (endpoint_status, safety_status)
                else (
                    ClinicalOutcomeStatus.FAVORABLE
                    if endpoint_status is ClinicalOutcomeStatus.FAVORABLE
                    and safety_status is ClinicalOutcomeStatus.FAVORABLE
                    else ClinicalOutcomeStatus.INDETERMINATE
                )
            )
            shared = unit_index < 2
            assessments.append(
                ClinicalOutcomeAssessment(
                    evidence_unit_id=diagnostic.evidence_unit_id,
                    program_id=diagnostic.program_id,
                    disease_id=diagnostic.disease_id,
                    candidate_id=diagnostic.candidate_id,
                    intervention_id=diagnostic.intervention_id,
                    endpoint_mapping_id=diagnostic.endpoint_mapping_id,
                    endpoint_family=diagnostic.endpoint_family,
                    stage=diagnostic.stage,
                    assessment_date=self.protocol.outcome_window_end,
                    endpoint_status=endpoint_status,
                    safety_status=safety_status,
                    composite_status=composite_status,
                    sources=(
                        ClinicalOutcomeSource(
                            source_id=(
                                "shared-future-source"
                                if shared
                                else "unique-future-source"
                            ),
                            source_version="2025-01-10",
                            source_content_sha256=_digest(
                                "shared future outcome source"
                                if shared
                                else "unique future outcome source"
                            ),
                            available_on=date(2025, 1, 10),
                            domains=(
                                ClinicalOutcomeDomain.ENDPOINT,
                                ClinicalOutcomeDomain.SAFETY,
                            ),
                            trial_id=("NCT-SHARED" if shared else "NCT-UNIQUE"),
                        ),
                    ),
                    endpoint_assessment_sha256=_digest(
                        f"endpoint-assessment-{unit_index}"
                    ),
                    safety_assessment_sha256=_digest(f"safety-assessment-{unit_index}"),
                    adjudication_sha256=_digest(f"adjudication-{unit_index}"),
                    independent_curator_count=2,
                )
            )
        manifest = ClinicalOutcomeManifest(
            manifest_id="synthetic-three-unit-outcomes:v1",
            protocol_id=protocol.protocol_id,
            protocol_fingerprint=protocol.fingerprint,
            cohort_report_fingerprint=cohort_report.fingerprint,
            curator_roster_commitment=protocol.curator_roster_commitment,
            frozen_on=self.outcome_manifest.frozen_on,
            assessments=tuple(
                sorted(assessments, key=lambda item: item.evidence_unit_id)
            ),
        )
        report = evaluate_clinical_outcomes(
            protocol,
            cohort_report,
            submissions,
            manifest,
        )
        self.assertEqual(
            (
                report.outcome_unit_count,
                report.evaluable_outcome_unit_count,
                report.indeterminate_outcome_unit_count,
            ),
            (3, 2, 1),
        )
        self.assertEqual(report.outcome_cross_unit_source_overlap_count, 1)
        self.assertEqual(report.outcome_cross_unit_trial_overlap_count, 1)
        self.assertFalse(report.outcome_units_source_disjoint)
        self.assertFalse(report.outcome_units_trial_disjoint)
        summaries = {item.policy.policy_id: item for item in report.policy_summaries}
        self.assertEqual(
            summaries["synthetic-clinical-workflow-policy"].brier_score,
            0.565,
        )
        self.assertEqual(
            summaries["synthetic-relaxed-clinical-workflow-policy"].brier_score,
            0.2,
        )
        self.assertTrue(
            all(item.evaluation_requirement_met for item in report.policy_summaries)
        )
        comparison = report.matched_policy_comparisons[0]
        self.assertEqual(comparison.shared_units, 3)
        self.assertEqual(comparison.shared_evaluable_units, 2)
        self.assertEqual(comparison.shared_indeterminate_units, 1)
        self.assertEqual(comparison.policy_b_lower_brier_units, 2)
        self.assertEqual(comparison.classification_disagreement_units, 1)

        rebound_source = replace(
            assessments[1].sources[0],
            source_id="rebound-shared-source",
        )
        rebound_assessments = (
            assessments[0],
            replace(assessments[1], sources=(rebound_source,)),
            assessments[2],
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "content hash is rebound",
        ):
            evaluate_clinical_outcomes(
                protocol,
                cohort_report,
                submissions,
                replace(
                    manifest,
                    assessments=tuple(
                        sorted(
                            rebound_assessments,
                            key=lambda item: item.evidence_unit_id,
                        )
                    ),
                ),
            )

    def test_cutoff_source_and_package_bindings_fail_closed(self) -> None:
        early_source = replace(
            self.outcome_manifest.assessments[0].sources[0],
            available_on=self.protocol.prediction_deadline,
        )
        early_assessment = replace(
            self.outcome_manifest.assessments[0],
            sources=(early_source,),
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "cutoff-safe availability",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions,
                replace(self.outcome_manifest, assessments=(early_assessment,)),
            )

        postdated_source = replace(
            self.outcome_manifest.assessments[0].sources[0],
            available_on=self.outcome_manifest.frozen_on,
        )
        postdated_assessment = replace(
            self.outcome_manifest.assessments[0],
            sources=(postdated_source,),
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "source postdates its assessment",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions,
                replace(self.outcome_manifest, assessments=(postdated_assessment,)),
            )

        baseline_source = replace(
            early_source,
            available_on=date(2025, 1, 10),
            source_content_sha256=(
                self.cohort_report.packages[0].source_content_hashes[0]
            ),
        )
        baseline_assessment = replace(
            self.outcome_manifest.assessments[0],
            sources=(baseline_source,),
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "reuses a baseline content hash",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions,
                replace(self.outcome_manifest, assessments=(baseline_assessment,)),
            )

        prediction = replace(
            self.submissions[0].predictions[0],
            package_integrity_sha256=_digest("rebound package"),
        )
        submission = replace(self.submissions[0], predictions=(prediction,))
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "prediction package binding",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                (submission, self.submissions[1]),
                self.outcome_manifest,
            )

    def test_roster_identity_and_exact_coverage_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "exactly cover cohort policies",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions[:1],
                self.outcome_manifest,
            )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "curator roster",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions,
                replace(
                    self.outcome_manifest,
                    curator_roster_commitment=_digest("rebound roster"),
                ),
            )
        assessment = replace(
            self.outcome_manifest.assessments[0],
            candidate_id="rebound-candidate",
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeEvaluationError,
            "outcome identity",
        ):
            evaluate_clinical_outcomes(
                self.protocol,
                self.cohort_report,
                self.submissions,
                replace(self.outcome_manifest, assessments=(assessment,)),
            )

        with self.assertRaisesRegex(ValueError, "submission metadata"):
            replace(
                self.submissions[0],
                metadata={"futureOutcome": "favorable"},
            )

        with self.assertRaisesRegex(
            ValueError,
            "exactly cover policy pairs",
        ):
            replace(self.report, matched_policy_comparisons=())

        first_summary = self.report.policy_summaries[0]
        inconsistent_summary = replace(
            first_summary,
            total_units=first_summary.total_units + 1,
            indeterminate_units=first_summary.indeterminate_units + 1,
        )
        with self.assertRaisesRegex(
            ValueError,
            "attrition must match the shared outcome cohort",
        ):
            replace(
                self.report,
                policy_summaries=(
                    inconsistent_summary,
                    *self.report.policy_summaries[1:],
                ),
            )

    def test_strict_readers_reject_tampering_duplicates_and_non_finite(self) -> None:
        round_trips = (
            (
                clinical_outcome_protocol_envelope(self.protocol),
                clinical_outcome_protocol_from_dict,
                clinical_outcome_protocol_from_json,
                self.protocol,
            ),
            (
                clinical_prediction_submission_envelope(self.submissions[0]),
                clinical_prediction_submission_from_dict,
                clinical_prediction_submission_from_json,
                self.submissions[0],
            ),
            (
                clinical_outcome_manifest_envelope(self.outcome_manifest),
                clinical_outcome_manifest_from_dict,
                clinical_outcome_manifest_from_json,
                self.outcome_manifest,
            ),
            (
                clinical_outcome_report_envelope(self.report),
                clinical_outcome_report_from_dict,
                clinical_outcome_report_from_json,
                self.report,
            ),
        )
        for envelope, from_dict, from_json, expected in round_trips:
            self.assertEqual(from_dict(envelope), expected)
            self.assertEqual(from_json(json.dumps(envelope)), expected)
            tampered = copy.deepcopy(envelope)
            tampered["integrity_sha256"] = _digest("tampered")
            with self.assertRaisesRegex(RecordParseError, "integrity mismatch"):
                from_dict(tampered)

        encoded = json.dumps(clinical_outcome_report_envelope(self.report))
        duplicate = encoded.replace(
            '"schema_version":',
            '"schema_version":"duplicate","schema_version":',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_outcome_report_from_json(duplicate)
        with self.assertRaisesRegex(RecordParseError, "non-finite"):
            clinical_outcome_report_from_json(
                encoded.replace('"brier_score": 0.49', '"brier_score": NaN')
            )

    def test_cli_evaluate_validate_and_summarize_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {
                "protocol": root / "protocol.json",
                "submission_a": root / "submission-a.json",
                "submission_b": root / "submission-b.json",
                "outcomes": root / "outcomes.json",
                "report": root / "report.json",
            }
            payloads = {
                "protocol": clinical_outcome_protocol_envelope(self.protocol),
                "submission_a": clinical_prediction_submission_envelope(
                    self.submissions[0]
                ),
                "submission_b": clinical_prediction_submission_envelope(
                    self.submissions[1]
                ),
                "outcomes": clinical_outcome_manifest_envelope(self.outcome_manifest),
            }
            for key, payload in payloads.items():
                paths[key].write_text(
                    json.dumps(payload, indent=2) + "\n",
                    encoding="utf-8",
                )
            command = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
                "evaluate-outcomes",
                "--protocol",
                str(paths["protocol"]),
                "--cohort-report",
                str(COHORT_REPORT_EXAMPLE),
                "--submission",
                str(paths["submission_a"]),
                "--submission",
                str(paths["submission_b"]),
                "--outcomes",
                str(paths["outcomes"]),
                "--output",
                str(paths["report"]),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                json.loads(completed.stdout)["validation"]["status"], "valid"
            )
            self.assertEqual(
                clinical_outcome_report_from_json(
                    paths["report"].read_text(encoding="utf-8")
                ),
                self.report,
            )
            collision = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(collision.returncode, 2)
            self.assertIn("already exists", collision.stderr)

            validate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "validate-outcomes",
                    "--report",
                    str(paths["report"]),
                    "--protocol",
                    str(paths["protocol"]),
                    "--cohort-report",
                    str(COHORT_REPORT_EXAMPLE),
                    "--submission",
                    str(paths["submission_a"]),
                    "--submission",
                    str(paths["submission_b"]),
                    "--outcomes",
                    str(paths["outcomes"]),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                json.loads(validate.stdout)["validation"]["status"], "valid"
            )
            summary = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize-outcomes",
                    "--report",
                    str(paths["report"]),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(summary.stdout)["outcome_units"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
