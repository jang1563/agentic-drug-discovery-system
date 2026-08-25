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

from agentic_drug_discovery.clinicaltrials_gov_harmonization_candidates import (
    clinicaltrials_gov_harmonization_packet_envelope,
    compile_clinicaltrials_gov_harmonization_candidates,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_diagnostics import (
    POPULATION_REVIEW_REQUIRED,
    SEMANTIC_ENDPOINT_REVIEW_REQUIRED,
    SOURCE_FIELD_COMPLETION_REQUIRED,
    ClinicalTrialsGovHarmonizationDiagnosticError,
    ClinicalTrialsGovHarmonizationDiagnosticSpec,
    clinicaltrials_gov_harmonization_diagnostic_report_envelope,
    clinicaltrials_gov_harmonization_diagnostic_report_from_dict,
    clinicaltrials_gov_harmonization_diagnostic_report_from_json,
    clinicaltrials_gov_harmonization_diagnostic_spec_from_dict,
    clinicaltrials_gov_harmonization_diagnostic_spec_from_json,
    clinicaltrials_gov_harmonization_diagnostic_spec_to_dict,
    clinicaltrials_gov_harmonization_diagnostic_summary,
    compile_clinicaltrials_gov_harmonization_diagnostic,
    validate_clinicaltrials_gov_harmonization_diagnostic,
)
from tests.test_clinicaltrials_gov_harmonization_candidates import (
    _complete_outcome,
    _inventory_packet,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_diagnostic_spec.schema.json"
)
SPEC_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_diagnostic_spec.example.json"
)
REPORT_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_diagnostic_report.schema.json"
)
PUBLIC_SPEC = ROOT / "docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_spec.json"
PUBLIC_REPORT = ROOT / "docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_report.json"


def _rehashed(envelope: dict) -> dict:
    envelope["integrity_sha256"] = hashlib.sha256(
        json.dumps(
            envelope["report"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return envelope


class ClinicalTrialsGovHarmonizationDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        first_secondary = _complete_outcome("Objective Response Rate")
        first_secondary["timeFrame"] = "12 months"
        first_secondary["paramType"] = "NUMBER"
        first_secondary["unitOfMeasure"] = "participants"
        first = _inventory_packet(
            "NCT00000001",
            [_complete_outcome(), first_secondary],
            adverse_time_frame="From first dose through 30 days after last dose",
        )
        incomplete = _complete_outcome("Objective Response Rate")
        incomplete.pop("timeFrame")
        incomplete["paramType"] = "NUMBER"
        incomplete["unitOfMeasure"] = "participants"
        third = _complete_outcome("Overall Survival")
        third["timeFrame"] = "36 months"
        third["populationDescription"] = "A distinct analysis population"
        second = _inventory_packet(
            "NCT00000002",
            [_complete_outcome(), incomplete, third],
            adverse_time_frame="From first dose through 30 days after last dose",
        )
        cls.candidate_packet = compile_clinicaltrials_gov_harmonization_candidates(
            _spec((first, second)), (second, first)
        )
        cls.spec = ClinicalTrialsGovHarmonizationDiagnosticSpec(
            report_id="synthetic-harmonization-difficulty:v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
        )
        cls.report = compile_clinicaltrials_gov_harmonization_diagnostic(
            cls.spec, cls.candidate_packet
        )

    def test_payload_free_aggregate_partitions_complete_graph(self) -> None:
        report = self.report
        self.assertEqual(report.trial_count, 2)
        self.assertEqual(report.endpoint_candidate_count, 5)
        self.assertEqual(report.pair_candidate_count, 6)
        self.assertEqual(sum(item.count for item in report.mechanical_status_counts), 6)
        self.assertEqual(
            sum(item.pair_count for item in report.difficulty_signatures), 6
        )
        self.assertEqual(
            report.unique_difficulty_signature_count,
            len(report.difficulty_signatures),
        )
        self.assertTrue(report.payload_free_aggregate_only)
        self.assertTrue(report.every_pair_requires_semantic_review)
        self.assertFalse(report.automatic_pair_approval_performed)
        self.assertFalse(report.automatic_pair_exclusion_performed)

    def test_overlapping_routes_keep_semantic_review_for_exact_pair(self) -> None:
        route_counts = {
            item.code: item.count for item in self.report.review_route_counts
        }
        self.assertEqual(route_counts[SEMANTIC_ENDPOINT_REVIEW_REQUIRED], 6)
        self.assertGreater(route_counts[SOURCE_FIELD_COMPLETION_REQUIRED], 0)
        self.assertEqual(route_counts[POPULATION_REVIEW_REQUIRED], 2)
        self.assertEqual(
            self.report.pairs_with_no_additional_mechanical_blocker_count, 1
        )
        self.assertGreater(self.report.pairs_with_multiple_additional_blockers_count, 0)
        exact_only = next(
            item
            for item in self.report.difficulty_signatures
            if item.route_codes == (SEMANTIC_ENDPOINT_REVIEW_REQUIRED,)
        )
        self.assertEqual(exact_only.pair_count, 1)

    def test_field_and_structure_denominators_are_explicit(self) -> None:
        fields = {item.field_name: item for item in self.report.pair_field_diagnostics}
        self.assertEqual(fields["time_frame"].pair_count, 6)
        self.assertEqual(fields["time_frame"].missing_pair_count, 2)
        self.assertEqual(
            fields["time_frame"].exact_count + fields["time_frame"].disagreement_count,
            fields["time_frame"].observed_both_count,
        )
        structures = {
            item.field_name: item for item in self.report.structural_diagnostics
        }
        self.assertEqual(structures["group_count"].pair_count, 6)
        self.assertEqual(
            structures["analysis_group_id_sets"].exact_count
            + structures["analysis_group_id_sets"].disagreement_count,
            6,
        )
        trials = {item.nct_id: item for item in self.report.trial_diagnostics}
        missing = {
            item.code: item.count
            for item in trials["NCT00000002"].endpoint_field_missing_counts
        }
        self.assertEqual(missing["time_frame"], 1)

    def test_report_does_not_retain_pair_or_clinical_payloads(self) -> None:
        encoded = json.dumps(
            clinicaltrials_gov_harmonization_diagnostic_report_envelope(self.report),
            sort_keys=True,
        )
        self.assertNotIn("Progression-Free Survival", encoded)
        self.assertNotIn("Objective Response Rate", encoded)
        self.assertNotIn("Synthetic serious event", encoded)
        self.assertNotIn("cross-trial-endpoint", encoded)
        self.assertNotIn('"pair_id"', encoded)
        self.assertIn("NCT00000001", encoded)

    def test_exact_binding_and_recompile_validation(self) -> None:
        rebound = replace(
            self.spec,
            candidate_packet_sha256="f" * 64,
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationDiagnosticError,
            "fingerprint does not match",
        ):
            compile_clinicaltrials_gov_harmonization_diagnostic(
                rebound, self.candidate_packet
            )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_diagnostic(
                self.spec, self.candidate_packet, self.report
            ),
            (),
        )
        changed = replace(
            self.report,
            candidate_packet_id="rebound-candidate-packet",
        )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_diagnostic(
                self.spec, self.candidate_packet, changed
            ),
            ("clinicaltrials_gov_harmonization_diagnostic_report_mismatch",),
        )

    def test_strict_reader_rejects_rehashed_route_and_json_tamper(self) -> None:
        envelope = clinicaltrials_gov_harmonization_diagnostic_report_envelope(
            self.report
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_diagnostic_report_from_dict(envelope),
            self.report,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_diagnostic_report_from_json(
                json.dumps(envelope)
            ),
            self.report,
        )
        changed = copy.deepcopy(envelope)
        changed["report"]["review_route_counts"][1]["count"] += 1
        with self.assertRaisesRegex(ValueError, "route counts do not match"):
            clinicaltrials_gov_harmonization_diagnostic_report_from_dict(
                _rehashed(changed)
            )
        duplicate = '{"schema_version":"x","schema_version":"y"}'
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationDiagnosticError, "duplicate JSON key"
        ):
            clinicaltrials_gov_harmonization_diagnostic_report_from_json(duplicate)
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationDiagnosticError, "non-finite"
        ):
            clinicaltrials_gov_harmonization_diagnostic_spec_from_json(
                '{"schema_version":NaN}'
            )

    def test_report_rejects_incomplete_cartesian_pair_denominator(self) -> None:
        first, second = self.report.trial_diagnostics
        first_reconciliation = (
            replace(first.reconciliation_status_counts[0], count=0),
            *first.reconciliation_status_counts[1:],
        )
        second_reconciliation = (
            replace(second.reconciliation_status_counts[0], count=3),
            *second.reconciliation_status_counts[1:],
        )
        with self.assertRaisesRegex(ValueError, "Cartesian"):
            replace(
                self.report,
                trial_diagnostics=(
                    replace(
                        first,
                        posted_outcome_count=1,
                        reconciliation_status_counts=first_reconciliation,
                    ),
                    replace(
                        second,
                        posted_outcome_count=4,
                        reconciliation_status_counts=second_reconciliation,
                    ),
                ),
            )

    def test_report_rejects_source_reuse_and_module_count_contradiction(self) -> None:
        first, second = self.report.trial_diagnostics
        with self.assertRaisesRegex(ValueError, "source content hashes must be unique"):
            replace(
                self.report,
                trial_diagnostics=(
                    first,
                    replace(
                        second,
                        source_content_hash_sha256=(first.source_content_hash_sha256),
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "absent protocol outcome module"):
            replace(first, protocol_outcome_module_present=False)

    def test_schemas_spec_round_trip_and_summary(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(report_schema)
        Draft202012Validator(spec_schema).validate(example)
        Draft202012Validator(spec_schema).validate(
            clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(self.spec)
        )
        Draft202012Validator(report_schema).validate(
            clinicaltrials_gov_harmonization_diagnostic_report_envelope(self.report)
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_diagnostic_spec_from_dict(
                clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(self.spec)
            ),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_diagnostic_spec_from_json(
                json.dumps(
                    clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(self.spec)
                )
            ),
            self.spec,
        )
        summary = clinicaltrials_gov_harmonization_diagnostic_summary(self.report)
        self.assertEqual(summary["pair_candidate_count"], 6)
        self.assertTrue(summary["every_pair_requires_semantic_review"])

    def test_public_olokizumab_diagnostic_is_strict_payload_free_aggregate(
        self,
    ) -> None:
        spec = clinicaltrials_gov_harmonization_diagnostic_spec_from_json(
            PUBLIC_SPEC.read_text(encoding="utf-8")
        )
        report_text = PUBLIC_REPORT.read_text(encoding="utf-8")
        report = clinicaltrials_gov_harmonization_diagnostic_report_from_json(
            report_text
        )
        Draft202012Validator(
            json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        ).validate(json.loads(report_text))
        self.assertEqual(report.spec_sha256, spec.fingerprint)
        self.assertEqual(report.trial_count, 2)
        self.assertEqual(report.endpoint_candidate_count, 12)
        self.assertEqual(report.pair_candidate_count, 35)
        self.assertEqual(report.unique_difficulty_signature_count, 8)
        self.assertEqual(
            report.fingerprint,
            "6a0d2aa20eafe670d6509fc4154558c10a783d5851ff476314b2d7dc86a0b089",
        )
        for forbidden in (
            '"pair_id":',
            '"endpoint_candidate_id":',
            '"safety_records":',
            '"title":',
            '"adverse_event_time_frame":',
        ):
            self.assertNotIn(forbidden, report_text)

    def test_cli_compiles_atomic_payload_free_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "diagnostic-spec.json"
            packet_path = root / "candidate-packet.json"
            output_path = root / "diagnostic-report.json"
            spec_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(self.spec)
                ),
                encoding="utf-8",
            )
            packet_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_packet_envelope(
                        self.candidate_packet
                    )
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "diagnose-clinicaltrials-gov-harmonization",
                    "--spec",
                    str(spec_path),
                    "--candidate-packet",
                    str(packet_path),
                    "--output",
                    str(output_path),
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
                "cross_trial_harmonization_diagnostic_compiled",
            )
            self.assertEqual(summary["pair_candidate_count"], 6)
            self.assertEqual(
                clinicaltrials_gov_harmonization_diagnostic_report_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.report,
            )


if __name__ == "__main__":
    unittest.main()
