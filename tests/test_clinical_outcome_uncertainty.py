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
from statistics import NormalDist

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery import (
    ClinicalCohortManifest,
    ClinicalCohortPackageBinding,
    ClinicalFavorableOutcomePrediction,
    ClinicalOutcomeAssessment,
    ClinicalOutcomeDependenceAssignment,
    ClinicalOutcomeDependenceManifest,
    ClinicalOutcomeDomain,
    ClinicalOutcomeManifest,
    ClinicalOutcomeSource,
    ClinicalOutcomeStatus,
    ClinicalOutcomeUncertaintyError,
    ClinicalOutcomeUncertaintyProtocol,
    ClinicalPredictionSubmission,
    ClusterInferenceStatus,
    RecordParseError,
    Stage,
    clinical_cohort_report_from_json,
    clinical_outcome_dependence_manifest_envelope,
    clinical_outcome_dependence_manifest_from_dict,
    clinical_outcome_dependence_manifest_from_json,
    clinical_outcome_manifest_from_json,
    clinical_outcome_protocol_from_json,
    clinical_outcome_report_from_json,
    clinical_outcome_uncertainty_protocol_envelope,
    clinical_outcome_uncertainty_protocol_from_dict,
    clinical_outcome_uncertainty_protocol_from_json,
    clinical_outcome_uncertainty_report_envelope,
    clinical_outcome_uncertainty_report_from_dict,
    clinical_outcome_uncertainty_report_from_json,
    clinical_outcome_uncertainty_summary,
    clinical_outcome_uncertainty_validation_summary,
    clinical_prediction_submission_from_json,
    evaluate_clinical_outcome_uncertainty,
    evaluate_clinical_outcomes,
    validate_clinical_outcome_uncertainty_report,
)
from agentic_drug_discovery.clinical_cohort import _aggregate_diagnostics
from tests.test_clinical_outcome_evaluation import (
    _digest,
    _evidence_unit_id,
    _synthetic_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "rl_env/specs"
COHORT_EXAMPLE = SPECS / "clinical_evidence_cohort_report.example.json"
OUTCOME_PROTOCOL_EXAMPLE = SPECS / "clinical_outcome_evaluation_protocol.example.json"
SUBMISSION_EXAMPLES = (
    SPECS / "clinical_prediction_submission.example.json",
    SPECS / "clinical_prediction_submission.relaxed.example.json",
)
OUTCOME_MANIFEST_EXAMPLE = SPECS / "clinical_outcome_manifest.example.json"
OUTCOME_REPORT_EXAMPLE = SPECS / "clinical_outcome_evaluation_report.example.json"
DEPENDENCE_SCHEMA = SPECS / "clinical_outcome_dependence_manifest.schema.json"
DEPENDENCE_EXAMPLE = SPECS / "clinical_outcome_dependence_manifest.example.json"
UNCERTAINTY_PROTOCOL_SCHEMA = (
    SPECS / "clinical_outcome_uncertainty_protocol.schema.json"
)
UNCERTAINTY_PROTOCOL_EXAMPLE = (
    SPECS / "clinical_outcome_uncertainty_protocol.example.json"
)
UNCERTAINTY_REPORT_SCHEMA = SPECS / "clinical_outcome_uncertainty_report.schema.json"
UNCERTAINTY_REPORT_EXAMPLE = SPECS / "clinical_outcome_uncertainty_report.example.json"
UNCERTAINTY_SUMMARY_SCHEMA = SPECS / "clinical_outcome_uncertainty_summary.schema.json"


def _public_artifacts():
    cohort = clinical_cohort_report_from_json(COHORT_EXAMPLE.read_text())
    outcome_protocol = clinical_outcome_protocol_from_json(
        OUTCOME_PROTOCOL_EXAMPLE.read_text()
    )
    submissions = tuple(
        clinical_prediction_submission_from_json(path.read_text())
        for path in SUBMISSION_EXAMPLES
    )
    outcome_manifest = clinical_outcome_manifest_from_json(
        OUTCOME_MANIFEST_EXAMPLE.read_text()
    )
    outcome_report = clinical_outcome_report_from_json(
        OUTCOME_REPORT_EXAMPLE.read_text()
    )
    dependence_manifest = clinical_outcome_dependence_manifest_from_json(
        DEPENDENCE_EXAMPLE.read_text()
    )
    uncertainty_protocol = clinical_outcome_uncertainty_protocol_from_json(
        UNCERTAINTY_PROTOCOL_EXAMPLE.read_text()
    )
    uncertainty_report = clinical_outcome_uncertainty_report_from_json(
        UNCERTAINTY_REPORT_EXAMPLE.read_text()
    )
    return (
        cohort,
        outcome_protocol,
        submissions,
        outcome_manifest,
        outcome_report,
        dependence_manifest,
        uncertainty_protocol,
        uncertainty_report,
    )


def _clustered_artifacts():
    base_cohort, base_protocol, _, _, _ = _synthetic_artifacts()
    diagnostics = []
    for unit_index in range(8):
        program_id = f"clustered-program-{unit_index}"
        synthesis_fingerprint = _digest(f"clustered-synthesis-{unit_index}")
        unit_id = _evidence_unit_id(program_id, synthesis_fingerprint)
        for base in base_cohort.packages:
            diagnostics.append(
                replace(
                    base,
                    package_id=f"{base.package_id}:clustered-{unit_index}",
                    program_id=program_id,
                    integrity_sha256=_digest(
                        f"{base.package_id}:clustered-{unit_index}:package"
                    ),
                    synthesis_id=f"clustered-synthesis-{unit_index}",
                    synthesis_fingerprint=synthesis_fingerprint,
                    evidence_unit_id=unit_id,
                    candidate_id=f"clustered-candidate-{unit_index}",
                    intervention_id=f"clustered-intervention-{unit_index}",
                    stage=(
                        Stage.CLINICAL_STRATEGY
                        if unit_index < 4
                        else Stage.REGULATORY_POSTMARKET
                    ),
                    trial_ids=(
                        f"NCT-BASE-{unit_index}-A",
                        f"NCT-BASE-{unit_index}-B",
                    ),
                    source_content_hashes=tuple(
                        sorted(
                            (
                                _digest(f"clustered-baseline-source-{unit_index}-a"),
                                _digest(f"clustered-baseline-source-{unit_index}-b"),
                            )
                        )
                    ),
                )
            )
    ordered = tuple(sorted(diagnostics, key=lambda item: item.sort_key))
    cohort_specification = _digest("synthetic eight-unit clustered cohort")
    cohort_manifest = ClinicalCohortManifest(
        cohort_id="synthetic-eight-unit-clustered-outcomes",
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
    cohort = replace(
        base_cohort,
        cohort_id=cohort_manifest.cohort_id,
        cohort_specification_sha256=cohort_specification,
        manifest_fingerprint=cohort_manifest.fingerprint,
        package_count=16,
        program_count=8,
        evidence_unit_count=8,
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
    outcome_protocol = replace(
        base_protocol,
        cohort_id=cohort.cohort_id,
        cohort_specification_sha256=cohort.cohort_specification_sha256,
        cohort_report_fingerprint=cohort.fingerprint,
        minimum_evaluable_units=4,
    )
    probabilities = {
        "synthetic-clinical-workflow-policy": (
            0.2,
            0.8,
            0.4,
            0.6,
            0.3,
            0.7,
            0.9,
            0.1,
        ),
        "synthetic-relaxed-clinical-workflow-policy": (
            0.7,
            0.3,
            0.6,
            0.4,
            0.8,
            0.2,
            0.4,
            0.9,
        ),
    }
    unit_index_by_id = {
        item.evidence_unit_id: int(item.program_id.rsplit("-", 1)[1])
        for item in cohort.packages
    }
    submissions = []
    for policy in sorted(
        {item.policy for item in cohort.packages},
        key=lambda item: item.sort_key,
    ):
        policy_packages = tuple(
            sorted(
                (item for item in cohort.packages if item.policy == policy),
                key=lambda item: (item.evidence_unit_id, item.package_id),
            )
        )
        submissions.append(
            ClinicalPredictionSubmission(
                submission_id=f"{policy.policy_id}:clustered:v1",
                protocol_id=outcome_protocol.protocol_id,
                protocol_fingerprint=outcome_protocol.fingerprint,
                cohort_report_fingerprint=cohort.fingerprint,
                policy=policy,
                submitted_on=outcome_protocol.prediction_deadline,
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
    assessments = []
    assignments = []
    for unit_index in range(8):
        diagnostic = next(
            item
            for item in cohort.packages
            if item.program_id == f"clustered-program-{unit_index}"
        )
        cluster_index = unit_index // 2
        endpoint_status = (
            ClinicalOutcomeStatus.INDETERMINATE
            if unit_index == 7
            else (
                ClinicalOutcomeStatus.FAVORABLE
                if unit_index % 2 == 0
                else ClinicalOutcomeStatus.UNFAVORABLE
            )
        )
        composite_status = endpoint_status
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
                assessment_date=outcome_protocol.outcome_window_end,
                endpoint_status=endpoint_status,
                safety_status=ClinicalOutcomeStatus.FAVORABLE,
                composite_status=composite_status,
                sources=(
                    ClinicalOutcomeSource(
                        source_id=f"clustered-future-source-{cluster_index}",
                        source_version="2025-01-10",
                        source_content_sha256=_digest(
                            f"clustered-future-source-{cluster_index}"
                        ),
                        available_on=date(2025, 1, 10),
                        domains=(
                            ClinicalOutcomeDomain.ENDPOINT,
                            ClinicalOutcomeDomain.SAFETY,
                        ),
                        trial_id=f"NCT-OUTCOME-CLUSTER-{cluster_index}",
                    ),
                ),
                endpoint_assessment_sha256=_digest(
                    f"clustered-endpoint-assessment-{unit_index}"
                ),
                safety_assessment_sha256=_digest(
                    f"clustered-safety-assessment-{unit_index}"
                ),
                adjudication_sha256=_digest(f"clustered-adjudication-{unit_index}"),
                independent_curator_count=2,
            )
        )
        assignments.append(
            ClinicalOutcomeDependenceAssignment(
                evidence_unit_id=diagnostic.evidence_unit_id,
                cluster_id=_digest(f"clustered-dependence-{cluster_index}"),
                assignment_basis_sha256=_digest(
                    f"clustered-dependence-basis-{cluster_index}"
                ),
            )
        )
    outcome_manifest = ClinicalOutcomeManifest(
        manifest_id="synthetic-clustered-outcomes:v1",
        protocol_id=outcome_protocol.protocol_id,
        protocol_fingerprint=outcome_protocol.fingerprint,
        cohort_report_fingerprint=cohort.fingerprint,
        curator_roster_commitment=outcome_protocol.curator_roster_commitment,
        frozen_on=date(2025, 1, 31),
        assessments=tuple(sorted(assessments, key=lambda item: item.evidence_unit_id)),
    )
    outcome_report = evaluate_clinical_outcomes(
        outcome_protocol,
        cohort,
        submissions,
        outcome_manifest,
    )
    dependence_manifest = ClinicalOutcomeDependenceManifest(
        manifest_id="synthetic-clustered-dependence:v1",
        registered_on=date(2025, 1, 3),
        cohort_report_fingerprint=cohort.fingerprint,
        construction_policy_sha256=_digest("clustered construction policy"),
        independence_attestation_sha256=_digest("clustered independence attestation"),
        assignments=tuple(sorted(assignments, key=lambda item: item.evidence_unit_id)),
    )
    uncertainty_protocol = ClinicalOutcomeUncertaintyProtocol(
        protocol_id="synthetic-clustered-uncertainty",
        version="1.0.0",
        registered_on=date(2025, 1, 3),
        outcome_protocol_id=outcome_protocol.protocol_id,
        outcome_protocol_fingerprint=outcome_protocol.fingerprint,
        cohort_report_fingerprint=cohort.fingerprint,
        dependence_manifest_fingerprint=dependence_manifest.fingerprint,
        confidence_level=0.95,
        minimum_clusters_overall=3,
        minimum_clusters_per_stratum=3,
        maximum_evaluable_cluster_fraction=0.4,
    )
    uncertainty_report = evaluate_clinical_outcome_uncertainty(
        uncertainty_protocol,
        dependence_manifest,
        outcome_protocol,
        cohort,
        submissions,
        outcome_manifest,
        outcome_report,
    )
    return (
        cohort,
        outcome_protocol,
        tuple(submissions),
        outcome_manifest,
        outcome_report,
        dependence_manifest,
        uncertainty_protocol,
        uncertainty_report,
    )


class ClinicalOutcomeUncertaintyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.public = _public_artifacts()
        cls.clustered = _clustered_artifacts()

    def test_schema_examples_and_public_replay_are_synchronized(self) -> None:
        schema_examples = (
            (DEPENDENCE_SCHEMA, DEPENDENCE_EXAMPLE),
            (UNCERTAINTY_PROTOCOL_SCHEMA, UNCERTAINTY_PROTOCOL_EXAMPLE),
            (UNCERTAINTY_REPORT_SCHEMA, UNCERTAINTY_REPORT_EXAMPLE),
        )
        for schema_path, example_path in schema_examples:
            schema = json.loads(schema_path.read_text())
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(json.loads(example_path.read_text()))
        Draft202012Validator(
            json.loads(UNCERTAINTY_REPORT_SCHEMA.read_text()),
            format_checker=FormatChecker(),
        ).validate(clinical_outcome_uncertainty_report_envelope(self.clustered[-1]))
        summary_schema = json.loads(UNCERTAINTY_SUMMARY_SCHEMA.read_text())
        Draft202012Validator.check_schema(summary_schema)
        expected_stages = [item.value for item in Stage]
        self.assertEqual(
            json.loads(UNCERTAINTY_REPORT_SCHEMA.read_text())["$defs"]["stage"][
                "enum"
            ],
            expected_stages,
        )
        self.assertEqual(summary_schema["$defs"]["stage"]["enum"], expected_stages)
        summary_validator = Draft202012Validator(summary_schema)
        summary_validator.validate(clinical_outcome_uncertainty_summary(self.public[-1]))
        summary_validator.validate(clinical_outcome_uncertainty_summary(self.clustered[-1]))
        summary_validator.validate(
            clinical_outcome_uncertainty_validation_summary(self.public[-1])
        )
        summary_validator.validate(
            clinical_outcome_uncertainty_validation_summary(
                self.public[-1],
                failures=("synthetic_replay_failure",),
            )
        )
        (
            cohort,
            outcome_protocol,
            submissions,
            outcome_manifest,
            outcome_report,
            dependence_manifest,
            uncertainty_protocol,
            uncertainty_report,
        ) = self.public
        self.assertEqual(
            clinical_outcome_dependence_manifest_envelope(dependence_manifest),
            json.loads(DEPENDENCE_EXAMPLE.read_text()),
        )
        self.assertEqual(
            clinical_outcome_uncertainty_protocol_envelope(uncertainty_protocol),
            json.loads(UNCERTAINTY_PROTOCOL_EXAMPLE.read_text()),
        )
        self.assertEqual(
            clinical_outcome_uncertainty_report_envelope(uncertainty_report),
            json.loads(UNCERTAINTY_REPORT_EXAMPLE.read_text()),
        )
        self.assertEqual(
            evaluate_clinical_outcome_uncertainty(
                uncertainty_protocol,
                dependence_manifest,
                outcome_protocol,
                cohort,
                submissions,
                outcome_manifest,
                outcome_report,
            ),
            uncertainty_report,
        )
        self.assertEqual(
            uncertainty_report.overall_cluster_diagnostic.status,
            ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
        )
        self.assertIsNone(uncertainty_report.policy_summaries[0].brier_score.lower)

    def test_multi_cluster_cr1_math_strata_and_paired_covariance(self) -> None:
        report = self.clustered[-1]
        diagnostic = report.overall_cluster_diagnostic
        self.assertEqual(
            (
                diagnostic.total_units,
                diagnostic.evaluable_units,
                diagnostic.indeterminate_units,
                diagnostic.cluster_count,
                diagnostic.evaluable_cluster_count,
            ),
            (8, 7, 1, 4, 4),
        )
        self.assertEqual(diagnostic.status, ClusterInferenceStatus.COMPUTED)
        self.assertAlmostEqual(
            diagnostic.largest_evaluable_cluster_fraction,
            2 / 7,
            places=12,
        )
        self.assertEqual(report.known_dependence_link_count, 4)
        self.assertEqual(len(report.stratum_summaries), 2)
        self.assertEqual(
            tuple(
                (
                    item.stage,
                    item.cluster_diagnostic.total_units,
                    item.cluster_diagnostic.evaluable_units,
                    item.cluster_diagnostic.evaluable_cluster_count,
                    item.cluster_diagnostic.status,
                )
                for item in report.stratum_summaries
            ),
            (
                (
                    Stage.CLINICAL_STRATEGY,
                    4,
                    4,
                    2,
                    ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
                ),
                (
                    Stage.REGULATORY_POSTMARKET,
                    4,
                    3,
                    2,
                    ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
                ),
            ),
        )
        self.assertTrue(
            all(
                item.policy_summaries[0].brier_score.lower is None
                for item in report.stratum_summaries
            )
        )

        summaries = {item.policy.policy_id: item for item in report.policy_summaries}
        strict = summaries["synthetic-clinical-workflow-policy"]
        relaxed = summaries["synthetic-relaxed-clinical-workflow-policy"]
        losses_strict = ((0.64, 0.64), (0.36, 0.36), (0.49, 0.49), (0.01,))
        losses_relaxed = ((0.09, 0.09), (0.16, 0.16), (0.04, 0.04), (0.36,))

        def expected(values: tuple[tuple[float, ...], ...]) -> tuple[float, float]:
            flattened = tuple(item for cluster in values for item in cluster)
            mean = sum(flattened) / len(flattened)
            variance = (
                len(values)
                / (len(values) - 1)
                * sum(sum(item - mean for item in cluster) ** 2 for cluster in values)
                / len(flattened) ** 2
            )
            return mean, math.sqrt(variance)

        strict_mean, strict_se = expected(losses_strict)
        relaxed_mean, relaxed_se = expected(losses_relaxed)
        self.assertAlmostEqual(strict.brier_score.estimate, strict_mean, places=12)
        self.assertAlmostEqual(strict.brier_score.standard_error, strict_se, places=12)
        self.assertAlmostEqual(relaxed.brier_score.estimate, relaxed_mean, places=12)
        self.assertAlmostEqual(
            relaxed.brier_score.standard_error, relaxed_se, places=12
        )
        z = NormalDist().inv_cdf(0.975)
        self.assertAlmostEqual(
            strict.brier_score.lower,
            max(0.0, strict_mean - z * strict_se),
            places=12,
        )
        self.assertAlmostEqual(
            strict.brier_score.upper,
            min(1.0, strict_mean + z * strict_se),
            places=12,
        )
        comparison = report.matched_policy_comparisons[0]
        self.assertAlmostEqual(
            comparison.brier_difference_b_minus_a.estimate,
            relaxed_mean - strict_mean,
            places=12,
        )
        self.assertEqual(
            comparison.brier_difference_b_minus_a.status,
            ClusterInferenceStatus.COMPUTED,
        )
        changed_observed_rate = replace(
            relaxed.observed_favorable_rate,
            standard_error=relaxed.observed_favorable_rate.standard_error + 0.001,
        )
        changed_relaxed = replace(
            relaxed,
            observed_favorable_rate=changed_observed_rate,
        )
        with self.assertRaisesRegex(ValueError, "share one observed favorable rate"):
            replace(report, policy_summaries=(strict, changed_relaxed))
        self.assertFalse(report.cluster_assignments_included)
        encoded = json.dumps(clinical_outcome_uncertainty_report_envelope(report))
        for assignment in self.clustered[5].assignments:
            self.assertNotIn(assignment.cluster_id, encoded)
            self.assertNotIn(assignment.evidence_unit_id, encoded)
            self.assertNotIn(assignment.assignment_basis_sha256, encoded)
        self.assertNotIn(self.clustered[5].construction_policy_sha256, encoded)
        self.assertNotIn(self.clustered[5].independence_attestation_sha256, encoded)
        self.assertEqual(
            validate_clinical_outcome_uncertainty_report(
                report,
                self.clustered[6],
                self.clustered[5],
                self.clustered[1],
                self.clustered[0],
                self.clustered[2],
                self.clustered[3],
                self.clustered[4],
            ),
            (),
        )

    def test_small_dominant_and_zero_variance_boards_fail_closed(self) -> None:
        (
            cohort,
            outcome_protocol,
            submissions,
            outcome_manifest,
            outcome_report,
            dependence_manifest,
            uncertainty_protocol,
            _,
        ) = self.clustered
        insufficient_protocol = replace(
            uncertainty_protocol,
            minimum_clusters_overall=5,
            minimum_clusters_per_stratum=5,
        )
        insufficient = evaluate_clinical_outcome_uncertainty(
            insufficient_protocol,
            dependence_manifest,
            outcome_protocol,
            cohort,
            submissions,
            outcome_manifest,
            outcome_report,
        )
        self.assertEqual(
            insufficient.overall_cluster_diagnostic.status,
            ClusterInferenceStatus.INSUFFICIENT_CLUSTERS,
        )
        self.assertIsNone(insufficient.policy_summaries[0].brier_score.lower)

        dominant_protocol = replace(
            uncertainty_protocol,
            maximum_evaluable_cluster_fraction=0.2,
        )
        dominant = evaluate_clinical_outcome_uncertainty(
            dominant_protocol,
            dependence_manifest,
            outcome_protocol,
            cohort,
            submissions,
            outcome_manifest,
            outcome_report,
        )
        self.assertEqual(
            dominant.overall_cluster_diagnostic.status,
            ClusterInferenceStatus.DOMINANT_CLUSTER,
        )
        self.assertIsNone(dominant.policy_summaries[0].brier_score.standard_error)

        raw_largest_fraction = 2 / 7
        boundary_protocol = replace(
            uncertainty_protocol,
            maximum_evaluable_cluster_fraction=raw_largest_fraction - 1e-14,
        )
        boundary = evaluate_clinical_outcome_uncertainty(
            boundary_protocol,
            dependence_manifest,
            outcome_protocol,
            cohort,
            submissions,
            outcome_manifest,
            outcome_report,
        )
        self.assertEqual(
            boundary.overall_cluster_diagnostic.status,
            ClusterInferenceStatus.DOMINANT_CLUSTER,
        )
        self.assertEqual(
            boundary.overall_cluster_diagnostic.largest_evaluable_cluster_fraction,
            round(raw_largest_fraction, 12),
        )
        with self.assertRaisesRegex(ValueError, "fraction is inconsistent"):
            replace(
                boundary.overall_cluster_diagnostic,
                largest_evaluable_cluster_fraction=0.1,
            )

        uniform_submissions = tuple(
            replace(
                submission,
                predictions=tuple(
                    replace(prediction, favorable_probability=0.5)
                    for prediction in submission.predictions
                ),
            )
            for submission in submissions
        )
        uniform_outcome_report = evaluate_clinical_outcomes(
            outcome_protocol,
            cohort,
            uniform_submissions,
            outcome_manifest,
        )
        zero_variance = evaluate_clinical_outcome_uncertainty(
            uncertainty_protocol,
            dependence_manifest,
            outcome_protocol,
            cohort,
            uniform_submissions,
            outcome_manifest,
            uniform_outcome_report,
        )
        self.assertTrue(
            all(
                item.brier_score.status is ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE
                for item in zero_variance.policy_summaries
            )
        )
        self.assertEqual(
            zero_variance.matched_policy_comparisons[
                0
            ].brier_difference_b_minus_a.status,
            ClusterInferenceStatus.ZERO_CLUSTER_VARIANCE,
        )

    def test_manifest_chronology_coverage_and_known_overlap_fail_closed(self) -> None:
        (
            cohort,
            outcome_protocol,
            submissions,
            outcome_manifest,
            outcome_report,
            dependence_manifest,
            uncertainty_protocol,
            _,
        ) = self.clustered
        with self.assertRaisesRegex(
            ClinicalOutcomeUncertaintyError,
            "exactly cover cohort",
        ):
            shortened = replace(
                dependence_manifest,
                assignments=dependence_manifest.assignments[:-1],
            )
            evaluate_clinical_outcome_uncertainty(
                replace(
                    uncertainty_protocol,
                    dependence_manifest_fingerprint=shortened.fingerprint,
                ),
                shortened,
                outcome_protocol,
                cohort,
                submissions,
                outcome_manifest,
                outcome_report,
            )

        late_manifest = replace(dependence_manifest, registered_on=date(2025, 1, 5))
        with self.assertRaisesRegex(
            ClinicalOutcomeUncertaintyError,
            "not frozen before submission",
        ):
            evaluate_clinical_outcome_uncertainty(
                replace(
                    uncertainty_protocol,
                    registered_on=date(2025, 1, 5),
                    dependence_manifest_fingerprint=late_manifest.fingerprint,
                ),
                late_manifest,
                outcome_protocol,
                cohort,
                submissions,
                outcome_manifest,
                outcome_report,
            )

        first = dependence_manifest.assignments[0]
        same_cluster_peer_index = next(
            index
            for index, item in enumerate(dependence_manifest.assignments[1:], start=1)
            if item.cluster_id == first.cluster_id
        )
        split_assignments = list(dependence_manifest.assignments)
        split_assignments[same_cluster_peer_index] = replace(
            split_assignments[same_cluster_peer_index],
            cluster_id=_digest("laundered dependence cluster"),
            assignment_basis_sha256=_digest("laundered dependence basis"),
        )
        split_manifest = replace(
            dependence_manifest,
            assignments=tuple(split_assignments),
        )
        with self.assertRaisesRegex(
            ClinicalOutcomeUncertaintyError,
            "dependence was split",
        ):
            evaluate_clinical_outcome_uncertainty(
                replace(
                    uncertainty_protocol,
                    dependence_manifest_fingerprint=split_manifest.fingerprint,
                ),
                split_manifest,
                outcome_protocol,
                cohort,
                submissions,
                outcome_manifest,
                outcome_report,
            )

    def test_strict_readers_reject_tampering_duplicates_and_nonfinite(self) -> None:
        round_trips = (
            (
                clinical_outcome_dependence_manifest_envelope(self.public[5]),
                clinical_outcome_dependence_manifest_from_dict,
                clinical_outcome_dependence_manifest_from_json,
                self.public[5],
            ),
            (
                clinical_outcome_uncertainty_protocol_envelope(self.public[6]),
                clinical_outcome_uncertainty_protocol_from_dict,
                clinical_outcome_uncertainty_protocol_from_json,
                self.public[6],
            ),
            (
                clinical_outcome_uncertainty_report_envelope(self.public[7]),
                clinical_outcome_uncertainty_report_from_dict,
                clinical_outcome_uncertainty_report_from_json,
                self.public[7],
            ),
        )
        for envelope, from_dict, from_json, expected in round_trips:
            self.assertEqual(from_dict(envelope), expected)
            self.assertEqual(from_json(json.dumps(envelope)), expected)
            tampered = copy.deepcopy(envelope)
            tampered["integrity_sha256"] = _digest("tampered uncertainty")
            with self.assertRaisesRegex(RecordParseError, "integrity mismatch"):
                from_dict(tampered)
            unknown = copy.deepcopy(envelope)
            unknown["unexpected"] = "rejected"
            with self.assertRaises(RecordParseError):
                from_dict(unknown)
            payload_field = next(
                key
                for key in envelope
                if key not in {"schema_version", "integrity_sha256"}
            )
            nested_unknown = copy.deepcopy(envelope)
            nested_unknown[payload_field]["unexpected"] = "rejected"
            with self.assertRaises(RecordParseError):
                from_dict(nested_unknown)
        encoded = json.dumps(
            clinical_outcome_uncertainty_report_envelope(self.public[7])
        )
        duplicate = encoded.replace(
            '"schema_version":',
            '"schema_version":"duplicate","schema_version":',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_outcome_uncertainty_report_from_json(duplicate)
        with self.assertRaisesRegex(RecordParseError, "non-finite"):
            clinical_outcome_uncertainty_report_from_json(
                encoded.replace('"estimate": 0.49', '"estimate": NaN')
            )
        with self.assertRaisesRegex(ValueError, "exactly cover policy pairs"):
            replace(self.public[7], matched_policy_comparisons=())
        diagnostic = self.public[7].overall_cluster_diagnostic
        with self.assertRaisesRegex(ValueError, "require an evaluable cluster"):
            replace(
                diagnostic,
                total_units=2,
                indeterminate_units=1,
                evaluable_cluster_count=0,
                clusters_without_evaluable_units=diagnostic.cluster_count,
            )

    def test_cli_evaluate_validate_and_summarize_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "uncertainty-report.json"
            base = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
            ]
            evaluate_args = [
                *base,
                "evaluate-uncertainty",
                "--uncertainty-protocol",
                str(UNCERTAINTY_PROTOCOL_EXAMPLE),
                "--dependence-manifest",
                str(DEPENDENCE_EXAMPLE),
                "--outcome-protocol",
                str(OUTCOME_PROTOCOL_EXAMPLE),
                "--cohort-report",
                str(COHORT_EXAMPLE),
                "--submission",
                str(SUBMISSION_EXAMPLES[0]),
                "--submission",
                str(SUBMISSION_EXAMPLES[1]),
                "--outcomes",
                str(OUTCOME_MANIFEST_EXAMPLE),
                "--outcome-report",
                str(OUTCOME_REPORT_EXAMPLE),
                "--output",
                str(output),
            ]
            completed = subprocess.run(
                evaluate_args,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(output.read_text()),
                json.loads(UNCERTAINTY_REPORT_EXAMPLE.read_text()),
            )
            refused = subprocess.run(
                evaluate_args,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(
                json.loads(output.read_text()),
                json.loads(UNCERTAINTY_REPORT_EXAMPLE.read_text()),
            )

            validate_args = [
                *base,
                "validate-uncertainty",
                "--report",
                str(output),
                "--uncertainty-protocol",
                str(UNCERTAINTY_PROTOCOL_EXAMPLE),
                "--dependence-manifest",
                str(DEPENDENCE_EXAMPLE),
                "--outcome-protocol",
                str(OUTCOME_PROTOCOL_EXAMPLE),
                "--cohort-report",
                str(COHORT_EXAMPLE),
                "--submission",
                str(SUBMISSION_EXAMPLES[0]),
                "--submission",
                str(SUBMISSION_EXAMPLES[1]),
                "--outcomes",
                str(OUTCOME_MANIFEST_EXAMPLE),
                "--outcome-report",
                str(OUTCOME_REPORT_EXAMPLE),
            ]
            validated = subprocess.run(
                validate_args,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(
                json.loads(validated.stdout)["validation"]["status"], "valid"
            )

            summarized = subprocess.run(
                [*base, "summarize-uncertainty", "--report", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            summary = json.loads(summarized.stdout)
            self.assertEqual(
                summary["cluster_status"],
                ClusterInferenceStatus.INSUFFICIENT_CLUSTERS.value,
            )
            self.assertFalse(summary["cluster_assignments_included"])
            self.assertFalse(summary["unit_level_predictions_included"])
            self.assertFalse(summary["unit_level_outcomes_included"])
            self.assertFalse(summary["ece_cluster_interval_included"])
            self.assertFalse(summary["policy_superiority_test_included"])
            self.assertEqual(
                summary["policy_summaries"][0]["observed_favorable_rate"]["estimate"],
                1.0,
            )
            self.assertEqual(summary["stratum_count"], len(summary["strata"]))
            self.assertEqual(summary["clusters"]["minimum_required"], 2)
            self.assertEqual(summary["clusters"]["maximum_allowed_fraction"], 0.5)
            self.assertEqual(
                summary["strata"][0]["policy_summaries"][0]["brier_score"][
                    "estimate"
                ],
                0.49,
            )
            self.assertEqual(
                summary["matched_policy_comparison_count"],
                len(summary["matched_policy_comparisons"]),
            )
            self.assertEqual(
                summary["matched_policy_comparisons"][0]["shared_outcome_units"],
                {"total": 1, "evaluable": 1, "indeterminate": 0},
            )
            self.assertEqual(
                summary["matched_policy_comparisons"][0][
                    "brier_difference_b_minus_a"
                ]["estimate"],
                -0.45,
            )


if __name__ == "__main__":
    unittest.main()
