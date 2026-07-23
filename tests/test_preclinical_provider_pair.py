from __future__ import annotations

import copy
import json
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from adapters.execution_registry import register_existing_adapters
from adapters.pinned_evidence_adapter import PinnedEvidenceAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    Decision,
    DiseaseRecord,
    EpisodeArm,
    EpisodeMatchKey,
    EvidenceEvent,
    EvidenceRelation,
    FailureCause,
    MatchedEpisodePair,
    ProgramState,
    PromotionContext,
    PromotionStatus,
    SourceReference,
    Stage,
    StagePlan,
    TargetRecord,
    ToolCallSpec,
    ToolRegistry,
    build_default_semantic_mapper_registry,
    compile_pinned_evidence_manifest,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    extract_chembl_activity_ingestion_job,
    extract_ncbi_pubmed_disease_model_ingestion_job,
)
from tests.test_chembl_activity_ingestion import (
    chembl_job,
    source_bundles as chembl_source_bundles,
)
from tests.test_ncbi_pubmed_disease_model_ingestion import (
    disease_model_job,
    pubmed_bundle,
)


REQUEST_AT = datetime(2026, 7, 15, 2, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def compile_provider_manifest() -> tuple[dict, dict]:
    chembl_bundles = chembl_source_bundles()
    pubmed = pubmed_bundle()
    functional = extract_chembl_activity_ingestion_job(chembl_job(), chembl_bundles)
    model = extract_ncbi_pubmed_disease_model_ingestion_job(disease_model_job(), pubmed)
    combined = {
        "schema_version": "adds.pinned-ingestion-job.v1",
        "job_id": "synthetic-preclinical-provider-pair",
        "records": [*functional["records"], *model["records"]],
    }
    return compile_pinned_evidence_manifest(
        combined,
        {
            chembl_bundles["activity"].receipt.receipt_id: chembl_bundles["activity"],
            pubmed.receipt.receipt_id: pubmed,
        },
    )


def preclinical_state(*, program_id: str) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id="synthetic-disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="synthetic disease",
        predicate="disease_context_resolved",
        object_value="MONDO_SYNTHETIC",
        source=SourceReference(
            source_id="synthetic-disease-source",
            source_version="fixture-2026-05-06",
            locator="https://example.invalid/synthetic-disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2026, 5, 6),
        available_at=date(2026, 5, 6),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_SYNTHETIC"},
    )
    return ProgramState(
        program_id=program_id,
        disease="synthetic disease",
        therapeutic_hypothesis="Synthetic provider records govern one stage gate.",
        as_of_date=date(2026, 7, 15),
        current_stage=Stage.PRECLINICAL_VALIDATION,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence,),
        diseases=(
            DiseaseRecord(
                disease_id="MONDO_SYNTHETIC",
                name="synthetic disease",
                stage=Stage.DISEASE_CONTEXT,
                identifiers={"canonical": "MONDO_SYNTHETIC"},
                supporting_evidence=(disease_evidence.evidence_id,),
            ),
        ),
        targets=(
            TargetRecord(
                target_id="ENSG_SYNTHETIC1",
                symbol="SYN1",
                disease_id="MONDO_SYNTHETIC",
                organism="Homo sapiens",
                stage=Stage.MODALITY_SELECTION,
                identifiers={
                    "ensembl_gene": "ENSG_SYNTHETIC1",
                    "gene_symbol": "SYN1",
                    "chembl_target": "CHEMBL9000014",
                    "uniprot": "P00001",
                },
            ),
        ),
        candidates=(
            CandidateRecord(
                candidate_id="CHEMBL9000013",
                name="SYNTHETIC-CANDIDATE",
                modality="small molecule",
                stage=Stage.LEAD_OPTIMIZATION,
                status=CandidateStatus.SELECTED,
                attributes={
                    "target_record_id": "ENSG_SYNTHETIC1",
                    "target_chembl_id": "CHEMBL9000014",
                    "target_symbol": "SYN1",
                    "disease_id": "MONDO_SYNTHETIC",
                },
            ),
        ),
    )


def preclinical_plan() -> StagePlan:
    return StagePlan(
        plan_id="synthetic-preclinical-provider-plan",
        stage=Stage.PRECLINICAL_VALIDATION,
        calls=(
            ToolCallSpec(
                call_id="functional-effect",
                tool_id="pinned_evidence",
                operation="candidate_functional_effect",
                action_type=ActionType.QUERY_DATABASE,
                purpose=(
                    "Resolve typed functional and disease-model effects from "
                    "lineage-independent provider records."
                ),
                arguments={
                    "candidate_id": "CHEMBL9000013",
                    "target_id": "CHEMBL9000014",
                    "disease_id": "MONDO_SYNTHETIC",
                },
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.CLINICAL_STRATEGY,
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
        state=preclinical_state(program_id=program_id),
        stage_plan=preclinical_plan(),
        promotion_contexts={
            "functional-effect": PromotionContext(
                observed_at=date(2002, 11, 14),
                available_at=date(2026, 5, 1),
                subject="SYNTHETIC-CANDIDATE",
                object_value="CHEMBL9000014",
                confidence=0.9,
                candidate_id="CHEMBL9000013",
                candidate_name="SYNTHETIC-CANDIDATE",
                modality="small molecule",
                biological_context={"disease_id": "MONDO_SYNTHETIC"},
            )
        },
    )


class PreclinicalProviderPairTests(unittest.TestCase):
    def test_public_validation_snapshot_is_payload_free_and_self_consistent(
        self,
    ) -> None:
        snapshot = json.loads(
            (
                ROOT / "docs/preclinical_provider_validation_snapshot.json"
            ).read_text(encoding="utf-8")
        )
        policy = snapshot["public_payload_policy"]
        self.assertEqual(
            snapshot["schema_version"],
            "adds.preclinical-provider-validation-snapshot.v1",
        )
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        functional = snapshot["functional_activity"]
        disease_model = snapshot["disease_model_effect"]
        self.assertIn(
            disease_model["source_candidate_name"].casefold(),
            {value.casefold() for value in functional["candidate_aliases"]},
        )
        functional_lineages = {
            value.casefold() for value in functional["source_lineage_ids"]
        }
        model_lineages = {
            value.casefold() for value in disease_model["source_lineage_ids"]
        }
        self.assertTrue(functional_lineages.isdisjoint(model_lineages))

        digests = [
            *functional["source_sha256_by_resource"].values(),
            functional["review_job_sha256"],
            functional["sanitized_output_sha256"],
            disease_model["source_xml_sha256"],
            disease_model["review_job_sha256"],
            disease_model["sanitized_output_sha256"],
            snapshot["composite_manifest"]["sha256"],
        ]
        self.assertTrue(all(SHA256.fullmatch(value) for value in digests))
        human_report = (
            ROOT / "docs/20_preclinical_provider_ingestion.md"
        ).read_text(encoding="utf-8")
        for digest in digests:
            self.assertIn(digest, human_report)

        matched = snapshot["matched_pair"]
        self.assertEqual(matched["success"]["decision"], "advance")
        self.assertEqual(matched["failure"]["decision"], "defer")
        self.assertEqual(matched["failure"]["new_preclinical_evidence_count"], 0)
        self.assertEqual(
            set(matched["failure"]["overlapping_source_lineage_ids"]),
            {"pubmed:18232633"},
        )
        self.assertEqual(matched["balanced_accuracy"], 1.0)
        self.assertIn("not discovery performance", matched["metric_interpretation"])
        self.assertIn(matched["success"]["promotion_code"], human_report)
        self.assertIn(matched["failure"]["promotion_code"], human_report)

    def test_independent_provider_pair_advances_and_same_lineage_arm_defers(
        self,
    ) -> None:
        manifest, review = compile_provider_manifest()
        same_lineage = copy.deepcopy(manifest)
        disease_model = next(
            record
            for record in same_lineage["records"]
            if record["predicate"] == "disease_model_effect_supported"
        )
        disease_model["metadata"]["source_lineage_ids"].append("pubmed:99999991")

        success_run = run_manifest(manifest, program_id="synthetic-provider-success")
        failure_run = run_manifest(
            same_lineage, program_id="synthetic-provider-same-lineage"
        )

        self.assertEqual(review["independent_source_count"], 2)
        self.assertEqual(success_run.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(success_run.final_state.current_stage, Stage.CLINICAL_STRATEGY)
        self.assertEqual(
            success_run.final_state.assays[0].attributes["endpoint_value"], 12.0
        )
        self.assertEqual(
            success_run.final_state.model_systems[0].attributes["endpoint_value"],
            90.0,
        )
        self.assertEqual(
            success_run.promotions[0].details["independent_lineage_count"], 5
        )

        self.assertEqual(failure_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            failure_run.final_state.current_stage, Stage.PRECLINICAL_VALIDATION
        )
        self.assertEqual(
            failure_run.final_state.evidence,
            failure_run.initial_state.evidence,
        )
        self.assertEqual(failure_run.final_state.assays, ())
        self.assertEqual(failure_run.final_state.model_systems, ())
        self.assertEqual(failure_run.promotions[0].status, PromotionStatus.ABSTAINED)
        self.assertEqual(
            failure_run.promotions[0].code,
            "pinned_functional_effect_lineage_not_independent",
        )
        self.assertEqual(
            failure_run.promotions[0].details["overlapping_source_lineage_ids"],
            ("pubmed:99999991",),
        )

        match_key = EpisodeMatchKey(
            disease="synthetic disease",
            stage=Stage.PRECLINICAL_VALIDATION,
            modality="small molecule",
            population="synthetic preclinical provider contract",
            endpoint_family="functional and disease-model effect",
            target_or_mechanism="CHEMBL9000014",
            decision_time_bin="2026",
        )
        pair_id = "synthetic-provider-lineage-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="synthetic-provider-independent",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=match_key,
                asset_or_candidate_id="CHEMBL9000013",
                target_or_mechanism_id="CHEMBL9000014",
                condition_or_context_id="MONDO_SYNTHETIC",
                available_evidence_packet_id="synthetic-independent-packet",
                evaluator_label_id="synthetic-independent-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="synthetic-provider-shared-lineage",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=match_key,
                asset_or_candidate_id="CHEMBL9000013",
                target_or_mechanism_id="CHEMBL9000014",
                condition_or_context_id="MONDO_SYNTHETIC",
                available_evidence_packet_id="synthetic-shared-lineage-packet",
                evaluator_label_id="synthetic-shared-lineage-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.EVIDENCE_QUALITY,),
            ),
        )
        score = evaluate_matched_pair(pair)

        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)


if __name__ == "__main__":
    unittest.main()
