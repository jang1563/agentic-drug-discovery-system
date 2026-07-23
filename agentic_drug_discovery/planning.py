"""Bounded, fail-closed planning over registered tool contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .execution import ToolExecutionLedger, ToolRegistry, ToolRequest
from .models import (
    ActionType,
    Decision,
    ProgramState,
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_instance,
    _require_text,
)


def _require_non_negative_number(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


class PlanningStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ToolCallSpec(SerializableRecord):
    call_id: str
    tool_id: str
    operation: str
    action_type: ActionType
    purpose: str
    arguments: Mapping[str, Any]
    max_cost: float
    required: bool = True

    def __post_init__(self) -> None:
        for field_name in ("call_id", "tool_id", "operation", "purpose"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.action_type, ActionType, "action_type")
        _require_non_negative_number(self.max_cost, "max_cost")
        if not isinstance(self.required, bool):
            raise TypeError("required must be boolean")
        object.__setattr__(
            self, "arguments", _freeze_mapping(self.arguments, "arguments")
        )


@dataclass(frozen=True, slots=True)
class StagePlan(SerializableRecord):
    plan_id: str
    stage: Stage
    calls: tuple[ToolCallSpec, ...]
    max_steps: int
    max_total_cost: float
    success_confidence: float
    failure_confidence: float
    success_decision: Decision = Decision.ADVANCE
    failure_decision: Decision = Decision.DEFER
    next_stage: Stage | None = None
    backtrack_stage: Stage | None = None
    stop_on_required_failure: bool = True
    recover_to_defer_on_readiness_block: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.plan_id, "plan_id")
        _require_instance(self.stage, Stage, "stage")
        object.__setattr__(self, "calls", tuple(self.calls))
        if not self.calls:
            raise ValueError("calls must not be empty")
        for call in self.calls:
            _require_instance(call, ToolCallSpec, "calls item")
        call_ids = tuple(call.call_id for call in self.calls)
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("calls must have unique call_id values")
        if (
            not isinstance(self.max_steps, int)
            or isinstance(self.max_steps, bool)
            or self.max_steps < 1
        ):
            raise ValueError("max_steps must be a positive integer")
        required_count = sum(call.required for call in self.calls)
        if required_count > self.max_steps:
            raise ValueError("max_steps cannot be lower than the required call count")
        _require_non_negative_number(self.max_total_cost, "max_total_cost")
        for field_name in ("success_confidence", "failure_confidence"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")
        _require_instance(self.success_decision, Decision, "success_decision")
        _require_instance(self.failure_decision, Decision, "failure_decision")
        if self.failure_decision in {Decision.ADVANCE, Decision.PIVOT}:
            raise ValueError("failure_decision must not advance or pivot")
        if self.next_stage is not None:
            _require_instance(self.next_stage, Stage, "next_stage")
        if self.backtrack_stage is not None:
            _require_instance(self.backtrack_stage, Stage, "backtrack_stage")
        if self.success_decision is Decision.PIVOT:
            if self.backtrack_stage is None or self.next_stage is not None:
                raise ValueError("pivot success requires only backtrack_stage")
        elif self.success_decision is Decision.ADVANCE:
            if self.backtrack_stage is not None:
                raise ValueError("advance success cannot set backtrack_stage")
        elif self.next_stage is not None or self.backtrack_stage is not None:
            raise ValueError(
                "non-moving success decisions cannot set stage destinations"
            )
        for field_name in (
            "stop_on_required_failure",
            "recover_to_defer_on_readiness_block",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def required_call_ids(self) -> tuple[str, ...]:
        return tuple(call.call_id for call in self.calls if call.required)


@dataclass(frozen=True, slots=True)
class PlanResult(SerializableRecord):
    status: PlanningStatus
    plan_id: str
    code: str
    message: str
    requests: tuple[ToolRequest, ...] = ()
    call_ids: tuple[str, ...] = ()
    skipped_call_ids: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.status, PlanningStatus, "status")
        for field_name in ("plan_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "requests", tuple(self.requests))
        for request in self.requests:
            _require_instance(request, ToolRequest, "requests item")
        object.__setattr__(
            self, "call_ids", _freeze_text_tuple(self.call_ids, "call_ids")
        )
        object.__setattr__(
            self,
            "skipped_call_ids",
            _freeze_text_tuple(self.skipped_call_ids, "skipped_call_ids"),
        )
        if len(self.requests) != len(self.call_ids):
            raise ValueError("requests and call_ids must have equal length")
        if set(self.call_ids) & set(self.skipped_call_ids):
            raise ValueError("planned and skipped call ids must not overlap")
        _require_non_negative_number(self.estimated_cost, "estimated_cost")
        if self.status is PlanningStatus.READY and not self.requests:
            raise ValueError("ready plan results require at least one request")
        if self.status is PlanningStatus.BLOCKED and self.requests:
            raise ValueError("blocked plan results cannot expose partial requests")
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


class BoundedPlanner:
    """Compile one declarative stage plan into a bounded request batch."""

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def plan(
        self,
        state: ProgramState,
        stage_plan: StagePlan,
        registry: ToolRegistry,
        *,
        execution_ledger: ToolExecutionLedger = ToolExecutionLedger(),
    ) -> PlanResult:
        _require_instance(state, ProgramState, "state")
        _require_instance(stage_plan, StagePlan, "stage_plan")
        if not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry")
        _require_instance(execution_ledger, ToolExecutionLedger, "execution_ledger")

        try:
            state.validate_committed_history()
        except Exception as exc:
            return self._blocked(
                stage_plan,
                "input_state_integrity_invalid",
                "Input state failed committed-history validation.",
                details={"exception_type": type(exc).__name__},
            )
        if state.current_stage is not stage_plan.stage:
            return self._blocked(
                stage_plan,
                "stage_plan_context_mismatch",
                "Stage plan does not match the current program stage.",
                details={
                    "current_stage": state.current_stage.value,
                    "plan_stage": stage_plan.stage.value,
                },
            )
        if state.is_terminal:
            return self._blocked(
                stage_plan,
                "terminal_state",
                "Terminal programs cannot schedule additional tool calls.",
            )
        foreign_programs = sorted(
            {
                outcome.request.program_id
                for outcome in execution_ledger.outcomes
                if outcome.request.program_id != state.program_id
            }
        )
        if foreign_programs:
            return self._blocked(
                stage_plan,
                "execution_ledger_program_mismatch",
                "Execution ledger contains outcomes from another program.",
                details={"foreign_program_ids": foreign_programs},
            )
        try:
            created_at = self._clock()
        except Exception as exc:
            return self._blocked(
                stage_plan,
                "planner_clock_invalid",
                "Planner clock failed before request construction.",
                details={"exception_type": type(exc).__name__},
            )

        invocation_remaining = max(
            0.0,
            float(state.budget.limit) - float(execution_ledger.total_cost),
        )
        available_cost = min(
            float(stage_plan.max_total_cost),
            float(state.budget.remaining),
            invocation_remaining,
        )
        prior_request_ids = set(execution_ledger.by_request_id)
        prior_fingerprints = {
            outcome.request.fingerprint for outcome in execution_ledger.outcomes
        }
        requests: list[ToolRequest] = []
        call_ids: list[str] = []
        skipped: list[str] = []
        skip_reasons: dict[str, str] = {}
        estimated_cost = 0.0

        for call in stage_plan.calls:
            request_id = f"{stage_plan.plan_id}:v{state.version}:{call.call_id}"
            if len(requests) >= stage_plan.max_steps:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_step_limit_exceeded",
                        "Required calls do not fit within the plan step limit.",
                        details={"call_id": call.call_id},
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "step_limit"
                continue
            contract = registry.contract_for(call.tool_id, call.operation)
            if contract is None:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_tool_contract_missing",
                        "A required tool operation is not registered.",
                        details={"call_id": call.call_id},
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "contract_missing"
                continue
            if request_id in prior_request_ids:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_request_already_executed",
                        "A required deterministic request id already exists in the ledger.",
                        details={"call_id": call.call_id, "request_id": request_id},
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "request_already_executed"
                continue
            try:
                request = ToolRequest(
                    request_id=request_id,
                    program_id=state.program_id,
                    expected_state_version=state.version,
                    stage=state.current_stage,
                    tool_id=call.tool_id,
                    operation=call.operation,
                    action_type=call.action_type,
                    purpose=call.purpose,
                    arguments=call.arguments,
                    max_cost=call.max_cost,
                    created_at=created_at,
                )
            except Exception as exc:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_request_invalid",
                        "A required tool request could not be constructed.",
                        details={
                            "call_id": call.call_id,
                            "exception_type": type(exc).__name__,
                        },
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "request_invalid"
                continue
            if request.fingerprint in prior_fingerprints:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_request_repeated",
                        "A required semantic invocation already exists in the ledger.",
                        details={"call_id": call.call_id},
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "request_repeated"
                continue
            preflight = registry.preflight(state, request)
            if preflight is not None:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_request_preflight_failed",
                        "A required request failed tool-contract preflight.",
                        details={
                            "call_id": call.call_id,
                            "error_code": preflight.error_code,
                            "failures": preflight.payload.get("failures", ()),
                        },
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = preflight.error_code or "preflight_failed"
                continue
            projected_cost = estimated_cost + float(contract.default_cost)
            if projected_cost > available_cost + 1e-12:
                if call.required:
                    return self._blocked(
                        stage_plan,
                        "required_execution_budget_exceeded",
                        "Required calls exceed the bounded invocation budget.",
                        details={
                            "call_id": call.call_id,
                            "available_cost": available_cost,
                            "projected_cost": projected_cost,
                        },
                        skipped_call_ids=tuple(skipped),
                    )
                skipped.append(call.call_id)
                skip_reasons[call.call_id] = "execution_budget"
                continue
            requests.append(request)
            call_ids.append(call.call_id)
            estimated_cost = projected_cost

        if not requests:
            return self._blocked(
                stage_plan,
                "no_executable_calls",
                "No calls remained after bounded planning.",
                details={"optional_skip_reasons": skip_reasons},
                skipped_call_ids=tuple(skipped),
            )
        return PlanResult(
            status=PlanningStatus.READY,
            plan_id=stage_plan.plan_id,
            code="bounded_plan_ready",
            message="Tool requests satisfy contract, step, replay, and cost bounds.",
            requests=tuple(requests),
            call_ids=tuple(call_ids),
            skipped_call_ids=tuple(skipped),
            estimated_cost=estimated_cost,
            details={
                "available_cost": available_cost,
                "invocation_ledger_cost": execution_ledger.total_cost,
                "optional_skip_reasons": skip_reasons,
                "stage_plan_metadata": stage_plan.metadata,
            },
        )

    @staticmethod
    def _blocked(
        stage_plan: StagePlan,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        skipped_call_ids: tuple[str, ...] = (),
    ) -> PlanResult:
        return PlanResult(
            status=PlanningStatus.BLOCKED,
            plan_id=stage_plan.plan_id,
            code=code,
            message=message,
            skipped_call_ids=skipped_call_ids,
            details=details or {},
        )
