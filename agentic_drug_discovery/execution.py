"""Typed tool execution and replay contracts for discovery agents.

Tool outputs remain observations until an explicit ``EvidenceDraft`` promotes them
into the scientific ledger. This prevents adapters from silently deciding claim
polarity, confidence, or stage readiness.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .models import (
    ActionRecord,
    ActionType,
    AssayRecord,
    BenefitRiskSynthesisRecord,
    CandidateRecord,
    ClinicalEndpointMappingRecord,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    InterventionRecord,
    ModelSystemRecord,
    ProgramState,
    ScientificClaim,
    SerializableRecord,
    SourceReference,
    Stage,
    TargetRecord,
    TrialDesignRecord,
    TrialRecord,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_date,
    _require_instance,
    _require_probability,
    _require_text,
    to_primitive,
)


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class ExecutionMode(str, Enum):
    LIVE = "live"
    CACHE = "cache"
    LOCAL = "local"
    REPLAY = "replay"
    UNKNOWN = "unknown"


def _require_non_negative_number(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolContract(SerializableRecord):
    tool_id: str
    operation: str
    action_type: ActionType
    description: str
    contract_version: str = "1"
    allowed_stages: tuple[Stage, ...] = tuple(Stage)
    required_arguments: tuple[str, ...] = ()
    optional_arguments: tuple[str, ...] = ()
    default_cost: float = 0.0
    allow_extra_arguments: bool = False

    def __post_init__(self) -> None:
        for field_name in ("tool_id", "operation", "description", "contract_version"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.action_type, ActionType, "action_type")
        object.__setattr__(
            self,
            "allowed_stages",
            tuple(self.allowed_stages),
        )
        if not self.allowed_stages:
            raise ValueError("allowed_stages must not be empty")
        if len(self.allowed_stages) != len(set(self.allowed_stages)):
            raise ValueError("allowed_stages must contain unique values")
        for stage in self.allowed_stages:
            _require_instance(stage, Stage, "allowed_stages item")
        object.__setattr__(
            self,
            "required_arguments",
            _freeze_text_tuple(self.required_arguments, "required_arguments"),
        )
        object.__setattr__(
            self,
            "optional_arguments",
            _freeze_text_tuple(self.optional_arguments, "optional_arguments"),
        )
        overlap = set(self.required_arguments) & set(self.optional_arguments)
        if overlap:
            raise ValueError(
                "required_arguments and optional_arguments must not overlap"
            )
        _require_non_negative_number(self.default_cost, "default_cost")
        if not isinstance(self.allow_extra_arguments, bool):
            raise TypeError("allow_extra_arguments must be boolean")

    @property
    def key(self) -> tuple[str, str]:
        return self.tool_id, self.operation

    @property
    def contract_id(self) -> str:
        return f"{self.tool_id}.{self.operation}@{self.contract_version}"


@dataclass(frozen=True, slots=True)
class ToolRequest(SerializableRecord):
    request_id: str
    program_id: str
    expected_state_version: int
    stage: Stage
    tool_id: str
    operation: str
    action_type: ActionType
    purpose: str
    arguments: Mapping[str, Any]
    max_cost: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "program_id",
            "tool_id",
            "operation",
            "purpose",
        ):
            _require_text(getattr(self, field_name), field_name)
        if (
            not isinstance(self.expected_state_version, int)
            or isinstance(self.expected_state_version, bool)
            or self.expected_state_version < 0
        ):
            raise ValueError("expected_state_version must be a non-negative integer")
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.action_type, ActionType, "action_type")
        _require_non_negative_number(self.max_cost, "max_cost")
        _require_aware_datetime(self.created_at, "created_at")
        object.__setattr__(
            self, "arguments", _freeze_mapping(self.arguments, "arguments")
        )
        fingerprint_payload = {
            "program_id": self.program_id,
            "expected_state_version": self.expected_state_version,
            "stage": self.stage,
            "tool_id": self.tool_id,
            "operation": self.operation,
            "action_type": self.action_type,
            "arguments": self.arguments,
        }
        object.__setattr__(self, "fingerprint", _sha256_json(fingerprint_payload))


@dataclass(frozen=True, slots=True)
class ToolResponse(SerializableRecord):
    """Structured response returned by a registered adapter binding."""

    status: ToolStatus
    payload: Mapping[str, Any] = field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.UNKNOWN
    sources: tuple[SourceReference, ...] = ()
    error_code: str | None = None
    message: str = "Tool invocation completed."

    def __post_init__(self) -> None:
        _require_instance(self.status, ToolStatus, "status")
        _require_instance(self.execution_mode, ExecutionMode, "execution_mode")
        _require_text(self.message, "message")
        object.__setattr__(self, "payload", _freeze_mapping(self.payload, "payload"))
        object.__setattr__(self, "sources", tuple(self.sources))
        for source in self.sources:
            _require_instance(source, SourceReference, "sources item")
        if self.status is ToolStatus.SUCCEEDED:
            if self.error_code is not None:
                raise ValueError("successful tool responses cannot carry error_code")
        else:
            if self.error_code is None:
                raise ValueError(
                    "unavailable or failed tool responses require error_code"
                )
            _require_text(self.error_code, "error_code")


@dataclass(frozen=True, slots=True)
class ToolOutcome(SerializableRecord):
    request: ToolRequest
    contract_id: str
    status: ToolStatus
    action_type: ActionType
    payload: Mapping[str, Any]
    cost: float
    execution_mode: ExecutionMode
    completed_at: datetime
    sources: tuple[SourceReference, ...] = ()
    error_code: str | None = None
    message: str = "Tool invocation completed."
    payload_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_instance(self.request, ToolRequest, "request")
        _require_text(self.contract_id, "contract_id")
        expected_contract_prefix = f"{self.request.tool_id}.{self.request.operation}@"
        if not self.contract_id.startswith(expected_contract_prefix):
            raise ValueError("contract_id must match the requested tool operation")
        _require_instance(self.status, ToolStatus, "status")
        _require_instance(self.action_type, ActionType, "action_type")
        if self.action_type is not self.request.action_type:
            raise ValueError("outcome action_type must match request.action_type")
        _require_instance(self.execution_mode, ExecutionMode, "execution_mode")
        _require_non_negative_number(self.cost, "cost")
        if self.cost > self.request.max_cost + 1e-12:
            raise ValueError("outcome cost cannot exceed request.max_cost")
        _require_aware_datetime(self.completed_at, "completed_at")
        if self.completed_at < self.request.created_at:
            raise ValueError("completed_at cannot precede request.created_at")
        _require_text(self.message, "message")
        object.__setattr__(self, "payload", _freeze_mapping(self.payload, "payload"))
        object.__setattr__(self, "sources", tuple(self.sources))
        for source in self.sources:
            _require_instance(source, SourceReference, "sources item")
        if self.status is ToolStatus.SUCCEEDED:
            if self.error_code is not None:
                raise ValueError("successful tool outcomes cannot carry error_code")
        else:
            if self.error_code is None:
                raise ValueError(
                    "unavailable or failed tool outcomes require error_code"
                )
            _require_text(self.error_code, "error_code")
        object.__setattr__(self, "payload_sha256", _sha256_json(self.payload))

    @property
    def request_id(self) -> str:
        return self.request.request_id


@dataclass(frozen=True, slots=True)
class ToolExecutionLedger(SerializableRecord):
    outcomes: tuple[ToolOutcome, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        for outcome in self.outcomes:
            _require_instance(outcome, ToolOutcome, "outcomes item")
        request_ids = tuple(item.request_id for item in self.outcomes)
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("execution ledger request ids must be unique")

    @property
    def by_request_id(self) -> dict[str, ToolOutcome]:
        return {item.request_id: item for item in self.outcomes}

    @property
    def total_cost(self) -> float:
        return sum(float(item.cost) for item in self.outcomes)

    def append(self, outcome: ToolOutcome) -> "ToolExecutionLedger":
        if outcome.request_id in self.by_request_id:
            raise ValueError(
                f"execution ledger already contains request: {outcome.request_id}"
            )
        return replace(self, outcomes=(*self.outcomes, outcome))


ToolHandler = Callable[[Mapping[str, Any]], ToolResponse]


class ToolRegistry:
    """Execute registered tool contracts without importing adapter dependencies."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registered: dict[tuple[str, str], tuple[ToolContract, ToolHandler]] = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def contracts(self) -> tuple[ToolContract, ...]:
        return tuple(item[0] for item in self._registered.values())

    def contract_for(self, tool_id: str, operation: str) -> ToolContract | None:
        """Return one registered contract without exposing its handler."""

        registered = self._registered.get((tool_id, operation))
        return None if registered is None else registered[0]

    def register(self, contract: ToolContract, handler: ToolHandler) -> None:
        _require_instance(contract, ToolContract, "contract")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if contract.key in self._registered:
            raise ValueError(
                f"tool contract already registered: {contract.contract_id}"
            )
        self._registered[contract.key] = (contract, handler)

    def preflight(
        self,
        state: ProgramState,
        request: ToolRequest,
    ) -> ToolOutcome | None:
        """Validate one request without invoking its registered handler."""

        _require_instance(state, ProgramState, "state")
        _require_instance(request, ToolRequest, "request")
        try:
            return self._preflight(state, request)
        except Exception as exc:
            return self._failure_outcome(
                request,
                contract=self.contract_for(request.tool_id, request.operation),
                code="executor_preflight_error",
                message="Tool preflight failed closed before invocation.",
                details={"exception_type": type(exc).__name__},
                completed_at=request.created_at,
            )

    def execute(self, state: ProgramState, request: ToolRequest) -> ToolOutcome:
        _require_instance(state, ProgramState, "state")
        _require_instance(request, ToolRequest, "request")
        try:
            return self._execute(state, request)
        except Exception as exc:
            return self._failure_outcome(
                request,
                contract=self._registered.get(
                    (request.tool_id, request.operation), (None, None)
                )[0],
                code="executor_internal_error",
                message="Tool executor failed closed before producing a valid outcome.",
                details={"exception_type": type(exc).__name__},
                completed_at=request.created_at,
            )

    def replay(
        self,
        state: ProgramState,
        request: ToolRequest,
        ledger: ToolExecutionLedger,
    ) -> ToolOutcome:
        _require_instance(ledger, ToolExecutionLedger, "ledger")
        recorded = ledger.by_request_id.get(request.request_id)
        if recorded is None:
            return self._failure_outcome(
                request,
                contract=self._registered.get(
                    (request.tool_id, request.operation), (None, None)
                )[0],
                code="replay_outcome_missing",
                message="No recorded outcome exists for this tool request.",
            )
        if (
            recorded.request != request
            or recorded.request.fingerprint != request.fingerprint
        ):
            return self._failure_outcome(
                request,
                contract=self._registered.get(
                    (request.tool_id, request.operation), (None, None)
                )[0],
                code="replay_request_mismatch",
                message="Recorded outcome does not match the requested invocation.",
            )
        preflight = self._preflight(state, request)
        if preflight is not None:
            return preflight
        contract = self._registered[(request.tool_id, request.operation)][0]
        if (
            recorded.contract_id != contract.contract_id
            or recorded.action_type is not contract.action_type
            or not math.isclose(
                float(recorded.cost),
                float(contract.default_cost),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            return self._failure_outcome(
                request,
                contract=contract,
                code="replay_contract_mismatch",
                message="Recorded outcome does not match the active tool contract.",
            )
        return recorded

    def _execute(self, state: ProgramState, request: ToolRequest) -> ToolOutcome:
        preflight = self._preflight(state, request)
        if preflight is not None:
            return preflight
        contract, handler = self._registered[(request.tool_id, request.operation)]
        try:
            response = handler(request.arguments)
        except Exception as exc:
            return self._failure_outcome(
                request,
                contract=contract,
                code="tool_handler_exception",
                message="Registered tool handler raised an exception; execution failed closed.",
                details={"exception_type": type(exc).__name__},
                cost=contract.default_cost,
            )
        if not isinstance(response, ToolResponse):
            return self._failure_outcome(
                request,
                contract=contract,
                code="tool_response_contract_invalid",
                message="Registered tool handler returned an invalid response type.",
                details={"return_type": type(response).__name__},
                cost=contract.default_cost,
            )
        return ToolOutcome(
            request=request,
            contract_id=contract.contract_id,
            status=response.status,
            action_type=contract.action_type,
            payload=response.payload,
            cost=contract.default_cost,
            execution_mode=response.execution_mode,
            completed_at=self._timestamp(request),
            sources=response.sources,
            error_code=response.error_code,
            message=response.message,
        )

    def _preflight(
        self, state: ProgramState, request: ToolRequest
    ) -> ToolOutcome | None:
        try:
            state.validate_committed_history()
        except Exception as exc:
            return self._failure_outcome(
                request,
                contract=self._registered.get(
                    (request.tool_id, request.operation), (None, None)
                )[0],
                code="input_state_integrity_invalid",
                message="Input state failed committed-history validation.",
                details={"exception_type": type(exc).__name__},
            )
        context_failures: list[str] = []
        if request.program_id != state.program_id:
            context_failures.append("program_id_mismatch")
        if request.expected_state_version != state.version:
            context_failures.append("stale_state_version")
        if request.stage is not state.current_stage:
            context_failures.append("stage_mismatch")
        if (
            state.packet_history
            and request.created_at < state.packet_history[-1].created_at
        ):
            context_failures.append("request_predates_last_decision")
        if state.is_terminal:
            context_failures.append("terminal_state")
        if context_failures:
            return self._failure_outcome(
                request,
                contract=self._registered.get(
                    (request.tool_id, request.operation), (None, None)
                )[0],
                code="tool_request_context_invalid",
                message="Tool request does not match the current program state.",
                details={"failures": context_failures},
            )

        registered = self._registered.get((request.tool_id, request.operation))
        if registered is None:
            return self._failure_outcome(
                request,
                contract=None,
                code="tool_contract_not_registered",
                message="Requested tool operation has no registered contract.",
            )
        contract = registered[0]
        failures: list[str] = []
        if request.action_type is not contract.action_type:
            failures.append("action_type_mismatch")
        if request.stage not in contract.allowed_stages:
            failures.append("stage_not_allowed")
        provided = set(request.arguments)
        missing = set(contract.required_arguments) - provided
        allowed = set(contract.required_arguments) | set(contract.optional_arguments)
        extra = set() if contract.allow_extra_arguments else provided - allowed
        if missing:
            failures.append("required_arguments_missing")
        if extra:
            failures.append("unexpected_arguments")
        if contract.default_cost > request.max_cost + 1e-12:
            failures.append("cost_limit_exceeded")
        if failures:
            return self._failure_outcome(
                request,
                contract=contract,
                code="tool_request_contract_invalid",
                message="Tool request violates the registered contract.",
                details={
                    "failures": failures,
                    "missing_arguments": sorted(missing),
                    "unexpected_arguments": sorted(extra),
                    "contract_cost": contract.default_cost,
                    "max_cost": request.max_cost,
                },
            )
        return None

    def _timestamp(self, request: ToolRequest) -> datetime:
        value = self._clock()
        _require_aware_datetime(value, "clock result")
        if value < request.created_at:
            raise ValueError("clock result cannot precede request.created_at")
        return value

    def _failure_outcome(
        self,
        request: ToolRequest,
        *,
        contract: ToolContract | None,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        cost: float = 0.0,
        completed_at: datetime | None = None,
    ) -> ToolOutcome:
        timestamp = completed_at
        if timestamp is None:
            try:
                timestamp = self._timestamp(request)
            except Exception:
                timestamp = request.created_at
        return ToolOutcome(
            request=request,
            contract_id=(
                contract.contract_id
                if contract is not None
                else f"{request.tool_id}.{request.operation}@unregistered"
            ),
            status=ToolStatus.FAILED,
            action_type=contract.action_type
            if contract is not None
            else request.action_type,
            payload=details or {},
            cost=cost,
            execution_mode=ExecutionMode.UNKNOWN,
            completed_at=timestamp,
            error_code=code,
            message=message,
        )


@dataclass(frozen=True, slots=True)
class EvidenceDraft(SerializableRecord):
    evidence_id: str
    request_id: str
    subject: str
    predicate: str
    object_value: str
    observed_at: date
    available_at: date
    source_id: str | None = None
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS
    direction: str | None = None
    biological_context: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "request_id",
            "subject",
            "predicate",
            "object_value",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.observed_at, "observed_at")
        _require_date(self.available_at, "available_at")
        if self.available_at < self.observed_at:
            raise ValueError("available_at cannot precede observed_at")
        if self.source_id is not None:
            _require_text(self.source_id, "source_id")
        _require_instance(self.relation, EvidenceRelation, "relation")
        if self.direction is not None:
            _require_text(self.direction, "direction")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(
            self,
            "biological_context",
            _freeze_mapping(self.biological_context, "biological_context"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


def evidence_from_outcome(draft: EvidenceDraft, outcome: ToolOutcome) -> EvidenceEvent:
    """Promote one successful tool outcome into explicitly typed evidence."""

    if draft.request_id != outcome.request_id:
        raise ValueError("evidence draft request_id does not match the tool outcome")
    if outcome.status is not ToolStatus.SUCCEEDED:
        raise ValueError("only successful tool outcomes can be promoted to evidence")
    if draft.source_id is not None:
        matches = tuple(
            source for source in outcome.sources if source.source_id == draft.source_id
        )
        if len(matches) != 1:
            raise ValueError(
                "evidence draft source_id must resolve to exactly one outcome source"
            )
        source = matches[0]
    elif len(outcome.sources) == 1:
        source = outcome.sources[0]
    elif outcome.sources:
        raise ValueError(
            "evidence drafts for multi-source outcomes require an explicit source_id"
        )
    else:
        source = SourceReference(
            source_id=outcome.contract_id,
            source_version="tool-outcome-v1",
            locator=(
                f"tool://{outcome.request.tool_id}/{outcome.request.operation}/"
                f"{outcome.request_id}"
            ),
            content_hash=outcome.payload_sha256,
        )
    metadata = {
        **dict(draft.metadata),
        "tool_request_id": outcome.request_id,
        "tool_request_fingerprint": outcome.request.fingerprint,
        "tool_contract_id": outcome.contract_id,
        "tool_payload_sha256": outcome.payload_sha256,
        "execution_mode": outcome.execution_mode.value,
        "tool_source_count": len(outcome.sources),
        "selected_source_id": source.source_id,
    }
    return EvidenceEvent(
        evidence_id=draft.evidence_id,
        stage=outcome.request.stage,
        subject=draft.subject,
        predicate=draft.predicate,
        object_value=draft.object_value,
        source=source,
        observed_at=draft.observed_at,
        available_at=draft.available_at,
        relation=draft.relation,
        direction=draft.direction,
        biological_context=draft.biological_context,
        confidence=draft.confidence,
        metadata=metadata,
    )


def action_from_outcome(
    outcome: ToolOutcome,
    *,
    evidence_ids: tuple[str, ...] = (),
    action_id: str | None = None,
) -> ActionRecord:
    """Create the compact action-ledger record linked to a full tool outcome."""

    metadata = {
        "tool_request_id": outcome.request_id,
        "tool_request_fingerprint": outcome.request.fingerprint,
        "tool_contract_id": outcome.contract_id,
        "tool_payload_sha256": outcome.payload_sha256,
        "tool_status": outcome.status.value,
        "execution_mode": outcome.execution_mode.value,
        "completed_at": outcome.completed_at.isoformat(),
        "error_code": outcome.error_code,
    }
    return ActionRecord(
        action_id=action_id or outcome.request_id,
        action_type=outcome.action_type,
        purpose=outcome.request.purpose,
        cost=outcome.cost,
        evidence_ids=evidence_ids,
        metadata=metadata,
    )


def packet_from_tool_outcomes(
    state: ProgramState,
    *,
    packet_id: str,
    decision: Decision,
    rationale: str,
    confidence: float,
    outcomes: tuple[ToolOutcome, ...],
    evidence_drafts: tuple[EvidenceDraft, ...] = (),
    claim_updates: tuple[ScientificClaim, ...] = (),
    disease_updates: tuple[DiseaseRecord, ...] = (),
    target_updates: tuple[TargetRecord, ...] = (),
    candidate_updates: tuple[CandidateRecord, ...] = (),
    assay_updates: tuple[AssayRecord, ...] = (),
    model_system_updates: tuple[ModelSystemRecord, ...] = (),
    intervention_updates: tuple[InterventionRecord, ...] = (),
    trial_updates: tuple[TrialRecord, ...] = (),
    trial_design_updates: tuple[TrialDesignRecord, ...] = (),
    clinical_endpoint_mapping_updates: tuple[ClinicalEndpointMappingRecord, ...] = (),
    benefit_risk_synthesis_updates: tuple[BenefitRiskSynthesisRecord, ...] = (),
    next_stage: Stage | None = None,
    backtrack_stage: Stage | None = None,
    created_at: datetime,
    metadata: Mapping[str, Any] | None = None,
) -> DecisionPacket:
    """Assemble a decision packet while keeping full tool payloads in a replay ledger."""

    _require_instance(state, ProgramState, "state")
    _require_aware_datetime(created_at, "created_at")
    outcome_by_request: dict[str, ToolOutcome] = {}
    for outcome in outcomes:
        _require_instance(outcome, ToolOutcome, "outcomes item")
        if outcome.request_id in outcome_by_request:
            raise ValueError(f"duplicate tool outcome request id: {outcome.request_id}")
        if (
            outcome.request.program_id != state.program_id
            or outcome.request.expected_state_version != state.version
            or outcome.request.stage is not state.current_stage
        ):
            raise ValueError(
                f"tool outcome is stale or outside state context: {outcome.request_id}"
            )
        if created_at < outcome.completed_at:
            raise ValueError(
                f"packet cannot predate linked tool outcome: {outcome.request_id}"
            )
        outcome_by_request[outcome.request_id] = outcome

    drafts_by_request: dict[str, list[EvidenceDraft]] = {
        request_id: [] for request_id in outcome_by_request
    }
    for draft in evidence_drafts:
        _require_instance(draft, EvidenceDraft, "evidence_drafts item")
        if draft.request_id not in outcome_by_request:
            raise ValueError(
                f"evidence draft references unknown tool request: {draft.request_id}"
            )
        drafts_by_request[draft.request_id].append(draft)

    evidence_additions = tuple(
        evidence_from_outcome(draft, outcome_by_request[draft.request_id])
        for draft in evidence_drafts
    )
    actions = tuple(
        action_from_outcome(
            outcome,
            evidence_ids=tuple(
                draft.evidence_id for draft in drafts_by_request[outcome.request_id]
            ),
        )
        for outcome in outcomes
    )
    packet_metadata = {
        **dict(metadata or {}),
        "tool_request_ids": [item.request_id for item in outcomes],
        "tool_outcome_hashes": {
            item.request_id: item.payload_sha256 for item in outcomes
        },
        "full_tool_payloads_external_to_packet": True,
    }
    return DecisionPacket(
        packet_id=packet_id,
        program_id=state.program_id,
        expected_state_version=state.version,
        stage=state.current_stage,
        decision=decision,
        rationale=rationale,
        confidence=confidence,
        actions=actions,
        evidence_additions=evidence_additions,
        claim_updates=claim_updates,
        disease_updates=disease_updates,
        target_updates=target_updates,
        candidate_updates=candidate_updates,
        assay_updates=assay_updates,
        model_system_updates=model_system_updates,
        intervention_updates=intervention_updates,
        trial_updates=trial_updates,
        trial_design_updates=trial_design_updates,
        clinical_endpoint_mapping_updates=clinical_endpoint_mapping_updates,
        benefit_risk_synthesis_updates=benefit_risk_synthesis_updates,
        next_stage=next_stage,
        backtrack_stage=backtrack_stage,
        created_at=created_at,
        metadata=packet_metadata,
    )
