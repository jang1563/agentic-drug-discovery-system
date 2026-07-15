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
    extract_ncbi_pubmed_disease_model_ingestion_job,
    normalize_ncbi_pubmed_disease_model_ingestion_job,
    write_source_bundle,
)
from agentic_drug_discovery.ingestion_cli import main as ingestion_main


ROOT = Path(__file__).resolve().parents[1]
PMID = "99999992"
DOI = "10.1000/synthetic.disease-model"
TITLE = "Synthetic in-vivo disease-model contract fixture."
EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
    f"db=pubmed&id={PMID}&retmode=xml"
)
RETRIEVED_AT = datetime(2026, 7, 15, 1, 30, tzinfo=timezone.utc)
RESULT_EXCERPT = (
    "In a synthetic transgenic mouse disease model, treatment with SYNTH-CODE-1 "
    "(10 mg/kg orally, twice a day) for 21 days showed synthetic channel activity "
    "inhibition of 90% +/- 27%, P <.005"
)
CONCLUSION_EXCERPT = (
    "These synthetic data indicate that SYNTH-CODE-1 improves the synthetic "
    "disease-model endpoint."
)


def disease_model_job() -> dict:
    return json.loads(
        (
            ROOT / "rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.example.json"
        ).read_text(encoding="utf-8")
    )


def synthetic_pubmed_xml() -> bytes:
    abstract = (
        "Synthetic introduction text for a deterministic provider contract. "
        f"{RESULT_EXCERPT}, followed by additional synthetic outcomes. "
        f"{CONCLUSION_EXCERPT}"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2026//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_260101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">{PMID}</PMID>
      <Article PubModel="Print-Electronic">
        <Journal><JournalIssue><PubDate><Year>2003</Year></PubDate></JournalIssue></Journal>
        <ArticleTitle>{TITLE}</ArticleTitle>
        <ELocationID EIdType="doi" ValidYN="Y">{DOI}</ELocationID>
        <Abstract><AbstractText>{abstract.replace("<", "&lt;")}</AbstractText></Abstract>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
        </PublicationTypeList>
        <ArticleDate DateType="Electronic">
          <Year>2002</Year><Month>11</Month><Day>14</Day>
        </ArticleDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">{PMID}</ArticleId>
        <ArticleId IdType="doi">{DOI}</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".encode()


def pubmed_bundle(
    *,
    payload: bytes | None = None,
    locator: str = EFETCH_URL,
    source_version: str = "pmid-99999992-pubmed-xml-2026-07-15",
    media_type: str = "text/xml",
) -> SourceBundle:
    return capture_source_bytes(
        payload or synthetic_pubmed_xml(),
        receipt_id="synthetic-pubmed-disease-model-receipt",
        source_id="synthetic-ncbi-pubmed-disease-model",
        source_version=source_version,
        locator=locator,
        retrieved_at=RETRIEVED_AT,
        media_type=media_type,
        capture_method="local_file",
    )


class NcbiPubmedDiseaseModelIngestionTests(unittest.TestCase):
    def test_machine_example_round_trips_and_validates_against_schema(self) -> None:
        job = disease_model_job()
        schema = json.loads(
            (
                ROOT
                / "rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(normalize_ncbi_pubmed_disease_model_ingestion_job(job), job)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(job)
        with self.assertRaisesRegex(ValueError, "exactly"):
            normalize_ncbi_pubmed_disease_model_ingestion_job(
                {**job, "undeclared": True}
            )

    def test_extractor_binds_typed_in_vivo_result_and_removes_text(self) -> None:
        extracted = extract_ncbi_pubmed_disease_model_ingestion_job(
            disease_model_job(), pubmed_bundle()
        )
        record = extracted["records"][0]
        metadata = record["metadata"]

        self.assertEqual(extracted["schema_version"], "adds.pinned-ingestion-job.v1")
        self.assertEqual(metadata["provider_id"], "ncbi_pubmed")
        self.assertEqual(metadata["article_pmid"], PMID)
        self.assertIsNone(metadata["article_pmcid"])
        self.assertEqual(metadata["endpoint_value"], 90.0)
        self.assertEqual(metadata["endpoint_variation_value"], 27.0)
        self.assertEqual(metadata["dose_value"], 10.0)
        self.assertEqual(metadata["duration_value"], 21.0)
        self.assertEqual(
            metadata["source_lineage_ids"],
            ["pubmed:99999992", "doi:10.1000/synthetic.disease-model"],
        )
        self.assertEqual(
            metadata["result_excerpt_sha256"],
            hashlib.sha256(RESULT_EXCERPT.encode()).hexdigest(),
        )
        serialized = json.dumps(extracted)
        self.assertNotIn(RESULT_EXCERPT, serialized)
        self.assertNotIn(CONCLUSION_EXCERPT, serialized)
        self.assertNotIn('"evidence"', serialized)

    def test_article_identity_receipt_and_retraction_mismatches_fail_closed(
        self,
    ) -> None:
        job_cases = {
            "pmcid": (
                lambda job: job["article"].update(pmcid="PMC1234567"),
                "source PMCID",
            ),
            "doi": (
                lambda job: job["article"].update(doi="10.1000/different"),
                "source DOI",
            ),
            "title": (
                lambda job: job["article"].update(title="Different title."),
                "source title",
            ),
        }
        for label, (mutate, message) in job_cases.items():
            with self.subTest(label=label):
                job = copy.deepcopy(disease_model_job())
                mutate(job)
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_disease_model_ingestion_job(
                        job, pubmed_bundle()
                    )

        receipt_cases = {
            "locator": (
                pubmed_bundle(locator=f"{EFETCH_URL}&tool=unreviewed"),
                "exact NCBI PubMed EFetch",
            ),
            "version": (
                pubmed_bundle(source_version="pmid-99999992-pubmed-xml-2026-07-14"),
                "source_version",
            ),
            "media": (pubmed_bundle(media_type="text/html"), "declare XML"),
            "retraction": (
                pubmed_bundle(
                    payload=synthetic_pubmed_xml().replace(
                        b">Journal Article<", b">Retracted Publication<"
                    )
                ),
                "retracted publication",
            ),
        }
        for label, (bundle, message) in receipt_cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_disease_model_ingestion_job(
                        disease_model_job(), bundle
                    )

    def test_typed_dose_endpoint_and_anchor_mismatches_fail_closed(self) -> None:
        cases = {
            "dose": (
                lambda job: job["records"][0]["metadata"].update(dose_value=11.0),
                "dose does not match",
            ),
            "endpoint": (
                lambda job: job["records"][0]["metadata"].update(endpoint_value=91.0),
                "endpoint value does not match",
            ),
            "p-value": (
                lambda job: job["records"][0]["metadata"].update(p_value=0.01),
                "p-value does not match",
            ),
            "candidate": (
                lambda job: job["records"][0]["metadata"].update(
                    source_candidate_name="OTHER"
                ),
                "source candidate",
            ),
            "model-anchor": (
                lambda job: job["records"][0]["evidence"].update(
                    model_anchor="different model"
                ),
                "model_anchor must occur exactly once",
            ),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(label=label):
                job = copy.deepcopy(disease_model_job())
                mutate(job)
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_disease_model_ingestion_job(
                        job, pubmed_bundle()
                    )

    def test_cli_reports_source_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-pubmed-model-cli-") as temp_dir:
            root = Path(temp_dir)
            bundle = pubmed_bundle()
            bundle_path = write_source_bundle(root / "bundle", bundle)
            job_path = root / "job.json"
            output_path = root / "extracted.json"
            job_path.write_text(json.dumps(disease_model_job()), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = ingestion_main(
                    [
                        "extract-ncbi-pubmed-disease-model",
                        "--job",
                        str(job_path),
                        "--bundle",
                        str(bundle_path),
                        "--output",
                        str(output_path),
                    ]
                )

            report = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["evidence_type"], "disease_model_effect")
            self.assertEqual(report["source_content_hash"], bundle.receipt.content_hash)
            self.assertEqual(
                report["output_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
