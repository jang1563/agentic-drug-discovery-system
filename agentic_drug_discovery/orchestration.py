"""Bounded stage execution from tool planning through gated state transition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .environment import GatedDiscoveryEnvironment
from .execution import (
    ToolExecutionLedger,
    ToolOutcome,
    ToolRegistry,
    ToolStatus,
    packet_from_tool_outcomes,
)
from .models import (
    Decision,
    DecisionPacket,
    ProgramState,
    SerializableRecord,
    TransitionResult,
    _freeze_mapping,
    _require_instance,
    _require_text,
)
from .planning import (
    BoundedPlanner,
    PlanningStatus,
    PlanResult,
    StagePlan,
)
from .promotion import (
    PromotionContext,
    PromotionResult,
    PromotionStatus,
    SemanticMapperRegistry,
)


class StageRunStatus(str, Enum):
    PLANNING_BLOCKED = "planning_blocked"
    COMMITTED = "committed"
    TRANSITION_BLOCKED = "transition_blocked"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class StageRun(SerializableRecord):
    run_id: str
    status: StageRunStatus
    code: str
    message: str
    initial_state: ProgramState
    final_state: ProgramState
    plan_result: PlanResult
    outcomes: tuple[ToolOutcome, ...] = ()
    promotions: tuple[PromotionResult, ...] = ()
    attempted_packets: tuple[DecisionPacket, ...] = ()
    transition_results: tuple[TransitionResult, ...] = ()
    execution_ledger: ToolExecutionLedger = ToolExecutionLedger()
    recovered_to_defer: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("run_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.status, StageRunStatus, "status")
        _require_instance(self.initial_state, ProgramState, "initial_state")
        _require_instance(self.final_state, ProgramState, "final_state")
        _require_instance(self.plan_result, PlanResult, "plan_result")
        _require_instance(
            self.execution_ledger,
            ToolExecutionLedger,
            "execution_ledger",
        )
        for field_name, expected in (
            ("outcomes", ToolOutcome),
            ("promotions", PromotionResult),
            ("attempted_packets", DecisionPacket),
            ("transition_results", TransitionResult),
        ):
            values = tuple(getattr(self, field_name))
            object.__setattr__(self, field_name, values)
            for value in values:
                _require_instance(value, expected, f"{field_name} item")
        if len(self.attempted_packets) != len(self.transition_results):
            raise ValueError("attempted_packets and transition_results must align")
        if any(
            result.packet != packet
            for packet, result in zip(
                self.attempted_packets,
                self.transition_results,
                strict=True,
            )
        ):
            raise ValueError("transition result packets must match attempted packets")
        ledger_outcomes = self.execution_ledger.by_request_id
        for outcome in self.outcomes:
            if ledger_outcomes.get(outcome.request_id) != outcome:
                raise ValueError(
                    "stage outcomes must be present in the execution ledger"
                )
        outcome_ids = {item.request_id for item in self.outcomes}
        if any(item.request_id not in outcome_ids for item in self.promotions):
            raise ValueError("promotions must reference stage outcomes")
        if not isinstance(self.recovered_to_defer, bool):
            raise TypeError("recovered_to_defer must be boolean")
        if self.recovered_to_defer:
            if (
                len(self.transition_results) != 2
                or self.transition_results[0].applied
                or not self.transition_results[1].applied
                or self.attempted_packets[1].decision is not Decision.DEFER
            ):
                raise ValueError(
                    "defer recovery requires one blocked and one applied attempt"
                )
        if self.status is StageRunStatus.PLANNING_BLOCKED:
            if self.plan_result.status is not PlanningStatus.BLOCKED:
                raise ValueError("planning-blocked runs require a blocked plan result")
            if self.outcomes or self.attempted_packets:
                raise ValueError("planning-blocked runs cannot invoke tools or packets")
            if self.final_state != self.initial_state:
                raise ValueError("planning-blocked runs must preserve state")
        elif self.status is StageRunStatus.COMMITTED:
            if not self.transition_results or not self.transition_results[-1].applied:
                raise ValueError("committed runs require a final applied transition")
            if self.final_state != self.transition_results[-1].state:
                raise ValueError(
                    "committed run final_state must match transition state"
                )
        elif self.status is StageRunStatus.TRANSITION_BLOCKED:
            if not self.transition_results or any(
                item.applied for item in self.transition_results
            ):
                raise ValueError(
                    "transition-blocked runs cannot contain applied results"
                )
            if self.final_state != self.initial_state:
                raise ValueError("blocked transitions must preserve the initial state")
        elif self.final_state != self.initial_state:
            raise ValueError("internal-error runs must preserve the initial state")
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))

    @property
    def accepted_packets(self) -> tuple[DecisionPacket, ...]:
        return tuple(
            packet
            for packet, result in zip(
                self.attempted_packets,
                self.transition_results,
                strict=True,
            )
            if result.applied
        )


class BoundedStageRunner:
    """Execute a declarative stage plan and preserve every bounded attempt."""

    _RECOVERABLE_ADVANCE_CODES = {
        "stage_not_ready",
        "unresolved_program_claims",
    }
    _DECISION_PRIORITY = {
        Decision.ADVANCE: 0,
        Decision.DEFER: 1,
        Decision.PIVOT: 2,
        Decision.HOLD: 3,
        Decision.KILL: 4,
    }

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        mapper_registry: SemanticMapperRegistry,
        planner: BoundedPlanner | None = None,
        environment: GatedDiscoveryEnvironment | None = None,
        clock=None,
    ) -> None:
        if not isinstance(tool_registry, ToolRegistry):
            raise TypeError("tool_registry must be a ToolRegistry")
        if not isinstance(mapper_registry, SemanticMapperRegistry):
            raise TypeError("mapper_registry must be a SemanticMapperRegistry")
        if planner is not None and not isinstance(planner, BoundedPlanner):
            raise TypeError("planner must be a BoundedPlanner")
        if environment is not None and not isinstance(
            environment,
            GatedDiscoveryEnvironment,
        ):
            raise TypeError("environment must be a GatedDiscoveryEnvironment")
        self.tool_registry = tool_registry
        self.mapper_registry = mapper_registry
        self.planner = planner or BoundedPlanner()
        self.environment = environment or GatedDiscoveryEnvironment()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_stage(
        self,
        *,
        run_id: str,
        state: ProgramState,
        stage_plan: StagePlan,
        promotion_contexts: Mapping[str, PromotionContext],
        execution_ledger: ToolExecutionLedger = ToolExecutionLedger(),
    ) -> StageRun:
        _require_text(run_id, "run_id")
        _require_instance(state, ProgramState, "state")
        _require_instance(stage_plan, StagePlan, "stage_plan")
        _require_instance(execution_ledger, ToolExecutionLedger, "execution_ledger")
        if not isinstance(promotion_contexts, Mapping):
            raise TypeError("promotion_contexts must be a mapping")
        contexts = dict(promotion_contexts)
        for call_id, context in contexts.items():
            _require_text(call_id, "promotion_contexts key")
            _require_instance(context, PromotionContext, "promotion_contexts value")
        known_call_ids = {call.call_id for call in stage_plan.calls}
        unknown_context_ids = sorted(set(contexts) - known_call_ids)
        if unknown_context_ids:
            plan_result = PlanResult(
                status=PlanningStatus.BLOCKED,
                plan_id=stage_plan.plan_id,
                code="promotion_context_unknown_call",
                message="Promotion contexts reference unknown stage-plan calls.",
                details={"unknown_call_ids": unknown_context_ids},
            )
            return self._planning_blocked(
                run_id,
                state,
                plan_result,
                execution_ledger,
            )

        plan_result = self.planner.plan(
            state,
            stage_plan,
            self.tool_registry,
            execution_ledger=execution_ledger,
        )
        if plan_result.status is PlanningStatus.BLOCKED:
            return self._planning_blocked(
                run_id,
                state,
                plan_result,
                execution_ledger,
            )
        missing_context_ids = tuple(
            call_id for call_id in plan_result.call_ids if call_id not in contexts
        )
        if missing_context_ids:
            blocked_result = PlanResult(
                status=PlanningStatus.BLOCKED,
                plan_id=stage_plan.plan_id,
                code="promotion_context_missing",
                message=(
                    "Every planned tool call requires an explicit promotion context "
                    "before invocation."
                ),
                skipped_call_ids=plan_result.skipped_call_ids,
                details={
                    "missing_call_ids": missing_context_ids,
                    "bounded_plan_code": plan_result.code,
                    "bounded_plan_estimated_cost": plan_result.estimated_cost,
                },
            )
            return self._planning_blocked(
                run_id,
                state,
                blocked_result,
                execution_ledger,
            )
        cutoff_violations = {
            call_id: contexts[call_id].available_at.isoformat()
            for call_id in plan_result.call_ids
            if contexts[call_id].available_at > state.as_of_date
        }
        if cutoff_violations:
            blocked_result = PlanResult(
                status=PlanningStatus.BLOCKED,
                plan_id=stage_plan.plan_id,
                code="promotion_context_after_cutoff",
                message=(
                    "Planned tool calls cannot use promotion context unavailable at "
                    "the program cutoff."
                ),
                skipped_call_ids=plan_result.skipped_call_ids,
                details={
                    "as_of_date": state.as_of_date.isoformat(),
                    "available_at_by_call_id": cutoff_violations,
                    "bounded_plan_code": plan_result.code,
                    "bounded_plan_estimated_cost": plan_result.estimated_cost,
                },
            )
            return self._planning_blocked(
                run_id,
                state,
                blocked_result,
                execution_ledger,
            )

        call_specs = {call.call_id: call for call in stage_plan.calls}
        ledger = execution_ledger
        outcomes: list[ToolOutcome] = []
        promotions: list[PromotionResult] = []
        executed_call_ids: list[str] = []
        for call_id, request in zip(
            plan_result.call_ids,
            plan_result.requests,
            strict=True,
        ):
            call = call_specs[call_id]
            outcome = self.tool_registry.execute(state, request)
            try:
                ledger = ledger.append(outcome)
            except Exception as exc:
                return self._internal_error(
                    run_id,
                    state,
                    plan_result,
                    execution_ledger,
                    outcomes=tuple(outcomes),
                    promotions=tuple(promotions),
                    code="execution_ledger_append_failed",
                    exception_type=type(exc).__name__,
                )
            outcomes.append(outcome)
            executed_call_ids.append(call_id)
            promotion = self.mapper_registry.promote(
                state,
                outcome,
                contexts[call_id],
            )
            promotions.append(promotion)
            if call.required and stage_plan.stop_on_required_failure:
                if (
                    outcome.status is not ToolStatus.SUCCEEDED
                    or promotion.status is not PromotionStatus.PROMOTED
                ):
                    break

        required_ids = set(stage_plan.required_call_ids)
        outcome_by_call = dict(zip(executed_call_ids, outcomes, strict=True))
        promotion_by_call = dict(zip(executed_call_ids, promotions, strict=True))
        required_ready = all(
            call_id in outcome_by_call
            and outcome_by_call[call_id].status is ToolStatus.SUCCEEDED
            and promotion_by_call[call_id].status is PromotionStatus.PROMOTED
            for call_id in required_ids
        )
        decision = (
            stage_plan.success_decision
            if required_ready
            else stage_plan.failure_decision
        )
        recommendations = tuple(
            item.recommended_decision
            for item in promotions
            if item.recommended_decision is not None
        )
        if recommendations:
            decision = max(
                (decision, *recommendations),
                key=self._DECISION_PRIORITY.__getitem__,
            )
        if decision is Decision.PIVOT and stage_plan.backtrack_stage is None:
            decision = stage_plan.failure_decision
            required_ready = False

        promoted = tuple(
            item for item in promotions if item.status is PromotionStatus.PROMOTED
        )
        evidence_drafts = tuple(
            draft for item in promoted for draft in item.evidence_drafts
        )
        claim_updates = tuple(
            item for result in promoted for item in result.claim_updates
        )
        disease_updates = tuple(
            item for result in promoted for item in result.disease_updates
        )
        target_updates = tuple(
            item for result in promoted for item in result.target_updates
        )
        candidate_updates = tuple(
            item for result in promoted for item in result.candidate_updates
        )
        assay_updates = tuple(
            item for result in promoted for item in result.assay_updates
        )
        model_system_updates = tuple(
            item for result in promoted for item in result.model_system_updates
        )
        intervention_updates = tuple(
            item for result in promoted for item in result.intervention_updates
        )
        trial_updates = tuple(
            item for result in promoted for item in result.trial_updates
        )
        trial_design_updates = tuple(
            item for result in promoted for item in result.trial_design_updates
        )
        clinical_endpoint_mapping_updates = tuple(
            item
            for result in promoted
            for item in result.clinical_endpoint_mapping_updates
        )
        benefit_risk_synthesis_updates = tuple(
            item
            for result in promoted
            for item in result.benefit_risk_synthesis_updates
        )
        conflict = self._artifact_conflict(
            evidence_drafts,
            claim_updates,
            disease_updates,
            target_updates,
            candidate_updates,
            assay_updates,
            model_system_updates,
            intervention_updates,
            trial_updates,
            trial_design_updates,
            clinical_endpoint_mapping_updates,
            benefit_risk_synthesis_updates,
        )
        if conflict is not None:
            return self._internal_error(
                run_id,
                state,
                plan_result,
                ledger,
                outcomes=tuple(outcomes),
                promotions=tuple(promotions),
                code=conflict,
                exception_type=None,
            )
        try:
            packet_time = self._packet_time(tuple(outcomes))
            evidence_confidences = tuple(draft.confidence for draft in evidence_drafts)
            base_confidence = (
                stage_plan.success_confidence
                if required_ready
                else stage_plan.failure_confidence
            )
            packet_confidence = min((base_confidence, *evidence_confidences))
            promotion_codes = tuple(item.code for item in promotions)
            proposal = packet_from_tool_outcomes(
                state,
                packet_id=f"{run_id}:proposal:v{state.version}",
                decision=decision,
                rationale=(
                    f"Bounded plan {stage_plan.plan_id} selected {decision.value}; "
                    f"promotion codes: {', '.join(promotion_codes) or 'none'}."
                ),
                confidence=packet_confidence,
                outcomes=tuple(outcomes),
                evidence_drafts=evidence_drafts,
                claim_updates=claim_updates,
                disease_updates=disease_updates,
                target_updates=target_updates,
                candidate_updates=candidate_updates,
                assay_updates=assay_updates,
                model_system_updates=model_system_updates,
                intervention_updates=intervention_updates,
                trial_updates=trial_updates,
                trial_design_updates=trial_design_updates,
                clinical_endpoint_mapping_updates=(
                    clinical_endpoint_mapping_updates
                ),
                benefit_risk_synthesis_updates=benefit_risk_synthesis_updates,
                next_stage=(
                    stage_plan.next_stage if decision is Decision.ADVANCE else None
                ),
                backtrack_stage=(
                    stage_plan.backtrack_stage if decision is Decision.PIVOT else None
                ),
                created_at=packet_time,
                metadata={
                    "run_id": run_id,
                    "stage_plan_id": stage_plan.plan_id,
                    "required_call_ids": stage_plan.required_call_ids,
                    "executed_call_ids": tuple(executed_call_ids),
                    "promotion_codes": promotion_codes,
                    "required_calls_ready": required_ready,
                    "bounded_policy": True,
                    "stage_plan_metadata": stage_plan.metadata,
                },
            )
        except Exception as exc:
            return self._internal_error(
                run_id,
                state,
                plan_result,
                ledger,
                outcomes=tuple(outcomes),
                promotions=tuple(promotions),
                code="decision_packet_assembly_failed",
                exception_type=type(exc).__name__,
            )

        proposal_result = self.environment.transition(state, proposal)
        attempted_packets = [proposal]
        transition_results = [proposal_result]
        if proposal_result.applied:
            return StageRun(
                run_id=run_id,
                status=StageRunStatus.COMMITTED,
                code="stage_transition_committed",
                message="Bounded stage plan produced an accepted transition.",
                initial_state=state,
                final_state=proposal_result.state,
                plan_result=plan_result,
                outcomes=tuple(outcomes),
                promotions=tuple(promotions),
                attempted_packets=tuple(attempted_packets),
                transition_results=tuple(transition_results),
                execution_ledger=ledger,
                details={"decision": proposal.decision.value},
            )

        blocking_codes = {
            item.code for item in proposal_result.verifier_results if item.blocking
        }
        can_recover = (
            stage_plan.recover_to_defer_on_readiness_block
            and proposal.decision is Decision.ADVANCE
            and blocking_codes
            and blocking_codes.issubset(self._RECOVERABLE_ADVANCE_CODES)
        )
        if can_recover:
            try:
                recovery = packet_from_tool_outcomes(
                    state,
                    packet_id=f"{run_id}:recovery-defer:v{state.version}",
                    decision=Decision.DEFER,
                    rationale=(
                        "Advance proposal failed readiness gates; preserve the bounded "
                        "observations and defer for additional evidence."
                    ),
                    confidence=min(
                        (stage_plan.failure_confidence, *evidence_confidences)
                    ),
                    outcomes=tuple(outcomes),
                    evidence_drafts=evidence_drafts,
                    claim_updates=claim_updates,
                    disease_updates=disease_updates,
                    target_updates=target_updates,
                    candidate_updates=candidate_updates,
                    assay_updates=assay_updates,
                    model_system_updates=model_system_updates,
                    intervention_updates=intervention_updates,
                    trial_updates=trial_updates,
                    trial_design_updates=trial_design_updates,
                    clinical_endpoint_mapping_updates=(
                        clinical_endpoint_mapping_updates
                    ),
                    benefit_risk_synthesis_updates=(
                        benefit_risk_synthesis_updates
                    ),
                    created_at=packet_time,
                    metadata={
                        "run_id": run_id,
                        "stage_plan_id": stage_plan.plan_id,
                        "recovered_from_packet_id": proposal.packet_id,
                        "recovered_from_blocking_codes": sorted(blocking_codes),
                        "required_call_ids": stage_plan.required_call_ids,
                        "executed_call_ids": tuple(executed_call_ids),
                        "promotion_codes": promotion_codes,
                        "bounded_policy": True,
                        "stage_plan_metadata": stage_plan.metadata,
                    },
                )
            except Exception as exc:
                return self._internal_error(
                    run_id,
                    state,
                    plan_result,
                    ledger,
                    outcomes=tuple(outcomes),
                    promotions=tuple(promotions),
                    code="defer_recovery_assembly_failed",
                    exception_type=type(exc).__name__,
                    attempted_packets=tuple(attempted_packets),
                    transition_results=tuple(transition_results),
                )
            recovery_result = self.environment.transition(state, recovery)
            attempted_packets.append(recovery)
            transition_results.append(recovery_result)
            if recovery_result.applied:
                return StageRun(
                    run_id=run_id,
                    status=StageRunStatus.COMMITTED,
                    code="stage_transition_recovered_to_defer",
                    message="Readiness-blocked advance was recovered as an accepted defer.",
                    initial_state=state,
                    final_state=recovery_result.state,
                    plan_result=plan_result,
                    outcomes=tuple(outcomes),
                    promotions=tuple(promotions),
                    attempted_packets=tuple(attempted_packets),
                    transition_results=tuple(transition_results),
                    execution_ledger=ledger,
                    recovered_to_defer=True,
                    details={"blocking_codes": sorted(blocking_codes)},
                )

        return StageRun(
            run_id=run_id,
            status=StageRunStatus.TRANSITION_BLOCKED,
            code="stage_transition_blocked",
            message="Bounded stage proposal did not pass deterministic transition gates.",
            initial_state=state,
            final_state=state,
            plan_result=plan_result,
            outcomes=tuple(outcomes),
            promotions=tuple(promotions),
            attempted_packets=tuple(attempted_packets),
            transition_results=tuple(transition_results),
            execution_ledger=ledger,
            details={
                "blocking_codes": sorted(
                    {
                        item.code
                        for result in transition_results
                        for item in result.verifier_results
                        if item.blocking
                    }
                )
            },
        )

    def _packet_time(self, outcomes: tuple[ToolOutcome, ...]) -> datetime:
        timestamp = self._clock()
        if not isinstance(timestamp, datetime):
            raise TypeError("runner clock must return datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("runner clock must return a timezone-aware datetime")
        if outcomes:
            timestamp = max(timestamp, *(item.completed_at for item in outcomes))
        return timestamp

    @staticmethod
    def _artifact_conflict(
        evidence_drafts,
        claim_updates,
        disease_updates,
        target_updates,
        candidate_updates,
        assay_updates,
        model_system_updates,
        intervention_updates,
        trial_updates,
        trial_design_updates,
        clinical_endpoint_mapping_updates,
        benefit_risk_synthesis_updates,
    ) -> str | None:
        groups = (
            (
                "promotion_evidence_id_conflict",
                [item.evidence_id for item in evidence_drafts],
            ),
            ("promotion_claim_id_conflict", [item.claim_id for item in claim_updates]),
            (
                "promotion_disease_id_conflict",
                [item.disease_id for item in disease_updates],
            ),
            (
                "promotion_target_id_conflict",
                [item.target_id for item in target_updates],
            ),
            (
                "promotion_candidate_id_conflict",
                [item.candidate_id for item in candidate_updates],
            ),
            (
                "promotion_assay_id_conflict",
                [item.assay_id for item in assay_updates],
            ),
            (
                "promotion_model_system_id_conflict",
                [item.model_system_id for item in model_system_updates],
            ),
            (
                "promotion_intervention_id_conflict",
                [item.intervention_id for item in intervention_updates],
            ),
            (
                "promotion_trial_id_conflict",
                [item.trial_id for item in trial_updates],
            ),
            (
                "promotion_trial_design_id_conflict",
                [item.design_id for item in trial_design_updates],
            ),
            (
                "promotion_clinical_endpoint_mapping_id_conflict",
                [item.mapping_id for item in clinical_endpoint_mapping_updates],
            ),
            (
                "promotion_benefit_risk_synthesis_id_conflict",
                [item.synthesis_id for item in benefit_risk_synthesis_updates],
            ),
        )
        for code, identifiers in groups:
            if len(identifiers) != len(set(identifiers)):
                return code
        return None

    @staticmethod
    def _planning_blocked(
        run_id: str,
        state: ProgramState,
        plan_result: PlanResult,
        ledger: ToolExecutionLedger,
    ) -> StageRun:
        return StageRun(
            run_id=run_id,
            status=StageRunStatus.PLANNING_BLOCKED,
            code=plan_result.code,
            message=plan_result.message,
            initial_state=state,
            final_state=state,
            plan_result=plan_result,
            execution_ledger=ledger,
            details=plan_result.details,
        )

    @staticmethod
    def _internal_error(
        run_id: str,
        state: ProgramState,
        plan_result: PlanResult,
        ledger: ToolExecutionLedger,
        *,
        outcomes: tuple[ToolOutcome, ...],
        promotions: tuple[PromotionResult, ...],
        code: str,
        exception_type: str | None,
        attempted_packets: tuple[DecisionPacket, ...] = (),
        transition_results: tuple[TransitionResult, ...] = (),
    ) -> StageRun:
        details = {"exception_type": exception_type} if exception_type else {}
        return StageRun(
            run_id=run_id,
            status=StageRunStatus.INTERNAL_ERROR,
            code=code,
            message="Stage runner failed closed before committing state.",
            initial_state=state,
            final_state=state,
            plan_result=plan_result,
            outcomes=outcomes,
            promotions=promotions,
            attempted_packets=attempted_packets,
            transition_results=transition_results,
            execution_ledger=ledger,
            details=details,
        )
