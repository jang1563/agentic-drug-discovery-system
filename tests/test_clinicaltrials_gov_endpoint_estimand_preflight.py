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

from agentic_drug_discovery.clinicaltrials_gov_endpoint_estimand_preflight import (
    ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
    READY_FOR_ENDPOINT_ESTIMAND_REVIEW,
    REQUIRED_ESTIMAND_DIMENSIONS,
    SOURCE_COMPLETION_REQUIRED,
    ClinicalTrialsGovEndpointEstimandPreflightError,
    ClinicalTrialsGovEndpointEstimandPreflightSpec,
    clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope,
    clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict,
    clinicaltrials_gov_endpoint_estimand_preflight_packet_from_json,
    clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict,
    clinicaltrials_gov_endpoint_estimand_preflight_spec_from_json,
    clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict,
    clinicaltrials_gov_endpoint_estimand_preflight_summary,
    compile_clinicaltrials_gov_endpoint_estimand_preflight,
    validate_clinicaltrials_gov_endpoint_estimand_preflight,
)
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
    compile_clinicaltrials_gov_harmonization_structure,
)
from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventorySpec,
    compile_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.clinicaltrials_gov_structural_presence import (
    ClinicalTrialsGovHarmonizationPresenceSpec,
    ClinicalTrialsGovStructuralPresenceSpec,
    StructuralPresenceSidecarBinding,
    clinicaltrials_gov_harmonization_presence_report_envelope,
    clinicaltrials_gov_structural_presence_packet_envelope,
    compile_clinicaltrials_gov_harmonization_presence,
    compile_clinicaltrials_gov_structural_presence,
)
from agentic_drug_discovery.ingestion import (
    canonical_json_bytes,
    capture_source_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SPEC_SCHEMA = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_endpoint_estimand_preflight_spec.schema.json"
)
SPEC_EXAMPLE = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_endpoint_estimand_preflight_spec.example.json"
)
PACKET_SCHEMA = (
    ROOT
    / "rl_env/specs/clinicaltrials_gov_endpoint_estimand_preflight_packet.schema.json"
)
AUDIT_SCRIPT = (
    ROOT
    / "scripts/audit/compile_clinicaltrials_gov_endpoint_estimand_preflight.py"
)
PUBLIC_ARTIFACTS = (
    {
        "spec_path": ROOT
        / "docs/ra_olokizumab_mtx_ir_endpoint_estimand_preflight_spec.json",
        "packet_path": ROOT
        / "docs/ra_olokizumab_mtx_ir_endpoint_estimand_preflight_packet.json",
        "spec_file_sha256": (
            "1ac0a657241c1df5fd4b72f1c7744f0e6bf251ceffbf5bee4186f2a37cdedc46"
        ),
        "packet_file_sha256": (
            "e95e836704cd13931e0260fe02c81d39b320afac97e6a807914522261d9154b9"
        ),
        "integrity_sha256": (
            "5cbcbce0ea91616de8512fcb5e58b808577db383d7fffa89ba2d6adf9e4c82b3"
        ),
        "pair_count": 35,
        "source_completion_required_pair_count": 0,
        "ready_for_endpoint_estimand_review_pair_count": 35,
        "nonblocking_context_gap_pair_count": 34,
        "source_hashes": {
            "d1c5b7f19aa2f06f3247ba92ec2f09aa0bf39d7bd2aafd4e58646f4a561d31d1",
            "1adc07342f9a7e3b93c985769d151f89022032d8ffe794656985fb3c897d295d",
        },
    },
    {
        "spec_path": ROOT
        / "docs/uc_ozanimod_endpoint_estimand_preflight_spec.json",
        "packet_path": ROOT
        / "docs/uc_ozanimod_endpoint_estimand_preflight_packet.json",
        "spec_file_sha256": (
            "b4c9730e3563966fb7ff89a58cc90a65c9a17f59a1f45d8e86a653cf563e8047"
        ),
        "packet_file_sha256": (
            "525e50a83a6098ea95f0bce4f210a6dbe9a65b686d3b42dd18c213afe80ba0a1"
        ),
        "integrity_sha256": (
            "0af8e92339cc2d1657695f1f7f7b1b6bd8229e9dc865101bc1cd6755e7356640"
        ),
        "pair_count": 110,
        "source_completion_required_pair_count": 96,
        "ready_for_endpoint_estimand_review_pair_count": 14,
        "nonblocking_context_gap_pair_count": 110,
        "source_hashes": {
            "6baf9b0c0f267a9c18afe543760a204ba7edfc0ff71cc848971ced0c0b69d00a",
            "af38449d4374221082e4c769917c3b4c3aad2ff3c8431528edcf197e5000e435",
        },
    },
)


def _base_source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _complete_outcome() -> dict:
    outcome = copy.deepcopy(
        _base_source()["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]
    )
    outcome["reportingStatus"] = "POSTED"
    outcome["dispersionType"] = "STANDARD_DEVIATION"
    outcome["unitOfMeasure"] = "months"
    return outcome


def _inventory_bundle(nct_id: str, outcomes: list[dict]):
    source = _base_source()
    source["protocolSection"]["identificationModule"]["nctId"] = nct_id
    source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"] = outcomes
    receipt_id = f"ctgov-preflight-{nct_id}"
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


def _pipeline(left_outcomes: list[dict], right_outcomes: list[dict]):
    inventory_bundles = (
        _inventory_bundle("NCT00000001", left_outcomes),
        _inventory_bundle("NCT00000002", right_outcomes),
    )
    inventories = tuple(item[0] for item in inventory_bundles)
    bundles = tuple(item[1] for item in inventory_bundles)
    sidecars = tuple(
        compile_clinicaltrials_gov_structural_presence(
            ClinicalTrialsGovStructuralPresenceSpec(
                sidecar_id=f"{inventory.nct_id}:structural-presence:v1",
                inventory_sha256=inventory.fingerprint,
                source_content_hash_sha256=bundle.receipt.content_hash,
                max_structural_array_record_count=1000,
            ),
            bundle,
            inventory,
        )
        for inventory, bundle in zip(inventories, bundles, strict=True)
    )
    candidate_spec = ClinicalTrialsGovHarmonizationCandidateSpec(
        packet_id="synthetic-endpoint-estimand-candidates:v1",
        inventory_bindings=tuple(
            ClinicalTrialsGovHarmonizationInventoryBinding(
                inventory_id=inventory.inventory_id,
                nct_id=inventory.nct_id,
                inventory_sha256=inventory.fingerprint,
            )
            for inventory in inventories
        ),
        max_endpoint_candidate_count=20,
        max_pair_count=100,
    )
    candidate = compile_clinicaltrials_gov_harmonization_candidates(
        candidate_spec, tuple(reversed(inventories))
    )
    diagnostic = compile_clinicaltrials_gov_harmonization_diagnostic(
        ClinicalTrialsGovHarmonizationDiagnosticSpec(
            report_id="synthetic-endpoint-estimand-diagnostic:v1",
            candidate_packet_sha256=candidate.fingerprint,
        ),
        candidate,
    )
    structure = compile_clinicaltrials_gov_harmonization_structure(
        ClinicalTrialsGovHarmonizationStructureSpec(
            report_id="synthetic-endpoint-estimand-structure:v1",
            candidate_packet_sha256=candidate.fingerprint,
            diagnostic_report_sha256=diagnostic.fingerprint,
        ),
        candidate,
        diagnostic,
    )
    bindings = tuple(
        StructuralPresenceSidecarBinding(
            nct_id=sidecar.nct_id,
            inventory_sha256=sidecar.inventory_sha256,
            sidecar_sha256=sidecar.fingerprint,
        )
        for sidecar in sidecars
    )
    presence = compile_clinicaltrials_gov_harmonization_presence(
        ClinicalTrialsGovHarmonizationPresenceSpec(
            report_id="synthetic-endpoint-estimand-presence:v1",
            candidate_packet_sha256=candidate.fingerprint,
            structure_report_sha256=structure.fingerprint,
            sidecar_bindings=bindings,
        ),
        candidate,
        structure,
        tuple(reversed(sidecars)),
    )
    spec = ClinicalTrialsGovEndpointEstimandPreflightSpec(
        packet_id="synthetic-endpoint-estimand-preflight:v1",
        candidate_packet_sha256=candidate.fingerprint,
        presence_report_sha256=presence.fingerprint,
        sidecar_bindings=bindings,
        max_pair_count=100,
    )
    packet = compile_clinicaltrials_gov_endpoint_estimand_preflight(
        spec, candidate, presence, tuple(reversed(sidecars))
    )
    return spec, packet, candidate, presence, sidecars


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


class ClinicalTrialsGovEndpointEstimandPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        left_missing = _complete_outcome()
        left_missing.pop("analyses")
        left_complete = _complete_outcome()
        right_null_group_ids = _complete_outcome()
        right_null_group_ids["analyses"][0]["groupIds"] = None
        right_complete = _complete_outcome()
        (
            cls.spec,
            cls.packet,
            cls.candidate,
            cls.presence,
            cls.sidecars,
        ) = _pipeline(
            [left_missing, left_complete],
            [right_null_group_ids, right_complete],
        )

    def test_routes_missing_analysis_group_ids_and_ready_pair(self) -> None:
        self.assertEqual(self.packet.pair_count, 4)
        self.assertEqual(self.packet.source_completion_required_pair_count, 3)
        self.assertEqual(self.packet.identity_reconciliation_required_pair_count, 0)
        self.assertEqual(self.packet.ready_for_endpoint_estimand_review_pair_count, 1)
        self.assertEqual(self.packet.missing_analysis_pair_count, 2)
        self.assertEqual(self.packet.incomplete_analysis_group_ids_pair_count, 2)
        self.assertEqual(self.packet.blocking_endpoint_field_pair_count, 0)
        self.assertEqual(self.packet.nonblocking_context_gap_pair_count, 0)
        self.assertEqual(self.packet.unresolved_protocol_link_pair_count, 0)
        routes = {item.review_route for item in self.packet.pair_preflights}
        self.assertEqual(
            routes, {SOURCE_COMPLETION_REQUIRED, READY_FOR_ENDPOINT_ESTIMAND_REVIEW}
        )
        self.assertEqual(
            {item.blocker_code: item.pair_count for item in self.packet.blocker_counts},
            {
                "left.outcome_analyses.absent": 2,
                "right.analysis_group_ids.present_null": 2,
            },
        )

    def test_five_estimand_dimensions_remain_unresolved_without_review(self) -> None:
        for item in self.packet.pair_preflights:
            self.assertEqual(item.required_estimand_dimensions, REQUIRED_ESTIMAND_DIMENSIONS)
            self.assertEqual(item.unresolved_estimand_dimensions, REQUIRED_ESTIMAND_DIMENSIONS)
            self.assertFalse(item.automatic_exclusion_performed)
            self.assertFalse(item.reviewer_approval_performed)
            self.assertFalse(item.estimand_equivalence_approved)
        self.assertFalse(self.packet.automatic_exclusion_performed)
        self.assertFalse(self.packet.reviewer_approval_performed)

    def test_unmatched_protocol_link_has_distinct_identity_route(self) -> None:
        left = _complete_outcome()
        left["title"] = "Unmapped synthetic endpoint"
        spec, packet, *_ = _pipeline([left], [_complete_outcome()])
        self.assertEqual(packet.source_completion_required_pair_count, 0)
        self.assertEqual(packet.identity_reconciliation_required_pair_count, 1)
        self.assertEqual(packet.ready_for_endpoint_estimand_review_pair_count, 0)
        self.assertEqual(
            packet.pair_preflights[0].review_route,
            ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
        )
        self.assertIn(
            "left.protocol_link.unmatched",
            packet.pair_preflights[0].blocker_codes,
        )
        self.assertEqual(spec.required_estimand_dimensions, REQUIRED_ESTIMAND_DIMENSIONS)

    def test_missing_dispersion_is_nonblocking_context_not_estimand_blocker(self) -> None:
        left = _complete_outcome()
        right = _complete_outcome()
        left.pop("dispersionType")
        right.pop("dispersionType")
        _, packet, *_ = _pipeline([left], [right])
        pair = packet.pair_preflights[0]
        self.assertEqual(pair.review_route, READY_FOR_ENDPOINT_ESTIMAND_REVIEW)
        self.assertEqual(pair.blocker_codes, ())
        self.assertEqual(
            pair.context_gap_codes,
            (
                "left.endpoint_field.dispersion_type.missing",
                "right.endpoint_field.dispersion_type.missing",
            ),
        )
        self.assertEqual(packet.nonblocking_context_gap_pair_count, 1)
        self.assertEqual(packet.blocking_endpoint_field_pair_count, 0)

    def test_exact_bindings_and_replay_are_order_independent(self) -> None:
        rebuilt = compile_clinicaltrials_gov_endpoint_estimand_preflight(
            self.spec,
            self.candidate,
            self.presence,
            self.sidecars,
        )
        self.assertEqual(rebuilt, self.packet)
        self.assertEqual(
            validate_clinicaltrials_gov_endpoint_estimand_preflight(
                self.spec,
                self.candidate,
                self.presence,
                tuple(reversed(self.sidecars)),
                self.packet,
            ),
            (),
        )
        rebound = replace(self.spec, candidate_packet_sha256="0" * 64)
        with self.assertRaises(ClinicalTrialsGovEndpointEstimandPreflightError):
            compile_clinicaltrials_gov_endpoint_estimand_preflight(
                rebound, self.candidate, self.presence, self.sidecars
            )

    def test_strict_readers_and_integrity(self) -> None:
        spec_value = clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict(
            self.spec
        )
        envelope = clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope(
            self.packet
        )
        self.assertEqual(
            clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict(spec_value),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_endpoint_estimand_preflight_spec_from_json(
                json.dumps(spec_value)
            ),
            self.spec,
        )
        self.assertEqual(
            clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(envelope),
            self.packet,
        )
        self.assertEqual(
            clinicaltrials_gov_endpoint_estimand_preflight_packet_from_json(
                json.dumps(envelope)
            ),
            self.packet,
        )
        changed = copy.deepcopy(envelope)
        changed["packet"]["pair_preflights"][0]["review_state"] = (
            "pending_human_review"
        )
        with self.assertRaises(ValueError):
            clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(
                _rehashed(changed)
            )
        unknown = copy.deepcopy(spec_value)
        unknown["unexpected"] = True
        with self.assertRaises(ClinicalTrialsGovEndpointEstimandPreflightError):
            clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict(unknown)
        with self.assertRaises(ClinicalTrialsGovEndpointEstimandPreflightError):
            clinicaltrials_gov_endpoint_estimand_preflight_spec_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )

    def test_schemas_and_example(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator(spec_schema).validate(example)
        Draft202012Validator(spec_schema).validate(
            clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict(self.spec)
        )
        Draft202012Validator(packet_schema).validate(
            clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope(
                self.packet
            )
        )

    def test_exact_public_artifacts_are_strictly_bound(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        for expected in PUBLIC_ARTIFACTS:
            spec_path = expected["spec_path"]
            packet_path = expected["packet_path"]
            spec_value = json.loads(spec_path.read_text(encoding="utf-8"))
            packet_value = json.loads(packet_path.read_text(encoding="utf-8"))
            spec = clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict(
                spec_value
            )
            packet = clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(
                packet_value
            )

            Draft202012Validator(spec_schema).validate(spec_value)
            Draft202012Validator(packet_schema).validate(packet_value)
            self.assertEqual(
                hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                expected["spec_file_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(packet_path.read_bytes()).hexdigest(),
                expected["packet_file_sha256"],
            )
            self.assertEqual(packet.fingerprint, expected["integrity_sha256"])
            self.assertEqual(packet.spec_sha256, spec.fingerprint)
            self.assertEqual(packet.pair_count, expected["pair_count"])
            self.assertEqual(
                packet.source_completion_required_pair_count,
                expected["source_completion_required_pair_count"],
            )
            self.assertEqual(
                packet.ready_for_endpoint_estimand_review_pair_count,
                expected["ready_for_endpoint_estimand_review_pair_count"],
            )
            self.assertEqual(
                packet.nonblocking_context_gap_pair_count,
                expected["nonblocking_context_gap_pair_count"],
            )
            self.assertEqual(
                {
                    binding.source_content_hash_sha256
                    for binding in packet.source_bindings
                },
                expected["source_hashes"],
            )
            self.assertFalse(packet.automatic_exclusion_performed)
            self.assertFalse(packet.reviewer_approval_performed)

    def test_summary_is_payload_free(self) -> None:
        summary = clinicaltrials_gov_endpoint_estimand_preflight_summary(self.packet)
        self.assertEqual(summary["pair_count"], 4)
        self.assertNotIn("pair_preflights", summary)
        serialized = json.dumps(
            clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope(
                self.packet
            )
        )
        self.assertNotIn("Progression-Free Survival", serialized)
        self.assertNotIn("All randomized participants", serialized)

    def test_cli_compiles_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "spec.json"
            candidate_path = tmp_path / "candidate.json"
            presence_path = tmp_path / "presence.json"
            sidecar_paths = [tmp_path / f"sidecar-{index}.json" for index in range(2)]
            output_path = tmp_path / "preflight.json"
            spec_path.write_text(
                json.dumps(
                    clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict(
                        self.spec
                    )
                ),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(clinicaltrials_gov_harmonization_packet_envelope(self.candidate)),
                encoding="utf-8",
            )
            presence_path.write_text(
                json.dumps(
                    clinicaltrials_gov_harmonization_presence_report_envelope(
                        self.presence
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
            command = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.ingestion_cli",
                "compile-clinicaltrials-gov-endpoint-estimand-preflight",
                "--spec",
                str(spec_path),
                "--candidate-packet",
                str(candidate_path),
                "--presence-report",
                str(presence_path),
                "--sidecar",
                str(sidecar_paths[1]),
                "--sidecar",
                str(sidecar_paths[0]),
                "--output",
                str(output_path),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)
            self.assertEqual(
                result["status"], "endpoint_estimand_review_preflight_compiled"
            )
            self.assertEqual(result["source_completion_required_pair_count"], 3)
            self.assertEqual(
                clinicaltrials_gov_endpoint_estimand_preflight_packet_from_json(
                    output_path.read_text(encoding="utf-8")
                ),
                self.packet,
            )

    def test_exact_cohort_audit_replays_and_bounds_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            studies: list[tuple[str, Path, str]] = []
            for nct_id in ("NCT00000001", "NCT00000002"):
                source = _base_source()
                source["protocolSection"]["identificationModule"]["nctId"] = nct_id
                source_path = tmp_path / f"{nct_id}.json"
                source_path.write_text(
                    json.dumps(source, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
                studies.append(
                    (
                        nct_id,
                        source_path,
                        hashlib.sha256(source_path.read_bytes()).hexdigest(),
                    )
                )
            spec_path = tmp_path / "audit-spec.json"
            packet_path = tmp_path / "audit-packet.json"
            command = [
                sys.executable,
                str(AUDIT_SCRIPT),
                "--cohort-id",
                "synthetic-audit",
                "--registry-version",
                "2025-01-01",
                "--retrieved-at",
                "2025-01-02T00:00:00+00:00",
            ]
            for nct_id, source_path, _ in studies:
                command.extend(("--study", f"{nct_id}={source_path}"))
            for nct_id, _, source_hash in studies:
                command.extend(("--source-sha256", f"{nct_id}={source_hash}"))
            command.extend(
                (
                    "--max-source-bytes",
                    str(1024 * 1024),
                    "--spec-output",
                    str(spec_path),
                    "--packet-output",
                    str(packet_path),
                )
            )
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["pair_count"], 1)
            self.assertEqual(summary["ready_for_endpoint_estimand_review_pair_count"], 1)
            clinicaltrials_gov_endpoint_estimand_preflight_spec_from_json(
                spec_path.read_text(encoding="utf-8")
            )
            clinicaltrials_gov_endpoint_estimand_preflight_packet_from_json(
                packet_path.read_text(encoding="utf-8")
            )

            bounded_command = command[:-6] + [
                "--max-source-bytes",
                "1",
                "--spec-output",
                str(tmp_path / "bounded-spec.json"),
                "--packet-output",
                str(tmp_path / "bounded-packet.json"),
            ]
            bounded = subprocess.run(
                bounded_command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(bounded.returncode, 0)
            self.assertIn("source exceeds max-source-bytes", bounded.stderr)
            self.assertFalse((tmp_path / "bounded-spec.json").exists())
            self.assertFalse((tmp_path / "bounded-packet.json").exists())


if __name__ == "__main__":
    unittest.main()
