from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery.clinicaltrials_gov_harmonization_diagnostics import (
    clinicaltrials_gov_harmonization_diagnostic_report_from_json,
    clinicaltrials_gov_harmonization_diagnostic_spec_from_json,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_robustness import (
    ABSENT_ALL,
    HETEROGENEOUS,
    SATURATED_ALL,
    ClinicalTrialsGovHarmonizationRobustnessError,
    ClinicalTrialsGovHarmonizationRobustnessSpec,
    ExactRate,
    HarmonizationRobustnessReportBinding,
    classify_harmonization_rate_stability,
    clinicaltrials_gov_harmonization_robustness_report_envelope,
    clinicaltrials_gov_harmonization_robustness_report_from_dict,
    clinicaltrials_gov_harmonization_robustness_report_from_json,
    clinicaltrials_gov_harmonization_robustness_spec_from_dict,
    clinicaltrials_gov_harmonization_robustness_spec_from_json,
    clinicaltrials_gov_harmonization_robustness_spec_to_dict,
    clinicaltrials_gov_harmonization_robustness_summary,
    compile_clinicaltrials_gov_harmonization_robustness,
    validate_clinicaltrials_gov_harmonization_robustness,
)


ROOT = Path(__file__).resolve().parents[1]
RA_REPORT = ROOT / "docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_report.json"
UC_REPORT = ROOT / "docs/uc_ozanimod_harmonization_diagnostic_report.json"
UC_SPEC = ROOT / "docs/uc_ozanimod_harmonization_diagnostic_spec.json"
PUBLIC_SPEC = ROOT / "docs/ra_uc_harmonization_robustness_spec.json"
PUBLIC_REPORT = ROOT / "docs/ra_uc_harmonization_robustness_report.json"
SPEC_SCHEMA = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_harmonization_robustness_spec.schema.json"
)
REPORT_SCHEMA = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_harmonization_robustness_report.schema.json"
)
DIAGNOSTIC_SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_diagnostic_spec.schema.json"
)
DIAGNOSTIC_REPORT_SCHEMA = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_harmonization_diagnostic_report.schema.json"
)


class ClinicalTrialsGovHarmonizationRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ra = clinicaltrials_gov_harmonization_diagnostic_report_from_json(
            RA_REPORT.read_text(encoding="utf-8")
        )
        cls.uc = clinicaltrials_gov_harmonization_diagnostic_report_from_json(
            UC_REPORT.read_text(encoding="utf-8")
        )
        cls.spec = clinicaltrials_gov_harmonization_robustness_spec_from_json(
            PUBLIC_SPEC.read_text(encoding="utf-8")
        )
        cls.report = compile_clinicaltrials_gov_harmonization_robustness(
            cls.spec, (cls.uc, cls.ra)
        )

    def test_exact_rational_stability_classification(self) -> None:
        def rates(*values: tuple[int, int]) -> tuple[ExactRate, ...]:
            return tuple(
                ExactRate(code="route", numerator=numerator, denominator=denominator)
                for numerator, denominator in values
            )

        self.assertEqual(
            classify_harmonization_rate_stability(rates((1, 1), (4, 4))),
            SATURATED_ALL,
        )
        self.assertEqual(
            classify_harmonization_rate_stability(rates((0, 3), (0, 8))),
            ABSENT_ALL,
        )
        self.assertEqual(
            classify_harmonization_rate_stability(rates((1, 2), (2, 4))),
            "stable_non_boundary",
        )
        self.assertEqual(
            classify_harmonization_rate_stability(rates((1, 3), (2, 3))),
            HETEROGENEOUS,
        )
        with self.assertRaisesRegex(ValueError, "requires two rates"):
            classify_harmonization_rate_stability(rates((1, 2)))
        with self.assertRaisesRegex(ValueError, "one diagnostic code"):
            classify_harmonization_rate_stability(
                (
                    ExactRate("left", 1, 2),
                    ExactRate("right", 1, 2),
                )
            )

    def test_exact_rates_and_cross_cohort_stability(self) -> None:
        profiles = {item.cohort_id: item for item in self.report.cohort_profiles}
        self.assertEqual(profiles["ra-olokizumab-mtx-ir"].pair_candidate_count, 35)
        self.assertEqual(profiles["uc-ozanimod"].pair_candidate_count, 110)
        route_statuses = {
            item.code: item.status for item in self.report.review_route_stability
        }
        self.assertEqual(
            route_statuses["semantic_endpoint_review_required"], SATURATED_ALL
        )
        self.assertEqual(
            route_statuses["estimand_structure_review_required"], SATURATED_ALL
        )
        self.assertEqual(
            route_statuses["safety_window_review_required"], SATURATED_ALL
        )
        self.assertEqual(
            route_statuses["within_trial_reconciliation_review_required"],
            ABSENT_ALL,
        )
        self.assertEqual(
            route_statuses["source_field_completion_required"], HETEROGENEOUS
        )
        field_statuses = {
            item.code: item.status
            for item in self.report.pair_field_missing_stability
        }
        self.assertEqual(field_statuses["dispersion_type"], HETEROGENEOUS)
        self.assertEqual(field_statuses["title"], ABSENT_ALL)

    def test_input_order_is_irrelevant_and_validation_recompiles(self) -> None:
        forward = compile_clinicaltrials_gov_harmonization_robustness(
            self.spec, (self.ra, self.uc)
        )
        reverse = compile_clinicaltrials_gov_harmonization_robustness(
            self.spec, (self.uc, self.ra)
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_robustness(
                self.spec, (self.uc, self.ra), self.report
            ),
            (),
        )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_robustness(
                self.spec,
                (self.uc, self.ra),
                replace(self.report, benchmark_id="rebound-benchmark"),
            ),
            ("clinicaltrials_gov_harmonization_robustness_report_mismatch",),
        )

    def test_hash_mismatch_and_source_overlap_fail_closed(self) -> None:
        bad_binding = replace(
            self.spec.report_bindings[0], diagnostic_report_sha256="0" * 64
        )
        bad_spec = replace(
            self.spec,
            report_bindings=(bad_binding, self.spec.report_bindings[1]),
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationRobustnessError, "hash mismatch"
        ):
            compile_clinicaltrials_gov_harmonization_robustness(
                bad_spec, (self.ra, self.uc)
            )

        first, second = self.uc.trial_diagnostics
        overlapping_uc = replace(
            self.uc,
            trial_diagnostics=(
                first,
                replace(second, nct_id=self.ra.trial_diagnostics[0].nct_id),
            ),
        )
        overlap_spec = ClinicalTrialsGovHarmonizationRobustnessSpec(
            benchmark_id="overlap-must-fail",
            report_bindings=(
                HarmonizationRobustnessReportBinding(
                    cohort_id="ra",
                    diagnostic_report_id=self.ra.report_id,
                    diagnostic_report_sha256=self.ra.fingerprint,
                ),
                HarmonizationRobustnessReportBinding(
                    cohort_id="uc",
                    diagnostic_report_id=overlapping_uc.report_id,
                    diagnostic_report_sha256=overlapping_uc.fingerprint,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "not source-disjoint"):
            compile_clinicaltrials_gov_harmonization_robustness(
                overlap_spec, (self.ra, overlapping_uc)
            )

        source_overlapping_uc = replace(
            self.uc,
            trial_diagnostics=(
                first,
                replace(
                    second,
                    source_content_hash_sha256=(
                        self.ra.trial_diagnostics[0].source_content_hash_sha256
                    ),
                ),
            ),
        )
        source_overlap_spec = ClinicalTrialsGovHarmonizationRobustnessSpec(
            benchmark_id="source-overlap-must-fail",
            report_bindings=(
                self.spec.report_bindings[0],
                replace(
                    self.spec.report_bindings[1],
                    diagnostic_report_sha256=source_overlapping_uc.fingerprint,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "content hash"):
            compile_clinicaltrials_gov_harmonization_robustness(
                source_overlap_spec, (self.ra, source_overlapping_uc)
            )

    def test_derived_stability_tampering_fails_closed(self) -> None:
        first, *rest = self.report.review_route_stability
        with self.assertRaisesRegex(ValueError, "does not match cohort rates"):
            replace(
                self.report,
                review_route_stability=(
                    replace(first, status=ABSENT_ALL),
                    *rest,
                ),
            )

    def test_schema_round_trip_duplicate_keys_and_integrity(self) -> None:
        spec_value = clinicaltrials_gov_harmonization_robustness_spec_to_dict(
            self.spec
        )
        report_value = clinicaltrials_gov_harmonization_robustness_report_envelope(
            self.report
        )
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(report_schema)
        Draft202012Validator(spec_schema).validate(spec_value)
        Draft202012Validator(report_schema).validate(report_value)
        self.assertEqual(
            clinicaltrials_gov_harmonization_robustness_spec_from_dict(spec_value),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_robustness_report_from_dict(
                report_value
            ),
            self.report,
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationRobustnessError, "duplicate JSON key"
        ):
            clinicaltrials_gov_harmonization_robustness_spec_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )
        tampered = json.loads(json.dumps(report_value))
        tampered["integrity_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationRobustnessError, "integrity_sha256"
        ):
            clinicaltrials_gov_harmonization_robustness_report_from_dict(tampered)

    def test_public_report_and_summary_are_exact(self) -> None:
        public_text = PUBLIC_REPORT.read_text(encoding="utf-8")
        public_report = (
            clinicaltrials_gov_harmonization_robustness_report_from_json(
                public_text
            )
        )
        self.assertEqual(public_report, self.report)
        self.assertEqual(
            public_report.fingerprint,
            "53a0d589d745502e4a657937f9ab359b78302dc6b2887a2743962fffacca3af4",
        )
        summary = clinicaltrials_gov_harmonization_robustness_summary(public_report)
        self.assertEqual(summary["saturated_review_route_count"], 3)
        self.assertEqual(summary["absent_review_route_count"], 2)
        self.assertEqual(summary["heterogeneous_review_route_count"], 5)
        for forbidden in (
            '"pair_id":',
            '"endpoint_candidate_id":',
            '"title":',
            '"safety_records":',
        ):
            self.assertNotIn(forbidden, public_text)

    def test_public_uc_diagnostic_is_exact_and_schema_valid(self) -> None:
        spec_text = UC_SPEC.read_text(encoding="utf-8")
        report_text = UC_REPORT.read_text(encoding="utf-8")
        spec_value = json.loads(spec_text)
        report_value = json.loads(report_text)
        Draft202012Validator(
            json.loads(DIAGNOSTIC_SPEC_SCHEMA.read_text(encoding="utf-8"))
        ).validate(spec_value)
        Draft202012Validator(
            json.loads(DIAGNOSTIC_REPORT_SCHEMA.read_text(encoding="utf-8"))
        ).validate(report_value)
        spec = clinicaltrials_gov_harmonization_diagnostic_spec_from_json(
            spec_text
        )
        self.assertEqual(self.uc.spec_sha256, spec.fingerprint)
        self.assertEqual(self.uc.endpoint_candidate_count, 21)
        self.assertEqual(self.uc.pair_candidate_count, 110)
        self.assertEqual(self.uc.unique_difficulty_signature_count, 2)
        self.assertEqual(
            self.uc.fingerprint,
            "2edf2956e0f4fdf0b2de97bd1db95bd9b15b210910af812709181f9a74d13156",
        )
        self.assertEqual(
            hashlib.sha256(spec_text.encode("utf-8")).hexdigest(),
            "cc567d0cc2288438df866bf6dde25c3a32769f9c3f78287667f6733947133c1a",
        )
        self.assertEqual(
            hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
            "f77b8e8d68d4de86782a4b0b4c2024b35de5d2516e0e0544fac8662391d41b68",
        )

    def test_cli_compiles_atomic_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "robustness-report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "benchmark-clinicaltrials-gov-harmonization-robustness",
                    "--spec",
                    str(PUBLIC_SPEC),
                    "--diagnostic-report",
                    str(UC_REPORT),
                    "--diagnostic-report",
                    str(RA_REPORT),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(
                summary["status"],
                "cross_cohort_harmonization_robustness_compiled",
            )
            self.assertEqual(
                clinicaltrials_gov_harmonization_robustness_report_from_json(
                    output.read_text(encoding="utf-8")
                ),
                self.report,
            )


if __name__ == "__main__":
    unittest.main()
