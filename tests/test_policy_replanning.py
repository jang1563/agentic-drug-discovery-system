from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedProgramRunner,
    BoundedReplanPolicy,
    BoundedStageRunner,
    BudgetState,
    CheckpointDisposition,
    Decision,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    PolicyDrivenProgramRunner,
    PolicyProgramRunStatus,
    ProgramRunStatus,
    ProgramState,
    ProgramStep,
    PromotionBinding,
    PromotionContext,
    RecordParseError,
    ReplanAction,
    ReplanRule,
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
    policy_checkpoint_from_dict,
    policy_checkpoint_from_json,
    policy_checkpoint_to_dict,
    policy_checkpoint_to_json,
    replay_program,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_SCHEMA = ROOT / "rl_env/specs/policy_checkpoint.schema.json"


class TickClock:
    def __init__(self) -> None:
        self.current = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def initial_state() -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id="policy-test:preloaded-disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="policy-test-disease",
            source_version="fixture-v1",
            locator="fixture://tests/policy/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id="policy-replan-test",
        disease="test disease",
        therapeutic_hypothesis="Typed replanning must remain replayable.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.TARGET_NOMINATION,
        budget=BudgetState(limit=3.0),
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


def target_step(plan_id: str, symbol: str) -> ProgramStep:
    return ProgramStep(
        stage_plan=StagePlan(
            plan_id=plan_id,
            stage=Stage.TARGET_NOMINATION,
            calls=(
                ToolCallSpec(
                    call_id="association",
                    tool_id="opentargets",
                    operation="target_disease_association",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Resolve a target-disease association.",
                    arguments={"symbol": symbol, "disease_efo": "MONDO_TEST"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.MODALITY_SELECTION,
        ),
        promotion_bindings=(
            PromotionBinding(
                call_id="association",
                context=PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject=symbol,
                    object_value="test disease",
                    confidence=0.9,
                ),
            ),
        ),
    )


def policy_runner(
    *,
    fallback_plan_id: str = "secondary-target-plan",
    fallback_symbol: str = "SECONDARY",
) -> PolicyDrivenProgramRunner:
    clock = TickClock()
    registry = ToolRegistry(clock=clock)
    registry.register(
        ToolContract(
            tool_id="opentargets",
            operation="target_disease_association",
            action_type=ActionType.QUERY_DATABASE,
            description="Return a deterministic target-disease association.",
            allowed_stages=(Stage.TARGET_NOMINATION,),
            required_arguments=("symbol", "disease_efo"),
            default_cost=0.1,
        ),
        lambda arguments: ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload={
                "target": arguments["symbol"],
                "target_id": f"ENSG_{arguments['symbol']}",
                "disease": "test disease",
                "disease_efo": arguments["disease_efo"],
                "organism": "Homo sapiens",
                "found": True,
                "score": 0.2 if arguments["symbol"] == "PRIMARY" else 0.9,
                "rank": 1,
                "datatypes": {"genetic_association": 0.8},
            },
            execution_mode=ExecutionMode.CACHE,
        ),
    )
    program_runner = BoundedProgramRunner(
        stage_runner=BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=clock),
            clock=clock,
        )
    )
    policy = BoundedReplanPolicy(
        policy_id="typed-target-recovery",
        version="1",
        rules=(
            ReplanRule(
                rule_id="defer-to-secondary-target",
                stage=Stage.TARGET_NOMINATION,
                run_statuses=(ProgramRunStatus.PAUSED,),
                action=ReplanAction.REPLAN,
                replacement_steps=(
                    target_step(fallback_plan_id, fallback_symbol),
                ),
                trigger_codes=("program_paused_on_defer",),
                decisions=(Decision.DEFER,),
                preserve_pending=True,
                max_applications=1,
            ),
        ),
        max_replans=1,
    )
    return PolicyDrivenProgramRunner(
        program_runner=program_runner,
        policy=policy,
    )


class PolicyReplanningTests(unittest.TestCase):
    def test_checkpoint_envelope_validates_public_json_schema(self) -> None:
        runner = policy_runner()
        checkpoint = runner.start_checkpoint(
            checkpoint_id="schema-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )
        schema = json.loads(CHECKPOINT_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)

        self.assertEqual(
            list(validator.iter_errors(policy_checkpoint_to_dict(checkpoint))),
            [],
        )

    def test_defer_replans_to_predeclared_fallback_and_replays(self) -> None:
        state = initial_state()
        runner = policy_runner()
        checkpoint = runner.start_checkpoint(
            checkpoint_id="initial-policy-checkpoint",
            state=state,
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )

        run = runner.run(
            run_id="defer-then-replan",
            checkpoint=checkpoint,
            expected_checkpoint_fingerprint=checkpoint.fingerprint,
            max_invocations=2,
        )

        self.assertEqual(run.status, PolicyProgramRunStatus.EXHAUSTED)
        self.assertEqual(
            run.final_checkpoint.disposition,
            CheckpointDisposition.EXHAUSTED,
        )
        self.assertEqual(run.final_checkpoint.state.version, 2)
        self.assertEqual(
            run.final_checkpoint.state.current_stage,
            Stage.MODALITY_SELECTION,
        )
        self.assertEqual(len(run.segments), 2)
        self.assertEqual(run.segments[0].status, ProgramRunStatus.PAUSED)
        self.assertEqual(run.segments[1].status, ProgramRunStatus.EXHAUSTED)
        self.assertEqual(len(run.final_checkpoint.replan_history), 1)
        self.assertEqual(
            run.final_checkpoint.replan_history[0].directive.action,
            ReplanAction.REPLAN,
        )
        self.assertEqual(len(run.final_checkpoint.execution_ledger.outcomes), 2)
        packets = tuple(
            packet for segment in run.segments for packet in segment.accepted_packets
        )
        replay = replay_program(
            ReplayBundle(
                initial_state=state,
                packets=packets,
                tool_execution_ledger=run.final_checkpoint.execution_ledger,
            )
        )
        self.assertEqual(replay.final_state, run.final_checkpoint.state)

    def test_hash_bound_checkpoint_round_trip_resumes_exactly(self) -> None:
        runner = policy_runner()
        checkpoint = runner.start_checkpoint(
            checkpoint_id="resume-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )
        first = runner.run(
            run_id="resume-part-one",
            checkpoint=checkpoint,
            expected_checkpoint_fingerprint=checkpoint.fingerprint,
            max_invocations=1,
        )
        self.assertEqual(first.status, PolicyProgramRunStatus.PAUSED)
        self.assertEqual(
            first.final_checkpoint.disposition,
            CheckpointDisposition.READY,
        )
        self.assertEqual(
            first.final_checkpoint.pending_steps[0].stage_plan.plan_id,
            "secondary-target-plan",
        )

        encoded = policy_checkpoint_to_json(first.final_checkpoint)
        restored = policy_checkpoint_from_json(encoded)
        self.assertEqual(restored, first.final_checkpoint)
        self.assertEqual(restored.fingerprint, first.final_checkpoint.fingerprint)

        resumed = runner.run(
            run_id="resume-part-two",
            checkpoint=restored,
            expected_checkpoint_fingerprint=restored.fingerprint,
            max_invocations=1,
        )
        self.assertEqual(resumed.status, PolicyProgramRunStatus.EXHAUSTED)
        self.assertEqual(resumed.final_checkpoint.state.version, 2)
        self.assertEqual(resumed.final_checkpoint.invocation_count, 2)
        self.assertEqual(
            resumed.final_checkpoint.parent_fingerprint,
            restored.fingerprint,
        )

    def test_checkpoint_tampering_and_stale_resume_token_fail_closed(self) -> None:
        runner = policy_runner()
        checkpoint = runner.start_checkpoint(
            checkpoint_id="tamper-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )
        payload = json.loads(policy_checkpoint_to_json(checkpoint))
        payload["checkpoint"]["pending_steps"][0]["stage_plan"]["calls"][0][
            "arguments"
        ]["symbol"] = "TAMPERED"
        with self.assertRaisesRegex(RecordParseError, "integrity hash"):
            policy_checkpoint_from_dict(payload)
        with self.assertRaisesRegex(ValueError, "resume token"):
            runner.run(
                run_id="stale-token",
                checkpoint=checkpoint,
                expected_checkpoint_fingerprint="f" * 64,
                max_invocations=1,
            )

    def test_consumed_plan_id_cannot_be_reintroduced_by_policy(self) -> None:
        runner = policy_runner(fallback_plan_id="primary-target-plan")
        checkpoint = runner.start_checkpoint(
            checkpoint_id="collision-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )

        run = runner.run(
            run_id="collision-run",
            checkpoint=checkpoint,
            expected_checkpoint_fingerprint=checkpoint.fingerprint,
            max_invocations=2,
        )

        self.assertEqual(run.status, PolicyProgramRunStatus.PAUSED)
        self.assertEqual(
            run.final_checkpoint.disposition,
            CheckpointDisposition.PAUSED,
        )
        self.assertEqual(
            run.final_checkpoint.replan_history[-1].directive.reason_code,
            "replacement_plan_id_conflict",
        )
        self.assertEqual(len(run.segments), 1)
        self.assertEqual(len(run.final_checkpoint.execution_ledger.outcomes), 1)

    def test_global_replan_limit_stops_a_repeated_defer_loop(self) -> None:
        runner = policy_runner(fallback_symbol="PRIMARY")
        checkpoint = runner.start_checkpoint(
            checkpoint_id="bounded-loop-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )

        run = runner.run(
            run_id="bounded-loop",
            checkpoint=checkpoint,
            expected_checkpoint_fingerprint=checkpoint.fingerprint,
            max_invocations=3,
        )

        self.assertEqual(run.status, PolicyProgramRunStatus.PAUSED)
        self.assertEqual(len(run.segments), 2)
        self.assertEqual(len(run.final_checkpoint.replan_history), 2)
        self.assertEqual(
            run.final_checkpoint.replan_history[-1].directive.reason_code,
            "global_replan_limit_reached",
        )
        self.assertEqual(len(run.final_checkpoint.execution_ledger.outcomes), 2)

    def test_policy_identity_mismatch_cannot_resume_checkpoint(self) -> None:
        runner = policy_runner()
        checkpoint = runner.start_checkpoint(
            checkpoint_id="policy-identity-initial",
            state=initial_state(),
            steps=(target_step("primary-target-plan", "PRIMARY"),),
        )
        other = PolicyDrivenProgramRunner(
            program_runner=runner.program_runner,
            policy=BoundedReplanPolicy(
                policy_id="other-policy",
                version="1",
                rules=(),
                max_replans=0,
            ),
        )
        with self.assertRaisesRegex(ValueError, "policy identity"):
            other.run(
                run_id="wrong-policy",
                checkpoint=checkpoint,
                expected_checkpoint_fingerprint=checkpoint.fingerprint,
                max_invocations=1,
            )


if __name__ == "__main__":
    unittest.main()
