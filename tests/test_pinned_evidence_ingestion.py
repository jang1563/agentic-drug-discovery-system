from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
    capture_local_file,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    normalize_pinned_ingestion_job,
    read_source_bundle,
    source_receipt_from_dict,
    verify_source_payload,
    write_source_bundle,
)
from agentic_drug_discovery.ingestion import canonical_json_bytes
from agentic_drug_discovery.ingestion_cli import main as ingestion_main


RETRIEVED_AT = datetime(2024, 6, 15, 12, tzinfo=timezone.utc)
REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
ROOT = Path(__file__).resolve().parents[1]


def source_bundle(
    receipt_id: str,
    source_id: str,
    payload: bytes,
) -> SourceBundle:
    return capture_source_bytes(
        payload,
        receipt_id=receipt_id,
        source_id=source_id,
        source_version="snapshot-2024-06-15",
        locator=f"https://example.invalid/public-source/{source_id}",
        retrieved_at=RETRIEVED_AT,
        media_type="application/json",
        capture_method="local_file",
    )


def disease_job(*, gap_receipt_id: str = "gap-receipt") -> dict:
    return {
        "schema_version": "adds.pinned-ingestion-job.v1",
        "job_id": "test-disease-context-ingestion",
        "records": [
            {
                "source_receipt_id": "burden-receipt",
                "record_id": "ingested-burden",
                "predicate": "disease_burden_supported",
                "subject": "test disease",
                "object_value": "A bounded burden summary is available.",
                "observed_at": "2024-06-01",
                "available_at": "2024-06-10",
                "confidence": 0.8,
                "biological_context": {
                    "disease_id": "MONDO_TEST",
                    "evidence_context_id": "test-population-context",
                },
                "metadata": {
                    "measure_type": "prevalence",
                    "measure_value": 12.5,
                    "measure_unit": "persons per 100,000",
                    "population": "illustrative population",
                    "geography": "illustrative geography",
                    "reference_period": "2024",
                },
            },
            {
                "source_receipt_id": gap_receipt_id,
                "record_id": "ingested-treatment-gap",
                "predicate": "treatment_gap_supported",
                "subject": "test disease",
                "object_value": "A bounded treatment-gap summary is available.",
                "observed_at": "2024-06-02",
                "available_at": "2024-06-11",
                "confidence": 0.8,
                "biological_context": {
                    "disease_id": "MONDO_TEST",
                    "evidence_context_id": "test-population-context",
                },
                "metadata": {
                    "treatment_context": "illustrative standard of care",
                    "gap_summary": "A residual need remains in the reviewed summary.",
                    "population": "illustrative population",
                    "geography": "illustrative geography",
                    "reference_period": "2024",
                },
            },
        ],
    }


def disease_state(program_id: str) -> ProgramState:
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Pinned ingestion must preserve source provenance.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.DISEASE_CONTEXT,
        budget=BudgetState(limit=1.0),
    )


def disease_plan() -> StagePlan:
    return StagePlan(
        plan_id="ingested-disease-plan",
        stage=Stage.DISEASE_CONTEXT,
        calls=(
            ToolCallSpec(
                call_id="unmet-need",
                tool_id="pinned_evidence",
                operation="disease_unmet_need",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve burden and treatment gap from captured sources.",
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
    return runner.run_stage(
        run_id=f"{program_id}-run",
        state=disease_state(program_id),
        stage_plan=disease_plan(),
        promotion_contexts={
            "unmet-need": PromotionContext(
                observed_at=date(2024, 6, 1),
                available_at=date(2024, 6, 11),
                subject="test disease",
                object_value="MONDO_TEST",
                confidence=0.9,
            )
        },
    )


class PinnedEvidenceIngestionTests(unittest.TestCase):
    def test_machine_examples_round_trip_through_strict_parsers(self) -> None:
        receipt_path = ROOT / "rl_env/specs/source_receipt.example.json"
        job_path = ROOT / "rl_env/specs/pinned_evidence_ingestion_job.example.json"
        receipt_example = json.loads(receipt_path.read_text(encoding="utf-8"))
        job_example = json.loads(job_path.read_text(encoding="utf-8"))

        self.assertEqual(
            source_receipt_from_dict(receipt_example).to_dict(),
            receipt_example,
        )
        self.assertEqual(normalize_pinned_ingestion_job(job_example), job_example)
        with self.assertRaises(ValueError):
            normalize_pinned_ingestion_job({**job_example, "undeclared": True})

    def test_source_receipt_round_trips_and_bundle_verifies(self) -> None:
        bundle = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )
        receipt = source_receipt_from_dict(bundle.receipt.to_dict())

        self.assertEqual(receipt, bundle.receipt)
        verify_source_payload(receipt, bundle.payload)
        self.assertNotIn("/tmp/", json.dumps(receipt.to_dict()))

        with tempfile.TemporaryDirectory(prefix="adds-ingestion-test-") as temp_dir:
            path = Path(temp_dir) / "bundle"
            write_source_bundle(path, bundle)
            self.assertEqual(read_source_bundle(path), bundle)

    def test_source_payload_tampering_fails_closed(self) -> None:
        bundle = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )

        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verify_source_payload(bundle.receipt, b'{"measure": 99.9}')

    def test_public_locator_rejects_credentials_without_overmatching(self) -> None:
        safe = capture_source_bytes(
            b"safe",
            receipt_id="safe-receipt",
            source_id="safe-source",
            source_version="snapshot-2024-06-15",
            locator="https://example.invalid/data?monkey=visible",
            retrieved_at=RETRIEVED_AT,
            media_type="text/plain",
            capture_method="local_file",
        )
        self.assertEqual(safe.receipt.source_id, "safe-source")

        with self.assertRaisesRegex(ValueError, "credential-like"):
            capture_source_bytes(
                b"unsafe",
                receipt_id="unsafe-receipt",
                source_id="unsafe-source",
                source_version="snapshot-2024-06-15",
                locator="https://example.invalid/data?api_key=not-public",
                retrieved_at=RETRIEVED_AT,
                media_type="text/plain",
                capture_method="local_file",
            )
        with self.assertRaisesRegex(ValueError, "credential-like"):
            capture_source_bytes(
                b"unsafe",
                receipt_id="signed-receipt",
                source_id="signed-source",
                source_version="snapshot-2024-06-15",
                locator=(
                    "https://example.invalid/data?"
                    "X-Amz-Signature=not-public"
                ),
                retrieved_at=RETRIEVED_AT,
                media_type="text/plain",
                capture_method="local_file",
            )
        with self.assertRaisesRegex(ValueError, "immutable source revision"):
            capture_source_bytes(
                b"unsafe",
                receipt_id="mutable-receipt",
                source_id="mutable-source",
                source_version="latest",
                locator="https://example.invalid/data",
                retrieved_at=RETRIEVED_AT,
                media_type="text/plain",
                capture_method="local_file",
            )

    def test_local_capture_rejects_invalid_or_racing_size_limits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-ingestion-size-") as temp_dir:
            source = Path(temp_dir) / "source.json"
            source.write_bytes(b"12345")
            kwargs = {
                "receipt_id": "bounded-receipt",
                "source_id": "bounded-source",
                "source_version": "snapshot-2024-06-15",
                "locator": "https://example.invalid/data",
                "retrieved_at": RETRIEVED_AT,
            }

            with self.assertRaisesRegex(ValueError, "positive integer"):
                capture_local_file(source, max_bytes=True, **kwargs)
            with self.assertRaisesRegex(ValueError, "configured limit"):
                capture_local_file(source, max_bytes=4, **kwargs)

    def test_compiler_emits_adapter_readable_payload_free_manifest(self) -> None:
        burden = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )
        gap = source_bundle(
            "gap-receipt",
            "gap-source",
            b'{"limitation": "residual need"}',
        )

        manifest, review = compile_pinned_evidence_manifest(
            disease_job(),
            {
                burden.receipt.receipt_id: burden,
                gap.receipt.receipt_id: gap,
            },
        )

        adapter = PinnedEvidenceAdapter(manifest)
        self.assertEqual(adapter.disease_unmet_need("MONDO_TEST")["status"], "resolved")
        self.assertEqual(review["status"], "requires_human_review")
        self.assertEqual(review["independent_source_count"], 2)
        self.assertEqual(
            review["manifest_sha256"],
            hashlib.sha256(canonical_json_bytes(manifest)).hexdigest(),
        )
        serialized = json.dumps({"manifest": manifest, "review": review})
        self.assertNotIn('"measure"', serialized)
        self.assertNotIn('"limitation"', serialized)

    def test_compiler_rejects_false_chronology_and_payload_fields(self) -> None:
        burden = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )
        gap = source_bundle(
            "gap-receipt",
            "gap-source",
            b'{"limitation": "residual need"}',
        )
        bundles = {
            burden.receipt.receipt_id: burden,
            gap.receipt.receipt_id: gap,
        }
        future = disease_job()
        future["records"][0]["available_at"] = "2024-06-20"
        with self.assertRaisesRegex(ValueError, "cannot follow source retrieval"):
            compile_pinned_evidence_manifest(future, bundles)

        raw_field = disease_job()
        raw_field["records"][0]["metadata"]["Raw.Payload"] = {"rows": []}
        with self.assertRaisesRegex(ValueError, "forbidden raw-payload field"):
            compile_pinned_evidence_manifest(raw_field, bundles)

        nonfinite = disease_job()
        nonfinite["records"][0]["metadata"]["measure_value"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite number"):
            compile_pinned_evidence_manifest(nonfinite, bundles)

    def test_duplicate_source_bytes_cannot_masquerade_as_independence(self) -> None:
        shared_payload = b'{"same_snapshot": true}'
        burden = source_bundle(
            "burden-receipt",
            "burden-source",
            shared_payload,
        )
        gap = source_bundle(
            "gap-receipt",
            "gap-source",
            shared_payload,
        )
        manifest, review = compile_pinned_evidence_manifest(
            disease_job(),
            {
                burden.receipt.receipt_id: burden,
                gap.receipt.receipt_id: gap,
            },
        )

        run = run_manifest(manifest, program_id="duplicate-source-bytes-program")

        self.assertEqual(review["independent_source_count"], 1)
        self.assertTrue(review["reused_content_hashes"])
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            run.promotions[0].code,
            "pinned_unmet_need_sources_not_independent",
        )
        self.assertEqual(len(run.final_state.evidence), 0)

    def test_compiled_independent_and_reused_sources_form_matched_pair(self) -> None:
        burden = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )
        gap = source_bundle(
            "gap-receipt",
            "gap-source",
            b'{"limitation": "residual need"}',
        )
        success_manifest, success_review = compile_pinned_evidence_manifest(
            disease_job(),
            {
                burden.receipt.receipt_id: burden,
                gap.receipt.receipt_id: gap,
            },
        )
        failure_manifest, failure_review = compile_pinned_evidence_manifest(
            disease_job(gap_receipt_id="burden-receipt"),
            {burden.receipt.receipt_id: burden},
        )
        success_run = run_manifest(
            success_manifest,
            program_id="ingested-source-success-program",
        )
        failure_run = run_manifest(
            failure_manifest,
            program_id="ingested-source-failure-program",
        )
        key = EpisodeMatchKey(
            disease="test disease",
            stage=Stage.DISEASE_CONTEXT,
            modality="not yet selected",
            population="illustrative population",
            endpoint_family="unmet need",
            target_or_mechanism="unmet-need",
            decision_time_bin="2025",
        )
        pair_id = "ingested-source-independence-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="ingested-source-success",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="ingested-source-success-packet",
                evaluator_label_id="ingested-source-success-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="ingested-source-failure",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="ingested-source-failure-packet",
                evaluator_label_id="ingested-source-failure-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.EVIDENCE_QUALITY,),
            ),
        )

        score = evaluate_matched_pair(pair)

        self.assertEqual(success_review["independent_source_count"], 2)
        self.assertEqual(failure_review["independent_source_count"], 1)
        self.assertTrue(failure_review["reused_source_ids"])
        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_cli_captures_local_source_without_exposing_its_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-ingestion-cli-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.json"
            source.write_text('{"measure": 12.5}', encoding="utf-8")
            output = root / "bundle"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = ingestion_main(
                    [
                        "capture",
                        "--input-file",
                        str(source),
                        "--locator",
                        "https://example.invalid/public-source/burden",
                        "--receipt-id",
                        "cli-burden-receipt",
                        "--source-id",
                        "cli-burden-source",
                        "--source-version",
                        "snapshot-2024-06-15",
                        "--retrieved-at",
                        "2024-06-15T12:00:00Z",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(code, 0)
            report = json.loads(stdout.getvalue())
            receipt_text = (output / "receipt.json").read_text(encoding="utf-8")
            self.assertEqual(report["status"], "captured")
            self.assertNotIn(str(source), receipt_text)

    def test_cli_compile_preflights_both_outputs_before_writing(self) -> None:
        burden = source_bundle(
            "burden-receipt",
            "burden-source",
            b'{"measure": 12.5}',
        )
        gap = source_bundle(
            "gap-receipt",
            "gap-source",
            b'{"limitation": "residual need"}',
        )
        with tempfile.TemporaryDirectory(prefix="adds-ingestion-compile-") as temp_dir:
            root = Path(temp_dir)
            burden_path = write_source_bundle(root / "burden-bundle", burden)
            gap_path = write_source_bundle(root / "gap-bundle", gap)
            job_path = root / "job.json"
            job_path.write_text(json.dumps(disease_job()), encoding="utf-8")
            manifest_path = root / "manifest.json"
            review_path = root / "review.json"
            review_path.write_text('{"sentinel": true}', encoding="utf-8")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                code = ingestion_main(
                    [
                        "compile",
                        "--job",
                        str(job_path),
                        "--bundle",
                        str(burden_path),
                        "--bundle",
                        str(gap_path),
                        "--manifest-out",
                        str(manifest_path),
                        "--review-out",
                        str(review_path),
                    ]
                )

            self.assertEqual(code, 2)
            self.assertFalse(manifest_path.exists())
            self.assertEqual(review_path.read_text(encoding="utf-8"), '{"sentinel": true}')
            self.assertIn("compile outputs already exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
