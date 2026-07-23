"""Reviewer-approved endpoint ontology mappings bound to clinical ledgers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from .models import (
    ClinicalEndpointBindingRecord,
    ClinicalEndpointMappingRecord,
    EvidenceRelation,
    ProgramState,
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _require_instance,
    _require_text,
    to_primitive,
)


CLINICAL_ENDPOINT_MAPPING_SPEC_SCHEMA_VERSION = (
    "adds.clinical-endpoint-mapping-spec.v1"
)
_ENDPOINT_FAMILY_ID = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_MAPPING_METADATA_FIELDS = frozenset({"review_note", "review_protocol_id"})


class ClinicalEndpointMappingError(ValueError):
    """Raised when a reviewed mapping cannot bind exactly to clinical records."""


@dataclass(frozen=True, slots=True)
class ClinicalEndpointSelection(SerializableRecord):
    """Exact endpoint and safety identities selected from one trial design."""

    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str

    def __post_init__(self) -> None:
        for field_name in ("trial_id", "design_id", "endpoint_id", "safety_id"):
            _require_text(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalEndpointOntology(SerializableRecord):
    """Reviewer-declared ontology identity; no authority lookup is implied."""

    system: str
    version: str
    code: str
    label: str

    def __post_init__(self) -> None:
        for field_name in ("system", "version", "code", "label"):
            _require_text(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalEndpointMappingReview(SerializableRecord):
    """Human approval identity and timestamp for one endpoint mapping."""

    status: str
    reviewer_id: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.status, "status")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_instance(self.reviewed_at, datetime, "reviewed_at")
        if self.status != "approved":
            raise ValueError("mapping review status must be approved")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ClinicalEndpointMappingSpec(SerializableRecord):
    """Reviewed endpoint-family declaration containing identities, not measurements."""

    mapping_id: str
    portfolio_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_family_id: str
    endpoint_family_label: str
    ontology: ClinicalEndpointOntology
    effect_measure: str
    favorable_direction: str
    safety_measure: str
    bindings: tuple[ClinicalEndpointSelection, ...]
    review: ClinicalEndpointMappingReview
    stage: Stage = Stage.REGULATORY_POSTMARKET
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_instance(self.ontology, ClinicalEndpointOntology, "ontology")
        _require_instance(self.review, ClinicalEndpointMappingReview, "review")
        for field_name in (
            "mapping_id",
            "portfolio_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_family_id",
            "endpoint_family_label",
            "effect_measure",
            "favorable_direction",
            "safety_measure",
        ):
            _require_text(getattr(self, field_name), field_name)
        if _ENDPOINT_FAMILY_ID.fullmatch(self.endpoint_family_id) is None:
            raise ValueError("endpoint_family_id must be a canonical snake-case id")
        if self.stage is not Stage.REGULATORY_POSTMARKET:
            raise ValueError("endpoint mapping is limited to regulatory_postmarket")
        if self.effect_measure != "hazard_ratio":
            raise ValueError("v1 supports only hazard_ratio effect estimates")
        if self.favorable_direction != "lower_is_better":
            raise ValueError("hazard_ratio requires lower_is_better direction")
        if self.safety_measure != "serious_adverse_event_risk_difference":
            raise ValueError("unsupported safety_measure")
        bindings = tuple(self.bindings)
        object.__setattr__(self, "bindings", bindings)
        if len(bindings) < 2:
            raise ValueError("bindings must contain at least two trials")
        for binding in bindings:
            _require_instance(binding, ClinicalEndpointSelection, "bindings item")
        for label, values in (
            ("trial ids", tuple(item.trial_id for item in bindings)),
            ("design ids", tuple(item.design_id for item in bindings)),
            ("endpoint ids", tuple(item.endpoint_id for item in bindings)),
            ("safety ids", tuple(item.safety_id for item in bindings)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"bindings must use unique {label}")
        metadata = dict(self.metadata)
        unknown_metadata = set(metadata) - _MAPPING_METADATA_FIELDS
        if unknown_metadata:
            raise ValueError(
                "mapping metadata contains unsupported fields: "
                + ", ".join(sorted(unknown_metadata))
            )
        for key, value in metadata.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"mapping metadata {key} must be non-empty text")
        object.__setattr__(self, "metadata", _freeze_mapping(metadata, "metadata"))


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalEndpointMappingError(f"{path} must be an object")
    return dict(value)


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClinicalEndpointMappingError(f"{path} must be an array")
    return tuple(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClinicalEndpointMappingError(f"{path} must be a non-empty string")
    return value.strip()


def _exact_fields(data: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(data) != expected:
        raise ClinicalEndpointMappingError(
            f"{path} must contain exactly {sorted(expected)}"
        )


def _reviewed_at(value: Any, path: str) -> datetime:
    text = _text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClinicalEndpointMappingError(f"{path} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClinicalEndpointMappingError(f"{path} must be timezone-aware")
    return parsed


def clinical_endpoint_mapping_spec_from_dict(
    value: Any,
    path: str = "clinical_endpoint_mapping_spec",
) -> ClinicalEndpointMappingSpec:
    """Parse one strict reviewer-approved endpoint mapping declaration."""

    data = _mapping(value, path)
    expected = {
        "schema_version",
        "mapping_id",
        "portfolio_id",
        "candidate_id",
        "intervention_id",
        "disease_id",
        "endpoint_family_id",
        "endpoint_family_label",
        "ontology",
        "effect_measure",
        "favorable_direction",
        "safety_measure",
        "bindings",
        "review",
        "stage",
        "metadata",
    }
    _exact_fields(data, expected, path)
    if data["schema_version"] != CLINICAL_ENDPOINT_MAPPING_SPEC_SCHEMA_VERSION:
        raise ClinicalEndpointMappingError(f"{path}.schema_version is unsupported")
    ontology = _mapping(data["ontology"], f"{path}.ontology")
    _exact_fields(ontology, {"system", "version", "code", "label"}, f"{path}.ontology")
    review = _mapping(data["review"], f"{path}.review")
    _exact_fields(review, {"status", "reviewer_id", "reviewed_at"}, f"{path}.review")
    bindings: list[ClinicalEndpointSelection] = []
    for index, value in enumerate(_sequence(data["bindings"], f"{path}.bindings")):
        binding = _mapping(value, f"{path}.bindings[{index}]")
        _exact_fields(
            binding,
            {"trial_id", "design_id", "endpoint_id", "safety_id"},
            f"{path}.bindings[{index}]",
        )
        bindings.append(
            ClinicalEndpointSelection(
                trial_id=_text(binding["trial_id"], f"{path}.bindings[{index}].trial_id"),
                design_id=_text(binding["design_id"], f"{path}.bindings[{index}].design_id"),
                endpoint_id=_text(
                    binding["endpoint_id"], f"{path}.bindings[{index}].endpoint_id"
                ),
                safety_id=_text(binding["safety_id"], f"{path}.bindings[{index}].safety_id"),
            )
        )
    try:
        stage = Stage(data["stage"])
    except (TypeError, ValueError) as exc:
        raise ClinicalEndpointMappingError(f"{path}.stage is invalid") from exc
    return ClinicalEndpointMappingSpec(
        mapping_id=_text(data["mapping_id"], f"{path}.mapping_id"),
        portfolio_id=_text(data["portfolio_id"], f"{path}.portfolio_id"),
        candidate_id=_text(data["candidate_id"], f"{path}.candidate_id"),
        intervention_id=_text(data["intervention_id"], f"{path}.intervention_id"),
        disease_id=_text(data["disease_id"], f"{path}.disease_id"),
        endpoint_family_id=_text(
            data["endpoint_family_id"], f"{path}.endpoint_family_id"
        ),
        endpoint_family_label=_text(
            data["endpoint_family_label"], f"{path}.endpoint_family_label"
        ),
        ontology=ClinicalEndpointOntology(
            system=_text(ontology["system"], f"{path}.ontology.system"),
            version=_text(ontology["version"], f"{path}.ontology.version"),
            code=_text(ontology["code"], f"{path}.ontology.code"),
            label=_text(ontology["label"], f"{path}.ontology.label"),
        ),
        effect_measure=_text(data["effect_measure"], f"{path}.effect_measure"),
        favorable_direction=_text(
            data["favorable_direction"], f"{path}.favorable_direction"
        ),
        safety_measure=_text(data["safety_measure"], f"{path}.safety_measure"),
        bindings=tuple(bindings),
        review=ClinicalEndpointMappingReview(
            status=_text(review["status"], f"{path}.review.status"),
            reviewer_id=_text(review["reviewer_id"], f"{path}.review.reviewer_id"),
            reviewed_at=_reviewed_at(
                review["reviewed_at"], f"{path}.review.reviewed_at"
            ),
        ),
        stage=stage,
        metadata=_mapping(data["metadata"], f"{path}.metadata"),
    )


def clinical_endpoint_mapping_spec_to_dict(
    spec: ClinicalEndpointMappingSpec,
) -> dict[str, Any]:
    """Return the canonical tool payload for a reviewed mapping declaration."""

    _require_instance(spec, ClinicalEndpointMappingSpec, "spec")
    value = to_primitive(spec)
    if not isinstance(value, dict):
        raise TypeError("serialized endpoint mapping spec must be an object")
    return {"schema_version": CLINICAL_ENDPOINT_MAPPING_SPEC_SCHEMA_VERSION, **value}


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _resolve_binding(
    state: ProgramState,
    spec: ClinicalEndpointMappingSpec,
    selection: ClinicalEndpointSelection,
) -> ClinicalEndpointBindingRecord:
    trial = state.trials_by_id.get(selection.trial_id)
    design = state.trial_designs_by_id.get(selection.design_id)
    if trial is None or design is None:
        raise ClinicalEndpointMappingError("selected trial or design is absent")
    if (
        design.trial_id != selection.trial_id
        or trial.intervention_id != spec.intervention_id
        or trial.disease_id != spec.disease_id
        or design.intervention_id != spec.intervention_id
        or design.disease_id != spec.disease_id
    ):
        raise ClinicalEndpointMappingError("selected trial/design identity is rebound")
    endpoints = tuple(
        item for item in design.endpoints if item.endpoint_id == selection.endpoint_id
    )
    safety_records = tuple(
        item for item in design.safety_records if item.safety_id == selection.safety_id
    )
    if len(endpoints) != 1 or len(safety_records) != 1:
        raise ClinicalEndpointMappingError(
            "selected endpoint or safety record is not unique"
        )
    endpoint = endpoints[0]
    safety = safety_records[0]
    if (
        _normalized(endpoint.outcome_type) != "primary"
        or _normalized(endpoint.reporting_status) != "posted"
        or _normalized(safety.event_category) != "serious"
        or _normalized(safety.reporting_status) != "posted"
    ):
        raise ClinicalEndpointMappingError(
            "selected endpoint/safety record is not posted primary data"
        )
    analysis = _mapping(endpoint.attributes.get("analysis"), "endpoint.analysis")
    parameter_type = _normalized(
        _text(analysis.get("parameter_type"), "endpoint.analysis.parameter_type")
    )
    if parameter_type not in {"hazard ratio", "hazard ratio (hr)"}:
        raise ClinicalEndpointMappingError(
            "selected endpoint does not report the declared hazard ratio"
        )
    source_evidence_ids = tuple(sorted(set(design.supporting_evidence)))
    source_content_hashes: set[str] = set()
    for evidence_id in source_evidence_ids:
        evidence = state.evidence_by_id.get(evidence_id)
        if evidence is None:
            raise ClinicalEndpointMappingError(
                f"selected design references missing evidence: {evidence_id}"
            )
        if evidence.relation is not EvidenceRelation.SUPPORTS:
            raise ClinicalEndpointMappingError(
                f"selected design references non-support evidence: {evidence_id}"
            )
        if not evidence.is_visible_at(state.as_of_date):
            raise ClinicalEndpointMappingError(
                f"selected design references evidence after cutoff: {evidence_id}"
            )
        digest = evidence.source.content_hash
        if not isinstance(digest, str) or len(digest) != 64 or digest != digest.lower():
            raise ClinicalEndpointMappingError(
                f"selected design evidence is not source-pinned: {evidence_id}"
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ClinicalEndpointMappingError(
                f"selected design evidence is not source-pinned: {evidence_id}"
            ) from exc
        source_content_hashes.add(digest)
    if not source_evidence_ids or not source_content_hashes:
        raise ClinicalEndpointMappingError("selected design lacks source-pinned support")
    fingerprint_context = {
        "trial_id": selection.trial_id,
        "design_id": selection.design_id,
        "source_evidence_ids": source_evidence_ids,
    }
    return ClinicalEndpointBindingRecord(
        trial_id=selection.trial_id,
        design_id=selection.design_id,
        endpoint_id=selection.endpoint_id,
        safety_id=selection.safety_id,
        endpoint_fingerprint_sha256=_sha256_json(
            {**fingerprint_context, "endpoint": endpoint}
        ),
        safety_fingerprint_sha256=_sha256_json(
            {**fingerprint_context, "safety": safety}
        ),
        source_evidence_ids=source_evidence_ids,
        source_content_hashes=tuple(sorted(source_content_hashes)),
    )


def compile_clinical_endpoint_mapping(
    state: ProgramState,
    spec: ClinicalEndpointMappingSpec,
) -> ClinicalEndpointMappingRecord:
    """Bind one approved mapping to exact committed clinical records."""

    _require_instance(state, ProgramState, "state")
    _require_instance(spec, ClinicalEndpointMappingSpec, "spec")
    candidate = state.candidates_by_id.get(spec.candidate_id)
    intervention = state.interventions_by_id.get(spec.intervention_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if candidate is None or intervention is None or disease is None:
        raise ClinicalEndpointMappingError(
            "candidate, intervention, and disease must exist before mapping"
        )
    if (
        intervention.candidate_id != candidate.candidate_id
        or intervention.disease_id != disease.disease_id
        or candidate.attributes.get("disease_id") != disease.disease_id
        or _normalized(disease.name) != _normalized(state.disease)
    ):
        raise ClinicalEndpointMappingError(
            "candidate/intervention/disease identity is not continuous"
        )
    if spec.mapping_id in state.clinical_endpoint_mappings_by_id:
        raise ClinicalEndpointMappingError("mapping_id already exists in the ledger")
    if spec.review.reviewed_at.date() > state.as_of_date:
        raise ClinicalEndpointMappingError("mapping review occurred after state cutoff")
    bindings = tuple(_resolve_binding(state, spec, item) for item in spec.bindings)
    source_evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for binding in bindings
                for evidence_id in binding.source_evidence_ids
            }
        )
    )
    source_content_hashes = tuple(
        sorted(
            {
                digest
                for binding in bindings
                for digest in binding.source_content_hashes
            }
        )
    )
    review_cutoff = spec.review.reviewed_at.date()
    if any(
        not state.evidence_by_id[evidence_id].is_visible_at(review_cutoff)
        for evidence_id in source_evidence_ids
    ):
        raise ClinicalEndpointMappingError(
            "mapping review predates selected evidence availability"
        )
    return ClinicalEndpointMappingRecord(
        mapping_id=spec.mapping_id,
        portfolio_id=spec.portfolio_id,
        candidate_id=spec.candidate_id,
        intervention_id=spec.intervention_id,
        disease_id=spec.disease_id,
        endpoint_family_id=spec.endpoint_family_id,
        endpoint_family_label=spec.endpoint_family_label,
        ontology_system=spec.ontology.system,
        ontology_version=spec.ontology.version,
        ontology_code=spec.ontology.code,
        ontology_label=spec.ontology.label,
        effect_measure=spec.effect_measure,
        favorable_direction=spec.favorable_direction,
        safety_measure=spec.safety_measure,
        bindings=bindings,
        review_status=spec.review.status,
        reviewer_id=spec.review.reviewer_id,
        reviewed_at=spec.review.reviewed_at,
        source_evidence_ids=source_evidence_ids,
        source_content_hashes=source_content_hashes,
        stage=spec.stage,
        supporting_evidence=source_evidence_ids,
        identifiers={
            "canonical": spec.mapping_id,
            "endpoint_ontology": f"{spec.ontology.system}:{spec.ontology.code}",
        },
        attributes={
            "selection_spec": [to_primitive(item) for item in spec.bindings],
            "spec_metadata": dict(spec.metadata),
            "ontology_authority_verified": False,
            "ontology_identity_reviewer_declared": True,
            "automatic_endpoint_mapping_performed": False,
            "source_measurements_supplied_by_mapping_spec": False,
        },
    )


def validate_clinical_endpoint_mapping(
    state: ProgramState,
    record: ClinicalEndpointMappingRecord,
) -> tuple[str, ...]:
    """Recompile a mapping and validate its single derived approval event."""

    _require_instance(state, ProgramState, "state")
    _require_instance(record, ClinicalEndpointMappingRecord, "record")
    raw_selections = record.attributes.get("selection_spec")
    if not isinstance(raw_selections, Sequence) or isinstance(
        raw_selections, (str, bytes)
    ):
        return ("mapping_selection_spec_missing",)
    if any(not isinstance(item, Mapping) for item in raw_selections):
        return ("mapping_selection_spec_invalid",)
    try:
        selections = tuple(
            ClinicalEndpointSelection(
                trial_id=_text(item.get("trial_id"), "trial_id"),
                design_id=_text(item.get("design_id"), "design_id"),
                endpoint_id=_text(item.get("endpoint_id"), "endpoint_id"),
                safety_id=_text(item.get("safety_id"), "safety_id"),
            )
            for item in raw_selections
        )
        spec = ClinicalEndpointMappingSpec(
            mapping_id=record.mapping_id,
            portfolio_id=record.portfolio_id,
            candidate_id=record.candidate_id,
            intervention_id=record.intervention_id,
            disease_id=record.disease_id,
            endpoint_family_id=record.endpoint_family_id,
            endpoint_family_label=record.endpoint_family_label,
            ontology=ClinicalEndpointOntology(
                system=record.ontology_system,
                version=record.ontology_version,
                code=record.ontology_code,
                label=record.ontology_label,
            ),
            effect_measure=record.effect_measure,
            favorable_direction=record.favorable_direction,
            safety_measure=record.safety_measure,
            bindings=selections,
            review=ClinicalEndpointMappingReview(
                status=record.review_status,
                reviewer_id=record.reviewer_id,
                reviewed_at=record.reviewed_at,
            ),
            stage=record.stage,
            metadata=_mapping(record.attributes.get("spec_metadata", {}), "spec_metadata"),
        )
        state_without_record = replace(
            state,
            clinical_endpoint_mappings=tuple(
                item
                for item in state.clinical_endpoint_mappings
                if item.mapping_id != record.mapping_id
            ),
        )
        rebuilt = compile_clinical_endpoint_mapping(state_without_record, spec)
    except (ClinicalEndpointMappingError, TypeError, ValueError):
        return ("mapping_recompile_failed",)
    normalized = replace(record, supporting_evidence=rebuilt.supporting_evidence)
    if normalized != rebuilt:
        return ("mapping_recompiled_record_mismatch",)
    source_count = len(rebuilt.supporting_evidence)
    if record.supporting_evidence[:source_count] != rebuilt.supporting_evidence:
        return ("mapping_supporting_evidence_layout_invalid",)
    derived_ids = record.supporting_evidence[source_count:]
    if len(derived_ids) != 1:
        return (
            "derived_mapping_evidence_missing"
            if not derived_ids
            else "derived_mapping_evidence_count_invalid",
        )
    evidence = state.evidence_by_id.get(derived_ids[0])
    candidate = state.candidates_by_id.get(record.candidate_id)
    if evidence is None or candidate is None:
        return ("derived_mapping_evidence_binding_invalid",)
    context = to_primitive(evidence.biological_context)
    metadata = to_primitive(evidence.metadata)
    trial_ids = [item.trial_id for item in record.bindings]
    if (
        evidence.stage is not record.stage
        or evidence.relation is not EvidenceRelation.SUPPORTS
        or not evidence.is_visible_at(state.as_of_date)
        or _normalized(evidence.subject) != _normalized(candidate.name)
        or evidence.predicate != "clinical_endpoint_mapping_approved"
        or evidence.object_value != record.endpoint_family_id
        or not isinstance(context, dict)
        or context.get("candidate_id") != record.candidate_id
        or context.get("intervention_id") != record.intervention_id
        or context.get("disease_id") != record.disease_id
        or context.get("mapping_id") != record.mapping_id
        or context.get("portfolio_id") != record.portfolio_id
        or context.get("endpoint_family_id") != record.endpoint_family_id
        or context.get("trial_ids") != trial_ids
    ):
        return ("derived_mapping_evidence_binding_invalid",)
    if (
        not isinstance(metadata, dict)
        or metadata.get("upstream_evidence_ids") != list(record.source_evidence_ids)
        or metadata.get("upstream_source_content_hashes")
        != list(record.source_content_hashes)
        or metadata.get("ontology")
        != {
            "system": record.ontology_system,
            "version": record.ontology_version,
            "code": record.ontology_code,
            "label": record.ontology_label,
        }
        or metadata.get("review_status") != "approved"
        or metadata.get("reviewer_id") != record.reviewer_id
        or metadata.get("reviewed_at") != record.reviewed_at.isoformat()
        or metadata.get("binding_count") != len(record.bindings)
        or metadata.get("automatic_endpoint_mapping_performed") is not False
        or metadata.get("ontology_authority_verified") is not False
    ):
        return ("derived_mapping_evidence_metadata_invalid",)
    return ()
