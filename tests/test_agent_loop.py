from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    Decision,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    PlanningStatus,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    ReplayBundle,
    SourceReference,
    Stage,
    StagePlan,
    ToolCallSpec,
    ToolContract,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
    build_default_semantic_mapper_registry,
    replay_program,
)
from agentic_drug_discovery.bounded_demo import build_bounded_demo_report


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
PACKET_AT = REQUEST_AT + timedelta(minutes=2)


def make_state(
    *,
    stage: Stage = Stage.TARGET_NOMINATION,
    budget_limit: float = 2.0,
) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id=f"{stage.value}:preloaded-disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="test-disease-identity",
            source_version="fixture-v1",
            locator="fixture://tests/agent-loop/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id=f"bounded-program-{stage.value}",
        disease="test disease",
        therapeutic_hypothesis="Bounded tool evidence can update a typed program.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=budget_limit),
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


def target_contract() -> ToolContract:
    return ToolContract(
        tool_id="opentargets",
        operation="target_disease_association",
        action_type=ActionType.QUERY_DATABASE,
        description="Return a target-disease association record.",
        allowed_stages=(Stage.TARGET_NOMINATION,),
        required_arguments=("symbol", "disease_efo"),
        default_cost=0.1,
    )


def target_call(call_id: str, symbol: str = "TEST1") -> ToolCallSpec:
    return ToolCallSpec(
        call_id=call_id,
        tool_id="opentargets",
        operation="target_disease_association",
        action_type=ActionType.QUERY_DATABASE,
        purpose="Retrieve target-disease evidence.",
        arguments={"symbol": symbol, "disease_efo": "MONDO_TEST"},
        max_cost=0.1,
    )


def target_plan(*calls: ToolCallSpec) -> StagePlan:
    return StagePlan(
        plan_id="target-stage-plan",
        stage=Stage.TARGET_NOMINATION,
        calls=calls or (target_call("association"),),
        max_steps=max(1, len(calls)),
        max_total_cost=0.2,
        success_confidence=0.9,
        failure_confidence=0.95,
        success_decision=Decision.ADVANCE,
        failure_decision=Decision.DEFER,
        next_stage=Stage.MODALITY_SELECTION,
    )


def context(
    subject: str = "TEST1", object_value: str = "test disease"
) -> PromotionContext:
    return PromotionContext(
        observed_at=date(2024, 12, 1),
        available_at=date(2024, 12, 2),
        subject=subject,
        object_value=object_value,
        confidence=0.9,
    )


def association_payload(
    arguments: dict,
    *,
    score: float,
    disease: str = "test disease",
) -> dict:
    return {
        "target": arguments["symbol"],
        "target_id": f"ENSG_{arguments['symbol']}",
        "disease": disease,
        "disease_efo": arguments["disease_efo"],
        "organism": "Homo sapiens",
        "found": True,
        "score": score,
        "rank": 1,
        "datatypes": {"genetic_association": 0.88},
    }


def runner(registry: ToolRegistry) -> BoundedStageRunner:
    return BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: PACKET_AT,
    )


class BoundedAgentLoopTests(unittest.TestCase):
    def test_public_bounded_demo_advances_with_typed_target_identity(self) -> None:
        report = build_bounded_demo_report()

        self.assertEqual(report["decision"], "advance")
        self.assertEqual(report["stage_after"], "modality_selection")
        self.assertEqual(
            report["evidence_predicates"],
            ["target_identity_resolved", "target_disease_supported"],
        )
        self.assertEqual(report["disease_ids"], ["MONDO_0011382"])
        self.assertEqual(report["target_ids"], ["ENSG00000119866"])

    def test_missing_promotion_context_blocks_before_invocation(self) -> None:
        state = make_state()
        invocation_count = 0
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)

        def handler(arguments):
            nonlocal invocation_count
            invocation_count += 1
            return ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={"target": arguments["symbol"]},
            )

        registry.register(target_contract(), handler)
        run = runner(registry).run_stage(
            run_id="target-context-missing",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={},
        )

        self.assertEqual(run.status.value, "planning_blocked")
        self.assertEqual(run.code, "promotion_context_missing")
        self.assertEqual(invocation_count, 0)
        self.assertEqual(run.outcomes, ())
        self.assertEqual(run.execution_ledger.outcomes, ())

    def test_future_promotion_context_blocks_before_invocation(self) -> None:
        state = make_state()
        invocation_count = 0
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)

        def handler(arguments):
            nonlocal invocation_count
            invocation_count += 1
            return ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={"target": arguments["symbol"]},
            )

        registry.register(target_contract(), handler)
        future_context = PromotionContext(
            observed_at=date(2025, 1, 2),
            available_at=date(2025, 1, 3),
            subject="TEST1",
            object_value="test disease",
            confidence=0.9,
        )
        run = runner(registry).run_stage(
            run_id="target-context-after-cutoff",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": future_context},
        )

        self.assertEqual(run.status.value, "planning_blocked")
        self.assertEqual(run.code, "promotion_context_after_cutoff")
        self.assertEqual(invocation_count, 0)
        self.assertEqual(run.execution_ledger.outcomes, ())

    def test_target_association_advances_and_replays(self) -> None:
        state = make_state()
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload=association_payload(arguments, score=0.91),
                execution_mode=ExecutionMode.CACHE,
            ),
        )

        run = runner(registry).run_stage(
            run_id="target-success",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": context()},
        )

        self.assertEqual(run.status.value, "committed")
        self.assertEqual(run.final_state.current_stage, Stage.MODALITY_SELECTION)
        self.assertEqual(run.final_state.status, ProgramStatus.ACTIVE)
        self.assertEqual(
            {
                item.predicate
                for item in run.final_state.evidence
                if item.stage is Stage.TARGET_NOMINATION
            },
            {"target_identity_resolved", "target_disease_supported"},
        )
        self.assertEqual(
            run.final_state.claims[0].supporting_evidence,
            tuple(
                item.evidence_id
                for item in run.final_state.evidence
                if item.stage is Stage.TARGET_NOMINATION
            ),
        )
        self.assertAlmostEqual(run.final_state.budget.spent, 0.1)
        self.assertEqual(len(run.accepted_packets), 1)
        self.assertEqual(len(run.execution_ledger.outcomes), 1)
        self.assertEqual(
            run.accepted_packets[0].metadata["stage_plan_metadata"],
            {},
        )
        self.assertIn("plan_result", json.dumps(run.to_dict(), sort_keys=True))

        bundle = ReplayBundle(
            initial_state=state,
            packets=run.accepted_packets,
            tool_execution_ledger=run.execution_ledger,
        )
        replayed = replay_program(bundle)
        self.assertEqual(replayed.final_state, run.final_state)

    def test_low_association_score_is_contextual_and_defers(self) -> None:
        state = make_state()
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload=association_payload(arguments, score=0.2),
                execution_mode=ExecutionMode.CACHE,
            ),
        )

        run = runner(registry).run_stage(
            run_id="target-low-score",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": context()},
        )

        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(run.final_state.current_stage, Stage.TARGET_NOMINATION)
        self.assertEqual(
            [
                item
                for item in run.final_state.evidence
                if item.stage is Stage.TARGET_NOMINATION
            ][0].relation,
            EvidenceRelation.CONTEXTUALIZES,
        )
        self.assertEqual(run.final_state.claims, ())
        self.assertEqual(
            run.accepted_packets[0].decision,
            Decision.DEFER,
        )

    def test_unresolved_association_defers_without_malformed_payload_claim(self) -> None:
        state = make_state()
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "target": arguments["symbol"],
                    "disease": "test disease",
                    "disease_efo": arguments["disease_efo"],
                    "organism": "Homo sapiens",
                    "found": False,
                    "score": None,
                    "evidence_status": "not_found_in_loaded_page",
                },
                execution_mode=ExecutionMode.CACHE,
            ),
        )

        run = runner(registry).run_stage(
            run_id="target-unresolved",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": context()},
        )

        self.assertEqual(
            run.promotions[0].code,
            "opentargets_association_unresolved",
        )
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertFalse(
            any(
                item.stage is Stage.TARGET_NOMINATION
                for item in run.final_state.evidence
            )
        )

    def test_target_disease_context_mismatch_is_not_promoted(self) -> None:
        state = make_state()
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload=association_payload(
                    arguments, score=0.91, disease="different disease"
                ),
                execution_mode=ExecutionMode.CACHE,
            ),
        )

        run = runner(registry).run_stage(
            run_id="target-disease-mismatch",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": context()},
        )

        self.assertEqual(run.promotions[0].code, "opentargets_disease_mismatch")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertFalse(
            any(
                item.stage is Stage.TARGET_NOMINATION
                for item in run.final_state.evidence
            )
        )

    def test_required_unavailable_stops_remaining_calls_and_defers(self) -> None:
        state = make_state()
        invocation_count = 0
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)

        def unavailable(arguments):
            nonlocal invocation_count
            invocation_count += 1
            return ToolResponse(
                status=ToolStatus.UNAVAILABLE,
                payload={"target": arguments["symbol"]},
                execution_mode=ExecutionMode.CACHE,
                error_code="dataset_unavailable",
            )

        registry.register(target_contract(), unavailable)
        plan = target_plan(
            target_call("primary", "TEST1"),
            target_call("backup", "TEST2"),
        )

        run = runner(registry).run_stage(
            run_id="target-unavailable",
            state=state,
            stage_plan=plan,
            promotion_contexts={
                "primary": context("TEST1"),
                "backup": context("TEST2"),
            },
        )

        self.assertEqual(invocation_count, 1)
        self.assertEqual(len(run.outcomes), 1)
        self.assertEqual(run.outcomes[0].status, ToolStatus.UNAVAILABLE)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertFalse(
            any(
                item.stage is Stage.TARGET_NOMINATION
                for item in run.final_state.evidence
            )
        )
        self.assertEqual(
            run.accepted_packets[0].metadata["executed_call_ids"],
            ("primary",),
        )

    def test_planner_blocks_required_batch_before_budget_is_spent(self) -> None:
        state = make_state(budget_limit=0.05)
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={"target": arguments["symbol"]},
            ),
        )

        result = BoundedPlanner(clock=lambda: REQUEST_AT).plan(
            state,
            target_plan(),
            registry,
        )

        self.assertEqual(result.status, PlanningStatus.BLOCKED)
        self.assertEqual(result.code, "required_execution_budget_exceeded")
        self.assertEqual(result.requests, ())
        self.assertEqual(state.budget.spent, 0.0)

    def test_soft_boltz_evidence_cannot_satisfy_candidate_gate(self) -> None:
        state = make_state(stage=Stage.CANDIDATE_GENERATION)
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            ToolContract(
                tool_id="boltz2",
                operation="predict_binding",
                action_type=ActionType.RUN_SFM,
                description="Return a structured binding prediction.",
                allowed_stages=(Stage.CANDIDATE_GENERATION,),
                required_arguments=("spec",),
                default_cost=1.0,
            ),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "status": "predicted",
                    "target": "TEST1",
                    "ligand": "CCO",
                    "affinity": 0.7,
                    "affinity_units": "service-defined",
                    "confidence": 0.8,
                    "iptm": 0.75,
                },
                execution_mode=ExecutionMode.LIVE,
            ),
        )
        plan = StagePlan(
            plan_id="boltz-soft-plan",
            stage=Stage.CANDIDATE_GENERATION,
            calls=(
                ToolCallSpec(
                    call_id="binding",
                    tool_id="boltz2",
                    operation="predict_binding",
                    action_type=ActionType.RUN_SFM,
                    purpose="Use binding prediction as a soft prefilter.",
                    arguments={"spec": "TEST1|CCO"},
                    max_cost=1.0,
                ),
            ),
            max_steps=1,
            max_total_cost=1.0,
            success_confidence=0.8,
            failure_confidence=0.95,
            next_stage=Stage.LEAD_OPTIMIZATION,
        )
        bounded_runner = BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=lambda: REQUEST_AT),
            clock=lambda: PACKET_AT,
        )

        run = bounded_runner.run_stage(
            run_id="boltz-soft-only",
            state=state,
            stage_plan=plan,
            promotion_contexts={
                "binding": PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="candidate-1",
                    object_value="TEST1",
                    confidence=0.8,
                )
            },
        )

        self.assertTrue(run.recovered_to_defer)
        self.assertEqual(len(run.attempted_packets), 2)
        self.assertEqual(run.attempted_packets[0].decision, Decision.ADVANCE)
        self.assertFalse(run.transition_results[0].applied)
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(
            [
                item
                for item in run.final_state.evidence
                if item.stage is Stage.CANDIDATE_GENERATION
            ][0].predicate,
            "predicted_target_binding",
        )
        self.assertEqual(
            [
                item
                for item in run.final_state.evidence
                if item.stage is Stage.CANDIDATE_GENERATION
            ][0].relation,
            EvidenceRelation.CONTEXTUALIZES,
        )
        self.assertEqual(run.final_state.claims, ())

        bundle = ReplayBundle(
            initial_state=state,
            packets=run.accepted_packets,
            tool_execution_ledger=run.execution_ledger,
        )
        self.assertEqual(replay_program(bundle).final_state, run.final_state)

    def test_retry_planner_clock_cannot_predate_last_accepted_packet(self) -> None:
        state = make_state()
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            target_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload=association_payload(arguments, score=0.2),
                execution_mode=ExecutionMode.CACHE,
            ),
        )
        first_run = runner(registry).run_stage(
            run_id="target-first-defer",
            state=state,
            stage_plan=target_plan(),
            promotion_contexts={"association": context()},
        )
        retry_plan = StagePlan(
            plan_id="target-retry-plan",
            stage=Stage.TARGET_NOMINATION,
            calls=(target_call("association"),),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.MODALITY_SELECTION,
        )

        result = BoundedPlanner(clock=lambda: REQUEST_AT).plan(
            first_run.final_state,
            retry_plan,
            registry,
            execution_ledger=first_run.execution_ledger,
        )

        self.assertEqual(result.status, PlanningStatus.BLOCKED)
        self.assertEqual(result.code, "required_request_preflight_failed")
        self.assertIn(
            "request_predates_last_decision",
            result.details["failures"],
        )


if __name__ == "__main__":
    unittest.main()
