from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedProgramRunner,
    BoundedStageRunner,
    BudgetState,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    ProgramRunStatus,
    ProgramState,
    ProgramStep,
    PromotionBinding,
    PromotionContext,
    SourceReference,
    Stage,
    StagePlan,
    ToolCallSpec,
    ToolContract,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
    build_default_semantic_mapper_registry,
    replay_program_run,
)


class TickClock:
    def __init__(self) -> None:
        self.current = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def state() -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id="program-runner:preloaded-disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="test-disease-identity",
            source_version="fixture-v1",
            locator="fixture://tests/program-runner/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id="program-runner-test",
        disease="test disease",
        therapeutic_hypothesis="A bounded program must preserve every decision boundary.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.TARGET_NOMINATION,
        budget=BudgetState(limit=2.0),
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
    )


def target_step(*, plan_stage: Stage = Stage.TARGET_NOMINATION) -> ProgramStep:
    plan = StagePlan(
        plan_id=f"program-target-{plan_stage.value}",
        stage=plan_stage,
        calls=(
            ToolCallSpec(
                call_id="association",
                tool_id="opentargets",
                operation="target_disease_association",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve a target-disease association.",
                arguments={"symbol": "TEST1", "disease_efo": "MONDO_TEST"},
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.MODALITY_SELECTION,
    )
    return ProgramStep(
        stage_plan=plan,
        promotion_bindings=(
            PromotionBinding(
                call_id="association",
                context=PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="TEST1",
                    object_value="test disease",
                    confidence=0.9,
                ),
            ),
        ),
    )


def program_runner(*, association_score: float = 0.9) -> BoundedProgramRunner:
    clock = TickClock()
    registry = ToolRegistry(clock=clock)
    registry.register(
        ToolContract(
            tool_id="opentargets",
            operation="target_disease_association",
            action_type=ActionType.QUERY_DATABASE,
            description="Return one target-disease association.",
            allowed_stages=(Stage.TARGET_NOMINATION,),
            required_arguments=("symbol", "disease_efo"),
            default_cost=0.1,
        ),
        lambda arguments: ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload={
                "target": arguments["symbol"],
                "target_id": "ENSG_TEST1",
                "disease": "test disease",
                "disease_efo": arguments["disease_efo"],
                "organism": "Homo sapiens",
                "found": True,
                "score": association_score,
                "rank": 1,
                "datatypes": {"genetic_association": 0.8},
            },
            execution_mode=ExecutionMode.CACHE,
        ),
    )
    return BoundedProgramRunner(
        stage_runner=BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=clock),
            clock=clock,
        )
    )


class BoundedProgramRunnerTests(unittest.TestCase):
    def test_advance_exhausts_supplied_plan_and_replays_exactly(self) -> None:
        initial = state()
        run = program_runner().run_program(
            run_id="one-step-program",
            state=initial,
            steps=(target_step(),),
        )

        self.assertEqual(run.status, ProgramRunStatus.EXHAUSTED)
        self.assertEqual(run.final_state.current_stage, Stage.MODALITY_SELECTION)
        self.assertEqual(run.final_state.version, 1)
        self.assertEqual(len(run.accepted_packets), 1)
        self.assertEqual(len(run.execution_ledger.outcomes), 1)
        self.assertEqual(replay_program_run(run).final_state, run.final_state)
        self.assertEqual(run.replay_bundle.packets, run.accepted_packets)

    def test_mismatched_followup_stage_blocks_without_losing_prior_advance(self) -> None:
        initial = state()
        mismatched = target_step(plan_stage=Stage.CANDIDATE_GENERATION)
        run = program_runner().run_program(
            run_id="blocked-followup-program",
            state=initial,
            steps=(target_step(), mismatched),
        )

        self.assertEqual(run.status, ProgramRunStatus.BLOCKED)
        self.assertEqual(run.final_state.current_stage, Stage.MODALITY_SELECTION)
        self.assertEqual(run.final_state.version, 1)
        self.assertEqual(len(run.stage_runs), 2)
        self.assertEqual(run.stage_runs[-1].code, "stage_plan_context_mismatch")
        self.assertEqual(len(run.execution_ledger.outcomes), 1)
        self.assertEqual(replay_program_run(run).final_state, run.final_state)

    def test_defer_pauses_before_any_followup_plan(self) -> None:
        initial = state()
        run = program_runner(association_score=0.2).run_program(
            run_id="deferred-program",
            state=initial,
            steps=(
                target_step(),
                target_step(plan_stage=Stage.CANDIDATE_GENERATION),
            ),
        )

        self.assertEqual(run.status, ProgramRunStatus.PAUSED)
        self.assertEqual(run.code, "program_paused_on_defer")
        self.assertEqual(run.final_state.current_stage, Stage.TARGET_NOMINATION)
        self.assertEqual(run.final_state.status.value, "deferred")
        self.assertEqual(len(run.stage_runs), 1)
        self.assertEqual(len(run.execution_ledger.outcomes), 1)
        self.assertEqual(replay_program_run(run).final_state, run.final_state)

    def test_program_step_rejects_binding_for_unknown_call(self) -> None:
        valid = target_step()
        with self.assertRaisesRegex(ValueError, "unknown stage-plan calls"):
            ProgramStep(
                stage_plan=valid.stage_plan,
                promotion_bindings=(
                    PromotionBinding(
                        call_id="unknown",
                        context=valid.promotion_bindings[0].context,
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
