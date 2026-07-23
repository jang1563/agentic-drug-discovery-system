from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery import (
    SourceBundle,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    extract_chembl_activity_ingestion_job,
    normalize_chembl_activity_ingestion_job,
    write_source_bundle,
)
from agentic_drug_discovery.ingestion_cli import main as ingestion_main


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = datetime(2026, 7, 15, 1, tzinfo=timezone.utc)
ASSAY_DESCRIPTION = (
    "Synthetic channel inhibition in human cells assessed by a synthetic "
    "stimulated ion-efflux readout"
)
FUNCTIONAL_ANCHOR = "synthetic stimulated ion-efflux readout"


def chembl_job() -> dict:
    return json.loads(
        (ROOT / "rl_env/specs/chembl_activity_ingestion_job.example.json").read_text(
            encoding="utf-8"
        )
    )


def source_objects() -> dict[str, dict]:
    return {
        "status": {
            "chembl_db_version": "ChEMBL_37",
            "chembl_release_date": "2026-05-01",
            "status": "UP",
        },
        "activity": {
            "activity_id": 9000001,
            "assay_chembl_id": "CHEMBL9000011",
            "document_chembl_id": "CHEMBL9000012",
            "molecule_chembl_id": "CHEMBL9000013",
            "target_chembl_id": "CHEMBL9000014",
            "standard_flag": 1,
            "standard_relation": "=",
            "standard_value": "12.0",
            "standard_units": "nM",
            "standard_type": "IC50",
            "standard_upper_value": None,
            "standard_text_value": None,
            "pchembl_value": "7.92",
            "data_validity_comment": None,
            "potential_duplicate": 0,
            "assay_description": ASSAY_DESCRIPTION,
            "assay_type": "B",
            "bao_endpoint": "BAO_0000190",
            "bao_format": "BAO_0000357",
            "target_organism": "Homo sapiens",
            "molecule_pref_name": "SYNTHETIC-CANDIDATE",
            "parent_molecule_chembl_id": "CHEMBL9000013",
            "record_id": 9900001,
        },
        "assay": {
            "assay_chembl_id": "CHEMBL9000011",
            "description": ASSAY_DESCRIPTION,
            "assay_type": "B",
            "assay_type_description": "Binding",
            "confidence_score": 9,
            "confidence_description": "Direct single protein target assigned",
            "relationship_type": "D",
            "document_chembl_id": "CHEMBL9000012",
            "target_chembl_id": "CHEMBL9000014",
            "bao_format": "BAO_0000357",
        },
        "document": {
            "document_chembl_id": "CHEMBL9000012",
            "doc_type": "PUBLICATION",
            "title": ("Synthetic inhibitors for a disease-model contract fixture."),
            "year": 2008,
            "pubmed_id": 99999991,
            "doi": "10.1000/synthetic.chembl.activity",
        },
        "molecule": {
            "molecule_chembl_id": "CHEMBL9000013",
            "pref_name": "SYNTHETIC-CANDIDATE",
            "molecule_synonyms": [
                {
                    "molecule_synonym": "SYNTH-CODE-1",
                    "syn_type": "RESEARCH_CODE",
                    "synonyms": "SYNTH-CODE-1",
                },
                {
                    "molecule_synonym": "SYNTH-CODE-2",
                    "syn_type": "RESEARCH_CODE",
                    "synonyms": "SYNTH-CODE-2",
                },
                {
                    "molecule_synonym": "Synthetic Candidate",
                    "syn_type": "INN",
                    "synonyms": "SYNTHETIC-CANDIDATE",
                },
            ],
        },
        "target": {
            "target_chembl_id": "CHEMBL9000014",
            "pref_name": "Synthetic ion channel protein 1",
            "target_type": "SINGLE PROTEIN",
            "organism": "Homo sapiens",
            "tax_id": 9606,
            "target_components": [
                {
                    "accession": "P00001",
                    "component_type": "PROTEIN",
                    "target_component_synonyms": [
                        {
                            "component_synonym": "SYN1",
                            "syn_type": "GENE_SYMBOL",
                        },
                        {
                            "component_synonym": "Synthetic channel",
                            "syn_type": "UNIPROT",
                        },
                    ],
                }
            ],
        },
    }


def resource_identifier(resource: str) -> str | None:
    return {
        "status": None,
        "activity": "9000001",
        "assay": "CHEMBL9000011",
        "document": "CHEMBL9000012",
        "molecule": "CHEMBL9000013",
        "target": "CHEMBL9000014",
    }[resource]


def source_bundle(
    resource: str,
    source: dict | None = None,
    *,
    payload: bytes | None = None,
    locator: str | None = None,
    source_version: str | None = None,
    media_type: str = "application/json",
) -> SourceBundle:
    identifier = resource_identifier(resource)
    suffix = "status.json" if identifier is None else f"{resource}/{identifier}.json"
    version_identifier = "status" if identifier is None else f"{resource}-{identifier}"
    return capture_source_bytes(
        payload
        or json.dumps(source or source_objects()[resource], sort_keys=True).encode(),
        receipt_id=chembl_job()["source_receipt_ids"][resource],
        source_id=(
            "chembl-status" if identifier is None else f"chembl-{resource}-{identifier}"
        ),
        source_version=(
            source_version or f"chembl-37-{version_identifier}-release-2026-05-01"
        ),
        locator=locator or f"https://www.ebi.ac.uk/chembl/api/data/{suffix}",
        retrieved_at=RETRIEVED_AT,
        media_type=media_type,
        capture_method="local_file",
    )


def source_bundles(objects: dict[str, dict] | None = None) -> dict[str, SourceBundle]:
    values = objects or source_objects()
    return {
        resource: source_bundle(resource, source) for resource, source in values.items()
    }


class ChemblActivityIngestionTests(unittest.TestCase):
    def test_machine_example_round_trips_and_validates_against_schema(self) -> None:
        job = chembl_job()
        schema = json.loads(
            (ROOT / "rl_env/specs/chembl_activity_ingestion_job.schema.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(normalize_chembl_activity_ingestion_job(job), job)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(job)
        with self.assertRaisesRegex(ValueError, "exactly"):
            normalize_chembl_activity_ingestion_job({**job, "undeclared": True})

    def test_extractor_cross_checks_resources_and_strips_evidence_text(self) -> None:
        bundles = source_bundles()
        extracted = extract_chembl_activity_ingestion_job(chembl_job(), bundles)
        record = extracted["records"][0]
        metadata = record["metadata"]

        self.assertEqual(extracted["schema_version"], "adds.pinned-ingestion-job.v1")
        self.assertEqual(metadata["provider_id"], "chembl")
        self.assertEqual(metadata["chembl_database_version"], "ChEMBL_37")
        self.assertEqual(metadata["activity_id"], 9000001)
        self.assertEqual(metadata["source_assay_type"], "B")
        self.assertEqual(metadata["source_assay_type_description"], "Binding")
        self.assertEqual(
            metadata["source_lineage_ids"],
            [
                "chembl-document:CHEMBL9000012",
                "pubmed:99999991",
                "doi:10.1000/synthetic.chembl.activity",
            ],
        )
        self.assertEqual(
            metadata["linked_source_receipts"]["target"]["content_hash"],
            bundles["target"].receipt.content_hash,
        )
        self.assertEqual(
            metadata["assay_description_sha256"],
            hashlib.sha256(ASSAY_DESCRIPTION.encode()).hexdigest(),
        )
        serialized = json.dumps(extracted)
        self.assertNotIn(ASSAY_DESCRIPTION, serialized)
        self.assertNotIn(FUNCTIONAL_ANCHOR, serialized)
        self.assertNotIn('"evidence"', serialized)

        manifest, review = compile_pinned_evidence_manifest(
            extracted,
            {
                bundles["activity"].receipt.receipt_id: bundles["activity"],
            },
        )
        self.assertEqual(review["receipt_count"], 1)
        self.assertEqual(
            manifest["records"][0]["source"]["content_hash"],
            bundles["activity"].receipt.content_hash,
        )

    def test_cross_resource_identity_and_typed_endpoint_mismatches_fail(self) -> None:
        cases = {
            "linked-target": (
                lambda values: values["activity"].update(
                    target_chembl_id="CHEMBL999999"
                ),
                "linked resource identity mismatch",
            ),
            "endpoint": (
                lambda values: values["activity"].update(standard_value="13.0"),
                "typed endpoint",
            ),
            "source-assay-type": (
                lambda values: values["assay"].update(assay_type="F"),
                "source assay classification",
            ),
            "target-symbol": (
                lambda values: values["target"]["target_components"][0][
                    "target_component_synonyms"
                ][0].update(component_synonym="OTHER"),
                "gene-symbol identity",
            ),
            "release": (
                lambda values: values["status"].update(chembl_db_version="ChEMBL_36"),
                "active release",
            ),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(label=label):
                values = copy.deepcopy(source_objects())
                mutate(values)
                with self.assertRaisesRegex(ValueError, message):
                    extract_chembl_activity_ingestion_job(
                        chembl_job(), source_bundles(values)
                    )

    def test_receipt_and_json_structure_mismatches_fail_closed(self) -> None:
        bundles = source_bundles()
        bundles["activity"] = source_bundle(
            "activity",
            locator=(
                "https://www.ebi.ac.uk/chembl/api/data/activity/9000001.json?"
                "format=json"
            ),
        )
        with self.assertRaisesRegex(ValueError, "exact public API URL"):
            extract_chembl_activity_ingestion_job(chembl_job(), bundles)

        bundles = source_bundles()
        bundles["assay"] = source_bundle(
            "assay",
            source_version=("chembl-37-assay-CHEMBL9000011-release-2026-05-02"),
        )
        with self.assertRaisesRegex(ValueError, "source_version"):
            extract_chembl_activity_ingestion_job(chembl_job(), bundles)

        bundles = source_bundles()
        bundles["status"] = source_bundle(
            "status",
            payload=(
                b'{"chembl_db_version":"ChEMBL_37",'
                b'"chembl_db_version":"ChEMBL_36",'
                b'"chembl_release_date":"2026-05-01","status":"UP"}'
            ),
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            extract_chembl_activity_ingestion_job(chembl_job(), bundles)

    def test_cli_reports_all_six_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-chembl-cli-") as temp_dir:
            root = Path(temp_dir)
            job_path = root / "job.json"
            output_path = root / "extracted.json"
            job_path.write_text(json.dumps(chembl_job()), encoding="utf-8")
            args = [
                "extract-chembl-activity",
                "--job",
                str(job_path),
            ]
            bundles = source_bundles()
            for resource, bundle in bundles.items():
                path = write_source_bundle(root / resource, bundle)
                args.extend(["--bundle", str(path)])
            args.extend(["--output", str(output_path)])
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = ingestion_main(args)

            report = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["provider_id"], "chembl")
            self.assertEqual(
                set(report["source_content_hashes"]), set(source_objects())
            )
            self.assertEqual(
                report["output_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
