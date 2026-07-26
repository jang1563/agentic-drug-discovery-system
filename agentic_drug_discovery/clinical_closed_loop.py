"""Bounded clinical evidence execution and provenance-preserving refresh."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from .clinical_decision import (
    CLINICAL_DECISION_PACKAGE_SCHEMA_VERSION,
    CLINICAL_WORKFLOW_SCOPE,
    ClinicalDecisionPackage,
    ClinicalEvidenceGapCode,
    clinical_decision_package_from_dict,
    compile_clinical_decision_package,
    validate_clinical_decision_package,
)
from .environment import GatedDiscoveryEnvironment
from .execution import (
    ExecutionMode,
    ToolExecutionLedger,
    ToolOutcome,
    ToolRegistry,
    ToolStatus,
)
from .models import (
    ActionRecord,
    ActionType,
    BenefitRiskSynthesisRecord,
    Decision,
    DecisionPacket,
    ProgramState,
    SerializableRecord,
    SourceReference,
    Stage,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_date,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .orchestration import BoundedStageRunner, StageRun, StageRunStatus
from .planning import BoundedPlanner, StagePlan, ToolCallSpec
from .promotion import (
    PromotionContext,
    PromotionStatus,
    SemanticMapperRegistry,
)
from .serialization import RecordParseError


CLINICAL_CLOSED_LOOP_SCHEMA_VERSION = "adds.clinical-evidence-closed-loop-transition.v1"
CLINICAL_CLOSED_LOOP_METHOD_ID = "adds.provenance-preserving-clinical-closed-loop.v1"
CLINICAL_EXECUTION_BATCH_METHOD_ID = "adds.bounded-clinical-evidence-execution.v1"

_ALLOWED_ACQUISITION_ACTION_TYPES = {
    ActionType.RETRIEVE_EVIDENCE,
    ActionType.QUERY_DATABASE,
    ActionType.RUN_VERIFIER,
}
_GAP_ORDER = tuple(ClinicalEvidenceGapCode)
_GAP_INDEX = {code: index for index, code in enumerate(_GAP_ORDER)}
_REQUIRED_LIMITATIONS = (
    (
        "Provider outputs remain observations until explicit semantic promotion "
        "and deterministic state-transition verification succeed."
    ),
    (
        "Refresh runs are bounded reviewer-verifier transformations; providers "
        "cannot directly issue clinical decisions or rewrite committed artifacts."
    ),
    (
        "Resolved gaps are policy-relative evidence-workflow transitions, not "
        "treatment, regulatory, or clinical acceptability conclusions."
    ),
    (
        "Attempted catalog action identifiers are single-use in this transition; "
        "a retry requires an explicitly revised catalog action."
    ),
    (
        "ADVANCE remains evidence-workflow readiness only and never constitutes "
        "a terminal development or patient-care recommendation."
    ),
)
_REFRESH_FORBIDDEN_UPDATE_FIELDS = (
    "disease_updates",
    "target_updates",
    "candidate_updates",
    "assay_updates",
    "model_system_updates",
    "intervention_updates",
    "trial_updates",
    "trial_design_updates",
)


class ClinicalClosedLoopError(ValueError):
    """Raised when a clinical evidence cycle cannot be bound safely."""


class ClinicalReceiptSourceMode(str, Enum):
    PROVIDER_DECLARED = "provider_declared"
    PAYLOAD_FALLBACK = "payload_fallback"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


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


def _require_sorted_unique_text(
    values: Sequence[str],
    field_name: str,
) -> tuple[str, ...]:
    result = _freeze_text_tuple(values, field_name)
    if result != tuple(sorted(result)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return result


def _require_gap_codes(
    values: Sequence[ClinicalEvidenceGapCode],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[ClinicalEvidenceGapCode, ...]:
    result = tuple(values)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must contain unique values")
    for value in result:
        _require_instance(value, ClinicalEvidenceGapCode, f"{field_name} item")
    if result != tuple(sorted(result, key=_GAP_INDEX.__getitem__)):
        raise ValueError(f"{field_name} must use canonical gap-code order")
    return result


def _round_metric(value: float) -> float:
    return round(float(value), 12)


@dataclass(frozen=True, slots=True)
class ClinicalClosedLoopPolicy(SerializableRecord):
    """Preregistered bounds for provider execution and reviewer refresh."""

    policy_id: str
    version: str
    registered_on: date
    max_refresh_runs: int
    max_refresh_actions: int
    max_refresh_cost: float
    require_committed_runs: bool = True
    require_refresh_verifier_actions: bool = True
    require_new_source_provenance_for_resolution: bool = True
    consume_attempted_actions: bool = True
    provider_auto_decision_prohibited: bool = True
    terminal_decisions_prohibited: bool = True
    workflow_scope: str = CLINICAL_WORKFLOW_SCOPE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        _require_positive_int(self.max_refresh_runs, "max_refresh_runs")
        _require_positive_int(self.max_refresh_actions, "max_refresh_actions")
        _require_non_negative_number(self.max_refresh_cost, "max_refresh_cost")
        for field_name in (
            "require_committed_runs",
            "require_refresh_verifier_actions",
            "require_new_source_provenance_for_resolution",
            "consume_attempted_actions",
            "provider_auto_decision_prohibited",
            "terminal_decisions_prohibited",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")
        if self.workflow_scope != CLINICAL_WORKFLOW_SCOPE:
            raise ValueError(f"workflow_scope must be {CLINICAL_WORKFLOW_SCOPE}")
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata, "metadata"),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceExecutionCall(SerializableRecord):
    """One selected action compiled into an exact bounded tool call."""

    rank: int
    call_id: str
    action_id: str
    action_fingerprint: str
    selection_fingerprint: str
    targeted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    targeted_gap_ids: tuple[str, ...]
    tool_id: str
    operation: str
    action_type: ActionType
    purpose: str
    arguments: Mapping[str, Any]
    max_cost: float

    def __post_init__(self) -> None:
        _require_positive_int(self.rank, "rank")
        for field_name in (
            "call_id",
            "action_id",
            "tool_id",
            "operation",
            "purpose",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.action_fingerprint, "action_fingerprint")
        _require_sha256(self.selection_fingerprint, "selection_fingerprint")
        object.__setattr__(
            self,
            "targeted_gap_codes",
            _require_gap_codes(
                self.targeted_gap_codes,
                "targeted_gap_codes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "targeted_gap_ids",
            _require_sorted_unique_text(
                self.targeted_gap_ids,
                "targeted_gap_ids",
            ),
        )
        if not self.targeted_gap_ids:
            raise ValueError("targeted_gap_ids must not be empty")
        _require_instance(self.action_type, ActionType, "action_type")
        if self.action_type not in _ALLOWED_ACQUISITION_ACTION_TYPES:
            raise ValueError("unsupported clinical acquisition action type")
        object.__setattr__(
            self,
            "arguments",
            _freeze_mapping(self.arguments, "arguments"),
        )
        _require_non_negative_number(self.max_cost, "max_cost")
        if self.max_cost <= 0:
            raise ValueError("max_cost must be positive")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceExecutionBatch(SerializableRecord):
    """Exact selected-action batch bound to one state and decision package."""

    batch_id: str
    method_id: str
    program_id: str
    expected_state_version: int
    as_of_date: date
    stage: Stage
    decision_package_id: str
    decision_package_fingerprint: str
    tensor_id: str
    tensor_fingerprint: str
    plan_id: str
    plan_fingerprint: str
    decision_policy_id: str
    decision_policy_version: str
    decision_policy_fingerprint: str
    closed_loop_policy: ClinicalClosedLoopPolicy
    calls: tuple[ClinicalEvidenceExecutionCall, ...]
    max_steps: int
    max_total_cost: float
    workflow_scope: str = CLINICAL_WORKFLOW_SCOPE
    provider_auto_decision_issued: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "batch_id",
            "program_id",
            "decision_package_id",
            "tensor_id",
            "plan_id",
            "decision_policy_id",
            "decision_policy_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_EXECUTION_BATCH_METHOD_ID:
            raise ValueError("method_id is unsupported")
        _require_non_negative_int(
            self.expected_state_version,
            "expected_state_version",
        )
        _require_date(self.as_of_date, "as_of_date")
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "decision_package_fingerprint",
            "tensor_fingerprint",
            "plan_fingerprint",
            "decision_policy_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_instance(
            self.closed_loop_policy,
            ClinicalClosedLoopPolicy,
            "closed_loop_policy",
        )
        calls = tuple(self.calls)
        object.__setattr__(self, "calls", calls)
        if not calls:
            raise ValueError("execution batch requires at least one call")
        for call in calls:
            _require_instance(call, ClinicalEvidenceExecutionCall, "calls item")
        if tuple(item.rank for item in calls) != tuple(range(1, len(calls) + 1)):
            raise ValueError("execution call ranks must be contiguous")
        if len({item.action_id for item in calls}) != len(calls):
            raise ValueError("execution action ids must be unique")
        expected_call_ids = tuple(
            f"{self.batch_id}:call:{item.rank:02d}:{item.action_id}" for item in calls
        )
        if tuple(item.call_id for item in calls) != expected_call_ids:
            raise ValueError("call ids are not bound to batch, rank, and action")
        _require_positive_int(self.max_steps, "max_steps")
        if self.max_steps != len(calls):
            raise ValueError("max_steps must equal the selected call count")
        _require_non_negative_number(self.max_total_cost, "max_total_cost")
        expected_cost = _round_metric(sum(item.max_cost for item in calls))
        if not math.isclose(
            self.max_total_cost,
            expected_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("max_total_cost does not match execution calls")
        if self.workflow_scope != CLINICAL_WORKFLOW_SCOPE:
            raise ValueError("workflow_scope is unsupported")
        _require_bool(
            self.provider_auto_decision_issued,
            "provider_auto_decision_issued",
        )
        if self.provider_auto_decision_issued:
            raise ValueError("providers cannot issue clinical decisions")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalToolOutcomeReceipt(SerializableRecord):
    """Compact receipt for one exact request, outcome, and committed action."""

    call_id: str
    program_id: str
    request_id: str
    request_fingerprint: str
    expected_state_version: int
    stage: Stage
    tool_id: str
    operation: str
    action_type: ActionType
    purpose: str
    arguments: Mapping[str, Any]
    max_cost: float
    request_created_at: datetime
    contract_id: str
    status: ToolStatus
    execution_mode: ExecutionMode
    payload_sha256: str
    source_mode: ClinicalReceiptSourceMode
    sources: tuple[SourceReference, ...]
    cost: float
    completed_at: datetime
    error_code: str | None
    accepted_packet_id: str
    action_ledger_id: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "call_id",
            "program_id",
            "request_id",
            "tool_id",
            "operation",
            "purpose",
            "contract_id",
            "accepted_packet_id",
            "action_ledger_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.request_fingerprint, "request_fingerprint")
        _require_non_negative_int(
            self.expected_state_version,
            "expected_state_version",
        )
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.action_type, ActionType, "action_type")
        object.__setattr__(
            self,
            "arguments",
            _freeze_mapping(self.arguments, "arguments"),
        )
        _require_non_negative_number(self.max_cost, "max_cost")
        _require_aware_datetime(self.request_created_at, "request_created_at")
        if not self.contract_id.startswith(f"{self.tool_id}.{self.operation}@"):
            raise ValueError("contract_id does not match tool operation")
        _require_instance(self.status, ToolStatus, "status")
        _require_instance(self.execution_mode, ExecutionMode, "execution_mode")
        _require_sha256(self.payload_sha256, "payload_sha256")
        _require_instance(
            self.source_mode,
            ClinicalReceiptSourceMode,
            "source_mode",
        )
        sources = tuple(self.sources)
        object.__setattr__(self, "sources", sources)
        if not sources:
            raise ValueError("receipt sources must not be empty")
        for source in sources:
            _require_instance(source, SourceReference, "sources item")
            if source.content_hash is None:
                raise ValueError("receipt sources require content hashes")
            _require_sha256(source.content_hash, "source content_hash")
        source_keys = tuple(
            (
                item.source_id,
                item.source_version,
                item.locator,
                item.content_hash,
            )
            for item in sources
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("receipt sources must be unique")
        if source_keys != tuple(sorted(source_keys)):
            raise ValueError("receipt sources must use canonical order")
        if self.source_mode is ClinicalReceiptSourceMode.PAYLOAD_FALLBACK:
            expected = (
                SourceReference(
                    source_id=self.contract_id,
                    source_version="tool-outcome-v1",
                    locator=(
                        f"tool://{self.tool_id}/{self.operation}/{self.request_id}"
                    ),
                    content_hash=self.payload_sha256,
                ),
            )
            if sources != expected:
                raise ValueError("payload fallback source is not canonical")
        _require_non_negative_number(self.cost, "cost")
        if self.cost > self.max_cost + 1e-12:
            raise ValueError("receipt cost exceeds request max_cost")
        _require_aware_datetime(self.completed_at, "completed_at")
        if self.completed_at < self.request_created_at:
            raise ValueError("completed_at precedes request_created_at")
        if self.status is ToolStatus.SUCCEEDED:
            if self.error_code is not None:
                raise ValueError("successful receipts cannot carry error_code")
        else:
            if self.error_code is None:
                raise ValueError("non-success receipts require error_code")
            _require_text(self.error_code, "error_code")
        object.__setattr__(
            self,
            "evidence_ids",
            _require_sorted_unique_text(self.evidence_ids, "evidence_ids"),
        )
        if self.action_ledger_id != self.request_id:
            raise ValueError("action_ledger_id must equal the deterministic request id")
        if self.status is not ToolStatus.SUCCEEDED and self.evidence_ids:
            raise ValueError("unsuccessful outcomes cannot promote evidence")
        expected_request_fingerprint = _sha256(
            {
                "program_id": self.program_id,
                "expected_state_version": self.expected_state_version,
                "stage": self.stage,
                "tool_id": self.tool_id,
                "operation": self.operation,
                "action_type": self.action_type,
                "arguments": self.arguments,
            }
        )
        if self.request_fingerprint != expected_request_fingerprint:
            raise ValueError("request_fingerprint does not match request fields")

    @property
    def source_content_hashes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.content_hash
                    for item in self.sources
                    if item.content_hash is not None
                }
            )
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalSelectedActionReceipt(SerializableRecord):
    """Outcome receipt bound to one selected bounded-VOI action."""

    rank: int
    action_id: str
    action_fingerprint: str
    selection_fingerprint: str
    targeted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    targeted_gap_ids: tuple[str, ...]
    outcome: ClinicalToolOutcomeReceipt

    def __post_init__(self) -> None:
        _require_positive_int(self.rank, "rank")
        _require_text(self.action_id, "action_id")
        _require_sha256(self.action_fingerprint, "action_fingerprint")
        _require_sha256(self.selection_fingerprint, "selection_fingerprint")
        object.__setattr__(
            self,
            "targeted_gap_codes",
            _require_gap_codes(
                self.targeted_gap_codes,
                "targeted_gap_codes",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "targeted_gap_ids",
            _require_sorted_unique_text(
                self.targeted_gap_ids,
                "targeted_gap_ids",
            ),
        )
        if not self.targeted_gap_ids:
            raise ValueError("targeted_gap_ids must not be empty")
        _require_instance(
            self.outcome,
            ClinicalToolOutcomeReceipt,
            "outcome",
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalRefreshRunReceipt(SerializableRecord):
    """One committed reviewer-verifier refresh run."""

    run_id: str
    plan_id: str
    initial_state_version: int
    final_state_version: int
    stage: Stage
    accepted_packet_id: str
    decision: Decision
    outcomes: tuple[ClinicalToolOutcomeReceipt, ...]
    promotion_codes: tuple[str, ...]
    action_cost: float

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "plan_id",
            "accepted_packet_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_non_negative_int(
            self.initial_state_version,
            "initial_state_version",
        )
        _require_non_negative_int(
            self.final_state_version,
            "final_state_version",
        )
        if self.final_state_version != self.initial_state_version + 1:
            raise ValueError("refresh runs must commit exactly one state transition")
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.decision, Decision, "decision")
        if self.decision is not Decision.HOLD:
            raise ValueError("refresh runs must preserve a non-terminal HOLD state")
        outcomes = tuple(self.outcomes)
        object.__setattr__(self, "outcomes", outcomes)
        if not outcomes:
            raise ValueError("refresh receipts require at least one outcome")
        for outcome in outcomes:
            _require_instance(
                outcome,
                ClinicalToolOutcomeReceipt,
                "outcomes item",
            )
            if outcome.action_type is not ActionType.RUN_VERIFIER:
                raise ValueError("refresh outcomes must be reviewer-verifier actions")
            if outcome.status is not ToolStatus.SUCCEEDED:
                raise ValueError("refresh outcomes must succeed")
            if outcome.expected_state_version != self.initial_state_version:
                raise ValueError("refresh outcome state version mismatch")
            if outcome.stage is not self.stage:
                raise ValueError("refresh outcome stage mismatch")
            if outcome.accepted_packet_id != self.accepted_packet_id:
                raise ValueError("refresh outcome packet mismatch")
        object.__setattr__(
            self,
            "promotion_codes",
            _freeze_text_tuple(
                self.promotion_codes,
                "promotion_codes",
                unique=False,
            ),
        )
        if len(self.promotion_codes) != len(outcomes):
            raise ValueError("promotion_codes must align with refresh outcomes")
        _require_non_negative_number(self.action_cost, "action_cost")
        expected_cost = _round_metric(sum(item.cost for item in outcomes))
        if not math.isclose(
            self.action_cost,
            expected_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("refresh action_cost does not match outcomes")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalEvidenceTransitionPackage(SerializableRecord):
    """Integrity-bound before/action/refresh/after clinical evidence cycle."""

    transition_id: str
    method_id: str
    program_id: str
    as_of_date: date
    before_state_version: int
    after_state_version: int
    closed_loop_policy: ClinicalClosedLoopPolicy
    execution_batch: ClinicalEvidenceExecutionBatch
    before_package: ClinicalDecisionPackage
    selected_action_receipts: tuple[ClinicalSelectedActionReceipt, ...]
    refresh_receipts: tuple[ClinicalRefreshRunReceipt, ...]
    after_package: ClinicalDecisionPackage
    accepted_packet_ids: tuple[str, ...]
    consumed_action_ids: tuple[str, ...]
    remaining_action_ids: tuple[str, ...]
    resolved_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    persisted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    new_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    added_source_content_hashes: tuple[str, ...]
    removed_source_content_hashes: tuple[str, ...]
    acquisition_cost: float
    refresh_cost: float
    total_cost: float
    budget_spent_before: float
    budget_spent_after: float
    before_decision: Decision
    after_decision: Decision
    workflow_scope: str = CLINICAL_WORKFLOW_SCOPE
    clinical_acceptability_inferred: bool = False
    terminal_decision_issued: bool = False
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in ("transition_id", "program_id"):
            _require_text(getattr(self, field_name), field_name)
        if self.method_id != CLINICAL_CLOSED_LOOP_METHOD_ID:
            raise ValueError("method_id is unsupported")
        _require_date(self.as_of_date, "as_of_date")
        _require_non_negative_int(
            self.before_state_version,
            "before_state_version",
        )
        _require_non_negative_int(
            self.after_state_version,
            "after_state_version",
        )
        _require_instance(
            self.closed_loop_policy,
            ClinicalClosedLoopPolicy,
            "closed_loop_policy",
        )
        _require_instance(
            self.execution_batch,
            ClinicalEvidenceExecutionBatch,
            "execution_batch",
        )
        _require_instance(
            self.before_package,
            ClinicalDecisionPackage,
            "before_package",
        )
        _require_instance(
            self.after_package,
            ClinicalDecisionPackage,
            "after_package",
        )
        selected = tuple(self.selected_action_receipts)
        object.__setattr__(self, "selected_action_receipts", selected)
        if not selected:
            raise ValueError("transition requires selected action receipts")
        for receipt in selected:
            _require_instance(
                receipt,
                ClinicalSelectedActionReceipt,
                "selected_action_receipts item",
            )
        if tuple(item.rank for item in selected) != tuple(range(1, len(selected) + 1)):
            raise ValueError("selected receipt ranks must be contiguous")
        if len({item.action_id for item in selected}) != len(selected):
            raise ValueError("selected receipt action ids must be unique")
        refresh = tuple(self.refresh_receipts)
        object.__setattr__(self, "refresh_receipts", refresh)
        for receipt in refresh:
            _require_instance(
                receipt,
                ClinicalRefreshRunReceipt,
                "refresh_receipts item",
            )
        if len(refresh) > self.closed_loop_policy.max_refresh_runs:
            raise ValueError("refresh run count exceeds closed-loop policy")
        refresh_action_count = sum(len(item.outcomes) for item in refresh)
        if refresh_action_count > self.closed_loop_policy.max_refresh_actions:
            raise ValueError("refresh action count exceeds closed-loop policy")
        if (
            self.program_id != self.before_package.program_id
            or self.program_id != self.after_package.program_id
            or self.program_id != self.execution_batch.program_id
        ):
            raise ValueError("program ids do not match across transition")
        if (
            self.as_of_date != self.before_package.as_of_date
            or self.as_of_date != self.after_package.as_of_date
            or self.as_of_date != self.execution_batch.as_of_date
        ):
            raise ValueError("cutoff dates do not match across transition")
        if self.execution_batch.closed_loop_policy != self.closed_loop_policy:
            raise ValueError("execution batch closed-loop policy mismatch")
        if (
            self.execution_batch.decision_package_id != self.before_package.package_id
            or self.execution_batch.decision_package_fingerprint
            != self.before_package.fingerprint
            or self.execution_batch.tensor_id != self.before_package.tensor.tensor_id
            or self.execution_batch.tensor_fingerprint
            != self.before_package.tensor.fingerprint
            or self.execution_batch.plan_id != self.before_package.plan.plan_id
            or self.execution_batch.plan_fingerprint
            != self.before_package.plan.fingerprint
            or self.execution_batch.decision_policy_id
            != self.before_package.policy.policy_id
            or self.execution_batch.decision_policy_version
            != self.before_package.policy.version
            or self.execution_batch.decision_policy_fingerprint
            != self.before_package.policy.fingerprint
        ):
            raise ValueError("execution batch is not bound to before package")
        if self.before_package.plan.decision is not Decision.HOLD:
            raise ValueError("closed-loop execution requires a HOLD before package")
        calls = self.execution_batch.calls
        if len(selected) > len(calls):
            raise ValueError("receipts exceed execution batch calls")
        for call, receipt in zip(calls, selected, strict=False):
            expected_request_id = (
                f"{self.execution_batch.batch_id}:v{self.before_state_version}:"
                f"{call.call_id}"
            )
            if (
                receipt.rank != call.rank
                or receipt.action_id != call.action_id
                or receipt.action_fingerprint != call.action_fingerprint
                or receipt.selection_fingerprint != call.selection_fingerprint
                or receipt.targeted_gap_codes != call.targeted_gap_codes
                or receipt.targeted_gap_ids != call.targeted_gap_ids
                or receipt.outcome.call_id != call.call_id
                or receipt.outcome.tool_id != call.tool_id
                or receipt.outcome.operation != call.operation
                or receipt.outcome.action_type is not call.action_type
                or receipt.outcome.purpose != call.purpose
                or receipt.outcome.arguments != call.arguments
                or receipt.outcome.program_id != self.program_id
                or receipt.outcome.expected_state_version != self.before_state_version
                or receipt.outcome.stage is not self.execution_batch.stage
                or receipt.outcome.request_id != expected_request_id
                or not math.isclose(
                    receipt.outcome.max_cost,
                    call.max_cost,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ):
                raise ValueError("selected receipt is not bound to execution call")
        acquisition_packet_ids = {item.outcome.accepted_packet_id for item in selected}
        if len(acquisition_packet_ids) != 1:
            raise ValueError("selected receipts must share one accepted packet")
        expected_version_delta = 1 + len(refresh)
        if self.after_state_version != (
            self.before_state_version + expected_version_delta
        ):
            raise ValueError("state version delta does not match committed runs")
        if self.execution_batch.expected_state_version != self.before_state_version:
            raise ValueError("execution batch state version mismatch")
        for index, receipt in enumerate(refresh):
            expected_initial = self.before_state_version + 1 + index
            if (
                receipt.initial_state_version != expected_initial
                or receipt.final_state_version != expected_initial + 1
            ):
                raise ValueError("refresh receipt versions are not contiguous")
            if any(
                outcome.program_id != self.program_id for outcome in receipt.outcomes
            ):
                raise ValueError("refresh outcome program id mismatch")
        expected_packet_ids = (
            selected[0].outcome.accepted_packet_id,
            *(item.accepted_packet_id for item in refresh),
        )
        object.__setattr__(
            self,
            "accepted_packet_ids",
            _freeze_text_tuple(
                self.accepted_packet_ids,
                "accepted_packet_ids",
            ),
        )
        if self.accepted_packet_ids != expected_packet_ids:
            raise ValueError("accepted_packet_ids do not match receipts")
        expected_consumed = tuple(item.action_id for item in selected)
        object.__setattr__(
            self,
            "consumed_action_ids",
            _freeze_text_tuple(
                self.consumed_action_ids,
                "consumed_action_ids",
            ),
        )
        if self.consumed_action_ids != expected_consumed:
            raise ValueError("consumed_action_ids do not match selected receipts")
        expected_remaining_catalog = tuple(
            item
            for item in self.before_package.action_catalog
            if item.action_id not in set(expected_consumed)
        )
        if self.after_package.action_catalog != expected_remaining_catalog:
            raise ValueError("after catalog did not consume attempted actions")
        expected_remaining_ids = tuple(
            item.action_id for item in expected_remaining_catalog
        )
        object.__setattr__(
            self,
            "remaining_action_ids",
            _freeze_text_tuple(
                self.remaining_action_ids,
                "remaining_action_ids",
            ),
        )
        if self.remaining_action_ids != expected_remaining_ids:
            raise ValueError("remaining_action_ids do not match after catalog")
        if self.before_package.policy != self.after_package.policy:
            raise ValueError("clinical decision policy changed within transition")
        before_tensor = self.before_package.tensor
        after_tensor = self.after_package.tensor
        for field_name in (
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_family",
            "effect_measure",
            "safety_measure",
            "stage",
        ):
            if getattr(before_tensor, field_name) != getattr(after_tensor, field_name):
                raise ValueError(f"tensor {field_name} changed within transition")
        before_codes = {item.code for item in before_tensor.gaps}
        after_codes = {item.code for item in after_tensor.gaps}
        expected_resolved = tuple(
            sorted(before_codes - after_codes, key=_GAP_INDEX.__getitem__)
        )
        expected_persisted = tuple(
            sorted(before_codes & after_codes, key=_GAP_INDEX.__getitem__)
        )
        expected_new = tuple(
            sorted(after_codes - before_codes, key=_GAP_INDEX.__getitem__)
        )
        for field_name, expected in (
            ("resolved_gap_codes", expected_resolved),
            ("persisted_gap_codes", expected_persisted),
            ("new_gap_codes", expected_new),
        ):
            observed = _require_gap_codes(
                getattr(self, field_name),
                field_name,
                allow_empty=True,
            )
            object.__setattr__(self, field_name, observed)
            if observed != expected:
                raise ValueError(f"{field_name} does not match tensor transition")
        before_hashes = set(before_tensor.source_content_hashes)
        after_hashes = set(after_tensor.source_content_hashes)
        expected_added = tuple(sorted(after_hashes - before_hashes))
        expected_removed = tuple(sorted(before_hashes - after_hashes))
        object.__setattr__(
            self,
            "added_source_content_hashes",
            _require_sorted_unique_text(
                self.added_source_content_hashes,
                "added_source_content_hashes",
            ),
        )
        object.__setattr__(
            self,
            "removed_source_content_hashes",
            _require_sorted_unique_text(
                self.removed_source_content_hashes,
                "removed_source_content_hashes",
            ),
        )
        for field_name in (
            "added_source_content_hashes",
            "removed_source_content_hashes",
        ):
            for digest in getattr(self, field_name):
                _require_sha256(digest, f"{field_name} item")
        if self.added_source_content_hashes != expected_added:
            raise ValueError("added source hashes do not match tensor transition")
        if self.removed_source_content_hashes != expected_removed:
            raise ValueError("removed source hashes do not match tensor transition")
        successful_source_hashes = {
            digest
            for item in selected
            if item.outcome.status is ToolStatus.SUCCEEDED
            for digest in item.outcome.source_content_hashes
        }
        if not set(expected_added).issubset(successful_source_hashes):
            raise ValueError("new tensor sources are not bound to successful actions")
        if (
            before_tensor.synthesis_fingerprint != after_tensor.synthesis_fingerprint
            and not expected_added
        ):
            raise ValueError("changed synthesis lacks new action-bound provenance")
        for code in expected_resolved:
            matching = tuple(
                item
                for item in selected
                if item.outcome.status is ToolStatus.SUCCEEDED
                and code in item.targeted_gap_codes
                and set(item.outcome.source_content_hashes) & set(expected_added)
            )
            if not matching:
                raise ValueError("resolved gap lacks targeted successful source rejoin")
        for field_name in (
            "acquisition_cost",
            "refresh_cost",
            "total_cost",
            "budget_spent_before",
            "budget_spent_after",
        ):
            _require_non_negative_number(getattr(self, field_name), field_name)
        expected_acquisition_cost = _round_metric(
            sum(item.outcome.cost for item in selected)
        )
        expected_refresh_cost = _round_metric(sum(item.action_cost for item in refresh))
        if not math.isclose(
            self.acquisition_cost,
            expected_acquisition_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("acquisition_cost does not match receipts")
        if not math.isclose(
            self.refresh_cost,
            expected_refresh_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("refresh_cost does not match receipts")
        if self.refresh_cost > self.closed_loop_policy.max_refresh_cost + 1e-12:
            raise ValueError("refresh_cost exceeds closed-loop policy")
        if not math.isclose(
            self.total_cost,
            self.acquisition_cost + self.refresh_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("total_cost does not match cycle costs")
        if not math.isclose(
            self.budget_spent_after,
            self.budget_spent_before + self.total_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("budget delta does not match cycle cost")
        if not math.isclose(
            self.before_package.plan.budget_spent,
            self.budget_spent_before,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.after_package.plan.budget_spent,
            self.budget_spent_after,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("decision package budgets do not match cycle budgets")
        _require_instance(self.before_decision, Decision, "before_decision")
        _require_instance(self.after_decision, Decision, "after_decision")
        if (
            self.before_decision is not self.before_package.plan.decision
            or self.after_decision is not self.after_package.plan.decision
        ):
            raise ValueError("decision transition does not match packages")
        if self.workflow_scope != CLINICAL_WORKFLOW_SCOPE:
            raise ValueError("workflow_scope is unsupported")
        for field_name in (
            "clinical_acceptability_inferred",
            "terminal_decision_issued",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if value:
                raise ValueError(f"{field_name} must be false")
        limitations = _freeze_text_tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required closed-loop limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def compile_clinical_execution_batch(
    state: ProgramState,
    package: ClinicalDecisionPackage,
    closed_loop_policy: ClinicalClosedLoopPolicy,
    *,
    batch_id: str,
) -> ClinicalEvidenceExecutionBatch:
    """Compile selected bounded-VOI actions into an exact execution batch."""

    _require_instance(state, ProgramState, "state")
    _require_instance(package, ClinicalDecisionPackage, "package")
    _require_instance(
        closed_loop_policy,
        ClinicalClosedLoopPolicy,
        "closed_loop_policy",
    )
    _require_text(batch_id, "batch_id")
    try:
        state.validate_committed_history()
    except (TypeError, ValueError) as exc:
        raise ClinicalClosedLoopError("program committed history is invalid") from exc
    if state.is_terminal:
        raise ClinicalClosedLoopError(
            "terminal programs cannot execute evidence actions"
        )
    if closed_loop_policy.registered_on > state.as_of_date:
        raise ClinicalClosedLoopError("closed-loop policy is after the program cutoff")
    failures = validate_clinical_decision_package(state, package)
    if failures:
        raise ClinicalClosedLoopError(
            "before decision package failed replay: " + ", ".join(failures)
        )
    if package.plan.decision is not Decision.HOLD:
        raise ClinicalClosedLoopError(
            "clinical execution requires a HOLD package with selected actions"
        )
    if state.current_stage is not package.tensor.stage:
        raise ClinicalClosedLoopError(
            "program stage does not match the clinical evidence tensor"
        )
    catalog_by_id = {item.action_id: item for item in package.action_catalog}
    gaps_by_id = {item.gap_id: item for item in package.tensor.gaps}
    calls: list[ClinicalEvidenceExecutionCall] = []
    for selection in package.plan.selected_actions:
        option = catalog_by_id[selection.action_id]
        targeted_codes = tuple(
            sorted(
                {gaps_by_id[item].code for item in selection.targeted_gap_ids},
                key=_GAP_INDEX.__getitem__,
            )
        )
        calls.append(
            ClinicalEvidenceExecutionCall(
                rank=selection.rank,
                call_id=(f"{batch_id}:call:{selection.rank:02d}:{selection.action_id}"),
                action_id=selection.action_id,
                action_fingerprint=selection.action_fingerprint,
                selection_fingerprint=_sha256(selection),
                targeted_gap_codes=targeted_codes,
                targeted_gap_ids=selection.targeted_gap_ids,
                tool_id=option.tool_id,
                operation=option.operation,
                action_type=option.action_type,
                purpose=option.purpose,
                arguments=option.arguments,
                max_cost=selection.max_cost,
            )
        )
    return ClinicalEvidenceExecutionBatch(
        batch_id=batch_id,
        method_id=CLINICAL_EXECUTION_BATCH_METHOD_ID,
        program_id=state.program_id,
        expected_state_version=state.version,
        as_of_date=state.as_of_date,
        stage=state.current_stage,
        decision_package_id=package.package_id,
        decision_package_fingerprint=package.fingerprint,
        tensor_id=package.tensor.tensor_id,
        tensor_fingerprint=package.tensor.fingerprint,
        plan_id=package.plan.plan_id,
        plan_fingerprint=package.plan.fingerprint,
        decision_policy_id=package.policy.policy_id,
        decision_policy_version=package.policy.version,
        decision_policy_fingerprint=package.policy.fingerprint,
        closed_loop_policy=closed_loop_policy,
        calls=tuple(calls),
        max_steps=len(calls),
        max_total_cost=package.plan.planned_cost,
    )


def clinical_execution_stage_plan(
    batch: ClinicalEvidenceExecutionBatch,
) -> StagePlan:
    """Translate an exact clinical batch into the existing bounded runner."""

    _require_instance(
        batch,
        ClinicalEvidenceExecutionBatch,
        "batch",
    )
    return StagePlan(
        plan_id=batch.batch_id,
        stage=batch.stage,
        calls=tuple(
            ToolCallSpec(
                call_id=item.call_id,
                tool_id=item.tool_id,
                operation=item.operation,
                action_type=item.action_type,
                purpose=item.purpose,
                arguments=item.arguments,
                max_cost=item.max_cost,
                required=True,
            )
            for item in batch.calls
        ),
        max_steps=batch.max_steps,
        max_total_cost=batch.max_total_cost,
        success_confidence=1.0,
        failure_confidence=1.0,
        success_decision=Decision.HOLD,
        failure_decision=Decision.DEFER,
        stop_on_required_failure=True,
        recover_to_defer_on_readiness_block=False,
        metadata={
            "clinical_execution_batch_method_id": batch.method_id,
            "clinical_execution_batch_id": batch.batch_id,
            "clinical_execution_batch_fingerprint": batch.fingerprint,
            "clinical_decision_package_id": batch.decision_package_id,
            "clinical_decision_package_fingerprint": (
                batch.decision_package_fingerprint
            ),
            "clinical_tensor_id": batch.tensor_id,
            "clinical_tensor_fingerprint": batch.tensor_fingerprint,
            "clinical_plan_id": batch.plan_id,
            "clinical_plan_fingerprint": batch.plan_fingerprint,
            "closed_loop_policy_id": batch.closed_loop_policy.policy_id,
            "closed_loop_policy_version": batch.closed_loop_policy.version,
            "closed_loop_policy_fingerprint": (batch.closed_loop_policy.fingerprint),
            "selected_action_ids": tuple(item.action_id for item in batch.calls),
            "provider_auto_decision_prohibited": True,
            "workflow_scope": CLINICAL_WORKFLOW_SCOPE,
        },
    )


def execute_clinical_evidence_batch(
    state: ProgramState,
    package: ClinicalDecisionPackage,
    batch: ClinicalEvidenceExecutionBatch,
    *,
    tool_registry: ToolRegistry,
    mapper_registry: SemanticMapperRegistry,
    promotion_contexts: Mapping[str, PromotionContext],
    environment: GatedDiscoveryEnvironment | None = None,
    planner: BoundedPlanner | None = None,
    execution_ledger: ToolExecutionLedger = ToolExecutionLedger(),
    clock=None,
    run_id: str | None = None,
) -> StageRun:
    """Execute a validated batch through the existing fail-closed runner."""

    expected = compile_clinical_execution_batch(
        state,
        package,
        batch.closed_loop_policy,
        batch_id=batch.batch_id,
    )
    if expected != batch:
        raise ClinicalClosedLoopError(
            "execution batch does not match deterministic compilation"
        )
    runner = BoundedStageRunner(
        tool_registry=tool_registry,
        mapper_registry=mapper_registry,
        planner=planner,
        environment=environment,
        clock=clock,
    )
    return runner.run_stage(
        run_id=run_id or f"{batch.batch_id}:acquisition",
        state=state,
        stage_plan=clinical_execution_stage_plan(batch),
        promotion_contexts=promotion_contexts,
        execution_ledger=execution_ledger,
    )


def _receipt_sources(
    outcome: ToolOutcome,
) -> tuple[ClinicalReceiptSourceMode, tuple[SourceReference, ...]]:
    if outcome.sources:
        sources = tuple(
            sorted(
                outcome.sources,
                key=lambda item: (
                    item.source_id,
                    item.source_version,
                    item.locator,
                    item.content_hash or "",
                ),
            )
        )
        return ClinicalReceiptSourceMode.PROVIDER_DECLARED, sources
    return (
        ClinicalReceiptSourceMode.PAYLOAD_FALLBACK,
        (
            SourceReference(
                source_id=outcome.contract_id,
                source_version="tool-outcome-v1",
                locator=(
                    f"tool://{outcome.request.tool_id}/"
                    f"{outcome.request.operation}/{outcome.request_id}"
                ),
                content_hash=outcome.payload_sha256,
            ),
        ),
    )


def _tool_outcome_receipt(
    *,
    call_id: str,
    outcome: ToolOutcome,
    packet_id: str,
    action: ActionRecord,
) -> ClinicalToolOutcomeReceipt:
    source_mode, sources = _receipt_sources(outcome)
    return ClinicalToolOutcomeReceipt(
        call_id=call_id,
        program_id=outcome.request.program_id,
        request_id=outcome.request_id,
        request_fingerprint=outcome.request.fingerprint,
        expected_state_version=outcome.request.expected_state_version,
        stage=outcome.request.stage,
        tool_id=outcome.request.tool_id,
        operation=outcome.request.operation,
        action_type=outcome.request.action_type,
        purpose=outcome.request.purpose,
        arguments=outcome.request.arguments,
        max_cost=outcome.request.max_cost,
        request_created_at=outcome.request.created_at,
        contract_id=outcome.contract_id,
        status=outcome.status,
        execution_mode=outcome.execution_mode,
        payload_sha256=outcome.payload_sha256,
        source_mode=source_mode,
        sources=sources,
        cost=outcome.cost,
        completed_at=outcome.completed_at,
        error_code=outcome.error_code,
        accepted_packet_id=packet_id,
        action_ledger_id=action.action_id,
        evidence_ids=tuple(sorted(action.evidence_ids)),
    )


def _single_accepted_packet(run: StageRun, label: str):
    if run.status is not StageRunStatus.COMMITTED:
        raise ClinicalClosedLoopError(f"{label} did not commit")
    accepted = run.accepted_packets
    if len(accepted) != 1:
        raise ClinicalClosedLoopError(
            f"{label} must contain exactly one accepted packet"
        )
    return accepted[0]


def _refresh_packet_scope_valid(packet: DecisionPacket) -> bool:
    if any(
        getattr(packet, field_name) for field_name in _REFRESH_FORBIDDEN_UPDATE_FIELDS
    ):
        return False
    return bool(
        packet.clinical_endpoint_mapping_updates
        or packet.benefit_risk_synthesis_updates
    )


def _selected_receipts(
    batch: ClinicalEvidenceExecutionBatch,
    run: StageRun,
) -> tuple[ClinicalSelectedActionReceipt, ...]:
    packet = _single_accepted_packet(run, "acquisition run")
    if run.initial_state.version != batch.expected_state_version:
        raise ClinicalClosedLoopError("acquisition initial state version mismatch")
    if run.plan_result.plan_id != batch.batch_id:
        raise ClinicalClosedLoopError("acquisition plan id mismatch")
    expected_metadata = clinical_execution_stage_plan(batch).metadata
    if run.plan_result.details.get("stage_plan_metadata") != expected_metadata:
        raise ClinicalClosedLoopError("acquisition stage-plan metadata mismatch")
    if packet.metadata.get("stage_plan_metadata") != expected_metadata:
        raise ClinicalClosedLoopError("accepted packet batch metadata mismatch")
    if packet.decision not in {Decision.HOLD, Decision.DEFER}:
        raise ClinicalClosedLoopError("acquisition issued an unsupported decision")
    if run.final_state.current_stage is not run.initial_state.current_stage:
        raise ClinicalClosedLoopError("acquisition cannot change program stage")
    if run.final_state.is_terminal:
        raise ClinicalClosedLoopError("acquisition cannot terminate the program")
    call_ids = run.plan_result.call_ids[: len(run.outcomes)]
    if len(call_ids) != len(run.outcomes):
        raise ClinicalClosedLoopError("acquisition calls and outcomes do not align")
    if len(packet.actions) != len(run.outcomes):
        raise ClinicalClosedLoopError("acquisition actions and outcomes do not align")
    receipts: list[ClinicalSelectedActionReceipt] = []
    calls_by_id = {item.call_id: item for item in batch.calls}
    expected_prefix = tuple(item.call_id for item in batch.calls[: len(call_ids)])
    if tuple(call_ids) != expected_prefix:
        raise ClinicalClosedLoopError("acquisition outcomes are not a call prefix")
    for call_id, outcome, action in zip(
        call_ids,
        run.outcomes,
        packet.actions,
        strict=True,
    ):
        call = calls_by_id[call_id]
        if outcome.request != run.plan_result.requests[call.rank - 1]:
            raise ClinicalClosedLoopError("acquisition outcome request mismatch")
        receipts.append(
            ClinicalSelectedActionReceipt(
                rank=call.rank,
                action_id=call.action_id,
                action_fingerprint=call.action_fingerprint,
                selection_fingerprint=call.selection_fingerprint,
                targeted_gap_codes=call.targeted_gap_codes,
                targeted_gap_ids=call.targeted_gap_ids,
                outcome=_tool_outcome_receipt(
                    call_id=call_id,
                    outcome=outcome,
                    packet_id=packet.packet_id,
                    action=action,
                ),
            )
        )
    return tuple(receipts)


def _refresh_receipt(run: StageRun) -> ClinicalRefreshRunReceipt:
    packet = _single_accepted_packet(run, "refresh run")
    if packet.decision is not Decision.HOLD:
        raise ClinicalClosedLoopError("refresh run must commit HOLD")
    if run.final_state.version != run.initial_state.version + 1:
        raise ClinicalClosedLoopError("refresh run must commit one transition")
    if run.final_state.current_stage is not run.initial_state.current_stage:
        raise ClinicalClosedLoopError("refresh run cannot change program stage")
    if run.final_state.is_terminal:
        raise ClinicalClosedLoopError("refresh run cannot terminate the program")
    if not _refresh_packet_scope_valid(packet):
        raise ClinicalClosedLoopError(
            "refresh run must append only governed mapping or synthesis artifacts"
        )
    if len(run.outcomes) != len(packet.actions):
        raise ClinicalClosedLoopError("refresh actions and outcomes do not align")
    if len(run.promotions) != len(run.outcomes):
        raise ClinicalClosedLoopError("refresh promotions and outcomes do not align")
    if any(item.status is not PromotionStatus.PROMOTED for item in run.promotions):
        raise ClinicalClosedLoopError("refresh promotions must all succeed")
    call_ids = run.plan_result.call_ids[: len(run.outcomes)]
    if len(call_ids) != len(run.outcomes):
        raise ClinicalClosedLoopError("refresh calls and outcomes do not align")
    receipts = tuple(
        _tool_outcome_receipt(
            call_id=call_id,
            outcome=outcome,
            packet_id=packet.packet_id,
            action=action,
        )
        for call_id, outcome, action in zip(
            call_ids,
            run.outcomes,
            packet.actions,
            strict=True,
        )
    )
    return ClinicalRefreshRunReceipt(
        run_id=run.run_id,
        plan_id=run.plan_result.plan_id,
        initial_state_version=run.initial_state.version,
        final_state_version=run.final_state.version,
        stage=run.initial_state.current_stage,
        accepted_packet_id=packet.packet_id,
        decision=packet.decision,
        outcomes=receipts,
        promotion_codes=tuple(item.code for item in run.promotions),
        action_cost=packet.action_cost,
    )


def _receipt_evidence_source_hashes(
    state: ProgramState,
    receipt: ClinicalToolOutcomeReceipt,
) -> tuple[str, ...] | None:
    hashes: set[str] = set()
    for evidence_id in receipt.evidence_ids:
        evidence = state.evidence_by_id.get(evidence_id)
        if evidence is None or evidence.source.content_hash is None:
            return None
        hashes.add(evidence.source.content_hash)
    return tuple(sorted(hashes))


def compile_clinical_evidence_transition(
    before_state: ProgramState,
    before_package: ClinicalDecisionPackage,
    execution_batch: ClinicalEvidenceExecutionBatch,
    acquisition_run: StageRun,
    refresh_runs: Sequence[StageRun],
    after_synthesis: BenefitRiskSynthesisRecord,
    *,
    transition_id: str,
    after_package_id: str,
    after_tensor_id: str,
    after_plan_id: str,
) -> ClinicalEvidenceTransitionPackage:
    """Compile a source-rejoined before/action/refresh/after transition."""

    _require_text(transition_id, "transition_id")
    expected_batch = compile_clinical_execution_batch(
        before_state,
        before_package,
        execution_batch.closed_loop_policy,
        batch_id=execution_batch.batch_id,
    )
    if expected_batch != execution_batch:
        raise ClinicalClosedLoopError("execution batch failed deterministic replay")
    if acquisition_run.initial_state != before_state:
        raise ClinicalClosedLoopError(
            "acquisition run does not start from before_state"
        )
    selected_receipts = _selected_receipts(execution_batch, acquisition_run)
    acquisition_packet = _single_accepted_packet(
        acquisition_run,
        "acquisition run",
    )
    if (
        acquisition_packet.clinical_endpoint_mapping_updates
        or acquisition_packet.benefit_risk_synthesis_updates
    ):
        raise ClinicalClosedLoopError(
            "acquisition cannot directly refresh governed clinical artifacts"
        )
    runs = tuple(refresh_runs)
    previous_state = acquisition_run.final_state
    refresh_receipts: list[ClinicalRefreshRunReceipt] = []
    for run in runs:
        if run.initial_state != previous_state:
            raise ClinicalClosedLoopError("refresh runs are not state-contiguous")
        receipt = _refresh_receipt(run)
        refresh_receipts.append(receipt)
        previous_state = run.final_state
    after_state = previous_state
    try:
        before_state.validate_committed_history()
        after_state.validate_committed_history()
    except (TypeError, ValueError) as exc:
        raise ClinicalClosedLoopError("cycle state history is invalid") from exc
    committed = after_state.benefit_risk_syntheses_by_id.get(
        after_synthesis.synthesis_id
    )
    if committed is None or committed != after_synthesis:
        raise ClinicalClosedLoopError(
            "after synthesis must exactly match the committed final state"
        )
    consumed = tuple(item.action_id for item in selected_receipts)
    residual_catalog = tuple(
        item
        for item in before_package.action_catalog
        if item.action_id not in set(consumed)
    )
    after_package = compile_clinical_decision_package(
        after_state,
        after_synthesis,
        before_package.policy,
        residual_catalog,
        package_id=after_package_id,
        tensor_id=after_tensor_id,
        plan_id=after_plan_id,
    )
    synthesis_changed = (
        before_package.tensor.synthesis_fingerprint
        != after_package.tensor.synthesis_fingerprint
    )
    refresh_packets = tuple(_single_accepted_packet(run, "refresh run") for run in runs)
    if synthesis_changed and not any(
        after_synthesis in packet.benefit_risk_synthesis_updates
        for packet in refresh_packets
    ):
        raise ClinicalClosedLoopError(
            "changed synthesis must be committed by a reviewer refresh"
        )
    before_codes = {item.code for item in before_package.tensor.gaps}
    after_codes = {item.code for item in after_package.tensor.gaps}
    before_hashes = set(before_package.tensor.source_content_hashes)
    after_hashes = set(after_package.tensor.source_content_hashes)
    added_hashes = after_hashes - before_hashes
    promoted_hashes_by_action: dict[str, set[str]] = {}
    for receipt in selected_receipts:
        hashes = _receipt_evidence_source_hashes(after_state, receipt.outcome)
        if hashes is None:
            raise ClinicalClosedLoopError(
                "selected receipt evidence is missing source provenance"
            )
        promoted_hashes_by_action[receipt.action_id] = set(hashes)
    successful_promoted_hashes = {
        digest
        for receipt in selected_receipts
        if receipt.outcome.status is ToolStatus.SUCCEEDED
        for digest in promoted_hashes_by_action[receipt.action_id]
    }
    if not added_hashes.issubset(successful_promoted_hashes):
        raise ClinicalClosedLoopError(
            "new tensor sources are not promoted by successful selected actions"
        )
    for code in before_codes - after_codes:
        if not any(
            receipt.outcome.status is ToolStatus.SUCCEEDED
            and code in receipt.targeted_gap_codes
            and promoted_hashes_by_action[receipt.action_id] & added_hashes
            for receipt in selected_receipts
        ):
            raise ClinicalClosedLoopError(
                "resolved gap lacks targeted promoted source rejoin"
            )
    refresh_receipt_tuple = tuple(refresh_receipts)
    return ClinicalEvidenceTransitionPackage(
        transition_id=transition_id,
        method_id=CLINICAL_CLOSED_LOOP_METHOD_ID,
        program_id=before_state.program_id,
        as_of_date=before_state.as_of_date,
        before_state_version=before_state.version,
        after_state_version=after_state.version,
        closed_loop_policy=execution_batch.closed_loop_policy,
        execution_batch=execution_batch,
        before_package=before_package,
        selected_action_receipts=selected_receipts,
        refresh_receipts=refresh_receipt_tuple,
        after_package=after_package,
        accepted_packet_ids=(
            selected_receipts[0].outcome.accepted_packet_id,
            *(item.accepted_packet_id for item in refresh_receipt_tuple),
        ),
        consumed_action_ids=consumed,
        remaining_action_ids=tuple(item.action_id for item in residual_catalog),
        resolved_gap_codes=tuple(
            sorted(before_codes - after_codes, key=_GAP_INDEX.__getitem__)
        ),
        persisted_gap_codes=tuple(
            sorted(before_codes & after_codes, key=_GAP_INDEX.__getitem__)
        ),
        new_gap_codes=tuple(
            sorted(after_codes - before_codes, key=_GAP_INDEX.__getitem__)
        ),
        added_source_content_hashes=tuple(sorted(added_hashes)),
        removed_source_content_hashes=tuple(sorted(before_hashes - after_hashes)),
        acquisition_cost=_round_metric(
            sum(item.outcome.cost for item in selected_receipts)
        ),
        refresh_cost=_round_metric(
            sum(item.action_cost for item in refresh_receipt_tuple)
        ),
        total_cost=_round_metric(
            sum(item.outcome.cost for item in selected_receipts)
            + sum(item.action_cost for item in refresh_receipt_tuple)
        ),
        budget_spent_before=before_state.budget.spent,
        budget_spent_after=after_state.budget.spent,
        before_decision=before_package.plan.decision,
        after_decision=after_package.plan.decision,
    )


def _receipt_matches_state(
    state: ProgramState,
    receipt: ClinicalToolOutcomeReceipt,
) -> bool:
    action = state.actions_by_id.get(receipt.action_ledger_id)
    if action is None:
        return False
    if (
        action.action_type is not receipt.action_type
        or action.purpose != receipt.purpose
        or not math.isclose(
            action.cost,
            receipt.cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or tuple(sorted(action.evidence_ids)) != receipt.evidence_ids
    ):
        return False
    metadata = action.metadata
    if (
        metadata.get("tool_request_id") != receipt.request_id
        or metadata.get("tool_request_fingerprint") != receipt.request_fingerprint
        or metadata.get("tool_contract_id") != receipt.contract_id
        or metadata.get("tool_payload_sha256") != receipt.payload_sha256
        or metadata.get("tool_status") != receipt.status.value
        or metadata.get("execution_mode") != receipt.execution_mode.value
        or metadata.get("completed_at") != receipt.completed_at.isoformat()
        or metadata.get("error_code") != receipt.error_code
    ):
        return False
    source_keys = {
        (
            item.source_id,
            item.source_version,
            item.locator,
            item.content_hash,
        )
        for item in receipt.sources
    }
    for evidence_id in receipt.evidence_ids:
        evidence = state.evidence_by_id.get(evidence_id)
        if evidence is None:
            return False
        if (
            evidence.metadata.get("tool_request_id") != receipt.request_id
            or evidence.metadata.get("tool_request_fingerprint")
            != receipt.request_fingerprint
            or evidence.metadata.get("tool_contract_id") != receipt.contract_id
            or evidence.metadata.get("tool_payload_sha256") != receipt.payload_sha256
            or (
                evidence.source.source_id,
                evidence.source.source_version,
                evidence.source.locator,
                evidence.source.content_hash,
            )
            not in source_keys
        ):
            return False
    return True


def validate_clinical_evidence_transition(
    before_state: ProgramState,
    after_state: ProgramState,
    package: ClinicalEvidenceTransitionPackage,
) -> tuple[str, ...]:
    """Validate a transition against both committed state ledgers."""

    _require_instance(before_state, ProgramState, "before_state")
    _require_instance(after_state, ProgramState, "after_state")
    _require_instance(
        package,
        ClinicalEvidenceTransitionPackage,
        "package",
    )
    try:
        before_state.validate_committed_history()
        after_state.validate_committed_history()
    except (TypeError, ValueError):
        return ("state_history_invalid",)
    if (
        before_state.program_id != package.program_id
        or after_state.program_id != package.program_id
        or before_state.as_of_date != package.as_of_date
        or after_state.as_of_date != package.as_of_date
        or before_state.version != package.before_state_version
        or after_state.version != package.after_state_version
    ):
        return ("state_context_mismatch",)
    if before_state.is_terminal or after_state.is_terminal:
        return ("terminal_state_present",)
    if (
        after_state.packet_history[: before_state.version]
        != before_state.packet_history
        or after_state.decision_history[: before_state.version]
        != before_state.decision_history
        or after_state.action_history[: len(before_state.action_history)]
        != before_state.action_history
    ):
        return ("state_history_prefix_mismatch",)
    delta_packets = after_state.packet_history[
        before_state.version : after_state.version
    ]
    if tuple(item.packet_id for item in delta_packets) != package.accepted_packet_ids:
        return ("accepted_packet_ids_mismatch",)
    acquisition_packet = delta_packets[0]
    acquisition_metadata = acquisition_packet.metadata
    expected_acquisition_call_ids = tuple(
        item.outcome.call_id for item in package.selected_action_receipts
    )
    if (
        acquisition_packet.program_id != package.program_id
        or acquisition_packet.expected_state_version != package.before_state_version
        or acquisition_packet.stage is not package.execution_batch.stage
        or acquisition_packet.decision not in {Decision.HOLD, Decision.DEFER}
        or acquisition_metadata.get("stage_plan_id") != package.execution_batch.batch_id
        or acquisition_metadata.get("required_call_ids")
        != tuple(item.call_id for item in package.execution_batch.calls)
        or acquisition_metadata.get("executed_call_ids")
        != expected_acquisition_call_ids
        or acquisition_metadata.get("stage_plan_metadata")
        != clinical_execution_stage_plan(package.execution_batch).metadata
        or acquisition_metadata.get("bounded_policy") is not True
    ):
        return ("acquisition_packet_metadata_mismatch",)
    if (
        acquisition_packet.clinical_endpoint_mapping_updates
        or acquisition_packet.benefit_risk_synthesis_updates
    ):
        return ("acquisition_governance_bypass",)
    refresh_packets = delta_packets[1:]
    if len(refresh_packets) != len(package.refresh_receipts):
        return ("refresh_packet_count_mismatch",)
    for packet, receipt in zip(
        refresh_packets,
        package.refresh_receipts,
        strict=True,
    ):
        metadata = packet.metadata
        if (
            packet.program_id != package.program_id
            or packet.expected_state_version != receipt.initial_state_version
            or packet.stage is not receipt.stage
            or packet.decision is not receipt.decision
            or metadata.get("run_id") != receipt.run_id
            or metadata.get("stage_plan_id") != receipt.plan_id
            or metadata.get("executed_call_ids")
            != tuple(item.call_id for item in receipt.outcomes)
            or metadata.get("promotion_codes") != receipt.promotion_codes
            or metadata.get("bounded_policy") is not True
        ):
            return ("refresh_packet_metadata_mismatch",)
        if not _refresh_packet_scope_valid(packet):
            return ("refresh_governance_scope_invalid",)
    before_failures = validate_clinical_decision_package(
        before_state,
        package.before_package,
    )
    if before_failures:
        return ("before_package_invalid",)
    after_failures = validate_clinical_decision_package(
        after_state,
        package.after_package,
    )
    if after_failures:
        return ("after_package_invalid",)
    try:
        expected_batch = compile_clinical_execution_batch(
            before_state,
            package.before_package,
            package.closed_loop_policy,
            batch_id=package.execution_batch.batch_id,
        )
    except (ClinicalClosedLoopError, TypeError, ValueError):
        return ("execution_batch_recompile_failed",)
    if expected_batch != package.execution_batch:
        return ("execution_batch_mismatch",)
    all_receipts = tuple(
        item.outcome for item in package.selected_action_receipts
    ) + tuple(
        outcome for refresh in package.refresh_receipts for outcome in refresh.outcomes
    )
    if any(not _receipt_matches_state(after_state, item) for item in all_receipts):
        return ("receipt_state_binding_invalid",)
    promoted_hashes_by_action: dict[str, set[str]] = {}
    for receipt in package.selected_action_receipts:
        hashes = _receipt_evidence_source_hashes(after_state, receipt.outcome)
        if hashes is None:
            return ("selected_receipt_evidence_source_missing",)
        promoted_hashes_by_action[receipt.action_id] = set(hashes)
    successful_promoted_hashes = {
        digest
        for receipt in package.selected_action_receipts
        if receipt.outcome.status is ToolStatus.SUCCEEDED
        for digest in promoted_hashes_by_action[receipt.action_id]
    }
    added_hashes = set(package.added_source_content_hashes)
    if not added_hashes.issubset(successful_promoted_hashes):
        return ("added_source_not_promoted_by_selected_action",)
    for code in package.resolved_gap_codes:
        if not any(
            receipt.outcome.status is ToolStatus.SUCCEEDED
            and code in receipt.targeted_gap_codes
            and promoted_hashes_by_action[receipt.action_id] & added_hashes
            for receipt in package.selected_action_receipts
        ):
            return ("resolved_gap_promoted_source_mismatch",)
    packet_action_ids = tuple(
        action.action_id for packet in delta_packets for action in packet.actions
    )
    receipt_action_ids = tuple(item.action_ledger_id for item in all_receipts)
    if packet_action_ids != receipt_action_ids:
        return ("receipt_action_order_mismatch",)
    if not math.isclose(
        after_state.budget.spent - before_state.budget.spent,
        package.total_cost,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return ("state_budget_delta_mismatch",)
    synthesis = after_state.benefit_risk_syntheses_by_id.get(
        package.after_package.tensor.synthesis_id
    )
    if synthesis is None:
        return ("after_synthesis_missing",)
    if (
        package.before_package.tensor.synthesis_fingerprint
        != package.after_package.tensor.synthesis_fingerprint
        and not any(
            synthesis in packet.benefit_risk_synthesis_updates
            for packet in refresh_packets
        )
    ):
        return ("after_synthesis_not_reviewer_refreshed",)
    try:
        rebuilt_after = compile_clinical_decision_package(
            after_state,
            synthesis,
            package.after_package.policy,
            package.after_package.action_catalog,
            package_id=package.after_package.package_id,
            tensor_id=package.after_package.tensor.tensor_id,
            plan_id=package.after_package.plan.plan_id,
        )
    except (TypeError, ValueError):
        return ("after_package_recompile_failed",)
    if rebuilt_after != package.after_package:
        return ("after_package_recompile_mismatch",)
    return ()


def clinical_evidence_transition_envelope(
    package: ClinicalEvidenceTransitionPackage,
) -> dict[str, Any]:
    """Return a strict integrity-bound closed-loop transition envelope."""

    _require_instance(
        package,
        ClinicalEvidenceTransitionPackage,
        "package",
    )
    return {
        "schema_version": CLINICAL_CLOSED_LOOP_SCHEMA_VERSION,
        "integrity_sha256": package.fingerprint,
        "transition": package.to_dict(),
    }


def _parse_record(
    value: Any,
    path: str,
    fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing:
        raise RecordParseError(f"{path} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise RecordParseError(f"{path} has unknown fields: {', '.join(sorted(extra))}")
    return data


def _parse_sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _parse_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    return dict(value)


def _parse_enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is invalid") from exc


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc


def _parse_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO datetime")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO datetime") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise RecordParseError(f"{path} must be timezone-aware")
    return result


def _parse_policy(value: Any, path: str) -> ClinicalClosedLoopPolicy:
    fields = {
        "policy_id",
        "version",
        "registered_on",
        "max_refresh_runs",
        "max_refresh_actions",
        "max_refresh_cost",
        "require_committed_runs",
        "require_refresh_verifier_actions",
        "require_new_source_provenance_for_resolution",
        "consume_attempted_actions",
        "provider_auto_decision_prohibited",
        "terminal_decisions_prohibited",
        "workflow_scope",
        "metadata",
    }
    data = _parse_record(value, path, fields)
    return ClinicalClosedLoopPolicy(
        policy_id=data["policy_id"],
        version=data["version"],
        registered_on=_parse_date(
            data["registered_on"],
            f"{path}.registered_on",
        ),
        max_refresh_runs=data["max_refresh_runs"],
        max_refresh_actions=data["max_refresh_actions"],
        max_refresh_cost=data["max_refresh_cost"],
        require_committed_runs=data["require_committed_runs"],
        require_refresh_verifier_actions=(data["require_refresh_verifier_actions"]),
        require_new_source_provenance_for_resolution=(
            data["require_new_source_provenance_for_resolution"]
        ),
        consume_attempted_actions=data["consume_attempted_actions"],
        provider_auto_decision_prohibited=(data["provider_auto_decision_prohibited"]),
        terminal_decisions_prohibited=data["terminal_decisions_prohibited"],
        workflow_scope=data["workflow_scope"],
        metadata=_parse_mapping(data["metadata"], f"{path}.metadata"),
    )


def _parse_execution_call(
    value: Any,
    path: str,
) -> ClinicalEvidenceExecutionCall:
    fields = {
        "rank",
        "call_id",
        "action_id",
        "action_fingerprint",
        "selection_fingerprint",
        "targeted_gap_codes",
        "targeted_gap_ids",
        "tool_id",
        "operation",
        "action_type",
        "purpose",
        "arguments",
        "max_cost",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceExecutionCall(
        rank=data["rank"],
        call_id=data["call_id"],
        action_id=data["action_id"],
        action_fingerprint=data["action_fingerprint"],
        selection_fingerprint=data["selection_fingerprint"],
        targeted_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.targeted_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["targeted_gap_codes"],
                    f"{path}.targeted_gap_codes",
                )
            )
        ),
        targeted_gap_ids=_parse_sequence(
            data["targeted_gap_ids"],
            f"{path}.targeted_gap_ids",
        ),
        tool_id=data["tool_id"],
        operation=data["operation"],
        action_type=_parse_enum(
            ActionType,
            data["action_type"],
            f"{path}.action_type",
        ),
        purpose=data["purpose"],
        arguments=_parse_mapping(data["arguments"], f"{path}.arguments"),
        max_cost=data["max_cost"],
    )


def _parse_execution_batch(
    value: Any,
    path: str,
) -> ClinicalEvidenceExecutionBatch:
    fields = {
        "batch_id",
        "method_id",
        "program_id",
        "expected_state_version",
        "as_of_date",
        "stage",
        "decision_package_id",
        "decision_package_fingerprint",
        "tensor_id",
        "tensor_fingerprint",
        "plan_id",
        "plan_fingerprint",
        "decision_policy_id",
        "decision_policy_version",
        "decision_policy_fingerprint",
        "closed_loop_policy",
        "calls",
        "max_steps",
        "max_total_cost",
        "workflow_scope",
        "provider_auto_decision_issued",
    }
    data = _parse_record(value, path, fields)
    return ClinicalEvidenceExecutionBatch(
        batch_id=data["batch_id"],
        method_id=data["method_id"],
        program_id=data["program_id"],
        expected_state_version=data["expected_state_version"],
        as_of_date=_parse_date(data["as_of_date"], f"{path}.as_of_date"),
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        decision_package_id=data["decision_package_id"],
        decision_package_fingerprint=data["decision_package_fingerprint"],
        tensor_id=data["tensor_id"],
        tensor_fingerprint=data["tensor_fingerprint"],
        plan_id=data["plan_id"],
        plan_fingerprint=data["plan_fingerprint"],
        decision_policy_id=data["decision_policy_id"],
        decision_policy_version=data["decision_policy_version"],
        decision_policy_fingerprint=data["decision_policy_fingerprint"],
        closed_loop_policy=_parse_policy(
            data["closed_loop_policy"],
            f"{path}.closed_loop_policy",
        ),
        calls=tuple(
            _parse_execution_call(item, f"{path}.calls[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["calls"], f"{path}.calls")
            )
        ),
        max_steps=data["max_steps"],
        max_total_cost=data["max_total_cost"],
        workflow_scope=data["workflow_scope"],
        provider_auto_decision_issued=data["provider_auto_decision_issued"],
    )


def _parse_source(value: Any, path: str) -> SourceReference:
    data = _parse_record(
        value,
        path,
        {"source_id", "source_version", "locator", "content_hash"},
    )
    return SourceReference(
        source_id=data["source_id"],
        source_version=data["source_version"],
        locator=data["locator"],
        content_hash=data["content_hash"],
    )


def _parse_tool_receipt(
    value: Any,
    path: str,
) -> ClinicalToolOutcomeReceipt:
    fields = {
        "call_id",
        "program_id",
        "request_id",
        "request_fingerprint",
        "expected_state_version",
        "stage",
        "tool_id",
        "operation",
        "action_type",
        "purpose",
        "arguments",
        "max_cost",
        "request_created_at",
        "contract_id",
        "status",
        "execution_mode",
        "payload_sha256",
        "source_mode",
        "sources",
        "cost",
        "completed_at",
        "error_code",
        "accepted_packet_id",
        "action_ledger_id",
        "evidence_ids",
    }
    data = _parse_record(value, path, fields)
    return ClinicalToolOutcomeReceipt(
        call_id=data["call_id"],
        program_id=data["program_id"],
        request_id=data["request_id"],
        request_fingerprint=data["request_fingerprint"],
        expected_state_version=data["expected_state_version"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        tool_id=data["tool_id"],
        operation=data["operation"],
        action_type=_parse_enum(
            ActionType,
            data["action_type"],
            f"{path}.action_type",
        ),
        purpose=data["purpose"],
        arguments=_parse_mapping(data["arguments"], f"{path}.arguments"),
        max_cost=data["max_cost"],
        request_created_at=_parse_datetime(
            data["request_created_at"],
            f"{path}.request_created_at",
        ),
        contract_id=data["contract_id"],
        status=_parse_enum(ToolStatus, data["status"], f"{path}.status"),
        execution_mode=_parse_enum(
            ExecutionMode,
            data["execution_mode"],
            f"{path}.execution_mode",
        ),
        payload_sha256=data["payload_sha256"],
        source_mode=_parse_enum(
            ClinicalReceiptSourceMode,
            data["source_mode"],
            f"{path}.source_mode",
        ),
        sources=tuple(
            _parse_source(item, f"{path}.sources[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["sources"], f"{path}.sources")
            )
        ),
        cost=data["cost"],
        completed_at=_parse_datetime(
            data["completed_at"],
            f"{path}.completed_at",
        ),
        error_code=data["error_code"],
        accepted_packet_id=data["accepted_packet_id"],
        action_ledger_id=data["action_ledger_id"],
        evidence_ids=_parse_sequence(
            data["evidence_ids"],
            f"{path}.evidence_ids",
        ),
    )


def _parse_selected_receipt(
    value: Any,
    path: str,
) -> ClinicalSelectedActionReceipt:
    fields = {
        "rank",
        "action_id",
        "action_fingerprint",
        "selection_fingerprint",
        "targeted_gap_codes",
        "targeted_gap_ids",
        "outcome",
    }
    data = _parse_record(value, path, fields)
    return ClinicalSelectedActionReceipt(
        rank=data["rank"],
        action_id=data["action_id"],
        action_fingerprint=data["action_fingerprint"],
        selection_fingerprint=data["selection_fingerprint"],
        targeted_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.targeted_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["targeted_gap_codes"],
                    f"{path}.targeted_gap_codes",
                )
            )
        ),
        targeted_gap_ids=_parse_sequence(
            data["targeted_gap_ids"],
            f"{path}.targeted_gap_ids",
        ),
        outcome=_parse_tool_receipt(data["outcome"], f"{path}.outcome"),
    )


def _parse_refresh_receipt(
    value: Any,
    path: str,
) -> ClinicalRefreshRunReceipt:
    fields = {
        "run_id",
        "plan_id",
        "initial_state_version",
        "final_state_version",
        "stage",
        "accepted_packet_id",
        "decision",
        "outcomes",
        "promotion_codes",
        "action_cost",
    }
    data = _parse_record(value, path, fields)
    return ClinicalRefreshRunReceipt(
        run_id=data["run_id"],
        plan_id=data["plan_id"],
        initial_state_version=data["initial_state_version"],
        final_state_version=data["final_state_version"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        accepted_packet_id=data["accepted_packet_id"],
        decision=_parse_enum(
            Decision,
            data["decision"],
            f"{path}.decision",
        ),
        outcomes=tuple(
            _parse_tool_receipt(item, f"{path}.outcomes[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["outcomes"], f"{path}.outcomes")
            )
        ),
        promotion_codes=_parse_sequence(
            data["promotion_codes"],
            f"{path}.promotion_codes",
        ),
        action_cost=data["action_cost"],
    )


def _parse_decision_package_raw(
    value: Any,
    path: str,
) -> ClinicalDecisionPackage:
    raw = _parse_mapping(value, path)
    digest = _sha256(raw)
    return clinical_decision_package_from_dict(
        {
            "schema_version": CLINICAL_DECISION_PACKAGE_SCHEMA_VERSION,
            "integrity_sha256": digest,
            "package": raw,
        }
    )


def clinical_evidence_transition_from_dict(
    value: Any,
) -> ClinicalEvidenceTransitionPackage:
    """Parse one strict integrity-bound closed-loop transition."""

    envelope = _parse_record(
        value,
        "clinical_evidence_transition_envelope",
        {"schema_version", "integrity_sha256", "transition"},
    )
    if envelope["schema_version"] != CLINICAL_CLOSED_LOOP_SCHEMA_VERSION:
        raise RecordParseError(
            "clinical evidence transition schema_version is unsupported"
        )
    expected_hash = envelope["integrity_sha256"]
    if (
        not isinstance(expected_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
    ):
        raise RecordParseError(
            "clinical evidence transition integrity_sha256 is invalid"
        )
    raw = _parse_mapping(
        envelope["transition"],
        "clinical_evidence_transition_envelope.transition",
    )
    if _sha256(raw) != expected_hash:
        raise RecordParseError(
            "clinical evidence transition integrity hash does not match"
        )
    path = "clinical_evidence_transition_envelope.transition"
    fields = {
        "transition_id",
        "method_id",
        "program_id",
        "as_of_date",
        "before_state_version",
        "after_state_version",
        "closed_loop_policy",
        "execution_batch",
        "before_package",
        "selected_action_receipts",
        "refresh_receipts",
        "after_package",
        "accepted_packet_ids",
        "consumed_action_ids",
        "remaining_action_ids",
        "resolved_gap_codes",
        "persisted_gap_codes",
        "new_gap_codes",
        "added_source_content_hashes",
        "removed_source_content_hashes",
        "acquisition_cost",
        "refresh_cost",
        "total_cost",
        "budget_spent_before",
        "budget_spent_after",
        "before_decision",
        "after_decision",
        "workflow_scope",
        "clinical_acceptability_inferred",
        "terminal_decision_issued",
        "limitations",
    }
    data = _parse_record(raw, path, fields)
    package = ClinicalEvidenceTransitionPackage(
        transition_id=data["transition_id"],
        method_id=data["method_id"],
        program_id=data["program_id"],
        as_of_date=_parse_date(data["as_of_date"], f"{path}.as_of_date"),
        before_state_version=data["before_state_version"],
        after_state_version=data["after_state_version"],
        closed_loop_policy=_parse_policy(
            data["closed_loop_policy"],
            f"{path}.closed_loop_policy",
        ),
        execution_batch=_parse_execution_batch(
            data["execution_batch"],
            f"{path}.execution_batch",
        ),
        before_package=_parse_decision_package_raw(
            data["before_package"],
            f"{path}.before_package",
        ),
        selected_action_receipts=tuple(
            _parse_selected_receipt(
                item,
                f"{path}.selected_action_receipts[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["selected_action_receipts"],
                    f"{path}.selected_action_receipts",
                )
            )
        ),
        refresh_receipts=tuple(
            _parse_refresh_receipt(
                item,
                f"{path}.refresh_receipts[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["refresh_receipts"],
                    f"{path}.refresh_receipts",
                )
            )
        ),
        after_package=_parse_decision_package_raw(
            data["after_package"],
            f"{path}.after_package",
        ),
        accepted_packet_ids=_parse_sequence(
            data["accepted_packet_ids"],
            f"{path}.accepted_packet_ids",
        ),
        consumed_action_ids=_parse_sequence(
            data["consumed_action_ids"],
            f"{path}.consumed_action_ids",
        ),
        remaining_action_ids=_parse_sequence(
            data["remaining_action_ids"],
            f"{path}.remaining_action_ids",
        ),
        resolved_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.resolved_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["resolved_gap_codes"],
                    f"{path}.resolved_gap_codes",
                )
            )
        ),
        persisted_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.persisted_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["persisted_gap_codes"],
                    f"{path}.persisted_gap_codes",
                )
            )
        ),
        new_gap_codes=tuple(
            _parse_enum(
                ClinicalEvidenceGapCode,
                item,
                f"{path}.new_gap_codes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["new_gap_codes"],
                    f"{path}.new_gap_codes",
                )
            )
        ),
        added_source_content_hashes=_parse_sequence(
            data["added_source_content_hashes"],
            f"{path}.added_source_content_hashes",
        ),
        removed_source_content_hashes=_parse_sequence(
            data["removed_source_content_hashes"],
            f"{path}.removed_source_content_hashes",
        ),
        acquisition_cost=data["acquisition_cost"],
        refresh_cost=data["refresh_cost"],
        total_cost=data["total_cost"],
        budget_spent_before=data["budget_spent_before"],
        budget_spent_after=data["budget_spent_after"],
        before_decision=_parse_enum(
            Decision,
            data["before_decision"],
            f"{path}.before_decision",
        ),
        after_decision=_parse_enum(
            Decision,
            data["after_decision"],
            f"{path}.after_decision",
        ),
        workflow_scope=data["workflow_scope"],
        clinical_acceptability_inferred=data["clinical_acceptability_inferred"],
        terminal_decision_issued=data["terminal_decision_issued"],
        limitations=_parse_sequence(
            data["limitations"],
            f"{path}.limitations",
        ),
    )
    if package.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed clinical evidence transition changed canonical identity"
        )
    return package


def _parse_envelope_json(payload: str) -> Any:
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RecordParseError(
                    f"clinical evidence transition duplicates key {key}"
                )
            result[key] = item
        return result

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RecordParseError(f"clinical evidence transition contains {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(
            "clinical evidence transition is not valid JSON"
        ) from exc


def clinical_evidence_transition_from_json(
    payload: str,
) -> ClinicalEvidenceTransitionPackage:
    """Parse JSON without duplicate keys or non-finite numeric values."""

    return clinical_evidence_transition_from_dict(_parse_envelope_json(payload))
