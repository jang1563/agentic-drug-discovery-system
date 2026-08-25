from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventoryError,
    ClinicalTrialsGovInventorySpec,
    clinicaltrials_gov_inventory_packet_envelope,
    clinicaltrials_gov_inventory_packet_from_dict,
    clinicaltrials_gov_inventory_packet_from_json,
    clinicaltrials_gov_inventory_spec_from_dict,
    clinicaltrials_gov_inventory_spec_from_json,
    clinicaltrials_gov_inventory_spec_to_dict,
    clinicaltrials_gov_inventory_summary,
    compile_clinicaltrials_gov_inventory,
    validate_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.ingestion import (
    canonical_json_bytes,
    capture_source_bytes,
    write_source_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SPEC_SCHEMA = ROOT / "rl_env/specs/clinicaltrials_gov_inventory_spec.schema.json"
SPEC_EXAMPLE = ROOT / "rl_env/specs/clinicaltrials_gov_inventory_spec.example.json"
PACKET_SCHEMA = ROOT / "rl_env/specs/clinicaltrials_gov_inventory_packet.schema.json"


def _source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _bundle(source: dict | None = None):
    return capture_source_bytes(
        canonical_json_bytes(source or _source()),
        receipt_id="ctgov-test-trial",
        source_id="clinicaltrials-gov-NCT00000001",
        source_version="clinicaltrials-gov-NCT00000001-version-2025-01-01",
        locator="https://clinicaltrials.gov/api/v2/studies/NCT00000001",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )


def _spec() -> ClinicalTrialsGovInventorySpec:
    return ClinicalTrialsGovInventorySpec(
        inventory_id="NCT00000001:registry-record-wide-inventory:v1",
        source_receipt_id="ctgov-test-trial",
        nct_id="NCT00000001",
        registry_version="2025-01-01",
    )


def _rich_source() -> dict:
    source = _source()
    outcomes = source["protocolSection"]["outcomesModule"]
    outcomes["secondaryOutcomes"] = [
        {
            "measure": "Objective Response Rate",
            "timeFrame": "12 months",
            "description": "Protocol secondary outcome A.",
        },
        {
            "measure": "  objective response rate ",
            "timeFrame": "  12   MONTHS ",
            "description": "Protocol secondary outcome B with the same lexical key.",
        },
        {
            "measure": "Quality of Life",
            "timeFrame": "6 months",
        },
    ]
    posted = source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"]
    posted.append(
        {
            "type": "SECONDARY",
            "title": "Objective Response Rate",
            "timeFrame": "12 months",
            "reportingStatus": "POSTED",
            "paramType": "NUMBER",
            "dispersionType": "STANDARD_DEVIATION",
            "unitOfMeasure": "participants",
            "description": "Posted secondary result.",
            "populationDescription": "Response-evaluable participants.",
            "groups": [
                {"id": "OG000", "title": "Test Drug"},
                {"id": "OG001", "title": "Comparator Drug"},
            ],
            "classes": [
                {
                    "denoms": [
                        {
                            "units": "Participants",
                            "counts": [
                                {"groupId": "OG000", "value": "58"},
                                {"groupId": "OG001", "value": "57"},
                            ],
                        }
                    ],
                    "categories": [
                        {
                            "title": "Responders",
                            "measurements": [
                                {"groupId": "OG000", "value": "40"},
                                {"groupId": "OG001", "value": "28"},
                            ],
                        }
                    ],
                }
            ],
            "analyses": [{"groupIds": ["OG000", "OG001"]}],
        }
    )
    posted.append(
        {
            "type": "SECONDARY",
            "title": "Overall Survival",
            "timeFrame": "36 months",
            "reportingStatus": "POSTED",
        }
    )
    adverse = source["resultsSection"]["adverseEventsModule"]
    adverse["frequencyThreshold"] = "5"
    adverse["eventGroups"][0].update({"otherNumAffected": 20, "otherNumAtRisk": 60})
    adverse["eventGroups"][1].update({"otherNumAffected": 25, "otherNumAtRisk": 60})
    adverse["otherEvents"] = [
        {
            "term": "Synthetic other event",
            "organSystem": "General disorders",
            "assessmentType": "SYSTEMATIC_ASSESSMENT",
            "notes": "Public aggregate event note.",
            "stats": [
                {
                    "groupId": "EG000",
                    "numAffected": 20,
                    "numAtRisk": 60,
                    "numEvents": 24,
                },
                {
                    "groupId": "EG001",
                    "numAffected": 25,
                    "numAtRisk": 60,
                    "numEvents": 29,
                },
            ],
        }
    ]
    return source


def _rehashed(envelope: dict) -> dict:
    encoded = json.dumps(
        envelope["packet"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    envelope["integrity_sha256"] = hashlib.sha256(encoded).hexdigest()
    return envelope


class ClinicalTrialsGovInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = _spec()
        cls.bundle = _bundle(_rich_source())
        cls.packet = compile_clinicaltrials_gov_inventory(cls.spec, cls.bundle)

    def test_complete_protocol_posted_and_safety_enumeration(self) -> None:
        packet = self.packet
        self.assertEqual(packet.protocol_outcome_count, 4)
        self.assertEqual(packet.posted_outcome_count, 3)
        self.assertEqual(packet.lexical_link_candidate_count, 3)
        self.assertEqual(packet.unmatched_protocol_outcome_count, 1)
        self.assertEqual(packet.unmatched_posted_outcome_count, 1)
        self.assertEqual(packet.ambiguous_protocol_outcome_count, 0)
        self.assertEqual(packet.ambiguous_posted_outcome_count, 1)
        self.assertEqual(packet.safety_group_count, 2)
        self.assertEqual(packet.serious_event_count, 2)
        self.assertEqual(packet.other_event_count, 1)
        self.assertEqual(packet.safety_event_stat_count, 6)
        self.assertEqual(
            [item.source_index for item in packet.protocol_outcomes], [0, 0, 1, 2]
        )
        self.assertEqual(
            [item.source_index for item in packet.posted_outcomes], [0, 1, 2]
        )
        self.assertEqual(
            packet.posted_outcomes[1].denominator_group_ids,
            ("OG000", "OG001"),
        )
        self.assertEqual(
            packet.posted_outcomes[1].measurement_group_ids,
            ("OG000", "OG001"),
        )
        self.assertEqual(
            packet.other_events[0].stats[0].num_events,
            24,
        )
        self.assertTrue(packet.full_source_array_enumeration_performed)
        self.assertTrue(packet.exact_lexical_reconciliation_only)
        self.assertFalse(packet.reviewer_approval_performed)
        self.assertFalse(packet.endpoint_selected)
        self.assertFalse(packet.endpoint_family_assigned)
        self.assertFalse(packet.ontology_mapping_approved)
        self.assertFalse(packet.estimand_equivalence_inferred)
        self.assertFalse(packet.clinical_comparability_inferred)
        self.assertFalse(packet.comparative_safety_inferred)
        self.assertFalse(packet.benefit_risk_synthesis_performed)
        self.assertFalse(packet.treatment_choice_inferred)
        self.assertEqual(
            validate_clinicaltrials_gov_inventory(self.spec, self.bundle, packet), ()
        )

    def test_lexical_links_are_diagnostic_and_two_sided(self) -> None:
        links = self.packet.lexical_link_candidates
        self.assertEqual(
            {item.protocol_outcome_id for item in links},
            {
                "NCT00000001:protocol:primary:0",
                "NCT00000001:protocol:secondary:0",
                "NCT00000001:protocol:secondary:1",
            },
        )
        self.assertEqual(
            self.packet.posted_outcomes[1].reconciliation_status,
            "ambiguous_exact_candidates",
        )
        self.assertTrue(all(not item.endpoint_identity_approved for item in links))
        self.assertTrue(all(not item.semantic_equivalence_approved for item in links))
        self.assertTrue(all(not item.clinical_comparability_inferred for item in links))

    def test_source_hashes_pointers_and_scope_replay_detect_rebinding(self) -> None:
        envelope = clinicaltrials_gov_inventory_packet_envelope(self.packet)
        rebound = copy.deepcopy(envelope)
        rebound["packet"]["protocol_outcomes"][0]["source_json_pointer"] = (
            "/protocolSection/outcomesModule/secondaryOutcomes/0"
        )
        with self.assertRaises(ValueError):
            clinicaltrials_gov_inventory_packet_from_dict(_rehashed(rebound))

        changed_source = _rich_source()
        changed_source["protocolSection"]["outcomesModule"]["primaryOutcomes"][0][
            "measure"
        ] = "Changed endpoint"
        changed_bundle = _bundle(changed_source)
        self.assertEqual(
            validate_clinicaltrials_gov_inventory(
                self.spec, changed_bundle, self.packet
            ),
            ("clinicaltrials_gov_inventory_packet_mismatch",),
        )

    def test_strict_readers_integrity_counts_unknown_fields_and_nonclaims(self) -> None:
        envelope = clinicaltrials_gov_inventory_packet_envelope(self.packet)
        self.assertEqual(
            clinicaltrials_gov_inventory_packet_from_dict(envelope), self.packet
        )
        self.assertEqual(
            clinicaltrials_gov_inventory_packet_from_json(json.dumps(envelope)),
            self.packet,
        )

        changed = copy.deepcopy(envelope)
        changed["packet"]["protocol_outcome_count"] += 1
        with self.assertRaises(ValueError):
            clinicaltrials_gov_inventory_packet_from_dict(_rehashed(changed))

        changed = copy.deepcopy(envelope)
        changed["packet"]["endpoint_selected"] = True
        with self.assertRaises(ValueError):
            clinicaltrials_gov_inventory_packet_from_dict(_rehashed(changed))

        changed = copy.deepcopy(envelope)
        changed["packet"]["unexpected"] = "field"
        with self.assertRaises(ClinicalTrialsGovInventoryError):
            clinicaltrials_gov_inventory_packet_from_dict(_rehashed(changed))

        changed = copy.deepcopy(envelope)
        changed["packet"]["nct_id"] = "NCT00000002"
        with self.assertRaises(ValueError):
            clinicaltrials_gov_inventory_packet_from_dict(changed)

        text = json.dumps(envelope)
        duplicate = text.replace(
            '"schema_version":', '"schema_version": "duplicate", "schema_version":', 1
        )
        with self.assertRaises(ClinicalTrialsGovInventoryError):
            clinicaltrials_gov_inventory_packet_from_json(duplicate)
        with self.assertRaises(ClinicalTrialsGovInventoryError):
            clinicaltrials_gov_inventory_packet_from_json('{"schema_version":NaN}')

    def test_specs_and_packets_validate_against_strict_schemas(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator(spec_schema).validate(
            clinicaltrials_gov_inventory_spec_to_dict(self.spec)
        )
        example = json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator(spec_schema).validate(example)
        self.assertEqual(
            clinicaltrials_gov_inventory_spec_from_dict(example), self.spec
        )
        Draft202012Validator(packet_schema).validate(
            clinicaltrials_gov_inventory_packet_envelope(self.packet)
        )
        self.assertEqual(
            clinicaltrials_gov_inventory_spec_from_dict(
                clinicaltrials_gov_inventory_spec_to_dict(self.spec)
            ),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_inventory_spec_from_json(
                json.dumps(clinicaltrials_gov_inventory_spec_to_dict(self.spec))
            ),
            self.spec,
        )

    def test_missing_modules_remain_visible_instead_of_becoming_empty_claims(
        self,
    ) -> None:
        source = _source()
        source["hasResults"] = False
        del source["resultsSection"]
        del source["protocolSection"]["outcomesModule"]
        packet = compile_clinicaltrials_gov_inventory(self.spec, _bundle(source))
        self.assertFalse(packet.source_has_results)
        self.assertFalse(packet.protocol_outcome_module_present)
        self.assertFalse(packet.posted_outcome_module_present)
        self.assertFalse(packet.adverse_event_module_present)
        self.assertEqual(packet.protocol_outcome_count, 0)
        self.assertEqual(packet.posted_outcome_count, 0)
        self.assertEqual(packet.safety_group_count, 0)

    def test_source_duplicate_keys_and_nonfinite_values_fail_before_inventory(
        self,
    ) -> None:
        payload = canonical_json_bytes(_source())
        duplicate = payload.replace(
            b'"hasResults": true',
            b'"hasResults": true, "hasResults": true',
            1,
        )
        with self.assertRaises(ClinicalTrialsGovInventoryError):
            compile_clinicaltrials_gov_inventory(
                self.spec,
                capture_source_bytes(
                    duplicate,
                    receipt_id="ctgov-test-trial",
                    source_id="clinicaltrials-gov-NCT00000001",
                    source_version=(
                        "clinicaltrials-gov-NCT00000001-version-2025-01-01"
                    ),
                    locator=("https://clinicaltrials.gov/api/v2/studies/NCT00000001"),
                    retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                    media_type="application/json",
                    capture_method="https",
                    http_status=200,
                ),
            )
        nonfinite = payload.replace(b'"hasResults": true', b'"x": NaN', 1)
        with self.assertRaises(ClinicalTrialsGovInventoryError):
            compile_clinicaltrials_gov_inventory(
                self.spec,
                capture_source_bytes(
                    nonfinite,
                    receipt_id="ctgov-test-trial",
                    source_id="clinicaltrials-gov-NCT00000001",
                    source_version=(
                        "clinicaltrials-gov-NCT00000001-version-2025-01-01"
                    ),
                    locator=("https://clinicaltrials.gov/api/v2/studies/NCT00000001"),
                    retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                    media_type="application/json",
                    capture_method="https",
                    http_status=200,
                ),
            )

    def test_cli_compiles_external_bundle_to_strict_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_path = write_source_bundle(root / "bundle", self.bundle)
            spec_path = root / "spec.json"
            output_path = root / "inventory.json"
            spec_path.write_bytes(
                canonical_json_bytes(
                    clinicaltrials_gov_inventory_spec_to_dict(self.spec)
                )
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "extract-clinicaltrials-gov-inventory",
                    "--spec",
                    str(spec_path),
                    "--bundle",
                    str(bundle_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "registry_inventory_compiled")
            self.assertEqual(report["protocol_outcome_count"], 4)
            self.assertEqual(report["posted_outcome_count"], 3)
            self.assertEqual(
                clinicaltrials_gov_inventory_packet_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.packet,
            )

    def test_summary_is_bounded_and_machine_readable(self) -> None:
        summary = clinicaltrials_gov_inventory_summary(self.packet)
        self.assertEqual(summary["nct_id"], "NCT00000001")
        self.assertEqual(summary["protocol_outcome_count"], 4)
        self.assertFalse(summary["reviewer_approval_performed"])
        self.assertFalse(summary["benefit_risk_synthesis_performed"])


if __name__ == "__main__":
    unittest.main()
