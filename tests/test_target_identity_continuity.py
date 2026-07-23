from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from adapters.execution_registry import register_existing_adapters
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EpisodeArm,
    EpisodeMatchKey,
    FailureCause,
    EvidenceEvent,
    EvidenceRelation,
    GatedDiscoveryEnvironment,
    MatchedEpisodePair,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    SourceReference,
    Stage,
    StagePlan,
    TargetRecord,
    ToolCallSpec,
    ToolRegistry,
    build_default_semantic_mapper_registry,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    target_record_from_dict,
)


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
PACKET_AT = REQUEST_AT + timedelta(minutes=2)
ROOT = Path(__file__).resolve().parents[1]


def target_record(
    *,
    target_id: str = "ENSG_TEST1",
    symbol: str = "TEST1",
    chembl_target: str | None = None,
) -> TargetRecord:
    identifiers = {"ensembl_gene": target_id, "gene_symbol": symbol}
    if chembl_target is not None:
        identifiers["chembl_target"] = chembl_target
    return TargetRecord(
        target_id=target_id,
        symbol=symbol,
        disease_id="MONDO_TEST",
        organism="Homo sapiens",
        stage=(
            Stage.MODALITY_SELECTION
            if chembl_target is not None
            else Stage.TARGET_NOMINATION
        ),
        identifiers=identifiers,
    )


def state(
    program_id: str,
    *,
    stage: Stage = Stage.MODALITY_SELECTION,
    targets: tuple[TargetRecord, ...] | None = None,
) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id=f"{program_id}:preloaded-disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="test-disease-identity",
            source_version="fixture-v1",
            locator="fixture://tests/target-continuity/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Target identity must remain continuous across stages.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
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
        targets=targets if targets is not None else (target_record(),),
    )


def defer_packet(
    current_state: ProgramState,
    *,
    packet_id: str,
    target_updates: tuple[TargetRecord, ...] = (),
    candidate_updates: tuple[CandidateRecord, ...] = (),
) -> DecisionPacket:
    return DecisionPacket(
        packet_id=packet_id,
        program_id=current_state.program_id,
        expected_state_version=current_state.version,
        stage=current_state.current_stage,
        decision=Decision.DEFER,
        rationale="Exercise target identity continuity independently of stage readiness.",
        confidence=0.9,
        target_updates=target_updates,
        candidate_updates=candidate_updates,
        created_at=PACKET_AT,
    )


class FakeChembl:
    def __init__(self, gene_symbol: str) -> None:
        self.gene_symbol = gene_symbol

    def molecule(self, chembl_id=None, name=None):
        return {
            "found": True,
            "chembl_id": chembl_id,
            "name": "Test Drug",
            "type": "Small molecule",
            "max_phase": 2,
            "first_approval": None,
        }

    def mechanism(self, chembl_id):
        return [
            {
                "moa": "TEST1 inhibitor",
                "target": "CHEMBL_TARGET",
                "action": "INHIBITOR",
            }
        ]

    def target(self, target_id):
        return {
            "found": True,
            "target_id": target_id,
            "preferred_name": "Test target",
            "target_type": "SINGLE PROTEIN",
            "organism": "Homo sapiens",
            "gene_symbols": [self.gene_symbol],
            "accessions": ["P00001"],
        }


def modality_run(program_id: str, *, gene_symbol: str):
    current_state = state(program_id)
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        chembl=FakeChembl(gene_symbol),
    )
    plan = StagePlan(
        plan_id=f"target-continuity-{program_id}",
        stage=Stage.MODALITY_SELECTION,
        calls=(
            ToolCallSpec(
                call_id="mechanism",
                tool_id="chembl",
                operation="molecule_target_mechanism_profile",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Verify ChEMBL target continuity before selecting modality.",
                arguments={
                    "chembl_id": "CHEMBL_TEST",
                    "target_id": "CHEMBL_TARGET",
                    "target_record_id": "ENSG_TEST1",
                },
                max_cost=0.25,
            ),
        ),
        max_steps=1,
        max_total_cost=0.25,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.CANDIDATE_GENERATION,
    )
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: PACKET_AT,
    )
    return runner.run_stage(
        run_id=f"target-continuity-{program_id}",
        state=current_state,
        stage_plan=plan,
        promotion_contexts={
            "mechanism": PromotionContext(
                observed_at=date(2024, 12, 1),
                available_at=date(2024, 12, 2),
                subject="Test Drug",
                object_value="CHEMBL_TARGET",
                confidence=0.9,
                candidate_id="CHEMBL_TEST",
                candidate_name="Test Drug",
                modality="small molecule",
            )
        },
    )


class TargetIdentityContinuityTests(unittest.TestCase):
    def test_machine_example_round_trips_through_the_strict_parser(self) -> None:
        example_path = ROOT / "rl_env/specs/target_identity_record.example.json"
        schema_path = ROOT / "rl_env/specs/target_identity_record.schema.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        parsed = target_record_from_dict(example)

        self.assertEqual(parsed.to_dict(), example)
        self.assertEqual(set(schema["required"]), set(example))
        self.assertTrue(
            set(schema["properties"]["identifiers"]["required"]).issubset(
                example["identifiers"]
            )
        )

    def test_existing_namespace_binding_cannot_be_rebound(self) -> None:
        current_state = state("target-rebind")
        rebound = TargetRecord(
            target_id="ENSG_TEST1",
            symbol="TEST1",
            disease_id="MONDO_TEST",
            organism="Homo sapiens",
            stage=Stage.MODALITY_SELECTION,
            identifiers={"ensembl_gene": "ENSG_OTHER", "gene_symbol": "TEST1"},
        )

        result = GatedDiscoveryEnvironment().transition(
            current_state,
            defer_packet(
                current_state,
                packet_id="target-rebind-packet",
                target_updates=(rebound,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("target_identity_continuity_invalid", result.reason)

    def test_two_targets_cannot_claim_the_same_namespace_binding(self) -> None:
        first = target_record(chembl_target="CHEMBL_TARGET")
        second = target_record(target_id="ENSG_TEST2", symbol="TEST2")
        current_state = state(
            "target-collision",
            targets=(first, second),
        )
        colliding_second = TargetRecord(
            target_id=second.target_id,
            symbol=second.symbol,
            disease_id=second.disease_id,
            organism=second.organism,
            stage=Stage.MODALITY_SELECTION,
            identifiers={
                **dict(second.identifiers),
                "chembl_target": "CHEMBL_TARGET",
            },
        )

        result = GatedDiscoveryEnvironment().transition(
            current_state,
            defer_packet(
                current_state,
                packet_id="target-collision-packet",
                target_updates=(colliding_second,),
            ),
        )

        self.assertFalse(result.applied)
        continuity = next(
            item
            for item in result.verifier_results
            if item.verifier_id == "target_identity_continuity"
        )
        self.assertIn("target_namespace_collision", continuity.details["failures"])

    def test_target_update_must_be_authored_at_the_current_stage(self) -> None:
        current_state = state("target-stage-mismatch")
        stale_stage_update = TargetRecord(
            target_id="ENSG_TEST1",
            symbol="TEST1",
            disease_id="MONDO_TEST",
            organism="Homo sapiens",
            stage=Stage.TARGET_NOMINATION,
            identifiers={
                "ensembl_gene": "ENSG_TEST1",
                "gene_symbol": "TEST1",
                "chembl_target": "CHEMBL_TARGET",
            },
        )

        result = GatedDiscoveryEnvironment().transition(
            current_state,
            defer_packet(
                current_state,
                packet_id="target-stage-mismatch-packet",
                target_updates=(stale_stage_update,),
            ),
        )

        self.assertFalse(result.applied)
        continuity = next(
            item
            for item in result.verifier_results
            if item.verifier_id == "target_identity_continuity"
        )
        self.assertIn(
            "target_update_stage_mismatch:ENSG_TEST1",
            continuity.details["failures"],
        )

    def test_candidate_link_must_resolve_to_the_same_target_record(self) -> None:
        current_state = state(
            "candidate-broken-link",
            stage=Stage.CANDIDATE_GENERATION,
            targets=(target_record(chembl_target="CHEMBL_TARGET"),),
        )
        candidate = CandidateRecord(
            candidate_id="CHEMBL_TEST",
            name="Test Drug",
            modality="small molecule",
            stage=Stage.CANDIDATE_GENERATION,
            attributes={
                "target_record_id": "ENSG_TEST1",
                "target_chembl_id": "CHEMBL_OTHER",
                "target_symbol": "TEST1",
                "disease_id": "MONDO_TEST",
            },
        )

        result = GatedDiscoveryEnvironment().transition(
            current_state,
            defer_packet(
                current_state,
                packet_id="candidate-broken-link-packet",
                candidate_updates=(candidate,),
            ),
        )

        self.assertFalse(result.applied)
        continuity = next(
            item
            for item in result.verifier_results
            if item.verifier_id == "target_identity_continuity"
        )
        self.assertEqual(
            continuity.details["broken_candidate_ids"],
            ("CHEMBL_TEST",),
        )

    def test_symbol_match_and_mismatch_form_a_matched_evaluation_pair(self) -> None:
        success_run = modality_run("identity-success", gene_symbol="TEST1")
        failure_run = modality_run("identity-failure", gene_symbol="OTHER1")

        self.assertEqual(success_run.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(
            success_run.final_state.current_stage,
            Stage.CANDIDATE_GENERATION,
        )
        self.assertEqual(
            success_run.final_state.targets[0].identifiers["chembl_target"],
            "CHEMBL_TARGET",
        )
        self.assertEqual(failure_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(failure_run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(
            failure_run.promotions[0].code,
            "chembl_target_symbol_mismatch",
        )
        self.assertNotIn(
            "chembl_target",
            failure_run.final_state.targets[0].identifiers,
        )

        key = EpisodeMatchKey(
            disease="test disease",
            stage=Stage.MODALITY_SELECTION,
            modality="small molecule",
            population="not applicable",
            endpoint_family="target identity continuity",
            target_or_mechanism="CHEMBL_TARGET",
            decision_time_bin="2020-2025",
        )
        pair = MatchedEpisodePair(
            pair_id="target-symbol-continuity-pair",
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="target-symbol-success",
                pair_id="target-symbol-continuity-pair",
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="CHEMBL_TARGET",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="target-symbol-visible-success",
                evaluator_label_id="target-symbol-label-success",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="target-symbol-failure",
                pair_id="target-symbol-continuity-pair",
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="CHEMBL_TARGET",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="target-symbol-visible-failure",
                evaluator_label_id="target-symbol-label-failure",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.MECHANISM_OR_CONTEXT,),
            ),
        )

        score = evaluate_matched_pair(pair)
        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)


if __name__ == "__main__":
    unittest.main()
