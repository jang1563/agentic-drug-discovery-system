from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

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
    EvidenceEvent,
    EvidenceRelation,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    PromotionStatus,
    SourceReference,
    Stage,
    StagePlan,
    TargetRecord,
    ToolCallSpec,
    ToolRegistry,
    build_default_semantic_mapper_registry,
)


REQUEST_AT = datetime(2025, 1, 2, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)


def disposition_manifest() -> dict:
    context = {
        "candidate_id": "CHEMBL_TEST",
        "intervention_id": "CHEMBL_TEST",
        "disease_id": "MONDO_TEST",
        "trial_id": "NCT00000002",
        "protocol_id": "TEST-P3-FAIL",
    }
    common_metadata = {
        "protocol_id": "TEST-P3-FAIL",
        "candidate_aliases": ["Test Drug", "TestDrug-1"],
        "shared_trial_lineage_id": "sponsor-protocol:TEST-P3-FAIL",
    }
    return {
        "schema_version": "adds.pinned-evidence.v1",
        "records": [
            {
                "record_id": "test-registry-termination",
                "predicate": "clinical_trial_terminated_for_lack_of_efficacy",
                "subject": "Test Drug",
                "object_value": "test disease",
                "observed_at": "2024-06-01",
                "available_at": "2024-06-02",
                "confidence": 0.95,
                "source": {
                    "source_id": "clinicaltrials-gov-NCT00000002",
                    "source_version": (
                        "clinicaltrials-gov-NCT00000002-version-2025-01-01"
                    ),
                    "locator": (
                        "https://clinicaltrials.gov/api/v2/studies/NCT00000002"
                    ),
                    "content_hash": "1" * 64,
                },
                "biological_context": dict(context),
                "metadata": {
                    **common_metadata,
                    "provider_id": "clinicaltrials_gov",
                    "registry": "ClinicalTrials.gov",
                    "registry_version": "2025-01-01",
                    "study_type": "INTERVENTIONAL",
                    "overall_status": "TERMINATED",
                    "phase": "PHASE3",
                    "why_stopped": "Low probability of meeting the primary endpoint.",
                    "why_stopped_code": "lack_of_efficacy",
                    "source_interventions": ["TestDrug-1"],
                    "source_conditions": ["test disease"],
                    "primary_endpoint": "Test event rate",
                    "enrollment_count": 200,
                    "source_lineage_ids": [
                        "clinicaltrials-gov:NCT00000002",
                        "sponsor-protocol:TEST-P3-FAIL",
                    ],
                },
            },
            {
                "record_id": "test-publication-endpoint",
                "predicate": "clinical_primary_endpoint_not_met",
                "subject": "Test Drug",
                "object_value": "test disease",
                "observed_at": "2024-08-01",
                "available_at": "2024-08-02",
                "confidence": 0.95,
                "source": {
                    "source_id": "ncbi-pubmed-99999991",
                    "source_version": "pmid-99999991-pubmed-xml-2025-01-02",
                    "locator": (
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
                        "efetch.fcgi?db=pubmed&id=99999991&retmode=xml"
                    ),
                    "content_hash": "2" * 64,
                },
                "biological_context": dict(context),
                "metadata": {
                    **common_metadata,
                    "provider_id": "ncbi_pubmed",
                    "pmid": "99999991",
                    "doi": "10.1000/test.negative-trial",
                    "article_title": "A negative test phase III trial.",
                    "publication_date": "2024-08-01",
                    "source_candidate_name": "Test Drug",
                    "primary_endpoint_met": False,
                    "effect_direction": "no_clinical_benefit",
                    "endpoint_name": "Test event rate",
                    "candidate_rate": 0.4,
                    "comparator_rate": 0.3,
                    "rate_unit": "reported event-rate value",
                    "early_termination_reason": "lack_of_efficacy",
                    "source_lineage_ids": [
                        "pubmed:99999991",
                        "sponsor-protocol:TEST-P3-FAIL",
                    ],
                },
            },
        ],
    }


def clinical_state(*, program_id: str, as_of_date: date = date(2025, 1, 2)) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id=f"{program_id}:disease",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="test-disease-source",
            source_version="fixture-2024-01-01",
            locator="https://example.invalid/test-disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 1),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Clinical outcomes govern indication disposition.",
        as_of_date=as_of_date,
        current_stage=Stage.CLINICAL_STRATEGY,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence,),
        diseases=(
            DiseaseRecord(
                disease_id="MONDO_TEST",
                name="test disease",
                stage=Stage.DISEASE_CONTEXT,
                identifiers={"canonical": "MONDO_TEST"},
                supporting_evidence=(disease_evidence.evidence_id,),
            ),
        ),
        targets=(
            TargetRecord(
                target_id="ENSG_TEST1",
                symbol="TEST1",
                disease_id="MONDO_TEST",
                organism="Homo sapiens",
                stage=Stage.MODALITY_SELECTION,
                identifiers={
                    "canonical": "ENSG_TEST1",
                    "ensembl_gene": "ENSG_TEST1",
                    "gene_symbol": "TEST1",
                    "chembl_target": "CHEMBL_TARGET",
                },
            ),
        ),
        candidates=(
            CandidateRecord(
                candidate_id="CHEMBL_TEST",
                name="Test Drug",
                modality="small molecule",
                stage=Stage.LEAD_OPTIMIZATION,
                status=CandidateStatus.SELECTED,
                attributes={
                    "target_record_id": "ENSG_TEST1",
                    "target_chembl_id": "CHEMBL_TARGET",
                    "target_symbol": "TEST1",
                    "disease_id": "MONDO_TEST",
                },
            ),
        ),
    )


def clinical_plan() -> StagePlan:
    return StagePlan(
        plan_id="pinned-clinical-disposition-plan",
        stage=Stage.CLINICAL_STRATEGY,
        calls=(
            ToolCallSpec(
                call_id="clinical-disposition",
                tool_id="pinned_evidence",
                operation="clinical_trial_disposition",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve one historical negative clinical disposition.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "disease_id": "MONDO_TEST",
                    "trial_id": "NCT00000002",
                },
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.REGULATORY_POSTMARKET,
    )


def run_manifest(
    manifest: dict,
    *,
    program_id: str,
    state_as_of: date = date(2025, 1, 2),
):
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
        state=clinical_state(program_id=program_id, as_of_date=state_as_of),
        stage_plan=clinical_plan(),
        promotion_contexts={
            "clinical-disposition": PromotionContext(
                observed_at=date(2024, 6, 1),
                available_at=date(2024, 6, 2),
                subject="Test Drug",
                object_value="test disease",
                confidence=0.9,
                candidate_id="CHEMBL_TEST",
                candidate_name="Test Drug",
                modality="small molecule",
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "intervention_id": "CHEMBL_TEST",
                },
            )
        },
    )


class ClinicalTrialDispositionTests(unittest.TestCase):
    def test_profile_requires_both_corroborating_records(self) -> None:
        complete = PinnedEvidenceAdapter(disposition_manifest())
        incomplete_manifest = disposition_manifest()
        incomplete_manifest["records"].pop()
        incomplete = PinnedEvidenceAdapter(incomplete_manifest)

        resolved = complete.clinical_trial_disposition(
            "CHEMBL_TEST", "MONDO_TEST", "NCT00000002"
        )
        missing = incomplete.clinical_trial_disposition(
            "CHEMBL_TEST", "MONDO_TEST", "NCT00000002"
        )

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(len(resolved["records"]), 2)
        self.assertEqual(missing["status"], "incomplete")
        self.assertEqual(
            missing["missing_predicates"], ["clinical_primary_endpoint_not_met"]
        )

    def test_exact_pair_kills_historical_program_and_preserves_one_trial_lineage(
        self,
    ) -> None:
        run = run_manifest(disposition_manifest(), program_id="negative-clinical")

        self.assertEqual(run.accepted_packets[0].decision, Decision.KILL)
        self.assertEqual(run.final_state.status, ProgramStatus.TERMINATED)
        self.assertEqual(run.final_state.current_stage, Stage.CLINICAL_STRATEGY)
        self.assertEqual(len(run.final_state.interventions), 1)
        self.assertEqual(len(run.final_state.trials), 1)
        trial = run.final_state.trials[0]
        self.assertEqual(trial.attributes["corroborating_source_count"], 2)
        self.assertEqual(trial.attributes["independent_trial_count"], 1)
        self.assertTrue(trial.attributes["shared_trial_lineage"])
        self.assertEqual(
            run.promotions[0].code,
            "pinned_clinical_lack_of_efficacy_promoted",
        )
        self.assertEqual(
            {item.source.source_id for item in run.final_state.evidence[-3:]},
            {
                "clinicaltrials-gov-NCT00000002",
                "ncbi-pubmed-99999991",
            },
        )

    def test_incomplete_pair_defers_without_partial_updates(self) -> None:
        manifest = disposition_manifest()
        manifest["records"].pop()
        run = run_manifest(manifest, program_id="incomplete-clinical")

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.interventions, ())
        self.assertEqual(run.final_state.trials, ())
        self.assertEqual(run.final_state.evidence, run.initial_state.evidence)
        self.assertEqual(run.promotions[0].code, "outcome_not_successful")

    def test_protocol_mismatch_and_source_collision_fail_closed(self) -> None:
        protocol_mismatch = disposition_manifest()
        protocol_mismatch["records"][1]["biological_context"][
            "protocol_id"
        ] = "OTHER-PROTOCOL"
        source_collision = disposition_manifest()
        source_collision["records"][1]["source"]["content_hash"] = "1" * 64

        cases = (
            (
                "protocol",
                protocol_mismatch,
                "pinned_clinical_disposition_record_mismatch",
            ),
            (
                "source",
                source_collision,
                "pinned_clinical_disposition_source_collision",
            ),
        )
        for label, manifest, code in cases:
            with self.subTest(label=label):
                run = run_manifest(manifest, program_id=f"mismatch-{label}")
                self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
                self.assertEqual(run.final_state.interventions, ())
                self.assertEqual(run.final_state.trials, ())
                self.assertEqual(run.promotions[0].status, PromotionStatus.REJECTED)
                self.assertEqual(run.promotions[0].code, code)

    def test_publication_after_cutoff_is_rejected_atomically(self) -> None:
        run = run_manifest(
            disposition_manifest(),
            program_id="cutoff-clinical",
            state_as_of=date(2024, 7, 1),
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.interventions, ())
        self.assertEqual(run.final_state.trials, ())
        self.assertEqual(
            run.promotions[0].code,
            "pinned_clinical_disposition_after_cutoff",
        )

    def test_same_inputs_replay_to_identical_stage_run(self) -> None:
        first = run_manifest(disposition_manifest(), program_id="replay-clinical")
        second = run_manifest(disposition_manifest(), program_id="replay-clinical")

        self.assertEqual(first.to_dict(), second.to_dict())


if __name__ == "__main__":
    unittest.main()
