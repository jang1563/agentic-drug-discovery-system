"""Typed bounded replanning and hash-bound program checkpoint resume."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .execution import ToolExecutionLedger
from .models import (
    ActionType,
    Decision,
    ProgramState,
    ProgramStatus,
    SerializableRecord,
    Stage,
    _freeze_text_tuple,
    _require_instance,
    _require_text,
    to_primitive,
)
from .planning import StagePlan, ToolCallSpec
from .program import (
    BoundedProgramRun,
    BoundedProgramRunner,
    ProgramRunStatus,
    ProgramStep,
    PromotionBinding,
)
from .promotion import PromotionContext
from .serialization import (
    RecordParseError,
    program_state_from_dict,
    tool_execution_ledger_from_dict,
)


POLICY_CHECKPOINT_SCHEMA_VERSION = "adds.policy-checkpoint-envelope.v1"


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ReplanAction(str, Enum):
    """Policy actions that do not bypass a scientific stage decision."""

    REPLAN = "replan"
    PAUSE = "pause"


class CheckpointDisposition(str, Enum):
    """Whether a checkpoint may execute, must wait, or is terminal."""

    READY = "ready"
    PAUSED = "paused"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class PolicyProgramRunStatus(str, Enum):
    """Outcome of one bounded policy-runner invocation."""

    COMPLETED = "completed"
    TERMINATED = "terminated"
    EXHAUSTED = "exhausted"
    PAUSED = "paused"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ReplanObservation(SerializableRecord):
    """Policy-visible summary of one non-advance program segment."""

    program_id: str
    state_version: int
    stage: Stage
    program_status: ProgramStatus
    run_status: ProgramRunStatus
    program_run_code: str
    stage_run_code: str
    consumed_plan_id: str
    pending_plan_ids: tuple[str, ...] = ()
    blocking_codes: tuple[str, ...] = ()
    last_decision: Decision | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "program_id",
            "program_run_code",
            "stage_run_code",
            "consumed_plan_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _non_negative_int(self.state_version, "state_version")
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.program_status, ProgramStatus, "program_status")
        _require_instance(self.run_status, ProgramRunStatus, "run_status")
        if self.run_status not in {
            ProgramRunStatus.PAUSED,
            ProgramRunStatus.BLOCKED,
        }:
            raise ValueError("replan observations require paused or blocked runs")
        if self.last_decision is not None:
            _require_instance(self.last_decision, Decision, "last_decision")
        if self.run_status is ProgramRunStatus.PAUSED:
            if self.last_decision in {None, Decision.ADVANCE}:
                raise ValueError("paused observations require a non-advance decision")
        elif self.last_decision is not None:
            raise ValueError("blocked observations cannot claim an accepted decision")
        object.__setattr__(
            self,
            "pending_plan_ids",
            _freeze_text_tuple(self.pending_plan_ids, "pending_plan_ids"),
        )
        object.__setattr__(
            self,
            "blocking_codes",
            _freeze_text_tuple(self.blocking_codes, "blocking_codes"),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ReplanRule(SerializableRecord):
    """One deterministic match rule and its predeclared replacement plans."""

    rule_id: str
    stage: Stage
    run_statuses: tuple[ProgramRunStatus, ...]
    action: ReplanAction
    replacement_steps: tuple[ProgramStep, ...] = ()
    trigger_codes: tuple[str, ...] = ()
    decisions: tuple[Decision, ...] = ()
    required_blocking_codes: tuple[str, ...] = ()
    preserve_pending: bool = True
    max_applications: int = 1

    def __post_init__(self) -> None:
        _require_text(self.rule_id, "rule_id")
        _require_instance(self.stage, Stage, "stage")
        statuses = tuple(self.run_statuses)
        object.__setattr__(self, "run_statuses", statuses)
        if not statuses:
            raise ValueError("run_statuses must not be empty")
        for status in statuses:
            _require_instance(status, ProgramRunStatus, "run_statuses item")
            if status not in {ProgramRunStatus.PAUSED, ProgramRunStatus.BLOCKED}:
                raise ValueError("rules may match only paused or blocked runs")
        if len(statuses) != len(set(statuses)):
            raise ValueError("run_statuses must be unique")
        _require_instance(self.action, ReplanAction, "action")
        replacement_steps = tuple(self.replacement_steps)
        object.__setattr__(self, "replacement_steps", replacement_steps)
        for step in replacement_steps:
            _require_instance(step, ProgramStep, "replacement_steps item")
        replacement_ids = tuple(
            step.stage_plan.plan_id for step in replacement_steps
        )
        if len(replacement_ids) != len(set(replacement_ids)):
            raise ValueError("replacement_steps must use unique plan ids")
        replacement_ids = tuple(
            step.stage_plan.plan_id for step in replacement_steps
        )
        if len(replacement_ids) != len(set(replacement_ids)):
            raise ValueError("replacement steps must use unique plan ids")
        if self.action is ReplanAction.REPLAN:
            if not replacement_steps:
                raise ValueError("replan rules require replacement_steps")
            if replacement_steps[0].stage_plan.stage is not self.stage:
                raise ValueError("first replacement step must match the rule stage")
        elif replacement_steps:
            raise ValueError("pause rules cannot carry replacement_steps")
        for field_name in ("trigger_codes", "required_blocking_codes"):
            object.__setattr__(
                self,
                field_name,
                _freeze_text_tuple(getattr(self, field_name), field_name),
            )
        decisions = tuple(self.decisions)
        object.__setattr__(self, "decisions", decisions)
        for decision in decisions:
            _require_instance(decision, Decision, "decisions item")
            if decision is Decision.ADVANCE:
                raise ValueError("replan rules cannot match advance decisions")
        if len(decisions) != len(set(decisions)):
            raise ValueError("decisions must be unique")
        if not isinstance(self.preserve_pending, bool):
            raise TypeError("preserve_pending must be boolean")
        if self.action is ReplanAction.PAUSE and not self.preserve_pending:
            raise ValueError("pause rules must preserve pending steps")
        _positive_int(self.max_applications, "max_applications")

    def matches(self, observation: ReplanObservation) -> bool:
        _require_instance(observation, ReplanObservation, "observation")
        if observation.stage is not self.stage:
            return False
        if observation.run_status not in self.run_statuses:
            return False
        if self.trigger_codes and not (
            set(self.trigger_codes)
            & {observation.program_run_code, observation.stage_run_code}
        ):
            return False
        if self.decisions and observation.last_decision not in self.decisions:
            return False
        if not set(self.required_blocking_codes).issubset(
            observation.blocking_codes
        ):
            return False
        return True


@dataclass(frozen=True, slots=True)
class ReplanDirective(SerializableRecord):
    """One policy decision bound to an exact observation fingerprint."""

    directive_id: str
    policy_id: str
    policy_version: str
    rule_id: str
    revision_index: int
    action: ReplanAction
    reason_code: str
    observation_fingerprint: str
    replacement_steps: tuple[ProgramStep, ...] = ()
    preserve_pending: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "directive_id",
            "policy_id",
            "policy_version",
            "rule_id",
            "reason_code",
            "observation_fingerprint",
        ):
            _require_text(getattr(self, field_name), field_name)
        _positive_int(self.revision_index, "revision_index")
        _require_instance(self.action, ReplanAction, "action")
        if len(self.observation_fingerprint) != 64:
            raise ValueError("observation_fingerprint must be a SHA-256 hex digest")
        try:
            int(self.observation_fingerprint, 16)
        except ValueError as exc:
            raise ValueError(
                "observation_fingerprint must be a SHA-256 hex digest"
            ) from exc
        replacement_steps = tuple(self.replacement_steps)
        object.__setattr__(self, "replacement_steps", replacement_steps)
        for step in replacement_steps:
            _require_instance(step, ProgramStep, "replacement_steps item")
        if self.action is ReplanAction.REPLAN and not replacement_steps:
            raise ValueError("replan directives require replacement_steps")
        if self.action is ReplanAction.PAUSE and replacement_steps:
            raise ValueError("pause directives cannot carry replacement_steps")
        if not isinstance(self.preserve_pending, bool):
            raise TypeError("preserve_pending must be boolean")
        if self.action is ReplanAction.PAUSE and not self.preserve_pending:
            raise ValueError("pause directives must preserve pending steps")


@dataclass(frozen=True, slots=True)
class ReplanRecord(SerializableRecord):
    """Applied queue mutation or explicit abstention for one observation."""

    observation: ReplanObservation
    directive: ReplanDirective
    prior_pending_plan_ids: tuple[str, ...]
    resulting_pending_plan_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_instance(self.observation, ReplanObservation, "observation")
        _require_instance(self.directive, ReplanDirective, "directive")
        if self.directive.observation_fingerprint != self.observation.fingerprint:
            raise ValueError("directive does not bind the replan observation")
        for field_name in (
            "prior_pending_plan_ids",
            "resulting_pending_plan_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_text_tuple(getattr(self, field_name), field_name),
            )
        if self.prior_pending_plan_ids != self.observation.pending_plan_ids:
            raise ValueError("replan record prior queue does not match observation")
        if self.directive.action is ReplanAction.PAUSE:
            expected = self.prior_pending_plan_ids
        else:
            replacement_ids = tuple(
                step.stage_plan.plan_id
                for step in self.directive.replacement_steps
            )
            expected = (
                (*replacement_ids, *self.prior_pending_plan_ids)
                if self.directive.preserve_pending
                else replacement_ids
            )
        if self.resulting_pending_plan_ids != tuple(expected):
            raise ValueError("replan record resulting queue is inconsistent")


@dataclass(frozen=True, slots=True)
class BoundedReplanPolicy(SerializableRecord):
    """Ordered deterministic policy over typed non-advance observations."""

    policy_id: str
    version: str
    rules: tuple[ReplanRule, ...]
    max_replans: int

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        rules = tuple(self.rules)
        object.__setattr__(self, "rules", rules)
        for rule in rules:
            _require_instance(rule, ReplanRule, "rules item")
        rule_ids = tuple(rule.rule_id for rule in rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rules must use unique rule ids")
        _non_negative_int(self.max_replans, "max_replans")

    def decide(
        self,
        observation: ReplanObservation,
        history: Sequence[ReplanRecord],
    ) -> ReplanDirective:
        _require_instance(observation, ReplanObservation, "observation")
        records = tuple(history)
        for record in records:
            _require_instance(record, ReplanRecord, "history item")
            if (
                record.directive.policy_id != self.policy_id
                or record.directive.policy_version != self.version
            ):
                raise ValueError("replan history belongs to another policy")
        revision_index = len(records) + 1
        total_replans = sum(
            record.directive.action is ReplanAction.REPLAN for record in records
        )
        if total_replans >= self.max_replans:
            return self._pause(
                observation,
                revision_index,
                rule_id="__global__",
                reason_code="global_replan_limit_reached",
            )
        matching_rule = next(
            (rule for rule in self.rules if rule.matches(observation)),
            None,
        )
        if matching_rule is None:
            return self._pause(
                observation,
                revision_index,
                rule_id="__default__",
                reason_code="no_matching_replan_rule",
            )
        applications = sum(
            record.directive.action is ReplanAction.REPLAN
            and record.directive.rule_id == matching_rule.rule_id
            for record in records
        )
        if applications >= matching_rule.max_applications:
            return self._pause(
                observation,
                revision_index,
                rule_id=matching_rule.rule_id,
                reason_code="rule_application_limit_reached",
            )
        return self._directive(
            observation=observation,
            revision_index=revision_index,
            rule_id=matching_rule.rule_id,
            action=matching_rule.action,
            reason_code=(
                "matched_replan_rule"
                if matching_rule.action is ReplanAction.REPLAN
                else "matched_pause_rule"
            ),
            replacement_steps=matching_rule.replacement_steps,
            preserve_pending=matching_rule.preserve_pending,
        )

    def _pause(
        self,
        observation: ReplanObservation,
        revision_index: int,
        *,
        rule_id: str,
        reason_code: str,
    ) -> ReplanDirective:
        return self._directive(
            observation=observation,
            revision_index=revision_index,
            rule_id=rule_id,
            action=ReplanAction.PAUSE,
            reason_code=reason_code,
            replacement_steps=(),
            preserve_pending=True,
        )

    def _directive(
        self,
        *,
        observation: ReplanObservation,
        revision_index: int,
        rule_id: str,
        action: ReplanAction,
        reason_code: str,
        replacement_steps: tuple[ProgramStep, ...],
        preserve_pending: bool,
    ) -> ReplanDirective:
        short_hash = hashlib.sha256(
            (
                f"{self.policy_id}|{self.version}|{rule_id}|{revision_index}|"
                f"{observation.fingerprint}"
            ).encode("utf-8")
        ).hexdigest()[:16]
        return ReplanDirective(
            directive_id=(
                f"{self.policy_id}:{rule_id}:r{revision_index}:{short_hash}"
            ),
            policy_id=self.policy_id,
            policy_version=self.version,
            rule_id=rule_id,
            revision_index=revision_index,
            action=action,
            reason_code=reason_code,
            observation_fingerprint=observation.fingerprint,
            replacement_steps=replacement_steps,
            preserve_pending=preserve_pending,
        )


@dataclass(frozen=True, slots=True)
class PolicyCheckpoint(SerializableRecord):
    """Complete resumable cursor over state, execution, plans, and policy history."""

    checkpoint_id: str
    policy_id: str
    policy_version: str
    disposition: CheckpointDisposition
    state: ProgramState
    execution_ledger: ToolExecutionLedger
    pending_steps: tuple[ProgramStep, ...] = ()
    consumed_plan_ids: tuple[str, ...] = ()
    replan_history: tuple[ReplanRecord, ...] = ()
    invocation_count: int = 0
    parent_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("checkpoint_id", "policy_id", "policy_version"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.disposition, CheckpointDisposition, "disposition")
        _require_instance(self.state, ProgramState, "state")
        _require_instance(
            self.execution_ledger,
            ToolExecutionLedger,
            "execution_ledger",
        )
        self.state.validate_committed_history()
        foreign_programs = {
            outcome.request.program_id
            for outcome in self.execution_ledger.outcomes
            if outcome.request.program_id != self.state.program_id
        }
        if foreign_programs:
            raise ValueError("checkpoint ledger contains another program")
        if any(
            outcome.request.expected_state_version > self.state.version
            for outcome in self.execution_ledger.outcomes
        ):
            raise ValueError("checkpoint ledger contains a future-state request")
        pending_steps = tuple(self.pending_steps)
        object.__setattr__(self, "pending_steps", pending_steps)
        for step in pending_steps:
            _require_instance(step, ProgramStep, "pending_steps item")
        pending_ids = tuple(step.stage_plan.plan_id for step in pending_steps)
        if len(pending_ids) != len(set(pending_ids)):
            raise ValueError("pending steps must use unique plan ids")
        object.__setattr__(
            self,
            "consumed_plan_ids",
            _freeze_text_tuple(self.consumed_plan_ids, "consumed_plan_ids"),
        )
        if set(pending_ids) & set(self.consumed_plan_ids):
            raise ValueError("pending and consumed plan ids must not overlap")
        _non_negative_int(self.invocation_count, "invocation_count")
        history = tuple(self.replan_history)
        object.__setattr__(self, "replan_history", history)
        if len(history) > self.invocation_count:
            raise ValueError("replan history cannot exceed invocation count")
        for index, record in enumerate(history, start=1):
            _require_instance(record, ReplanRecord, "replan_history item")
            if (
                record.directive.policy_id != self.policy_id
                or record.directive.policy_version != self.policy_version
            ):
                raise ValueError("checkpoint replan history uses another policy")
            if record.directive.revision_index != index:
                raise ValueError("checkpoint replan history is not contiguous")
            if record.observation.program_id != self.state.program_id:
                raise ValueError("checkpoint replan history uses another program")
            if record.observation.state_version > self.state.version:
                raise ValueError("checkpoint replan history is from a future state")
            if record.observation.consumed_plan_id not in self.consumed_plan_ids:
                raise ValueError("replan history references an unconsumed plan")
        if self.invocation_count != len(self.consumed_plan_ids):
            raise ValueError("invocation_count must equal consumed plan count")
        if self.parent_fingerprint is not None:
            if len(self.parent_fingerprint) != 64:
                raise ValueError("parent_fingerprint must be a SHA-256 hex digest")
            try:
                int(self.parent_fingerprint, 16)
            except ValueError as exc:
                raise ValueError(
                    "parent_fingerprint must be a SHA-256 hex digest"
                ) from exc
        self._validate_disposition(pending_steps)

    def _validate_disposition(self, pending_steps: tuple[ProgramStep, ...]) -> None:
        if self.state.status is ProgramStatus.COMPLETED:
            if (
                self.disposition is not CheckpointDisposition.COMPLETED
                or pending_steps
            ):
                raise ValueError("completed state requires an empty completed checkpoint")
            return
        if self.state.status is ProgramStatus.TERMINATED:
            if (
                self.disposition is not CheckpointDisposition.TERMINATED
                or pending_steps
            ):
                raise ValueError(
                    "terminated state requires an empty terminated checkpoint"
                )
            return
        if self.disposition in {
            CheckpointDisposition.COMPLETED,
            CheckpointDisposition.TERMINATED,
        }:
            raise ValueError("terminal checkpoint requires a matching terminal state")
        if self.disposition is CheckpointDisposition.READY and not pending_steps:
            raise ValueError("ready checkpoint requires pending steps")
        if self.disposition is CheckpointDisposition.EXHAUSTED and pending_steps:
            raise ValueError("exhausted checkpoint cannot contain pending steps")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class PolicyDrivenProgramRun(SerializableRecord):
    """Auditable chain of single-step bounded runs and policy checkpoints."""

    run_id: str
    status: PolicyProgramRunStatus
    code: str
    message: str
    checkpoints: tuple[PolicyCheckpoint, ...]
    segments: tuple[BoundedProgramRun, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("run_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.status, PolicyProgramRunStatus, "status")
        checkpoints = tuple(self.checkpoints)
        segments = tuple(self.segments)
        object.__setattr__(self, "checkpoints", checkpoints)
        object.__setattr__(self, "segments", segments)
        if not checkpoints:
            raise ValueError("policy-driven runs require at least one checkpoint")
        if len(checkpoints) != len(segments) + 1:
            raise ValueError("checkpoints must bracket every program segment")
        for checkpoint in checkpoints:
            _require_instance(checkpoint, PolicyCheckpoint, "checkpoints item")
        for segment in segments:
            _require_instance(segment, BoundedProgramRun, "segments item")
        for before, segment, after in zip(
            checkpoints[:-1],
            segments,
            checkpoints[1:],
            strict=True,
        ):
            if after.parent_fingerprint != before.fingerprint:
                raise ValueError("checkpoint fingerprint chain is broken")
            if segment.initial_state != before.state:
                raise ValueError("program segment breaks checkpoint state input")
            if segment.initial_execution_ledger != before.execution_ledger:
                raise ValueError("program segment breaks checkpoint ledger input")
            if segment.final_state != after.state:
                raise ValueError("program segment breaks checkpoint state output")
            if segment.execution_ledger != after.execution_ledger:
                raise ValueError("program segment breaks checkpoint ledger output")
            if len(segment.steps) != 1:
                raise ValueError("policy runner segments must consume one step")
            plan_id = segment.steps[0].stage_plan.plan_id
            if after.consumed_plan_ids != (*before.consumed_plan_ids, plan_id):
                raise ValueError("checkpoint consumed-plan chain is broken")
            if after.invocation_count != before.invocation_count + 1:
                raise ValueError("checkpoint invocation count is not contiguous")
            if after.replan_history[: len(before.replan_history)] != (
                before.replan_history
            ):
                raise ValueError("checkpoint replan history is not append-only")
            history_delta = len(after.replan_history) - len(before.replan_history)
            if history_delta not in {0, 1}:
                raise ValueError("one invocation may append at most one replan record")
            unconsumed_tail = tuple(
                item.stage_plan.plan_id for item in before.pending_steps[1:]
            )
            if segment.status in {
                ProgramRunStatus.PAUSED,
                ProgramRunStatus.BLOCKED,
            }:
                if history_delta != 1:
                    raise ValueError("non-advance segment requires one policy record")
                record = after.replan_history[-1]
                if (
                    record.observation.consumed_plan_id != plan_id
                    or record.observation.state_version != segment.final_state.version
                    or record.observation.stage is not segment.final_state.current_stage
                    or record.observation.program_status is not segment.final_state.status
                    or record.observation.run_status is not segment.status
                    or record.observation.program_run_code != segment.code
                    or record.observation.stage_run_code
                    != segment.stage_runs[-1].code
                    or record.prior_pending_plan_ids != unconsumed_tail
                    or record.resulting_pending_plan_ids
                    != tuple(
                        item.stage_plan.plan_id for item in after.pending_steps
                    )
                ):
                    raise ValueError("policy record does not match its program segment")
            else:
                if history_delta:
                    raise ValueError("advance or terminal segment cannot append a replan")
                expected_pending = (
                    ()
                    if segment.status
                    in {ProgramRunStatus.COMPLETED, ProgramRunStatus.TERMINATED}
                    else before.pending_steps[1:]
                )
                if after.pending_steps != expected_pending:
                    raise ValueError("checkpoint pending-step chain is broken")
        final = checkpoints[-1]
        expected = {
            CheckpointDisposition.COMPLETED: PolicyProgramRunStatus.COMPLETED,
            CheckpointDisposition.TERMINATED: PolicyProgramRunStatus.TERMINATED,
            CheckpointDisposition.EXHAUSTED: PolicyProgramRunStatus.EXHAUSTED,
            CheckpointDisposition.PAUSED: PolicyProgramRunStatus.PAUSED,
            CheckpointDisposition.BLOCKED: PolicyProgramRunStatus.BLOCKED,
        }.get(final.disposition)
        if expected is not None and self.status is not expected:
            raise ValueError("run status does not match final checkpoint disposition")
        if final.disposition is CheckpointDisposition.READY and self.status is not (
            PolicyProgramRunStatus.PAUSED
        ):
            raise ValueError("ready final checkpoint represents a bounded pause")

    @property
    def initial_checkpoint(self) -> PolicyCheckpoint:
        return self.checkpoints[0]

    @property
    def final_checkpoint(self) -> PolicyCheckpoint:
        return self.checkpoints[-1]


class PolicyDrivenProgramRunner:
    """Run one plan at a time, apply typed policy rules, and emit resumable cursors."""

    def __init__(
        self,
        *,
        program_runner: BoundedProgramRunner,
        policy: BoundedReplanPolicy,
    ) -> None:
        _require_instance(program_runner, BoundedProgramRunner, "program_runner")
        _require_instance(policy, BoundedReplanPolicy, "policy")
        self.program_runner = program_runner
        self.policy = policy

    def start_checkpoint(
        self,
        *,
        checkpoint_id: str,
        state: ProgramState,
        steps: Sequence[ProgramStep],
        execution_ledger: ToolExecutionLedger = ToolExecutionLedger(),
    ) -> PolicyCheckpoint:
        _require_text(checkpoint_id, "checkpoint_id")
        _require_instance(state, ProgramState, "state")
        _require_instance(execution_ledger, ToolExecutionLedger, "execution_ledger")
        pending = tuple(steps)
        if state.status is ProgramStatus.COMPLETED:
            disposition = CheckpointDisposition.COMPLETED
            pending = ()
        elif state.status is ProgramStatus.TERMINATED:
            disposition = CheckpointDisposition.TERMINATED
            pending = ()
        elif pending:
            disposition = CheckpointDisposition.READY
        else:
            disposition = CheckpointDisposition.EXHAUSTED
        return PolicyCheckpoint(
            checkpoint_id=checkpoint_id,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            disposition=disposition,
            state=state,
            execution_ledger=execution_ledger,
            pending_steps=pending,
        )

    def run(
        self,
        *,
        run_id: str,
        checkpoint: PolicyCheckpoint,
        expected_checkpoint_fingerprint: str,
        max_invocations: int,
    ) -> PolicyDrivenProgramRun:
        _require_text(run_id, "run_id")
        _require_instance(checkpoint, PolicyCheckpoint, "checkpoint")
        _require_text(
            expected_checkpoint_fingerprint,
            "expected_checkpoint_fingerprint",
        )
        _positive_int(max_invocations, "max_invocations")
        if checkpoint.fingerprint != expected_checkpoint_fingerprint:
            raise ValueError("checkpoint fingerprint does not match resume token")
        if (
            checkpoint.policy_id != self.policy.policy_id
            or checkpoint.policy_version != self.policy.version
        ):
            raise ValueError("checkpoint policy identity does not match runner policy")
        if checkpoint.disposition is not CheckpointDisposition.READY:
            return self._non_ready_run(run_id, checkpoint)

        checkpoints = [checkpoint]
        segments: list[BoundedProgramRun] = []
        current = checkpoint
        for _ in range(max_invocations):
            step = current.pending_steps[0]
            remaining = tuple(current.pending_steps[1:])
            segment = self.program_runner.run_program(
                run_id=(
                    f"{run_id}:invocation-{current.invocation_count + 1}:"
                    f"{step.stage_plan.plan_id}"
                ),
                state=current.state,
                steps=(step,),
                execution_ledger=current.execution_ledger,
            )
            segments.append(segment)
            history = current.replan_history
            disposition: CheckpointDisposition
            stop_status: PolicyProgramRunStatus | None = None
            stop_code = ""
            stop_message = ""

            if segment.status is ProgramRunStatus.COMPLETED:
                remaining = ()
                disposition = CheckpointDisposition.COMPLETED
                stop_status = PolicyProgramRunStatus.COMPLETED
                stop_code = "policy_program_completed"
                stop_message = "Program reached a verifier-gated completed state."
            elif segment.status is ProgramRunStatus.TERMINATED:
                remaining = ()
                disposition = CheckpointDisposition.TERMINATED
                stop_status = PolicyProgramRunStatus.TERMINATED
                stop_code = "policy_program_terminated"
                stop_message = "Program reached an accepted kill decision."
            elif segment.status is ProgramRunStatus.EXHAUSTED:
                if remaining:
                    disposition = CheckpointDisposition.READY
                else:
                    disposition = CheckpointDisposition.EXHAUSTED
                    stop_status = PolicyProgramRunStatus.EXHAUSTED
                    stop_code = "policy_program_plan_exhausted"
                    stop_message = "No declared plan remains for the active program."
            else:
                observation = self._observation(segment, remaining)
                directive = self.policy.decide(observation, history)
                directive = self._validate_runtime_directive(
                    directive,
                    observation,
                    current,
                    remaining,
                )
                prior_ids = tuple(item.stage_plan.plan_id for item in remaining)
                if directive.action is ReplanAction.REPLAN:
                    replacement = directive.replacement_steps
                    remaining = (
                        (*replacement, *remaining)
                        if directive.preserve_pending
                        else replacement
                    )
                    disposition = CheckpointDisposition.READY
                else:
                    disposition = (
                        CheckpointDisposition.PAUSED
                        if segment.status is ProgramRunStatus.PAUSED
                        else CheckpointDisposition.BLOCKED
                    )
                    stop_status = (
                        PolicyProgramRunStatus.PAUSED
                        if segment.status is ProgramRunStatus.PAUSED
                        else PolicyProgramRunStatus.BLOCKED
                    )
                    stop_code = directive.reason_code
                    stop_message = (
                        "Policy paused after a typed non-advance observation."
                    )
                resulting_ids = tuple(
                    item.stage_plan.plan_id for item in remaining
                )
                history = (
                    *history,
                    ReplanRecord(
                        observation=observation,
                        directive=directive,
                        prior_pending_plan_ids=prior_ids,
                        resulting_pending_plan_ids=resulting_ids,
                    ),
                )

            next_checkpoint = PolicyCheckpoint(
                checkpoint_id=(
                    f"{run_id}:checkpoint:{current.invocation_count + 1}:"
                    f"r{len(history)}"
                ),
                policy_id=self.policy.policy_id,
                policy_version=self.policy.version,
                disposition=disposition,
                state=segment.final_state,
                execution_ledger=segment.execution_ledger,
                pending_steps=remaining,
                consumed_plan_ids=(
                    *current.consumed_plan_ids,
                    step.stage_plan.plan_id,
                ),
                replan_history=history,
                invocation_count=current.invocation_count + 1,
                parent_fingerprint=current.fingerprint,
            )
            checkpoints.append(next_checkpoint)
            current = next_checkpoint
            if stop_status is not None:
                return PolicyDrivenProgramRun(
                    run_id=run_id,
                    status=stop_status,
                    code=stop_code,
                    message=stop_message,
                    checkpoints=tuple(checkpoints),
                    segments=tuple(segments),
                )

        return PolicyDrivenProgramRun(
            run_id=run_id,
            status=PolicyProgramRunStatus.PAUSED,
            code="policy_invocation_limit_reached",
            message=(
                "Invocation limit reached with a hash-bound ready checkpoint."
            ),
            checkpoints=tuple(checkpoints),
            segments=tuple(segments),
        )

    def _non_ready_run(
        self,
        run_id: str,
        checkpoint: PolicyCheckpoint,
    ) -> PolicyDrivenProgramRun:
        mapping = {
            CheckpointDisposition.COMPLETED: (
                PolicyProgramRunStatus.COMPLETED,
                "checkpoint_already_completed",
            ),
            CheckpointDisposition.TERMINATED: (
                PolicyProgramRunStatus.TERMINATED,
                "checkpoint_already_terminated",
            ),
            CheckpointDisposition.EXHAUSTED: (
                PolicyProgramRunStatus.EXHAUSTED,
                "checkpoint_plan_exhausted",
            ),
            CheckpointDisposition.PAUSED: (
                PolicyProgramRunStatus.PAUSED,
                "checkpoint_requires_reauthorization",
            ),
            CheckpointDisposition.BLOCKED: (
                PolicyProgramRunStatus.BLOCKED,
                "checkpoint_requires_replan",
            ),
        }
        status, code = mapping[checkpoint.disposition]
        return PolicyDrivenProgramRun(
            run_id=run_id,
            status=status,
            code=code,
            message="Checkpoint is not in a ready disposition; no plan was invoked.",
            checkpoints=(checkpoint,),
        )

    @staticmethod
    def _observation(
        segment: BoundedProgramRun,
        remaining: tuple[ProgramStep, ...],
    ) -> ReplanObservation:
        final_stage_run = segment.stage_runs[-1]
        blocking_codes = sorted(
            {
                result.code
                for transition in final_stage_run.transition_results
                for result in transition.verifier_results
                if result.blocking
            }
        )
        accepted = segment.accepted_packets
        last_decision = accepted[-1].decision if accepted else None
        return ReplanObservation(
            program_id=segment.final_state.program_id,
            state_version=segment.final_state.version,
            stage=segment.final_state.current_stage,
            program_status=segment.final_state.status,
            run_status=segment.status,
            program_run_code=segment.code,
            stage_run_code=final_stage_run.code,
            consumed_plan_id=segment.steps[0].stage_plan.plan_id,
            pending_plan_ids=tuple(
                item.stage_plan.plan_id for item in remaining
            ),
            blocking_codes=tuple(blocking_codes),
            last_decision=last_decision,
        )

    def _validate_runtime_directive(
        self,
        directive: ReplanDirective,
        observation: ReplanObservation,
        checkpoint: PolicyCheckpoint,
        remaining: tuple[ProgramStep, ...],
    ) -> ReplanDirective:
        _require_instance(directive, ReplanDirective, "directive")
        if (
            directive.policy_id != self.policy.policy_id
            or directive.policy_version != self.policy.version
            or directive.observation_fingerprint != observation.fingerprint
        ):
            raise ValueError("policy directive identity or observation binding failed")
        if directive.action is ReplanAction.PAUSE:
            return directive
        replacement = directive.replacement_steps
        replacement_ids = tuple(item.stage_plan.plan_id for item in replacement)
        existing_ids = {
            *checkpoint.consumed_plan_ids,
            observation.consumed_plan_id,
        }
        if directive.preserve_pending:
            existing_ids.update(item.stage_plan.plan_id for item in remaining)
        if set(replacement_ids) & existing_ids:
            return self._runtime_pause(
                directive,
                reason_code="replacement_plan_id_conflict",
            )
        if replacement[0].stage_plan.stage is not observation.stage:
            return self._runtime_pause(
                directive,
                reason_code="replacement_stage_mismatch",
            )
        return directive

    @staticmethod
    def _runtime_pause(
        directive: ReplanDirective,
        *,
        reason_code: str,
    ) -> ReplanDirective:
        return ReplanDirective(
            directive_id=f"{directive.directive_id}:runtime-pause",
            policy_id=directive.policy_id,
            policy_version=directive.policy_version,
            rule_id=directive.rule_id,
            revision_index=directive.revision_index,
            action=ReplanAction.PAUSE,
            reason_code=reason_code,
            observation_fingerprint=directive.observation_fingerprint,
            preserve_pending=True,
        )


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    if set(data) != fields:
        raise RecordParseError(f"{path} must contain exactly {sorted(fields)}")
    return data


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is not a valid {enum_type.__name__}") from exc


def _date(value: Any, path: str):
    from datetime import date

    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc


def _tool_call_spec_from_dict(value: Any, path: str) -> ToolCallSpec:
    data = _record(
        value,
        path,
        {
            "call_id",
            "tool_id",
            "operation",
            "action_type",
            "purpose",
            "arguments",
            "max_cost",
            "required",
        },
    )
    return ToolCallSpec(
        call_id=data["call_id"],
        tool_id=data["tool_id"],
        operation=data["operation"],
        action_type=_enum(ActionType, data["action_type"], f"{path}.action_type"),
        purpose=data["purpose"],
        arguments=data["arguments"],
        max_cost=data["max_cost"],
        required=data["required"],
    )


def _stage_plan_from_dict(value: Any, path: str) -> StagePlan:
    data = _record(
        value,
        path,
        {
            "plan_id",
            "stage",
            "calls",
            "max_steps",
            "max_total_cost",
            "success_confidence",
            "failure_confidence",
            "success_decision",
            "failure_decision",
            "next_stage",
            "backtrack_stage",
            "stop_on_required_failure",
            "recover_to_defer_on_readiness_block",
            "metadata",
        },
    )
    return StagePlan(
        plan_id=data["plan_id"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        calls=tuple(
            _tool_call_spec_from_dict(item, f"{path}.calls[{index}]")
            for index, item in enumerate(_sequence(data["calls"], f"{path}.calls"))
        ),
        max_steps=data["max_steps"],
        max_total_cost=data["max_total_cost"],
        success_confidence=data["success_confidence"],
        failure_confidence=data["failure_confidence"],
        success_decision=_enum(
            Decision,
            data["success_decision"],
            f"{path}.success_decision",
        ),
        failure_decision=_enum(
            Decision,
            data["failure_decision"],
            f"{path}.failure_decision",
        ),
        next_stage=(
            None
            if data["next_stage"] is None
            else _enum(Stage, data["next_stage"], f"{path}.next_stage")
        ),
        backtrack_stage=(
            None
            if data["backtrack_stage"] is None
            else _enum(Stage, data["backtrack_stage"], f"{path}.backtrack_stage")
        ),
        stop_on_required_failure=data["stop_on_required_failure"],
        recover_to_defer_on_readiness_block=(
            data["recover_to_defer_on_readiness_block"]
        ),
        metadata=data["metadata"],
    )


def _promotion_context_from_dict(value: Any, path: str) -> PromotionContext:
    data = _record(
        value,
        path,
        {
            "observed_at",
            "available_at",
            "subject",
            "object_value",
            "confidence",
            "candidate_id",
            "candidate_name",
            "modality",
            "biological_context",
            "metadata",
        },
    )
    return PromotionContext(
        observed_at=_date(data["observed_at"], f"{path}.observed_at"),
        available_at=_date(data["available_at"], f"{path}.available_at"),
        subject=data["subject"],
        object_value=data["object_value"],
        confidence=data["confidence"],
        candidate_id=data["candidate_id"],
        candidate_name=data["candidate_name"],
        modality=data["modality"],
        biological_context=data["biological_context"],
        metadata=data["metadata"],
    )


def _program_step_from_dict(value: Any, path: str) -> ProgramStep:
    data = _record(value, path, {"stage_plan", "promotion_bindings"})
    bindings = []
    for index, item in enumerate(
        _sequence(data["promotion_bindings"], f"{path}.promotion_bindings")
    ):
        binding_path = f"{path}.promotion_bindings[{index}]"
        binding = _record(item, binding_path, {"call_id", "context"})
        bindings.append(
            PromotionBinding(
                call_id=binding["call_id"],
                context=_promotion_context_from_dict(
                    binding["context"], f"{binding_path}.context"
                ),
            )
        )
    return ProgramStep(
        stage_plan=_stage_plan_from_dict(data["stage_plan"], f"{path}.stage_plan"),
        promotion_bindings=tuple(bindings),
    )


def _observation_from_dict(value: Any, path: str) -> ReplanObservation:
    data = _record(
        value,
        path,
        {
            "program_id",
            "state_version",
            "stage",
            "program_status",
            "run_status",
            "program_run_code",
            "stage_run_code",
            "consumed_plan_id",
            "pending_plan_ids",
            "blocking_codes",
            "last_decision",
        },
    )
    return ReplanObservation(
        program_id=data["program_id"],
        state_version=data["state_version"],
        stage=_enum(Stage, data["stage"], f"{path}.stage"),
        program_status=_enum(
            ProgramStatus,
            data["program_status"],
            f"{path}.program_status",
        ),
        run_status=_enum(
            ProgramRunStatus,
            data["run_status"],
            f"{path}.run_status",
        ),
        program_run_code=data["program_run_code"],
        stage_run_code=data["stage_run_code"],
        consumed_plan_id=data["consumed_plan_id"],
        pending_plan_ids=tuple(data["pending_plan_ids"]),
        blocking_codes=tuple(data["blocking_codes"]),
        last_decision=(
            None
            if data["last_decision"] is None
            else _enum(Decision, data["last_decision"], f"{path}.last_decision")
        ),
    )


def _directive_from_dict(value: Any, path: str) -> ReplanDirective:
    data = _record(
        value,
        path,
        {
            "directive_id",
            "policy_id",
            "policy_version",
            "rule_id",
            "revision_index",
            "action",
            "reason_code",
            "observation_fingerprint",
            "replacement_steps",
            "preserve_pending",
        },
    )
    return ReplanDirective(
        directive_id=data["directive_id"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        rule_id=data["rule_id"],
        revision_index=data["revision_index"],
        action=_enum(ReplanAction, data["action"], f"{path}.action"),
        reason_code=data["reason_code"],
        observation_fingerprint=data["observation_fingerprint"],
        replacement_steps=tuple(
            _program_step_from_dict(item, f"{path}.replacement_steps[{index}]")
            for index, item in enumerate(
                _sequence(data["replacement_steps"], f"{path}.replacement_steps")
            )
        ),
        preserve_pending=data["preserve_pending"],
    )


def _replan_record_from_dict(value: Any, path: str) -> ReplanRecord:
    data = _record(
        value,
        path,
        {
            "observation",
            "directive",
            "prior_pending_plan_ids",
            "resulting_pending_plan_ids",
        },
    )
    return ReplanRecord(
        observation=_observation_from_dict(
            data["observation"], f"{path}.observation"
        ),
        directive=_directive_from_dict(data["directive"], f"{path}.directive"),
        prior_pending_plan_ids=tuple(data["prior_pending_plan_ids"]),
        resulting_pending_plan_ids=tuple(data["resulting_pending_plan_ids"]),
    )


def policy_checkpoint_to_dict(checkpoint: PolicyCheckpoint) -> dict[str, Any]:
    """Serialize one checkpoint with a canonical SHA-256 integrity envelope."""

    _require_instance(checkpoint, PolicyCheckpoint, "checkpoint")
    return {
        "schema_version": POLICY_CHECKPOINT_SCHEMA_VERSION,
        "integrity_sha256": checkpoint.fingerprint,
        "checkpoint": checkpoint.to_dict(),
    }


def policy_checkpoint_to_json(
    checkpoint: PolicyCheckpoint,
    *,
    indent: int | None = 2,
) -> str:
    """Serialize a checkpoint as deterministic JSON suitable for later resume."""

    return json.dumps(
        policy_checkpoint_to_dict(checkpoint),
        sort_keys=True,
        indent=indent,
        ensure_ascii=True,
        allow_nan=False,
    )


def policy_checkpoint_from_dict(value: Any) -> PolicyCheckpoint:
    """Parse and integrity-check one checkpoint envelope."""

    envelope = _record(
        value,
        "policy_checkpoint_envelope",
        {"schema_version", "integrity_sha256", "checkpoint"},
    )
    if envelope["schema_version"] != POLICY_CHECKPOINT_SCHEMA_VERSION:
        raise RecordParseError("policy checkpoint schema_version is unsupported")
    expected_hash = envelope["integrity_sha256"]
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise RecordParseError("integrity_sha256 must be a SHA-256 hex digest")
    raw = envelope["checkpoint"]
    if _sha256(raw) != expected_hash:
        raise RecordParseError("policy checkpoint integrity hash does not match")
    data = _record(
        raw,
        "checkpoint",
        {
            "checkpoint_id",
            "policy_id",
            "policy_version",
            "disposition",
            "state",
            "execution_ledger",
            "pending_steps",
            "consumed_plan_ids",
            "replan_history",
            "invocation_count",
            "parent_fingerprint",
        },
    )
    checkpoint = PolicyCheckpoint(
        checkpoint_id=data["checkpoint_id"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        disposition=_enum(
            CheckpointDisposition,
            data["disposition"],
            "checkpoint.disposition",
        ),
        state=program_state_from_dict(data["state"], "checkpoint.state"),
        execution_ledger=tool_execution_ledger_from_dict(
            data["execution_ledger"],
            "checkpoint.execution_ledger",
        ),
        pending_steps=tuple(
            _program_step_from_dict(item, f"checkpoint.pending_steps[{index}]")
            for index, item in enumerate(
                _sequence(data["pending_steps"], "checkpoint.pending_steps")
            )
        ),
        consumed_plan_ids=tuple(data["consumed_plan_ids"]),
        replan_history=tuple(
            _replan_record_from_dict(item, f"checkpoint.replan_history[{index}]")
            for index, item in enumerate(
                _sequence(data["replan_history"], "checkpoint.replan_history")
            )
        ),
        invocation_count=data["invocation_count"],
        parent_fingerprint=data["parent_fingerprint"],
    )
    if checkpoint.fingerprint != expected_hash:
        raise RecordParseError("parsed policy checkpoint changed canonical identity")
    return checkpoint


def policy_checkpoint_from_json(payload: str) -> PolicyCheckpoint:
    """Reject duplicate keys and non-finite values before checkpoint parsing."""

    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RecordParseError(f"policy checkpoint duplicates key {key}")
            result[key] = item
        return result

    try:
        value = json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RecordParseError(f"policy checkpoint contains {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError("policy checkpoint is not valid JSON") from exc
    return policy_checkpoint_from_dict(value)
