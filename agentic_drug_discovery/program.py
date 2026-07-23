"""Bounded multi-stage execution with explicit stop and replay semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .environment import GatedDiscoveryEnvironment
from .execution import ToolExecutionLedger
from .models import (
    Decision,
    DecisionPacket,
    ProgramState,
    ProgramStatus,
    SerializableRecord,
    _freeze_mapping,
    _require_instance,
    _require_text,
)
from .orchestration import BoundedStageRunner, StageRun, StageRunStatus
from .planning import StagePlan
from .promotion import PromotionContext
from .serialization import ReplayBundle, ReplayReport, replay_program


class ProgramRunStatus(str, Enum):
    """Terminal state of one bounded program-run invocation."""

    COMPLETED = "completed"
    TERMINATED = "terminated"
    PAUSED = "paused"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class PromotionBinding(SerializableRecord):
    """Bind one declared stage-plan call to its time-sliced semantic context."""

    call_id: str
    context: PromotionContext

    def __post_init__(self) -> None:
        _require_text(self.call_id, "call_id")
        _require_instance(self.context, PromotionContext, "context")


@dataclass(frozen=True, slots=True)
class ProgramStep(SerializableRecord):
    """One stage plan plus explicit promotion contexts for its declared calls."""

    stage_plan: StagePlan
    promotion_bindings: tuple[PromotionBinding, ...]

    def __post_init__(self) -> None:
        _require_instance(self.stage_plan, StagePlan, "stage_plan")
        object.__setattr__(self, "promotion_bindings", tuple(self.promotion_bindings))
        for binding in self.promotion_bindings:
            _require_instance(binding, PromotionBinding, "promotion_bindings item")
        call_ids = tuple(item.call_id for item in self.promotion_bindings)
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("promotion bindings must have unique call_id values")
        known_call_ids = {call.call_id for call in self.stage_plan.calls}
        unknown = sorted(set(call_ids) - known_call_ids)
        if unknown:
            raise ValueError(
                "promotion bindings reference unknown stage-plan calls: "
                + ", ".join(unknown)
            )

    @property
    def promotion_contexts(self) -> dict[str, PromotionContext]:
        return {item.call_id: item.context for item in self.promotion_bindings}


@dataclass(frozen=True, slots=True)
class BoundedProgramRun(SerializableRecord):
    """Auditable result of sequentially applying a bounded set of stage plans."""

    run_id: str
    status: ProgramRunStatus
    code: str
    message: str
    initial_state: ProgramState
    final_state: ProgramState
    steps: tuple[ProgramStep, ...] = ()
    stage_runs: tuple[StageRun, ...] = ()
    initial_execution_ledger: ToolExecutionLedger = ToolExecutionLedger()
    execution_ledger: ToolExecutionLedger = ToolExecutionLedger()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("run_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.status, ProgramRunStatus, "status")
        _require_instance(self.initial_state, ProgramState, "initial_state")
        _require_instance(self.final_state, ProgramState, "final_state")
        _require_instance(
            self.initial_execution_ledger,
            ToolExecutionLedger,
            "initial_execution_ledger",
        )
        _require_instance(
            self.execution_ledger,
            ToolExecutionLedger,
            "execution_ledger",
        )
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "stage_runs", tuple(self.stage_runs))
        for step in self.steps:
            _require_instance(step, ProgramStep, "steps item")
        for stage_run in self.stage_runs:
            _require_instance(stage_run, StageRun, "stage_runs item")
        plan_ids = tuple(step.stage_plan.plan_id for step in self.steps)
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("program steps must have unique plan_id values")
        if len(self.stage_runs) > len(self.steps):
            raise ValueError("stage_runs cannot exceed declared program steps")

        expected_state = self.initial_state
        expected_outcomes = self.initial_execution_ledger.outcomes
        for index, (step, stage_run) in enumerate(
            zip(self.steps, self.stage_runs, strict=False)
        ):
            if stage_run.plan_result.plan_id != step.stage_plan.plan_id:
                raise ValueError(f"stage run {index} does not match its program step")
            if stage_run.initial_state != expected_state:
                raise ValueError(f"stage run {index} breaks the state chain")
            actual_outcomes = stage_run.execution_ledger.outcomes
            if actual_outcomes[: len(expected_outcomes)] != expected_outcomes:
                raise ValueError(f"stage run {index} breaks the execution-ledger chain")
            expected_state = stage_run.final_state
            expected_outcomes = actual_outcomes
            if stage_run.status is StageRunStatus.COMMITTED:
                if len(stage_run.accepted_packets) != 1:
                    raise ValueError("committed stage runs must apply exactly one packet")
            elif stage_run.accepted_packets:
                raise ValueError("non-committed stage runs cannot apply packets")
        if self.final_state != expected_state:
            raise ValueError("final_state must equal the final stage-run state")
        if self.execution_ledger.outcomes != expected_outcomes:
            raise ValueError("execution_ledger must equal the final cumulative ledger")
        foreign_programs = {
            outcome.request.program_id
            for outcome in self.execution_ledger.outcomes
            if outcome.request.program_id != self.initial_state.program_id
        }
        if foreign_programs:
            raise ValueError("execution ledger contains outcomes from another program")

        accepted_packets = self.accepted_packets
        initial_packet_count = len(self.initial_state.packet_history)
        if self.final_state.packet_history[:initial_packet_count] != (
            self.initial_state.packet_history
        ):
            raise ValueError("final state does not preserve initial packet history")
        if self.final_state.packet_history[initial_packet_count:] != accepted_packets:
            raise ValueError("final state packet suffix does not match accepted packets")
        if self.final_state.version != self.initial_state.version + len(accepted_packets):
            raise ValueError("final state version does not match accepted packet count")

        self._validate_status()
        _ = self.replay_bundle
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))

    def _validate_status(self) -> None:
        if self.final_state.status is ProgramStatus.COMPLETED:
            if self.status is not ProgramRunStatus.COMPLETED:
                raise ValueError("completed state requires completed run status")
            return
        if self.final_state.status is ProgramStatus.TERMINATED:
            if self.status is not ProgramRunStatus.TERMINATED:
                raise ValueError("terminated state requires terminated run status")
            return
        if self.status in {ProgramRunStatus.COMPLETED, ProgramRunStatus.TERMINATED}:
            raise ValueError("terminal run status requires a matching terminal state")
        if self.status is ProgramRunStatus.BLOCKED:
            if not self.stage_runs or self.stage_runs[-1].status is StageRunStatus.COMMITTED:
                raise ValueError("blocked program runs require a final blocked stage run")
            return
        if self.status is ProgramRunStatus.PAUSED:
            if not self.stage_runs or self.stage_runs[-1].status is not StageRunStatus.COMMITTED:
                raise ValueError("paused program runs require a committed final stage run")
            if self.stage_runs[-1].accepted_packets[0].decision is Decision.ADVANCE:
                raise ValueError("paused program runs require a non-advance decision")
            return
        if len(self.stage_runs) != len(self.steps):
            raise ValueError("exhausted runs must consume every declared program step")
        if any(item.status is not StageRunStatus.COMMITTED for item in self.stage_runs):
            raise ValueError("exhausted runs cannot contain blocked stage runs")
        if self.stage_runs and (
            self.stage_runs[-1].accepted_packets[0].decision is not Decision.ADVANCE
        ):
            raise ValueError("exhausted runs may stop only after an advance decision")

    @property
    def accepted_packets(self) -> tuple[DecisionPacket, ...]:
        return tuple(
            packet for stage_run in self.stage_runs for packet in stage_run.accepted_packets
        )

    @property
    def replay_bundle(self) -> ReplayBundle:
        return ReplayBundle(
            initial_state=self.initial_state,
            packets=self.accepted_packets,
            tool_execution_ledger=self.execution_ledger,
        )


class BoundedProgramRunner:
    """Execute stage plans in order and stop at the first non-advance outcome."""

    def __init__(self, *, stage_runner: BoundedStageRunner) -> None:
        _require_instance(stage_runner, BoundedStageRunner, "stage_runner")
        self.stage_runner = stage_runner

    def run_program(
        self,
        *,
        run_id: str,
        state: ProgramState,
        steps: tuple[ProgramStep, ...],
        execution_ledger: ToolExecutionLedger = ToolExecutionLedger(),
    ) -> BoundedProgramRun:
        _require_text(run_id, "run_id")
        _require_instance(state, ProgramState, "state")
        _require_instance(execution_ledger, ToolExecutionLedger, "execution_ledger")
        resolved_steps = tuple(steps)
        for step in resolved_steps:
            _require_instance(step, ProgramStep, "steps item")

        initial_state = state
        initial_ledger = execution_ledger
        stage_runs: list[StageRun] = []
        if state.is_terminal:
            status = (
                ProgramRunStatus.COMPLETED
                if state.status is ProgramStatus.COMPLETED
                else ProgramRunStatus.TERMINATED
            )
            return self._build(
                run_id=run_id,
                status=status,
                code="program_already_terminal",
                message="Program state was already terminal; no stage plan was invoked.",
                initial_state=initial_state,
                final_state=state,
                steps=resolved_steps,
                stage_runs=stage_runs,
                initial_execution_ledger=initial_ledger,
                execution_ledger=execution_ledger,
            )

        for index, step in enumerate(resolved_steps, start=1):
            stage_run = self.stage_runner.run_stage(
                run_id=f"{run_id}:step-{index}:{step.stage_plan.plan_id}",
                state=state,
                stage_plan=step.stage_plan,
                promotion_contexts=step.promotion_contexts,
                execution_ledger=execution_ledger,
            )
            stage_runs.append(stage_run)
            execution_ledger = stage_run.execution_ledger
            state = stage_run.final_state
            if stage_run.status is not StageRunStatus.COMMITTED:
                return self._build(
                    run_id=run_id,
                    status=ProgramRunStatus.BLOCKED,
                    code="program_stage_blocked",
                    message="Program execution stopped at a fail-closed stage boundary.",
                    initial_state=initial_state,
                    final_state=state,
                    steps=resolved_steps,
                    stage_runs=stage_runs,
                    initial_execution_ledger=initial_ledger,
                    execution_ledger=execution_ledger,
                    details={
                        "step_index": index,
                        "stage_run_status": stage_run.status.value,
                        "stage_run_code": stage_run.code,
                    },
                )

            decision = stage_run.accepted_packets[0].decision
            if state.status is ProgramStatus.COMPLETED:
                return self._build(
                    run_id=run_id,
                    status=ProgramRunStatus.COMPLETED,
                    code="program_completed",
                    message="The final stage passed its verifier-gated advance decision.",
                    initial_state=initial_state,
                    final_state=state,
                    steps=resolved_steps,
                    stage_runs=stage_runs,
                    initial_execution_ledger=initial_ledger,
                    execution_ledger=execution_ledger,
                )
            if state.status is ProgramStatus.TERMINATED:
                return self._build(
                    run_id=run_id,
                    status=ProgramRunStatus.TERMINATED,
                    code="program_terminated",
                    message="Program execution stopped after an accepted kill decision.",
                    initial_state=initial_state,
                    final_state=state,
                    steps=resolved_steps,
                    stage_runs=stage_runs,
                    initial_execution_ledger=initial_ledger,
                    execution_ledger=execution_ledger,
                )
            if decision is not Decision.ADVANCE:
                return self._build(
                    run_id=run_id,
                    status=ProgramRunStatus.PAUSED,
                    code=f"program_paused_on_{decision.value}",
                    message="Program execution paused without scheduling another stage.",
                    initial_state=initial_state,
                    final_state=state,
                    steps=resolved_steps,
                    stage_runs=stage_runs,
                    initial_execution_ledger=initial_ledger,
                    execution_ledger=execution_ledger,
                    details={"step_index": index, "decision": decision.value},
                )

        return self._build(
            run_id=run_id,
            status=ProgramRunStatus.EXHAUSTED,
            code="program_plan_exhausted",
            message="Supplied stage plans were exhausted while the program remains nonterminal.",
            initial_state=initial_state,
            final_state=state,
            steps=resolved_steps,
            stage_runs=stage_runs,
            initial_execution_ledger=initial_ledger,
            execution_ledger=execution_ledger,
        )

    @staticmethod
    def _build(**values: Any) -> BoundedProgramRun:
        return BoundedProgramRun(**values)


def replay_program_run(
    run: BoundedProgramRun,
    *,
    environment: GatedDiscoveryEnvironment | None = None,
) -> ReplayReport:
    """Replay accepted packets and require exact equality with the recorded final state."""

    _require_instance(run, BoundedProgramRun, "run")
    report = replay_program(run.replay_bundle, environment=environment)
    if report.stopped_on_block or report.final_state != run.final_state:
        raise ValueError("program run did not reproduce exactly through accepted-packet replay")
    return report
