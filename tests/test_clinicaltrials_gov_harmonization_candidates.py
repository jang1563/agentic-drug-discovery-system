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
    ALL_MECHANICAL_FIELDS_EQUAL,
    INCOMPLETE_SOURCE_FIELDS,
    ClinicalTrialsGovHarmonizationCandidateSpec,
    ClinicalTrialsGovHarmonizationError,
    ClinicalTrialsGovHarmonizationInventoryBinding,
    clinicaltrials_gov_harmonization_packet_envelope,
    clinicaltrials_gov_harmonization_packet_from_dict,
    clinicaltrials_gov_harmonization_packet_from_json,
    clinicaltrials_gov_harmonization_spec_from_dict,
    clinicaltrials_gov_harmonization_spec_from_json,
    clinicaltrials_gov_harmonization_spec_to_dict,
    clinicaltrials_gov_harmonization_summary,
    compile_clinicaltrials_gov_harmonization_candidates,
    validate_clinicaltrials_gov_harmonization_candidates,
)
from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventorySpec,
    clinicaltrials_gov_inventory_packet_envelope,
    compile_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.ingestion import (
    canonical_json_bytes,
    capture_source_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SPEC_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_candidate_spec.schema.json"
)
SPEC_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_candidate_spec.example.json"
)
PACKET_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_harmonization_candidate_packet.schema.json"
)


def _base_source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _complete_outcome(title: str = "Progression-Free Survival") -> dict:
    outcome = copy.deepcopy(
        _base_source()["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    )
    outcome["title"] = title
    outcome["dispersionType"] = "INTER_QUARTILE_RANGE"
    return outcome


def _inventory_packet(
    nct_id: str,
    outcomes: list[dict],
    *,
    adverse_time_frame: str,
    duplicate_protocol_primary: bool = False,
    posted_module_present: bool = True,
):
    source = _base_source()
    source["protocolSection"]["identificationModule"]["nctId"] = nct_id
    if posted_module_present:
        source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"] = outcomes
    else:
        del source["resultsSection"]["outcomeMeasuresModule"]
    if duplicate_protocol_primary:
        source["protocolSection"]["outcomesModule"]["secondaryOutcomes"] = [
            {
                "measure": " progression-free survival ",
                "timeFrame": " 24   MONTHS ",
            }
        ]
    source["resultsSection"]["adverseEventsModule"]["timeFrame"] = adverse_time_frame
    receipt_id = f"ctgov-harmonization-{nct_id}"
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
    spec = ClinicalTrialsGovInventorySpec(
        inventory_id=f"{nct_id}:registry-record-wide-inventory:v1",
        source_receipt_id=receipt_id,
        nct_id=nct_id,
        registry_version=version,
    )
    return compile_clinicaltrials_gov_inventory(spec, bundle)


def _spec(
    packets,
    max_pair_count: int = 100,
    max_endpoint_candidate_count: int = 100,
):
    bindings = tuple(
        ClinicalTrialsGovHarmonizationInventoryBinding(
            inventory_id=item.inventory_id,
            nct_id=item.nct_id,
            inventory_sha256=item.fingerprint,
        )
        for item in sorted(packets, key=lambda item: item.nct_id)
    )
    return ClinicalTrialsGovHarmonizationCandidateSpec(
        packet_id="synthetic-cross-trial-harmonization:v1",
        inventory_bindings=bindings,
        max_endpoint_candidate_count=max_endpoint_candidate_count,
        max_pair_count=max_pair_count,
    )


def _rehashed(envelope: dict) -> dict:
    envelope["integrity_sha256"] = hashlib.sha256(
        json.dumps(
            envelope["packet"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return envelope


class ClinicalTrialsGovHarmonizationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        first_secondary = _complete_outcome("Objective Response Rate")
        first_secondary["timeFrame"] = "12 months"
        first_secondary["paramType"] = "NUMBER"
        first_secondary["unitOfMeasure"] = "participants"
        cls.first = _inventory_packet(
            "NCT00000001",
            [_complete_outcome(), first_secondary],
            adverse_time_frame="From first dose through 30 days after last dose",
            duplicate_protocol_primary=True,
        )

        incomplete = _complete_outcome("Objective Response Rate")
        incomplete.pop("timeFrame")
        incomplete["paramType"] = "NUMBER"
        incomplete["unitOfMeasure"] = "participants"
        third = _complete_outcome("Overall Survival")
        third["timeFrame"] = "36 months"
        cls.second = _inventory_packet(
            "NCT00000002",
            [_complete_outcome(), incomplete, third],
            adverse_time_frame="From first dose through 60 days after last dose",
        )
        cls.zero = _inventory_packet(
            "NCT00000003",
            [],
            adverse_time_frame="From first dose through 30 days after last dose",
        )
        cls.packets = (cls.second, cls.zero, cls.first)
        cls.spec = _spec(cls.packets)
        cls.packet = compile_clinicaltrials_gov_harmonization_candidates(
            cls.spec, cls.packets
        )

    def test_full_cross_trial_cartesian_universe_and_zero_trial_retention(self) -> None:
        packet = self.packet
        self.assertEqual(packet.inventory_count, 3)
        self.assertEqual(packet.endpoint_candidate_count, 5)
        self.assertEqual(packet.pair_candidate_count, 6)
        self.assertEqual(packet.zero_posted_outcome_inventory_count, 1)
        self.assertEqual(
            [item.nct_id for item in packet.safety_contexts],
            ["NCT00000001", "NCT00000002", "NCT00000003"],
        )
        zero_context = packet.safety_contexts[2]
        self.assertTrue(zero_context.source_has_results)
        self.assertTrue(zero_context.posted_outcome_module_present)
        self.assertEqual(zero_context.posted_outcome_count, 0)
        self.assertEqual(
            {(item.left_nct_id, item.right_nct_id) for item in packet.pair_candidates},
            {("NCT00000001", "NCT00000002")},
        )
        self.assertTrue(packet.full_cross_trial_cartesian_enumeration_performed)
        self.assertTrue(packet.bounded_work_preflight_performed)
        self.assertTrue(packet.source_inventory_integrity_verified)
        self.assertFalse(packet.source_bundle_replay_performed)

    def test_mechanical_equality_missingness_and_nonclaims(self) -> None:
        exact = self.packet.pair_candidates[0]
        self.assertEqual(exact.mechanical_status, ALL_MECHANICAL_FIELDS_EQUAL)
        self.assertTrue(exact.title_exact)
        self.assertTrue(exact.population_description_sha256_exact)
        self.assertFalse(exact.safety_time_frame_exact)
        self.assertFalse(exact.endpoint_identity_approved)
        self.assertFalse(exact.clinical_comparability_inferred)
        self.assertFalse(exact.safety_comparability_inferred)

        incomplete = next(
            item
            for item in self.packet.pair_candidates
            if "right.time_frame" in item.missing_field_codes
        )
        self.assertEqual(incomplete.mechanical_status, INCOMPLETE_SOURCE_FIELDS)
        self.assertFalse(incomplete.time_frame_exact)
        self.assertFalse(self.packet.reviewer_approval_performed)
        self.assertFalse(self.packet.benefit_risk_synthesis_performed)
        self.assertFalse(self.packet.treatment_choice_inferred)

    def test_absent_and_present_empty_posted_modules_remain_distinct(self) -> None:
        absent = _inventory_packet(
            "NCT00000004",
            [],
            adverse_time_frame="From first dose through 30 days after last dose",
            posted_module_present=False,
        )
        packet = compile_clinicaltrials_gov_harmonization_candidates(
            _spec((self.zero, absent)), (absent, self.zero)
        )
        contexts = {item.nct_id: item for item in packet.safety_contexts}
        self.assertTrue(contexts["NCT00000003"].posted_outcome_module_present)
        self.assertFalse(contexts["NCT00000004"].posted_outcome_module_present)
        self.assertEqual(packet.endpoint_candidate_count, 0)
        self.assertEqual(packet.pair_candidate_count, 0)
        self.assertEqual(packet.zero_posted_outcome_inventory_count, 2)

    def test_within_trial_ambiguity_and_safety_provenance_are_carried(self) -> None:
        endpoint = self.packet.endpoint_candidates[0]
        self.assertEqual(
            endpoint.within_trial_reconciliation_status, "ambiguous_exact_candidates"
        )
        self.assertEqual(len(endpoint.within_trial_protocol_outcome_ids), 2)
        self.assertEqual(len(endpoint.within_trial_lexical_link_ids), 2)
        context = self.packet.safety_contexts[0]
        self.assertEqual(context.safety_group_count, 2)
        self.assertEqual(context.serious_event_count, 2)
        self.assertEqual(context.safety_event_stat_count, 4)
        self.assertEqual(
            [item.record_type for item in context.safety_records],
            ["GROUP", "GROUP", "SERIOUS_EVENT", "SERIOUS_EVENT"],
        )
        self.assertTrue(
            all(item.source_record_sha256 for item in context.safety_records)
        )

    def test_bound_fails_before_partial_enumeration(self) -> None:
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationError,
            "expected pair count 6 exceeds max_pair_count 5",
        ):
            compile_clinicaltrials_gov_harmonization_candidates(
                _spec(self.packets, max_pair_count=5), self.packets
            )
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationError,
            "expected endpoint count 5 exceeds max_endpoint_candidate_count 4",
        ):
            compile_clinicaltrials_gov_harmonization_candidates(
                _spec(self.packets, max_endpoint_candidate_count=4),
                self.packets,
            )

    def test_exact_inventory_bindings_and_source_disjointness(self) -> None:
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationError, "exact spec bindings"
        ):
            compile_clinicaltrials_gov_harmonization_candidates(
                self.spec, (self.first, self.second)
            )
        rebound_source = replace(
            self.second.source,
            content_hash_sha256=self.first.source.content_hash_sha256,
        )
        rebound_second = replace(self.second, source=rebound_source)
        packets = (self.first, rebound_second, self.zero)
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationError, "distinct source content hash"
        ):
            compile_clinicaltrials_gov_harmonization_candidates(_spec(packets), packets)

    def test_strict_readers_reject_diagnostic_tamper_and_invalid_json(self) -> None:
        envelope = clinicaltrials_gov_harmonization_packet_envelope(self.packet)
        self.assertEqual(
            clinicaltrials_gov_harmonization_packet_from_dict(envelope), self.packet
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_packet_from_json(json.dumps(envelope)),
            self.packet,
        )
        changed = copy.deepcopy(envelope)
        changed["packet"]["pair_candidates"][0]["safety_time_frame_exact"] = True
        with self.assertRaisesRegex(
            ValueError, "pair candidate diagnostics were rebound"
        ):
            clinicaltrials_gov_harmonization_packet_from_dict(_rehashed(changed))
        with self.assertRaisesRegex(
            ClinicalTrialsGovHarmonizationError, "duplicate JSON key"
        ):
            clinicaltrials_gov_harmonization_packet_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )
        with self.assertRaisesRegex(ClinicalTrialsGovHarmonizationError, "non-finite"):
            clinicaltrials_gov_harmonization_spec_from_json('{"schema_version":NaN}')

    def test_recompile_validation_detects_packet_mismatch(self) -> None:
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_candidates(
                self.spec, self.packets, self.packet
            ),
            (),
        )
        changed = replace(
            self.packet,
            max_pair_count=self.packet.max_pair_count - 1,
        )
        self.assertEqual(
            validate_clinicaltrials_gov_harmonization_candidates(
                self.spec, self.packets, changed
            ),
            ("clinicaltrials_gov_harmonization_packet_mismatch",),
        )

    def test_schemas_example_round_trip_and_summary(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator(spec_schema).validate(example)
        Draft202012Validator(spec_schema).validate(
            clinicaltrials_gov_harmonization_spec_to_dict(self.spec)
        )
        Draft202012Validator(packet_schema).validate(
            clinicaltrials_gov_harmonization_packet_envelope(self.packet)
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_spec_from_dict(
                clinicaltrials_gov_harmonization_spec_to_dict(self.spec)
            ),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_harmonization_spec_from_json(
                json.dumps(clinicaltrials_gov_harmonization_spec_to_dict(self.spec))
            ),
            self.spec,
        )
        summary = clinicaltrials_gov_harmonization_summary(self.packet)
        self.assertEqual(summary["pair_candidate_count"], 6)
        self.assertFalse(summary["clinical_comparability_inferred"])

    def test_cli_compiles_multiple_exact_inventory_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "spec.json"
            output_path = root / "candidate-packet.json"
            spec_path.write_text(
                json.dumps(clinicaltrials_gov_harmonization_spec_to_dict(self.spec)),
                encoding="utf-8",
            )
            inventory_paths = []
            for index, packet in enumerate(self.packets):
                path = root / f"inventory-{index}.json"
                path.write_text(
                    json.dumps(clinicaltrials_gov_inventory_packet_envelope(packet)),
                    encoding="utf-8",
                )
                inventory_paths.append(path)
            command = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.ingestion_cli",
                "compile-clinicaltrials-gov-harmonization-candidates",
                "--spec",
                str(spec_path),
            ]
            for path in inventory_paths:
                command.extend(["--inventory", str(path)])
            command.extend(["--output", str(output_path)])
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(
                report["status"],
                "cross_trial_harmonization_candidates_compiled",
            )
            self.assertEqual(report["pair_candidate_count"], 6)
            self.assertEqual(
                clinicaltrials_gov_harmonization_packet_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.packet,
            )
            bounded_output = root / "bounded-output.json"
            bounded_command = [
                *command[:-2],
                "--output",
                str(bounded_output),
                "--max-bytes",
                "1",
            ]
            bounded = subprocess.run(
                bounded_command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bounded.returncode, 2)
            self.assertIn("inventory packet bytes exceed max-bytes", bounded.stderr)
            self.assertFalse(bounded_output.exists())


if __name__ == "__main__":
    unittest.main()
