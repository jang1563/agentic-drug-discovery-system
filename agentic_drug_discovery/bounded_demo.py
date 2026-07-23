"""Dependency-free fixture for the bounded planner-to-transition agent loop."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from .execution import (
    ExecutionMode,
    ToolContract,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
)
from .models import (
    ActionType,
    BudgetState,
    Decision,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ProgramState,
    SourceReference,
    Stage,
)
from .orchestration import BoundedStageRunner, StageRun, StageRunStatus
from .planning import BoundedPlanner, StagePlan, ToolCallSpec
from .promotion import PromotionContext, build_default_semantic_mapper_registry


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
PACKET_AT = REQUEST_AT + timedelta(minutes=2)


def run_bounded_target_demo() -> StageRun:
    """Run one deterministic target-nomination fixture through the real agent loop."""

    disease_evidence = EvidenceEvent(
        evidence_id="bounded-target-demo:disease-identity",
        stage=Stage.DISEASE_CONTEXT,
        subject="sickle cell disease",
        predicate="disease_context_resolved",
        object_value="MONDO_0011382",
        source=SourceReference(
            source_id="bounded-target-demo-fixture",
            source_version="fixture-v1",
            locator="fixture://bounded-target-demo/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 11, 1),
        available_at=date(2024, 11, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_0011382", "fixture": True},
    )
    state = ProgramState(
        program_id="bounded-target-demo",
        disease="sickle cell disease",
        therapeutic_hypothesis="A target association can be promoted under explicit policy.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.TARGET_NOMINATION,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence,),
        diseases=(
            DiseaseRecord(
                disease_id="MONDO_0011382",
                name="sickle cell disease",
                stage=Stage.DISEASE_CONTEXT,
                identifiers={"canonical": "MONDO_0011382"},
                supporting_evidence=(disease_evidence.evidence_id,),
                attributes={"fixture": True},
            ),
        ),
    )
    registry = ToolRegistry(clock=lambda: COMPLETED_AT)
    registry.register(
        ToolContract(
            tool_id="opentargets",
            operation="target_disease_association",
            action_type=ActionType.QUERY_DATABASE,
            description="Return a deterministic Open Targets-shaped fixture record.",
            allowed_stages=(Stage.TARGET_NOMINATION,),
            required_arguments=("symbol", "disease_efo"),
            default_cost=0.1,
        ),
        lambda arguments: ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload={
                "target": arguments["symbol"],
                "target_id": "ENSG00000119866",
                "disease": "sickle cell disease",
                "disease_efo": arguments["disease_efo"],
                "organism": "Homo sapiens",
                "found": True,
                "score": 0.91,
                "rank": 1,
                "datatypes": {"fixture": 0.91},
            },
            execution_mode=ExecutionMode.CACHE,
            message="Deterministic non-benchmark fixture completed.",
        ),
    )
    mapper_registry = build_default_semantic_mapper_registry(
        target_association_minimum_score=0.5
    )
    plan = StagePlan(
        plan_id="bounded-target-demo-plan",
        stage=Stage.TARGET_NOMINATION,
        calls=(
            ToolCallSpec(
                call_id="association",
                tool_id="opentargets",
                operation="target_disease_association",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Exercise bounded target evidence promotion.",
                arguments={
                    "symbol": "BCL11A",
                    "disease_efo": "MONDO_0011382",
                },
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        success_decision=Decision.ADVANCE,
        failure_decision=Decision.DEFER,
        next_stage=Stage.MODALITY_SELECTION,
        metadata={"fixture": True, "non_benchmark": True},
    )
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=mapper_registry,
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: PACKET_AT,
    )
    run = runner.run_stage(
        run_id="bounded-target-demo-run",
        state=state,
        stage_plan=plan,
        promotion_contexts={
            "association": PromotionContext(
                observed_at=date(2024, 12, 1),
                available_at=date(2024, 12, 2),
                subject="BCL11A",
                object_value="sickle cell disease",
                confidence=0.9,
                metadata={"fixture": True, "non_benchmark": True},
            )
        },
    )
    if run.status is not StageRunStatus.COMMITTED:
        raise RuntimeError("bounded target demo did not commit")
    return run


def build_bounded_demo_report(*, full_state: bool = False) -> dict[str, Any]:
    run = run_bounded_target_demo()
    accepted = run.accepted_packets
    report: dict[str, Any] = {
        "fixture": True,
        "non_benchmark": True,
        "plan_status": run.plan_result.status.value,
        "run_status": run.status.value,
        "decision": accepted[-1].decision.value,
        "stage_before": run.initial_state.current_stage.value,
        "stage_after": run.final_state.current_stage.value,
        "program_status": run.final_state.status.value,
        "accepted_packet_count": len(accepted),
        "evidence_predicates": [
            item.predicate
            for item in run.final_state.evidence
            if item.stage is run.initial_state.current_stage
        ],
        "disease_ids": [item.disease_id for item in run.final_state.diseases],
        "target_ids": [item.target_id for item in run.final_state.targets],
        "tool_statuses": [item.status.value for item in run.outcomes],
        "execution_ledger_cost": run.execution_ledger.total_cost,
        "recovered_to_defer": run.recovered_to_defer,
    }
    if full_state:
        report["stage_run"] = run.to_dict()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-state", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build_bounded_demo_report(full_state=args.full_state), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
