"""Stage-specific semantic promotion of tool outcomes into scientific records."""

from __future__ import annotations

import math
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Any

from .execution import EvidenceDraft, ToolOutcome, ToolStatus
from .clinical_synthesis import (
    ClinicalSynthesisError,
    clinical_synthesis_spec_from_dict,
    clinical_synthesis_spec_to_dict,
    compile_benefit_risk_synthesis,
)
from .clinical_endpoint_mapping import (
    ClinicalEndpointMappingError,
    clinical_endpoint_mapping_spec_from_dict,
    clinical_endpoint_mapping_spec_to_dict,
    compile_clinical_endpoint_mapping,
)
from .models import (
    AssayRecord,
    BenefitRiskSynthesisRecord,
    CandidateRecord,
    CandidateStatus,
    ClinicalEndpointMappingRecord,
    ClaimDisposition,
    Decision,
    DiseaseRecord,
    EvidenceRelation,
    InterventionRecord,
    ModelSystemRecord,
    ProgramState,
    ScientificClaim,
    SerializableRecord,
    Stage,
    TargetRecord,
    TrialArmRecord,
    TrialArmRole,
    TrialDesignRecord,
    TrialEndpointRecord,
    TrialPopulationRecord,
    TrialRecord,
    TrialSafetyArmRecord,
    TrialSafetyRecord,
    to_primitive,
    _freeze_mapping,
    _require_date,
    _require_instance,
    _require_probability,
    _require_text,
)


class PromotionStatus(str, Enum):
    PROMOTED = "promoted"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PromotionContext(SerializableRecord):
    observed_at: date
    available_at: date
    subject: str
    object_value: str
    confidence: float
    candidate_id: str | None = None
    candidate_name: str | None = None
    modality: str | None = None
    biological_context: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_date(self.observed_at, "observed_at")
        _require_date(self.available_at, "available_at")
        if self.available_at < self.observed_at:
            raise ValueError("available_at cannot precede observed_at")
        for field_name in ("subject", "object_value"):
            _require_text(getattr(self, field_name), field_name)
        _require_probability(self.confidence, "confidence")
        for field_name in ("candidate_id", "candidate_name", "modality"):
            value = getattr(self, field_name)
            if value is not None:
                _require_text(value, field_name)
        object.__setattr__(
            self,
            "biological_context",
            _freeze_mapping(self.biological_context, "biological_context"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class PromotionResult(SerializableRecord):
    mapper_id: str
    request_id: str
    status: PromotionStatus
    code: str
    message: str
    evidence_drafts: tuple[EvidenceDraft, ...] = ()
    claim_updates: tuple[ScientificClaim, ...] = ()
    disease_updates: tuple[DiseaseRecord, ...] = ()
    target_updates: tuple[TargetRecord, ...] = ()
    candidate_updates: tuple[CandidateRecord, ...] = ()
    assay_updates: tuple[AssayRecord, ...] = ()
    model_system_updates: tuple[ModelSystemRecord, ...] = ()
    intervention_updates: tuple[InterventionRecord, ...] = ()
    trial_updates: tuple[TrialRecord, ...] = ()
    trial_design_updates: tuple[TrialDesignRecord, ...] = ()
    clinical_endpoint_mapping_updates: tuple[ClinicalEndpointMappingRecord, ...] = ()
    benefit_risk_synthesis_updates: tuple[BenefitRiskSynthesisRecord, ...] = ()
    recommended_decision: Decision | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("mapper_id", "request_id", "code", "message"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.status, PromotionStatus, "status")
        if self.recommended_decision is not None:
            _require_instance(
                self.recommended_decision,
                Decision,
                "recommended_decision",
            )
        for field_name, expected in (
            ("evidence_drafts", EvidenceDraft),
            ("claim_updates", ScientificClaim),
            ("disease_updates", DiseaseRecord),
            ("target_updates", TargetRecord),
            ("candidate_updates", CandidateRecord),
            ("assay_updates", AssayRecord),
            ("model_system_updates", ModelSystemRecord),
            ("intervention_updates", InterventionRecord),
            ("trial_updates", TrialRecord),
            ("trial_design_updates", TrialDesignRecord),
            ("clinical_endpoint_mapping_updates", ClinicalEndpointMappingRecord),
            ("benefit_risk_synthesis_updates", BenefitRiskSynthesisRecord),
        ):
            values = tuple(getattr(self, field_name))
            object.__setattr__(self, field_name, values)
            for value in values:
                _require_instance(value, expected, f"{field_name} item")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_drafts)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_drafts must have unique evidence ids")
        if any(item.request_id != self.request_id for item in self.evidence_drafts):
            raise ValueError("evidence drafts must reference the promotion request")
        claim_ids = tuple(item.claim_id for item in self.claim_updates)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_updates must have unique claim ids")
        disease_ids = tuple(item.disease_id for item in self.disease_updates)
        if len(disease_ids) != len(set(disease_ids)):
            raise ValueError("disease_updates must have unique disease ids")
        target_ids = tuple(item.target_id for item in self.target_updates)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("target_updates must have unique target ids")
        candidate_ids = tuple(item.candidate_id for item in self.candidate_updates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_updates must have unique candidate ids")
        assay_ids = tuple(item.assay_id for item in self.assay_updates)
        if len(assay_ids) != len(set(assay_ids)):
            raise ValueError("assay_updates must have unique assay ids")
        model_system_ids = tuple(
            item.model_system_id for item in self.model_system_updates
        )
        if len(model_system_ids) != len(set(model_system_ids)):
            raise ValueError("model_system_updates must have unique model system ids")
        intervention_ids = tuple(
            item.intervention_id for item in self.intervention_updates
        )
        if len(intervention_ids) != len(set(intervention_ids)):
            raise ValueError("intervention_updates must have unique intervention ids")
        trial_ids = tuple(item.trial_id for item in self.trial_updates)
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("trial_updates must have unique trial ids")
        design_ids = tuple(item.design_id for item in self.trial_design_updates)
        if len(design_ids) != len(set(design_ids)):
            raise ValueError("trial_design_updates must have unique design ids")
        synthesis_ids = tuple(
            item.synthesis_id for item in self.benefit_risk_synthesis_updates
        )
        if len(synthesis_ids) != len(set(synthesis_ids)):
            raise ValueError(
                "benefit_risk_synthesis_updates must have unique synthesis ids"
            )
        referenced_ids = {
            evidence_id
            for claim in self.claim_updates
            for evidence_id in (
                *claim.supporting_evidence,
                *claim.contradicting_evidence,
            )
        }
        if not referenced_ids.issubset(evidence_ids):
            raise ValueError("promotion claims may reference only promotion evidence")
        has_artifacts = bool(
            self.evidence_drafts
            or self.claim_updates
            or self.disease_updates
            or self.target_updates
            or self.candidate_updates
            or self.assay_updates
            or self.model_system_updates
            or self.intervention_updates
            or self.trial_updates
            or self.trial_design_updates
            or self.benefit_risk_synthesis_updates
        )
        if self.status is PromotionStatus.PROMOTED and not self.evidence_drafts:
            raise ValueError("promoted results require at least one evidence draft")
        if self.status is not PromotionStatus.PROMOTED and has_artifacts:
            raise ValueError("abstained or rejected results cannot contain artifacts")
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


SemanticMapper = Callable[
    [ProgramState, ToolOutcome, PromotionContext],
    PromotionResult,
]


class SemanticMapperRegistry:
    """Run explicit, operation-specific payload interpreters without silent fallback."""

    def __init__(self) -> None:
        self._registered: dict[tuple[str, str], tuple[str, SemanticMapper]] = {}

    @property
    def mapper_ids(self) -> tuple[str, ...]:
        return tuple(item[0] for item in self._registered.values())

    def register(
        self,
        *,
        tool_id: str,
        operation: str,
        mapper_id: str,
        mapper: SemanticMapper,
    ) -> None:
        for field_name, value in (
            ("tool_id", tool_id),
            ("operation", operation),
            ("mapper_id", mapper_id),
        ):
            _require_text(value, field_name)
        if not callable(mapper):
            raise TypeError("mapper must be callable")
        key = (tool_id, operation)
        if key in self._registered:
            raise ValueError(
                f"semantic mapper already registered: {tool_id}.{operation}"
            )
        self._registered[key] = (mapper_id, mapper)

    def promote(
        self,
        state: ProgramState,
        outcome: ToolOutcome,
        context: PromotionContext,
    ) -> PromotionResult:
        _require_instance(state, ProgramState, "state")
        _require_instance(outcome, ToolOutcome, "outcome")
        _require_instance(context, PromotionContext, "context")
        key = (outcome.request.tool_id, outcome.request.operation)
        registered = self._registered.get(key)
        mapper_id = registered[0] if registered is not None else "unregistered_mapper"
        if (
            outcome.request.program_id != state.program_id
            or outcome.request.expected_state_version != state.version
            or outcome.request.stage is not state.current_stage
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "promotion_context_mismatch",
                "Tool outcome does not match the current program state.",
            )
        if outcome.status is not ToolStatus.SUCCEEDED:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.ABSTAINED,
                "outcome_not_successful",
                "Only successful tool outcomes are eligible for semantic promotion.",
                recommended_decision=Decision.DEFER,
                details={
                    "tool_status": outcome.status.value,
                    "error_code": outcome.error_code,
                },
            )
        if context.available_at > state.as_of_date:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "promotion_evidence_after_cutoff",
                "Promotion context contains evidence unavailable at the program cutoff.",
                details={
                    "available_at": context.available_at.isoformat(),
                    "as_of_date": state.as_of_date.isoformat(),
                },
            )
        if registered is None:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.ABSTAINED,
                "semantic_mapper_missing",
                "No explicit semantic mapper is registered for this tool operation.",
                recommended_decision=Decision.DEFER,
            )
        try:
            result = registered[1](state, outcome, context)
        except Exception as exc:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "semantic_mapper_exception",
                "Semantic mapper failed closed.",
                details={"exception_type": type(exc).__name__},
            )
        if not isinstance(result, PromotionResult):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "semantic_mapper_contract_invalid",
                "Semantic mapper returned an invalid result type.",
                details={"return_type": type(result).__name__},
            )
        failures: list[str] = []
        if result.mapper_id != mapper_id:
            failures.append("mapper_id_mismatch")
        if result.request_id != outcome.request_id:
            failures.append("request_id_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.claim_updates
        ):
            failures.append("claim_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.disease_updates
        ):
            failures.append("disease_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.target_updates
        ):
            failures.append("target_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.candidate_updates
        ):
            failures.append("candidate_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.assay_updates
        ):
            failures.append("assay_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage
            for item in result.model_system_updates
        ):
            failures.append("model_system_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage
            for item in result.intervention_updates
        ):
            failures.append("intervention_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage for item in result.trial_updates
        ):
            failures.append("trial_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage
            for item in result.trial_design_updates
        ):
            failures.append("trial_design_stage_mismatch")
        if any(
            item.stage is not outcome.request.stage
            for item in result.benefit_risk_synthesis_updates
        ):
            failures.append("benefit_risk_synthesis_stage_mismatch")
        if failures:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "semantic_mapper_contract_invalid",
                "Semantic mapper result violates its declared contract.",
                details={"failures": failures},
            )
        return result


def _empty_result(
    mapper_id: str,
    outcome: ToolOutcome,
    status: PromotionStatus,
    code: str,
    message: str,
    *,
    recommended_decision: Decision | None = None,
    details: Mapping[str, Any] | None = None,
) -> PromotionResult:
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=status,
        code=code,
        message=message,
        recommended_decision=recommended_decision,
        details=details or {},
    )


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _probability(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _source_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _non_negative_int(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _source_text_matches(expected: str, observed: object) -> bool:
    if not isinstance(observed, str):
        return False
    expected_tokens = re.findall(r"[a-z0-9]+", expected.casefold())
    observed_tokens = set(re.findall(r"[a-z0-9]+", observed.casefold()))
    return bool(expected_tokens) and all(
        token in observed_tokens for token in expected_tokens
    )


def _evidence_id(outcome: ToolOutcome, suffix: str) -> str:
    return f"{outcome.request_id}:evidence:{suffix}"


def _claim_id(outcome: ToolOutcome, suffix: str) -> str:
    return f"{outcome.request_id}:claim:{suffix}"


def _draft(
    outcome: ToolOutcome,
    context: PromotionContext,
    *,
    evidence_id: str,
    predicate: str,
    object_value: str,
    relation: EvidenceRelation,
    confidence: float,
    direction: str | None = None,
    source_id: str | None = None,
    observed_at: date | None = None,
    available_at: date | None = None,
    biological_context: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceDraft:
    return EvidenceDraft(
        evidence_id=evidence_id,
        request_id=outcome.request_id,
        subject=context.subject,
        predicate=predicate,
        object_value=object_value,
        observed_at=observed_at or context.observed_at,
        available_at=available_at or context.available_at,
        source_id=source_id,
        relation=relation,
        direction=direction,
        biological_context=(
            context.biological_context
            if biological_context is None
            else biological_context
        ),
        confidence=confidence,
        metadata={**dict(context.metadata), **dict(metadata or {})},
    )


@dataclass(frozen=True, slots=True)
class _PinnedPromotionRecord:
    record_id: str
    predicate: str
    subject: str
    object_value: str
    observed_at: date
    available_at: date
    confidence: float
    source_id: str
    source_version: str
    locator: str
    content_hash: str
    biological_context: Mapping[str, Any]
    metadata: Mapping[str, Any]


def _iso_date(value: Any, field_name: str) -> date:
    text = _text(value)
    if text is None:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _parse_pinned_profile(
    outcome: ToolOutcome,
    expected_predicates: tuple[str, ...],
) -> tuple[_PinnedPromotionRecord, ...]:
    payload = outcome.payload
    if payload.get("schema_version") != "adds.pinned-evidence.v1":
        raise ValueError("unsupported pinned evidence schema_version")
    if payload.get("status") != "resolved":
        raise ValueError("pinned evidence profile is not resolved")
    if tuple(payload.get("required_predicates", ())) != expected_predicates:
        raise ValueError("pinned evidence required_predicates do not match the mapper")
    if (
        payload.get("missing_predicates") != ()
        or payload.get("duplicate_predicates") != ()
    ):
        raise ValueError("resolved pinned evidence profile contains gap markers")
    raw_records = payload.get("records")
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes)):
        raise ValueError("pinned evidence records must be a sequence")
    if len(raw_records) != len(expected_predicates):
        raise ValueError("pinned evidence profile has an unexpected record count")

    source_by_id: dict[str, Any] = {}
    for source in outcome.sources:
        if source.source_id in source_by_id:
            raise ValueError("pinned outcome source_id values must be unique")
        source_by_id[source.source_id] = source

    parsed: dict[str, _PinnedPromotionRecord] = {}
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping):
            raise ValueError(f"records[{index}] must be an object")
        record_id = _text(raw.get("record_id"))
        predicate = _text(raw.get("predicate"))
        subject = _text(raw.get("subject"))
        object_value = _text(raw.get("object_value"))
        confidence = _probability(raw.get("confidence"))
        biological_context = raw.get("biological_context")
        metadata = raw.get("metadata")
        source_value = raw.get("source")
        if (
            record_id is None
            or predicate is None
            or subject is None
            or object_value is None
            or confidence is None
            or not isinstance(biological_context, Mapping)
            or not isinstance(metadata, Mapping)
            or not isinstance(source_value, Mapping)
        ):
            raise ValueError(f"records[{index}] violates the pinned record schema")
        if predicate not in expected_predicates or predicate in parsed:
            raise ValueError("pinned evidence predicates must be exact and unique")
        observed_at = _iso_date(raw.get("observed_at"), "observed_at")
        available_at = _iso_date(raw.get("available_at"), "available_at")
        if available_at < observed_at:
            raise ValueError("pinned evidence available_at cannot precede observed_at")

        source_id = _text(source_value.get("source_id"))
        source_version = _text(source_value.get("source_version"))
        locator = _text(source_value.get("locator"))
        content_hash = source_value.get("content_hash")
        if (
            source_id is None
            or source_version is None
            or locator is None
            or "unpinned" in source_version.casefold()
            or not _is_sha256(content_hash)
        ):
            raise ValueError("pinned evidence source identity is incomplete")
        outcome_source = source_by_id.get(source_id)
        if outcome_source is None or (
            outcome_source.source_version != source_version
            or outcome_source.locator != locator
            or outcome_source.content_hash != content_hash
        ):
            raise ValueError("payload source does not match the tool outcome source")
        parsed[predicate] = _PinnedPromotionRecord(
            record_id=record_id,
            predicate=predicate,
            subject=subject,
            object_value=object_value,
            observed_at=observed_at,
            available_at=available_at,
            confidence=confidence,
            source_id=source_id,
            source_version=source_version,
            locator=locator,
            content_hash=content_hash,
            biological_context=dict(biological_context),
            metadata=dict(metadata),
        )
    return tuple(parsed[predicate] for predicate in expected_predicates)


def _profile_query_matches(payload: Mapping[str, Any], **expected: str) -> bool:
    query = payload.get("query")
    return isinstance(query, Mapping) and all(
        isinstance(query.get(key), str)
        and _normalized(query[key]) == _normalized(value)
        for key, value in expected.items()
    )


def _record_context_matches(
    record: _PinnedPromotionRecord,
    **expected: str,
) -> bool:
    return all(
        isinstance(record.biological_context.get(key), str)
        and _normalized(record.biological_context[key]) == _normalized(value)
        for key, value in expected.items()
    )


def _record_metadata_complete(
    record: _PinnedPromotionRecord,
    fields: tuple[str, ...],
) -> bool:
    return all(
        field in record.metadata
        and record.metadata[field] is not None
        and record.metadata[field] != ""
        for field in fields
    )


def _metadata_text_values(
    record: _PinnedPromotionRecord,
    field: str,
) -> tuple[str, ...] | None:
    value = record.metadata.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    items = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if not items or len(items) != len(value):
        return None
    return items


def _typed_effect_metadata_valid(
    record: _PinnedPromotionRecord,
    *,
    functional: bool,
) -> bool:
    relation = _text(record.metadata.get("endpoint_relation"))
    lineages = _metadata_text_values(record, "source_lineage_ids")
    if (
        relation is None
        or relation.casefold() not in {"lt", "le", "eq", "ge", "gt"}
        or _number(record.metadata.get("endpoint_value")) is None
        or _text(record.metadata.get("endpoint_unit")) is None
        or lineages is None
    ):
        return False
    if not functional:
        return _text(record.metadata.get("source_candidate_name")) is not None
    return (
        record.metadata.get("functional_readout") is True
        and _text(record.metadata.get("source_assay_type")) is not None
        and _text(record.metadata.get("source_assay_type_description")) is not None
        and _metadata_text_values(record, "candidate_aliases") is not None
    )


def _pinned_draft(
    outcome: ToolOutcome,
    context: PromotionContext,
    record: _PinnedPromotionRecord,
    *,
    suffix: str,
    direction: str | None = None,
) -> EvidenceDraft:
    return _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, suffix),
        predicate=record.predicate,
        object_value=record.object_value,
        relation=EvidenceRelation.SUPPORTS,
        confidence=min(context.confidence, record.confidence),
        direction=direction,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context={
            **dict(context.biological_context),
            **dict(record.biological_context),
        },
        metadata={
            **dict(record.metadata),
            "pinned_record_id": record.record_id,
            "record_dates_from_manifest": True,
            "promotion_context_dates_used_as_source_dates": False,
        },
    )


def _map_pinned_disease_unmet_need(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "pinned_disease_unmet_need_v1"
    if outcome.request.stage is not Stage.DISEASE_CONTEXT:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_stage_unsupported",
            "Pinned unmet-need promotion is limited to disease context.",
        )
    disease_id = _text(outcome.request.arguments.get("disease_id"))
    if (
        disease_id is None
        or _normalized(disease_id) != _normalized(context.object_value)
        or _normalized(context.subject) != _normalized(state.disease)
        or not _profile_query_matches(outcome.payload, disease_id=disease_id)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_identity_mismatch",
            "Disease request, profile query, and promotion context must match.",
        )
    expected = ("disease_burden_supported", "treatment_gap_supported")
    try:
        burden, treatment_gap = _parse_pinned_profile(outcome, expected)
    except ValueError as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_profile_invalid",
            "Pinned unmet-need profile failed schema or source validation.",
            details={"validation_error": str(exc)},
        )
    records = (burden, treatment_gap)
    if any(
        _normalized(record.subject) != _normalized(context.subject)
        or not _record_context_matches(record, disease_id=disease_id)
        for record in records
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_record_mismatch",
            "Pinned burden and treatment-gap records must match the disease context.",
        )
    if not _record_metadata_complete(
        burden,
        (
            "measure_type",
            "measure_value",
            "measure_unit",
            "population",
            "geography",
            "reference_period",
        ),
    ) or not _record_metadata_complete(
        treatment_gap,
        (
            "treatment_context",
            "gap_summary",
            "population",
            "geography",
            "reference_period",
        ),
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_metadata_incomplete",
            "Pinned unmet-need records lack required typed summary fields.",
        )
    context_pairs = {
        "evidence_context_id": (
            burden.biological_context["evidence_context_id"],
            treatment_gap.biological_context["evidence_context_id"],
        ),
        "population": (
            burden.metadata["population"],
            treatment_gap.metadata["population"],
        ),
        "geography": (
            burden.metadata["geography"],
            treatment_gap.metadata["geography"],
        ),
    }
    mismatched_context_fields = sorted(
        field_name
        for field_name, values in context_pairs.items()
        if _normalized(str(values[0])) != _normalized(str(values[1]))
    )
    if mismatched_context_fields:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_unmet_need_context_mismatch",
            "Disease burden and treatment gap must describe one population and geography.",
            recommended_decision=Decision.DEFER,
            details={"mismatched_fields": mismatched_context_fields},
        )
    if len({record.source_id for record in records}) != len(records) or len(
        {record.content_hash for record in records}
    ) != len(records):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_unmet_need_sources_not_independent",
            "Disease burden and treatment gap require independent source ids and bytes.",
            recommended_decision=Decision.DEFER,
        )
    future = sorted(
        record.record_id for record in records if record.available_at > state.as_of_date
    )
    if future:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_unmet_need_after_cutoff",
            "Pinned unmet-need evidence was unavailable at the program cutoff.",
            details={"record_ids": future, "as_of_date": state.as_of_date.isoformat()},
        )

    drafts = (
        _pinned_draft(outcome, context, burden, suffix="disease-burden"),
        _pinned_draft(outcome, context, treatment_gap, suffix="treatment-gap"),
    )
    claim_confidence = min(item.confidence for item in drafts)
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "unmet-need"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="unmet_need_defined",
        object_value=disease_id,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=tuple(item.evidence_id for item in drafts),
        confidence=claim_confidence,
        biological_context={
            **dict(context.biological_context),
            "disease_id": disease_id,
            "evidence_context_id": burden.biological_context["evidence_context_id"],
            "population": burden.metadata["population"],
            "geography": burden.metadata["geography"],
        },
    )
    previous = state.diseases_by_id.get(disease_id)
    if previous is not None and _normalized(previous.name) != _normalized(
        context.subject
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_disease_identity_rebound",
            "Pinned disease identity conflicts with the existing disease ledger.",
        )
    supporting_evidence = tuple(item.evidence_id for item in drafts)
    if previous is not None:
        supporting_evidence = tuple(
            dict.fromkeys((*previous.supporting_evidence, *supporting_evidence))
        )
    disease_record = DiseaseRecord(
        disease_id=disease_id,
        name=context.subject,
        stage=outcome.request.stage,
        identifiers={
            **(dict(previous.identifiers) if previous is not None else {}),
            "canonical": disease_id,
        },
        supporting_evidence=supporting_evidence,
        attributes={
            **(dict(previous.attributes) if previous is not None else {}),
            "pinned_record_ids": [item.record_id for item in records],
            "independent_source_ids": [item.source_id for item in records],
            "evidence_context_id": burden.biological_context["evidence_context_id"],
            "population": burden.metadata["population"],
            "geography": burden.metadata["geography"],
            "reference_periods": {
                burden.predicate: burden.metadata["reference_period"],
                treatment_gap.predicate: treatment_gap.metadata["reference_period"],
            },
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="pinned_unmet_need_promoted",
        message=(
            "Independent pinned burden and treatment-gap records support the "
            "unmet-need claim."
        ),
        evidence_drafts=drafts,
        claim_updates=(claim,),
        disease_updates=(disease_record,),
        recommended_decision=Decision.ADVANCE,
        details={"independent_source_count": len(records)},
    )


def _map_pinned_candidate_functional_effect(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "pinned_candidate_functional_effect_v1"
    if outcome.request.stage is not Stage.PRECLINICAL_VALIDATION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_stage_unsupported",
            "Pinned functional-effect promotion is limited to preclinical validation.",
        )
    candidate_id = _text(outcome.request.arguments.get("candidate_id"))
    target_id = _text(outcome.request.arguments.get("target_id"))
    disease_id = _text(outcome.request.arguments.get("disease_id"))
    context_disease_id = context.biological_context.get("disease_id")
    candidate = (
        state.candidates_by_id.get(candidate_id) if candidate_id is not None else None
    )
    target_record_id = (
        _text(candidate.attributes.get("target_record_id"))
        if candidate is not None
        else None
    )
    target_record = (
        state.targets_by_id.get(target_record_id)
        if target_record_id is not None
        else None
    )
    disease_record = (
        state.diseases_by_id.get(disease_id) if disease_id is not None else None
    )
    if (
        candidate_id is None
        or target_id is None
        or disease_id is None
        or context.candidate_id is None
        or _normalized(candidate_id) != _normalized(context.candidate_id)
        or _normalized(target_id) != _normalized(context.object_value)
        or not isinstance(context_disease_id, str)
        or _normalized(disease_id) != _normalized(context_disease_id)
        or candidate is None
        or target_record is None
        or disease_record is None
        or _normalized(target_id)
        != _normalized(target_record.identifiers.get("chembl_target", ""))
        or _normalized(disease_id) != _normalized(target_record.disease_id)
        or candidate.attributes.get("target_chembl_id") != target_id
        or candidate.attributes.get("target_symbol") != target_record.symbol
        or candidate.attributes.get("disease_id") != target_record.disease_id
        or _normalized(context.subject)
        not in {_normalized(candidate.candidate_id), _normalized(candidate.name)}
        or not _profile_query_matches(
            outcome.payload,
            candidate_id=candidate_id,
            target_id=target_id,
            disease_id=disease_id,
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_identity_mismatch",
            "Candidate, target, disease, profile query, and program state must match.",
        )
    expected = (
        "candidate_target_functional_activity_supported",
        "disease_model_effect_supported",
    )
    try:
        target_function, disease_effect = _parse_pinned_profile(outcome, expected)
    except ValueError as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_profile_invalid",
            "Pinned functional-effect profile failed schema or source validation.",
            details={"validation_error": str(exc)},
        )
    allowed_subjects = {
        _normalized(candidate.candidate_id),
        _normalized(candidate.name),
    }
    if (
        _normalized(target_function.subject) not in allowed_subjects
        or _normalized(disease_effect.subject) not in allowed_subjects
        or not _record_context_matches(
            target_function,
            candidate_id=candidate_id,
            target_id=target_id,
            target_record_id=target_record.target_id,
            disease_id=disease_id,
            organism=target_record.organism,
        )
        or not _record_context_matches(
            disease_effect,
            candidate_id=candidate_id,
            disease_id=disease_id,
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_record_mismatch",
            "Pinned functional records must match the existing candidate and context.",
        )
    if (
        not _record_metadata_complete(
            target_function,
            (
                "assay_name",
                "assay_type",
                "source_assay_type",
                "source_assay_type_description",
                "functional_readout",
                "endpoint",
                "endpoint_relation",
                "endpoint_value",
                "endpoint_unit",
                "effect_direction",
                "candidate_aliases",
                "source_lineage_ids",
            ),
        )
        or _normalized(str(target_function.metadata["assay_type"])) != "functional"
        or not _typed_effect_metadata_valid(target_function, functional=True)
        or not _record_metadata_complete(
            disease_effect,
            (
                "model_system",
                "model_type",
                "endpoint",
                "endpoint_relation",
                "endpoint_value",
                "endpoint_unit",
                "effect_direction",
                "disease_relevance",
                "source_candidate_name",
                "source_lineage_ids",
            ),
        )
        or not _typed_effect_metadata_valid(disease_effect, functional=False)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_metadata_incomplete",
            "Pinned functional records lack required assay or disease-model fields.",
        )
    candidate_aliases = {
        _normalized(value)
        for value in _metadata_text_values(target_function, "candidate_aliases") or ()
    }
    source_candidate_name = _text(disease_effect.metadata.get("source_candidate_name"))
    if (
        not candidate_aliases.intersection(allowed_subjects)
        or source_candidate_name is None
        or _normalized(source_candidate_name) not in candidate_aliases
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_functional_effect_candidate_alias_mismatch",
            "Disease-model candidate naming must resolve to the functional source aliases.",
            recommended_decision=Decision.DEFER,
            details={"source_candidate_name": source_candidate_name},
        )
    assay_id = _text(target_function.biological_context.get("assay_id"))
    assay_name = _text(target_function.metadata.get("assay_name"))
    assay_type = _text(target_function.metadata.get("assay_type"))
    model_system_id = _text(disease_effect.biological_context.get("model_system_id"))
    model_system_name = _text(disease_effect.metadata.get("model_system"))
    model_type = _text(disease_effect.metadata.get("model_type"))
    model_organism = _text(disease_effect.biological_context.get("organism"))
    if (
        assay_id is None
        or assay_name is None
        or assay_type is None
        or model_system_id is None
        or model_system_name is None
        or model_type is None
        or model_organism is None
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_experimental_identity_incomplete",
            "Pinned records lack canonical assay or model-system identity.",
        )
    previous_assay = state.assays_by_id.get(assay_id)
    if previous_assay is not None and (
        _normalized(previous_assay.name) != _normalized(assay_name)
        or _normalized(previous_assay.assay_type) != _normalized(assay_type)
        or previous_assay.target_id != target_record.target_id
        or previous_assay.disease_id != disease_id
        or _normalized(previous_assay.organism) != _normalized(target_record.organism)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_assay_identity_rebound",
            "Pinned assay identity conflicts with the existing assay ledger.",
        )
    previous_model = state.model_systems_by_id.get(model_system_id)
    if previous_model is not None and (
        _normalized(previous_model.name) != _normalized(model_system_name)
        or _normalized(previous_model.model_type) != _normalized(model_type)
        or previous_model.disease_id != disease_id
        or _normalized(previous_model.organism) != _normalized(model_organism)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_model_system_identity_rebound",
            "Pinned model-system identity conflicts with the existing ledger.",
        )
    records = (target_function, disease_effect)
    target_lineages = {
        _normalized(value)
        for value in _metadata_text_values(target_function, "source_lineage_ids") or ()
    }
    model_lineages = {
        _normalized(value)
        for value in _metadata_text_values(disease_effect, "source_lineage_ids") or ()
    }
    overlapping_lineages = sorted(target_lineages.intersection(model_lineages))
    if overlapping_lineages:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_functional_effect_lineage_not_independent",
            "Target activity and disease-model effect share an upstream source lineage.",
            recommended_decision=Decision.DEFER,
            details={"overlapping_source_lineage_ids": overlapping_lineages},
        )
    if len({record.source_id for record in records}) != len(records) or len(
        {record.content_hash for record in records}
    ) != len(records):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_functional_effect_sources_not_independent",
            "Target activity and disease-model effect require independent source ids and bytes.",
            recommended_decision=Decision.DEFER,
        )
    future = sorted(
        record.record_id for record in records if record.available_at > state.as_of_date
    )
    if future:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_functional_effect_after_cutoff",
            "Pinned functional evidence was unavailable at the program cutoff.",
            details={"record_ids": future, "as_of_date": state.as_of_date.isoformat()},
        )

    drafts = (
        _pinned_draft(
            outcome,
            context,
            target_function,
            suffix="candidate-target-function",
            direction=str(target_function.metadata["effect_direction"]),
        ),
        _pinned_draft(
            outcome,
            context,
            disease_effect,
            suffix="disease-model-effect",
            direction=str(disease_effect.metadata["effect_direction"]),
        ),
    )
    claim_confidence = min(item.confidence for item in drafts)
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "functional-effect"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="functional_effect_supported",
        object_value=target_id,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=tuple(item.evidence_id for item in drafts),
        confidence=claim_confidence,
        biological_context={
            **dict(context.biological_context),
            "candidate_id": candidate_id,
            "target_id": target_id,
            "disease_id": disease_id,
        },
    )
    assay_support = (drafts[0].evidence_id,)
    if previous_assay is not None:
        assay_support = tuple(
            dict.fromkeys((*previous_assay.supporting_evidence, *assay_support))
        )
    assay_record = AssayRecord(
        assay_id=assay_id,
        name=assay_name,
        assay_type=assay_type,
        target_id=target_record.target_id,
        disease_id=disease_id,
        organism=target_record.organism,
        stage=outcome.request.stage,
        identifiers={
            **(dict(previous_assay.identifiers) if previous_assay is not None else {}),
            "canonical": assay_id,
        },
        supporting_evidence=assay_support,
        attributes={
            **(dict(previous_assay.attributes) if previous_assay is not None else {}),
            "pinned_record_id": target_function.record_id,
            "source_id": target_function.source_id,
            "endpoint": target_function.metadata["endpoint"],
            "endpoint_relation": target_function.metadata["endpoint_relation"],
            "endpoint_value": target_function.metadata["endpoint_value"],
            "endpoint_unit": target_function.metadata["endpoint_unit"],
            "effect_direction": target_function.metadata["effect_direction"],
            "source_lineage_ids": target_function.metadata["source_lineage_ids"],
            "target_chembl_id": target_id,
        },
    )
    model_support = (drafts[1].evidence_id,)
    if previous_model is not None:
        model_support = tuple(
            dict.fromkeys((*previous_model.supporting_evidence, *model_support))
        )
    model_system_record = ModelSystemRecord(
        model_system_id=model_system_id,
        name=model_system_name,
        model_type=model_type,
        disease_id=disease_id,
        organism=model_organism,
        stage=outcome.request.stage,
        identifiers={
            **(dict(previous_model.identifiers) if previous_model is not None else {}),
            "canonical": model_system_id,
        },
        supporting_evidence=model_support,
        attributes={
            **(dict(previous_model.attributes) if previous_model is not None else {}),
            "pinned_record_id": disease_effect.record_id,
            "source_id": disease_effect.source_id,
            "endpoint": disease_effect.metadata["endpoint"],
            "endpoint_relation": disease_effect.metadata["endpoint_relation"],
            "endpoint_value": disease_effect.metadata["endpoint_value"],
            "endpoint_unit": disease_effect.metadata["endpoint_unit"],
            "effect_direction": disease_effect.metadata["effect_direction"],
            "disease_relevance": disease_effect.metadata["disease_relevance"],
            "source_candidate_name": disease_effect.metadata["source_candidate_name"],
            "source_lineage_ids": disease_effect.metadata["source_lineage_ids"],
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="pinned_functional_effect_promoted",
        message=(
            "Independent pinned target-functional and disease-model records support "
            "the candidate functional-effect claim."
        ),
        evidence_drafts=drafts,
        claim_updates=(claim,),
        assay_updates=(assay_record,),
        model_system_updates=(model_system_record,),
        recommended_decision=Decision.ADVANCE,
        details={
            "independent_source_count": len(records),
            "independent_lineage_count": len(target_lineages | model_lineages),
        },
    )


def _map_opentargets_disease(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "opentargets_disease_context_v1"
    if outcome.request.stage is not Stage.DISEASE_CONTEXT:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "opentargets_disease_stage_unsupported",
            "Open Targets disease profiles are limited to disease-context review.",
        )
    payload = outcome.payload
    disease_efo = _text(payload.get("disease_efo"))
    disease = _text(payload.get("disease"))
    requested_efo = _text(outcome.request.arguments.get("disease_efo"))
    if payload.get("resolved") is not True or disease_efo is None or disease is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "opentargets_disease_unresolved",
            "No resolved Open Targets disease profile can be promoted.",
            recommended_decision=Decision.DEFER,
        )
    if requested_efo is not None and _normalized(requested_efo) != _normalized(
        disease_efo
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "opentargets_disease_request_mismatch",
            "Resolved disease id does not match the requested Open Targets id.",
        )
    if _normalized(context.object_value) != _normalized(disease_efo):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "opentargets_disease_id_mismatch",
            "Resolved disease id does not match the promotion context.",
        )
    if _normalized(context.subject) != _normalized(disease) or _normalized(
        state.disease
    ) != _normalized(disease):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "opentargets_disease_name_mismatch",
            "Resolved disease name does not match the program and promotion context.",
        )
    loaded_targets = _non_negative_int(payload.get("loaded_targets"))
    total_targets_raw = payload.get("total_associated_targets")
    total_targets = (
        None if total_targets_raw is None else _non_negative_int(total_targets_raw)
    )
    page_complete = payload.get("page_complete")
    if (
        loaded_targets is None
        or (total_targets_raw is not None and total_targets is None)
        or not isinstance(page_complete, bool)
        or (total_targets is not None and loaded_targets > total_targets)
        or (page_complete and total_targets is None)
        or (
            page_complete
            and total_targets is not None
            and loaded_targets < total_targets
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "opentargets_disease_payload_invalid",
            "Open Targets disease profile metadata violates the declared schema.",
        )
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "disease-profile"),
        predicate="disease_context_resolved",
        object_value=disease_efo,
        relation=EvidenceRelation.CONTEXTUALIZES,
        confidence=context.confidence,
        metadata={
            "resolved_disease_name": disease,
            "loaded_targets": loaded_targets,
            "total_associated_targets": total_targets,
            "page_complete": page_complete,
            "does_not_establish_unmet_need": True,
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="opentargets_disease_contextualized",
        message=(
            "Disease identity was contextualized without inferring burden, treatment "
            "gap, or unmet need."
        ),
        evidence_drafts=(evidence,),
        recommended_decision=Decision.DEFER,
        details={"does_not_establish_unmet_need": True},
    )


def _map_opentargets(
    minimum_score: float,
) -> SemanticMapper:
    def mapper(
        state: ProgramState,
        outcome: ToolOutcome,
        context: PromotionContext,
    ) -> PromotionResult:
        mapper_id = "opentargets_target_disease_v1"
        if outcome.request.stage is not Stage.TARGET_NOMINATION:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "opentargets_stage_unsupported",
                "Open Targets association promotion is limited to target nomination.",
            )
        payload = outcome.payload
        target = _text(payload.get("target"))
        target_id = _text(payload.get("target_id"))
        disease = _text(payload.get("disease"))
        disease_id = _text(payload.get("disease_efo"))
        organism = _text(payload.get("organism"))
        requested_target = _text(outcome.request.arguments.get("symbol"))
        requested_disease_id = _text(outcome.request.arguments.get("disease_efo"))
        disease_record = (
            state.diseases_by_id.get(disease_id) if disease_id is not None else None
        )
        if (
            target is None
            or disease_id is None
            or requested_target is None
            or requested_disease_id is None
            or (
                _normalized(target) != _normalized(requested_target)
                or _normalized(context.subject) != _normalized(requested_target)
            )
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "opentargets_target_mismatch",
                "Open Targets payload target does not match the explicit request context.",
            )
        if (
            disease is None
            or _normalized(disease) != _normalized(context.object_value)
            or _normalized(disease) != _normalized(state.disease)
            or _normalized(disease_id) != _normalized(requested_disease_id)
            or disease_record is None
            or _normalized(disease_record.name) != _normalized(state.disease)
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "opentargets_disease_mismatch",
                "Open Targets payload disease does not match the promotion context.",
            )
        if payload.get("found") is not True:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.ABSTAINED,
                "opentargets_association_unresolved",
                "No resolved target-disease association can be promoted.",
                recommended_decision=Decision.DEFER,
            )
        score = _probability(payload.get("score"))
        if (
            score is None
            or target_id is None
            or not target_id.upper().startswith("ENSG")
            or organism is None
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "opentargets_target_identity_invalid",
                "Resolved association lacks a valid Ensembl target identity or organism.",
            )
        confidence = min(context.confidence, score)
        if score < minimum_score:
            evidence = _draft(
                outcome,
                context,
                evidence_id=_evidence_id(outcome, "association-score"),
                predicate="target_disease_association_score",
                object_value=context.object_value,
                relation=EvidenceRelation.CONTEXTUALIZES,
                confidence=confidence,
                metadata={
                    "association_score": score,
                    "promotion_threshold": minimum_score,
                },
            )
            return PromotionResult(
                mapper_id=mapper_id,
                request_id=outcome.request_id,
                status=PromotionStatus.PROMOTED,
                code="opentargets_score_below_promotion_threshold",
                message="Association score was preserved as contextual evidence only.",
                evidence_drafts=(evidence,),
                recommended_decision=Decision.DEFER,
                details={"score": score, "minimum_score": minimum_score},
            )
        identity_evidence = _draft(
            outcome,
            context,
            evidence_id=_evidence_id(outcome, "target-identity"),
            predicate="target_identity_resolved",
            object_value=target_id,
            relation=EvidenceRelation.SUPPORTS,
            confidence=confidence,
            metadata={
                "ensembl_gene": target_id,
                "gene_symbol": target,
                "organism": organism,
                "disease_id": disease_id,
            },
        )
        association_evidence = _draft(
            outcome,
            context,
            evidence_id=_evidence_id(outcome, "target-disease"),
            predicate="target_disease_supported",
            object_value=context.object_value,
            relation=EvidenceRelation.SUPPORTS,
            confidence=confidence,
            metadata={
                "association_score": score,
                "promotion_threshold": minimum_score,
                "rank": payload.get("rank"),
                "datatypes": payload.get("datatypes", {}),
                "ensembl_gene": target_id,
                "gene_symbol": target,
                "disease_id": disease_id,
                "organism": organism,
            },
        )
        evidence = (identity_evidence, association_evidence)
        claim = ScientificClaim(
            claim_id=_claim_id(outcome, "target-disease"),
            stage=outcome.request.stage,
            subject=context.subject,
            predicate="target_disease_supported",
            object_value=context.object_value,
            disposition=ClaimDisposition.SUPPORTED,
            supporting_evidence=tuple(item.evidence_id for item in evidence),
            confidence=confidence,
            biological_context={
                **dict(context.biological_context),
                "target_record_id": target_id,
                "disease_id": disease_id,
                "organism": organism,
            },
        )
        previous = state.targets_by_id.get(target_id)
        if previous is not None and (
            _normalized(previous.symbol) != _normalized(target)
            or _normalized(previous.disease_id) != _normalized(disease_id)
            or _normalized(previous.organism) != _normalized(organism)
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "opentargets_target_identity_rebound",
                "Resolved Open Targets identity conflicts with the existing target record.",
            )
        identifiers = dict(previous.identifiers) if previous is not None else {}
        identifiers.update({"ensembl_gene": target_id, "gene_symbol": target})
        supporting_evidence = (
            (
                *previous.supporting_evidence,
                *tuple(item.evidence_id for item in evidence),
            )
            if previous is not None
            else tuple(item.evidence_id for item in evidence)
        )
        attributes = dict(previous.attributes) if previous is not None else {}
        attributes["opentargets_association"] = {
            "score": score,
            "rank": payload.get("rank"),
            "datatypes": payload.get("datatypes", {}),
        }
        target_record = TargetRecord(
            target_id=target_id,
            symbol=target,
            disease_id=disease_id,
            organism=organism,
            stage=outcome.request.stage,
            identifiers=identifiers,
            supporting_evidence=tuple(dict.fromkeys(supporting_evidence)),
            attributes=attributes,
        )
        return PromotionResult(
            mapper_id=mapper_id,
            request_id=outcome.request_id,
            status=PromotionStatus.PROMOTED,
            code="opentargets_association_promoted",
            message=(
                "Resolved Ensembl target identity and disease association passed the "
                "explicit promotion threshold."
            ),
            evidence_drafts=evidence,
            claim_updates=(claim,),
            target_updates=(target_record,),
            recommended_decision=Decision.ADVANCE,
            details={"score": score, "minimum_score": minimum_score},
        )

    return mapper


def _map_chembl_modality(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    del state
    mapper_id = "chembl_modality_mechanism_v1"
    if outcome.request.stage is not Stage.MODALITY_SELECTION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_modality_stage_unsupported",
            "ChEMBL modality-mechanism promotion is limited to modality selection.",
        )
    molecule = outcome.payload.get("molecule")
    items = outcome.payload.get("items")
    if (
        not isinstance(molecule, Mapping)
        or not isinstance(items, Sequence)
        or isinstance(items, (str, bytes))
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_modality_payload_invalid",
            "ChEMBL modality payload must contain a molecule and mechanism sequence.",
        )
    chembl_id = _text(molecule.get("chembl_id"))
    molecule_type = _text(molecule.get("type"))
    requested_id = _text(outcome.request.arguments.get("chembl_id"))
    if (
        molecule.get("found") is not True
        or chembl_id is None
        or requested_id is None
        or context.candidate_id is None
        or _normalized(chembl_id) != _normalized(requested_id)
        or _normalized(chembl_id) != _normalized(context.candidate_id)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_modality_candidate_mismatch",
            "Request, payload, and promotion context must identify the same molecule.",
        )
    if (
        molecule_type is None
        or context.modality is None
        or _normalized(molecule_type) != _normalized(context.modality)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_modality_type_mismatch",
            "Resolved ChEMBL molecule type does not match the declared modality.",
        )

    matched_rows: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "chembl_modality_payload_invalid",
                "Every ChEMBL mechanism row must be a mapping.",
            )
        target = _text(item.get("target"))
        moa = _text(item.get("moa"))
        action = _text(item.get("action"))
        if (
            target is not None
            and _normalized(target) == _normalized(context.object_value)
            and moa is not None
            and action is not None
        ):
            matched_rows.append((moa, action))
    if not matched_rows:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "chembl_target_mechanism_unresolved",
            "No complete mechanism row matched the declared target.",
            recommended_decision=Decision.DEFER,
        )

    mechanism, action = matched_rows[0]
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "modality-mechanism"),
        predicate="modality_matches_mechanism",
        object_value=context.object_value,
        relation=EvidenceRelation.SUPPORTS,
        confidence=context.confidence,
        metadata={
            "chembl_id": chembl_id,
            "molecule_type": molecule_type,
            "mechanism_of_action": mechanism,
            "action_type": action,
            "matching_mechanism_rows": len(matched_rows),
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "modality-mechanism"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="modality_matches_mechanism",
        object_value=context.object_value,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(evidence.evidence_id,),
        confidence=context.confidence,
        biological_context=context.biological_context,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="chembl_modality_mechanism_promoted",
        message="Matched ChEMBL molecule type and target mechanism support the modality.",
        evidence_drafts=(evidence,),
        claim_updates=(claim,),
        recommended_decision=Decision.ADVANCE,
        details={"matching_mechanism_rows": len(matched_rows)},
    )


def _map_chembl_target_modality(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "chembl_target_modality_continuity_v1"
    if outcome.request.stage is not Stage.MODALITY_SELECTION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_modality_stage_unsupported",
            "ChEMBL target continuity is limited to modality selection.",
        )
    molecule = outcome.payload.get("molecule")
    target_profile = outcome.payload.get("target")
    items = outcome.payload.get("items")
    if (
        not isinstance(molecule, Mapping)
        or not isinstance(target_profile, Mapping)
        or not isinstance(items, Sequence)
        or isinstance(items, (str, bytes))
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_modality_payload_invalid",
            "ChEMBL continuity payload requires molecule, target, and mechanism records.",
        )

    requested_molecule = _text(outcome.request.arguments.get("chembl_id"))
    requested_target = _text(outcome.request.arguments.get("target_id"))
    target_record_id = _text(outcome.request.arguments.get("target_record_id"))
    molecule_id = _text(molecule.get("chembl_id"))
    molecule_type = _text(molecule.get("type"))
    resolved_target = _text(target_profile.get("target_id"))
    target_type = _text(target_profile.get("target_type"))
    organism = _text(target_profile.get("organism"))
    preferred_name = _text(target_profile.get("preferred_name"))
    target_record = (
        state.targets_by_id.get(target_record_id)
        if target_record_id is not None
        else None
    )
    if (
        molecule.get("found") is not True
        or target_profile.get("found") is not True
        or requested_molecule is None
        or requested_target is None
        or target_record_id is None
        or molecule_id is None
        or resolved_target is None
        or target_record is None
        or context.candidate_id is None
        or context.modality is None
        or _normalized(molecule_id) != _normalized(requested_molecule)
        or _normalized(molecule_id) != _normalized(context.candidate_id)
        or _normalized(resolved_target) != _normalized(requested_target)
        or _normalized(resolved_target) != _normalized(context.object_value)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_modality_identity_mismatch",
            "Molecule, ChEMBL target, canonical target record, and context must match.",
        )
    if molecule_type is None or _normalized(molecule_type) != _normalized(
        context.modality
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_modality_type_mismatch",
            "Resolved ChEMBL molecule type does not match the declared modality.",
        )
    if (
        target_type is None
        or _normalized(target_type) != "single protein"
        or organism is None
        or _normalized(organism) != _normalized(target_record.organism)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_profile_scope_mismatch",
            "Target continuity requires a same-organism ChEMBL single-protein target.",
        )

    raw_symbols = target_profile.get("gene_symbols")
    raw_accessions = target_profile.get("accessions")
    if (
        not isinstance(raw_symbols, Sequence)
        or isinstance(raw_symbols, (str, bytes))
        or not isinstance(raw_accessions, Sequence)
        or isinstance(raw_accessions, (str, bytes))
        or any(_text(item) is None for item in (*raw_symbols, *raw_accessions))
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_profile_invalid",
            "ChEMBL target symbols and accessions must be explicit string sequences.",
        )
    gene_symbols = tuple(str(item).strip() for item in raw_symbols)
    accessions = tuple(str(item).strip() for item in raw_accessions)
    if _normalized(target_record.symbol) not in {
        _normalized(item) for item in gene_symbols
    }:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_symbol_mismatch",
            "ChEMBL target components do not contain the canonical target symbol.",
        )

    matched_rows: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "chembl_target_modality_payload_invalid",
                "Every ChEMBL mechanism row must be a mapping.",
            )
        row_target = _text(item.get("target"))
        moa = _text(item.get("moa"))
        action = _text(item.get("action"))
        if (
            row_target is not None
            and _normalized(row_target) == _normalized(resolved_target)
            and moa is not None
            and action is not None
        ):
            matched_rows.append((moa, action))
    if not matched_rows:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "chembl_target_mechanism_unresolved",
            "No complete mechanism row matched the identity-verified ChEMBL target.",
            recommended_decision=Decision.DEFER,
        )

    existing_chembl_target = target_record.identifiers.get("chembl_target")
    if existing_chembl_target is not None and _normalized(
        existing_chembl_target
    ) != _normalized(resolved_target):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_target_namespace_rebound",
            "The canonical target record is already bound to another ChEMBL target.",
        )
    existing_uniprot = target_record.identifiers.get("uniprot")
    if existing_uniprot is not None and _normalized(existing_uniprot) not in {
        _normalized(item) for item in accessions
    }:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_uniprot_namespace_rebound",
            "ChEMBL target accessions conflict with the accepted UniProt binding.",
        )

    mechanism, action = matched_rows[0]
    identity_evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "target-continuity"),
        predicate="target_identity_continuous",
        object_value=resolved_target,
        relation=EvidenceRelation.SUPPORTS,
        confidence=context.confidence,
        metadata={
            "target_record_id": target_record.target_id,
            "ensembl_gene": target_record.identifiers.get("ensembl_gene"),
            "gene_symbol": target_record.symbol,
            "chembl_target": resolved_target,
            "target_type": target_type,
            "organism": organism,
            "preferred_name": preferred_name,
            "accessions": accessions,
        },
    )
    modality_evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "modality-mechanism"),
        predicate="modality_matches_mechanism",
        object_value=resolved_target,
        relation=EvidenceRelation.SUPPORTS,
        confidence=context.confidence,
        metadata={
            "target_record_id": target_record.target_id,
            "chembl_id": molecule_id,
            "molecule_type": molecule_type,
            "mechanism_of_action": mechanism,
            "action_type": action,
            "matching_mechanism_rows": len(matched_rows),
        },
    )
    evidence = (identity_evidence, modality_evidence)
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "modality-mechanism"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="modality_matches_mechanism",
        object_value=resolved_target,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=tuple(item.evidence_id for item in evidence),
        confidence=context.confidence,
        biological_context={
            **dict(context.biological_context),
            "target_record_id": target_record.target_id,
            "target_symbol": target_record.symbol,
            "disease_id": target_record.disease_id,
        },
    )
    identifiers = dict(target_record.identifiers)
    identifiers["chembl_target"] = resolved_target
    if len(set(accessions)) == 1:
        identifiers["uniprot"] = accessions[0]
    attributes = dict(target_record.attributes)
    attributes["chembl_target_profile"] = {
        "preferred_name": preferred_name,
        "target_type": target_type,
        "organism": organism,
        "gene_symbols": gene_symbols,
        "accessions": accessions,
    }
    updated_target = TargetRecord(
        target_id=target_record.target_id,
        symbol=target_record.symbol,
        disease_id=target_record.disease_id,
        organism=target_record.organism,
        stage=outcome.request.stage,
        identifiers=identifiers,
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *target_record.supporting_evidence,
                    *tuple(item.evidence_id for item in evidence),
                )
            )
        ),
        attributes=attributes,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="chembl_target_modality_continuity_promoted",
        message=(
            "ChEMBL target identity, molecule modality, and mechanism preserve the "
            "canonical target lineage."
        ),
        evidence_drafts=evidence,
        claim_updates=(claim,),
        target_updates=(updated_target,),
        recommended_decision=Decision.ADVANCE,
        details={
            "target_record_id": target_record.target_id,
            "matching_mechanism_rows": len(matched_rows),
        },
    )


def _map_chembl_molecule(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "chembl_candidate_identity_v1"
    if outcome.request.stage is not Stage.CANDIDATE_GENERATION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_candidate_stage_unsupported",
            "ChEMBL molecule identity promotion is limited to candidate generation.",
        )
    payload = outcome.payload
    chembl_id = _text(payload.get("chembl_id"))
    name = _text(payload.get("name")) or context.candidate_name
    if payload.get("found") is not True or chembl_id is None or name is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "chembl_candidate_unresolved",
            "ChEMBL did not return a resolved candidate identity.",
            recommended_decision=Decision.DEFER,
        )
    if context.candidate_id is None or context.modality is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_context_incomplete",
            "Candidate id and modality are required for identity promotion.",
        )
    if _normalized(context.candidate_id) != _normalized(chembl_id):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_candidate_id_mismatch",
            "Resolved ChEMBL id does not match the declared candidate id.",
        )
    requested_id = _text(outcome.request.arguments.get("chembl_id"))
    if requested_id is not None and _normalized(requested_id) != _normalized(chembl_id):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_request_id_mismatch",
            "Resolved ChEMBL id does not match the requested identifier.",
        )
    matching_targets = tuple(
        item
        for item in state.targets
        if _normalized(item.identifiers.get("chembl_target", ""))
        == _normalized(context.object_value)
    )
    if len(matching_targets) != 1:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_target_identity_unresolved",
            "Candidate identity requires exactly one continuity-verified target record.",
            details={"matching_target_count": len(matching_targets)},
        )
    target_record = matching_targets[0]
    previous = state.candidates_by_id.get(context.candidate_id)
    expected_link = {
        "target_record_id": target_record.target_id,
        "target_chembl_id": target_record.identifiers["chembl_target"],
        "target_symbol": target_record.symbol,
        "disease_id": target_record.disease_id,
    }
    if previous is not None and any(
        key in previous.attributes and previous.attributes[key] != value
        for key, value in expected_link.items()
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_target_link_rebound",
            "Existing candidate linkage conflicts with the resolved target record.",
        )
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "candidate-identity"),
        predicate="candidate_identity_resolved",
        object_value=chembl_id,
        relation=EvidenceRelation.SUPPORTS,
        confidence=context.confidence,
        metadata={
            "resolved_name": name,
            "molecule_type": payload.get("type"),
            "max_phase": payload.get("max_phase"),
            "first_approval": payload.get("first_approval"),
            **expected_link,
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "candidate-identity"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="candidate_identity_resolved",
        object_value=chembl_id,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(evidence.evidence_id,),
        confidence=context.confidence,
        biological_context={**dict(context.biological_context), **expected_link},
    )
    attributes = dict(previous.attributes) if previous is not None else {}
    attributes.update(
        {
            "chembl_id": chembl_id,
            "molecule_type": payload.get("type"),
            "max_phase": payload.get("max_phase"),
            "first_approval": payload.get("first_approval"),
            **expected_link,
        }
    )
    candidate = CandidateRecord(
        candidate_id=context.candidate_id,
        name=context.candidate_name or name,
        modality=context.modality,
        stage=outcome.request.stage,
        status=CandidateStatus.ACTIVE,
        attributes=attributes,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="chembl_candidate_identity_promoted",
        message="ChEMBL molecule identity was promoted with an explicit candidate record.",
        evidence_drafts=(evidence,),
        claim_updates=(claim,),
        candidate_updates=(candidate,),
        recommended_decision=Decision.ADVANCE,
    )


def _map_chembl_activity_context(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "chembl_preclinical_activity_context_v1"
    if outcome.request.stage is not Stage.PRECLINICAL_VALIDATION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_activity_stage_unsupported",
            "ChEMBL activity-count context is limited to preclinical validation.",
        )
    requested_target = _text(outcome.request.arguments.get("target_id"))
    if requested_target is None or _normalized(requested_target) != _normalized(
        context.object_value
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_activity_target_mismatch",
            "Requested ChEMBL target does not match the promotion context.",
        )
    if context.candidate_id is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "preclinical_candidate_context_missing",
            "Preclinical context must identify an existing candidate.",
        )
    candidate = state.candidates_by_id.get(context.candidate_id)
    target_record_id = (
        _text(candidate.attributes.get("target_record_id"))
        if candidate is not None
        else None
    )
    target_record = (
        state.targets_by_id.get(target_record_id)
        if target_record_id is not None
        else None
    )
    if (
        candidate is None
        or target_record is None
        or _normalized(context.subject)
        not in {
            _normalized(candidate.candidate_id),
            _normalized(candidate.name),
        }
        or _normalized(requested_target)
        != _normalized(target_record.identifiers.get("chembl_target", ""))
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "preclinical_candidate_context_mismatch",
            "Preclinical activity context does not match an existing candidate.",
        )
    count = _non_negative_int(outcome.payload.get("count"))
    if count is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "chembl_activity_count_invalid",
            "ChEMBL activity count must be a non-negative integer.",
        )
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "target-activity-landscape"),
        predicate="target_activity_landscape_available",
        object_value=context.object_value,
        relation=EvidenceRelation.CONTEXTUALIZES,
        confidence=context.confidence,
        metadata={
            "candidate_id": context.candidate_id,
            "activity_count": count,
            "does_not_establish_functional_effect": True,
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="chembl_activity_landscape_contextualized",
        message=(
            "Target activity volume was contextualized without inferring candidate "
            "functional effect."
        ),
        evidence_drafts=(evidence,),
        recommended_decision=Decision.DEFER,
        details={"does_not_establish_functional_effect": True},
    )


def _map_molprops(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "rdkit_developability_v1"
    if outcome.request.stage is not Stage.LEAD_OPTIMIZATION:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "molprops_stage_unsupported",
            "RDKit developability promotion is limited to lead optimization.",
        )
    if context.candidate_id is None or context.modality is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_context_incomplete",
            "Candidate id and modality are required for developability promotion.",
        )
    previous = state.candidates_by_id.get(context.candidate_id)
    if previous is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_not_in_state",
            "Lead optimization can update only a candidate already present in state.",
        )
    if _normalized(previous.modality) != _normalized(context.modality):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "candidate_modality_mismatch",
            "Promotion context modality does not match the existing candidate.",
        )
    payload = outcome.payload
    resolved_smiles = _text(payload.get("smiles"))
    verdict = _text(payload.get("verdict"))
    qed = _probability(payload.get("qed"))
    molecular_weight = _number(payload.get("molecular_weight"))
    logp = _number(payload.get("logp"))
    hbd = payload.get("hbd")
    hba = payload.get("hba")
    violations = payload.get("lipinski_violations")
    if (
        resolved_smiles is None
        or verdict not in {"drug-like", "borderline", "poor druglikeness"}
        or qed is None
        or molecular_weight is None
        or molecular_weight <= 0
        or logp is None
        or not isinstance(hbd, int)
        or isinstance(hbd, bool)
        or hbd < 0
        or not isinstance(hba, int)
        or isinstance(hba, bool)
        or hba < 0
        or not isinstance(violations, int)
        or isinstance(violations, bool)
        or violations < 0
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "molprops_payload_invalid",
            "RDKit payload is incomplete or outside the declared property schema.",
        )
    numeric_fields = {
        "qed": qed,
        "molecular_weight": molecular_weight,
        "logp": logp,
        "hbd": hbd,
        "hba": hba,
    }
    supportive = verdict in {"drug-like", "borderline"}
    relation = EvidenceRelation.SUPPORTS if supportive else EvidenceRelation.CONTRADICTS
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "developability"),
        predicate="developability_reviewed",
        object_value=verdict,
        relation=relation,
        confidence=context.confidence,
        metadata={
            **numeric_fields,
            "input_spec": outcome.request.arguments.get("spec"),
            "resolved_smiles": resolved_smiles,
            "lipinski_violations": violations,
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "developability"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="developability_reviewed",
        object_value=verdict,
        disposition=(
            ClaimDisposition.SUPPORTED if supportive else ClaimDisposition.REJECTED
        ),
        supporting_evidence=(evidence.evidence_id,) if supportive else (),
        contradicting_evidence=() if supportive else (evidence.evidence_id,),
        confidence=context.confidence,
        biological_context=context.biological_context,
    )
    attributes = dict(previous.attributes)
    attributes["molprops"] = {
        **numeric_fields,
        "input_spec": outcome.request.arguments.get("spec"),
        "resolved_smiles": resolved_smiles,
        "lipinski_violations": violations,
        "verdict": verdict,
    }
    candidate = CandidateRecord(
        candidate_id=context.candidate_id,
        name=context.candidate_name or previous.name,
        modality=context.modality,
        stage=outcome.request.stage,
        status=CandidateStatus.ACTIVE if supportive else CandidateStatus.HELD,
        attributes=attributes,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="molprops_developability_promoted",
        message="RDKit properties were promoted without treating them as binding evidence.",
        evidence_drafts=(evidence,),
        claim_updates=(claim,),
        candidate_updates=(candidate,),
        recommended_decision=Decision.ADVANCE if supportive else Decision.HOLD,
        details={"verdict": verdict},
    )


def _map_pinned_clinical_trial_design(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "pinned_clinical_trial_design_v1"
    if outcome.request.stage is not Stage.CLINICAL_STRATEGY:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_stage_unsupported",
            "Pinned clinical trial design promotion is limited to clinical strategy.",
        )
    candidate_id = _text(outcome.request.arguments.get("candidate_id"))
    disease_id = _text(outcome.request.arguments.get("disease_id"))
    trial_id = _text(outcome.request.arguments.get("trial_id"))
    candidate = (
        state.candidates_by_id.get(candidate_id) if candidate_id is not None else None
    )
    disease = state.diseases_by_id.get(disease_id) if disease_id is not None else None
    candidate_interventions = tuple(
        item
        for item in state.interventions
        if candidate is not None and item.candidate_id == candidate.candidate_id
    )
    if len(candidate_interventions) > 1:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_intervention_ambiguous",
            "More than one clinical intervention claims the accepted candidate.",
        )
    existing_intervention = (
        candidate_interventions[0] if candidate_interventions else None
    )
    intervention_id = (
        existing_intervention.intervention_id
        if existing_intervention is not None
        else candidate_id
    )
    if (
        candidate_id is None
        or disease_id is None
        or trial_id is None
        or re.fullmatch(r"NCT[0-9]{8}", trial_id) is None
        or candidate is None
        or disease is None
        or intervention_id is None
        or candidate.attributes.get("disease_id") != disease_id
        or _normalized(disease.name) != _normalized(state.disease)
        or context.candidate_id != candidate_id
        or context.candidate_name is None
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.subject) != _normalized(candidate.name)
        or _normalized(context.object_value) != _normalized(disease.name)
        or context.biological_context.get("disease_id") != disease_id
        or (
            context.biological_context.get("intervention_id") is not None
            and context.biological_context.get("intervention_id") != intervention_id
        )
        or not _profile_query_matches(
            outcome.payload,
            candidate_id=candidate_id,
            disease_id=disease_id,
            trial_id=trial_id,
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_context_mismatch",
            "Candidate, disease, intervention, trial, and profile query must match.",
        )
    try:
        (record,) = _parse_pinned_profile(
            outcome, ("clinical_trial_design_supported",)
        )
    except ValueError as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_profile_invalid",
            "Pinned clinical trial design profile failed source validation.",
            details={"validation_error": str(exc)},
        )
    design_id = f"{trial_id}:design"
    if (
        not _record_context_matches(
            record,
            candidate_id=candidate_id,
            intervention_id=intervention_id,
            disease_id=disease_id,
            trial_id=trial_id,
            design_id=design_id,
        )
        or _normalized(record.subject) != _normalized(candidate.name)
        or _normalized(record.object_value) != _normalized(disease.name)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_record_mismatch",
            "Pinned clinical design record does not match accepted identities.",
        )
    if record.available_at > state.as_of_date:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_after_cutoff",
            "Pinned clinical design evidence was unavailable at the program cutoff.",
            details={
                "record_id": record.record_id,
                "as_of_date": state.as_of_date.isoformat(),
            },
        )

    metadata = record.metadata
    aliases = _metadata_text_values(record, "candidate_aliases")
    source_interventions = _metadata_text_values(record, "source_interventions")
    source_conditions = _metadata_text_values(record, "source_conditions")
    lineages = _metadata_text_values(record, "source_lineage_ids")
    registry_version = _text(metadata.get("registry_version"))
    arms_raw = metadata.get("arms")
    population_raw = metadata.get("population")
    endpoint_raw = metadata.get("endpoint")
    safety_raw = metadata.get("safety")
    if (
        _normalized(str(metadata.get("provider_id", "")))
        != "clinicaltrials_gov"
        or _normalized(str(metadata.get("registry", ""))) != "clinicaltrials.gov"
        or _normalized(str(metadata.get("study_type", ""))) != "interventional"
        or _normalized(str(metadata.get("overall_status", ""))) != "completed"
        or aliases is None
        or source_interventions is None
        or source_conditions is None
        or lineages != (f"clinicaltrials-gov:{trial_id}",)
        or registry_version is None
        or record.source_version
        != f"clinicaltrials-gov-{trial_id}-version-{registry_version}"
        or record.locator
        != f"https://clinicaltrials.gov/api/v2/studies/{trial_id}"
        or not isinstance(arms_raw, Sequence)
        or isinstance(arms_raw, (str, bytes))
        or len(arms_raw) != 2
        or not isinstance(population_raw, Mapping)
        or not isinstance(endpoint_raw, Mapping)
        or not isinstance(safety_raw, Mapping)
        or _normalized(candidate.name)
        not in {_normalized(item) for item in aliases}
        or not any(
            _source_text_matches(candidate.name, item) for item in source_interventions
        )
        or not any(_source_text_matches(disease.name, item) for item in source_conditions)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_metadata_invalid",
            "Pinned clinical design metadata lacks exact registry identities.",
        )
    try:
        _iso_date(registry_version, "registry_version")
        arm_values = [dict(item) for item in arms_raw if isinstance(item, Mapping)]
        if len(arm_values) != 2:
            raise ValueError("arms must contain two objects")
        roles = {_text(item.get("role")): item for item in arm_values}
        candidate_arm = roles.get("candidate")
        comparator_arm = roles.get("comparator")
        if candidate_arm is None or comparator_arm is None:
            raise ValueError("arms must contain candidate and comparator roles")
        if candidate_arm.get("intervention_id") != intervention_id:
            raise ValueError("candidate arm intervention_id mismatch")
        if comparator_arm.get("intervention_id") is not None:
            raise ValueError("comparator arm cannot claim the candidate intervention")
        for item in arm_values:
            for field_name in (
                "arm_id",
                "source_group_id",
                "label",
                "arm_type",
            ):
                if _text(item.get(field_name)) is None:
                    raise ValueError(f"arm {field_name} is missing")
            names = item.get("intervention_names")
            if not isinstance(names, Sequence) or isinstance(names, (str, bytes)):
                raise ValueError("arm intervention_names must be an array")
            if not names or any(_text(value) is None for value in names):
                raise ValueError("arm intervention_names are incomplete")
            measurement = item.get("measurement")
            if not isinstance(measurement, Mapping):
                raise ValueError("arm measurement is missing")
            if _source_number(measurement.get("value")) is None:
                raise ValueError("arm measurement value is not numeric")
            denominator = measurement.get("denominator")
            if (
                not isinstance(denominator, int)
                or isinstance(denominator, bool)
                or denominator <= 0
            ):
                raise ValueError("arm denominator must be positive")
        if not any(
            _source_text_matches(candidate.name, item)
            for item in candidate_arm["intervention_names"]
        ):
            raise ValueError("candidate arm does not name the accepted candidate")

        population = dict(population_raw)
        endpoint = dict(endpoint_raw)
        analysis_raw = endpoint.get("analysis")
        if not isinstance(analysis_raw, Mapping):
            raise ValueError("endpoint analysis is missing")
        analysis = dict(analysis_raw)
        for value, field_name in (
            (population.get("population_id"), "population_id"),
            (population.get("description"), "population.description"),
            (population.get("enrollment_type"), "population.enrollment_type"),
            (population.get("sex"), "population.sex"),
            (population.get("minimum_age"), "population.minimum_age"),
            (endpoint.get("endpoint_id"), "endpoint_id"),
            (endpoint.get("name"), "endpoint.name"),
            (endpoint.get("outcome_type"), "endpoint.outcome_type"),
            (endpoint.get("time_frame"), "endpoint.time_frame"),
            (endpoint.get("parameter_type"), "endpoint.parameter_type"),
            (endpoint.get("unit"), "endpoint.unit"),
            (endpoint.get("reporting_status"), "endpoint.reporting_status"),
            (endpoint.get("favorable_direction"), "endpoint.favorable_direction"),
        ):
            if _text(value) is None:
                raise ValueError(f"{field_name} is missing")
        enrollment_count = population.get("enrollment_count")
        healthy_volunteers = population.get("healthy_volunteers")
        if (
            not isinstance(enrollment_count, int)
            or isinstance(enrollment_count, bool)
            or enrollment_count <= 0
            or not isinstance(healthy_volunteers, bool)
        ):
            raise ValueError("population typed fields are invalid")
        endpoint_arm_ids = endpoint.get("arm_ids")
        source_group_ids = analysis.get("source_group_ids")
        expected_arm_ids = [item["arm_id"] for item in arm_values]
        expected_group_ids = [item["source_group_id"] for item in arm_values]
        if (
            endpoint.get("population_id") != population.get("population_id")
            or list(endpoint_arm_ids or ()) != expected_arm_ids
            or list(source_group_ids or ()) != expected_group_ids
        ):
            raise ValueError("endpoint arm or population references are inconsistent")
        p_value = _number(analysis.get("p_value"))
        parameter_value = _number(analysis.get("parameter_value"))
        ci_percent = _number(analysis.get("confidence_interval_percent"))
        ci_lower = _number(analysis.get("confidence_interval_lower"))
        ci_upper = _number(analysis.get("confidence_interval_upper"))
        candidate_measurement = _source_number(
            candidate_arm["measurement"].get("value")
        )
        comparator_measurement = _source_number(
            comparator_arm["measurement"].get("value")
        )
        if None in {
            p_value,
            parameter_value,
            ci_percent,
            ci_lower,
            ci_upper,
            candidate_measurement,
            comparator_measurement,
        }:
            raise ValueError("endpoint analysis contains non-numeric values")
        if (
            _normalized(str(metadata.get("effect_direction", ""))) != "benefit"
            or _normalized(str(endpoint["outcome_type"])) != "primary"
            or _normalized(str(endpoint["reporting_status"])) != "posted"
            or _normalized(str(endpoint["favorable_direction"]))
            != "higher_is_better"
            or _normalized(str(analysis.get("parameter_type", "")))
            not in {"hazard ratio", "hazard ratio (hr)"}
            or analysis.get("p_value_relation") not in {"lt", "le"}
            or not 0 < p_value <= 0.05
            or not 0 < parameter_value < 1
            or not 0 < ci_lower <= parameter_value <= ci_upper < 1
            or not 0 < ci_percent <= 100
            or candidate_measurement <= comparator_measurement
        ):
            raise ValueError("posted primary endpoint does not prove bounded benefit")

        safety = dict(safety_raw)
        safety_arms_raw = safety.get("arms")
        if (
            safety.get("safety_id")
            != f"{trial_id}:safety:serious-adverse-events"
            or safety.get("event_category") != "SERIOUS"
            or safety.get("reporting_status") != "POSTED"
            or _text(safety.get("time_frame")) is None
            or (
                safety.get("description") is not None
                and _text(safety.get("description")) is None
            )
            or not isinstance(safety.get("event_term_count"), int)
            or isinstance(safety.get("event_term_count"), bool)
            or safety["event_term_count"] < 0
            or not isinstance(safety_arms_raw, Sequence)
            or isinstance(safety_arms_raw, (str, bytes))
            or len(safety_arms_raw) != 2
        ):
            raise ValueError("posted serious-adverse-event summary is incomplete")
        safety_arm_values = [
            dict(item) for item in safety_arms_raw if isinstance(item, Mapping)
        ]
        if len(safety_arm_values) != 2:
            raise ValueError("safety arms must contain two objects")
        canonical_arms = {item["arm_id"]: item for item in arm_values}
        if [item.get("arm_id") for item in safety_arm_values] != expected_arm_ids:
            raise ValueError("safety arm order does not match the selected design arms")
        safety_roles: set[str] = set()
        safety_group_ids: set[str] = set()
        safety_arm_ids: set[str] = set()
        for item in safety_arm_values:
            canonical_arm = canonical_arms.get(item.get("arm_id"))
            role = _text(item.get("role"))
            source_group_id = _text(item.get("source_group_id"))
            source_group_title = _text(item.get("source_group_title"))
            safety_arm_id = _text(item.get("safety_arm_id"))
            affected = item.get("serious_num_affected")
            at_risk = item.get("serious_num_at_risk")
            if (
                canonical_arm is None
                or role not in {"candidate", "comparator"}
                or canonical_arm.get("role") != role
                or source_group_id is None
                or re.fullmatch(r"EG[0-9]{3,}", source_group_id) is None
                or source_group_title is None
                or safety_arm_id is None
                or safety_arm_id
                != f"{safety['safety_id']}:arm:{source_group_id}"
                or _normalized(str(canonical_arm.get("label", "")))
                != _normalized(source_group_title)
                or not isinstance(affected, int)
                or isinstance(affected, bool)
                or affected < 0
                or not isinstance(at_risk, int)
                or isinstance(at_risk, bool)
                or at_risk <= 0
                or affected > at_risk
            ):
                raise ValueError("safety arm identity or serious-event counts are invalid")
            safety_roles.add(role)
            safety_group_ids.add(source_group_id)
            safety_arm_ids.add(safety_arm_id)
        if (
            safety_roles != {"candidate", "comparator"}
            or len(safety_group_ids) != 2
            or len(safety_arm_ids) != 2
        ):
            raise ValueError("safety arm identities must be unique and role-complete")
    except (TypeError, ValueError) as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "pinned_clinical_design_endpoint_not_supportive",
            "Clinical design was not promoted beyond the bounded benefit contract.",
            recommended_decision=Decision.DEFER,
            details={"validation_error": str(exc)},
        )

    if existing_intervention is not None and (
        existing_intervention.name != candidate.name
        or existing_intervention.candidate_id != candidate_id
        or existing_intervention.disease_id != disease_id
        or _normalized(existing_intervention.modality)
        != _normalized(candidate.modality)
        or existing_intervention.identifiers.get("canonical") != intervention_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_intervention_rebound",
            "Existing intervention identity conflicts with the candidate ledger.",
        )
    existing_trial = state.trials_by_id.get(trial_id)
    if existing_trial is not None and (
        _normalized(existing_trial.registry) != "clinicaltrials.gov"
        or existing_trial.intervention_id != intervention_id
        or existing_trial.disease_id != disease_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_trial_rebound",
            "Existing trial identity conflicts with the accepted intervention.",
        )
    existing_design = state.trial_designs_by_id.get(design_id)
    if existing_design is not None and (
        existing_design.trial_id != trial_id
        or existing_design.intervention_id != intervention_id
        or existing_design.disease_id != disease_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_design_identity_rebound",
            "Existing trial design conflicts with the accepted clinical identity.",
        )

    base_context = {
        **dict(context.biological_context),
        "candidate_id": candidate_id,
        "intervention_id": intervention_id,
        "disease_id": disease_id,
        "trial_id": trial_id,
        "design_id": design_id,
        "registry": "ClinicalTrials.gov",
    }
    confidence = min(context.confidence, record.confidence)
    identity_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, f"trial-identity-{trial_id}"),
        predicate="clinical_trial_identity_resolved",
        object_value=trial_id,
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context=base_context,
        metadata={
            "registry_version": registry_version,
            "overall_status": metadata["overall_status"],
            "study_type": metadata["study_type"],
            "phase": metadata["phase"],
        },
    )
    arm_drafts = tuple(
        _draft(
            outcome,
            context,
            evidence_id=_evidence_id(outcome, f"trial-arm-{item['source_group_id']}"),
            predicate="clinical_trial_arm_identity_resolved",
            object_value=item["arm_id"],
            relation=EvidenceRelation.SUPPORTS,
            confidence=confidence,
            source_id=record.source_id,
            observed_at=record.observed_at,
            available_at=record.available_at,
            biological_context={**base_context, "arm_id": item["arm_id"]},
            metadata={
                "source_group_id": item["source_group_id"],
                "role": item["role"],
                "arm_type": item["arm_type"],
            },
        )
        for item in arm_values
    )
    population_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "trial-population"),
        predicate="clinical_trial_population_identity_resolved",
        object_value=population["population_id"],
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context={
            **base_context,
            "population_id": population["population_id"],
        },
        metadata={
            "enrollment_count": population["enrollment_count"],
            "enrollment_type": population["enrollment_type"],
            "sex": population["sex"],
            "minimum_age": population["minimum_age"],
            "maximum_age": population.get("maximum_age"),
            "healthy_volunteers": population["healthy_volunteers"],
        },
    )
    endpoint_context = {
        **base_context,
        "population_id": population["population_id"],
        "endpoint_id": endpoint["endpoint_id"],
        "arm_ids": expected_arm_ids,
    }
    endpoint_identity_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "trial-endpoint-identity"),
        predicate="clinical_trial_endpoint_identity_resolved",
        object_value=endpoint["endpoint_id"],
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context=endpoint_context,
        metadata={
            "name": endpoint["name"],
            "outcome_type": endpoint["outcome_type"],
            "time_frame": endpoint["time_frame"],
            "parameter_type": endpoint["parameter_type"],
            "unit": endpoint["unit"],
            "reporting_status": endpoint["reporting_status"],
        },
    )
    clinical_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "clinical-endpoint-benefit"),
        predicate="clinical_evidence_assessed",
        object_value=disease.name,
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        direction="benefit",
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context=endpoint_context,
        metadata={
            "parameter_type": analysis["parameter_type"],
            "parameter_value": parameter_value,
            "confidence_interval_percent": ci_percent,
            "confidence_interval_lower": ci_lower,
            "confidence_interval_upper": ci_upper,
            "p_value_relation": analysis["p_value_relation"],
            "p_value": p_value,
            "candidate_measurement": candidate_measurement,
            "comparator_measurement": comparator_measurement,
            "unit": endpoint["unit"],
            "bounded_interpretation": "posted_primary_time_to_event_benefit",
        },
    )
    safety_context = {
        **base_context,
        "safety_id": safety["safety_id"],
        "arm_ids": expected_arm_ids,
    }
    safety_identity_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "trial-safety-identity"),
        predicate="clinical_trial_safety_identity_resolved",
        object_value=safety["safety_id"],
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context=safety_context,
        metadata={
            "event_category": safety["event_category"],
            "reporting_status": safety["reporting_status"],
            "time_frame": safety["time_frame"],
            "event_term_count": safety["event_term_count"],
        },
    )
    safety_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "clinical-safety-assessment"),
        predicate="clinical_safety_assessed",
        object_value=disease.name,
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        source_id=record.source_id,
        observed_at=record.observed_at,
        available_at=record.available_at,
        biological_context=safety_context,
        metadata={
            "event_category": safety["event_category"],
            "reporting_status": safety["reporting_status"],
            "arm_summaries": [
                {
                    "arm_id": item["arm_id"],
                    "role": item["role"],
                    "serious_num_affected": item["serious_num_affected"],
                    "serious_num_at_risk": item["serious_num_at_risk"],
                }
                for item in safety_arm_values
            ],
            "bounded_interpretation": (
                "posted_aggregate_serious_adverse_event_counts_only"
            ),
            "safety_acceptability_inferred": False,
        },
    )
    drafts = (
        identity_draft,
        *arm_drafts,
        population_draft,
        endpoint_identity_draft,
        clinical_draft,
        safety_identity_draft,
        safety_draft,
    )

    arm_records = tuple(
        TrialArmRecord(
            arm_id=item["arm_id"],
            trial_id=trial_id,
            label=item["label"],
            arm_type=item["arm_type"],
            role=TrialArmRole(item["role"]),
            stage=outcome.request.stage,
            intervention_id=item.get("intervention_id"),
            intervention_names=tuple(item["intervention_names"]),
            identifiers={
                "canonical": item["arm_id"],
                "clinicaltrials_gov_group": item["source_group_id"],
            },
            supporting_evidence=(arm_drafts[index].evidence_id,),
            attributes={
                "measurement": dict(item["measurement"]),
            },
        )
        for index, item in enumerate(arm_values)
    )
    population_record = TrialPopulationRecord(
        population_id=population["population_id"],
        trial_id=trial_id,
        disease_id=disease_id,
        description=population["description"],
        enrollment_count=population["enrollment_count"],
        enrollment_type=population["enrollment_type"],
        sex=population["sex"],
        minimum_age=population["minimum_age"],
        maximum_age=population.get("maximum_age"),
        healthy_volunteers=population["healthy_volunteers"],
        stage=outcome.request.stage,
        identifiers={"canonical": population["population_id"]},
        supporting_evidence=(population_draft.evidence_id,),
        attributes={"source_description_sha256": population.get("description_sha256")},
    )
    endpoint_record = TrialEndpointRecord(
        endpoint_id=endpoint["endpoint_id"],
        trial_id=trial_id,
        population_id=population["population_id"],
        name=endpoint["name"],
        outcome_type=endpoint["outcome_type"],
        time_frame=endpoint["time_frame"],
        parameter_type=endpoint["parameter_type"],
        unit=endpoint["unit"],
        reporting_status=endpoint["reporting_status"],
        arm_ids=tuple(expected_arm_ids),
        stage=outcome.request.stage,
        identifiers={
            "canonical": endpoint["endpoint_id"],
            "clinicaltrials_gov_outcome": (
                f"{trial_id}:outcome:{endpoint.get('outcome_index')}"
            ),
        },
        supporting_evidence=(
            endpoint_identity_draft.evidence_id,
            clinical_draft.evidence_id,
        ),
        attributes={
            "favorable_direction": endpoint["favorable_direction"],
            "analysis": analysis,
        },
    )
    safety_arm_records = tuple(
        TrialSafetyArmRecord(
            safety_arm_id=item["safety_arm_id"],
            safety_id=safety["safety_id"],
            trial_id=trial_id,
            arm_id=item["arm_id"],
            role=TrialArmRole(item["role"]),
            source_group_id=item["source_group_id"],
            source_group_title=item["source_group_title"],
            serious_num_affected=item["serious_num_affected"],
            serious_num_at_risk=item["serious_num_at_risk"],
            stage=outcome.request.stage,
            identifiers={
                "canonical": item["safety_arm_id"],
                "clinicaltrials_gov_adverse_event_group": item[
                    "source_group_id"
                ],
            },
            supporting_evidence=(
                safety_identity_draft.evidence_id,
                safety_draft.evidence_id,
            ),
            attributes={"summary_scope": "participants_with_serious_adverse_events"},
        )
        for item in safety_arm_values
    )
    safety_record = TrialSafetyRecord(
        safety_id=safety["safety_id"],
        trial_id=trial_id,
        event_category=safety["event_category"],
        reporting_status=safety["reporting_status"],
        time_frame=safety["time_frame"],
        description=safety.get("description"),
        event_term_count=safety["event_term_count"],
        arm_summaries=safety_arm_records,
        stage=outcome.request.stage,
        identifiers={
            "canonical": safety["safety_id"],
            "clinicaltrials_gov": trial_id,
        },
        supporting_evidence=(
            safety_identity_draft.evidence_id,
            safety_draft.evidence_id,
        ),
        attributes={
            "interpretation": "posted_aggregate_serious_adverse_event_counts_only",
            "safety_acceptability_inferred": False,
        },
    )
    design_support = tuple(item.evidence_id for item in drafts)
    design_record = TrialDesignRecord(
        design_id=design_id,
        trial_id=trial_id,
        intervention_id=intervention_id,
        disease_id=disease_id,
        stage=outcome.request.stage,
        arms=arm_records,
        populations=(population_record,),
        endpoints=(endpoint_record,),
        safety_records=(safety_record,),
        identifiers={
            "canonical": design_id,
            "clinicaltrials_gov": trial_id,
        },
        supporting_evidence=design_support,
        attributes={
            "registry_version": registry_version,
            "source_record_id": record.record_id,
            "source_lineage_ids": lineages,
        },
    )
    previous_intervention_support = (
        existing_intervention.supporting_evidence
        if existing_intervention is not None
        else ()
    )
    intervention = InterventionRecord(
        intervention_id=intervention_id,
        name=candidate.name,
        candidate_id=candidate_id,
        disease_id=disease_id,
        modality=candidate.modality,
        stage=outcome.request.stage,
        identifiers={
            **(
                dict(existing_intervention.identifiers)
                if existing_intervention is not None
                else {}
            ),
            "canonical": intervention_id,
            **(
                {"chembl_molecule": candidate_id}
                if candidate_id.startswith("CHEMBL")
                else {}
            ),
        },
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *previous_intervention_support,
                    identity_draft.evidence_id,
                    clinical_draft.evidence_id,
                    safety_draft.evidence_id,
                )
            )
        ),
        attributes={
            **(
                dict(existing_intervention.attributes)
                if existing_intervention is not None
                else {}
            ),
            "clinical_trial_ids": sorted(
                {
                    *(
                        existing_intervention.attributes.get("clinical_trial_ids", ())
                        if existing_intervention is not None
                        else ()
                    ),
                    trial_id,
                }
            ),
            "clinical_evidence_assessed": True,
            "clinical_safety_assessed": True,
        },
    )
    previous_trial_support = (
        existing_trial.supporting_evidence if existing_trial is not None else ()
    )
    trial = TrialRecord(
        trial_id=trial_id,
        registry="ClinicalTrials.gov",
        intervention_id=intervention_id,
        disease_id=disease_id,
        stage=outcome.request.stage,
        identifiers={
            **(dict(existing_trial.identifiers) if existing_trial is not None else {}),
            "canonical": trial_id,
            "clinicaltrials_gov": trial_id,
        },
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *previous_trial_support,
                    identity_draft.evidence_id,
                    clinical_draft.evidence_id,
                    safety_draft.evidence_id,
                )
            )
        ),
        attributes={
            **(dict(existing_trial.attributes) if existing_trial is not None else {}),
            "design_id": design_id,
            "registry_version": registry_version,
            "overall_status": metadata["overall_status"],
            "study_type": metadata["study_type"],
            "phase": metadata["phase"],
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "clinical-evidence"),
        stage=outcome.request.stage,
        subject=candidate.name,
        predicate="clinical_evidence_assessed",
        object_value=disease.name,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(clinical_draft.evidence_id,),
        confidence=confidence,
        biological_context=endpoint_context,
    )
    safety_claim = ScientificClaim(
        claim_id=_claim_id(outcome, "clinical-safety"),
        stage=outcome.request.stage,
        subject=candidate.name,
        predicate="clinical_safety_assessed",
        object_value=disease.name,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(safety_draft.evidence_id,),
        confidence=confidence,
        biological_context=safety_context,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="pinned_clinical_trial_design_promoted",
        message=(
            "Exact posted endpoint, serious-adverse-event summary, population, "
            "and arm identities were promoted atomically."
        ),
        evidence_drafts=drafts,
        claim_updates=(claim, safety_claim),
        intervention_updates=(intervention,),
        trial_updates=(trial,),
        trial_design_updates=(design_record,),
        recommended_decision=Decision.ADVANCE,
        details={
            "trial_id": trial_id,
            "design_id": design_id,
            "arm_ids": expected_arm_ids,
            "population_id": population["population_id"],
            "endpoint_id": endpoint["endpoint_id"],
            "safety_id": safety["safety_id"],
            "registry_version": registry_version,
        },
    )


def _pubmed_locator_matches(locator: str, pmid: str) -> bool:
    parsed = urllib.parse.urlsplit(locator)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return (
        parsed.scheme.casefold() == "https"
        and parsed.hostname == "eutils.ncbi.nlm.nih.gov"
        and parsed.path == "/entrez/eutils/efetch.fcgi"
        and query.get("db") == ["pubmed"]
        and query.get("id") == [pmid]
        and query.get("retmode") == ["xml"]
    )


def _map_pinned_clinical_trial_disposition(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "pinned_clinical_trial_disposition_v1"
    if outcome.request.stage is not Stage.CLINICAL_STRATEGY:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_stage_unsupported",
            "Pinned clinical disposition promotion is limited to clinical strategy.",
        )

    candidate_id = _text(outcome.request.arguments.get("candidate_id"))
    disease_id = _text(outcome.request.arguments.get("disease_id"))
    trial_id = _text(outcome.request.arguments.get("trial_id"))
    candidate = (
        state.candidates_by_id.get(candidate_id) if candidate_id is not None else None
    )
    disease = state.diseases_by_id.get(disease_id) if disease_id is not None else None
    candidate_interventions = tuple(
        item
        for item in state.interventions
        if candidate is not None and item.candidate_id == candidate.candidate_id
    )
    if len(candidate_interventions) > 1:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_intervention_ambiguous",
            "More than one clinical intervention claims the accepted candidate.",
        )
    existing_intervention = (
        candidate_interventions[0] if candidate_interventions else None
    )
    intervention_id = (
        existing_intervention.intervention_id
        if existing_intervention is not None
        else candidate_id
    )
    if (
        candidate_id is None
        or disease_id is None
        or trial_id is None
        or re.fullmatch(r"NCT[0-9]{8}", trial_id) is None
        or candidate is None
        or disease is None
        or intervention_id is None
        or candidate.attributes.get("disease_id") != disease_id
        or _normalized(disease.name) != _normalized(state.disease)
        or context.candidate_id != candidate_id
        or context.candidate_name is None
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.subject) != _normalized(candidate.name)
        or _normalized(context.object_value) != _normalized(disease.name)
        or context.biological_context.get("disease_id") != disease_id
        or (
            context.biological_context.get("intervention_id") is not None
            and context.biological_context.get("intervention_id") != intervention_id
        )
        or not _profile_query_matches(
            outcome.payload,
            candidate_id=candidate_id,
            disease_id=disease_id,
            trial_id=trial_id,
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_context_mismatch",
            "Candidate, disease, intervention, trial, and profile query must match.",
        )

    predicates = (
        "clinical_trial_terminated_for_lack_of_efficacy",
        "clinical_primary_endpoint_not_met",
    )
    try:
        registry_record, publication_record = _parse_pinned_profile(
            outcome, predicates
        )
    except ValueError as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_profile_invalid",
            "Pinned clinical disposition profile failed source validation.",
            details={"validation_error": str(exc)},
        )

    protocol_id = _text(registry_record.biological_context.get("protocol_id"))
    publication_protocol_id = _text(
        publication_record.biological_context.get("protocol_id")
    )
    records = (registry_record, publication_record)
    if (
        protocol_id is None
        or publication_protocol_id != protocol_id
        or any(
            not _record_context_matches(
                record,
                candidate_id=candidate_id,
                intervention_id=intervention_id,
                disease_id=disease_id,
                trial_id=trial_id,
                protocol_id=protocol_id,
            )
            for record in records
        )
        or any(
            _normalized(record.subject) != _normalized(candidate.name)
            or _normalized(record.object_value) != _normalized(disease.name)
            for record in records
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_record_mismatch",
            "Both records must bind the accepted candidate, disease, trial, and protocol.",
        )
    after_cutoff = [
        record.record_id for record in records if record.available_at > state.as_of_date
    ]
    if after_cutoff:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_after_cutoff",
            "Clinical disposition evidence was unavailable at the program cutoff.",
            details={
                "record_ids": after_cutoff,
                "as_of_date": state.as_of_date.isoformat(),
            },
        )
    if (
        registry_record.source_id == publication_record.source_id
        or registry_record.content_hash == publication_record.content_hash
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_source_collision",
            "Registry and publication records must come from distinct captured bytes.",
        )

    registry = registry_record.metadata
    publication = publication_record.metadata
    registry_aliases = _metadata_text_values(registry_record, "candidate_aliases")
    publication_aliases = _metadata_text_values(
        publication_record, "candidate_aliases"
    )
    source_interventions = _metadata_text_values(
        registry_record, "source_interventions"
    )
    source_conditions = _metadata_text_values(registry_record, "source_conditions")
    registry_lineages = _metadata_text_values(
        registry_record, "source_lineage_ids"
    )
    publication_lineages = _metadata_text_values(
        publication_record, "source_lineage_ids"
    )
    shared_lineage = _text(registry.get("shared_trial_lineage_id"))
    publication_shared_lineage = _text(
        publication.get("shared_trial_lineage_id")
    )
    registry_version = _text(registry.get("registry_version"))
    pmid = _text(publication.get("pmid"))
    publication_date = _text(publication.get("publication_date"))
    candidate_rate = _number(publication.get("candidate_rate"))
    comparator_rate = _number(publication.get("comparator_rate"))
    try:
        if registry_version is None or publication_date is None:
            raise ValueError("source dates are missing")
        _iso_date(registry_version, "registry_version")
        _iso_date(publication_date, "publication_date")
    except ValueError as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_source_date_invalid",
            "Clinical disposition source dates are invalid.",
            details={"validation_error": str(exc)},
        )

    registry_alias_set = {_normalized(item) for item in registry_aliases or ()}
    publication_alias_set = {
        _normalized(item) for item in publication_aliases or ()
    }
    source_intervention_set = {
        _normalized(item) for item in source_interventions or ()
    }
    expected_shared_lineage = f"sponsor-protocol:{protocol_id}"
    if (
        _normalized(str(registry.get("provider_id", "")))
        != "clinicaltrials_gov"
        or _normalized(str(registry.get("registry", "")))
        != "clinicaltrials.gov"
        or _normalized(str(registry.get("study_type", ""))) != "interventional"
        or _normalized(str(registry.get("overall_status", ""))) != "terminated"
        or _normalized(str(registry.get("why_stopped_code", "")))
        != "lack_of_efficacy"
        or _text(registry.get("why_stopped")) is None
        or _text(registry.get("phase")) is None
        or _text(registry.get("primary_endpoint")) is None
        or not isinstance(registry.get("enrollment_count"), int)
        or registry_aliases is None
        or publication_aliases is None
        or source_interventions is None
        or source_conditions is None
        or registry_lineages is None
        or publication_lineages is None
        or shared_lineage != expected_shared_lineage
        or publication_shared_lineage != expected_shared_lineage
        or expected_shared_lineage not in registry_lineages
        or expected_shared_lineage not in publication_lineages
        or f"clinicaltrials-gov:{trial_id}" not in registry_lineages
        or registry_record.source_id != f"clinicaltrials-gov-{trial_id}"
        or registry_record.source_version
        != f"clinicaltrials-gov-{trial_id}-version-{registry_version}"
        or registry_record.locator
        != f"https://clinicaltrials.gov/api/v2/studies/{trial_id}"
        or _normalized(candidate.name) not in registry_alias_set
        or not (registry_alias_set & source_intervention_set)
        or not any(
            _source_text_matches(disease.name, item) for item in source_conditions
        )
        or _normalized(str(publication.get("provider_id", "")))
        != "ncbi_pubmed"
        or pmid is None
        or re.fullmatch(r"[1-9][0-9]{0,15}", pmid) is None
        or publication_record.source_id != f"ncbi-pubmed-{pmid}"
        or re.fullmatch(
            rf"pmid-{re.escape(pmid)}-pubmed-xml-[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}",
            publication_record.source_version,
        )
        is None
        or not _pubmed_locator_matches(publication_record.locator, pmid)
        or _text(publication.get("doi")) is None
        or _text(publication.get("article_title")) is None
        or _text(publication.get("source_candidate_name")) is None
        or _normalized(str(publication.get("effect_direction", "")))
        != "no_clinical_benefit"
        or publication.get("primary_endpoint_met") is not False
        or _normalized(str(publication.get("early_termination_reason", "")))
        != "lack_of_efficacy"
        or _text(publication.get("endpoint_name")) is None
        or _text(publication.get("rate_unit")) is None
        or candidate_rate is None
        or comparator_rate is None
        or candidate_rate < 0
        or comparator_rate < 0
        or _normalized(candidate.name) not in publication_alias_set
        or _normalized(str(publication.get("source_candidate_name", "")))
        not in publication_alias_set
        or f"pubmed:{pmid}" not in publication_lineages
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_metadata_invalid",
            "Clinical disposition metadata lacks exact registry or publication identities.",
        )

    if existing_intervention is not None and (
        existing_intervention.name != candidate.name
        or existing_intervention.candidate_id != candidate_id
        or existing_intervention.disease_id != disease_id
        or _normalized(existing_intervention.modality)
        != _normalized(candidate.modality)
        or existing_intervention.identifiers.get("canonical") != intervention_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_intervention_rebound",
            "Existing intervention identity conflicts with the candidate ledger.",
        )
    existing_trial = state.trials_by_id.get(trial_id)
    if existing_trial is not None and (
        _normalized(existing_trial.registry) != "clinicaltrials.gov"
        or existing_trial.intervention_id != intervention_id
        or existing_trial.disease_id != disease_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "pinned_clinical_disposition_trial_rebound",
            "Existing trial identity conflicts with the accepted intervention.",
        )

    base_context = {
        **dict(context.biological_context),
        "candidate_id": candidate_id,
        "intervention_id": intervention_id,
        "disease_id": disease_id,
        "trial_id": trial_id,
        "protocol_id": protocol_id,
        "registry": "ClinicalTrials.gov",
    }
    registry_confidence = min(context.confidence, registry_record.confidence)
    publication_confidence = min(context.confidence, publication_record.confidence)
    identity_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, f"trial-identity-{trial_id}"),
        predicate="clinical_trial_identity_resolved",
        object_value=trial_id,
        relation=EvidenceRelation.SUPPORTS,
        confidence=registry_confidence,
        source_id=registry_record.source_id,
        observed_at=registry_record.observed_at,
        available_at=registry_record.available_at,
        biological_context=base_context,
        metadata={
            "registry_version": registry_version,
            "protocol_id": protocol_id,
            "overall_status": registry["overall_status"],
        },
    )
    registry_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "registry-negative-disposition"),
        predicate="clinical_evidence_assessed",
        object_value=disease.name,
        relation=EvidenceRelation.CONTRADICTS,
        direction="no_clinical_benefit",
        confidence=registry_confidence,
        source_id=registry_record.source_id,
        observed_at=registry_record.observed_at,
        available_at=registry_record.available_at,
        biological_context=base_context,
        metadata={
            "evidence_role": "registry_disposition",
            "overall_status": registry["overall_status"],
            "why_stopped": registry["why_stopped"],
            "why_stopped_code": registry["why_stopped_code"],
            "primary_endpoint": registry["primary_endpoint"],
            "shared_trial_lineage_id": expected_shared_lineage,
        },
    )
    publication_draft = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "publication-primary-endpoint"),
        predicate="clinical_evidence_assessed",
        object_value=disease.name,
        relation=EvidenceRelation.CONTRADICTS,
        direction="no_clinical_benefit",
        confidence=publication_confidence,
        source_id=publication_record.source_id,
        observed_at=publication_record.observed_at,
        available_at=publication_record.available_at,
        biological_context=base_context,
        metadata={
            "evidence_role": "publication_outcome",
            "pmid": pmid,
            "doi": publication["doi"],
            "primary_endpoint_met": False,
            "endpoint_name": publication["endpoint_name"],
            "candidate_rate": candidate_rate,
            "comparator_rate": comparator_rate,
            "rate_unit": publication["rate_unit"],
            "shared_trial_lineage_id": expected_shared_lineage,
        },
    )
    clinical_evidence_ids = (
        registry_draft.evidence_id,
        publication_draft.evidence_id,
    )
    previous_intervention_support = (
        existing_intervention.supporting_evidence
        if existing_intervention is not None
        else ()
    )
    intervention = InterventionRecord(
        intervention_id=intervention_id,
        name=candidate.name,
        candidate_id=candidate_id,
        disease_id=disease_id,
        modality=candidate.modality,
        stage=outcome.request.stage,
        identifiers={
            **(
                dict(existing_intervention.identifiers)
                if existing_intervention is not None
                else {}
            ),
            "canonical": intervention_id,
            **(
                {"chembl_molecule": candidate_id}
                if candidate_id.startswith("CHEMBL")
                else {}
            ),
        },
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *previous_intervention_support,
                    identity_draft.evidence_id,
                )
            )
        ),
        attributes={
            **(
                dict(existing_intervention.attributes)
                if existing_intervention is not None
                else {}
            ),
            "clinical_trial_ids": sorted(
                {
                    *(
                        existing_intervention.attributes.get("clinical_trial_ids", ())
                        if existing_intervention is not None
                        else ()
                    ),
                    trial_id,
                }
            ),
            "clinical_evidence_assessed": True,
            "historical_negative_disposition": True,
        },
    )
    previous_trial_support = (
        existing_trial.supporting_evidence if existing_trial is not None else ()
    )
    trial = TrialRecord(
        trial_id=trial_id,
        registry="ClinicalTrials.gov",
        intervention_id=intervention_id,
        disease_id=disease_id,
        stage=outcome.request.stage,
        identifiers={
            **(dict(existing_trial.identifiers) if existing_trial is not None else {}),
            "canonical": trial_id,
            "clinicaltrials_gov": trial_id,
            "sponsor_protocol": protocol_id,
        },
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *previous_trial_support,
                    identity_draft.evidence_id,
                )
            )
        ),
        attributes={
            **(dict(existing_trial.attributes) if existing_trial is not None else {}),
            "registry_version": registry_version,
            "overall_status": registry["overall_status"],
            "study_type": registry["study_type"],
            "phase": registry["phase"],
            "protocol_id": protocol_id,
            "primary_endpoint_met": False,
            "disposition": "terminated_for_lack_of_efficacy",
            "corroborating_source_count": 2,
            "independent_trial_count": 1,
            "shared_trial_lineage": True,
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "clinical-benefit"),
        stage=outcome.request.stage,
        subject=candidate.name,
        predicate="clinical_benefit_demonstrated",
        object_value=disease.name,
        disposition=ClaimDisposition.REJECTED,
        contradicting_evidence=clinical_evidence_ids,
        confidence=min(registry_confidence, publication_confidence),
        biological_context=base_context,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="pinned_clinical_lack_of_efficacy_promoted",
        message=(
            "Registry disposition and publication outcome were promoted as "
            "corroborating records for one historical trial lineage."
        ),
        evidence_drafts=(identity_draft, registry_draft, publication_draft),
        claim_updates=(claim,),
        intervention_updates=(intervention,),
        trial_updates=(trial,),
        recommended_decision=Decision.KILL,
        details={
            "trial_id": trial_id,
            "protocol_id": protocol_id,
            "corroborating_source_count": 2,
            "independent_trial_count": 1,
            "shared_trial_lineage": True,
            "scope": "historical_candidate_indication_pair",
        },
    )


def _map_ctgov_trials(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "ctgov_clinical_evidence_v1"
    if outcome.request.stage is not Stage.CLINICAL_STRATEGY:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_stage_unsupported",
            "ClinicalTrials.gov evidence promotion is limited to clinical strategy.",
        )
    candidate_id = context.candidate_id
    candidate = (
        state.candidates_by_id.get(candidate_id)
        if isinstance(candidate_id, str)
        else None
    )
    disease_id = (
        candidate.attributes.get("disease_id") if candidate is not None else None
    )
    disease = (
        state.diseases_by_id.get(disease_id) if isinstance(disease_id, str) else None
    )
    context_disease_id = context.biological_context.get("disease_id")
    context_intervention_id = context.biological_context.get("intervention_id")
    if (
        candidate is None
        or disease is None
        or context.candidate_name is None
        or context.modality is None
        or _normalized(context.subject) != _normalized(candidate.name)
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.modality) != _normalized(candidate.modality)
        or (context_disease_id is not None and context_disease_id != disease.disease_id)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_intervention_context_invalid",
            "ClinicalTrials.gov promotion lacks one canonical candidate and disease context.",
        )
    candidate_interventions = tuple(
        item
        for item in state.interventions
        if item.candidate_id == candidate.candidate_id
    )
    if len(candidate_interventions) > 1:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_intervention_identity_ambiguous",
            "More than one clinical intervention claims the accepted candidate.",
        )
    existing_intervention = (
        candidate_interventions[0] if candidate_interventions else None
    )
    intervention_id = (
        existing_intervention.intervention_id
        if existing_intervention is not None
        else candidate.candidate_id
    )
    if (
        context_intervention_id is not None
        and context_intervention_id != intervention_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_intervention_context_invalid",
            "ClinicalTrials.gov promotion context disagrees with the accepted intervention.",
        )
    requested_drug = _text(outcome.request.arguments.get("drug"))
    if (
        requested_drug is None
        or _normalized(requested_drug) != _normalized(context.subject)
        or _normalized(requested_drug) != _normalized(candidate.name)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_asset_mismatch",
            "ClinicalTrials.gov request asset does not match the candidate ledger.",
        )
    requested_condition = _text(outcome.request.arguments.get("condition"))
    if (
        requested_condition is None
        or _normalized(requested_condition) != _normalized(context.object_value)
        or _normalized(requested_condition) != _normalized(state.disease)
        or _normalized(requested_condition) != _normalized(disease.name)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_condition_mismatch",
            "ClinicalTrials.gov request condition does not match the disease ledger.",
        )
    items = outcome.payload.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_payload_invalid",
            "ClinicalTrials.gov payload must contain an item sequence.",
        )
    if not items:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "ctgov_no_matching_trials",
            "No matching trials were available for semantic promotion.",
            recommended_decision=Decision.DEFER,
        )

    if existing_intervention is not None and (
        existing_intervention.name != candidate.name
        or existing_intervention.candidate_id != candidate.candidate_id
        or existing_intervention.disease_id != disease.disease_id
        or _normalized(existing_intervention.modality)
        != _normalized(candidate.modality)
        or existing_intervention.identifiers.get("canonical")
        != existing_intervention.intervention_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ctgov_intervention_identity_rebound",
            "Existing clinical intervention identity disagrees with the candidate ledger.",
        )

    drafts: list[EvidenceDraft] = []
    trial_updates: list[TrialRecord] = []
    support_ids: list[str] = []
    contradiction_ids: list[str] = []
    intervention_support_ids = list(
        existing_intervention.supporting_evidence
        if existing_intervention is not None
        else ()
    )
    seen_ncts: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "ctgov_payload_invalid",
                "ClinicalTrials.gov trial items must be mappings.",
            )
        nct = _text(item.get("nct"))
        source_interventions = _text(item.get("interventions"))
        source_conditions = _text(item.get("conditions"))
        if nct is None or re.fullmatch(r"NCT[0-9]{8}", nct) is None or nct in seen_ncts:
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "ctgov_trial_identity_invalid",
                "ClinicalTrials.gov trial ids must be unique NCT identifiers.",
            )
        if not _source_text_matches(
            requested_drug, source_interventions
        ) or not _source_text_matches(requested_condition, source_conditions):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "ctgov_source_identity_mismatch",
                "ClinicalTrials.gov source fields do not match the intervention and disease.",
                details={"trial_id": nct},
            )
        seen_ncts.add(nct)
        significant = item.get("significant")
        direction = _text(item.get("direction")) or "unknown"
        has_results = item.get("has_results")
        mixed = item.get("mixed_within") is True
        if not (significant is None or isinstance(significant, bool)) or not isinstance(
            has_results, bool
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "ctgov_trial_result_invalid",
                "Clinical trial result flags violate the declared payload schema.",
            )
        relation = EvidenceRelation.CONTEXTUALIZES
        if has_results and significant is True and not mixed:
            if direction.casefold() == "benefit":
                relation = EvidenceRelation.SUPPORTS
            elif direction.casefold() == "harm":
                relation = EvidenceRelation.CONTRADICTS
        evidence_context = {
            **dict(context.biological_context),
            "candidate_id": candidate.candidate_id,
            "intervention_id": intervention_id,
            "disease_id": disease.disease_id,
            "trial_id": nct,
            "registry": "ClinicalTrials.gov",
        }
        evidence_id = _evidence_id(outcome, f"trial-result-{index + 1}-{nct}")
        result_draft = _draft(
            outcome,
            context,
            evidence_id=evidence_id,
            predicate="clinical_evidence_assessed",
            object_value=context.object_value,
            relation=relation,
            confidence=context.confidence,
            direction=direction,
            biological_context=evidence_context,
            metadata={
                "nct": nct,
                "source_interventions": source_interventions,
                "source_conditions": source_conditions,
                "significant": significant,
                "has_results": has_results,
                "mixed_within": mixed,
            },
        )
        identity_id = _evidence_id(outcome, f"trial-identity-{index + 1}-{nct}")
        identity_draft = _draft(
            outcome,
            context,
            evidence_id=identity_id,
            predicate="clinical_trial_identity_resolved",
            object_value=nct,
            relation=EvidenceRelation.SUPPORTS,
            confidence=context.confidence,
            biological_context=evidence_context,
            metadata={
                "nct": nct,
                "registry": "ClinicalTrials.gov",
                "source_interventions": source_interventions,
                "source_conditions": source_conditions,
            },
        )
        drafts.extend((result_draft, identity_draft))
        intervention_support_ids.append(identity_id)
        if relation is EvidenceRelation.SUPPORTS:
            support_ids.append(evidence_id)
            intervention_support_ids.append(evidence_id)
        elif relation is EvidenceRelation.CONTRADICTS:
            contradiction_ids.append(evidence_id)

        existing_trial = state.trials_by_id.get(nct)
        if existing_trial is not None and (
            _normalized(existing_trial.registry) != "clinicaltrials.gov"
            or existing_trial.intervention_id != intervention_id
            or existing_trial.disease_id != disease.disease_id
        ):
            return _empty_result(
                mapper_id,
                outcome,
                PromotionStatus.REJECTED,
                "ctgov_trial_identity_rebound",
                "Existing trial identity disagrees with the clinical intervention.",
                details={"trial_id": nct},
            )
        trial_support = [
            *(existing_trial.supporting_evidence if existing_trial is not None else ()),
            identity_id,
        ]
        if relation is EvidenceRelation.SUPPORTS:
            trial_support.append(evidence_id)
        trial_updates.append(
            TrialRecord(
                trial_id=nct,
                registry="ClinicalTrials.gov",
                intervention_id=intervention_id,
                disease_id=disease.disease_id,
                stage=outcome.request.stage,
                identifiers={
                    **(
                        dict(existing_trial.identifiers)
                        if existing_trial is not None
                        else {}
                    ),
                    "canonical": nct,
                    "clinicaltrials_gov": nct,
                },
                supporting_evidence=tuple(dict.fromkeys(trial_support)),
                attributes={
                    **(
                        dict(existing_trial.attributes)
                        if existing_trial is not None
                        else {}
                    ),
                    "source_interventions": source_interventions,
                    "source_conditions": source_conditions,
                    "significant": significant,
                    "direction": direction,
                    "has_results": has_results,
                    "mixed_within": mixed,
                },
            )
        )

    claim_context = {
        **dict(context.biological_context),
        "candidate_id": candidate.candidate_id,
        "intervention_id": intervention_id,
        "disease_id": disease.disease_id,
    }
    claims: tuple[ScientificClaim, ...] = ()
    recommended = Decision.DEFER
    code = "ctgov_evidence_contextual_only"
    if support_ids and contradiction_ids:
        claim = ScientificClaim(
            claim_id=_claim_id(outcome, "clinical-evidence"),
            stage=outcome.request.stage,
            subject=context.subject,
            predicate="clinical_evidence_assessed",
            object_value=context.object_value,
            disposition=ClaimDisposition.CONTESTED,
            supporting_evidence=tuple(support_ids),
            contradicting_evidence=tuple(contradiction_ids),
            confidence=context.confidence,
            resolution_rationale="Benefit and harm signals remain separated pending review.",
            biological_context=claim_context,
        )
        claims = (claim,)
        code = "ctgov_evidence_contested"
    elif support_ids:
        claim = ScientificClaim(
            claim_id=_claim_id(outcome, "clinical-evidence"),
            stage=outcome.request.stage,
            subject=context.subject,
            predicate="clinical_evidence_assessed",
            object_value=context.object_value,
            disposition=ClaimDisposition.SUPPORTED,
            supporting_evidence=tuple(support_ids),
            confidence=context.confidence,
            biological_context=claim_context,
        )
        claims = (claim,)
        recommended = Decision.ADVANCE
        code = "ctgov_benefit_evidence_promoted"
    elif contradiction_ids:
        claim = ScientificClaim(
            claim_id=_claim_id(outcome, "clinical-evidence"),
            stage=outcome.request.stage,
            subject=context.subject,
            predicate="clinical_evidence_assessed",
            object_value=context.object_value,
            disposition=ClaimDisposition.REJECTED,
            contradicting_evidence=tuple(contradiction_ids),
            confidence=context.confidence,
            biological_context=claim_context,
        )
        claims = (claim,)
        recommended = Decision.HOLD
        code = "ctgov_harm_evidence_promoted"

    identifiers = (
        dict(existing_intervention.identifiers)
        if existing_intervention is not None
        else {"canonical": intervention_id}
    )
    if candidate.candidate_id.startswith("CHEMBL"):
        identifiers["chembl_molecule"] = candidate.candidate_id
    previous_trial_ids = (
        existing_intervention.attributes.get("clinical_trial_ids", ())
        if existing_intervention is not None
        else ()
    )
    intervention = InterventionRecord(
        intervention_id=intervention_id,
        name=candidate.name,
        candidate_id=candidate.candidate_id,
        disease_id=disease.disease_id,
        modality=candidate.modality,
        stage=outcome.request.stage,
        identifiers=identifiers,
        supporting_evidence=tuple(dict.fromkeys(intervention_support_ids)),
        attributes={
            **(
                dict(existing_intervention.attributes)
                if existing_intervention is not None
                else {}
            ),
            "clinical_trial_ids": sorted({*previous_trial_ids, *seen_ncts}),
            "clinical_evidence_assessed": True,
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code=code,
        message="Clinical trial records were promoted without treating non-significance as failure.",
        evidence_drafts=tuple(drafts),
        claim_updates=claims,
        intervention_updates=(intervention,),
        trial_updates=tuple(trial_updates),
        recommended_decision=recommended,
        details={
            "trial_count": len(trial_updates),
            "support_count": len(support_ids),
            "contradiction_count": len(contradiction_ids),
            "intervention_id": intervention.intervention_id,
            "trial_ids": sorted(seen_ncts),
        },
    )


def _map_clinical_endpoint_mapping(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "clinical_endpoint_mapping_v1"
    if outcome.request.stage is not Stage.REGULATORY_POSTMARKET:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_endpoint_mapping_stage_unsupported",
            "Endpoint mapping is limited to regulatory/postmarket review.",
        )
    try:
        spec = clinical_endpoint_mapping_spec_from_dict(outcome.payload)
        request_spec = clinical_endpoint_mapping_spec_from_dict(
            outcome.request.arguments.get("spec"), "request.spec"
        )
    except (ClinicalEndpointMappingError, TypeError, ValueError) as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_endpoint_mapping_spec_invalid",
            "Endpoint mapping declaration failed strict schema validation.",
            details={"validation_error": str(exc)},
        )
    if (
        spec != request_spec
        or to_primitive(outcome.payload)
        != clinical_endpoint_mapping_spec_to_dict(spec)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_endpoint_mapping_payload_mismatch",
            "Tool payload does not exactly match the reviewed mapping request.",
        )
    if spec.review.reviewed_at > outcome.request.created_at:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_endpoint_mapping_review_not_yet_effective",
            "Endpoint mapping approval must precede the tool request.",
        )
    candidate = state.candidates_by_id.get(spec.candidate_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if (
        candidate is None
        or disease is None
        or context.candidate_id != spec.candidate_id
        or context.candidate_name is None
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.subject) != _normalized(candidate.name)
        or _normalized(context.object_value) != _normalized(disease.name)
        or context.biological_context.get("disease_id") != spec.disease_id
        or context.biological_context.get("intervention_id")
        != spec.intervention_id
        or context.biological_context.get("mapping_id") != spec.mapping_id
        or context.biological_context.get("portfolio_id") != spec.portfolio_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_endpoint_mapping_context_mismatch",
            "Mapping request does not match accepted clinical identities.",
        )
    try:
        mapping = compile_clinical_endpoint_mapping(state, spec)
    except (ClinicalEndpointMappingError, TypeError, ValueError) as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "clinical_endpoint_mapping_not_bindable",
            "Reviewed endpoint mapping did not bind to exact clinical ledger records.",
            recommended_decision=Decision.DEFER,
            details={"validation_error": str(exc)},
        )
    source_confidences = tuple(
        state.evidence_by_id[evidence_id].confidence
        for evidence_id in mapping.source_evidence_ids
    )
    confidence = min((context.confidence, *source_confidences))
    evidence_context = {
        **dict(context.biological_context),
        "candidate_id": mapping.candidate_id,
        "intervention_id": mapping.intervention_id,
        "disease_id": mapping.disease_id,
        "mapping_id": mapping.mapping_id,
        "portfolio_id": mapping.portfolio_id,
        "endpoint_family_id": mapping.endpoint_family_id,
        "trial_ids": [item.trial_id for item in mapping.bindings],
    }
    mapping_evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "endpoint-mapping"),
        predicate="clinical_endpoint_mapping_approved",
        object_value=mapping.endpoint_family_id,
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        biological_context=evidence_context,
        metadata={
            "upstream_evidence_ids": mapping.source_evidence_ids,
            "upstream_source_content_hashes": mapping.source_content_hashes,
            "ontology": {
                "system": mapping.ontology_system,
                "version": mapping.ontology_version,
                "code": mapping.ontology_code,
                "label": mapping.ontology_label,
            },
            "review_status": mapping.review_status,
            "reviewer_id": mapping.reviewer_id,
            "reviewed_at": mapping.reviewed_at.isoformat(),
            "binding_count": len(mapping.bindings),
            "automatic_endpoint_mapping_performed": False,
            "ontology_authority_verified": False,
        },
    )
    promoted_mapping = replace(
        mapping,
        supporting_evidence=(
            *mapping.supporting_evidence,
            mapping_evidence.evidence_id,
        ),
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "endpoint-mapping"),
        stage=outcome.request.stage,
        subject=candidate.name,
        predicate="clinical_endpoint_mapping_approved",
        object_value=mapping.endpoint_family_id,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(mapping_evidence.evidence_id,),
        confidence=confidence,
        resolution_rationale=(
            "The claim records reviewer approval and exact ledger binding; it does "
            "not assert ontology-authority verification or cross-trial comparability."
        ),
        biological_context=evidence_context,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="clinical_endpoint_mapping_promoted",
        message=(
            "Reviewer approval was bound to exact trial endpoint, safety, and source "
            "identities without automatic mapping."
        ),
        evidence_drafts=(mapping_evidence,),
        claim_updates=(claim,),
        clinical_endpoint_mapping_updates=(promoted_mapping,),
        details={
            "mapping_id": mapping.mapping_id,
            "portfolio_id": mapping.portfolio_id,
            "trial_ids": [item.trial_id for item in mapping.bindings],
            "source_content_hashes": mapping.source_content_hashes,
            "automatic_endpoint_mapping_performed": False,
            "ontology_authority_verified": False,
        },
    )


def _map_clinical_benefit_risk_synthesis(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "clinical_benefit_risk_synthesis_v1"
    if outcome.request.stage is not Stage.REGULATORY_POSTMARKET:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_synthesis_stage_unsupported",
            "Benefit-risk synthesis is limited to regulatory/postmarket review.",
        )
    try:
        spec = clinical_synthesis_spec_from_dict(outcome.payload)
        request_spec = clinical_synthesis_spec_from_dict(
            outcome.request.arguments.get("spec"), "request.spec"
        )
    except (ClinicalSynthesisError, TypeError, ValueError) as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_synthesis_spec_invalid",
            "Clinical synthesis declaration failed strict schema validation.",
            details={"validation_error": str(exc)},
        )
    if (
        spec != request_spec
        or to_primitive(outcome.payload) != clinical_synthesis_spec_to_dict(spec)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_synthesis_payload_mismatch",
            "Tool payload does not exactly match the reviewed synthesis request.",
        )
    candidate = state.candidates_by_id.get(spec.candidate_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if (
        candidate is None
        or disease is None
        or context.candidate_id != spec.candidate_id
        or context.candidate_name is None
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.subject) != _normalized(candidate.name)
        or _normalized(context.object_value) != _normalized(disease.name)
        or context.biological_context.get("disease_id") != spec.disease_id
        or context.biological_context.get("intervention_id")
        != spec.intervention_id
        or context.biological_context.get("endpoint_mapping_id")
        != spec.endpoint_mapping_id
        or context.biological_context.get("synthesis_id") != spec.synthesis_id
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "clinical_synthesis_context_mismatch",
            "Synthesis request does not match accepted clinical identities.",
        )
    try:
        synthesis = compile_benefit_risk_synthesis(state, spec)
    except (ClinicalSynthesisError, TypeError, ValueError) as exc:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "clinical_synthesis_not_harmonizable",
            "Selected trials did not satisfy the fail-closed harmonization contract.",
            recommended_decision=Decision.DEFER,
            details={"validation_error": str(exc)},
        )
    source_confidences = tuple(
        state.evidence_by_id[evidence_id].confidence
        for evidence_id in synthesis.source_evidence_ids
    )
    confidence = min((context.confidence, *source_confidences))
    evidence_context = {
        **dict(context.biological_context),
        "candidate_id": spec.candidate_id,
        "intervention_id": spec.intervention_id,
        "disease_id": spec.disease_id,
        "endpoint_mapping_id": spec.endpoint_mapping_id,
        "synthesis_id": spec.synthesis_id,
        "trial_ids": [item.trial_id for item in synthesis.studies],
        "endpoint_family": spec.endpoint_family,
    }
    synthesis_evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "benefit-risk-synthesis"),
        predicate="clinical_benefit_risk_synthesis_available",
        object_value=spec.endpoint_family,
        relation=EvidenceRelation.SUPPORTS,
        confidence=confidence,
        biological_context=evidence_context,
        metadata={
            "upstream_evidence_ids": synthesis.source_evidence_ids,
            "upstream_source_content_hashes": synthesis.source_content_hashes,
            "harmonization_policy_id": synthesis.harmonization_policy_id,
            "endpoint_mapping_id": synthesis.endpoint_mapping_id,
            "study_count": len(synthesis.studies),
            "pooling_method": synthesis.pooling_method,
            "pooling_performed": synthesis.pooling_performed,
            "benefit_risk_score_computed": False,
            "clinical_acceptability_inferred": False,
        },
    )
    promoted_synthesis = replace(
        synthesis,
        supporting_evidence=(
            *synthesis.supporting_evidence,
            synthesis_evidence.evidence_id,
        ),
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "benefit-risk-synthesis"),
        stage=outcome.request.stage,
        subject=candidate.name,
        predicate="clinical_benefit_risk_synthesis_available",
        object_value=spec.endpoint_family,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(synthesis_evidence.evidence_id,),
        confidence=confidence,
        resolution_rationale=(
            "The claim covers synthesis availability, not favorable benefit-risk "
            "or clinical acceptability."
        ),
        biological_context=evidence_context,
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="clinical_benefit_risk_synthesis_promoted",
        message=(
            "Source-disjoint trial effects and serious-event risks were harmonized "
            "descriptively without pooling or acceptability inference."
        ),
        evidence_drafts=(synthesis_evidence,),
        claim_updates=(claim,),
        benefit_risk_synthesis_updates=(promoted_synthesis,),
        details={
            "synthesis_id": synthesis.synthesis_id,
            "trial_ids": [item.trial_id for item in synthesis.studies],
            "source_content_hashes": synthesis.source_content_hashes,
            "pooling_performed": False,
            "clinical_acceptability_inferred": False,
        },
    )


def _map_ema(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    mapper_id = "ema_regulatory_status_v1"
    if outcome.request.stage is not Stage.REGULATORY_POSTMARKET:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ema_stage_unsupported",
            "EMA status promotion is limited to regulatory/postmarket review.",
        )
    candidate_id = context.candidate_id
    candidate = (
        state.candidates_by_id.get(candidate_id)
        if isinstance(candidate_id, str)
        else None
    )
    matching_interventions = (
        tuple(item for item in state.interventions if item.candidate_id == candidate_id)
        if isinstance(candidate_id, str)
        else ()
    )
    intervention = (
        matching_interventions[0] if len(matching_interventions) == 1 else None
    )
    disease = (
        state.diseases_by_id.get(intervention.disease_id)
        if intervention is not None
        else None
    )
    if (
        candidate is None
        or intervention is None
        or disease is None
        or intervention.candidate_id != candidate.candidate_id
        or candidate.attributes.get("disease_id") != intervention.disease_id
        or context.candidate_name is None
        or context.modality is None
        or _normalized(context.subject) != _normalized(intervention.name)
        or _normalized(context.candidate_name) != _normalized(candidate.name)
        or _normalized(context.modality) != _normalized(intervention.modality)
        or (
            context.biological_context.get("disease_id") is not None
            and context.biological_context.get("disease_id") != intervention.disease_id
        )
        or (
            context.biological_context.get("intervention_id") is not None
            and context.biological_context.get("intervention_id")
            != intervention.intervention_id
        )
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ema_intervention_context_invalid",
            "EMA promotion requires the accepted candidate and clinical intervention.",
        )
    payload = outcome.payload
    requested_query = _text(outcome.request.arguments.get("query"))
    if (
        requested_query is None
        or _normalized(requested_query) != _normalized(context.subject)
        or _normalized(requested_query) != _normalized(intervention.name)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ema_asset_context_mismatch",
            "EMA lookup query does not match the promotion subject.",
        )
    status = _text(payload.get("status"))
    if payload.get("found") is not True or status is None:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "ema_regulatory_match_unresolved",
            "No matched EMA medicine status can be promoted.",
            recommended_decision=Decision.DEFER,
        )
    asset = _text(payload.get("asset"))
    inn = _text(payload.get("inn"))
    if not (
        (asset is not None and _source_text_matches(requested_query, asset))
        or (inn is not None and _source_text_matches(requested_query, inn))
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ema_source_identity_mismatch",
            "EMA source identity does not match the accepted intervention.",
        )
    normalized_status = _normalized(status)
    if any(
        phrase in normalized_status for phrase in ("not authorised", "not authorized")
    ):
        recommended = Decision.DEFER
    elif any(word in normalized_status for word in ("revoked", "withdrawn", "refused")):
        recommended = Decision.KILL
    elif "suspend" in normalized_status:
        recommended = Decision.HOLD
    elif any(
        word in normalized_status
        for word in ("authorised", "authorized", "valid", "approved")
    ):
        recommended = Decision.ADVANCE
    else:
        recommended = Decision.DEFER
    evidence_context = {
        **dict(context.biological_context),
        "candidate_id": candidate.candidate_id,
        "intervention_id": intervention.intervention_id,
        "disease_id": intervention.disease_id,
    }
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "regulatory-status"),
        predicate="regulatory_status_assessed",
        object_value=status,
        relation=EvidenceRelation.SUPPORTS,
        confidence=context.confidence,
        biological_context=evidence_context,
        metadata={
            "asset": asset,
            "inn": inn,
            "marketing_authorisation_date": payload.get("ma_date"),
            "withdrawal_revocation_date": payload.get("withdrawal_revocation_date"),
            "suspension_date": payload.get("suspension_date"),
        },
    )
    claim = ScientificClaim(
        claim_id=_claim_id(outcome, "regulatory-status"),
        stage=outcome.request.stage,
        subject=context.subject,
        predicate="regulatory_status_assessed",
        object_value=status,
        disposition=ClaimDisposition.SUPPORTED,
        supporting_evidence=(evidence.evidence_id,),
        confidence=context.confidence,
        biological_context=evidence_context,
    )
    new_bindings = {
        key: value
        for key, value in (
            ("ema_asset", asset),
            ("ema_inn", inn),
            ("ema_product_url", _text(payload.get("url"))),
        )
        if value is not None
    }
    conflicting_namespaces = [
        namespace
        for namespace, value in new_bindings.items()
        if namespace in intervention.identifiers
        and intervention.identifiers[namespace] != value
    ]
    if conflicting_namespaces:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "ema_intervention_identity_rebound",
            "EMA identifiers would rebind an accepted intervention namespace.",
            details={"conflicting_namespaces": sorted(conflicting_namespaces)},
        )
    updated_intervention = InterventionRecord(
        intervention_id=intervention.intervention_id,
        name=intervention.name,
        candidate_id=intervention.candidate_id,
        disease_id=intervention.disease_id,
        modality=intervention.modality,
        stage=outcome.request.stage,
        identifiers={**dict(intervention.identifiers), **new_bindings},
        supporting_evidence=tuple(
            dict.fromkeys((*intervention.supporting_evidence, evidence.evidence_id))
        ),
        attributes={
            **dict(intervention.attributes),
            "ema_status": status,
            "ema_marketing_authorisation_date": payload.get("ma_date"),
            "ema_withdrawal_revocation_date": payload.get("withdrawal_revocation_date"),
            "ema_suspension_date": payload.get("suspension_date"),
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="ema_regulatory_status_promoted",
        message="Matched EMA medicine status was promoted as an assessed status claim.",
        evidence_drafts=(evidence,),
        claim_updates=(claim,),
        intervention_updates=(updated_intervention,),
        recommended_decision=recommended,
        details={
            "normalized_status": normalized_status,
            "intervention_id": intervention.intervention_id,
            "ema_namespaces_added": sorted(new_bindings),
        },
    )


def _map_boltz(
    state: ProgramState,
    outcome: ToolOutcome,
    context: PromotionContext,
) -> PromotionResult:
    del state
    mapper_id = "boltz_contextual_binding_v1"
    if outcome.request.stage not in {
        Stage.CANDIDATE_GENERATION,
        Stage.LEAD_OPTIMIZATION,
        Stage.PRECLINICAL_VALIDATION,
    }:
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "boltz_stage_unsupported",
            "Boltz binding promotion is unsupported at this stage.",
        )
    payload = outcome.payload
    if payload.get("status") != "predicted":
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.ABSTAINED,
            "structured_sfm_payload_required",
            "Only structured live Boltz predictions can enter the evidence ledger.",
            recommended_decision=Decision.DEFER,
        )
    target = _text(payload.get("target"))
    ligand = _text(payload.get("ligand"))
    service_confidence = _probability(payload.get("confidence"))
    affinity = _number(payload.get("affinity"))
    iptm = _probability(payload.get("iptm"))
    requested_spec = _text(outcome.request.arguments.get("spec"))
    requested_target: str | None = None
    requested_ligand: str | None = None
    if requested_spec is not None and "|" in requested_spec:
        requested_target, requested_ligand = (
            item.strip() for item in requested_spec.split("|", 1)
        )
    if (
        target is None
        or ligand is None
        or not requested_target
        or not requested_ligand
        or service_confidence is None
        or (affinity is None and iptm is None)
        or _normalized(target) != _normalized(context.object_value)
        or _normalized(target) != _normalized(requested_target)
        or _normalized(ligand) != _normalized(requested_ligand)
    ):
        return _empty_result(
            mapper_id,
            outcome,
            PromotionStatus.REJECTED,
            "boltz_payload_invalid",
            "Boltz payload lacks a matched target, ligand, confidence, or prediction value.",
        )
    evidence = _draft(
        outcome,
        context,
        evidence_id=_evidence_id(outcome, "predicted-binding"),
        predicate="predicted_target_binding",
        object_value=target,
        relation=EvidenceRelation.CONTEXTUALIZES,
        confidence=min(context.confidence, service_confidence),
        metadata={
            "ligand": ligand,
            "affinity": affinity,
            "affinity_units": payload.get("affinity_units"),
            "iptm": iptm,
            "service_confidence": service_confidence,
            "soft_prefilter_only": True,
        },
    )
    return PromotionResult(
        mapper_id=mapper_id,
        request_id=outcome.request_id,
        status=PromotionStatus.PROMOTED,
        code="boltz_prediction_contextualized",
        message="Boltz prediction was retained as contextual soft evidence only.",
        evidence_drafts=(evidence,),
        details={"soft_prefilter_only": True},
    )


def build_default_semantic_mapper_registry(
    *,
    target_association_minimum_score: float,
) -> SemanticMapperRegistry:
    """Build conservative mappings; the target threshold must be supplied explicitly."""

    _require_probability(
        target_association_minimum_score,
        "target_association_minimum_score",
    )
    registry = SemanticMapperRegistry()
    registry.register(
        tool_id="pinned_evidence",
        operation="disease_unmet_need",
        mapper_id="pinned_disease_unmet_need_v1",
        mapper=_map_pinned_disease_unmet_need,
    )
    registry.register(
        tool_id="pinned_evidence",
        operation="candidate_functional_effect",
        mapper_id="pinned_candidate_functional_effect_v1",
        mapper=_map_pinned_candidate_functional_effect,
    )
    registry.register(
        tool_id="pinned_evidence",
        operation="clinical_trial_design",
        mapper_id="pinned_clinical_trial_design_v1",
        mapper=_map_pinned_clinical_trial_design,
    )
    registry.register(
        tool_id="pinned_evidence",
        operation="clinical_trial_disposition",
        mapper_id="pinned_clinical_trial_disposition_v1",
        mapper=_map_pinned_clinical_trial_disposition,
    )
    registry.register(
        tool_id="clinical_synthesis",
        operation="register_endpoint_mapping",
        mapper_id="clinical_endpoint_mapping_v1",
        mapper=_map_clinical_endpoint_mapping,
    )
    registry.register(
        tool_id="clinical_synthesis",
        operation="harmonize_benefit_risk",
        mapper_id="clinical_benefit_risk_synthesis_v1",
        mapper=_map_clinical_benefit_risk_synthesis,
    )
    registry.register(
        tool_id="opentargets",
        operation="disease_profile",
        mapper_id="opentargets_disease_context_v1",
        mapper=_map_opentargets_disease,
    )
    registry.register(
        tool_id="opentargets",
        operation="target_disease_association",
        mapper_id="opentargets_target_disease_v1",
        mapper=_map_opentargets(float(target_association_minimum_score)),
    )
    registry.register(
        tool_id="chembl",
        operation="molecule_mechanism_profile",
        mapper_id="chembl_modality_mechanism_v1",
        mapper=_map_chembl_modality,
    )
    registry.register(
        tool_id="chembl",
        operation="molecule_target_mechanism_profile",
        mapper_id="chembl_target_modality_continuity_v1",
        mapper=_map_chembl_target_modality,
    )
    registry.register(
        tool_id="chembl",
        operation="molecule",
        mapper_id="chembl_candidate_identity_v1",
        mapper=_map_chembl_molecule,
    )
    registry.register(
        tool_id="chembl",
        operation="target_activity_count",
        mapper_id="chembl_preclinical_activity_context_v1",
        mapper=_map_chembl_activity_context,
    )
    registry.register(
        tool_id="molprops",
        operation="properties",
        mapper_id="rdkit_developability_v1",
        mapper=_map_molprops,
    )
    registry.register(
        tool_id="ctgov",
        operation="search_trials",
        mapper_id="ctgov_clinical_evidence_v1",
        mapper=_map_ctgov_trials,
    )
    registry.register(
        tool_id="ema",
        operation="lookup",
        mapper_id="ema_regulatory_status_v1",
        mapper=_map_ema,
    )
    registry.register(
        tool_id="boltz2",
        operation="predict_binding",
        mapper_id="boltz_contextual_binding_v1",
        mapper=_map_boltz,
    )
    return registry
