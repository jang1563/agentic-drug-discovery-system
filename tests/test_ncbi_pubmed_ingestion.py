from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from adapters.execution_registry import register_existing_adapters
from adapters.pinned_evidence_adapter import PinnedEvidenceAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    Decision,
    EpisodeArm,
    EpisodeMatchKey,
    FailureCause,
    MatchedEpisodePair,
    ProgramState,
    PromotionContext,
    SourceBundle,
    Stage,
    StagePlan,
    ToolCallSpec,
    ToolRegistry,
    build_default_semantic_mapper_registry,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    extract_ncbi_pubmed_ingestion_job,
    normalize_ncbi_pubmed_ingestion_job,
    write_source_bundle,
)
from agentic_drug_discovery.ingestion_cli import main as ingestion_main


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = datetime(2026, 7, 15, 1, 30, tzinfo=timezone.utc)
REQUEST_AT = datetime(2026, 7, 15, 2, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
PMID = "12345678"
PMCID = "PMC1234567"
DOI = "10.1000/synthetic.scd.1"
TITLE = "Synthetic PubMed SCD Access Study."
CANONICAL_URL = f"https://pubmed.ncbi.nlm.nih.gov/{PMID}/"
EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    f"?db=pubmed&id={PMID}&retmode=xml"
)
RESULT_EXCERPT = (
    "The cohort included 3,635 individuals. Although <20% of the cohort had a "
    "hydroxyurea prescription filled, utilization increased after 2014."
)
CONTEXT_EXCERPT = (
    "Individuals with synthetic SCD (<=65 years and enrolled in Medicaid for >=6 "
    "total calendar months any year between 2011 and 2016) were identified in a "
    "multisource database maintained by the California Sickle Cell Data Collection "
    "Program."
)


def synthetic_pubmed_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">{PMID}</PMID>
      <Article PubModel="Electronic">
        <ArticleTitle>{TITLE}</ArticleTitle>
        <ELocationID EIdType="doi" ValidYN="Y">{DOI}</ELocationID>
        <Abstract>
          <AbstractText Label="PURPOSE">Synthetic purpose for contract testing.</AbstractText>
          <AbstractText Label="METHODS">{CONTEXT_EXCERPT.replace('<', '&lt;').replace('>', '&gt;')}</AbstractText>
          <AbstractText Label="RESULTS">{RESULT_EXCERPT.replace('<', '&lt;')}</AbstractText>
          <AbstractText Label="CONCLUSIONS">Synthetic conclusion.</AbstractText>
        </Abstract>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
        </PublicationTypeList>
        <ArticleDate DateType="Electronic">
          <Year>2020</Year><Month>03</Month><Day>08</Day>
        </ArticleDate>
      </Article>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="CommentIn">
          <RefSource>Synthetic Journal</RefSource><PMID Version="1">99999999</PMID>
        </CommentsCorrections>
      </CommentsCorrectionsList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">{PMID}</ArticleId>
        <ArticleId IdType="pmc">{PMCID}</ArticleId>
        <ArticleId IdType="doi">{DOI}</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".encode()


def pubmed_bundle(
    *,
    payload: bytes | None = None,
    receipt_id: str = "synthetic-pubmed-receipt",
    source_version: str = "pmid-12345678-pubmed-xml-2026-07-15",
    locator: str = EFETCH_URL,
    retrieved_at: datetime = RETRIEVED_AT,
    media_type: str = "text/xml",
) -> SourceBundle:
    return capture_source_bytes(
        payload or synthetic_pubmed_xml(),
        receipt_id=receipt_id,
        source_id="synthetic-ncbi-pubmed-source",
        source_version=source_version,
        locator=locator,
        retrieved_at=retrieved_at,
        media_type=media_type,
        capture_method="local_file",
    )


def pubmed_job() -> dict:
    return json.loads(
        (
            ROOT / "rl_env/specs/ncbi_pubmed_ingestion_job.example.json"
        ).read_text(encoding="utf-8")
    )


def burden_bundle() -> SourceBundle:
    return capture_source_bytes(
        b'{"synthetic_burden_count": 3635}',
        receipt_id="synthetic-matched-burden-receipt",
        source_id="synthetic-matched-burden-source",
        source_version="snapshot-2020-03-09",
        locator="https://example.invalid/synthetic-matched-burden",
        retrieved_at=datetime(2020, 3, 9, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="local_file",
    )


def burden_record(*, matched: bool) -> dict:
    population = (
        "California Medicaid enrollees meeting the synthetic SCD cohort criteria"
        if matched
        else "broader California SCD surveillance population"
    )
    context_id = (
        "california-medicaid-scd-2011-2016"
        if matched
        else "california-scd-surveillance-2018"
    )
    return {
        "source_receipt_id": "synthetic-matched-burden-receipt",
        "record_id": f"synthetic-{'matched' if matched else 'broad'}-burden",
        "predicate": "disease_burden_supported",
        "subject": "synthetic sickle cell disease context",
        "object_value": "A separately captured synthetic burden is present.",
        "observed_at": "2016-12-31" if matched else "2018-12-31",
        "available_at": "2020-03-09",
        "confidence": 0.8,
        "biological_context": {
            "disease_id": "MONDO_TEST",
            "evidence_context_id": context_id,
        },
        "metadata": {
            "measure_type": "cohort count",
            "measure_value": 3635,
            "measure_unit": "persons",
            "population": population,
            "geography": "California",
            "reference_period": "2011-2016" if matched else "2018",
        },
    }


def compile_manifest(*, matched: bool) -> tuple[dict, dict]:
    gap_source = pubmed_bundle()
    burden_source = burden_bundle()
    gap_job = extract_ncbi_pubmed_ingestion_job(pubmed_job(), gap_source)
    combined = {
        **gap_job,
        "records": [burden_record(matched=matched), *gap_job["records"]],
    }
    return compile_pinned_evidence_manifest(
        combined,
        {
            burden_source.receipt.receipt_id: burden_source,
            gap_source.receipt.receipt_id: gap_source,
        },
    )


def run_manifest(manifest: dict, *, program_id: str):
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        pinned_evidence=PinnedEvidenceAdapter(manifest),
    )
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: COMPLETED_AT,
    )
    state = ProgramState(
        program_id=program_id,
        disease="synthetic sickle cell disease context",
        therapeutic_hypothesis="Provider evidence must remain context-bound.",
        as_of_date=date(2026, 7, 15),
        current_stage=Stage.DISEASE_CONTEXT,
        budget=BudgetState(limit=1.0),
    )
    plan = StagePlan(
        plan_id=f"{program_id}-plan",
        stage=Stage.DISEASE_CONTEXT,
        calls=(
            ToolCallSpec(
                call_id="unmet-need",
                tool_id="pinned_evidence",
                operation="disease_unmet_need",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve burden and treatment gap from pinned sources.",
                arguments={"disease_id": "MONDO_TEST"},
                max_cost=0.05,
            ),
        ),
        max_steps=1,
        max_total_cost=0.05,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.TARGET_NOMINATION,
    )
    return runner.run_stage(
        run_id=f"{program_id}-run",
        state=state,
        stage_plan=plan,
        promotion_contexts={
            "unmet-need": PromotionContext(
                observed_at=date(2016, 12, 31),
                available_at=date(2020, 3, 9),
                subject="synthetic sickle cell disease context",
                object_value="MONDO_TEST",
                confidence=0.9,
            )
        },
    )


class NcbiPubmedIngestionTests(unittest.TestCase):
    def test_machine_example_round_trips_through_strict_normalizer(self) -> None:
        example = pubmed_job()

        self.assertEqual(normalize_ncbi_pubmed_ingestion_job(example), example)
        with self.assertRaisesRegex(ValueError, "exactly"):
            normalize_ncbi_pubmed_ingestion_job({**example, "undeclared": True})

    def test_extractor_binds_identity_sections_and_removes_source_text(self) -> None:
        extracted = extract_ncbi_pubmed_ingestion_job(pubmed_job(), pubmed_bundle())
        record = extracted["records"][0]
        metadata = record["metadata"]

        self.assertEqual(extracted["schema_version"], "adds.pinned-ingestion-job.v1")
        self.assertEqual(metadata["provider_id"], "ncbi_pubmed")
        self.assertEqual(metadata["article_pmid"], PMID)
        self.assertEqual(metadata["article_pmcid"], PMCID)
        self.assertEqual(metadata["article_doi"], DOI)
        self.assertEqual(metadata["result_location"], "RESULTS")
        self.assertEqual(metadata["context_location"], "METHODS")
        self.assertEqual(
            metadata["result_excerpt_sha256"],
            hashlib.sha256(RESULT_EXCERPT.encode()).hexdigest(),
        )
        serialized = json.dumps(extracted)
        self.assertNotIn(RESULT_EXCERPT, serialized)
        self.assertNotIn(CONTEXT_EXCERPT, serialized)
        self.assertNotIn('"evidence"', serialized)
        self.assertNotIn(
            pubmed_job()["records"][0]["evidence"]["population_anchor"],
            serialized,
        )

    def test_matched_context_advances_and_cross_population_context_defers(self) -> None:
        matched_manifest, matched_review = compile_manifest(matched=True)
        mismatched_manifest, mismatched_review = compile_manifest(matched=False)
        matched_run = run_manifest(matched_manifest, program_id="pubmed-matched")
        mismatched_run = run_manifest(
            mismatched_manifest,
            program_id="pubmed-context-mismatch",
        )

        self.assertEqual(matched_review["independent_source_count"], 2)
        self.assertEqual(mismatched_review["independent_source_count"], 2)
        self.assertEqual(matched_run.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(mismatched_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            mismatched_run.promotions[0].code,
            "pinned_unmet_need_context_mismatch",
        )
        self.assertEqual(
            mismatched_run.promotions[0].details["mismatched_fields"],
            ("evidence_context_id", "population"),
        )

    def test_matched_evaluation_pair_scores_advance_and_defer(self) -> None:
        success_manifest, _ = compile_manifest(matched=True)
        failure_manifest, _ = compile_manifest(matched=False)
        success_run = run_manifest(success_manifest, program_id="pubmed-pair-success")
        failure_run = run_manifest(failure_manifest, program_id="pubmed-pair-failure")
        key = EpisodeMatchKey(
            disease="synthetic sickle cell disease context",
            stage=Stage.DISEASE_CONTEXT,
            modality="not yet selected",
            population="California Medicaid SCD evidence contract",
            endpoint_family="unmet need",
            target_or_mechanism="unmet-need",
            decision_time_bin="2026",
        )
        pair_id = "pubmed-context-identity-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="pubmed-context-success",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="california-medicaid-scd-2011-2016",
                available_evidence_packet_id="pubmed-success-packet",
                evaluator_label_id="pubmed-success-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="pubmed-context-failure",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="california-medicaid-scd-2011-2016",
                available_evidence_packet_id="pubmed-failure-packet",
                evaluator_label_id="pubmed-failure-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.MECHANISM_OR_CONTEXT,),
            ),
        )

        score = evaluate_matched_pair(pair)

        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_article_receipt_and_efetch_identity_mismatches_fail_closed(self) -> None:
        job_cases = {
            "receipt": (
                lambda job: job.update(source_receipt_id="different-receipt"),
                "source_receipt_id",
            ),
            "pmcid": (
                lambda job: job["article"].update(pmcid="PMC7654321"),
                "source PMCID",
            ),
            "doi": (
                lambda job: job["article"].update(doi="10.1000/different.scd.1"),
                "source DOI",
            ),
            "title": (
                lambda job: job["article"].update(title="Different title."),
                "source title",
            ),
            "date": (
                lambda job: (
                    job["article"].update(publication_date="2020-03-09"),
                    job["records"][0].update(available_at="2020-03-09"),
                ),
                "electronic publication date",
            ),
        }
        for label, (mutate, message) in job_cases.items():
            with self.subTest(label=label):
                job = copy.deepcopy(pubmed_job())
                mutate(job)
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_ingestion_job(job, pubmed_bundle())

        pmid_job = pubmed_job()
        pmid_job["article"].update(
            pmid="87654321",
            canonical_url="https://pubmed.ncbi.nlm.nih.gov/87654321/",
        )
        with self.assertRaisesRegex(ValueError, "source PMID"):
            extract_ncbi_pubmed_ingestion_job(
                pmid_job,
                pubmed_bundle(
                    locator=EFETCH_URL.replace(PMID, "87654321"),
                    source_version="pmid-87654321-pubmed-xml-2026-07-15",
                ),
            )

        bundle_cases = {
            "source-version": (
                pubmed_bundle(source_version="pmid-12345678-pubmed-xml-repacked"),
                "source_version",
            ),
            "media-type": (
                pubmed_bundle(media_type="text/html"),
                "XML media type",
            ),
            "query": (
                pubmed_bundle(locator=f"{EFETCH_URL}&tool=unreviewed"),
                "exact NCBI PubMed EFetch",
            ),
            "encoded-query": (
                pubmed_bundle(locator=EFETCH_URL.replace("pubmed", "%70ubmed", 1)),
                "exact NCBI PubMed EFetch",
            ),
            "port": (
                pubmed_bundle(locator=EFETCH_URL.replace(".gov/", ".gov:444/")),
                "exact NCBI PubMed EFetch",
            ),
            "chronology": (
                pubmed_bundle(
                    source_version="pmid-12345678-pubmed-xml-2020-03-07",
                    retrieved_at=datetime(2020, 3, 7, tzinfo=timezone.utc),
                ),
                "before article publication",
            ),
        }
        for label, (bundle, message) in bundle_cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_ingestion_job(pubmed_job(), bundle)

    def test_nested_pmid_does_not_override_direct_identity(self) -> None:
        extracted = extract_ncbi_pubmed_ingestion_job(pubmed_job(), pubmed_bundle())

        self.assertEqual(extracted["records"][0]["metadata"]["article_pmid"], PMID)

    def test_xml_security_retraction_and_structure_fail_closed(self) -> None:
        entity_xml = b'<!DOCTYPE x [<!ENTITY x "expanded">]><PubmedArticleSet />'
        retracted_xml = synthetic_pubmed_xml().replace(
            b">Journal Article<",
            b">Retracted Publication<",
        )
        retraction_relation = synthetic_pubmed_xml().replace(
            b'RefType="CommentIn"',
            b'RefType="RetractionIn"',
        )
        duplicate_article = synthetic_pubmed_xml().replace(
            b"</PubmedArticleSet>",
            b"<PubmedArticle /></PubmedArticleSet>",
        )
        duplicate_results = synthetic_pubmed_xml().replace(
            b'<AbstractText Label="RESULTS">',
            b'<AbstractText Label="RESULTS">Duplicate result.</AbstractText>'
            b'<AbstractText Label="RESULTS">',
        )
        cases = {
            "entity": (entity_xml, "entity declarations"),
            "publication-type": (retracted_xml, "retracted publication"),
            "retraction-link": (retraction_relation, "retraction relationship"),
            "duplicate-article": (duplicate_article, "exactly one PubmedArticle"),
            "duplicate-results": (duplicate_results, "result_label must resolve exactly once"),
        }
        for label, (payload, message) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_ingestion_job(
                        pubmed_job(),
                        pubmed_bundle(payload=payload),
                    )

    def test_section_value_comparator_unit_and_anchor_mismatches_fail_closed(self) -> None:
        cases = {
            "result-label": (
                lambda job: job["records"][0]["evidence"].update(
                    result_label="DISCUSSION"
                ),
                "result_label must be RESULTS",
            ),
            "context-label": (
                lambda job: job["records"][0]["evidence"].update(
                    context_label="PURPOSE"
                ),
                "context_label must be METHODS",
            ),
            "result-excerpt": (
                lambda job: job["records"][0]["evidence"].update(
                    result_excerpt="A different result statement with no source match."
                ),
                "result_excerpt must occur exactly once",
            ),
            "value": (
                lambda job: job["records"][0]["evidence"].update(value_text="<21%"),
                "numeric value does not match",
            ),
            "comparator": (
                lambda job: job["records"][0]["metadata"].update(
                    gap_measure_operator="le"
                ),
                "comparator does not match",
            ),
            "percent-unit": (
                lambda job: job["records"][0]["evidence"].update(value_text="<20"),
                "explicit % sign",
            ),
            "population-anchor": (
                lambda job: job["records"][0]["evidence"].update(
                    population_anchor="A sufficiently long but absent population description"
                ),
                "population_anchor must occur exactly once",
            ),
            "geography-anchor": (
                lambda job: job["records"][0]["evidence"].update(
                    geography_anchor="New York"
                ),
                "geography_anchor must occur exactly once",
            ),
            "reference-anchor": (
                lambda job: job["records"][0]["evidence"].update(
                    reference_period_anchor="between 2012 and 2016"
                ),
                "reference_period_anchor must occur exactly once",
            ),
            "treatment-anchor": (
                lambda job: job["records"][0]["evidence"].update(
                    treatment_anchor="different treatment"
                ),
                "treatment_anchor must occur exactly once",
            ),
            "provider-field-spoof": (
                lambda job: job["records"][0]["metadata"].update(
                    {"Article-PMID": "spoofed"}
                ),
                "provider-owned fields",
            ),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(label=label):
                job = copy.deepcopy(pubmed_job())
                mutate(job)
                with self.assertRaisesRegex(ValueError, message):
                    extract_ncbi_pubmed_ingestion_job(job, pubmed_bundle())

        duplicate_value_xml = synthetic_pubmed_xml().replace(
            b"utilization increased after 2014.",
            b"utilization increased after 2014, while &lt;20% remained the threshold.",
        )
        duplicate_value_job = pubmed_job()
        duplicate_value_job["records"][0]["evidence"]["result_excerpt"] = (
            "The cohort included 3,635 individuals. Although <20% of the cohort had "
            "a hydroxyurea prescription filled, utilization increased after 2014, "
            "while <20% remained the threshold."
        )
        with self.assertRaisesRegex(ValueError, "value_text must occur exactly once"):
            extract_ncbi_pubmed_ingestion_job(
                duplicate_value_job,
                pubmed_bundle(payload=duplicate_value_xml),
            )

    def test_cli_extracts_payload_free_generic_job_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-ncbi-pubmed-cli-") as temp_dir:
            root = Path(temp_dir)
            bundle = pubmed_bundle()
            bundle_path = write_source_bundle(root / "bundle", bundle)
            job_path = root / "job.json"
            output_path = root / "extracted.json"
            job_path.write_text(json.dumps(pubmed_job()), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = ingestion_main(
                    [
                        "extract-ncbi-pubmed",
                        "--job",
                        str(job_path),
                        "--bundle",
                        str(bundle_path),
                        "--output",
                        str(output_path),
                    ]
                )

            report = json.loads(stdout.getvalue())
            extracted_text = output_path.read_text(encoding="utf-8")
            self.assertEqual(code, 0)
            self.assertEqual(
                report["status"],
                "provider_job_extracted_requires_human_review",
            )
            self.assertEqual(report["provider_id"], "ncbi_pubmed")
            self.assertEqual(report["record_count"], 1)
            self.assertEqual(report["source_content_hash"], bundle.receipt.content_hash)
            self.assertEqual(
                report["output_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )
            self.assertNotIn(RESULT_EXCERPT, extracted_text)
            self.assertNotIn(CONTEXT_EXCERPT, extracted_text)


if __name__ == "__main__":
    unittest.main()
