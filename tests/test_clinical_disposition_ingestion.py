from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    Decision,
    ProgramStatus,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    extract_clinical_disposition_ingestion_job,
    normalize_clinical_disposition_ingestion_job,
    write_source_bundle,
)
from tests.test_clinical_trial_disposition import run_manifest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = (
    ROOT / "rl_env/specs/clinical_trial_disposition_ingestion_job.example.json"
)
SCHEMA = ROOT / "rl_env/specs/clinical_trial_disposition_ingestion_job.schema.json"
CTGOV_SOURCE = ROOT / "tests/fixtures/clinical_disposition_ctgov.synthetic.json"
PUBMED_SOURCE = ROOT / "tests/fixtures/clinical_disposition_pubmed.synthetic.xml"
RETRIEVED_AT = datetime(2025, 1, 2, tzinfo=timezone.utc)


def review_job() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def registry_bundle(*, payload: bytes | None = None):
    return capture_source_bytes(
        payload or CTGOV_SOURCE.read_bytes(),
        receipt_id="synthetic-clinical-disposition-registry",
        source_id="clinicaltrials-gov-NCT00000002",
        source_version="clinicaltrials-gov-NCT00000002-version-2025-01-01",
        locator="https://clinicaltrials.gov/api/v2/studies/NCT00000002",
        retrieved_at=RETRIEVED_AT,
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )


def publication_bundle(*, payload: bytes | None = None):
    return capture_source_bytes(
        payload or PUBMED_SOURCE.read_bytes(),
        receipt_id="synthetic-clinical-disposition-publication",
        source_id="ncbi-pubmed-99999991",
        source_version="pmid-99999991-pubmed-xml-2025-01-02",
        locator=(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
            "efetch.fcgi?db=pubmed&id=99999991&retmode=xml"
        ),
        retrieved_at=RETRIEVED_AT,
        media_type="text/xml",
        capture_method="https",
        http_status=200,
    )


def extracted_job() -> tuple[dict, dict]:
    bundles = {
        "registry": registry_bundle(),
        "publication": publication_bundle(),
    }
    return extract_clinical_disposition_ingestion_job(review_job(), bundles), bundles


class ClinicalDispositionIngestionTests(unittest.TestCase):
    def test_example_round_trips_and_validates_against_schema(self) -> None:
        job = review_job()
        self.assertEqual(normalize_clinical_disposition_ingestion_job(job), job)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(job)

    def test_extractor_emits_two_payload_free_shared_lineage_records(self) -> None:
        extracted, _ = extracted_job()

        self.assertEqual(
            [item["predicate"] for item in extracted["records"]],
            [
                "clinical_trial_terminated_for_lack_of_efficacy",
                "clinical_primary_endpoint_not_met",
            ],
        )
        shared = [
            item["metadata"]["shared_trial_lineage_id"]
            for item in extracted["records"]
        ]
        self.assertEqual(shared, ["sponsor-protocol:TEST-P3-FAIL"] * 2)
        publication = extracted["records"][1]["metadata"]
        self.assertFalse(publication["primary_endpoint_met"])
        self.assertEqual(publication["candidate_rate"], 0.4)
        self.assertEqual(publication["comparator_rate"], 0.3)
        self.assertEqual(len(publication["termination_excerpt_sha256"]), 64)
        encoded = json.dumps(extracted, sort_keys=True)
        self.assertNotIn("data monitoring committee", encoded.casefold())
        self.assertNotIn("no significant improvement", encoded.casefold())
        self.assertNotIn("protocolSection", encoded)
        self.assertNotIn("PubmedArticle", encoded)

    def test_compiled_provider_pair_drives_typed_kill(self) -> None:
        extracted, bundles = extracted_job()
        manifest, review = compile_pinned_evidence_manifest(
            extracted,
            {
                bundle.receipt.receipt_id: bundle
                for bundle in bundles.values()
            },
        )
        run = run_manifest(manifest, program_id="provider-negative-clinical")

        self.assertEqual(review["independent_source_count"], 2)
        self.assertEqual(run.accepted_packets[0].decision, Decision.KILL)
        self.assertEqual(run.final_state.status, ProgramStatus.TERMINATED)
        self.assertEqual(run.final_state.trials[0].attributes["independent_trial_count"], 1)

    def test_trial_protocol_candidate_and_endpoint_mismatches_fail_closed(self) -> None:
        wrong_protocol = json.loads(CTGOV_SOURCE.read_text(encoding="utf-8"))
        wrong_protocol["protocolSection"]["identificationModule"]["orgStudyIdInfo"][
            "id"
        ] = "OTHER-PROTOCOL"
        wrong_publication = PUBMED_SOURCE.read_text(encoding="utf-8").replace(
            "TEST-P3-FAIL Study Investigators",
            "OTHER-PROTOCOL Study Investigators",
        )
        wrong_endpoint = review_job()
        wrong_endpoint["publication_review"]["endpoint_name"] = "unrelated biomarker"

        cases = (
            (
                "registry-protocol",
                review_job(),
                registry_bundle(
                    payload=(json.dumps(wrong_protocol, sort_keys=True) + "\n").encode()
                ),
                publication_bundle(),
            ),
            (
                "publication-protocol",
                review_job(),
                registry_bundle(),
                publication_bundle(payload=wrong_publication.encode()),
            ),
            (
                "endpoint-mapping",
                wrong_endpoint,
                registry_bundle(),
                publication_bundle(),
            ),
        )
        for label, job, registry, publication in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                extract_clinical_disposition_ingestion_job(
                    job,
                    {"registry": registry, "publication": publication},
                )

    def test_reviewer_excerpts_do_not_enter_compiled_manifest(self) -> None:
        extracted, bundles = extracted_job()
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {
                bundle.receipt.receipt_id: bundle
                for bundle in bundles.values()
            },
        )
        encoded = json.dumps(manifest, sort_keys=True).casefold()
        for excerpt in (
            review_job()["publication_review"]["termination_excerpt"],
            review_job()["publication_review"]["endpoint_excerpt"],
        ):
            self.assertNotIn(excerpt.casefold(), encoded)

    def test_cli_reports_both_hashes_and_single_trial_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry_path = root / "registry"
            publication_path = root / "publication"
            output = root / "extracted.json"
            job_path = root / "job.json"
            job_path.write_text(json.dumps(review_job()), encoding="utf-8")
            registry = registry_bundle()
            publication = publication_bundle()
            write_source_bundle(registry_path, registry)
            write_source_bundle(publication_path, publication)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "extract-clinical-trial-disposition",
                    "--job",
                    str(job_path),
                    "--registry-bundle",
                    str(registry_path),
                    "--publication-bundle",
                    str(publication_path),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["record_count"], 2)
            self.assertEqual(report["independent_trial_count"], 1)
            self.assertTrue(report["shared_trial_lineage"])
            self.assertEqual(
                report["source_content_hashes"]["registry"],
                registry.receipt.content_hash,
            )
            self.assertEqual(
                report["source_content_hashes"]["publication"],
                publication.receipt.content_hash,
            )
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
