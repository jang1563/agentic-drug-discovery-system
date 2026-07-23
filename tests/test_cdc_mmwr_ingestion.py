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
    extract_cdc_mmwr_ingestion_job,
    normalize_cdc_mmwr_ingestion_job,
    write_source_bundle,
)
from agentic_drug_discovery.ingestion_cli import main as ingestion_main


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = datetime(2022, 10, 8, 12, tzinfo=timezone.utc)
REQUEST_AT = datetime(2023, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
CANONICAL_URL = "https://www.cdc.gov/mmwr/volumes/71/ss/synthetic.htm"
ARTICLE_TITLE = "Synthetic CDC MMWR SCD Report"
ARTICLE_DOI = "10.15585/mmwr.synthetic"
BURDEN_EXCERPT = (
    "The 2018 annual prevalence count was 6,027 cases for California."
)
GAP_EXCERPT = (
    "Among eligible recipients in California during 2018, 37% filled hydroxyurea."
)


def synthetic_mmwr_html() -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta name="citation_title" content="{ARTICLE_TITLE}">
  <meta name="citation_doi" content="{ARTICLE_DOI}">
  <meta name="citation_publication_date" content="2022">
  <link rel="canonical" href="{CANONICAL_URL}">
</head>
<body>
  <p>October 7, 2022</p>
  <h2><a id="results">Results</a></h2>
  <p>{BURDEN_EXCERPT}</p>
  <p>{GAP_EXCERPT}</p>
  <h2><a id="discussion">Discussion</a></h2>
  <p>This synthetic article exists only for deterministic contract tests.</p>
</body>
</html>
""".encode()


def mmwr_bundle(
    *,
    payload: bytes | None = None,
    receipt_id: str = "synthetic-mmwr-receipt",
    source_version: str = "doi-10.15585-mmwr.synthetic",
    locator: str = CANONICAL_URL,
    retrieved_at: datetime = RETRIEVED_AT,
) -> SourceBundle:
    return capture_source_bytes(
        payload or synthetic_mmwr_html(),
        receipt_id=receipt_id,
        source_id="synthetic-cdc-mmwr-source",
        source_version=source_version,
        locator=locator,
        retrieved_at=retrieved_at,
        media_type="text/html",
        capture_method="local_file",
    )


def mmwr_job(*, include_gap: bool = False) -> dict:
    job = json.loads(
        (
            ROOT / "rl_env/specs/cdc_mmwr_ingestion_job.example.json"
        ).read_text(encoding="utf-8")
    )
    if include_gap:
        job["records"].append(
            {
                "record_id": "synthetic-mmwr-california-treatment-gap",
                "predicate": "treatment_gap_supported",
                "subject": "synthetic sickle cell disease context",
                "object_value": (
                    "A synthetic hydroxyurea fill gap is reported for contract testing."
                ),
                "observed_at": "2018-12-31",
                "available_at": "2022-10-07",
                "confidence": 0.8,
                "biological_context": {
                    "disease_id": "MONDO_TEST",
                    "evidence_context_id": "scd-california-2018",
                },
                "metadata": {
                    "treatment_context": "synthetic hydroxyurea access",
                    "gap_summary": (
                        "A synthetic residual access gap remains for contract testing."
                    ),
                    "gap_measure_value": 37,
                    "gap_measure_unit": "percent",
                    "population": "synthetic California SCD surveillance population",
                    "geography": "California",
                    "reference_period": "2018",
                },
                "evidence": {
                    "location_id": "results",
                    "excerpt": GAP_EXCERPT,
                    "value_text": "37%",
                },
            }
        )
    return job


def independent_gap_bundle() -> SourceBundle:
    return capture_source_bytes(
        b'{"synthetic_treatment_gap": 37}',
        receipt_id="independent-gap-receipt",
        source_id="independent-gap-source",
        source_version="snapshot-2022-10-08",
        locator="https://example.invalid/synthetic-treatment-gap",
        retrieved_at=datetime(2022, 10, 9, 12, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="local_file",
    )


def independent_gap_record() -> dict:
    return {
        "source_receipt_id": "independent-gap-receipt",
        "record_id": "independent-california-treatment-gap",
        "predicate": "treatment_gap_supported",
        "subject": "synthetic sickle cell disease context",
        "object_value": "A separately sourced synthetic treatment gap is present.",
        "observed_at": "2018-12-31",
        "available_at": "2022-10-08",
        "confidence": 0.8,
        "biological_context": {
            "disease_id": "MONDO_TEST",
            "evidence_context_id": "scd-california-2018",
        },
        "metadata": {
            "treatment_context": "synthetic hydroxyurea access",
            "gap_summary": "A synthetic residual access gap remains.",
            "population": "synthetic California SCD surveillance population",
            "geography": "California",
            "reference_period": "2018",
        },
    }


def compile_success_manifest() -> tuple[dict, dict]:
    burden_bundle = mmwr_bundle()
    gap_bundle = independent_gap_bundle()
    extracted = extract_cdc_mmwr_ingestion_job(mmwr_job(), burden_bundle)
    combined = {
        **extracted,
        "records": [*extracted["records"], independent_gap_record()],
    }
    return compile_pinned_evidence_manifest(
        combined,
        {
            burden_bundle.receipt.receipt_id: burden_bundle,
            gap_bundle.receipt.receipt_id: gap_bundle,
        },
    )


def compile_reused_manifest() -> tuple[dict, dict]:
    bundle = mmwr_bundle()
    extracted = extract_cdc_mmwr_ingestion_job(
        mmwr_job(include_gap=True),
        bundle,
    )
    return compile_pinned_evidence_manifest(
        extracted,
        {bundle.receipt.receipt_id: bundle},
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
        as_of_date=date(2023, 1, 1),
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
                observed_at=date(2018, 12, 31),
                available_at=date(2022, 10, 8),
                subject="synthetic sickle cell disease context",
                object_value="MONDO_TEST",
                confidence=0.9,
            )
        },
    )


class CdcMmwrIngestionTests(unittest.TestCase):
    def test_machine_example_round_trips_through_strict_normalizer(self) -> None:
        example = mmwr_job()

        self.assertEqual(normalize_cdc_mmwr_ingestion_job(example), example)
        with self.assertRaisesRegex(ValueError, "exactly"):
            normalize_cdc_mmwr_ingestion_job({**example, "undeclared": True})

    def test_extractor_binds_article_location_value_and_removes_excerpt(self) -> None:
        extracted = extract_cdc_mmwr_ingestion_job(mmwr_job(), mmwr_bundle())
        record = extracted["records"][0]

        self.assertEqual(extracted["schema_version"], "adds.pinned-ingestion-job.v1")
        self.assertEqual(record["metadata"]["provider_id"], "cdc_mmwr")
        self.assertEqual(record["metadata"]["article_doi"], ARTICLE_DOI)
        self.assertEqual(record["metadata"]["evidence_location"], "results")
        self.assertEqual(
            record["metadata"]["evidence_excerpt_sha256"],
            hashlib.sha256(BURDEN_EXCERPT.encode()).hexdigest(),
        )
        serialized = json.dumps(extracted)
        self.assertNotIn(BURDEN_EXCERPT, serialized)
        self.assertNotIn('"evidence"', serialized)

    def test_provider_output_compiles_and_advances_with_independent_gap(self) -> None:
        manifest, review = compile_success_manifest()

        run = run_manifest(manifest, program_id="cdc-mmwr-provider-success")

        self.assertEqual(review["independent_source_count"], 2)
        self.assertEqual(run.accepted_packets[0].decision, Decision.ADVANCE)
        disease_record = run.final_state.diseases[0]
        self.assertEqual(
            disease_record.attributes["evidence_context_id"],
            "scd-california-2018",
        )
        self.assertEqual(disease_record.attributes["geography"], "California")

    def test_identity_location_value_and_unit_mismatches_fail_closed(self) -> None:
        cases = {
            "receipt": (
                lambda job: job.update(source_receipt_id="different-receipt"),
                "source_receipt_id",
            ),
            "title": (
                lambda job: job["article"].update(title="Different report title"),
                "source title",
            ),
            "doi": (
                lambda job: job["article"].update(doi="10.15585/mmwr.other"),
                "source_version",
            ),
            "location": (
                lambda job: job["records"][0]["evidence"].update(
                    location_id="discussion"
                ),
                "match exactly one block",
            ),
            "excerpt": (
                lambda job: job["records"][0]["evidence"].update(
                    excerpt="The source contains a different synthetic burden statement."
                ),
                "match exactly one block",
            ),
            "value": (
                lambda job: job["records"][0]["evidence"].update(
                    value_text="6,028"
                ),
                "must occur exactly once",
            ),
            "unit": (
                lambda job: job["records"][0]["metadata"].update(
                    measure_unit="persons"
                ),
                "declared unit is absent",
            ),
            "geography": (
                lambda job: job["records"][0]["metadata"].update(
                    geography="Georgia"
                ),
                "metadata.geography is absent",
            ),
            "provider-field-spoof": (
                lambda job: job["records"][0]["metadata"].update(
                    {"Provider-ID": "spoofed"}
                ),
                "provider-owned fields",
            ),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(label=label):
                job = copy.deepcopy(mmwr_job())
                mutate(job)
                with self.assertRaisesRegex(ValueError, message):
                    extract_cdc_mmwr_ingestion_job(job, mmwr_bundle())

    def test_receipt_version_port_and_publication_chronology_fail_closed(self) -> None:
        invalid_bundles = {
            "version": (
                mmwr_bundle(
                    source_version="doi-10.15585-mmwr.synthetic-repacked"
                ),
                "exactly bind",
            ),
            "port": (
                mmwr_bundle(
                    locator=(
                        "https://www.cdc.gov:444/mmwr/volumes/71/ss/synthetic.htm"
                    )
                ),
                "canonical public CDC MMWR URL",
            ),
            "chronology": (
                mmwr_bundle(
                    retrieved_at=datetime(2022, 10, 6, 12, tzinfo=timezone.utc)
                ),
                "before article publication",
            ),
        }
        for label, (bundle, message) in invalid_bundles.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    extract_cdc_mmwr_ingestion_job(mmwr_job(), bundle)

        malformed_doi = mmwr_job()
        malformed_doi["article"]["doi"] = "10.15585/mmwr.synthetic."
        with self.assertRaisesRegex(ValueError, "identify a CDC MMWR DOI"):
            normalize_cdc_mmwr_ingestion_job(malformed_doi)

    def test_reused_mmwr_snapshot_defers_and_forms_matched_evaluation_pair(self) -> None:
        success_manifest, success_review = compile_success_manifest()
        failure_manifest, failure_review = compile_reused_manifest()
        success_run = run_manifest(
            success_manifest,
            program_id="cdc-mmwr-matched-success",
        )
        failure_run = run_manifest(
            failure_manifest,
            program_id="cdc-mmwr-matched-failure",
        )

        self.assertEqual(success_review["independent_source_count"], 2)
        self.assertEqual(failure_review["independent_source_count"], 1)
        self.assertEqual(failure_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            failure_run.promotions[0].code,
            "pinned_unmet_need_sources_not_independent",
        )

        key = EpisodeMatchKey(
            disease="synthetic sickle cell disease context",
            stage=Stage.DISEASE_CONTEXT,
            modality="not yet selected",
            population="synthetic California SCD surveillance population",
            endpoint_family="unmet need",
            target_or_mechanism="unmet-need",
            decision_time_bin="2023",
        )
        pair_id = "cdc-mmwr-source-independence-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="cdc-mmwr-success",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="scd-california-2018",
                available_evidence_packet_id="cdc-mmwr-success-packet",
                evaluator_label_id="cdc-mmwr-success-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="cdc-mmwr-failure",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="scd-california-2018",
                available_evidence_packet_id="cdc-mmwr-failure-packet",
                evaluator_label_id="cdc-mmwr-failure-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.EVIDENCE_QUALITY,),
            ),
        )

        score = evaluate_matched_pair(pair)

        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_cli_extracts_payload_free_generic_job(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-cdc-mmwr-cli-") as temp_dir:
            root = Path(temp_dir)
            bundle = mmwr_bundle()
            bundle_path = write_source_bundle(root / "bundle", bundle)
            job_path = root / "job.json"
            output_path = root / "extracted.json"
            job_path.write_text(json.dumps(mmwr_job()), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = ingestion_main(
                    [
                        "extract-cdc-mmwr",
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
            self.assertEqual(report["record_count"], 1)
            self.assertEqual(
                report["source_content_hash"],
                bundle.receipt.content_hash,
            )
            self.assertEqual(
                report["output_sha256"],
                hashlib.sha256(output_path.read_bytes()).hexdigest(),
            )
            self.assertNotIn(BURDEN_EXCERPT, extracted_text)


if __name__ == "__main__":
    unittest.main()
