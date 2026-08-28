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
from io import BytesIO
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from agentic_drug_discovery.clinicaltrials_gov_endpoint_estimand_preflight import (
    READY_FOR_ENDPOINT_ESTIMAND_REVIEW,
    ClinicalTrialsGovEndpointEstimandPreflightSpec,
    clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict,
    compile_clinicaltrials_gov_endpoint_estimand_preflight,
)
from agentic_drug_discovery.clinicaltrials_gov_estimand_evidence_acquisition import (
    CANDIDATE_PAGES_FOUND,
    EVIDENCE_CUES_ACQUIRED,
    PREFLIGHT_BLOCKED,
    ClinicalTrialsGovEstimandEvidenceAcquisitionError,
    ClinicalTrialsGovEstimandEvidenceAcquisitionSpec,
    EstimandEvidenceDocumentBinding,
    clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope,
    clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict,
    clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict,
    clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict,
    compile_clinicaltrials_gov_estimand_evidence_acquisition,
    validate_clinicaltrials_gov_estimand_evidence_acquisition,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_candidates import (
    ClinicalTrialsGovHarmonizationCandidateSpec,
    ClinicalTrialsGovHarmonizationInventoryBinding,
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
    compile_clinicaltrials_gov_harmonization_presence,
    compile_clinicaltrials_gov_structural_presence,
)
from agentic_drug_discovery.ingestion import canonical_json_bytes, capture_source_bytes


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SPEC_SCHEMA = ROOT / "rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_spec.schema.json"
SPEC_EXAMPLE = ROOT / "rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_spec.example.json"
PACKET_SCHEMA = ROOT / "rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_packet.schema.json"
AUDIT_SCRIPT = ROOT / "scripts/audit/compile_clinicaltrials_gov_estimand_evidence_acquisition.py"
PUBLIC_ARTIFACTS = (
    {
        "spec": ROOT / "docs/ra_olokizumab_mtx_ir_estimand_evidence_acquisition_spec.json",
        "packet": ROOT / "docs/ra_olokizumab_mtx_ir_estimand_evidence_acquisition_packet.json",
        "preflight": ROOT / "docs/ra_olokizumab_mtx_ir_endpoint_estimand_preflight_packet.json",
        "spec_file_sha256": "caae0a22b2f317b2571cf321ee69b93f8dbbeda387840f3dd8fea73427155443",
        "packet_file_sha256": "6e397047064b2befe05ea3374f7174cdebaf23090b8a37c4114fda04e75e928f",
        "integrity_sha256": "5c490580d7fada91c2646d2167a1ea950bde5da2e7d69aeba2a5620804c5db42",
        "documents": 2,
        "pages": 354,
        "pairs": 35,
        "ready": 35,
        "blocked": 0,
        "endpoints": 12,
        "evidence": 60,
        "page_cues": 300,
    },
    {
        "spec": ROOT / "docs/uc_ozanimod_estimand_evidence_acquisition_spec.json",
        "packet": ROOT / "docs/uc_ozanimod_estimand_evidence_acquisition_packet.json",
        "preflight": ROOT / "docs/uc_ozanimod_endpoint_estimand_preflight_packet.json",
        "spec_file_sha256": "b5ae13dc051f6bc4f67a8f698e7ecfe99dc6f1414fa203e910ad0f068bf9e801",
        "packet_file_sha256": "2c24dd179edcca4abfebbf89f8a5c92a5398ce28aacc481dc8ec8720d8b3f7fb",
        "integrity_sha256": "f4197c53faa2cf6eadaf9e1d69b4e145b44af8bf5a8dfdfed719453ede8ceceb",
        "documents": 4,
        "pages": 339,
        "pairs": 110,
        "ready": 14,
        "blocked": 96,
        "endpoints": 9,
        "evidence": 45,
        "page_cues": 209,
    },
)


def _pdf_document() -> bytes:
    writer = PdfWriter()
    page_text = (
        "Randomized placebo treatment group dose regimen",
        "Eligibility inclusion exclusion intent-to-treat analysis population",
        "Primary efficacy endpoint clinical outcome measure at Week 12",
        "Missing data treatment discontinuation rescue medication multiple imputation",
        "Mean change proportion odds ratio ANCOVA confidence interval",
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for text in page_text:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 10 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _outcome(*, analyses: bool = True) -> dict:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    outcome = copy.deepcopy(
        source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    )
    outcome["reportingStatus"] = "POSTED"
    outcome["dispersionType"] = "STANDARD_DEVIATION"
    outcome["unitOfMeasure"] = "percent"
    if not analyses:
        outcome.pop("analyses")
    return outcome


def _pipeline(*, ready: bool = True):
    pdf = _pdf_document()
    inventory_bundles = []
    registry_sources: dict[str, bytes] = {}
    document_sources: dict[str, bytes] = {}
    document_bindings = []
    for index, nct_id in enumerate(("NCT00000001", "NCT00000002")):
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        source["protocolSection"]["identificationModule"]["nctId"] = nct_id
        source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"] = [
            _outcome(analyses=ready or index == 1)
        ]
        source["documentSection"] = {
            "largeDocumentModule": {
                "largeDocs": [
                    {
                        "typeAbbrev": "Prot_SAP",
                        "hasProtocol": True,
                        "hasSap": True,
                        "hasIcf": False,
                        "label": "Study Protocol and Statistical Analysis Plan",
                        "date": "2025-01-01",
                        "uploadDate": "2025-01-02T12:30",
                        "filename": "Prot_SAP_000.pdf",
                        "size": len(pdf),
                    }
                ]
            }
        }
        raw = canonical_json_bytes(source)
        registry_sources[nct_id] = raw
        receipt_id = f"ctgov-acquisition-{nct_id}"
        bundle = capture_source_bytes(
            raw,
            receipt_id=receipt_id,
            source_id=f"clinicaltrials-gov-{nct_id}",
            source_version=f"clinicaltrials-gov-{nct_id}-version-2025-01-01",
            locator=f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
            retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            media_type="application/json",
            capture_method="https",
            http_status=200,
        )
        inventory = compile_clinicaltrials_gov_inventory(
            ClinicalTrialsGovInventorySpec(
                inventory_id=f"{nct_id}:inventory:v1",
                source_receipt_id=receipt_id,
                nct_id=nct_id,
                registry_version="2025-01-01",
            ),
            bundle,
        )
        inventory_bundles.append((inventory, bundle))
        document_id = f"{nct_id}:Prot_SAP_000.pdf"
        document_sources[document_id] = pdf
        document_bindings.append(
            EstimandEvidenceDocumentBinding(
                document_id=document_id,
                nct_id=nct_id,
                filename="Prot_SAP_000.pdf",
                document_roles=("protocol", "sap"),
                source_label="Study Protocol and Statistical Analysis Plan",
                source_locator=(
                    "https://cdn.clinicaltrials.gov/large-docs/"
                    f"{nct_id[-2:]}/{nct_id}/Prot_SAP_000.pdf"
                ),
                source_document_date="2025-01-01",
                source_upload_date="2025-01-02T12:30",
                expected_size_bytes=len(pdf),
                source_content_sha256=hashlib.sha256(pdf).hexdigest(),
            )
        )
    inventories = tuple(item[0] for item in inventory_bundles)
    bundles = tuple(item[1] for item in inventory_bundles)
    sidecars = tuple(
        compile_clinicaltrials_gov_structural_presence(
            ClinicalTrialsGovStructuralPresenceSpec(
                sidecar_id=f"{inventory.nct_id}:presence:v1",
                inventory_sha256=inventory.fingerprint,
                source_content_hash_sha256=bundle.receipt.content_hash,
                max_structural_array_record_count=1000,
            ),
            bundle,
            inventory,
        )
        for inventory, bundle in zip(inventories, bundles, strict=True)
    )
    candidate = compile_clinicaltrials_gov_harmonization_candidates(
        ClinicalTrialsGovHarmonizationCandidateSpec(
            packet_id="synthetic-acquisition-candidates:v1",
            inventory_bindings=tuple(
                ClinicalTrialsGovHarmonizationInventoryBinding(
                    inventory_id=item.inventory_id,
                    nct_id=item.nct_id,
                    inventory_sha256=item.fingerprint,
                )
                for item in inventories
            ),
            max_endpoint_candidate_count=10,
            max_pair_count=10,
        ),
        tuple(reversed(inventories)),
    )
    diagnostic = compile_clinicaltrials_gov_harmonization_diagnostic(
        ClinicalTrialsGovHarmonizationDiagnosticSpec(
            report_id="synthetic-acquisition-diagnostic:v1",
            candidate_packet_sha256=candidate.fingerprint,
        ),
        candidate,
    )
    structure = compile_clinicaltrials_gov_harmonization_structure(
        ClinicalTrialsGovHarmonizationStructureSpec(
            report_id="synthetic-acquisition-structure:v1",
            candidate_packet_sha256=candidate.fingerprint,
            diagnostic_report_sha256=diagnostic.fingerprint,
        ),
        candidate,
        diagnostic,
    )
    sidecar_bindings = tuple(
        StructuralPresenceSidecarBinding(
            nct_id=item.nct_id,
            inventory_sha256=item.inventory_sha256,
            sidecar_sha256=item.fingerprint,
        )
        for item in sidecars
    )
    presence = compile_clinicaltrials_gov_harmonization_presence(
        ClinicalTrialsGovHarmonizationPresenceSpec(
            report_id="synthetic-acquisition-presence:v1",
            candidate_packet_sha256=candidate.fingerprint,
            structure_report_sha256=structure.fingerprint,
            sidecar_bindings=sidecar_bindings,
        ),
        candidate,
        structure,
        sidecars,
    )
    preflight = compile_clinicaltrials_gov_endpoint_estimand_preflight(
        ClinicalTrialsGovEndpointEstimandPreflightSpec(
            packet_id="synthetic-acquisition-preflight:v1",
            candidate_packet_sha256=candidate.fingerprint,
            presence_report_sha256=presence.fingerprint,
            sidecar_bindings=sidecar_bindings,
            max_pair_count=10,
        ),
        candidate,
        presence,
        sidecars,
    )
    spec = ClinicalTrialsGovEstimandEvidenceAcquisitionSpec(
        packet_id="synthetic-estimand-evidence-acquisition:v1",
        candidate_packet_sha256=candidate.fingerprint,
        preflight_packet_sha256=preflight.fingerprint,
        document_bindings=tuple(document_bindings),
        max_document_bytes=1_000_000,
        max_candidate_pages_per_dimension=3,
    )
    return spec, candidate, preflight, registry_sources, document_sources


class ClinicalTrialsGovEstimandEvidenceAcquisitionTests(unittest.TestCase):
    def test_acquires_bounded_cues_without_semantic_approval(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline()
        packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec, candidate, preflight, registry, documents
        )
        self.assertEqual(preflight.pair_preflights[0].review_route, READY_FOR_ENDPOINT_ESTIMAND_REVIEW)
        self.assertEqual(packet.review_ready_pair_count, 1)
        self.assertEqual(packet.preflight_blocked_pair_count, 0)
        self.assertEqual(packet.unique_review_ready_endpoint_count, 2)
        self.assertEqual(packet.evidence_record_count, 10)
        self.assertEqual(packet.source_document_count, 2)
        self.assertTrue(all(item.cue_state == CANDIDATE_PAGES_FOUND for item in packet.evidence_cues))
        self.assertTrue(all(len(item.candidate_pages) <= 3 for item in packet.evidence_cues))
        self.assertEqual(packet.pair_acquisitions[0].acquisition_state, EVIDENCE_CUES_ACQUIRED)
        self.assertFalse(packet.source_payload_included)
        self.assertFalse(packet.source_excerpt_included)
        self.assertFalse(packet.semantic_sufficiency_assessed)
        self.assertFalse(packet.estimand_equivalence_approved)
        self.assertEqual(
            validate_clinicaltrials_gov_estimand_evidence_acquisition(
                spec, candidate, preflight, registry, documents, packet
            ),
            (),
        )

    def test_preflight_blocker_is_preserved_without_endpoint_cues(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline(ready=False)
        packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec, candidate, preflight, registry, documents
        )
        self.assertEqual(packet.review_ready_pair_count, 0)
        self.assertEqual(packet.preflight_blocked_pair_count, 1)
        self.assertEqual(packet.unique_review_ready_endpoint_count, 0)
        self.assertEqual(packet.evidence_record_count, 0)
        self.assertEqual(packet.pair_acquisitions[0].acquisition_state, PREFLIGHT_BLOCKED)
        self.assertEqual(packet.pair_acquisitions[0].evidence_ids, ())
        self.assertTrue(packet.pair_acquisitions[0].blocker_codes)

    def test_registry_inventory_and_document_bytes_are_fail_closed(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline()
        tampered_registry = dict(registry)
        nct_id = sorted(tampered_registry)[0]
        tampered_registry[nct_id] += b" "
        with self.assertRaises(ClinicalTrialsGovEstimandEvidenceAcquisitionError):
            compile_clinicaltrials_gov_estimand_evidence_acquisition(
                spec, candidate, preflight, tampered_registry, documents
            )
        tampered_documents = dict(documents)
        document_id = sorted(tampered_documents)[0]
        tampered_documents[document_id] += b" "
        with self.assertRaises(ClinicalTrialsGovEstimandEvidenceAcquisitionError):
            compile_clinicaltrials_gov_estimand_evidence_acquisition(
                spec, candidate, preflight, registry, tampered_documents
            )

    def test_strict_spec_and_packet_readers_round_trip(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline()
        packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec, candidate, preflight, registry, documents
        )
        self.assertEqual(
            clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict(
                clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict(spec)
            ),
            spec,
        )
        envelope = clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope(packet)
        self.assertEqual(
            clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(envelope),
            packet,
        )
        tampered = copy.deepcopy(envelope)
        tampered["packet"]["source_payload_included"] = True
        with self.assertRaises(ValueError):
            clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(tampered)

    def test_json_schemas_accept_synthetic_artifacts(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline()
        packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec, candidate, preflight, registry, documents
        )
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator(
            spec_schema, format_checker=FormatChecker()
        ).validate(clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict(spec))
        Draft202012Validator(
            spec_schema, format_checker=FormatChecker()
        ).validate(json.loads(SPEC_EXAMPLE.read_text(encoding="utf-8")))
        Draft202012Validator(
            packet_schema, format_checker=FormatChecker()
        ).validate(
            clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope(packet)
        )

    def test_public_artifacts_are_exact_payload_free_and_schema_valid(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        for expected in PUBLIC_ARTIFACTS:
            spec_bytes = expected["spec"].read_bytes()
            packet_bytes = expected["packet"].read_bytes()
            self.assertEqual(hashlib.sha256(spec_bytes).hexdigest(), expected["spec_file_sha256"])
            self.assertEqual(hashlib.sha256(packet_bytes).hexdigest(), expected["packet_file_sha256"])
            spec_value = json.loads(spec_bytes)
            packet_value = json.loads(packet_bytes)
            Draft202012Validator(spec_schema, format_checker=FormatChecker()).validate(spec_value)
            Draft202012Validator(packet_schema, format_checker=FormatChecker()).validate(packet_value)
            spec = clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict(spec_value)
            packet = clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(packet_value)
            preflight = clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(
                json.loads(expected["preflight"].read_text(encoding="utf-8"))
            )
            self.assertEqual(spec.preflight_packet_sha256, preflight.fingerprint)
            self.assertEqual(spec.candidate_packet_sha256, preflight.candidate_packet_sha256)
            self.assertEqual(packet.preflight_packet_sha256, preflight.fingerprint)
            self.assertEqual(packet.fingerprint, expected["integrity_sha256"])
            self.assertEqual(packet.source_document_count, expected["documents"])
            self.assertEqual(packet.source_document_page_count, expected["pages"])
            self.assertEqual(packet.pair_count, expected["pairs"])
            self.assertEqual(packet.review_ready_pair_count, expected["ready"])
            self.assertEqual(packet.preflight_blocked_pair_count, expected["blocked"])
            self.assertEqual(packet.unique_review_ready_endpoint_count, expected["endpoints"])
            self.assertEqual(packet.evidence_record_count, expected["evidence"])
            self.assertEqual(packet.candidate_page_cue_count, expected["page_cues"])
            serialized = packet_bytes.decode("utf-8")
            self.assertNotIn('"source_excerpt":', serialized)
            self.assertNotIn('"page_text":', serialized)

    def test_validation_detects_packet_mismatch(self) -> None:
        spec, candidate, preflight, registry, documents = _pipeline()
        packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec, candidate, preflight, registry, documents
        )
        changed = replace(packet, packet_id="different-packet-id")
        self.assertEqual(
            validate_clinicaltrials_gov_estimand_evidence_acquisition(
                spec, candidate, preflight, registry, documents, changed
            ),
            ("clinicaltrials_gov_estimand_evidence_acquisition_packet_mismatch",),
        )

    def test_exact_source_audit_cli_writes_valid_artifacts(self) -> None:
        _, _, _, registry, documents = _pipeline()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            command = [
                sys.executable,
                str(AUDIT_SCRIPT),
                "--cohort-id",
                "synthetic-cli",
                "--registry-version",
                "2025-01-01",
                "--retrieved-at",
                "2025-01-02T00:00:00+00:00",
                "--max-endpoint-candidate-count",
                "10",
                "--max-pair-count",
                "10",
                "--max-structural-array-record-count",
                "1000",
            ]
            for nct_id, payload in sorted(registry.items()):
                path = temporary / f"{nct_id}.json"
                path.write_bytes(payload)
                command.extend(("--registry-study", f"{nct_id}={path}"))
                command.extend(
                    ("--source-sha256", f"{nct_id}={hashlib.sha256(payload).hexdigest()}")
                )
            for document_id, payload in sorted(documents.items()):
                path = temporary / document_id.replace(":", "-")
                path.write_bytes(payload)
                command.extend(("--document", f"{document_id}={path}"))
                command.extend(
                    (
                        "--document-sha256",
                        f"{document_id}={hashlib.sha256(payload).hexdigest()}",
                    )
                )
            spec_path = temporary / "spec.json"
            packet_path = temporary / "packet.json"
            command.extend(
                (
                    "--output-spec",
                    str(spec_path),
                    "--output-packet",
                    str(packet_path),
                )
            )
            result = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict(
                json.loads(spec_path.read_text(encoding="utf-8"))
            )
            packet = clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(
                json.loads(packet_path.read_text(encoding="utf-8"))
            )
            self.assertEqual(packet.review_ready_pair_count, 1)
            self.assertEqual(packet.evidence_record_count, 10)


if __name__ == "__main__":
    unittest.main()
