from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery.clinicaltrials_gov_harmonization_candidates import (
    ClinicalTrialsGovHarmonizationCandidateSpec,
    ClinicalTrialsGovHarmonizationInventoryBinding,
    clinicaltrials_gov_harmonization_packet_envelope,
    compile_clinicaltrials_gov_harmonization_candidates,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_diagnostics import (
    ClinicalTrialsGovHarmonizationDiagnosticSpec,
    compile_clinicaltrials_gov_harmonization_diagnostic,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_structure import (
    ClinicalTrialsGovHarmonizationStructureSpec,
    clinicaltrials_gov_harmonization_structure_report_envelope,
    compile_clinicaltrials_gov_harmonization_structure,
)
from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventorySpec,
    clinicaltrials_gov_inventory_packet_envelope,
    compile_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.clinicaltrials_gov_structural_presence import (
    ABSENT,
    ANALYSIS_GROUP_IDS,
    OUTCOME_ANALYSES,
    OUTCOME_DENOMINATORS,
    OUTCOME_GROUPS,
    PRESENT_EMPTY,
    PRESENT_NONEMPTY,
    PRESENT_NULL,
    ClinicalTrialsGovHarmonizationPresenceSpec,
    ClinicalTrialsGovStructuralPresenceError,
    ClinicalTrialsGovStructuralPresenceSpec,
    StructuralPresenceSidecarBinding,
    clinicaltrials_gov_harmonization_presence_report_envelope,
    clinicaltrials_gov_harmonization_presence_report_from_dict,
    clinicaltrials_gov_harmonization_presence_report_from_json,
    clinicaltrials_gov_harmonization_presence_spec_from_json,
    clinicaltrials_gov_harmonization_presence_spec_to_dict,
    clinicaltrials_gov_harmonization_presence_summary,
    clinicaltrials_gov_structural_presence_packet_envelope,
    clinicaltrials_gov_structural_presence_packet_from_dict,
    clinicaltrials_gov_structural_presence_packet_from_json,
    clinicaltrials_gov_structural_presence_spec_from_json,
    clinicaltrials_gov_structural_presence_spec_to_dict,
    clinicaltrials_gov_structural_presence_summary,
    compile_clinicaltrials_gov_harmonization_presence,
    compile_clinicaltrials_gov_structural_presence,
    validate_clinicaltrials_gov_harmonization_presence,
    validate_clinicaltrials_gov_structural_presence,
)
from agentic_drug_discovery.ingestion import (
    canonical_json_bytes,
    capture_source_bytes,
    write_source_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SIDECAR_SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_structural_presence_spec.schema.json"
)
SIDECAR_SPEC_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_structural_presence_spec.example.json"
)
SIDECAR_PACKET_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_structural_presence_packet.schema.json"
)
PRESENCE_SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_presence_spec.schema.json"
)
PRESENCE_SPEC_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_presence_spec.example.json"
)
PRESENCE_REPORT_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_presence_report.schema.json"
)
PUBLIC = {
    "ra": (
        ROOT / "docs/ra_olokizumab_mtx_ir_presence_spec.json",
        ROOT / "docs/ra_olokizumab_mtx_ir_presence_report.json",
    ),
    "uc": (
        ROOT / "docs/uc_ozanimod_presence_spec.json",
        ROOT / "docs/uc_ozanimod_presence_report.json",
    ),
}


def _base_source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _inventory_bundle(nct_id: str, outcome: dict):
    source = _base_source()
    source["protocolSection"]["identificationModule"]["nctId"] = nct_id
    source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"] = [outcome]
    receipt_id = f"ctgov-presence-{nct_id}"
    version = "2025-01-01"
    bundle = capture_source_bytes(
        canonical_json_bytes(source),
        receipt_id=receipt_id,
        source_id=f"clinicaltrials-gov-{nct_id}",
        source_version=f"clinicaltrials-gov-{nct_id}-version-{version}",
        locator=f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    inventory_spec = ClinicalTrialsGovInventorySpec(
        inventory_id=f"{nct_id}:registry-record-wide-inventory:v1",
        source_receipt_id=receipt_id,
        nct_id=nct_id,
        registry_version=version,
    )
    return compile_clinicaltrials_gov_inventory(inventory_spec, bundle), bundle


def _sidecar_spec(packet, bundle, *, maximum: int = 100):
    return ClinicalTrialsGovStructuralPresenceSpec(
        sidecar_id=f"{packet.nct_id}:structural-array-presence:v1",
        inventory_sha256=packet.fingerprint,
        source_content_hash_sha256=bundle.receipt.content_hash,
        max_structural_array_record_count=maximum,
    )


def _rehashed(envelope: dict, key: str) -> dict:
    envelope["integrity_sha256"] = hashlib.sha256(
        json.dumps(
            envelope[key],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return envelope


class ClinicalTrialsGovStructuralPresenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        first_outcome = copy.deepcopy(
            _base_source()["resultsSection"]["outcomeMeasuresModule"][
                "outcomeMeasures"
            ][0]
        )
        first_outcome["groups"] = []
        first_outcome.pop("denoms")
        first_outcome.pop("classes")
        first_outcome["analyses"] = [{"groupIds": None}]
        second_outcome = copy.deepcopy(first_outcome)
        second_outcome.pop("groups")
        second_outcome["denoms"] = []
        second_outcome["analyses"] = [{"groupIds": []}]
        first, first_bundle = _inventory_bundle("NCT00000001", first_outcome)
        second, second_bundle = _inventory_bundle("NCT00000002", second_outcome)
        cls.inventories = (first, second)
        cls.bundles = (first_bundle, second_bundle)
        cls.sidecar_specs = tuple(
            _sidecar_spec(packet, bundle)
            for packet, bundle in zip(cls.inventories, cls.bundles, strict=True)
        )
        cls.sidecars = tuple(
            compile_clinicaltrials_gov_structural_presence(spec, bundle, packet)
            for spec, bundle, packet in zip(
                cls.sidecar_specs, cls.bundles, cls.inventories, strict=True
            )
        )
        candidate_spec = ClinicalTrialsGovHarmonizationCandidateSpec(
            packet_id="synthetic-source-presence-candidates:v1",
            inventory_bindings=tuple(
                ClinicalTrialsGovHarmonizationInventoryBinding(
                    inventory_id=packet.inventory_id,
                    nct_id=packet.nct_id,
                    inventory_sha256=packet.fingerprint,
                )
                for packet in cls.inventories
            ),
            max_endpoint_candidate_count=10,
            max_pair_count=10,
        )
        cls.candidate_packet = compile_clinicaltrials_gov_harmonization_candidates(
            candidate_spec, tuple(reversed(cls.inventories))
        )
        diagnostic_spec = ClinicalTrialsGovHarmonizationDiagnosticSpec(
            report_id="synthetic-source-presence-diagnostic:v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
        )
        diagnostic = compile_clinicaltrials_gov_harmonization_diagnostic(
            diagnostic_spec, cls.candidate_packet
        )
        structure_spec = ClinicalTrialsGovHarmonizationStructureSpec(
            report_id="synthetic-source-presence-structure:v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
            diagnostic_report_sha256=diagnostic.fingerprint,
        )
        cls.structure_report = compile_clinicaltrials_gov_harmonization_structure(
            structure_spec, cls.candidate_packet, diagnostic
        )
        cls.presence_spec = ClinicalTrialsGovHarmonizationPresenceSpec(
            report_id="synthetic-source-presence-resolution:v1",
            candidate_packet_sha256=cls.candidate_packet.fingerprint,
            structure_report_sha256=cls.structure_report.fingerprint,
            sidecar_bindings=tuple(
                StructuralPresenceSidecarBinding(
                    nct_id=sidecar.nct_id,
                    inventory_sha256=sidecar.inventory_sha256,
                    sidecar_sha256=sidecar.fingerprint,
                )
                for sidecar in cls.sidecars
            ),
        )
        cls.presence_report = compile_clinicaltrials_gov_harmonization_presence(
            cls.presence_spec,
            cls.candidate_packet,
            cls.structure_report,
            tuple(reversed(cls.sidecars)),
        )

    def test_sidecar_preserves_all_four_states_without_values(self) -> None:
        first = self.sidecars[0]
        self.assertEqual(
            (
                first.structural_array_record_count,
                first.absent_count,
                first.present_null_count,
                first.present_empty_count,
                first.present_nonempty_count,
            ),
            (5, 2, 1, 1, 1),
        )
        records = {item.array_role: item for item in first.array_records}
        self.assertEqual(records[OUTCOME_GROUPS].presence_state, PRESENT_EMPTY)
        self.assertEqual(records[OUTCOME_DENOMINATORS].presence_state, ABSENT)
        self.assertEqual(records[OUTCOME_ANALYSES].presence_state, PRESENT_NONEMPTY)
        self.assertEqual(records[ANALYSIS_GROUP_IDS].presence_state, PRESENT_NULL)
        second_records = {
            item.array_role: item for item in self.sidecars[1].array_records
        }
        self.assertEqual(second_records[OUTCOME_GROUPS].presence_state, ABSENT)
        self.assertEqual(
            second_records[OUTCOME_DENOMINATORS].presence_state, PRESENT_EMPTY
        )
        self.assertEqual(
            second_records[ANALYSIS_GROUP_IDS].presence_state, PRESENT_EMPTY
        )
        text = json.dumps(clinicaltrials_gov_structural_presence_packet_envelope(first))
        for source_payload in ("Test Drug", "Comparator Drug", '"groupIds":'):
            self.assertNotIn(source_payload, text)
        self.assertTrue(first.v1_inventory_replay_verified)
        self.assertFalse(first.structural_array_values_retained)

    def test_exact_replay_bounds_and_tamper_fail_closed(self) -> None:
        self.assertEqual(
            validate_clinicaltrials_gov_structural_presence(
                self.sidecar_specs[0],
                self.bundles[0],
                self.inventories[0],
                self.sidecars[0],
            ),
            (),
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "inventory fingerprint"
        ):
            compile_clinicaltrials_gov_structural_presence(
                replace(self.sidecar_specs[0], inventory_sha256="f" * 64),
                self.bundles[0],
                self.inventories[0],
            )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "preregistered bound"
        ):
            compile_clinicaltrials_gov_structural_presence(
                _sidecar_spec(self.inventories[0], self.bundles[0], maximum=4),
                self.bundles[0],
                self.inventories[0],
            )
        self.assertEqual(
            validate_clinicaltrials_gov_structural_presence(
                self.sidecar_specs[0],
                self.bundles[0],
                self.inventories[0],
                replace(self.sidecars[0], sidecar_id="rebound"),
            ),
            ("clinicaltrials_gov_structural_presence_packet_mismatch",),
        )

    def test_presence_resolution_refines_every_legacy_zero_pair(self) -> None:
        report = self.presence_report
        self.assertEqual(report.legacy_non_identifiable_field_pair_count, 6)
        self.assertEqual(report.resolved_field_pair_count, 6)
        fields = {item.field_name: item for item in report.field_resolutions}
        self.assertEqual(fields["analysis_count"].resolved_pair_count, 0)
        for name in (
            "group_count",
            "denominator_count",
            "class_count",
            "category_count",
            "measurement_count",
            "analysis_group_id_sets",
        ):
            self.assertEqual(fields[name].resolved_pair_count, 1)
        self.assertEqual(
            fields["group_count"].zero_cause_signature_disagreement_count, 1
        )
        self.assertEqual(fields["class_count"].zero_cause_signature_exact_count, 1)
        self.assertEqual(
            fields["analysis_group_id_sets"].present_null_array_involved_pair_count,
            1,
        )
        self.assertEqual(
            fields["analysis_group_id_sets"].present_empty_array_involved_pair_count,
            1,
        )
        self.assertTrue(report.source_presence_provenance_retained)
        self.assertFalse(report.v1_artifacts_mutated)
        self.assertFalse(report.structural_array_values_retained)
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_presence(
                self.presence_spec,
                self.candidate_packet,
                self.structure_report,
                self.sidecars,
                report,
            ),
            (),
        )

    def test_binding_reordering_and_rebinding_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical nct_id order"):
            replace(
                self.presence_spec,
                sidecar_bindings=tuple(reversed(self.presence_spec.sidecar_bindings)),
            )
        rebound = replace(
            self.presence_spec.sidecar_bindings[0], sidecar_sha256="f" * 64
        )
        rebound_spec = replace(
            self.presence_spec,
            sidecar_bindings=(rebound, self.presence_spec.sidecar_bindings[1]),
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "sidecar provenance"
        ):
            compile_clinicaltrials_gov_harmonization_presence(
                rebound_spec,
                self.candidate_packet,
                self.structure_report,
                self.sidecars,
            )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "sidecar count"
        ):
            compile_clinicaltrials_gov_harmonization_presence(
                self.presence_spec,
                self.candidate_packet,
                self.structure_report,
                (*self.sidecars, self.sidecars[0]),
            )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "nct_id values must be unique"
        ):
            compile_clinicaltrials_gov_harmonization_presence(
                self.presence_spec,
                self.candidate_packet,
                self.structure_report,
                (self.sidecars[0], self.sidecars[0]),
            )

    def test_strict_round_trip_and_schemas(self) -> None:
        schema_examples = (
            (SIDECAR_SPEC_SCHEMA, SIDECAR_SPEC_EXAMPLE),
            (PRESENCE_SPEC_SCHEMA, PRESENCE_SPEC_EXAMPLE),
        )
        for schema_path, example_path in schema_examples:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(
                json.loads(example_path.read_text(encoding="utf-8"))
            )
        sidecar_schema = json.loads(SIDECAR_PACKET_SCHEMA.read_text(encoding="utf-8"))
        presence_schema = json.loads(PRESENCE_REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(sidecar_schema)
        Draft202012Validator.check_schema(presence_schema)
        sidecar_value = clinicaltrials_gov_structural_presence_packet_envelope(
            self.sidecars[0]
        )
        presence_value = clinicaltrials_gov_harmonization_presence_report_envelope(
            self.presence_report
        )
        Draft202012Validator(sidecar_schema).validate(sidecar_value)
        Draft202012Validator(presence_schema).validate(presence_value)
        self.assertEqual(
            clinicaltrials_gov_structural_presence_spec_from_json(
                json.dumps(
                    clinicaltrials_gov_structural_presence_spec_to_dict(
                        self.sidecar_specs[0]
                    )
                )
            ),
            self.sidecar_specs[0],
        )
        self.assertEqual(
            clinicaltrials_gov_structural_presence_packet_from_json(
                json.dumps(sidecar_value)
            ),
            self.sidecars[0],
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_presence_spec_from_json(
                json.dumps(
                    clinicaltrials_gov_harmonization_presence_spec_to_dict(
                        self.presence_spec
                    )
                )
            ),
            self.presence_spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_presence_report_from_json(
                json.dumps(presence_value)
            ),
            self.presence_report,
        )
        changed = copy.deepcopy(sidecar_value)
        changed["packet"]["sidecar_id"] = "changed"
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "integrity_sha256"
        ):
            clinicaltrials_gov_structural_presence_packet_from_dict(changed)
        changed_report = copy.deepcopy(presence_value)
        changed_report["report"]["report_id"] = "changed"
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "integrity_sha256"
        ):
            clinicaltrials_gov_harmonization_presence_report_from_dict(changed_report)
        self.assertEqual(
            clinicaltrials_gov_harmonization_presence_report_from_dict(
                _rehashed(changed_report, "report")
            ).report_id,
            "changed",
        )
        with self.assertRaisesRegex(
            ClinicalTrialsGovStructuralPresenceError, "duplicate JSON key"
        ):
            clinicaltrials_gov_structural_presence_packet_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )

    def test_public_ra_and_uc_exact_presence_resolution(self) -> None:
        schema = Draft202012Validator(
            json.loads(PRESENCE_REPORT_SCHEMA.read_text(encoding="utf-8"))
        )
        loaded = {}
        for cohort, (spec_path, report_path) in PUBLIC.items():
            spec = clinicaltrials_gov_harmonization_presence_spec_from_json(
                spec_path.read_text(encoding="utf-8")
            )
            report_text = report_path.read_text(encoding="utf-8")
            schema.validate(json.loads(report_text))
            report = clinicaltrials_gov_harmonization_presence_report_from_json(
                report_text
            )
            self.assertEqual(report.spec_sha256, spec.fingerprint)
            self.assertTrue(report.source_presence_provenance_retained)
            self.assertFalse(report.structural_array_values_retained)
            for forbidden in (
                '"record_id"',
                '"source_json_pointer"',
                '"source_value_sha256"',
                '"endpoint_candidate_id"',
                '"title"',
            ):
                self.assertNotIn(forbidden, report_text)
            loaded[cohort] = report
        ra = loaded["ra"]
        self.assertEqual(
            ra.fingerprint,
            "6aefcc37335edfffeb9e56bab65f3553a9ed556a61297bd830f4208089434390",
        )
        self.assertEqual(ra.resolved_field_pair_count, 0)
        self.assertEqual(
            [item.structural_array_record_count for item in ra.trial_profiles],
            [50, 75],
        )
        uc = loaded["uc"]
        self.assertEqual(
            uc.fingerprint,
            "b616abe93c94d76d0b2be0dd592416993f1e6ccdbc1da42dc5cc5b9b1398c4fc",
        )
        self.assertEqual(uc.resolved_field_pair_count, 192)
        self.assertEqual(
            [item.structural_array_record_count for item in uc.trial_profiles],
            [169, 90],
        )
        uc_fields = {item.field_name: item for item in uc.field_resolutions}
        for name in ("analysis_count", "analysis_group_id_sets"):
            self.assertEqual(
                (
                    uc_fields[name].resolved_pair_count,
                    uc_fields[name].absent_array_involved_pair_count,
                    uc_fields[name].zero_cause_signature_exact_count,
                    uc_fields[name].zero_cause_signature_disagreement_count,
                ),
                (96, 96, 27, 69),
            )

    def test_summary_and_cli_sidecar(self) -> None:
        self.assertEqual(
            clinicaltrials_gov_structural_presence_summary(self.sidecars[0])[
                "structural_array_record_count"
            ],
            5,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_presence_summary(self.presence_report)[
                "resolved_field_pair_count"
            ],
            6,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_path = root / "bundle"
            spec_path = root / "sidecar-spec.json"
            inventory_path = root / "inventory.json"
            output_path = root / "sidecar.json"
            write_source_bundle(bundle_path, self.bundles[0])
            spec_path.write_text(
                json.dumps(
                    clinicaltrials_gov_structural_presence_spec_to_dict(
                        self.sidecar_specs[0]
                    )
                ),
                encoding="utf-8",
            )
            inventory_path.write_text(
                json.dumps(
                    clinicaltrials_gov_inventory_packet_envelope(self.inventories[0])
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "compile-clinicaltrials-gov-structural-presence",
                    "--spec",
                    str(spec_path),
                    "--bundle",
                    str(bundle_path),
                    "--inventory",
                    str(inventory_path),
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
                "clinicaltrials_gov_structural_presence_compiled",
            )
            self.assertEqual(
                clinicaltrials_gov_structural_presence_packet_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.sidecars[0],
            )
            presence_spec_path = root / "presence-spec.json"
            candidate_path = root / "candidate.json"
            structure_path = root / "structure.json"
            sidecar_paths = [root / f"sidecar-{index}.json" for index in range(2)]
            presence_output_path = root / "presence-report.json"
            presence_spec_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_presence_spec_to_dict(
                        self.presence_spec
                    )
                ),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_packet_envelope(
                        self.candidate_packet
                    )
                ),
                encoding="utf-8",
            )
            structure_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_structure_report_envelope(
                        self.structure_report
                    )
                ),
                encoding="utf-8",
            )
            for path, sidecar in zip(sidecar_paths, self.sidecars, strict=True):
                path.write_text(
                    json.dumps(
                        clinicaltrials_gov_structural_presence_packet_envelope(sidecar)
                    ),
                    encoding="utf-8",
                )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "resolve-clinicaltrials-gov-harmonization-presence",
                    "--spec",
                    str(presence_spec_path),
                    "--candidate-packet",
                    str(candidate_path),
                    "--structure-report",
                    str(structure_path),
                    "--sidecar",
                    str(sidecar_paths[1]),
                    "--sidecar",
                    str(sidecar_paths[0]),
                    "--output",
                    str(presence_output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(completed.stdout)["status"],
                "cross_trial_harmonization_source_presence_resolved",
            )
            self.assertEqual(
                clinicaltrials_gov_harmonization_presence_report_from_json(
                    presence_output_path.read_text(encoding="utf-8")
                ),
                self.presence_report,
            )


if __name__ == "__main__":
    unittest.main()
