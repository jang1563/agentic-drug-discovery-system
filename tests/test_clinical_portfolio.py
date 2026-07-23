from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from agentic_drug_discovery import (
    capture_source_bytes,
    clinical_endpoint_mapping_spec_from_dict,
    clinical_endpoint_mapping_spec_to_dict,
    compile_pinned_evidence_manifest,
    extract_clinicaltrials_gov_portfolio_job,
    normalize_clinicaltrials_gov_portfolio_job,
    write_source_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
TRIAL_JOB = ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
TRIAL_SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
MAPPING_SCHEMA = ROOT / "rl_env/specs/clinical_endpoint_mapping.schema.json"
MAPPING_EXAMPLE = ROOT / "rl_env/specs/clinical_endpoint_mapping.example.json"
PORTFOLIO_SCHEMA = (
    ROOT / "rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json"
)
PORTFOLIO_EXAMPLE = (
    ROOT / "rl_env/specs/clinicaltrials_gov_portfolio_job.example.json"
)


def _trial_artifacts(trial_id: str, suffix: str):
    original_trial_id = "NCT00000001"
    job = json.loads(
        TRIAL_JOB.read_text(encoding="utf-8").replace(original_trial_id, trial_id)
    )
    source = TRIAL_SOURCE.read_text(encoding="utf-8").replace(
        original_trial_id, trial_id
    ).encode("utf-8")
    if suffix:
        job["job_id"] = f"clinicaltrials-gov-test-design-{suffix}"
        job["source_receipt_id"] = f"ctgov-test-trial-{suffix}"
    receipt_id = job["source_receipt_id"]
    bundle = capture_source_bytes(
        source,
        receipt_id=receipt_id,
        source_id=f"clinicaltrials-gov-{trial_id}",
        source_version=f"clinicaltrials-gov-{trial_id}-version-2025-01-01",
        locator=f"https://clinicaltrials.gov/api/v2/studies/{trial_id}",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    return job, bundle


def _portfolio() -> dict:
    return json.loads(PORTFOLIO_EXAMPLE.read_text(encoding="utf-8"))


class ClinicalPortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first_job, self.first_bundle = _trial_artifacts("NCT00000001", "")
        self.second_job, self.second_bundle = _trial_artifacts("NCT00000002", "2")
        self.jobs = [self.first_job, self.second_job]
        self.bundles = {
            self.first_bundle.receipt.receipt_id: self.first_bundle,
            self.second_bundle.receipt.receipt_id: self.second_bundle,
        }

    def test_public_mapping_and_portfolio_contracts_validate_and_round_trip(self) -> None:
        mapping_schema = json.loads(MAPPING_SCHEMA.read_text(encoding="utf-8"))
        mapping_example = json.loads(MAPPING_EXAMPLE.read_text(encoding="utf-8"))
        portfolio_schema = json.loads(PORTFOLIO_SCHEMA.read_text(encoding="utf-8"))
        portfolio_example = _portfolio()
        Draft202012Validator.check_schema(mapping_schema)
        Draft202012Validator(mapping_schema).validate(mapping_example)
        parsed_mapping = clinical_endpoint_mapping_spec_from_dict(mapping_example)
        self.assertEqual(
            clinical_endpoint_mapping_spec_to_dict(parsed_mapping),
            mapping_example,
        )
        Draft202012Validator.check_schema(portfolio_schema)
        registry = Registry().with_resource(
            mapping_schema["$id"],
            Resource.from_contents(mapping_schema),
        )
        Draft202012Validator(portfolio_schema, registry=registry).validate(
            portfolio_example
        )
        self.assertEqual(
            normalize_clinicaltrials_gov_portfolio_job(portfolio_example),
            portfolio_example,
        )

    def test_atomic_extraction_emits_two_payload_free_source_disjoint_records(self) -> None:
        extracted = extract_clinicaltrials_gov_portfolio_job(
            _portfolio(),
            self.jobs,
            self.bundles,
        )
        self.assertEqual(len(extracted["records"]), 2)
        for index, record in enumerate(extracted["records"]):
            portfolio = record["metadata"]["clinical_portfolio"]
            self.assertEqual(
                portfolio["portfolio_id"],
                "CHEMBL_TEST-MONDO_TEST-ctgov-portfolio-v1",
            )
            self.assertEqual(
                portfolio["endpoint_mapping_id"],
                "CHEMBL_TEST:MONDO_TEST:pfs-map:v1",
            )
            self.assertEqual(portfolio["trial_index"], index)
            self.assertTrue(portfolio["source_disjoint_by_content_hash"])
            self.assertFalse(portfolio["automatic_endpoint_mapping_performed"])
        encoded = json.dumps(extracted, sort_keys=True).casefold()
        for forbidden in (
            "protocolsection",
            "resultssection",
            "raw_payload",
            "eligibilitycriteria",
        ):
            self.assertNotIn(forbidden, encoded)
        manifest, review = compile_pinned_evidence_manifest(
            extracted,
            self.bundles,
        )
        self.assertEqual(len(manifest["records"]), 2)
        self.assertEqual(review["record_count"], 2)
        self.assertEqual(len({item["source"]["content_hash"] for item in manifest["records"]}), 2)

    def test_job_bundle_and_mapping_mismatches_fail_before_any_output(self) -> None:
        missing_job = self.jobs[:1]
        with self.assertRaisesRegex(ValueError, "trial job set mismatch"):
            extract_clinicaltrials_gov_portfolio_job(
                _portfolio(),
                missing_job,
                self.bundles,
            )

        rebound = _portfolio()
        rebound["trials"][1]["endpoint_id"] = "NCT00000002:endpoint:rebound"
        with self.assertRaisesRegex(ValueError, "exactly match"):
            extract_clinicaltrials_gov_portfolio_job(
                rebound,
                self.jobs,
                self.bundles,
            )

        duplicate_hash_bundle = capture_source_bytes(
            self.first_bundle.payload,
            receipt_id=self.second_bundle.receipt.receipt_id,
            source_id=self.second_bundle.receipt.source_id,
            source_version=self.second_bundle.receipt.source_version,
            locator=self.second_bundle.receipt.locator,
            retrieved_at=self.second_bundle.receipt.retrieved_at,
            media_type=self.second_bundle.receipt.media_type,
            capture_method=self.second_bundle.receipt.capture_method,
            http_status=self.second_bundle.receipt.http_status,
        )
        with self.assertRaisesRegex(ValueError, "content-hash disjoint"):
            extract_clinicaltrials_gov_portfolio_job(
                _portfolio(),
                self.jobs,
                {
                    self.first_bundle.receipt.receipt_id: self.first_bundle,
                    duplicate_hash_bundle.receipt.receipt_id: duplicate_hash_bundle,
                },
            )

    def test_mapping_rejects_unapproved_status_and_measurement_metadata(self) -> None:
        unapproved = json.loads(MAPPING_EXAMPLE.read_text(encoding="utf-8"))
        unapproved["review"]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "must be approved"):
            clinical_endpoint_mapping_spec_from_dict(unapproved)

        measurement = json.loads(MAPPING_EXAMPLE.read_text(encoding="utf-8"))
        measurement["metadata"]["effect_estimate"] = 0.7
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            clinical_endpoint_mapping_spec_from_dict(measurement)

    def test_mapping_approval_must_follow_every_source_capture(self) -> None:
        backdated = _portfolio()
        backdated["endpoint_mapping"]["review"]["reviewed_at"] = (
            self.first_bundle.receipt.retrieved_at - timedelta(seconds=1)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "predates source bundle retrieval"):
            extract_clinicaltrials_gov_portfolio_job(
                backdated,
                self.jobs,
                self.bundles,
            )

    def test_cli_preflight_is_atomic_on_reference_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-clinical-portfolio-") as tmp:
            root = Path(tmp)
            first_bundle_path = write_source_bundle(
                root / "bundle-one", self.first_bundle
            )
            second_bundle_path = write_source_bundle(
                root / "bundle-two", self.second_bundle
            )
            first_job_path = root / "trial-one.json"
            second_job_path = root / "trial-two.json"
            portfolio_path = root / "portfolio.json"
            output_path = root / "extracted.json"
            first_job_path.write_text(json.dumps(self.first_job), encoding="utf-8")
            second_job_path.write_text(json.dumps(self.second_job), encoding="utf-8")
            bad_portfolio = copy.deepcopy(_portfolio())
            bad_portfolio["trials"][1]["safety_id"] = (
                "NCT00000002:safety:unreviewed"
            )
            portfolio_path.write_text(json.dumps(bad_portfolio), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "extract-clinicaltrials-gov-portfolio",
                    "--job",
                    str(portfolio_path),
                    "--trial-job",
                    str(first_job_path),
                    "--trial-job",
                    str(second_job_path),
                    "--bundle",
                    str(first_bundle_path),
                    "--bundle",
                    str(second_bundle_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
