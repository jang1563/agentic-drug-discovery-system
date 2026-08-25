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
    ClinicalTrialsGovHarmonizationDiagnosticSpec,
    clinicaltrials_gov_harmonization_diagnostic_report_envelope,
    compile_clinicaltrials_gov_harmonization_diagnostic,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_structure import (
    ENDPOINT_LOCAL_DISAGREEMENT_PRESENT,
    TRIAL_GLOBAL_DISAGREEMENT_ONLY,
    ClinicalTrialsGovHarmonizationStructureError,
    ClinicalTrialsGovHarmonizationStructureSpec,
    clinicaltrials_gov_harmonization_structure_report_envelope,
    clinicaltrials_gov_harmonization_structure_report_from_dict,
    clinicaltrials_gov_harmonization_structure_report_from_json,
    clinicaltrials_gov_harmonization_structure_spec_from_dict,
    clinicaltrials_gov_harmonization_structure_spec_from_json,
    clinicaltrials_gov_harmonization_structure_spec_to_dict,
    clinicaltrials_gov_harmonization_structure_summary,
    compile_clinicaltrials_gov_harmonization_structure,
    validate_clinicaltrials_gov_harmonization_structure,
)
from tests.test_clinicaltrials_gov_harmonization_candidates import (
    _complete_outcome,
    _inventory_packet,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_structure_spec.schema.json"
)
SPEC_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_structure_spec.example.json"
)
REPORT_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_structure_report.schema.json"
)
PUBLIC = {
    "ra": (
        ROOT / "docs/ra_olokizumab_mtx_ir_structure_spec.json",
        ROOT / "docs/ra_olokizumab_mtx_ir_structure_report.json",
    ),
    "uc": (
        ROOT / "docs/uc_ozanimod_structure_spec.json",
        ROOT / "docs/uc_ozanimod_structure_report.json",
    ),
}


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


class ClinicalTrialsGovHarmonizationStructureTests(unittest.TestCase):
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
        packet = compile_clinicaltrials_gov_harmonization_candidates(
            _spec((first, second)), (second, first)
        )
        endpoints = []
        for endpoint in packet.endpoint_candidates:
            if endpoint.nct_id == "NCT00000001":
                endpoints.append(
                    replace(
                        endpoint,
                        group_count=2,
                        analysis_count=1,
                        analysis_group_id_sets=(("OG000", "OG001"),),
                    )
                )
                continue
            endpoint_local = endpoint.source_index == 2
            endpoints.append(
                replace(
                    endpoint,
                    group_count=1,
                    analysis_count=0 if endpoint_local else 1,
                    analysis_group_id_sets=(
                        () if endpoint_local else (("OG000", "OG001"),)
                    ),
                )
            )
        cls.candidate_packet = replace(
            packet, endpoint_candidates=tuple(endpoints)
        )
        diagnostic_spec = ClinicalTrialsGovHarmonizationDiagnosticSpec(
            report_id="synthetic-harmonization-difficulty:structure-v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
        )
        cls.diagnostic_report = (
            compile_clinicaltrials_gov_harmonization_diagnostic(
                diagnostic_spec, cls.candidate_packet
            )
        )
        cls.spec = ClinicalTrialsGovHarmonizationStructureSpec(
            report_id="synthetic-structure-decomposition:v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
            diagnostic_report_sha256=cls.diagnostic_report.fingerprint,
        )
        cls.report = compile_clinicaltrials_gov_harmonization_structure(
            cls.spec, cls.candidate_packet, cls.diagnostic_report
        )

    def test_trial_global_and_endpoint_local_partitions_are_complete(self) -> None:
        fields = {item.field_name: item for item in self.report.field_decompositions}
        self.assertEqual(
            (fields["group_count"].exact_count,
             fields["group_count"].trial_global_disagreement_count,
             fields["group_count"].endpoint_local_disagreement_count),
            (0, 6, 0),
        )
        self.assertEqual(
            (fields["analysis_count"].exact_count,
             fields["analysis_count"].trial_global_disagreement_count,
             fields["analysis_count"].endpoint_local_disagreement_count),
            (4, 0, 2),
        )
        diagnostic = {
            item.field_name: item
            for item in self.diagnostic_report.structural_diagnostics
        }
        for name, decomposition in fields.items():
            self.assertEqual(decomposition.exact_count, diagnostic[name].exact_count)
            self.assertEqual(
                decomposition.trial_global_disagreement_count
                + decomposition.endpoint_local_disagreement_count,
                diagnostic[name].disagreement_count,
            )

    def test_pair_categories_and_source_presence_non_identifiability(self) -> None:
        categories = {item.code: item.count for item in self.report.pair_category_counts}
        self.assertEqual(categories[TRIAL_GLOBAL_DISAGREEMENT_ONLY], 4)
        self.assertEqual(categories[ENDPOINT_LOCAL_DISAGREEMENT_PRESENT], 2)
        self.assertEqual(sum(categories.values()), self.report.pair_candidate_count)
        self.assertFalse(self.report.source_presence_identifiable)
        self.assertFalse(self.report.source_presence_provenance_retained)
        fields = {item.field_name: item for item in self.report.field_decompositions}
        self.assertEqual(
            fields["group_count"].source_presence_non_identifiable_pair_count, 0
        )
        self.assertEqual(
            fields["analysis_count"].source_presence_non_identifiable_pair_count,
            2,
        )
        second = self.report.trial_profiles[1]
        profiles = {item.field_name: item for item in second.field_profiles}
        self.assertFalse(profiles["analysis_count"].within_trial_constant)
        self.assertEqual(profiles["analysis_count"].zero_or_empty_value_count, 1)
        self.assertEqual(
            profiles["analysis_group_id_sets"].zero_or_empty_value_count, 1
        )
        with self.assertRaisesRegex(TypeError, "within_trial_constant"):
            replace(profiles["analysis_count"], within_trial_constant=1)

    def test_exact_bindings_and_recompile_validation(self) -> None:
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationStructureError,
            "candidate packet fingerprint",
        ):
            compile_clinicaltrials_gov_harmonization_structure(
                replace(self.spec, candidate_packet_sha256="f" * 64),
                self.candidate_packet,
                self.diagnostic_report,
            )
        rebound_diagnostic = replace(
            self.diagnostic_report,
            candidate_packet_id="rebound-candidate-packet",
        )
        rebound_spec = replace(
            self.spec,
            diagnostic_report_sha256=rebound_diagnostic.fingerprint,
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationStructureError,
            "does not bind the candidate packet",
        ):
            compile_clinicaltrials_gov_harmonization_structure(
                rebound_spec, self.candidate_packet, rebound_diagnostic
            )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_structure(
                self.spec,
                self.candidate_packet,
                self.diagnostic_report,
                self.report,
            ),
            (),
        )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_structure(
                self.spec,
                self.candidate_packet,
                self.diagnostic_report,
                replace(self.report, report_id="changed-report"),
            ),
            ("clinicaltrials_gov_harmonization_structure_report_mismatch",),
        )

    def test_strict_round_trip_integrity_and_schema(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(report_schema)
        Draft202012Validator(spec_schema).validate(
            json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8"))
        )
        spec_value = clinicaltrials_gov_harmonization_structure_spec_to_dict(
            self.spec
        )
        report_value = clinicaltrials_gov_harmonization_structure_report_envelope(
            self.report
        )
        Draft202012Validator(spec_schema).validate(spec_value)
        Draft202012Validator(report_schema).validate(report_value)
        self.assertEqual(
            clinicaltrials_gov_harmonization_structure_spec_from_dict(spec_value),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_structure_spec_from_json(
                json.dumps(spec_value)
            ),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_structure_report_from_dict(
                report_value
            ),
            self.report,
        )
        changed = copy.deepcopy(report_value)
        changed["report"]["report_id"] = "changed-report"
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationStructureError, "integrity_sha256"
        ):
            clinicaltrials_gov_harmonization_structure_report_from_dict(changed)
        self.assertEqual(
            clinicaltrials_gov_harmonization_structure_report_from_dict(
                _rehashed(changed)
            ).report_id,
            "changed-report",
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationStructureError, "duplicate JSON key"
        ):
            clinicaltrials_gov_harmonization_structure_report_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )

    def test_public_ra_and_uc_exact_decompositions(self) -> None:
        loaded = {}
        schema = Draft202012Validator(
            json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        )
        for cohort, (spec_path, report_path) in PUBLIC.items():
            spec = clinicaltrials_gov_harmonization_structure_spec_from_json(
                spec_path.read_text(encoding="utf-8")
            )
            report_text = report_path.read_text(encoding="utf-8")
            schema.validate(json.loads(report_text))
            report = clinicaltrials_gov_harmonization_structure_report_from_json(
                report_text
            )
            self.assertEqual(report.spec_sha256, spec.fingerprint)
            self.assertFalse(report.source_presence_provenance_retained)
            self.assertFalse(report.trial_global_disagreement_discounted)
            for forbidden in (
                '"pair_id"',
                '"endpoint_candidate_id"',
                '"source_json_pointer"',
                '"group_ids"',
                '"title"',
            ):
                self.assertNotIn(forbidden, report_text)
            loaded[cohort] = report

        ra = loaded["ra"]
        self.assertEqual(ra.candidate_packet_sha256, "cabb2ac6c2321483072c210dbfb677acbf6dad4ddd237181ecc0846d6f7ac004")
        self.assertTrue(ra.source_presence_identifiable)
        self.assertEqual(ra.fingerprint, "7f6a071ffc4e83f46b0f6d1d7cf237a3f22f3a39defa355f594e6dd99e910169")
        self.assertEqual((ra.endpoint_candidate_count, ra.pair_candidate_count), (12, 35))
        ra_fields = {item.field_name: item for item in ra.field_decompositions}
        self.assertEqual(ra_fields["group_count"].trial_global_disagreement_count, 35)
        self.assertEqual(ra_fields["measurement_count"].trial_global_disagreement_count, 35)
        self.assertEqual(ra_fields["analysis_count"].endpoint_local_disagreement_count, 25)
        self.assertEqual(ra_fields["analysis_group_id_sets"].endpoint_local_disagreement_count, 35)

        uc = loaded["uc"]
        self.assertEqual(uc.candidate_packet_sha256, "aaefafba4d1c4bfa10c5589ceb102fe866fc5ebe89530f7fc2580aed49245b22")
        self.assertFalse(uc.source_presence_identifiable)
        self.assertEqual(uc.fingerprint, "68f64745cc9db1ce98506970834822f64f0e502e35ecacb35c944ac2b8ca5b1b")
        self.assertEqual((uc.endpoint_candidate_count, uc.pair_candidate_count), (21, 110))
        uc_fields = {item.field_name: item for item in uc.field_decompositions}
        self.assertEqual(uc_fields["group_count"].endpoint_local_disagreement_count, 110)
        self.assertEqual(uc_fields["class_count"].endpoint_local_disagreement_count, 33)
        self.assertEqual(uc_fields["analysis_count"].endpoint_local_disagreement_count, 83)
        self.assertEqual(
            uc_fields["analysis_count"].source_presence_non_identifiable_pair_count,
            96,
        )
        self.assertEqual(uc.trial_global_saturated_field_count, 0)

    def test_summary_and_cli(self) -> None:
        summary = clinicaltrials_gov_harmonization_structure_summary(self.report)
        self.assertEqual(summary["trial_global_only_pair_count"], 4)
        self.assertEqual(summary["endpoint_local_present_pair_count"], 2)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "structure-spec.json"
            packet_path = root / "candidate-packet.json"
            diagnostic_path = root / "diagnostic-report.json"
            output_path = root / "structure-report.json"
            spec_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_structure_spec_to_dict(
                        self.spec
                    )
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
            diagnostic_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_diagnostic_report_envelope(
                        self.diagnostic_report
                    )
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "decompose-clinicaltrials-gov-harmonization-structure",
                    "--spec",
                    str(spec_path),
                    "--candidate-packet",
                    str(packet_path),
                    "--diagnostic-report",
                    str(diagnostic_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(completed.stdout)["status"],
                "cross_trial_harmonization_structure_decomposed",
            )
            self.assertEqual(
                clinicaltrials_gov_harmonization_structure_report_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.report,
            )


if __name__ == "__main__":
    unittest.main()
