from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    BudgetState,
    ClinicalCohortError,
    ClinicalCohortManifest,
    ClinicalCohortPackageBinding,
    ClinicalDecisionPackage,
    RecordParseError,
    clinical_cohort_manifest_envelope,
    clinical_cohort_manifest_from_dict,
    clinical_cohort_manifest_from_json,
    clinical_cohort_report_envelope,
    clinical_cohort_report_from_dict,
    clinical_cohort_report_from_json,
    clinical_cohort_report_summary,
    clinical_decision_config_from_dict,
    clinical_decision_package_envelope,
    clinical_program_state_fingerprint,
    compile_clinical_cohort_report,
    compile_clinical_decision_from_config,
    plan_clinical_evidence_actions,
    validate_clinical_cohort_report,
)
from tests.test_clinical_benefit_risk_synthesis import (
    _combined_state,
    _mapping_spec,
    _run_mapping,
    _run_synthesis,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_cohort_manifest.schema.json"
)
MANIFEST_EXAMPLE = (
    ROOT / "rl_env/specs/clinical_evidence_cohort_manifest.example.json"
)
REPORT_SCHEMA = ROOT / "rl_env/specs/clinical_evidence_cohort_report.schema.json"
REPORT_EXAMPLE = ROOT / "rl_env/specs/clinical_evidence_cohort_report.example.json"
SUMMARY_SCHEMA = ROOT / "rl_env/specs/clinical_evidence_cohort_summary.schema.json"
PACKAGE_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_decision_package.schema.json"
)
RELAXED_PACKAGE_EXAMPLE = (
    ROOT
    / "rl_env/specs/clinical_evidence_decision_package.relaxed.example.json"
)
CONFIG_EXAMPLE = (
    ROOT / "rl_env/specs/clinical_evidence_decision_config.example.json"
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ClinicalCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        mapping_run, _ = _run_mapping(_combined_state(), _mapping_spec())
        synthesis_run, _ = _run_synthesis(mapping_run.final_state, _spec())
        cls.state = synthesis_run.final_state
        config = clinical_decision_config_from_dict(
            json.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8"))
        )
        cls.package_a = compile_clinical_decision_from_config(cls.state, config)
        relaxed_policy = replace(
            config.policy,
            policy_id="synthetic-relaxed-clinical-workflow-policy",
            minimum_independent_trials=2,
            minimum_safety_participants_per_arm=50,
        )
        relaxed_config = replace(
            config,
            package_id="synthetic-clinical-evidence-decision-package-relaxed",
            tensor_id="synthetic-clinical-evidence-tensor-relaxed",
            plan_id="synthetic-clinical-evidence-plan-relaxed",
            policy=relaxed_policy,
        )
        cls.package_b = compile_clinical_decision_from_config(
            cls.state,
            relaxed_config,
        )
        cls.state_sha256 = clinical_program_state_fingerprint(cls.state)
        cls.bindings_without_state = tuple(
            sorted(
                (
                    ClinicalCohortPackageBinding(
                        package_id=package.package_id,
                        program_id=package.program_id,
                        integrity_sha256=package.fingerprint,
                    )
                    for package in (cls.package_a, cls.package_b)
                ),
                key=lambda item: (item.program_id, item.package_id),
            )
        )
        cls.bindings_with_state = tuple(
            replace(item, state_sha256=cls.state_sha256)
            for item in cls.bindings_without_state
        )
        cls.manifest_without_state = ClinicalCohortManifest(
            cohort_id="synthetic-clinical-policy-sensitivity",
            cohort_specification_sha256=_digest("synthetic cohort specification"),
            package_bindings=cls.bindings_without_state,
        )
        cls.manifest_with_state = replace(
            cls.manifest_without_state,
            package_bindings=cls.bindings_with_state,
        )

    def test_schema_examples_and_compiler_output_are_synchronized(self) -> None:
        manifest_schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
        report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        summary_schema = json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))
        package_schema = json.loads(PACKAGE_SCHEMA.read_text(encoding="utf-8"))
        manifest_example = json.loads(MANIFEST_EXAMPLE.read_text(encoding="utf-8"))
        report_example = json.loads(REPORT_EXAMPLE.read_text(encoding="utf-8"))
        relaxed_package_example = json.loads(
            RELAXED_PACKAGE_EXAMPLE.read_text(encoding="utf-8")
        )
        for schema in (
            manifest_schema,
            report_schema,
            summary_schema,
            package_schema,
        ):
            Draft202012Validator.check_schema(schema)
        Draft202012Validator(manifest_schema).validate(manifest_example)
        Draft202012Validator(report_schema).validate(report_example)
        Draft202012Validator(package_schema).validate(relaxed_package_example)
        self.assertEqual(
            relaxed_package_example,
            clinical_decision_package_envelope(self.package_b),
        )

        manifest = clinical_cohort_manifest_from_dict(manifest_example)
        self.assertEqual(manifest, self.manifest_without_state)
        report = compile_clinical_cohort_report(
            manifest,
            (self.package_b, self.package_a),
        )
        self.assertEqual(clinical_cohort_report_envelope(report), report_example)
        self.assertEqual(clinical_cohort_report_from_dict(report_example), report)
        Draft202012Validator(summary_schema).validate(
            clinical_cohort_report_summary(report)
        )

    def test_state_bound_matched_policy_diagnostics_are_descriptive(self) -> None:
        report = compile_clinical_cohort_report(
            self.manifest_with_state,
            (self.package_a, self.package_b),
            states=(self.state,),
        )
        self.assertEqual(
            report.package_validation_scope,
            "integrity_structure_and_state_replay",
        )
        self.assertEqual(
            (
                report.package_count,
                report.program_count,
                report.evidence_unit_count,
                report.policy_count,
            ),
            (2, 1, 1, 2),
        )
        self.assertEqual(
            [item.packages.count for item in report.decisions],
            [1, 1, 0],
        )
        comparison = report.matched_policy_comparisons[0]
        self.assertEqual(comparison.changed_decisions.count, 1)
        self.assertEqual(comparison.changed_gap_profiles.count, 1)
        self.assertEqual(comparison.changed_action_plans.count, 1)
        transitions = {
            (item.decision_a.value, item.decision_b.value): item.count
            for item in comparison.decision_transitions
        }
        self.assertEqual(transitions[("hold", "advance")], 1)
        self.assertTrue(report.evidence_units_source_disjoint)
        self.assertTrue(report.evidence_units_trial_disjoint)
        self.assertFalse(report.outcome_labels_included)
        self.assertFalse(report.performance_metrics_included)
        self.assertEqual(
            report.outcome_calibration_status,
            "not_estimable_without_independent_outcomes",
        )
        self.assertEqual(
            validate_clinical_cohort_report(
                report,
                self.manifest_with_state,
                (self.package_b, self.package_a),
                states=(self.state,),
            ),
            (),
        )

    def test_manifest_and_state_binding_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            ClinicalCohortError,
            "accepted states do not exactly cover",
        ):
            compile_clinical_cohort_report(
                self.manifest_with_state,
                (self.package_a, self.package_b),
            )
        rebound_manifest = replace(
            self.manifest_with_state,
            package_bindings=tuple(
                replace(item, state_sha256=_digest("wrong state"))
                for item in self.manifest_with_state.package_bindings
            ),
        )
        with self.assertRaisesRegex(
            ClinicalCohortError,
            "state integrity does not match",
        ):
            compile_clinical_cohort_report(
                rebound_manifest,
                (self.package_a, self.package_b),
                states=(self.state,),
            )
        with self.assertRaisesRegex(
            ClinicalCohortError,
            "packages do not exactly match",
        ):
            compile_clinical_cohort_report(
                self.manifest_without_state,
                (self.package_a,),
            )

    def test_cross_evidence_unit_overlap_is_explicit(self) -> None:
        reused_tensor = replace(
            self.package_b.tensor,
            synthesis_fingerprint=_digest("synthetic distinct synthesis identity"),
        )
        reused_plan = plan_clinical_evidence_actions(
            reused_tensor,
            self.package_b.policy,
            self.package_b.action_catalog,
            BudgetState(
                limit=self.package_b.plan.budget_limit,
                spent=self.package_b.plan.budget_spent,
            ),
            plan_id="synthetic-reused-provenance-plan",
        )
        reused_package = ClinicalDecisionPackage(
            package_id="synthetic-reused-provenance-package",
            program_id=self.package_b.program_id,
            as_of_date=self.package_b.as_of_date,
            policy=self.package_b.policy,
            action_catalog=self.package_b.action_catalog,
            tensor=reused_tensor,
            plan=reused_plan,
        )
        bindings = tuple(
            sorted(
                (
                    ClinicalCohortPackageBinding(
                        package_id=item.package_id,
                        program_id=item.program_id,
                        integrity_sha256=item.fingerprint,
                    )
                    for item in (self.package_b, reused_package)
                ),
                key=lambda item: (item.program_id, item.package_id),
            )
        )
        manifest = ClinicalCohortManifest(
            cohort_id="synthetic-provenance-overlap",
            cohort_specification_sha256=_digest("overlap specification"),
            package_bindings=bindings,
        )
        report = compile_clinical_cohort_report(
            manifest,
            (self.package_b, reused_package),
        )
        self.assertEqual(report.evidence_unit_count, 2)
        self.assertFalse(report.evidence_units_source_disjoint)
        self.assertFalse(report.evidence_units_trial_disjoint)
        self.assertGreater(len(report.provenance_overlaps), 0)
        self.assertTrue(
            all(len(item.evidence_unit_ids) == 2 for item in report.provenance_overlaps)
        )

    def test_report_reader_rejects_tampering_duplicate_keys_and_nan(self) -> None:
        report = compile_clinical_cohort_report(
            self.manifest_without_state,
            (self.package_a, self.package_b),
        )
        envelope = clinical_cohort_report_envelope(report)
        tampered = copy.deepcopy(envelope)
        tampered["report"]["package_count"] = 3
        with self.assertRaises((RecordParseError, ValueError)):
            clinical_cohort_report_from_dict(tampered)

        encoded = json.dumps(envelope)
        duplicate = encoded.replace(
            "{",
            '{"schema_version":"adds.clinical-evidence-cohort-report.v1",',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_cohort_report_from_json(duplicate)
        non_finite = encoded.replace('"planned_cost": 0.0', '"planned_cost": NaN', 1)
        with self.assertRaisesRegex(RecordParseError, "contains NaN"):
            clinical_cohort_report_from_json(non_finite)

        manifest_encoded = json.dumps(
            clinical_cohort_manifest_envelope(self.manifest_without_state)
        )
        self.assertEqual(
            clinical_cohort_manifest_from_json(manifest_encoded),
            self.manifest_without_state,
        )

    def test_cli_compiles_validates_and_summarizes_atomically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-clinical-cohort-cli-") as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            package_a_path = root / "package-a.json"
            package_b_path = root / "package-b.json"
            state_path = root / "state.json"
            report_path = root / "report.json"
            manifest_path.write_text(
                json.dumps(
                    clinical_cohort_manifest_envelope(self.manifest_with_state),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            for path, package in (
                (package_a_path, self.package_a),
                (package_b_path, self.package_b),
            ):
                path.write_text(
                    json.dumps(
                        clinical_decision_package_envelope(package),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            state_path.write_text(
                json.dumps(self.state.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            base = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
            ]
            compile_command = [
                *base,
                "cohort",
                "--manifest",
                str(manifest_path),
                "--package",
                str(package_a_path),
                "--package",
                str(package_b_path),
                "--state",
                str(state_path),
                "--output",
                str(report_path),
            ]
            compiled = subprocess.run(
                compile_command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(compiled.stdout)["validation"]["status"], "valid")

            validated = subprocess.run(
                [
                    *base,
                    "validate-cohort",
                    "--report",
                    str(report_path),
                    "--manifest",
                    str(manifest_path),
                    "--package",
                    str(package_a_path),
                    "--package",
                    str(package_b_path),
                    "--state",
                    str(state_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)["validation"]["status"], "valid")

            summarized = subprocess.run(
                [*base, "summarize-cohort", "--report", str(report_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            self.assertEqual(json.loads(summarized.stdout)["counts"]["policies"], 2)

            unchanged = report_path.read_bytes()
            duplicate = subprocess.run(
                compile_command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertEqual(report_path.read_bytes(), unchanged)


if __name__ == "__main__":
    unittest.main()
