"""Provenance-preserving diagnostics across clinical decision packages."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from typing import Any

from .clinical_decision import (
    ClinicalDecisionPackage,
    ClinicalDimensionStatus,
    ClinicalEvidenceDimension,
    ClinicalEvidenceGapCode,
)
from .clinical_workflow import validate_clinical_decision_against_state
from .models import (
    Decision,
    ProgramState,
    SerializableRecord,
    Stage,
    _require_date,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_COHORT_MANIFEST_SCHEMA_VERSION = (
    "adds.clinical-evidence-cohort-manifest.v1"
)
CLINICAL_COHORT_REPORT_SCHEMA_VERSION = "adds.clinical-evidence-cohort-report.v1"
CLINICAL_COHORT_SUMMARY_SCHEMA_VERSION = "adds.clinical-evidence-cohort-summary.v1"
CLINICAL_COHORT_METHOD_ID = "adds.clinical-evidence-cohort-diagnostics.v1"
CLINICAL_COHORT_ANALYSIS_SCOPE = "workflow_behavior_diagnostics"

_PACKAGE_VALIDATION_SCOPES = {
    "integrity_and_structure",
    "integrity_structure_and_state_replay",
}
_OUTCOME_CALIBRATION_STATUS = "not_estimable_without_independent_outcomes"
_DECISION_ORDER = (Decision.ADVANCE, Decision.HOLD, Decision.DEFER)
_DIMENSION_ORDER = tuple(ClinicalEvidenceDimension)
_GAP_ORDER = tuple(ClinicalEvidenceGapCode)
_OVERLAP_KIND_ORDER = {
    "source_content_hash": 0,
    "trial_id": 1,
}
_GAP_DIMENSIONS = {
    ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS: (
        ClinicalEvidenceDimension.TRIAL_COUNT
    ),
    ClinicalEvidenceGapCode.BENEFIT_NOT_DEMONSTRATED: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.BENEFIT_DIRECTION_CONFLICT: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL: (
        ClinicalEvidenceDimension.BENEFIT_DIRECTION
    ),
    ClinicalEvidenceGapCode.IMPRECISE_BENEFIT_ESTIMATE: (
        ClinicalEvidenceDimension.BENEFIT_PRECISION
    ),
    ClinicalEvidenceGapCode.MISSING_DESCRIPTIVE_ARM_MEASUREMENT: (
        ClinicalEvidenceDimension.DESCRIPTIVE_ARM_MEASUREMENT_COMPLETENESS
    ),
    ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK: (
        ClinicalEvidenceDimension.SAFETY_DIRECTION
    ),
    ClinicalEvidenceGapCode.SAFETY_DIRECTION_CONFLICT: (
        ClinicalEvidenceDimension.SAFETY_DIRECTION
    ),
    ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE: (
        ClinicalEvidenceDimension.SAFETY_EXPOSURE
    ),
    ClinicalEvidenceGapCode.ENDPOINT_TIMEFRAME_MISMATCH: (
        ClinicalEvidenceDimension.ENDPOINT_TIMEFRAME_ALIGNMENT
    ),
    ClinicalEvidenceGapCode.SAFETY_TIMEFRAME_MISMATCH: (
        ClinicalEvidenceDimension.SAFETY_TIMEFRAME_ALIGNMENT
    ),
    ClinicalEvidenceGapCode.MEASUREMENT_UNIT_MISMATCH: (
        ClinicalEvidenceDimension.MEASUREMENT_UNIT_ALIGNMENT
    ),
}
_BLOCKING_GAP_CODES = {
    ClinicalEvidenceGapCode.BENEFIT_HARM_SIGNAL,
    ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK,
}
_REQUIRED_LIMITATIONS = (
    (
        "Cohort diagnostics describe workflow behavior without outcome labels; "
        "they cannot estimate clinical utility, correctness, safety, or calibration."
    ),
    (
        "Package counts can include multiple policies applied to the same evidence "
        "unit and are not independent clinical observations."
    ),
    (
        "Matched policy comparisons are descriptive sensitivity analyses on shared "
        "evidence units and do not identify a superior policy."
    ),
    (
        "Source-hash or trial-id disjointness does not establish population "
        "independence, comparability, transportability, or absence of bias."
    ),
    (
        "Gap mass, bounded VOI, action frequency, and planned cost remain "
        "uncalibrated workflow quantities, not economic or clinical value."
    ),
    (
        "No cross-trial or cross-program pooling, benefit-risk scoring, treatment "
        "recommendation, clinical acceptability inference, or terminal decision is "
        "performed."
    ),
)


class ClinicalCohortError(ValueError):
    """Raised when a cohort report cannot be compiled safely."""


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


def _round_metric(value: float) -> float:
    return round(float(value), 12)


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_non_negative_number(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _sorted_unique_text(values: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc
    for value in result:
        _require_text(value, field_name)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must contain unique values")
    if result != tuple(sorted(result)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return result


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def clinical_program_state_fingerprint(state: ProgramState) -> str:
    """Return the canonical digest used to bind an accepted program state."""

    _require_instance(state, ProgramState, "state")
    return _sha256(state)


def _evidence_unit_id(program_id: str, synthesis_fingerprint: str) -> str:
    return _sha256(
        {
            "program_id": program_id,
            "synthesis_fingerprint": synthesis_fingerprint,
        }
    )


@dataclass(frozen=True, slots=True)
class ClinicalCohortRate(SerializableRecord):
    count: int
    total: int
    rate: float

    def __post_init__(self) -> None:
        _require_non_negative_int(self.count, "count")
        _require_positive_int(self.total, "total")
        if self.count > self.total:
            raise ValueError("count cannot exceed total")
        expected = _round_metric(self.count / self.total)
        if self.rate != expected:
            raise ValueError("rate does not match count and total")


def _rate(count: int, total: int) -> ClinicalCohortRate:
    return ClinicalCohortRate(
        count=count,
        total=total,
        rate=_round_metric(count / total),
    )


@dataclass(frozen=True, slots=True)
class ClinicalCohortPolicyIdentity(SerializableRecord):
    policy_id: str
    policy_version: str
    policy_fingerprint: str

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_text(self.policy_version, "policy_version")
        _require_sha256(self.policy_fingerprint, "policy_fingerprint")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.policy_id, self.policy_version, self.policy_fingerprint)


@dataclass(frozen=True, slots=True)
class ClinicalCohortPackageBinding(SerializableRecord):
    package_id: str
    program_id: str
    integrity_sha256: str
    state_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.package_id, "package_id")
        _require_text(self.program_id, "program_id")
        _require_sha256(self.integrity_sha256, "integrity_sha256")
        if self.state_sha256 is not None:
            _require_sha256(self.state_sha256, "state_sha256")


@dataclass(frozen=True, slots=True)
class ClinicalCohortManifest(SerializableRecord):
    cohort_id: str
    cohort_specification_sha256: str
    package_bindings: tuple[ClinicalCohortPackageBinding, ...]
    analysis_scope: str = CLINICAL_COHORT_ANALYSIS_SCOPE

    def __post_init__(self) -> None:
        _require_text(self.cohort_id, "cohort_id")
        _require_sha256(
            self.cohort_specification_sha256,
            "cohort_specification_sha256",
        )
        bindings = _tuple(self.package_bindings, "package_bindings")
        object.__setattr__(self, "package_bindings", bindings)
        if len(bindings) < 2:
            raise ValueError("clinical cohort requires at least two packages")
        for binding in bindings:
            _require_instance(
                binding,
                ClinicalCohortPackageBinding,
                "package_bindings item",
            )
        package_ids = tuple(item.package_id for item in bindings)
        if len(package_ids) != len(set(package_ids)):
            raise ValueError("cohort package ids must be unique")
        expected_order = tuple(
            sorted(bindings, key=lambda item: (item.program_id, item.package_id))
        )
        if bindings != expected_order:
            raise ValueError("package_bindings must use canonical identity order")
        replay_modes = {item.state_sha256 is not None for item in bindings}
        if len(replay_modes) != 1:
            raise ValueError("state_sha256 must be declared for all packages or none")
        state_by_program: dict[str, str] = {}
        for binding in bindings:
            if binding.state_sha256 is None:
                continue
            previous = state_by_program.setdefault(
                binding.program_id,
                binding.state_sha256,
            )
            if previous != binding.state_sha256:
                raise ValueError("one program cannot bind multiple accepted states")
        if self.analysis_scope != CLINICAL_COHORT_ANALYSIS_SCOPE:
            raise ValueError("analysis_scope is unsupported")

    @property
    def state_replay_required(self) -> bool:
        return self.package_bindings[0].state_sha256 is not None

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalCohortDimensionStatus(SerializableRecord):
    dimension: ClinicalEvidenceDimension
    status: ClinicalDimensionStatus

    def __post_init__(self) -> None:
        _require_instance(self.dimension, ClinicalEvidenceDimension, "dimension")
        _require_instance(self.status, ClinicalDimensionStatus, "status")


@dataclass(frozen=True, slots=True)
class ClinicalCohortSelectedAction(SerializableRecord):
    rank: int
    action_id: str
    action_fingerprint: str
    tool_id: str
    operation: str
    purpose: str
    max_cost: float

    def __post_init__(self) -> None:
        _require_positive_int(self.rank, "rank")
        for field_name in ("action_id", "tool_id", "operation", "purpose"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.action_fingerprint, "action_fingerprint")
        _require_non_negative_number(self.max_cost, "max_cost")
        if self.max_cost <= 0:
            raise ValueError("max_cost must be positive")

    @property
    def identity_tuple(self) -> tuple[Any, ...]:
        return (
            self.action_id,
            self.action_fingerprint,
            self.tool_id,
            self.operation,
            self.purpose,
            self.max_cost,
        )


@dataclass(frozen=True, slots=True)
class ClinicalCohortPackageDiagnostic(SerializableRecord):
    package_id: str
    program_id: str
    integrity_sha256: str
    state_sha256: str | None
    as_of_date: date
    policy: ClinicalCohortPolicyIdentity
    synthesis_id: str
    synthesis_fingerprint: str
    evidence_unit_id: str
    disease_id: str
    candidate_id: str
    intervention_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    stage: Stage
    trial_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    decision: Decision
    plan_code: str
    dimension_statuses: tuple[ClinicalCohortDimensionStatus, ...]
    gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    targeted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    untargeted_gap_codes: tuple[ClinicalEvidenceGapCode, ...]
    selected_actions: tuple[ClinicalCohortSelectedAction, ...]
    planned_cost: float

    def __post_init__(self) -> None:
        for field_name in (
            "package_id",
            "program_id",
            "synthesis_id",
            "disease_id",
            "candidate_id",
            "intervention_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "plan_code",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "integrity_sha256",
            "synthesis_fingerprint",
            "evidence_unit_id",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.state_sha256 is not None:
            _require_sha256(self.state_sha256, "state_sha256")
        _require_date(self.as_of_date, "as_of_date")
        _require_instance(self.policy, ClinicalCohortPolicyIdentity, "policy")
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.decision, Decision, "decision")
        if self.decision not in _DECISION_ORDER:
            raise ValueError("cohort packages support advance, hold, or defer")
        expected_unit_id = _evidence_unit_id(
            self.program_id,
            self.synthesis_fingerprint,
        )
        if self.evidence_unit_id != expected_unit_id:
            raise ValueError("evidence_unit_id is not bound to program and synthesis")
        object.__setattr__(
            self,
            "trial_ids",
            _sorted_unique_text(self.trial_ids, "trial_ids"),
        )
        source_hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        object.__setattr__(self, "source_content_hashes", source_hashes)
        if len(self.trial_ids) < 2 or len(source_hashes) < 2:
            raise ValueError("cohort diagnostics require multi-trial provenance")
        for index, digest in enumerate(source_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        dimensions = _tuple(self.dimension_statuses, "dimension_statuses")
        object.__setattr__(self, "dimension_statuses", dimensions)
        for item in dimensions:
            _require_instance(
                item,
                ClinicalCohortDimensionStatus,
                "dimension_statuses item",
            )
        if tuple(item.dimension for item in dimensions) != _DIMENSION_ORDER:
            raise ValueError("dimension_statuses must use canonical complete order")
        gap_codes = _tuple(self.gap_codes, "gap_codes")
        targeted = _tuple(self.targeted_gap_codes, "targeted_gap_codes")
        untargeted = _tuple(self.untargeted_gap_codes, "untargeted_gap_codes")
        for field_name, values in (
            ("gap_codes", gap_codes),
            ("targeted_gap_codes", targeted),
            ("untargeted_gap_codes", untargeted),
        ):
            for code in values:
                _require_instance(code, ClinicalEvidenceGapCode, f"{field_name} item")
            expected = tuple(code for code in _GAP_ORDER if code in set(values))
            if values != expected:
                raise ValueError(f"{field_name} must use canonical unique order")
        object.__setattr__(self, "gap_codes", gap_codes)
        object.__setattr__(self, "targeted_gap_codes", targeted)
        object.__setattr__(self, "untargeted_gap_codes", untargeted)
        if set(targeted) & set(untargeted):
            raise ValueError("targeted and untargeted gap codes must be disjoint")
        if tuple(code for code in _GAP_ORDER if code in set((*targeted, *untargeted))) != gap_codes:
            raise ValueError("targeted and untargeted gap codes must partition gaps")
        selected = _tuple(self.selected_actions, "selected_actions")
        object.__setattr__(self, "selected_actions", selected)
        for action in selected:
            _require_instance(
                action,
                ClinicalCohortSelectedAction,
                "selected_actions item",
            )
        if tuple(item.rank for item in selected) != tuple(range(1, len(selected) + 1)):
            raise ValueError("selected action ranks must be contiguous")
        if len({item.action_id for item in selected}) != len(selected):
            raise ValueError("selected action ids must be unique")
        _require_non_negative_number(self.planned_cost, "planned_cost")
        expected_cost = _round_metric(sum(item.max_cost for item in selected))
        if not math.isclose(
            self.planned_cost,
            expected_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("planned_cost does not match selected actions")
        if self.decision is Decision.ADVANCE and (gap_codes or selected):
            raise ValueError("advance diagnostics cannot contain gaps or actions")
        if self.decision is Decision.HOLD and (not gap_codes or not selected):
            raise ValueError("hold diagnostics require gaps and actions")
        if self.decision is Decision.DEFER and (not gap_codes or selected):
            raise ValueError("defer diagnostics require gaps without actions")

    @property
    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.program_id,
            self.evidence_unit_id,
            *self.policy.sort_key,
            self.package_id,
        )


@dataclass(frozen=True, slots=True)
class ClinicalCohortDecisionMetric(SerializableRecord):
    decision: Decision
    packages: ClinicalCohortRate

    def __post_init__(self) -> None:
        if self.decision not in _DECISION_ORDER:
            raise ValueError("decision metric is outside the cohort decision set")
        _require_instance(self.packages, ClinicalCohortRate, "packages")


@dataclass(frozen=True, slots=True)
class ClinicalCohortDimensionMetric(SerializableRecord):
    dimension: ClinicalEvidenceDimension
    satisfied: ClinicalCohortRate
    gap: ClinicalCohortRate
    blocking_signal: ClinicalCohortRate

    def __post_init__(self) -> None:
        _require_instance(self.dimension, ClinicalEvidenceDimension, "dimension")
        for field_name in ("satisfied", "gap", "blocking_signal"):
            _require_instance(getattr(self, field_name), ClinicalCohortRate, field_name)
        totals = {self.satisfied.total, self.gap.total, self.blocking_signal.total}
        if len(totals) != 1:
            raise ValueError("dimension status denominators must match")
        if (
            self.satisfied.count + self.gap.count + self.blocking_signal.count
            != self.satisfied.total
        ):
            raise ValueError("dimension status counts must partition packages")


@dataclass(frozen=True, slots=True)
class ClinicalCohortGapMetric(SerializableRecord):
    code: ClinicalEvidenceGapCode
    dimension: ClinicalEvidenceDimension
    blocking: bool
    present_packages: ClinicalCohortRate
    targeted_packages: ClinicalCohortRate

    def __post_init__(self) -> None:
        _require_instance(self.code, ClinicalEvidenceGapCode, "code")
        _require_instance(self.dimension, ClinicalEvidenceDimension, "dimension")
        if self.dimension is not _GAP_DIMENSIONS[self.code]:
            raise ValueError("gap metric code does not match dimension")
        _require_bool(self.blocking, "blocking")
        if self.blocking != (self.code in _BLOCKING_GAP_CODES):
            raise ValueError("gap metric blocking flag is inconsistent")
        for field_name in ("present_packages", "targeted_packages"):
            _require_instance(getattr(self, field_name), ClinicalCohortRate, field_name)
        if self.present_packages.total != self.targeted_packages.total:
            raise ValueError("gap metric denominators must match")
        if self.targeted_packages.count > self.present_packages.count:
            raise ValueError("targeted packages cannot exceed present packages")


@dataclass(frozen=True, slots=True)
class ClinicalCohortActionMetric(SerializableRecord):
    action_id: str
    action_fingerprint: str
    tool_id: str
    operation: str
    purpose: str
    max_cost: float
    selected_packages: ClinicalCohortRate
    total_planned_cost: float

    def __post_init__(self) -> None:
        for field_name in ("action_id", "tool_id", "operation", "purpose"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.action_fingerprint, "action_fingerprint")
        _require_non_negative_number(self.max_cost, "max_cost")
        if self.max_cost <= 0:
            raise ValueError("max_cost must be positive")
        _require_instance(self.selected_packages, ClinicalCohortRate, "selected_packages")
        _require_non_negative_number(self.total_planned_cost, "total_planned_cost")
        expected = _round_metric(self.selected_packages.count * self.max_cost)
        if not math.isclose(
            self.total_planned_cost,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("total_planned_cost does not match action selections")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.action_id, self.action_fingerprint)


@dataclass(frozen=True, slots=True)
class ClinicalCohortPolicyStratum(SerializableRecord):
    policy: ClinicalCohortPolicyIdentity
    package_ids: tuple[str, ...]
    evidence_unit_ids: tuple[str, ...]
    decisions: tuple[ClinicalCohortDecisionMetric, ...]
    dimensions: tuple[ClinicalCohortDimensionMetric, ...]
    gaps: tuple[ClinicalCohortGapMetric, ...]
    actions: tuple[ClinicalCohortActionMetric, ...]
    total_planned_cost: float

    def __post_init__(self) -> None:
        _require_instance(self.policy, ClinicalCohortPolicyIdentity, "policy")
        object.__setattr__(
            self,
            "package_ids",
            _sorted_unique_text(self.package_ids, "package_ids"),
        )
        object.__setattr__(
            self,
            "evidence_unit_ids",
            _sorted_unique_text(self.evidence_unit_ids, "evidence_unit_ids"),
        )
        if not self.package_ids or not self.evidence_unit_ids:
            raise ValueError("policy strata must not be empty")
        _validate_metric_orders(
            self.decisions,
            self.dimensions,
            self.gaps,
            self.actions,
            len(self.package_ids),
        )
        _require_non_negative_number(self.total_planned_cost, "total_planned_cost")
        expected_cost = _round_metric(
            sum(item.total_planned_cost for item in self.actions)
        )
        if not math.isclose(
            self.total_planned_cost,
            expected_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("policy stratum planned cost is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalCohortDecisionTransition(SerializableRecord):
    decision_a: Decision
    decision_b: Decision
    count: int

    def __post_init__(self) -> None:
        if self.decision_a not in _DECISION_ORDER or self.decision_b not in _DECISION_ORDER:
            raise ValueError("decision transition is outside the cohort decision set")
        _require_non_negative_int(self.count, "count")


@dataclass(frozen=True, slots=True)
class ClinicalCohortGapComparison(SerializableRecord):
    code: ClinicalEvidenceGapCode
    both: int
    policy_a_only: int
    policy_b_only: int
    neither: int

    def __post_init__(self) -> None:
        _require_instance(self.code, ClinicalEvidenceGapCode, "code")
        for field_name in ("both", "policy_a_only", "policy_b_only", "neither"):
            _require_non_negative_int(getattr(self, field_name), field_name)

    @property
    def total(self) -> int:
        return self.both + self.policy_a_only + self.policy_b_only + self.neither


@dataclass(frozen=True, slots=True)
class ClinicalCohortMatchedPolicyComparison(SerializableRecord):
    policy_a: ClinicalCohortPolicyIdentity
    policy_b: ClinicalCohortPolicyIdentity
    evidence_unit_ids: tuple[str, ...]
    decision_transitions: tuple[ClinicalCohortDecisionTransition, ...]
    changed_decisions: ClinicalCohortRate
    changed_gap_profiles: ClinicalCohortRate
    changed_action_plans: ClinicalCohortRate
    gap_comparisons: tuple[ClinicalCohortGapComparison, ...]
    policy_a_total_planned_cost: float
    policy_b_total_planned_cost: float

    def __post_init__(self) -> None:
        for field_name in ("policy_a", "policy_b"):
            _require_instance(
                getattr(self, field_name),
                ClinicalCohortPolicyIdentity,
                field_name,
            )
        if self.policy_a.sort_key >= self.policy_b.sort_key:
            raise ValueError("matched policy identities must use canonical order")
        unit_ids = _sorted_unique_text(self.evidence_unit_ids, "evidence_unit_ids")
        object.__setattr__(self, "evidence_unit_ids", unit_ids)
        if not unit_ids:
            raise ValueError("matched policy comparison requires shared evidence units")
        transitions = _tuple(self.decision_transitions, "decision_transitions")
        object.__setattr__(self, "decision_transitions", transitions)
        for item in transitions:
            _require_instance(
                item,
                ClinicalCohortDecisionTransition,
                "decision_transitions item",
            )
        expected_pairs = tuple((a, b) for a in _DECISION_ORDER for b in _DECISION_ORDER)
        if tuple((item.decision_a, item.decision_b) for item in transitions) != expected_pairs:
            raise ValueError("decision transitions must use complete canonical order")
        if sum(item.count for item in transitions) != len(unit_ids):
            raise ValueError("decision transition counts must match shared units")
        for field_name in (
            "changed_decisions",
            "changed_gap_profiles",
            "changed_action_plans",
        ):
            metric = getattr(self, field_name)
            _require_instance(metric, ClinicalCohortRate, field_name)
            if metric.total != len(unit_ids):
                raise ValueError(f"{field_name} denominator must match shared units")
        gap_comparisons = _tuple(self.gap_comparisons, "gap_comparisons")
        object.__setattr__(self, "gap_comparisons", gap_comparisons)
        for item in gap_comparisons:
            _require_instance(
                item,
                ClinicalCohortGapComparison,
                "gap_comparisons item",
            )
        if tuple(item.code for item in gap_comparisons) != _GAP_ORDER:
            raise ValueError("gap comparisons must use complete canonical order")
        if any(item.total != len(unit_ids) for item in gap_comparisons):
            raise ValueError("gap comparison counts must match shared units")
        for field_name in (
            "policy_a_total_planned_cost",
            "policy_b_total_planned_cost",
        ):
            _require_non_negative_number(getattr(self, field_name), field_name)

    @property
    def sort_key(self) -> tuple[Any, ...]:
        return (*self.policy_a.sort_key, *self.policy_b.sort_key)


@dataclass(frozen=True, slots=True)
class ClinicalCohortProvenanceOverlap(SerializableRecord):
    kind: str
    value: str
    evidence_unit_ids: tuple[str, ...]
    program_ids: tuple[str, ...]
    package_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in _OVERLAP_KIND_ORDER:
            raise ValueError("provenance overlap kind is unsupported")
        _require_text(self.value, "value")
        if self.kind == "source_content_hash":
            _require_sha256(self.value, "value")
        for field_name in ("evidence_unit_ids", "program_ids", "package_ids"):
            object.__setattr__(
                self,
                field_name,
                _sorted_unique_text(getattr(self, field_name), field_name),
            )
        if len(self.evidence_unit_ids) < 2:
            raise ValueError("provenance overlap requires two evidence units")
        if not self.program_ids or len(self.package_ids) < 2:
            raise ValueError("provenance overlap identities must not be empty")

    @property
    def sort_key(self) -> tuple[int, str]:
        return (_OVERLAP_KIND_ORDER[self.kind], self.value)


def _validate_metric_orders(
    decisions: Sequence[ClinicalCohortDecisionMetric],
    dimensions: Sequence[ClinicalCohortDimensionMetric],
    gaps: Sequence[ClinicalCohortGapMetric],
    actions: Sequence[ClinicalCohortActionMetric],
    package_count: int,
) -> None:
    resolved_decisions = _tuple(decisions, "decisions")
    resolved_dimensions = _tuple(dimensions, "dimensions")
    resolved_gaps = _tuple(gaps, "gaps")
    resolved_actions = _tuple(actions, "actions")
    for item in resolved_decisions:
        _require_instance(item, ClinicalCohortDecisionMetric, "decisions item")
    for item in resolved_dimensions:
        _require_instance(item, ClinicalCohortDimensionMetric, "dimensions item")
    for item in resolved_gaps:
        _require_instance(item, ClinicalCohortGapMetric, "gaps item")
    for item in resolved_actions:
        _require_instance(item, ClinicalCohortActionMetric, "actions item")
    if tuple(item.decision for item in resolved_decisions) != _DECISION_ORDER:
        raise ValueError("decision metrics must use complete canonical order")
    if tuple(item.dimension for item in resolved_dimensions) != _DIMENSION_ORDER:
        raise ValueError("dimension metrics must use complete canonical order")
    if tuple(item.code for item in resolved_gaps) != _GAP_ORDER:
        raise ValueError("gap metrics must use complete canonical order")
    if tuple(item.sort_key for item in resolved_actions) != tuple(
        sorted(item.sort_key for item in resolved_actions)
    ):
        raise ValueError("action metrics must use canonical identity order")
    if len({item.action_fingerprint for item in resolved_actions}) != len(
        resolved_actions
    ):
        raise ValueError("action metric fingerprints must be unique")
    all_rates = [item.packages for item in resolved_decisions]
    all_rates.extend(
        metric
        for item in resolved_dimensions
        for metric in (item.satisfied, item.gap, item.blocking_signal)
    )
    all_rates.extend(
        metric
        for item in resolved_gaps
        for metric in (item.present_packages, item.targeted_packages)
    )
    all_rates.extend(item.selected_packages for item in resolved_actions)
    if any(item.total != package_count for item in all_rates):
        raise ValueError("metric denominator does not match package count")
    if sum(item.packages.count for item in resolved_decisions) != package_count:
        raise ValueError("decision counts must partition packages")


@dataclass(frozen=True, slots=True)
class ClinicalCohortReport(SerializableRecord):
    cohort_id: str
    cohort_specification_sha256: str
    manifest_fingerprint: str
    method_id: str
    analysis_scope: str
    package_validation_scope: str
    earliest_as_of_date: date
    latest_as_of_date: date
    package_count: int
    program_count: int
    evidence_unit_count: int
    policy_count: int
    packages: tuple[ClinicalCohortPackageDiagnostic, ...]
    decisions: tuple[ClinicalCohortDecisionMetric, ...]
    dimensions: tuple[ClinicalCohortDimensionMetric, ...]
    gaps: tuple[ClinicalCohortGapMetric, ...]
    actions: tuple[ClinicalCohortActionMetric, ...]
    policy_strata: tuple[ClinicalCohortPolicyStratum, ...]
    matched_policy_comparisons: tuple[ClinicalCohortMatchedPolicyComparison, ...]
    provenance_overlaps: tuple[ClinicalCohortProvenanceOverlap, ...]
    evidence_units_source_disjoint: bool
    evidence_units_trial_disjoint: bool
    outcome_labels_included: bool
    performance_metrics_included: bool
    outcome_calibration_status: str
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        _require_text(self.cohort_id, "cohort_id")
        _require_sha256(
            self.cohort_specification_sha256,
            "cohort_specification_sha256",
        )
        _require_sha256(self.manifest_fingerprint, "manifest_fingerprint")
        if self.method_id != CLINICAL_COHORT_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.analysis_scope != CLINICAL_COHORT_ANALYSIS_SCOPE:
            raise ValueError("analysis_scope is unsupported")
        if self.package_validation_scope not in _PACKAGE_VALIDATION_SCOPES:
            raise ValueError("package_validation_scope is unsupported")
        _require_date(self.earliest_as_of_date, "earliest_as_of_date")
        _require_date(self.latest_as_of_date, "latest_as_of_date")
        if self.latest_as_of_date < self.earliest_as_of_date:
            raise ValueError("latest_as_of_date cannot precede earliest_as_of_date")
        for field_name in (
            "package_count",
            "program_count",
            "evidence_unit_count",
            "policy_count",
        ):
            _require_positive_int(getattr(self, field_name), field_name)
        packages = _tuple(self.packages, "packages")
        object.__setattr__(self, "packages", packages)
        if len(packages) < 2 or len(packages) != self.package_count:
            raise ValueError("package_count does not match cohort packages")
        for item in packages:
            _require_instance(item, ClinicalCohortPackageDiagnostic, "packages item")
        if tuple(item.sort_key for item in packages) != tuple(
            sorted(item.sort_key for item in packages)
        ):
            raise ValueError("packages must use canonical diagnostic order")
        if len({item.package_id for item in packages}) != len(packages):
            raise ValueError("report package ids must be unique")
        replayed = {item.state_sha256 is not None for item in packages}
        if len(replayed) != 1:
            raise ValueError("report package replay modes must be uniform")
        expected_scope = (
            "integrity_structure_and_state_replay"
            if True in replayed
            else "integrity_and_structure"
        )
        if self.package_validation_scope != expected_scope:
            raise ValueError("package_validation_scope does not match diagnostics")
        policy_by_identity: dict[tuple[str, str], str] = {}
        seen_unit_policy: set[tuple[str, str]] = set()
        for item in packages:
            identity = (item.policy.policy_id, item.policy.policy_version)
            previous = policy_by_identity.setdefault(
                identity,
                item.policy.policy_fingerprint,
            )
            if previous != item.policy.policy_fingerprint:
                raise ValueError("policy id and version are rebound across packages")
            unit_policy = (item.evidence_unit_id, item.policy.policy_fingerprint)
            if unit_policy in seen_unit_policy:
                raise ValueError("one policy can appear once per evidence unit")
            seen_unit_policy.add(unit_policy)
        expected_counts = (
            len(packages),
            len({item.program_id for item in packages}),
            len({item.evidence_unit_id for item in packages}),
            len({item.policy.policy_fingerprint for item in packages}),
        )
        observed_counts = (
            self.package_count,
            self.program_count,
            self.evidence_unit_count,
            self.policy_count,
        )
        if observed_counts != expected_counts:
            raise ValueError("cohort identity counts are inconsistent")
        dates = tuple(item.as_of_date for item in packages)
        if (self.earliest_as_of_date, self.latest_as_of_date) != (
            min(dates),
            max(dates),
        ):
            raise ValueError("cohort cutoff range is inconsistent")
        bindings = tuple(
            sorted(
                (
                    ClinicalCohortPackageBinding(
                        package_id=item.package_id,
                        program_id=item.program_id,
                        integrity_sha256=item.integrity_sha256,
                        state_sha256=item.state_sha256,
                    )
                    for item in packages
                ),
                key=lambda item: (item.program_id, item.package_id),
            )
        )
        reconstructed_manifest = ClinicalCohortManifest(
            cohort_id=self.cohort_id,
            cohort_specification_sha256=self.cohort_specification_sha256,
            package_bindings=bindings,
            analysis_scope=self.analysis_scope,
        )
        if reconstructed_manifest.fingerprint != self.manifest_fingerprint:
            raise ValueError("manifest_fingerprint does not match report packages")
        _validate_metric_orders(
            self.decisions,
            self.dimensions,
            self.gaps,
            self.actions,
            self.package_count,
        )
        for field_name, expected_type in (
            ("policy_strata", ClinicalCohortPolicyStratum),
            (
                "matched_policy_comparisons",
                ClinicalCohortMatchedPolicyComparison,
            ),
            ("provenance_overlaps", ClinicalCohortProvenanceOverlap),
        ):
            values = _tuple(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, values)
            for item in values:
                _require_instance(item, expected_type, f"{field_name} item")
        expected = _aggregate_diagnostics(packages)
        for field_name in (
            "decisions",
            "dimensions",
            "gaps",
            "actions",
            "policy_strata",
            "matched_policy_comparisons",
            "provenance_overlaps",
            "evidence_units_source_disjoint",
            "evidence_units_trial_disjoint",
        ):
            if getattr(self, field_name) != expected[field_name]:
                raise ValueError(f"{field_name} does not match package diagnostics")
        for field_name in (
            "evidence_units_source_disjoint",
            "evidence_units_trial_disjoint",
            "outcome_labels_included",
            "performance_metrics_included",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if self.outcome_labels_included or self.performance_metrics_included:
            raise ValueError("cohort diagnostics cannot include outcome performance")
        if self.outcome_calibration_status != _OUTCOME_CALIBRATION_STATUS:
            raise ValueError("outcome_calibration_status is unsupported")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("required cohort limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _decision_metrics(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortDecisionMetric, ...]:
    total = len(packages)
    return tuple(
        ClinicalCohortDecisionMetric(
            decision=decision,
            packages=_rate(
                sum(item.decision is decision for item in packages),
                total,
            ),
        )
        for decision in _DECISION_ORDER
    )


def _dimension_metrics(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortDimensionMetric, ...]:
    total = len(packages)
    status_by_package = [
        {item.dimension: item.status for item in package.dimension_statuses}
        for package in packages
    ]
    return tuple(
        ClinicalCohortDimensionMetric(
            dimension=dimension,
            satisfied=_rate(
                sum(
                    values[dimension] is ClinicalDimensionStatus.SATISFIED
                    for values in status_by_package
                ),
                total,
            ),
            gap=_rate(
                sum(
                    values[dimension] is ClinicalDimensionStatus.GAP
                    for values in status_by_package
                ),
                total,
            ),
            blocking_signal=_rate(
                sum(
                    values[dimension] is ClinicalDimensionStatus.BLOCKING_SIGNAL
                    for values in status_by_package
                ),
                total,
            ),
        )
        for dimension in _DIMENSION_ORDER
    )


def _gap_metrics(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortGapMetric, ...]:
    total = len(packages)
    return tuple(
        ClinicalCohortGapMetric(
            code=code,
            dimension=_GAP_DIMENSIONS[code],
            blocking=code in _BLOCKING_GAP_CODES,
            present_packages=_rate(
                sum(code in item.gap_codes for item in packages),
                total,
            ),
            targeted_packages=_rate(
                sum(code in item.targeted_gap_codes for item in packages),
                total,
            ),
        )
        for code in _GAP_ORDER
    )


def _action_metrics(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortActionMetric, ...]:
    total = len(packages)
    action_packages: dict[str, set[str]] = defaultdict(set)
    action_identity: dict[str, tuple[Any, ...]] = {}
    for package in packages:
        for action in package.selected_actions:
            previous = action_identity.setdefault(
                action.action_fingerprint,
                action.identity_tuple,
            )
            if previous != action.identity_tuple:
                raise ValueError("action fingerprint is rebound across packages")
            action_packages[action.action_fingerprint].add(package.package_id)
    metrics = []
    for fingerprint, package_ids in action_packages.items():
        action_id, _, tool_id, operation, purpose, max_cost = action_identity[
            fingerprint
        ]
        metrics.append(
            ClinicalCohortActionMetric(
                action_id=action_id,
                action_fingerprint=fingerprint,
                tool_id=tool_id,
                operation=operation,
                purpose=purpose,
                max_cost=max_cost,
                selected_packages=_rate(len(package_ids), total),
                total_planned_cost=_round_metric(len(package_ids) * max_cost),
            )
        )
    return tuple(sorted(metrics, key=lambda item: item.sort_key))


def _policy_strata(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortPolicyStratum, ...]:
    grouped: dict[str, list[ClinicalCohortPackageDiagnostic]] = defaultdict(list)
    for package in packages:
        grouped[package.policy.policy_fingerprint].append(package)
    strata = []
    for resolved in grouped.values():
        policy = resolved[0].policy
        resolved_tuple = tuple(sorted(resolved, key=lambda item: item.sort_key))
        strata.append(
            ClinicalCohortPolicyStratum(
                policy=policy,
                package_ids=tuple(sorted(item.package_id for item in resolved_tuple)),
                evidence_unit_ids=tuple(
                    sorted({item.evidence_unit_id for item in resolved_tuple})
                ),
                decisions=_decision_metrics(resolved_tuple),
                dimensions=_dimension_metrics(resolved_tuple),
                gaps=_gap_metrics(resolved_tuple),
                actions=_action_metrics(resolved_tuple),
                total_planned_cost=_round_metric(
                    sum(item.planned_cost for item in resolved_tuple)
                ),
            )
        )
    return tuple(sorted(strata, key=lambda item: item.policy.sort_key))


def _matched_policy_comparisons(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortMatchedPolicyComparison, ...]:
    by_unit: dict[str, dict[str, ClinicalCohortPackageDiagnostic]] = defaultdict(dict)
    policies: dict[str, ClinicalCohortPolicyIdentity] = {}
    for package in packages:
        policy_fingerprint = package.policy.policy_fingerprint
        policies[policy_fingerprint] = package.policy
        if policy_fingerprint in by_unit[package.evidence_unit_id]:
            raise ValueError("one policy can appear once per evidence unit")
        by_unit[package.evidence_unit_id][policy_fingerprint] = package
    ordered_policies = tuple(sorted(policies.values(), key=lambda item: item.sort_key))
    comparisons = []
    for policy_a, policy_b in combinations(ordered_policies, 2):
        shared_ids = tuple(
            sorted(
                unit_id
                for unit_id, unit_packages in by_unit.items()
                if policy_a.policy_fingerprint in unit_packages
                and policy_b.policy_fingerprint in unit_packages
            )
        )
        if not shared_ids:
            continue
        pairs = tuple(
            (
                by_unit[unit_id][policy_a.policy_fingerprint],
                by_unit[unit_id][policy_b.policy_fingerprint],
            )
            for unit_id in shared_ids
        )
        transitions = tuple(
            ClinicalCohortDecisionTransition(
                decision_a=decision_a,
                decision_b=decision_b,
                count=sum(
                    item_a.decision is decision_a and item_b.decision is decision_b
                    for item_a, item_b in pairs
                ),
            )
            for decision_a in _DECISION_ORDER
            for decision_b in _DECISION_ORDER
        )
        gap_comparisons = []
        for code in _GAP_ORDER:
            both = sum(
                code in item_a.gap_codes and code in item_b.gap_codes
                for item_a, item_b in pairs
            )
            a_only = sum(
                code in item_a.gap_codes and code not in item_b.gap_codes
                for item_a, item_b in pairs
            )
            b_only = sum(
                code not in item_a.gap_codes and code in item_b.gap_codes
                for item_a, item_b in pairs
            )
            gap_comparisons.append(
                ClinicalCohortGapComparison(
                    code=code,
                    both=both,
                    policy_a_only=a_only,
                    policy_b_only=b_only,
                    neither=len(pairs) - both - a_only - b_only,
                )
            )
        comparisons.append(
            ClinicalCohortMatchedPolicyComparison(
                policy_a=policy_a,
                policy_b=policy_b,
                evidence_unit_ids=shared_ids,
                decision_transitions=transitions,
                changed_decisions=_rate(
                    sum(item_a.decision is not item_b.decision for item_a, item_b in pairs),
                    len(pairs),
                ),
                changed_gap_profiles=_rate(
                    sum(
                        item_a.gap_codes != item_b.gap_codes
                        for item_a, item_b in pairs
                    ),
                    len(pairs),
                ),
                changed_action_plans=_rate(
                    sum(
                        tuple(
                            action.action_fingerprint
                            for action in item_a.selected_actions
                        )
                        != tuple(
                            action.action_fingerprint
                            for action in item_b.selected_actions
                        )
                        for item_a, item_b in pairs
                    ),
                    len(pairs),
                ),
                gap_comparisons=tuple(gap_comparisons),
                policy_a_total_planned_cost=_round_metric(
                    sum(item_a.planned_cost for item_a, _ in pairs)
                ),
                policy_b_total_planned_cost=_round_metric(
                    sum(item_b.planned_cost for _, item_b in pairs)
                ),
            )
        )
    return tuple(sorted(comparisons, key=lambda item: item.sort_key))


def _provenance_overlaps(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> tuple[ClinicalCohortProvenanceOverlap, ...]:
    memberships: dict[tuple[str, str], set[str]] = defaultdict(set)
    packages_by_value: dict[tuple[str, str], set[str]] = defaultdict(set)
    programs_by_value: dict[tuple[str, str], set[str]] = defaultdict(set)
    for package in packages:
        for kind, values in (
            ("source_content_hash", package.source_content_hashes),
            ("trial_id", package.trial_ids),
        ):
            for value in values:
                key = (kind, value)
                memberships[key].add(package.evidence_unit_id)
                packages_by_value[key].add(package.package_id)
                programs_by_value[key].add(package.program_id)
    overlaps = tuple(
        ClinicalCohortProvenanceOverlap(
            kind=kind,
            value=value,
            evidence_unit_ids=tuple(sorted(unit_ids)),
            program_ids=tuple(sorted(programs_by_value[(kind, value)])),
            package_ids=tuple(sorted(packages_by_value[(kind, value)])),
        )
        for (kind, value), unit_ids in memberships.items()
        if len(unit_ids) > 1
    )
    return tuple(sorted(overlaps, key=lambda item: item.sort_key))


def _aggregate_diagnostics(
    packages: Sequence[ClinicalCohortPackageDiagnostic],
) -> dict[str, Any]:
    resolved = tuple(packages)
    overlaps = _provenance_overlaps(resolved)
    return {
        "decisions": _decision_metrics(resolved),
        "dimensions": _dimension_metrics(resolved),
        "gaps": _gap_metrics(resolved),
        "actions": _action_metrics(resolved),
        "policy_strata": _policy_strata(resolved),
        "matched_policy_comparisons": _matched_policy_comparisons(resolved),
        "provenance_overlaps": overlaps,
        "evidence_units_source_disjoint": not any(
            item.kind == "source_content_hash" for item in overlaps
        ),
        "evidence_units_trial_disjoint": not any(
            item.kind == "trial_id" for item in overlaps
        ),
    }


def _package_diagnostic(
    package: ClinicalDecisionPackage,
    state_sha256: str | None,
) -> ClinicalCohortPackageDiagnostic:
    catalog = {item.action_id: item for item in package.action_catalog}
    gaps_by_id = {item.gap_id: item for item in package.tensor.gaps}
    targeted_codes = {
        gaps_by_id[gap_id].code for gap_id in package.plan.targeted_gap_ids
    }
    untargeted_codes = {
        gaps_by_id[gap_id].code for gap_id in package.plan.untargeted_gap_ids
    }
    selected_actions = tuple(
        ClinicalCohortSelectedAction(
            rank=item.rank,
            action_id=item.action_id,
            action_fingerprint=item.action_fingerprint,
            tool_id=catalog[item.action_id].tool_id,
            operation=catalog[item.action_id].operation,
            purpose=catalog[item.action_id].purpose,
            max_cost=item.max_cost,
        )
        for item in package.plan.selected_actions
    )
    synthesis_fingerprint = package.tensor.synthesis_fingerprint
    return ClinicalCohortPackageDiagnostic(
        package_id=package.package_id,
        program_id=package.program_id,
        integrity_sha256=package.fingerprint,
        state_sha256=state_sha256,
        as_of_date=package.as_of_date,
        policy=ClinicalCohortPolicyIdentity(
            policy_id=package.policy.policy_id,
            policy_version=package.policy.version,
            policy_fingerprint=package.policy.fingerprint,
        ),
        synthesis_id=package.tensor.synthesis_id,
        synthesis_fingerprint=synthesis_fingerprint,
        evidence_unit_id=_evidence_unit_id(
            package.program_id,
            synthesis_fingerprint,
        ),
        disease_id=package.tensor.disease_id,
        candidate_id=package.tensor.candidate_id,
        intervention_id=package.tensor.intervention_id,
        endpoint_mapping_id=package.tensor.endpoint_mapping_id,
        endpoint_family=package.tensor.endpoint_family,
        stage=package.tensor.stage,
        trial_ids=tuple(sorted(item.trial_id for item in package.tensor.cells)),
        source_content_hashes=package.tensor.source_content_hashes,
        decision=package.plan.decision,
        plan_code=package.plan.code,
        dimension_statuses=tuple(
            ClinicalCohortDimensionStatus(
                dimension=item.dimension,
                status=item.status,
            )
            for item in package.tensor.dimensions
        ),
        gap_codes=tuple(item.code for item in package.tensor.gaps),
        targeted_gap_codes=tuple(
            code for code in _GAP_ORDER if code in targeted_codes
        ),
        untargeted_gap_codes=tuple(
            code for code in _GAP_ORDER if code in untargeted_codes
        ),
        selected_actions=selected_actions,
        planned_cost=package.plan.planned_cost,
    )


def compile_clinical_cohort_report(
    manifest: ClinicalCohortManifest,
    packages: Sequence[ClinicalDecisionPackage],
    *,
    states: Sequence[ProgramState] = (),
) -> ClinicalCohortReport:
    """Compile deterministic cohort diagnostics from an exact package roster."""

    _require_instance(manifest, ClinicalCohortManifest, "manifest")
    resolved_packages = _tuple(packages, "packages")
    for package in resolved_packages:
        _require_instance(package, ClinicalDecisionPackage, "packages item")
    packages_by_id = {item.package_id: item for item in resolved_packages}
    if len(packages_by_id) != len(resolved_packages):
        raise ClinicalCohortError("input package ids must be unique")
    expected_ids = {item.package_id for item in manifest.package_bindings}
    if set(packages_by_id) != expected_ids:
        raise ClinicalCohortError("input packages do not exactly match the manifest")

    resolved_states = _tuple(states, "states")
    for state in resolved_states:
        _require_instance(state, ProgramState, "states item")
    states_by_program = {item.program_id: item for item in resolved_states}
    if len(states_by_program) != len(resolved_states):
        raise ClinicalCohortError("input state program ids must be unique")
    expected_programs = {item.program_id for item in manifest.package_bindings}
    if manifest.state_replay_required:
        if set(states_by_program) != expected_programs:
            raise ClinicalCohortError(
                "accepted states do not exactly cover manifest programs"
            )
    elif resolved_states:
        raise ClinicalCohortError(
            "states cannot be supplied when the manifest omits state_sha256"
        )

    diagnostics = []
    for binding in manifest.package_bindings:
        package = packages_by_id[binding.package_id]
        if package.program_id != binding.program_id:
            raise ClinicalCohortError("package program_id does not match manifest")
        if package.fingerprint != binding.integrity_sha256:
            raise ClinicalCohortError("package integrity does not match manifest")
        state_sha256 = None
        if manifest.state_replay_required:
            state = states_by_program[binding.program_id]
            state_sha256 = clinical_program_state_fingerprint(state)
            if state_sha256 != binding.state_sha256:
                raise ClinicalCohortError("accepted state integrity does not match manifest")
            failures = validate_clinical_decision_against_state(state, package)
            if failures:
                raise ClinicalCohortError(
                    "package failed accepted-state replay: " + ", ".join(failures)
                )
        diagnostics.append(_package_diagnostic(package, state_sha256))
    ordered = tuple(sorted(diagnostics, key=lambda item: item.sort_key))
    aggregate = _aggregate_diagnostics(ordered)
    dates = tuple(item.as_of_date for item in ordered)
    return ClinicalCohortReport(
        cohort_id=manifest.cohort_id,
        cohort_specification_sha256=manifest.cohort_specification_sha256,
        manifest_fingerprint=manifest.fingerprint,
        method_id=CLINICAL_COHORT_METHOD_ID,
        analysis_scope=manifest.analysis_scope,
        package_validation_scope=(
            "integrity_structure_and_state_replay"
            if manifest.state_replay_required
            else "integrity_and_structure"
        ),
        earliest_as_of_date=min(dates),
        latest_as_of_date=max(dates),
        package_count=len(ordered),
        program_count=len({item.program_id for item in ordered}),
        evidence_unit_count=len({item.evidence_unit_id for item in ordered}),
        policy_count=len({item.policy.policy_fingerprint for item in ordered}),
        packages=ordered,
        decisions=aggregate["decisions"],
        dimensions=aggregate["dimensions"],
        gaps=aggregate["gaps"],
        actions=aggregate["actions"],
        policy_strata=aggregate["policy_strata"],
        matched_policy_comparisons=aggregate["matched_policy_comparisons"],
        provenance_overlaps=aggregate["provenance_overlaps"],
        evidence_units_source_disjoint=aggregate["evidence_units_source_disjoint"],
        evidence_units_trial_disjoint=aggregate["evidence_units_trial_disjoint"],
        outcome_labels_included=False,
        performance_metrics_included=False,
        outcome_calibration_status=_OUTCOME_CALIBRATION_STATUS,
    )


def validate_clinical_cohort_report(
    report: ClinicalCohortReport,
    manifest: ClinicalCohortManifest,
    packages: Sequence[ClinicalDecisionPackage],
    *,
    states: Sequence[ProgramState] = (),
) -> tuple[str, ...]:
    """Recompile a cohort report from its exact manifest, packages, and states."""

    try:
        rebuilt = compile_clinical_cohort_report(
            manifest,
            packages,
            states=states,
        )
    except (ClinicalCohortError, TypeError, ValueError):
        return ("cohort_recompile_failed",)
    if rebuilt != report:
        return ("recompiled_cohort_report_mismatch",)
    return ()


def clinical_cohort_report_summary(
    report: ClinicalCohortReport,
) -> dict[str, Any]:
    """Return a compact human- and machine-readable cohort projection."""

    _require_instance(report, ClinicalCohortReport, "report")
    return {
        "schema_version": CLINICAL_COHORT_SUMMARY_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "cohort_id": report.cohort_id,
        "manifest_fingerprint": report.manifest_fingerprint,
        "package_validation_scope": report.package_validation_scope,
        "counts": {
            "packages": report.package_count,
            "programs": report.program_count,
            "evidence_units": report.evidence_unit_count,
            "policies": report.policy_count,
        },
        "decision_counts": {
            item.decision.value: item.packages.count for item in report.decisions
        },
        "matched_policy_comparison_count": len(
            report.matched_policy_comparisons
        ),
        "provenance_overlap_count": len(report.provenance_overlaps),
        "evidence_units_source_disjoint": (
            report.evidence_units_source_disjoint
        ),
        "evidence_units_trial_disjoint": report.evidence_units_trial_disjoint,
        "outcome_calibration_status": report.outcome_calibration_status,
    }


def clinical_cohort_validation_report(
    report: ClinicalCohortReport,
    *,
    failures: Sequence[str] = (),
    scope: str = "integrity_and_aggregate_consistency",
) -> dict[str, Any]:
    """Return a compact cohort summary with explicit validation status."""

    resolved_failures = tuple(failures)
    for failure in resolved_failures:
        _require_text(failure, "failure code")
    if len(resolved_failures) != len(set(resolved_failures)):
        raise ValueError("failure codes must be unique")
    _require_text(scope, "scope")
    return {
        **clinical_cohort_report_summary(report),
        "validation": {
            "status": "valid" if not resolved_failures else "invalid",
            "scope": scope,
            "failure_codes": list(resolved_failures),
        },
    }


def clinical_cohort_manifest_envelope(
    manifest: ClinicalCohortManifest,
) -> dict[str, Any]:
    _require_instance(manifest, ClinicalCohortManifest, "manifest")
    return {
        "schema_version": CLINICAL_COHORT_MANIFEST_SCHEMA_VERSION,
        "integrity_sha256": manifest.fingerprint,
        "manifest": manifest.to_dict(),
    }


def clinical_cohort_report_envelope(
    report: ClinicalCohortReport,
) -> dict[str, Any]:
    _require_instance(report, ClinicalCohortReport, "report")
    return {
        "schema_version": CLINICAL_COHORT_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
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


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc


def _parse_enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(f"{path} is not a valid {enum_type.__name__}") from exc


def _strict_json(payload: str, label: str) -> Any:
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RecordParseError(f"{label} duplicates key {key}")
            result[key] = item
        return result

    def reject_constant(value: str) -> Any:
        raise RecordParseError(f"{label} contains {value}")

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(f"{label} is not valid JSON") from exc


def _integrity_payload(
    value: Any,
    *,
    path: str,
    schema_version: str,
    payload_key: str,
) -> tuple[dict[str, Any], str]:
    data = _record(
        value,
        path,
        {"schema_version", "integrity_sha256", payload_key},
    )
    if data["schema_version"] != schema_version:
        raise RecordParseError(f"{path} schema_version is unsupported")
    _require_sha256(data["integrity_sha256"], f"{path}.integrity_sha256")
    if not isinstance(data[payload_key], Mapping):
        raise RecordParseError(f"{path}.{payload_key} must be an object")
    return dict(data[payload_key]), data["integrity_sha256"]


def _parse_binding(value: Any, path: str) -> ClinicalCohortPackageBinding:
    data = _record(
        value,
        path,
        {"package_id", "program_id", "integrity_sha256", "state_sha256"},
    )
    return ClinicalCohortPackageBinding(**data)


def clinical_cohort_manifest_from_dict(value: Any) -> ClinicalCohortManifest:
    """Parse and integrity-check one exact cohort manifest envelope."""

    raw, expected_hash = _integrity_payload(
        value,
        path="clinical_cohort_manifest_envelope",
        schema_version=CLINICAL_COHORT_MANIFEST_SCHEMA_VERSION,
        payload_key="manifest",
    )
    data = _record(
        raw,
        "manifest",
        {
            "cohort_id",
            "cohort_specification_sha256",
            "package_bindings",
            "analysis_scope",
        },
    )
    manifest = ClinicalCohortManifest(
        cohort_id=data["cohort_id"],
        cohort_specification_sha256=data["cohort_specification_sha256"],
        package_bindings=tuple(
            _parse_binding(item, f"manifest.package_bindings[{index}]")
            for index, item in enumerate(
                _sequence(data["package_bindings"], "manifest.package_bindings")
            )
        ),
        analysis_scope=data["analysis_scope"],
    )
    if manifest.fingerprint != expected_hash:
        raise RecordParseError("parsed cohort manifest changed canonical identity")
    return manifest


def clinical_cohort_manifest_from_json(payload: str) -> ClinicalCohortManifest:
    return clinical_cohort_manifest_from_dict(
        _strict_json(payload, "clinical cohort manifest")
    )


def _parse_rate(value: Any, path: str) -> ClinicalCohortRate:
    return ClinicalCohortRate(**_record(value, path, {"count", "total", "rate"}))


def _parse_policy(value: Any, path: str) -> ClinicalCohortPolicyIdentity:
    return ClinicalCohortPolicyIdentity(
        **_record(
            value,
            path,
            {"policy_id", "policy_version", "policy_fingerprint"},
        )
    )


def _parse_dimension_status(
    value: Any,
    path: str,
) -> ClinicalCohortDimensionStatus:
    data = _record(value, path, {"dimension", "status"})
    return ClinicalCohortDimensionStatus(
        dimension=_parse_enum(
            ClinicalEvidenceDimension,
            data["dimension"],
            f"{path}.dimension",
        ),
        status=_parse_enum(
            ClinicalDimensionStatus,
            data["status"],
            f"{path}.status",
        ),
    )


def _parse_selected_action(
    value: Any,
    path: str,
) -> ClinicalCohortSelectedAction:
    return ClinicalCohortSelectedAction(
        **_record(
            value,
            path,
            {
                "rank",
                "action_id",
                "action_fingerprint",
                "tool_id",
                "operation",
                "purpose",
                "max_cost",
            },
        )
    )


def _parse_gap_codes(value: Any, path: str) -> tuple[ClinicalEvidenceGapCode, ...]:
    return tuple(
        _parse_enum(ClinicalEvidenceGapCode, item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path))
    )


def _parse_package_diagnostic(
    value: Any,
    path: str,
) -> ClinicalCohortPackageDiagnostic:
    fields = {
        "package_id",
        "program_id",
        "integrity_sha256",
        "state_sha256",
        "as_of_date",
        "policy",
        "synthesis_id",
        "synthesis_fingerprint",
        "evidence_unit_id",
        "disease_id",
        "candidate_id",
        "intervention_id",
        "endpoint_mapping_id",
        "endpoint_family",
        "stage",
        "trial_ids",
        "source_content_hashes",
        "decision",
        "plan_code",
        "dimension_statuses",
        "gap_codes",
        "targeted_gap_codes",
        "untargeted_gap_codes",
        "selected_actions",
        "planned_cost",
    }
    data = _record(value, path, fields)
    return ClinicalCohortPackageDiagnostic(
        package_id=data["package_id"],
        program_id=data["program_id"],
        integrity_sha256=data["integrity_sha256"],
        state_sha256=data["state_sha256"],
        as_of_date=_parse_date(data["as_of_date"], f"{path}.as_of_date"),
        policy=_parse_policy(data["policy"], f"{path}.policy"),
        synthesis_id=data["synthesis_id"],
        synthesis_fingerprint=data["synthesis_fingerprint"],
        evidence_unit_id=data["evidence_unit_id"],
        disease_id=data["disease_id"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        endpoint_mapping_id=data["endpoint_mapping_id"],
        endpoint_family=data["endpoint_family"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        trial_ids=tuple(_sequence(data["trial_ids"], f"{path}.trial_ids")),
        source_content_hashes=tuple(
            _sequence(data["source_content_hashes"], f"{path}.source_content_hashes")
        ),
        decision=_parse_enum(Decision, data["decision"], f"{path}.decision"),
        plan_code=data["plan_code"],
        dimension_statuses=tuple(
            _parse_dimension_status(item, f"{path}.dimension_statuses[{index}]")
            for index, item in enumerate(
                _sequence(data["dimension_statuses"], f"{path}.dimension_statuses")
            )
        ),
        gap_codes=_parse_gap_codes(data["gap_codes"], f"{path}.gap_codes"),
        targeted_gap_codes=_parse_gap_codes(
            data["targeted_gap_codes"],
            f"{path}.targeted_gap_codes",
        ),
        untargeted_gap_codes=_parse_gap_codes(
            data["untargeted_gap_codes"],
            f"{path}.untargeted_gap_codes",
        ),
        selected_actions=tuple(
            _parse_selected_action(item, f"{path}.selected_actions[{index}]")
            for index, item in enumerate(
                _sequence(data["selected_actions"], f"{path}.selected_actions")
            )
        ),
        planned_cost=data["planned_cost"],
    )


def _parse_decision_metric(
    value: Any,
    path: str,
) -> ClinicalCohortDecisionMetric:
    data = _record(value, path, {"decision", "packages"})
    return ClinicalCohortDecisionMetric(
        decision=_parse_enum(Decision, data["decision"], f"{path}.decision"),
        packages=_parse_rate(data["packages"], f"{path}.packages"),
    )


def _parse_dimension_metric(
    value: Any,
    path: str,
) -> ClinicalCohortDimensionMetric:
    data = _record(
        value,
        path,
        {"dimension", "satisfied", "gap", "blocking_signal"},
    )
    return ClinicalCohortDimensionMetric(
        dimension=_parse_enum(
            ClinicalEvidenceDimension,
            data["dimension"],
            f"{path}.dimension",
        ),
        satisfied=_parse_rate(data["satisfied"], f"{path}.satisfied"),
        gap=_parse_rate(data["gap"], f"{path}.gap"),
        blocking_signal=_parse_rate(
            data["blocking_signal"],
            f"{path}.blocking_signal",
        ),
    )


def _parse_gap_metric(value: Any, path: str) -> ClinicalCohortGapMetric:
    data = _record(
        value,
        path,
        {"code", "dimension", "blocking", "present_packages", "targeted_packages"},
    )
    return ClinicalCohortGapMetric(
        code=_parse_enum(ClinicalEvidenceGapCode, data["code"], f"{path}.code"),
        dimension=_parse_enum(
            ClinicalEvidenceDimension,
            data["dimension"],
            f"{path}.dimension",
        ),
        blocking=data["blocking"],
        present_packages=_parse_rate(
            data["present_packages"],
            f"{path}.present_packages",
        ),
        targeted_packages=_parse_rate(
            data["targeted_packages"],
            f"{path}.targeted_packages",
        ),
    )


def _parse_action_metric(value: Any, path: str) -> ClinicalCohortActionMetric:
    data = _record(
        value,
        path,
        {
            "action_id",
            "action_fingerprint",
            "tool_id",
            "operation",
            "purpose",
            "max_cost",
            "selected_packages",
            "total_planned_cost",
        },
    )
    return ClinicalCohortActionMetric(
        action_id=data["action_id"],
        action_fingerprint=data["action_fingerprint"],
        tool_id=data["tool_id"],
        operation=data["operation"],
        purpose=data["purpose"],
        max_cost=data["max_cost"],
        selected_packages=_parse_rate(
            data["selected_packages"],
            f"{path}.selected_packages",
        ),
        total_planned_cost=data["total_planned_cost"],
    )


def _parse_metrics(data: dict[str, Any], path: str) -> dict[str, Any]:
    return {
        "decisions": tuple(
            _parse_decision_metric(item, f"{path}.decisions[{index}]")
            for index, item in enumerate(
                _sequence(data["decisions"], f"{path}.decisions")
            )
        ),
        "dimensions": tuple(
            _parse_dimension_metric(item, f"{path}.dimensions[{index}]")
            for index, item in enumerate(
                _sequence(data["dimensions"], f"{path}.dimensions")
            )
        ),
        "gaps": tuple(
            _parse_gap_metric(item, f"{path}.gaps[{index}]")
            for index, item in enumerate(_sequence(data["gaps"], f"{path}.gaps"))
        ),
        "actions": tuple(
            _parse_action_metric(item, f"{path}.actions[{index}]")
            for index, item in enumerate(
                _sequence(data["actions"], f"{path}.actions")
            )
        ),
    }


def _parse_policy_stratum(
    value: Any,
    path: str,
) -> ClinicalCohortPolicyStratum:
    fields = {
        "policy",
        "package_ids",
        "evidence_unit_ids",
        "decisions",
        "dimensions",
        "gaps",
        "actions",
        "total_planned_cost",
    }
    data = _record(value, path, fields)
    metrics = _parse_metrics(data, path)
    return ClinicalCohortPolicyStratum(
        policy=_parse_policy(data["policy"], f"{path}.policy"),
        package_ids=tuple(_sequence(data["package_ids"], f"{path}.package_ids")),
        evidence_unit_ids=tuple(
            _sequence(data["evidence_unit_ids"], f"{path}.evidence_unit_ids")
        ),
        total_planned_cost=data["total_planned_cost"],
        **metrics,
    )


def _parse_transition(
    value: Any,
    path: str,
) -> ClinicalCohortDecisionTransition:
    data = _record(value, path, {"decision_a", "decision_b", "count"})
    return ClinicalCohortDecisionTransition(
        decision_a=_parse_enum(
            Decision,
            data["decision_a"],
            f"{path}.decision_a",
        ),
        decision_b=_parse_enum(
            Decision,
            data["decision_b"],
            f"{path}.decision_b",
        ),
        count=data["count"],
    )


def _parse_gap_comparison(
    value: Any,
    path: str,
) -> ClinicalCohortGapComparison:
    data = _record(
        value,
        path,
        {"code", "both", "policy_a_only", "policy_b_only", "neither"},
    )
    return ClinicalCohortGapComparison(
        code=_parse_enum(ClinicalEvidenceGapCode, data.pop("code"), f"{path}.code"),
        **data,
    )


def _parse_matched_comparison(
    value: Any,
    path: str,
) -> ClinicalCohortMatchedPolicyComparison:
    fields = {
        "policy_a",
        "policy_b",
        "evidence_unit_ids",
        "decision_transitions",
        "changed_decisions",
        "changed_gap_profiles",
        "changed_action_plans",
        "gap_comparisons",
        "policy_a_total_planned_cost",
        "policy_b_total_planned_cost",
    }
    data = _record(value, path, fields)
    return ClinicalCohortMatchedPolicyComparison(
        policy_a=_parse_policy(data["policy_a"], f"{path}.policy_a"),
        policy_b=_parse_policy(data["policy_b"], f"{path}.policy_b"),
        evidence_unit_ids=tuple(
            _sequence(data["evidence_unit_ids"], f"{path}.evidence_unit_ids")
        ),
        decision_transitions=tuple(
            _parse_transition(item, f"{path}.decision_transitions[{index}]")
            for index, item in enumerate(
                _sequence(
                    data["decision_transitions"],
                    f"{path}.decision_transitions",
                )
            )
        ),
        changed_decisions=_parse_rate(
            data["changed_decisions"],
            f"{path}.changed_decisions",
        ),
        changed_gap_profiles=_parse_rate(
            data["changed_gap_profiles"],
            f"{path}.changed_gap_profiles",
        ),
        changed_action_plans=_parse_rate(
            data["changed_action_plans"],
            f"{path}.changed_action_plans",
        ),
        gap_comparisons=tuple(
            _parse_gap_comparison(item, f"{path}.gap_comparisons[{index}]")
            for index, item in enumerate(
                _sequence(data["gap_comparisons"], f"{path}.gap_comparisons")
            )
        ),
        policy_a_total_planned_cost=data["policy_a_total_planned_cost"],
        policy_b_total_planned_cost=data["policy_b_total_planned_cost"],
    )


def _parse_overlap(
    value: Any,
    path: str,
) -> ClinicalCohortProvenanceOverlap:
    data = _record(
        value,
        path,
        {"kind", "value", "evidence_unit_ids", "program_ids", "package_ids"},
    )
    return ClinicalCohortProvenanceOverlap(
        kind=data["kind"],
        value=data["value"],
        evidence_unit_ids=tuple(
            _sequence(data["evidence_unit_ids"], f"{path}.evidence_unit_ids")
        ),
        program_ids=tuple(_sequence(data["program_ids"], f"{path}.program_ids")),
        package_ids=tuple(_sequence(data["package_ids"], f"{path}.package_ids")),
    )


def clinical_cohort_report_from_dict(value: Any) -> ClinicalCohortReport:
    """Parse and integrity-check one cohort diagnostics report envelope."""

    raw, expected_hash = _integrity_payload(
        value,
        path="clinical_cohort_report_envelope",
        schema_version=CLINICAL_COHORT_REPORT_SCHEMA_VERSION,
        payload_key="report",
    )
    fields = {
        "cohort_id",
        "cohort_specification_sha256",
        "manifest_fingerprint",
        "method_id",
        "analysis_scope",
        "package_validation_scope",
        "earliest_as_of_date",
        "latest_as_of_date",
        "package_count",
        "program_count",
        "evidence_unit_count",
        "policy_count",
        "packages",
        "decisions",
        "dimensions",
        "gaps",
        "actions",
        "policy_strata",
        "matched_policy_comparisons",
        "provenance_overlaps",
        "evidence_units_source_disjoint",
        "evidence_units_trial_disjoint",
        "outcome_labels_included",
        "performance_metrics_included",
        "outcome_calibration_status",
        "limitations",
    }
    data = _record(raw, "report", fields)
    metrics = _parse_metrics(data, "report")
    report = ClinicalCohortReport(
        cohort_id=data["cohort_id"],
        cohort_specification_sha256=data["cohort_specification_sha256"],
        manifest_fingerprint=data["manifest_fingerprint"],
        method_id=data["method_id"],
        analysis_scope=data["analysis_scope"],
        package_validation_scope=data["package_validation_scope"],
        earliest_as_of_date=_parse_date(
            data["earliest_as_of_date"],
            "report.earliest_as_of_date",
        ),
        latest_as_of_date=_parse_date(
            data["latest_as_of_date"],
            "report.latest_as_of_date",
        ),
        package_count=data["package_count"],
        program_count=data["program_count"],
        evidence_unit_count=data["evidence_unit_count"],
        policy_count=data["policy_count"],
        packages=tuple(
            _parse_package_diagnostic(item, f"report.packages[{index}]")
            for index, item in enumerate(
                _sequence(data["packages"], "report.packages")
            )
        ),
        policy_strata=tuple(
            _parse_policy_stratum(item, f"report.policy_strata[{index}]")
            for index, item in enumerate(
                _sequence(data["policy_strata"], "report.policy_strata")
            )
        ),
        matched_policy_comparisons=tuple(
            _parse_matched_comparison(
                item,
                f"report.matched_policy_comparisons[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    data["matched_policy_comparisons"],
                    "report.matched_policy_comparisons",
                )
            )
        ),
        provenance_overlaps=tuple(
            _parse_overlap(item, f"report.provenance_overlaps[{index}]")
            for index, item in enumerate(
                _sequence(data["provenance_overlaps"], "report.provenance_overlaps")
            )
        ),
        evidence_units_source_disjoint=data["evidence_units_source_disjoint"],
        evidence_units_trial_disjoint=data["evidence_units_trial_disjoint"],
        outcome_labels_included=data["outcome_labels_included"],
        performance_metrics_included=data["performance_metrics_included"],
        outcome_calibration_status=data["outcome_calibration_status"],
        limitations=tuple(_sequence(data["limitations"], "report.limitations")),
        **metrics,
    )
    if report.fingerprint != expected_hash:
        raise RecordParseError("parsed cohort report changed canonical identity")
    return report


def clinical_cohort_report_from_json(payload: str) -> ClinicalCohortReport:
    return clinical_cohort_report_from_dict(
        _strict_json(payload, "clinical cohort report")
    )
