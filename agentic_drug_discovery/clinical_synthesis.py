"""Deterministic, provenance-preserving cross-trial benefit-risk synthesis."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .clinical_endpoint_mapping import validate_clinical_endpoint_mapping
from .models import (
    BenefitRiskSynthesisRecord,
    EvidenceRelation,
    ProgramState,
    SerializableRecord,
    Stage,
    StudyBenefitRiskRecord,
    TrialArmRole,
    _freeze_mapping,
    _require_instance,
    _require_text,
    to_primitive,
)


CLINICAL_SYNTHESIS_SPEC_SCHEMA_VERSION = (
    "adds.clinical-benefit-risk-synthesis-spec.v1"
)
CLINICAL_SYNTHESIS_POLICY_ID = "adds.descriptive-cross-trial-benefit-risk.v1"


class ClinicalSynthesisError(ValueError):
    """Raised when source records cannot satisfy the declared synthesis contract."""


@dataclass(frozen=True, slots=True)
class ClinicalStudySelection(SerializableRecord):
    """Explicit source-ledger selection for one trial in a synthesis."""

    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str

    def __post_init__(self) -> None:
        for field_name in ("trial_id", "design_id", "endpoint_id", "safety_id"):
            _require_text(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalSynthesisSpec(SerializableRecord):
    """Reviewed harmonization declaration; it contains no source measurements."""

    synthesis_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    effect_measure: str
    effect_measure_favorable_direction: str
    safety_measure: str
    harmonization_policy_id: str
    selections: tuple[ClinicalStudySelection, ...]
    stage: Stage = Stage.REGULATORY_POSTMARKET
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        for field_name in (
            "synthesis_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "effect_measure_favorable_direction",
            "safety_measure",
            "harmonization_policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        selections = tuple(self.selections)
        object.__setattr__(self, "selections", selections)
        if len(selections) < 2:
            raise ValueError("selections must contain at least two trials")
        for selection in selections:
            _require_instance(selection, ClinicalStudySelection, "selections item")
        for label, values in (
            ("trial ids", tuple(item.trial_id for item in selections)),
            ("design ids", tuple(item.design_id for item in selections)),
            ("endpoint ids", tuple(item.endpoint_id for item in selections)),
            ("safety ids", tuple(item.safety_id for item in selections)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"selections must use unique {label}")
        if self.stage is not Stage.REGULATORY_POSTMARKET:
            raise ValueError("clinical synthesis is limited to regulatory_postmarket")
        if self.harmonization_policy_id != CLINICAL_SYNTHESIS_POLICY_ID:
            raise ValueError("unsupported harmonization_policy_id")
        if self.effect_measure != "hazard_ratio":
            raise ValueError("v1 supports only hazard_ratio effect estimates")
        if self.effect_measure_favorable_direction != "lower_is_better":
            raise ValueError("hazard_ratio requires lower_is_better direction")
        if self.safety_measure != "serious_adverse_event_risk_difference":
            raise ValueError("unsupported safety_measure")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalSynthesisError(f"{field_name} must be an object")
    return dict(value)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClinicalSynthesisError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sequence(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClinicalSynthesisError(f"{field_name} must be an array")
    return tuple(value)


def _number(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        raise ClinicalSynthesisError(f"{field_name} must be numeric")
    try:
        result = float(value)
    except ValueError as exc:
        raise ClinicalSynthesisError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise ClinicalSynthesisError(f"{field_name} must be finite")
    return result


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def clinical_synthesis_spec_from_dict(
    value: Any,
    path: str = "clinical_synthesis_spec",
) -> ClinicalSynthesisSpec:
    """Parse one strict JSON-compatible synthesis declaration."""

    data = _mapping(value, path)
    expected = {
        "schema_version",
        "synthesis_id",
        "candidate_id",
        "intervention_id",
        "disease_id",
        "endpoint_mapping_id",
        "endpoint_family",
        "effect_measure",
        "effect_measure_favorable_direction",
        "safety_measure",
        "harmonization_policy_id",
        "selections",
        "stage",
        "metadata",
    }
    if set(data) != expected:
        raise ClinicalSynthesisError(f"{path} must contain exactly {sorted(expected)}")
    if data["schema_version"] != CLINICAL_SYNTHESIS_SPEC_SCHEMA_VERSION:
        raise ClinicalSynthesisError(f"{path}.schema_version is unsupported")
    selections = []
    for index, item in enumerate(_sequence(data["selections"], f"{path}.selections")):
        selection = _mapping(item, f"{path}.selections[{index}]")
        selection_fields = {"trial_id", "design_id", "endpoint_id", "safety_id"}
        if set(selection) != selection_fields:
            raise ClinicalSynthesisError(
                f"{path}.selections[{index}] must contain exactly "
                f"{sorted(selection_fields)}"
            )
        selections.append(
            ClinicalStudySelection(
                trial_id=_text(selection["trial_id"], "trial_id"),
                design_id=_text(selection["design_id"], "design_id"),
                endpoint_id=_text(selection["endpoint_id"], "endpoint_id"),
                safety_id=_text(selection["safety_id"], "safety_id"),
            )
        )
    try:
        stage = Stage(data["stage"])
    except (TypeError, ValueError) as exc:
        raise ClinicalSynthesisError(f"{path}.stage is invalid") from exc
    return ClinicalSynthesisSpec(
        synthesis_id=_text(data["synthesis_id"], f"{path}.synthesis_id"),
        candidate_id=_text(data["candidate_id"], f"{path}.candidate_id"),
        intervention_id=_text(
            data["intervention_id"], f"{path}.intervention_id"
        ),
        disease_id=_text(data["disease_id"], f"{path}.disease_id"),
        endpoint_mapping_id=_text(
            data["endpoint_mapping_id"], f"{path}.endpoint_mapping_id"
        ),
        endpoint_family=_text(
            data["endpoint_family"], f"{path}.endpoint_family"
        ),
        effect_measure=_text(data["effect_measure"], f"{path}.effect_measure"),
        effect_measure_favorable_direction=_text(
            data["effect_measure_favorable_direction"],
            f"{path}.effect_measure_favorable_direction",
        ),
        safety_measure=_text(data["safety_measure"], f"{path}.safety_measure"),
        harmonization_policy_id=_text(
            data["harmonization_policy_id"], f"{path}.harmonization_policy_id"
        ),
        selections=tuple(selections),
        stage=stage,
        metadata=_mapping(data["metadata"], f"{path}.metadata"),
    )


def clinical_synthesis_spec_to_dict(spec: ClinicalSynthesisSpec) -> dict[str, Any]:
    """Return the canonical tool payload for a reviewed synthesis declaration."""

    _require_instance(spec, ClinicalSynthesisSpec, "spec")
    value = to_primitive(spec)
    if not isinstance(value, dict):
        raise TypeError("serialized synthesis spec must be an object")
    return {"schema_version": CLINICAL_SYNTHESIS_SPEC_SCHEMA_VERSION, **value}


def _benefit_direction(lower: float, upper: float) -> str:
    if upper < 1.0:
        return "benefit"
    if lower > 1.0:
        return "harm"
    return "null_or_uncertain"


def _safety_direction(risk_difference: float) -> str:
    if math.isclose(risk_difference, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return "equal_observed_serious_event_risk"
    if risk_difference < 0:
        return "lower_observed_serious_event_risk"
    return "higher_observed_serious_event_risk"


def _study_record(
    state: ProgramState,
    spec: ClinicalSynthesisSpec,
    selection: ClinicalStudySelection,
) -> StudyBenefitRiskRecord:
    trial = state.trials_by_id.get(selection.trial_id)
    design = state.trial_designs_by_id.get(selection.design_id)
    if trial is None or design is None:
        raise ClinicalSynthesisError("selected trial or design is absent from the ledger")
    if (
        design.trial_id != selection.trial_id
        or trial.intervention_id != spec.intervention_id
        or trial.disease_id != spec.disease_id
        or design.intervention_id != spec.intervention_id
        or design.disease_id != spec.disease_id
    ):
        raise ClinicalSynthesisError("selected trial/design identity is rebound")
    endpoint_matches = tuple(
        item for item in design.endpoints if item.endpoint_id == selection.endpoint_id
    )
    safety_matches = tuple(
        item for item in design.safety_records if item.safety_id == selection.safety_id
    )
    if len(endpoint_matches) != 1 or len(safety_matches) != 1:
        raise ClinicalSynthesisError("selected endpoint or safety record is not unique")
    endpoint = endpoint_matches[0]
    safety = safety_matches[0]
    if (
        _normalized(endpoint.outcome_type) != "primary"
        or _normalized(endpoint.reporting_status) != "posted"
        or _normalized(safety.event_category) != "serious"
        or _normalized(safety.reporting_status) != "posted"
    ):
        raise ClinicalSynthesisError("selected endpoint/safety record is not posted primary data")
    analysis = _mapping(endpoint.attributes.get("analysis"), "endpoint.analysis")
    parameter_type = _normalized(
        _text(analysis.get("parameter_type"), "endpoint.analysis.parameter_type")
    )
    if parameter_type not in {"hazard ratio", "hazard ratio (hr)"}:
        raise ClinicalSynthesisError("selected endpoint does not report a hazard ratio")
    effect_estimate = _number(
        analysis.get("parameter_value"), "endpoint.analysis.parameter_value"
    )
    ci_percent = _number(
        analysis.get("confidence_interval_percent"),
        "endpoint.analysis.confidence_interval_percent",
    )
    ci_lower = _number(
        analysis.get("confidence_interval_lower"),
        "endpoint.analysis.confidence_interval_lower",
    )
    ci_upper = _number(
        analysis.get("confidence_interval_upper"),
        "endpoint.analysis.confidence_interval_upper",
    )
    if not 0 < ci_lower <= effect_estimate <= ci_upper:
        raise ClinicalSynthesisError("hazard-ratio confidence interval is invalid")
    arms_by_role = {item.role: item for item in design.arms}
    safety_by_role = {item.role: item for item in safety.arm_summaries}
    candidate_arm = arms_by_role.get(TrialArmRole.CANDIDATE)
    comparator_arm = arms_by_role.get(TrialArmRole.COMPARATOR)
    candidate_safety = safety_by_role.get(TrialArmRole.CANDIDATE)
    comparator_safety = safety_by_role.get(TrialArmRole.COMPARATOR)
    if any(
        item is None
        for item in (
            candidate_arm,
            comparator_arm,
            candidate_safety,
            comparator_safety,
        )
    ):
        raise ClinicalSynthesisError("candidate/comparator arm roles are incomplete")
    if candidate_arm is None or comparator_arm is None:
        raise ClinicalSynthesisError("candidate/comparator endpoint arms are incomplete")
    if candidate_safety is None or comparator_safety is None:
        raise ClinicalSynthesisError("candidate/comparator safety arms are incomplete")
    candidate_measurement = _mapping(
        candidate_arm.attributes.get("measurement"), "candidate_arm.measurement"
    )
    comparator_measurement = _mapping(
        comparator_arm.attributes.get("measurement"), "comparator_arm.measurement"
    )
    candidate_value = _number(candidate_measurement.get("value"), "candidate value")
    comparator_value = _number(
        comparator_measurement.get("value"), "comparator value"
    )
    candidate_risk = (
        candidate_safety.serious_num_affected
        / candidate_safety.serious_num_at_risk
    )
    comparator_risk = (
        comparator_safety.serious_num_affected
        / comparator_safety.serious_num_at_risk
    )
    risk_difference = candidate_risk - comparator_risk
    source_evidence_ids = tuple(sorted(set(design.supporting_evidence)))
    evidence_by_id = state.evidence_by_id
    source_hashes: set[str] = set()
    for evidence_id in source_evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            raise ClinicalSynthesisError(
                f"selected design references missing evidence: {evidence_id}"
            )
        if evidence.relation is not EvidenceRelation.SUPPORTS:
            raise ClinicalSynthesisError(
                f"selected design references non-support evidence: {evidence_id}"
            )
        if not evidence.is_visible_at(state.as_of_date):
            raise ClinicalSynthesisError(
                f"selected design references evidence after cutoff: {evidence_id}"
            )
        digest = evidence.source.content_hash
        if not isinstance(digest, str) or len(digest) != 64:
            raise ClinicalSynthesisError(
                f"selected design evidence is not source-pinned: {evidence_id}"
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ClinicalSynthesisError(
                f"selected design evidence is not source-pinned: {evidence_id}"
            ) from exc
        if digest != digest.lower():
            raise ClinicalSynthesisError(
                f"selected design evidence is not source-pinned: {evidence_id}"
            )
        source_hashes.add(digest)
    if not source_evidence_ids or not source_hashes:
        raise ClinicalSynthesisError("selected design lacks source-pinned support")
    study_record_id = f"{spec.synthesis_id}:study:{selection.trial_id}"
    endpoint_fingerprint = _sha256_json(
        {
            "trial_id": selection.trial_id,
            "design_id": selection.design_id,
            "endpoint": endpoint,
            "source_evidence_ids": source_evidence_ids,
        }
    )
    safety_fingerprint = _sha256_json(
        {
            "trial_id": selection.trial_id,
            "design_id": selection.design_id,
            "safety": safety,
            "source_evidence_ids": source_evidence_ids,
        }
    )
    return StudyBenefitRiskRecord(
        study_record_id=study_record_id,
        trial_id=selection.trial_id,
        design_id=selection.design_id,
        endpoint_id=selection.endpoint_id,
        safety_id=selection.safety_id,
        endpoint_family=spec.endpoint_family,
        effect_measure=spec.effect_measure,
        effect_estimate=effect_estimate,
        confidence_interval_percent=ci_percent,
        confidence_interval_lower=ci_lower,
        confidence_interval_upper=ci_upper,
        candidate_measurement=candidate_value,
        comparator_measurement=comparator_value,
        measurement_unit=endpoint.unit,
        endpoint_time_frame=endpoint.time_frame,
        safety_time_frame=safety.time_frame,
        candidate_serious_num_affected=candidate_safety.serious_num_affected,
        candidate_serious_num_at_risk=candidate_safety.serious_num_at_risk,
        comparator_serious_num_affected=comparator_safety.serious_num_affected,
        comparator_serious_num_at_risk=comparator_safety.serious_num_at_risk,
        candidate_serious_event_risk=candidate_risk,
        comparator_serious_event_risk=comparator_risk,
        serious_event_risk_difference=risk_difference,
        benefit_direction=_benefit_direction(ci_lower, ci_upper),
        safety_direction=_safety_direction(risk_difference),
        source_evidence_ids=source_evidence_ids,
        source_content_hashes=tuple(sorted(source_hashes)),
        stage=spec.stage,
        identifiers={
            "canonical": study_record_id,
            "endpoint_fingerprint_sha256": endpoint_fingerprint,
            "safety_fingerprint_sha256": safety_fingerprint,
        },
        attributes={
            "endpoint_name": endpoint.name,
            "endpoint_outcome_type": endpoint.outcome_type,
            "endpoint_reporting_status": endpoint.reporting_status,
            "effect_measure_favorable_direction": (
                spec.effect_measure_favorable_direction
            ),
            "endpoint_mapping_declared_by_spec": True,
            "endpoint_mapping_id": spec.endpoint_mapping_id,
            "automatic_endpoint_mapping_performed": False,
            "safety_event_category": safety.event_category,
            "safety_reporting_status": safety.reporting_status,
            "event_term_count": safety.event_term_count,
            "clinical_acceptability_inferred": False,
        },
    )


def compile_benefit_risk_synthesis(
    state: ProgramState,
    spec: ClinicalSynthesisSpec,
) -> BenefitRiskSynthesisRecord:
    """Compile selected trial records while retaining exact source-level values."""

    _require_instance(state, ProgramState, "state")
    _require_instance(spec, ClinicalSynthesisSpec, "spec")
    candidate = state.candidates_by_id.get(spec.candidate_id)
    intervention = state.interventions_by_id.get(spec.intervention_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if candidate is None or intervention is None or disease is None:
        raise ClinicalSynthesisError(
            "candidate, intervention, and disease must exist before synthesis"
        )
    if (
        intervention.candidate_id != candidate.candidate_id
        or intervention.disease_id != disease.disease_id
        or candidate.attributes.get("disease_id") != disease.disease_id
        or _normalized(disease.name) != _normalized(state.disease)
    ):
        raise ClinicalSynthesisError(
            "candidate/intervention/disease identity is not continuous"
        )
    existing = state.benefit_risk_syntheses_by_id.get(spec.synthesis_id)
    if existing is not None:
        raise ClinicalSynthesisError("synthesis_id already exists in the ledger")
    endpoint_mapping = state.clinical_endpoint_mappings_by_id.get(
        spec.endpoint_mapping_id
    )
    if endpoint_mapping is None:
        raise ClinicalSynthesisError("approved endpoint mapping is absent from the ledger")
    mapping_failures = validate_clinical_endpoint_mapping(state, endpoint_mapping)
    if mapping_failures:
        raise ClinicalSynthesisError("approved endpoint mapping failed ledger replay")
    if (
        endpoint_mapping.candidate_id != spec.candidate_id
        or endpoint_mapping.intervention_id != spec.intervention_id
        or endpoint_mapping.disease_id != spec.disease_id
        or endpoint_mapping.endpoint_family_id != spec.endpoint_family
        or endpoint_mapping.effect_measure != spec.effect_measure
        or endpoint_mapping.favorable_direction
        != spec.effect_measure_favorable_direction
        or endpoint_mapping.safety_measure != spec.safety_measure
        or endpoint_mapping.stage is not spec.stage
    ):
        raise ClinicalSynthesisError("endpoint mapping dimensions do not match synthesis")
    selected_keys = tuple(
        (item.trial_id, item.design_id, item.endpoint_id, item.safety_id)
        for item in spec.selections
    )
    mapping_keys = tuple(
        (item.trial_id, item.design_id, item.endpoint_id, item.safety_id)
        for item in endpoint_mapping.bindings
    )
    if selected_keys != mapping_keys:
        raise ClinicalSynthesisError(
            "synthesis selections do not exactly match the approved endpoint mapping"
        )
    studies = tuple(
        _study_record(state, spec, selection) for selection in spec.selections
    )
    source_hash_sets = [set(item.source_content_hashes) for item in studies]
    for index, values in enumerate(source_hash_sets):
        if any(values & other for other in source_hash_sets[index + 1 :]):
            raise ClinicalSynthesisError(
                "selected trials are not source-disjoint by content hash"
            )
    source_evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for study in studies
                for evidence_id in study.source_evidence_ids
            }
        )
    )
    source_content_hashes = tuple(
        sorted(
            {
                digest
                for study in studies
                for digest in study.source_content_hashes
            }
        )
    )
    return BenefitRiskSynthesisRecord(
        synthesis_id=spec.synthesis_id,
        candidate_id=spec.candidate_id,
        intervention_id=spec.intervention_id,
        disease_id=spec.disease_id,
        endpoint_mapping_id=spec.endpoint_mapping_id,
        endpoint_family=spec.endpoint_family,
        effect_measure=spec.effect_measure,
        safety_measure=spec.safety_measure,
        harmonization_policy_id=spec.harmonization_policy_id,
        studies=studies,
        pooling_method="none",
        pooling_performed=False,
        benefit_direction_consistent=len(
            {item.benefit_direction for item in studies}
        )
        == 1,
        safety_direction_consistent=len(
            {item.safety_direction for item in studies}
        )
        == 1,
        source_disjoint=True,
        clinical_acceptability_inferred=False,
        source_evidence_ids=source_evidence_ids,
        source_content_hashes=source_content_hashes,
        stage=spec.stage,
        supporting_evidence=source_evidence_ids,
        identifiers={"canonical": spec.synthesis_id},
        attributes={
            "compiler_schema_version": CLINICAL_SYNTHESIS_SPEC_SCHEMA_VERSION,
            "endpoint_mapping_id": endpoint_mapping.mapping_id,
            "endpoint_mapping_portfolio_id": endpoint_mapping.portfolio_id,
            "endpoint_mapping_ontology": {
                "system": endpoint_mapping.ontology_system,
                "version": endpoint_mapping.ontology_version,
                "code": endpoint_mapping.ontology_code,
                "label": endpoint_mapping.ontology_label,
            },
            "endpoint_mapping_review_status": endpoint_mapping.review_status,
            "effect_measure_favorable_direction": (
                spec.effect_measure_favorable_direction
            ),
            "selection_spec": [to_primitive(item) for item in spec.selections],
            "endpoint_mapping_mode": "explicit_reviewed_selection",
            "automatic_endpoint_mapping_performed": False,
            "interpretive_scope": "descriptive_cross_trial_harmonization",
            "cross_trial_comparability_inferred": False,
            "population_homogeneity_inferred": False,
            "automatic_pooling_prohibited": True,
            "benefit_risk_score_computed": False,
            "endpoint_time_frames_identical": len(
                {item.endpoint_time_frame for item in studies}
            )
            == 1,
            "safety_time_frames_identical": len(
                {item.safety_time_frame for item in studies}
            )
            == 1,
            "measurement_units_identical": len(
                {item.measurement_unit for item in studies}
            )
            == 1,
            "spec_metadata": dict(spec.metadata),
        },
    )


def validate_benefit_risk_synthesis(
    state: ProgramState,
    record: BenefitRiskSynthesisRecord,
) -> tuple[str, ...]:
    """Recompile one record from its immutable selection metadata."""

    _require_instance(state, ProgramState, "state")
    _require_instance(record, BenefitRiskSynthesisRecord, "record")
    attributes = dict(record.attributes)
    raw_selections = attributes.get("selection_spec")
    if not isinstance(raw_selections, Sequence) or isinstance(
        raw_selections, (str, bytes)
    ):
        return ("selection_spec_missing",)
    if any(not isinstance(item, Mapping) for item in raw_selections):
        return ("selection_spec_invalid",)
    try:
        spec = ClinicalSynthesisSpec(
            synthesis_id=record.synthesis_id,
            candidate_id=record.candidate_id,
            intervention_id=record.intervention_id,
            disease_id=record.disease_id,
            endpoint_mapping_id=record.endpoint_mapping_id,
            endpoint_family=record.endpoint_family,
            effect_measure=record.effect_measure,
            effect_measure_favorable_direction=_text(
                attributes.get("effect_measure_favorable_direction"),
                "effect_measure_favorable_direction",
            ),
            safety_measure=record.safety_measure,
            harmonization_policy_id=record.harmonization_policy_id,
            selections=tuple(
                ClinicalStudySelection(
                    trial_id=_text(item.get("trial_id"), "trial_id"),
                    design_id=_text(item.get("design_id"), "design_id"),
                    endpoint_id=_text(item.get("endpoint_id"), "endpoint_id"),
                    safety_id=_text(item.get("safety_id"), "safety_id"),
                )
                for item in raw_selections
            ),
            stage=record.stage,
            metadata=_mapping(attributes.get("spec_metadata", {}), "spec_metadata"),
        )
        state_without_record = replace(
            state,
            benefit_risk_syntheses=tuple(
                item
                for item in state.benefit_risk_syntheses
                if item.synthesis_id != record.synthesis_id
            ),
        )
        rebuilt = compile_benefit_risk_synthesis(state_without_record, spec)
    except (ClinicalSynthesisError, TypeError, ValueError):
        return ("recompile_failed",)
    normalized_record = replace(
        record,
        supporting_evidence=rebuilt.supporting_evidence,
    )
    if normalized_record != rebuilt:
        return ("recompiled_record_mismatch",)
    source_count = len(rebuilt.supporting_evidence)
    if record.supporting_evidence[:source_count] != rebuilt.supporting_evidence:
        return ("supporting_evidence_layout_invalid",)
    derived_evidence_ids = record.supporting_evidence[source_count:]
    if not derived_evidence_ids:
        return ("derived_synthesis_evidence_missing",)
    if len(derived_evidence_ids) != 1:
        return ("derived_synthesis_evidence_count_invalid",)
    derived_evidence = state.evidence_by_id.get(derived_evidence_ids[0])
    candidate = state.candidates_by_id.get(record.candidate_id)
    if derived_evidence is None or candidate is None:
        return ("derived_synthesis_evidence_binding_invalid",)
    context = to_primitive(derived_evidence.biological_context)
    metadata = to_primitive(derived_evidence.metadata)
    expected_trial_ids = [item.trial_id for item in record.studies]
    if (
        derived_evidence.stage is not record.stage
        or derived_evidence.relation is not EvidenceRelation.SUPPORTS
        or not derived_evidence.is_visible_at(state.as_of_date)
        or _normalized(derived_evidence.subject) != _normalized(candidate.name)
        or derived_evidence.predicate
        != "clinical_benefit_risk_synthesis_available"
        or derived_evidence.object_value != record.endpoint_family
        or not isinstance(context, dict)
        or context.get("candidate_id") != record.candidate_id
        or context.get("intervention_id") != record.intervention_id
        or context.get("disease_id") != record.disease_id
        or context.get("endpoint_mapping_id") != record.endpoint_mapping_id
        or context.get("synthesis_id") != record.synthesis_id
        or context.get("endpoint_family") != record.endpoint_family
        or context.get("trial_ids") != expected_trial_ids
    ):
        return ("derived_synthesis_evidence_binding_invalid",)
    if (
        not isinstance(metadata, dict)
        or metadata.get("upstream_evidence_ids")
        != list(record.source_evidence_ids)
        or metadata.get("upstream_source_content_hashes")
        != list(record.source_content_hashes)
        or metadata.get("harmonization_policy_id")
        != record.harmonization_policy_id
        or metadata.get("endpoint_mapping_id") != record.endpoint_mapping_id
        or metadata.get("study_count") != len(record.studies)
        or metadata.get("pooling_method") != "none"
        or metadata.get("pooling_performed") is not False
        or metadata.get("benefit_risk_score_computed") is not False
        or metadata.get("clinical_acceptability_inferred") is not False
    ):
        return ("derived_synthesis_evidence_metadata_invalid",)
    return ()
