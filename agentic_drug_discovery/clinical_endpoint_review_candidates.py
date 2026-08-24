"""Provenance-bound endpoint review candidates without semantic approval."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date
from itertools import combinations, product
from typing import Any

from .clinical_population import (
    ClinicalPopulationAlignmentError,
    TREATMENT_PHASES,
    validate_phase_bound_population_alignment,
)
from .models import (
    EvidenceRelation,
    ProgramState,
    SerializableRecord,
    TrialDesignRecord,
    TrialEndpointRecord,
    TrialPopulationRecord,
    TrialSafetyRecord,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)


CLINICAL_ENDPOINT_REVIEW_CANDIDATE_SPEC_SCHEMA_VERSION = (
    "adds.clinical-endpoint-review-candidate-spec.v1"
)
CLINICAL_ENDPOINT_REVIEW_CANDIDATE_PACKET_SCHEMA_VERSION = (
    "adds.clinical-endpoint-review-candidate-packet.v1"
)
CLINICAL_ENDPOINT_REVIEW_CANDIDATE_POLICY_ID = (
    "adds.provenance-bound-endpoint-review-candidates.v1"
)

REVIEW_CANDIDATE = "review_candidate"
MECHANICALLY_EXCLUDED = "mechanically_excluded"
REPORTING_STATUS_NOT_POSTED = "reporting_status_not_posted"
EVENT_CATEGORY_NOT_SERIOUS = "event_category_not_serious"
NOT_REFERENCED_BY_POSTED_ENDPOINT = "not_referenced_by_posted_endpoint"

PHASE_BOUND_ALIGNMENT_VALID = "phase_bound_alignment_valid"
LEGACY_PHASE_UNDECLARED = "legacy_phase_undeclared"
POPULATION_ALIGNMENT_INVALID = "population_alignment_invalid"

POPULATION_IDENTITY_MISMATCH = "analysis_population_identity_mismatch"
POPULATION_RECORD_MISMATCH = "analysis_population_record_mismatch"
ENDPOINT_TIMEFRAME_MISMATCH = "endpoint_timeframe_mismatch"
TREATMENT_PHASE_NOT_DECLARED = "treatment_phase_not_declared"
TREATMENT_PHASE_PARTIAL_DECLARATION = "treatment_phase_partial_declaration"
TREATMENT_PHASE_MISMATCH = "treatment_phase_mismatch"
POPULATION_ALIGNMENT_MISMATCH = "population_alignment_record_mismatch"

MATCHED_STRUCTURE = "matched_structure"
PHASE_UNDECLARED = "phase_undeclared"
HETEROGENEOUS_STRUCTURE = "heterogeneous_structure"

_PAIR_DIAGNOSTIC_CODES = frozenset(
    {
        POPULATION_IDENTITY_MISMATCH,
        POPULATION_RECORD_MISMATCH,
        ENDPOINT_TIMEFRAME_MISMATCH,
        TREATMENT_PHASE_NOT_DECLARED,
        TREATMENT_PHASE_PARTIAL_DECLARATION,
        TREATMENT_PHASE_MISMATCH,
        POPULATION_ALIGNMENT_MISMATCH,
    }
)

_REQUIRED_LIMITATIONS = (
    (
        "The packet is exhaustive only within the selected committed "
        "TrialDesignRecord scope and cannot recover upstream registry omissions."
    ),
    (
        "Candidate enumeration does not approve an endpoint family, ontology "
        "mapping, estimand, or endpoint equivalence."
    ),
    (
        "Structural endpoint-safety alignment does not approve a causal safety "
        "relationship, common risk window, or comparative safety claim."
    ),
    (
        "Matching population identifiers, hashes, or aggregate counts do not "
        "establish participant identity or exchangeability."
    ),
    (
        "The packet performs no pooling, utility weighting, treatment choice, "
        "regulatory inference, or benefit-risk conclusion."
    ),
)


class ClinicalEndpointReviewCandidateError(ValueError):
    """Raised when a review-candidate packet cannot be compiled or replayed."""


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


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def _sorted_unique_text(value: Any, field_name: str) -> tuple[str, ...]:
    values = _tuple(value, field_name)
    for item in values:
        _require_text(item, field_name)
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{field_name} must use canonical unique sorted order")
    return values


def _unique_text(value: Any, field_name: str) -> tuple[str, ...]:
    values = _tuple(value, field_name)
    for item in values:
        _require_text(item, field_name)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")
    return values


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    _require_text(value, field_name)
    return value


def _phase_alignment(attributes: Mapping[str, Any]) -> tuple[str | None, str | None]:
    phase = attributes.get("treatment_phase")
    alignment = attributes.get("population_alignment")
    if phase is None and alignment is None:
        return None, None
    if not isinstance(phase, str) or phase not in TREATMENT_PHASES:
        raise ClinicalEndpointReviewCandidateError(
            "record treatment phase is missing or unsupported"
        )
    if not isinstance(alignment, Mapping):
        raise ClinicalEndpointReviewCandidateError(
            "phase-bound record lacks population alignment"
        )
    return phase, _sha256(alignment)


def _eligibility(reasons: tuple[str, ...]) -> str:
    return MECHANICALLY_EXCLUDED if reasons else REVIEW_CANDIDATE


def _validate_eligibility(
    status: str,
    reasons: tuple[str, ...],
    expected_reasons: tuple[str, ...],
) -> None:
    if reasons != expected_reasons or status != _eligibility(expected_reasons):
        raise ValueError("eligibility status or exclusion reasons were rebound")


@dataclass(frozen=True, slots=True)
class ClinicalEndpointReviewCandidateSpec(SerializableRecord):
    """Exact state scope for exhaustive mechanical candidate enumeration."""

    packet_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    design_ids: tuple[str, ...]
    policy_id: str = CLINICAL_ENDPOINT_REVIEW_CANDIDATE_POLICY_ID

    def __post_init__(self) -> None:
        for field_name in (
            "packet_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICAL_ENDPOINT_REVIEW_CANDIDATE_POLICY_ID:
            raise ValueError("unsupported endpoint review candidate policy_id")
        design_ids = _sorted_unique_text(self.design_ids, "design_ids")
        if not design_ids:
            raise ValueError("design_ids must not be empty")
        object.__setattr__(self, "design_ids", design_ids)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalReviewSourceEvidence(SerializableRecord):
    """One visible source-pinned evidence identity used by the packet."""

    evidence_id: str
    source_id: str
    source_version: str
    locator: str
    content_hash_sha256: str
    observed_at: str
    available_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "source_id",
            "source_version",
            "locator",
            "observed_at",
            "available_at",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.content_hash_sha256, "content_hash_sha256")
        try:
            observed_at = date.fromisoformat(self.observed_at)
            available_at = date.fromisoformat(self.available_at)
        except ValueError as exc:
            raise ValueError(
                "source evidence dates must use ISO day precision"
            ) from exc
        if (
            observed_at.isoformat() != self.observed_at
            or available_at.isoformat() != self.available_at
        ):
            raise ValueError(
                "source evidence dates must use canonical ISO day precision"
            )
        if available_at < observed_at:
            raise ValueError("source evidence availability predates observation")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationReviewCandidate(SerializableRecord):
    """One fully retained population record and its mechanical review status."""

    population_id: str
    trial_id: str
    design_id: str
    disease_id: str
    description: str
    description_sha256: str
    enrollment_count: int
    enrollment_type: str
    sex: str
    minimum_age: str
    maximum_age: str | None
    healthy_volunteers: bool
    record_sha256: str
    referenced_endpoint_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    treatment_phase: str | None
    population_alignment_sha256: str | None
    eligibility_status: str
    exclusion_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "population_id",
            "trial_id",
            "design_id",
            "disease_id",
            "description",
            "enrollment_type",
            "sex",
            "minimum_age",
            "eligibility_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _optional_text(self.maximum_age, "maximum_age")
        for field_name in (
            "description_sha256",
            "record_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.description_sha256 != _sha256(self.description):
            raise ValueError("description_sha256 does not match description")
        if (
            not isinstance(self.enrollment_count, int)
            or isinstance(self.enrollment_count, bool)
            or self.enrollment_count <= 0
        ):
            raise ValueError("enrollment_count must be a positive integer")
        _require_bool(self.healthy_volunteers, "healthy_volunteers")
        referenced = _sorted_unique_text(
            self.referenced_endpoint_ids,
            "referenced_endpoint_ids",
        )
        evidence_ids = _sorted_unique_text(
            self.source_evidence_ids,
            "source_evidence_ids",
        )
        hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        if not evidence_ids or not hashes:
            raise ValueError("population candidate requires source-pinned evidence")
        for digest in hashes:
            _require_sha256(digest, "source_content_hashes")
        object.__setattr__(self, "referenced_endpoint_ids", referenced)
        object.__setattr__(self, "source_evidence_ids", evidence_ids)
        object.__setattr__(self, "source_content_hashes", hashes)
        if self.treatment_phase is None:
            if self.population_alignment_sha256 is not None:
                raise ValueError("population alignment hash requires treatment phase")
        else:
            if self.treatment_phase not in TREATMENT_PHASES:
                raise ValueError("unsupported treatment_phase")
            if self.population_alignment_sha256 is None:
                raise ValueError("treatment phase requires population alignment hash")
            _require_sha256(
                self.population_alignment_sha256,
                "population_alignment_sha256",
            )
        reasons = _sorted_unique_text(self.exclusion_reasons, "exclusion_reasons")
        expected = () if referenced else (NOT_REFERENCED_BY_POSTED_ENDPOINT,)
        _validate_eligibility(self.eligibility_status, reasons, expected)
        object.__setattr__(self, "exclusion_reasons", reasons)


@dataclass(frozen=True, slots=True)
class ClinicalEndpointReviewCandidate(SerializableRecord):
    """One endpoint record retained without semantic family assignment."""

    endpoint_id: str
    trial_id: str
    design_id: str
    population_id: str
    population_record_sha256: str
    name: str
    outcome_type: str
    time_frame: str
    parameter_type: str
    unit: str
    reporting_status: str
    arm_ids: tuple[str, ...]
    record_sha256: str
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    treatment_phase: str | None
    population_alignment_sha256: str | None
    eligibility_status: str
    exclusion_reasons: tuple[str, ...]
    endpoint_family_assigned: bool = False
    estimand_equivalence_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "endpoint_id",
            "trial_id",
            "design_id",
            "population_id",
            "name",
            "outcome_type",
            "time_frame",
            "parameter_type",
            "unit",
            "reporting_status",
            "eligibility_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.population_record_sha256, "population_record_sha256")
        _require_sha256(self.record_sha256, "record_sha256")
        arm_ids = _unique_text(self.arm_ids, "arm_ids")
        if len(arm_ids) < 2:
            raise ValueError("arm_ids must contain at least two arms")
        evidence_ids = _sorted_unique_text(
            self.source_evidence_ids,
            "source_evidence_ids",
        )
        hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        if not evidence_ids or not hashes:
            raise ValueError("endpoint candidate requires source-pinned evidence")
        for digest in hashes:
            _require_sha256(digest, "source_content_hashes")
        object.__setattr__(self, "arm_ids", arm_ids)
        object.__setattr__(self, "source_evidence_ids", evidence_ids)
        object.__setattr__(self, "source_content_hashes", hashes)
        if self.treatment_phase is None:
            if self.population_alignment_sha256 is not None:
                raise ValueError("population alignment hash requires treatment phase")
        else:
            if self.treatment_phase not in TREATMENT_PHASES:
                raise ValueError("unsupported treatment_phase")
            if self.population_alignment_sha256 is None:
                raise ValueError("treatment phase requires population alignment hash")
            _require_sha256(
                self.population_alignment_sha256,
                "population_alignment_sha256",
            )
        reasons = _sorted_unique_text(self.exclusion_reasons, "exclusion_reasons")
        expected = (
            ()
            if _normalized(self.reporting_status) == "posted"
            else (REPORTING_STATUS_NOT_POSTED,)
        )
        _validate_eligibility(self.eligibility_status, reasons, expected)
        object.__setattr__(self, "exclusion_reasons", reasons)
        for field_name in (
            "endpoint_family_assigned",
            "estimand_equivalence_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class ClinicalSafetyArmReviewCandidate(SerializableRecord):
    """One typed arm summary retained from a safety record."""

    safety_arm_id: str
    arm_id: str
    role: str
    source_group_id: str
    source_group_title: str
    serious_num_affected: int
    serious_num_at_risk: int

    def __post_init__(self) -> None:
        for field_name in (
            "safety_arm_id",
            "arm_id",
            "role",
            "source_group_id",
            "source_group_title",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.role not in {"candidate", "comparator"}:
            raise ValueError("safety arm role must be candidate or comparator")
        for field_name in ("serious_num_affected", "serious_num_at_risk"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.serious_num_at_risk <= 0:
            raise ValueError("serious_num_at_risk must be positive")
        if self.serious_num_affected > self.serious_num_at_risk:
            raise ValueError("serious_num_affected exceeds serious_num_at_risk")


@dataclass(frozen=True, slots=True)
class ClinicalSafetyReviewCandidate(SerializableRecord):
    """One safety record retained without endpoint relationship approval."""

    safety_id: str
    trial_id: str
    design_id: str
    event_category: str
    reporting_status: str
    time_frame: str
    event_term_count: int
    description: str | None
    arm_summaries: tuple[ClinicalSafetyArmReviewCandidate, ...]
    record_sha256: str
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    treatment_phase: str | None
    population_alignment_sha256: str | None
    eligibility_status: str
    exclusion_reasons: tuple[str, ...]
    endpoint_relationship_approved: bool = False
    comparative_safety_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "safety_id",
            "trial_id",
            "design_id",
            "event_category",
            "reporting_status",
            "time_frame",
            "eligibility_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _optional_text(self.description, "description")
        _require_non_negative_int(self.event_term_count, "event_term_count")
        summaries = _tuple(self.arm_summaries, "arm_summaries")
        if len(summaries) < 2:
            raise ValueError("arm_summaries must contain at least two arms")
        for item in summaries:
            _require_instance(
                item,
                ClinicalSafetyArmReviewCandidate,
                "arm_summaries item",
            )
        if len({item.arm_id for item in summaries}) != len(summaries):
            raise ValueError("arm_summaries arm ids must be unique")
        if len({item.safety_arm_id for item in summaries}) != len(summaries):
            raise ValueError("arm_summaries safety arm ids must be unique")
        if len({item.source_group_id for item in summaries}) != len(summaries):
            raise ValueError("arm_summaries source group ids must be unique")
        if {item.role for item in summaries} != {"candidate", "comparator"}:
            raise ValueError(
                "arm_summaries must include candidate and comparator roles"
            )
        object.__setattr__(self, "arm_summaries", summaries)
        _require_sha256(self.record_sha256, "record_sha256")
        evidence_ids = _sorted_unique_text(
            self.source_evidence_ids,
            "source_evidence_ids",
        )
        hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        if not evidence_ids or not hashes:
            raise ValueError("safety candidate requires source-pinned evidence")
        for digest in hashes:
            _require_sha256(digest, "source_content_hashes")
        object.__setattr__(self, "source_evidence_ids", evidence_ids)
        object.__setattr__(self, "source_content_hashes", hashes)
        if self.treatment_phase is None:
            if self.population_alignment_sha256 is not None:
                raise ValueError("population alignment hash requires treatment phase")
        else:
            if self.treatment_phase not in TREATMENT_PHASES:
                raise ValueError("unsupported treatment_phase")
            if self.population_alignment_sha256 is None:
                raise ValueError("treatment phase requires population alignment hash")
            _require_sha256(
                self.population_alignment_sha256,
                "population_alignment_sha256",
            )
        reasons: list[str] = []
        if _normalized(self.reporting_status) != "posted":
            reasons.append(REPORTING_STATUS_NOT_POSTED)
        if _normalized(self.event_category) != "serious":
            reasons.append(EVENT_CATEGORY_NOT_SERIOUS)
        canonical_reasons = tuple(sorted(reasons))
        parsed_reasons = _sorted_unique_text(
            self.exclusion_reasons,
            "exclusion_reasons",
        )
        _validate_eligibility(
            self.eligibility_status,
            parsed_reasons,
            canonical_reasons,
        )
        object.__setattr__(self, "exclusion_reasons", parsed_reasons)
        for field_name in (
            "endpoint_relationship_approved",
            "comparative_safety_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


def _pair_facts(
    left: ClinicalEndpointReviewCandidate,
    right: ClinicalEndpointReviewCandidate,
) -> dict[str, Any]:
    diagnostic_codes: list[str] = []
    if left.population_id != right.population_id:
        diagnostic_codes.append(POPULATION_IDENTITY_MISMATCH)
    elif left.population_record_sha256 != right.population_record_sha256:
        diagnostic_codes.append(POPULATION_RECORD_MISMATCH)
    if left.time_frame != right.time_frame:
        diagnostic_codes.append(ENDPOINT_TIMEFRAME_MISMATCH)
    if left.treatment_phase is None and right.treatment_phase is None:
        diagnostic_codes.append(TREATMENT_PHASE_NOT_DECLARED)
    elif left.treatment_phase is None or right.treatment_phase is None:
        diagnostic_codes.append(TREATMENT_PHASE_PARTIAL_DECLARATION)
    elif left.treatment_phase != right.treatment_phase:
        diagnostic_codes.append(TREATMENT_PHASE_MISMATCH)
    if (
        left.population_alignment_sha256 is not None
        and right.population_alignment_sha256 is not None
        and left.population_alignment_sha256 != right.population_alignment_sha256
    ):
        diagnostic_codes.append(POPULATION_ALIGNMENT_MISMATCH)
    codes = tuple(sorted(diagnostic_codes))
    if set(codes) - {TREATMENT_PHASE_NOT_DECLARED}:
        status = HETEROGENEOUS_STRUCTURE
    elif TREATMENT_PHASE_NOT_DECLARED in codes:
        status = PHASE_UNDECLARED
    else:
        status = MATCHED_STRUCTURE
    return {
        "shared_population_identity": left.population_id == right.population_id,
        "shared_population_record": (
            left.population_id == right.population_id
            and left.population_record_sha256 == right.population_record_sha256
        ),
        "endpoint_time_frames_equal": left.time_frame == right.time_frame,
        "treatment_phases_equal": (
            left.treatment_phase is not None
            and left.treatment_phase == right.treatment_phase
        ),
        "shared_population_alignment": (
            left.population_alignment_sha256 is not None
            and left.population_alignment_sha256 == right.population_alignment_sha256
        ),
        "shared_source_content_hashes": tuple(
            sorted(set(left.source_content_hashes) & set(right.source_content_hashes))
        ),
        "diagnostic_codes": codes,
        "structural_status": status,
    }


@dataclass(frozen=True, slots=True)
class ClinicalEndpointPairReviewCandidate(SerializableRecord):
    """One unordered same-design endpoint pair without equivalence approval."""

    pair_id: str
    trial_id: str
    design_id: str
    left_endpoint_id: str
    right_endpoint_id: str
    left_population_id: str
    right_population_id: str
    left_population_record_sha256: str
    right_population_record_sha256: str
    left_endpoint_time_frame: str
    right_endpoint_time_frame: str
    left_treatment_phase: str | None
    right_treatment_phase: str | None
    left_population_alignment_sha256: str | None
    right_population_alignment_sha256: str | None
    left_source_content_hashes: tuple[str, ...]
    right_source_content_hashes: tuple[str, ...]
    shared_population_identity: bool
    shared_population_record: bool
    endpoint_time_frames_equal: bool
    treatment_phases_equal: bool
    shared_population_alignment: bool
    shared_source_content_hashes: tuple[str, ...]
    diagnostic_codes: tuple[str, ...]
    structural_status: str
    endpoint_equivalence_approved: bool = False
    estimand_equivalence_inferred: bool = False
    clinical_comparability_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "design_id",
            "left_endpoint_id",
            "right_endpoint_id",
            "left_population_id",
            "right_population_id",
            "left_endpoint_time_frame",
            "right_endpoint_time_frame",
            "structural_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.pair_id, "pair_id")
        for field_name in (
            "left_population_record_sha256",
            "right_population_record_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.left_endpoint_id >= self.right_endpoint_id:
            raise ValueError("endpoint pair must use canonical endpoint-id order")
        expected_pair_id = _sha256(
            {
                "trial_id": self.trial_id,
                "design_id": self.design_id,
                "left_endpoint_id": self.left_endpoint_id,
                "right_endpoint_id": self.right_endpoint_id,
            }
        )
        if self.pair_id != expected_pair_id:
            raise ValueError("pair_id does not match endpoint identities")
        left_hashes = _sorted_unique_text(
            self.left_source_content_hashes,
            "left_source_content_hashes",
        )
        right_hashes = _sorted_unique_text(
            self.right_source_content_hashes,
            "right_source_content_hashes",
        )
        shared_hashes = _sorted_unique_text(
            self.shared_source_content_hashes,
            "shared_source_content_hashes",
        )
        for digest in (*left_hashes, *right_hashes, *shared_hashes):
            _require_sha256(digest, "source_content_hash")
        object.__setattr__(self, "left_source_content_hashes", left_hashes)
        object.__setattr__(self, "right_source_content_hashes", right_hashes)
        object.__setattr__(self, "shared_source_content_hashes", shared_hashes)
        codes = _sorted_unique_text(self.diagnostic_codes, "diagnostic_codes")
        if any(code not in _PAIR_DIAGNOSTIC_CODES for code in codes):
            raise ValueError("diagnostic_codes contains an unsupported value")
        object.__setattr__(self, "diagnostic_codes", codes)
        for phase, alignment_hash, side in (
            (
                self.left_treatment_phase,
                self.left_population_alignment_sha256,
                "left",
            ),
            (
                self.right_treatment_phase,
                self.right_population_alignment_sha256,
                "right",
            ),
        ):
            if phase is None:
                if alignment_hash is not None:
                    raise ValueError(f"{side} alignment hash requires treatment phase")
            else:
                if phase not in TREATMENT_PHASES or alignment_hash is None:
                    raise ValueError(f"{side} phase/alignment declaration is invalid")
                _require_sha256(alignment_hash, f"{side}_population_alignment_sha256")
        left = _pair_endpoint_view(self, left=True)
        right = _pair_endpoint_view(self, left=False)
        facts = _pair_facts(left, right)
        for field_name, expected in facts.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match endpoint pair")
        for field_name in (
            "shared_population_identity",
            "shared_population_record",
            "endpoint_time_frames_equal",
            "treatment_phases_equal",
            "shared_population_alignment",
            "endpoint_equivalence_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        for field_name in (
            "endpoint_equivalence_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


def _pair_endpoint_view(
    pair: ClinicalEndpointPairReviewCandidate,
    *,
    left: bool,
) -> ClinicalEndpointReviewCandidate:
    prefix = "left" if left else "right"
    return ClinicalEndpointReviewCandidate(
        endpoint_id=getattr(pair, f"{prefix}_endpoint_id"),
        trial_id=pair.trial_id,
        design_id=pair.design_id,
        population_id=getattr(pair, f"{prefix}_population_id"),
        population_record_sha256=getattr(
            pair,
            f"{prefix}_population_record_sha256",
        ),
        name="pair-view",
        outcome_type="pair-view",
        time_frame=getattr(pair, f"{prefix}_endpoint_time_frame"),
        parameter_type="pair-view",
        unit="pair-view",
        reporting_status="posted",
        arm_ids=("pair-view:candidate", "pair-view:comparator"),
        record_sha256="0" * 64,
        source_evidence_ids=("pair-view:evidence",),
        source_content_hashes=getattr(
            pair,
            f"{prefix}_source_content_hashes",
        ),
        treatment_phase=getattr(pair, f"{prefix}_treatment_phase"),
        population_alignment_sha256=getattr(
            pair,
            f"{prefix}_population_alignment_sha256",
        ),
        eligibility_status=REVIEW_CANDIDATE,
        exclusion_reasons=(),
    )


@dataclass(frozen=True, slots=True)
class ClinicalEndpointSafetyReviewLink(SerializableRecord):
    """One mechanically enumerated endpoint-safety relationship candidate."""

    link_id: str
    trial_id: str
    design_id: str
    endpoint_id: str
    safety_id: str
    population_id: str
    endpoint_time_frame: str
    safety_time_frame: str
    endpoint_arm_ids: tuple[str, ...]
    safety_arm_ids: tuple[str, ...]
    endpoint_treatment_phase: str | None
    safety_treatment_phase: str | None
    endpoint_population_alignment_sha256: str | None
    safety_population_alignment_sha256: str | None
    alignment_status: str
    endpoint_arms_covered_by_safety: bool
    source_content_hashes: tuple[str, ...]
    endpoint_relationship_approved: bool = False
    common_safety_risk_window_inferred: bool = False
    comparative_safety_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "design_id",
            "endpoint_id",
            "safety_id",
            "population_id",
            "endpoint_time_frame",
            "safety_time_frame",
            "alignment_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.link_id, "link_id")
        expected_link_id = _sha256(
            {
                "trial_id": self.trial_id,
                "design_id": self.design_id,
                "endpoint_id": self.endpoint_id,
                "safety_id": self.safety_id,
            }
        )
        if self.link_id != expected_link_id:
            raise ValueError("link_id does not match endpoint/safety identities")
        endpoint_arms = _unique_text(self.endpoint_arm_ids, "endpoint_arm_ids")
        safety_arms = _unique_text(self.safety_arm_ids, "safety_arm_ids")
        hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        if not hashes:
            raise ValueError("endpoint-safety link requires source content hashes")
        for digest in hashes:
            _require_sha256(digest, "source_content_hashes")
        object.__setattr__(self, "endpoint_arm_ids", endpoint_arms)
        object.__setattr__(self, "safety_arm_ids", safety_arms)
        object.__setattr__(self, "source_content_hashes", hashes)
        expected_coverage = set(endpoint_arms).issubset(safety_arms)
        if self.endpoint_arms_covered_by_safety != expected_coverage:
            raise ValueError("endpoint_arms_covered_by_safety was rebound")
        for field_name in (
            "endpoint_arms_covered_by_safety",
            "endpoint_relationship_approved",
            "common_safety_risk_window_inferred",
            "comparative_safety_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if self.alignment_status not in {
            PHASE_BOUND_ALIGNMENT_VALID,
            LEGACY_PHASE_UNDECLARED,
            POPULATION_ALIGNMENT_INVALID,
        }:
            raise ValueError("unsupported alignment_status")
        for phase, alignment_hash, side in (
            (
                self.endpoint_treatment_phase,
                self.endpoint_population_alignment_sha256,
                "endpoint",
            ),
            (
                self.safety_treatment_phase,
                self.safety_population_alignment_sha256,
                "safety",
            ),
        ):
            if phase is None:
                if alignment_hash is not None:
                    raise ValueError(f"{side} alignment hash requires treatment phase")
            else:
                if phase not in TREATMENT_PHASES or alignment_hash is None:
                    raise ValueError(f"{side} phase/alignment declaration is invalid")
                _require_sha256(alignment_hash, f"{side}_population_alignment_sha256")
        if self.alignment_status == LEGACY_PHASE_UNDECLARED and not (
            self.endpoint_treatment_phase is None
            and self.safety_treatment_phase is None
        ):
            raise ValueError(
                "legacy alignment requires undeclared endpoint and safety phase"
            )
        if self.alignment_status == PHASE_BOUND_ALIGNMENT_VALID and not (
            self.endpoint_treatment_phase is not None
            and self.safety_treatment_phase is not None
            and self.endpoint_treatment_phase == self.safety_treatment_phase
            and self.endpoint_population_alignment_sha256
            == self.safety_population_alignment_sha256
            and expected_coverage
        ):
            raise ValueError("valid phase-bound alignment fields are inconsistent")
        for field_name in (
            "endpoint_relationship_approved",
            "common_safety_risk_window_inferred",
            "comparative_safety_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class ClinicalEndpointReviewCandidatePacket(SerializableRecord):
    """Exhaustive provenance-bound candidates with fixed semantic nonclaims."""

    packet_id: str
    program_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    policy_id: str
    spec_sha256: str
    state_sha256: str
    design_ids: tuple[str, ...]
    source_evidence: tuple[ClinicalReviewSourceEvidence, ...]
    populations: tuple[ClinicalPopulationReviewCandidate, ...]
    endpoints: tuple[ClinicalEndpointReviewCandidate, ...]
    safety_records: tuple[ClinicalSafetyReviewCandidate, ...]
    endpoint_pairs: tuple[ClinicalEndpointPairReviewCandidate, ...]
    endpoint_safety_links: tuple[ClinicalEndpointSafetyReviewLink, ...]
    design_count: int
    source_evidence_count: int
    population_record_count: int
    population_candidate_count: int
    population_excluded_count: int
    endpoint_record_count: int
    endpoint_candidate_count: int
    endpoint_excluded_count: int
    safety_record_count: int
    safety_candidate_count: int
    safety_excluded_count: int
    endpoint_pair_count: int
    endpoint_safety_link_count: int
    full_record_enumeration_performed: bool
    full_state_replay_required: bool
    reviewer_approval_performed: bool
    endpoint_family_assigned: bool
    ontology_mapping_approved: bool
    estimand_equivalence_inferred: bool
    clinical_comparability_inferred: bool
    comparative_safety_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "packet_id",
            "program_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICAL_ENDPOINT_REVIEW_CANDIDATE_POLICY_ID:
            raise ValueError("unsupported endpoint review candidate policy_id")
        _require_sha256(self.spec_sha256, "spec_sha256")
        _require_sha256(self.state_sha256, "state_sha256")
        design_ids = _sorted_unique_text(self.design_ids, "design_ids")
        if not design_ids:
            raise ValueError("design_ids must not be empty")
        object.__setattr__(self, "design_ids", design_ids)
        collection_specs = (
            ("source_evidence", ClinicalReviewSourceEvidence, "evidence_id"),
            ("populations", ClinicalPopulationReviewCandidate, "population_id"),
            ("endpoints", ClinicalEndpointReviewCandidate, "endpoint_id"),
            ("safety_records", ClinicalSafetyReviewCandidate, "safety_id"),
            ("endpoint_pairs", ClinicalEndpointPairReviewCandidate, "pair_id"),
            ("endpoint_safety_links", ClinicalEndpointSafetyReviewLink, "link_id"),
        )
        for field_name, expected_type, identity_field in collection_specs:
            values = _tuple(getattr(self, field_name), field_name)
            for item in values:
                _require_instance(item, expected_type, f"{field_name} item")
            if len({getattr(item, identity_field) for item in values}) != len(values):
                raise ValueError(f"{field_name} identities must be unique")
            object.__setattr__(self, field_name, values)
        expected_orders = {
            "source_evidence": tuple(
                sorted(self.source_evidence, key=lambda item: item.evidence_id)
            ),
            "populations": tuple(
                sorted(
                    self.populations,
                    key=lambda item: (
                        item.trial_id,
                        item.design_id,
                        item.population_id,
                    ),
                )
            ),
            "endpoints": tuple(
                sorted(
                    self.endpoints,
                    key=lambda item: (item.trial_id, item.design_id, item.endpoint_id),
                )
            ),
            "safety_records": tuple(
                sorted(
                    self.safety_records,
                    key=lambda item: (item.trial_id, item.design_id, item.safety_id),
                )
            ),
            "endpoint_pairs": tuple(
                sorted(
                    self.endpoint_pairs,
                    key=lambda item: (
                        item.trial_id,
                        item.design_id,
                        item.left_endpoint_id,
                        item.right_endpoint_id,
                    ),
                )
            ),
            "endpoint_safety_links": tuple(
                sorted(
                    self.endpoint_safety_links,
                    key=lambda item: (
                        item.trial_id,
                        item.design_id,
                        item.endpoint_id,
                        item.safety_id,
                    ),
                )
            ),
        }
        for field_name, expected in expected_orders.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} must use canonical order")
        if not self.source_evidence:
            raise ValueError("source_evidence must not be empty")
        for field_name in ("populations", "endpoints", "safety_records"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")
        _validate_packet_cross_links(self)
        expected_counts = _packet_counts(self)
        for field_name, expected in expected_counts.items():
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match packet records")
        for field_name in (
            "full_record_enumeration_performed",
            "full_state_replay_required",
            "reviewer_approval_performed",
            "endpoint_family_assigned",
            "ontology_mapping_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "comparative_safety_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if (
            not self.full_record_enumeration_performed
            or not self.full_state_replay_required
        ):
            raise ValueError("packet requires full enumeration and state replay")
        for field_name in (
            "reviewer_approval_performed",
            "endpoint_family_assigned",
            "ontology_mapping_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "comparative_safety_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")
        limitations = _tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("endpoint review candidate limitations changed")
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _validate_packet_cross_links(
    packet: ClinicalEndpointReviewCandidatePacket,
) -> None:
    design_ids = set(packet.design_ids)
    for field_name in ("populations", "endpoints", "safety_records"):
        observed = {item.design_id for item in getattr(packet, field_name)}
        if observed != design_ids:
            raise ValueError(f"{field_name} do not exactly cover design_ids")

    trial_ids_by_design: dict[str, set[str]] = {
        design_id: set() for design_id in packet.design_ids
    }
    for item in (*packet.populations, *packet.endpoints, *packet.safety_records):
        trial_ids_by_design[item.design_id].add(item.trial_id)
    if any(len(trial_ids) != 1 for trial_ids in trial_ids_by_design.values()):
        raise ValueError("each design must bind exactly one trial identity")

    source_by_id = {item.evidence_id: item for item in packet.source_evidence}
    for item in (*packet.populations, *packet.endpoints, *packet.safety_records):
        try:
            expected_hashes = tuple(
                sorted(
                    {
                        source_by_id[evidence_id].content_hash_sha256
                        for evidence_id in item.source_evidence_ids
                    }
                )
            )
        except KeyError as exc:
            raise ValueError(
                "candidate record references source evidence absent from packet"
            ) from exc
        if item.source_content_hashes != expected_hashes:
            raise ValueError("candidate source-content hashes are rebound")

    population_by_key = {
        (item.design_id, item.population_id): item for item in packet.populations
    }
    endpoint_by_key = {
        (item.design_id, item.endpoint_id): item for item in packet.endpoints
    }
    safety_by_key = {
        (item.design_id, item.safety_id): item for item in packet.safety_records
    }
    for population in packet.populations:
        if population.disease_id != packet.disease_id:
            raise ValueError("population disease identity is rebound")
        expected_endpoint_ids = tuple(
            sorted(
                endpoint.endpoint_id
                for endpoint in packet.endpoints
                if endpoint.design_id == population.design_id
                and endpoint.population_id == population.population_id
                and endpoint.eligibility_status == REVIEW_CANDIDATE
            )
        )
        if population.referenced_endpoint_ids != expected_endpoint_ids:
            raise ValueError("population endpoint references are incomplete or rebound")
    for endpoint in packet.endpoints:
        population = population_by_key.get((endpoint.design_id, endpoint.population_id))
        if population is None:
            raise ValueError("endpoint references a population absent from packet")
        if endpoint.population_record_sha256 != population.record_sha256:
            raise ValueError("endpoint population record hash is rebound")
        if endpoint.trial_id != population.trial_id:
            raise ValueError("endpoint/population trial identity is rebound")

    eligible_by_design: dict[str, tuple[ClinicalEndpointReviewCandidate, ...]] = {}
    for design_id in packet.design_ids:
        eligible_by_design[design_id] = tuple(
            sorted(
                (
                    item
                    for item in packet.endpoints
                    if item.design_id == design_id
                    and item.eligibility_status == REVIEW_CANDIDATE
                ),
                key=lambda item: item.endpoint_id,
            )
        )
    expected_pairs = tuple(
        _endpoint_pair(left, right)
        for design_id in packet.design_ids
        for left, right in combinations(eligible_by_design[design_id], 2)
    )
    if {item.pair_id: item for item in expected_pairs} != {
        item.pair_id: item for item in packet.endpoint_pairs
    }:
        raise ValueError("endpoint pair enumeration is incomplete or rebound")

    eligible_safety_by_design: dict[str, tuple[ClinicalSafetyReviewCandidate, ...]] = {}
    for design_id in packet.design_ids:
        eligible_safety_by_design[design_id] = tuple(
            sorted(
                (
                    item
                    for item in packet.safety_records
                    if item.design_id == design_id
                    and item.eligibility_status == REVIEW_CANDIDATE
                ),
                key=lambda item: item.safety_id,
            )
        )
    expected_link_keys = {
        (design_id, endpoint.endpoint_id, safety.safety_id)
        for design_id in packet.design_ids
        for endpoint, safety in product(
            eligible_by_design[design_id],
            eligible_safety_by_design[design_id],
        )
    }
    actual_link_keys = {
        (item.design_id, item.endpoint_id, item.safety_id)
        for item in packet.endpoint_safety_links
    }
    if actual_link_keys != expected_link_keys:
        raise ValueError("endpoint-safety link enumeration is incomplete or rebound")
    for link in packet.endpoint_safety_links:
        endpoint = endpoint_by_key[(link.design_id, link.endpoint_id)]
        safety = safety_by_key[(link.design_id, link.safety_id)]
        expected_values = {
            "trial_id": endpoint.trial_id,
            "population_id": endpoint.population_id,
            "endpoint_time_frame": endpoint.time_frame,
            "safety_time_frame": safety.time_frame,
            "endpoint_arm_ids": endpoint.arm_ids,
            "safety_arm_ids": tuple(item.arm_id for item in safety.arm_summaries),
            "endpoint_treatment_phase": endpoint.treatment_phase,
            "safety_treatment_phase": safety.treatment_phase,
            "endpoint_population_alignment_sha256": (
                endpoint.population_alignment_sha256
            ),
            "safety_population_alignment_sha256": (safety.population_alignment_sha256),
            "source_content_hashes": tuple(
                sorted(
                    set(endpoint.source_content_hashes)
                    | set(safety.source_content_hashes)
                )
            ),
        }
        for field_name, expected in expected_values.items():
            if getattr(link, field_name) != expected:
                raise ValueError(f"endpoint-safety link {field_name} is rebound")


def _packet_counts(packet: ClinicalEndpointReviewCandidatePacket) -> dict[str, int]:
    return {
        "design_count": len(packet.design_ids),
        "source_evidence_count": len(packet.source_evidence),
        "population_record_count": len(packet.populations),
        "population_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE for item in packet.populations
        ),
        "population_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED
            for item in packet.populations
        ),
        "endpoint_record_count": len(packet.endpoints),
        "endpoint_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE for item in packet.endpoints
        ),
        "endpoint_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED
            for item in packet.endpoints
        ),
        "safety_record_count": len(packet.safety_records),
        "safety_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE
            for item in packet.safety_records
        ),
        "safety_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED
            for item in packet.safety_records
        ),
        "endpoint_pair_count": len(packet.endpoint_pairs),
        "endpoint_safety_link_count": len(packet.endpoint_safety_links),
    }


def _record_provenance(
    state: ProgramState,
    evidence_ids: tuple[str, ...],
    source_registry: dict[str, ClinicalReviewSourceEvidence],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    canonical_ids = tuple(sorted(set(evidence_ids)))
    if not canonical_ids:
        raise ClinicalEndpointReviewCandidateError(
            "review candidate record lacks supporting evidence"
        )
    hashes: set[str] = set()
    for evidence_id in canonical_ids:
        event = state.evidence_by_id.get(evidence_id)
        if event is None:
            raise ClinicalEndpointReviewCandidateError(
                f"review candidate references missing evidence: {evidence_id}"
            )
        if event.relation is not EvidenceRelation.SUPPORTS:
            raise ClinicalEndpointReviewCandidateError(
                f"review candidate references non-support evidence: {evidence_id}"
            )
        if not event.is_visible_at(state.as_of_date):
            raise ClinicalEndpointReviewCandidateError(
                f"review candidate evidence is after cutoff: {evidence_id}"
            )
        digest = event.source.content_hash
        if not isinstance(digest, str):
            raise ClinicalEndpointReviewCandidateError(
                f"review candidate evidence is not source-pinned: {evidence_id}"
            )
        try:
            _require_sha256(digest, "content_hash")
        except (TypeError, ValueError) as exc:
            raise ClinicalEndpointReviewCandidateError(
                f"review candidate evidence is not source-pinned: {evidence_id}"
            ) from exc
        source = ClinicalReviewSourceEvidence(
            evidence_id=evidence_id,
            source_id=event.source.source_id,
            source_version=event.source.source_version,
            locator=event.source.locator,
            content_hash_sha256=digest,
            observed_at=event.observed_at.isoformat(),
            available_at=event.available_at.isoformat(),
        )
        previous = source_registry.get(evidence_id)
        if previous is not None and previous != source:
            raise ClinicalEndpointReviewCandidateError(
                f"source evidence identity rebound: {evidence_id}"
            )
        source_registry[evidence_id] = source
        hashes.add(digest)
    return canonical_ids, tuple(sorted(hashes))


def _resolve_designs(
    state: ProgramState,
    spec: ClinicalEndpointReviewCandidateSpec,
) -> tuple[TrialDesignRecord, ...]:
    candidate = state.candidates_by_id.get(spec.candidate_id)
    intervention = state.interventions_by_id.get(spec.intervention_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if candidate is None or intervention is None or disease is None:
        raise ClinicalEndpointReviewCandidateError(
            "candidate, intervention, and disease must exist"
        )
    if (
        intervention.candidate_id != candidate.candidate_id
        or intervention.disease_id != disease.disease_id
        or candidate.attributes.get("disease_id") != disease.disease_id
        or _normalized(disease.name) != _normalized(state.disease)
    ):
        raise ClinicalEndpointReviewCandidateError(
            "candidate/intervention/disease identity is not continuous"
        )
    designs: list[TrialDesignRecord] = []
    for design_id in spec.design_ids:
        design = state.trial_designs_by_id.get(design_id)
        if design is None:
            raise ClinicalEndpointReviewCandidateError(
                f"selected trial design is absent: {design_id}"
            )
        trial = state.trials_by_id.get(design.trial_id)
        if trial is None:
            raise ClinicalEndpointReviewCandidateError(
                f"selected trial is absent: {design.trial_id}"
            )
        if (
            design.intervention_id != spec.intervention_id
            or design.disease_id != spec.disease_id
            or trial.intervention_id != spec.intervention_id
            or trial.disease_id != spec.disease_id
        ):
            raise ClinicalEndpointReviewCandidateError(
                f"selected trial/design identity is rebound: {design_id}"
            )
        designs.append(design)
    return tuple(designs)


def _population_candidate(
    state: ProgramState,
    design: TrialDesignRecord,
    population: TrialPopulationRecord,
    referenced_endpoint_ids: tuple[str, ...],
    source_registry: dict[str, ClinicalReviewSourceEvidence],
) -> ClinicalPopulationReviewCandidate:
    evidence_ids, content_hashes = _record_provenance(
        state,
        population.supporting_evidence,
        source_registry,
    )
    phase, alignment_hash = _phase_alignment(population.attributes)
    reasons = () if referenced_endpoint_ids else (NOT_REFERENCED_BY_POSTED_ENDPOINT,)
    return ClinicalPopulationReviewCandidate(
        population_id=population.population_id,
        trial_id=population.trial_id,
        design_id=design.design_id,
        disease_id=population.disease_id,
        description=population.description,
        description_sha256=_sha256(population.description),
        enrollment_count=population.enrollment_count,
        enrollment_type=population.enrollment_type,
        sex=population.sex,
        minimum_age=population.minimum_age,
        maximum_age=population.maximum_age,
        healthy_volunteers=population.healthy_volunteers,
        record_sha256=_sha256(
            {
                "trial_id": design.trial_id,
                "design_id": design.design_id,
                "population": population,
            }
        ),
        referenced_endpoint_ids=referenced_endpoint_ids,
        source_evidence_ids=evidence_ids,
        source_content_hashes=content_hashes,
        treatment_phase=phase,
        population_alignment_sha256=alignment_hash,
        eligibility_status=_eligibility(reasons),
        exclusion_reasons=reasons,
    )


def _endpoint_candidate(
    state: ProgramState,
    design: TrialDesignRecord,
    endpoint: TrialEndpointRecord,
    population_record_sha256: str,
    source_registry: dict[str, ClinicalReviewSourceEvidence],
) -> ClinicalEndpointReviewCandidate:
    evidence_ids, content_hashes = _record_provenance(
        state,
        endpoint.supporting_evidence,
        source_registry,
    )
    phase, alignment_hash = _phase_alignment(endpoint.attributes)
    reasons = (
        ()
        if _normalized(endpoint.reporting_status) == "posted"
        else (REPORTING_STATUS_NOT_POSTED,)
    )
    return ClinicalEndpointReviewCandidate(
        endpoint_id=endpoint.endpoint_id,
        trial_id=endpoint.trial_id,
        design_id=design.design_id,
        population_id=endpoint.population_id,
        population_record_sha256=population_record_sha256,
        name=endpoint.name,
        outcome_type=endpoint.outcome_type,
        time_frame=endpoint.time_frame,
        parameter_type=endpoint.parameter_type,
        unit=endpoint.unit,
        reporting_status=endpoint.reporting_status,
        arm_ids=endpoint.arm_ids,
        record_sha256=_sha256(
            {
                "trial_id": design.trial_id,
                "design_id": design.design_id,
                "endpoint": endpoint,
            }
        ),
        source_evidence_ids=evidence_ids,
        source_content_hashes=content_hashes,
        treatment_phase=phase,
        population_alignment_sha256=alignment_hash,
        eligibility_status=_eligibility(reasons),
        exclusion_reasons=reasons,
    )


def _safety_candidate(
    state: ProgramState,
    design: TrialDesignRecord,
    safety: TrialSafetyRecord,
    source_registry: dict[str, ClinicalReviewSourceEvidence],
) -> ClinicalSafetyReviewCandidate:
    evidence_ids, content_hashes = _record_provenance(
        state,
        safety.supporting_evidence,
        source_registry,
    )
    phase, alignment_hash = _phase_alignment(safety.attributes)
    reasons: list[str] = []
    if _normalized(safety.reporting_status) != "posted":
        reasons.append(REPORTING_STATUS_NOT_POSTED)
    if _normalized(safety.event_category) != "serious":
        reasons.append(EVENT_CATEGORY_NOT_SERIOUS)
    canonical_reasons = tuple(sorted(reasons))
    return ClinicalSafetyReviewCandidate(
        safety_id=safety.safety_id,
        trial_id=safety.trial_id,
        design_id=design.design_id,
        event_category=safety.event_category,
        reporting_status=safety.reporting_status,
        time_frame=safety.time_frame,
        event_term_count=safety.event_term_count,
        description=safety.description,
        arm_summaries=tuple(
            ClinicalSafetyArmReviewCandidate(
                safety_arm_id=item.safety_arm_id,
                arm_id=item.arm_id,
                role=item.role.value,
                source_group_id=item.source_group_id,
                source_group_title=item.source_group_title,
                serious_num_affected=item.serious_num_affected,
                serious_num_at_risk=item.serious_num_at_risk,
            )
            for item in safety.arm_summaries
        ),
        record_sha256=_sha256(
            {
                "trial_id": design.trial_id,
                "design_id": design.design_id,
                "safety": safety,
            }
        ),
        source_evidence_ids=evidence_ids,
        source_content_hashes=content_hashes,
        treatment_phase=phase,
        population_alignment_sha256=alignment_hash,
        eligibility_status=_eligibility(canonical_reasons),
        exclusion_reasons=canonical_reasons,
    )


def _endpoint_pair(
    left: ClinicalEndpointReviewCandidate,
    right: ClinicalEndpointReviewCandidate,
) -> ClinicalEndpointPairReviewCandidate:
    if left.endpoint_id > right.endpoint_id:
        left, right = right, left
    facts = _pair_facts(left, right)
    return ClinicalEndpointPairReviewCandidate(
        pair_id=_sha256(
            {
                "trial_id": left.trial_id,
                "design_id": left.design_id,
                "left_endpoint_id": left.endpoint_id,
                "right_endpoint_id": right.endpoint_id,
            }
        ),
        trial_id=left.trial_id,
        design_id=left.design_id,
        left_endpoint_id=left.endpoint_id,
        right_endpoint_id=right.endpoint_id,
        left_population_id=left.population_id,
        right_population_id=right.population_id,
        left_population_record_sha256=left.population_record_sha256,
        right_population_record_sha256=right.population_record_sha256,
        left_endpoint_time_frame=left.time_frame,
        right_endpoint_time_frame=right.time_frame,
        left_treatment_phase=left.treatment_phase,
        right_treatment_phase=right.treatment_phase,
        left_population_alignment_sha256=left.population_alignment_sha256,
        right_population_alignment_sha256=right.population_alignment_sha256,
        left_source_content_hashes=left.source_content_hashes,
        right_source_content_hashes=right.source_content_hashes,
        **facts,
    )


def _endpoint_safety_link(
    design: TrialDesignRecord,
    endpoint_record: TrialEndpointRecord,
    endpoint: ClinicalEndpointReviewCandidate,
    safety_record: TrialSafetyRecord,
    safety: ClinicalSafetyReviewCandidate,
) -> ClinicalEndpointSafetyReviewLink:
    try:
        alignment = validate_phase_bound_population_alignment(
            design,
            endpoint_record,
            safety_record,
        )
    except ClinicalPopulationAlignmentError:
        alignment_status = POPULATION_ALIGNMENT_INVALID
    else:
        alignment_status = (
            LEGACY_PHASE_UNDECLARED
            if alignment is None
            else PHASE_BOUND_ALIGNMENT_VALID
        )
    safety_arm_ids = tuple(item.arm_id for item in safety.arm_summaries)
    return ClinicalEndpointSafetyReviewLink(
        link_id=_sha256(
            {
                "trial_id": design.trial_id,
                "design_id": design.design_id,
                "endpoint_id": endpoint.endpoint_id,
                "safety_id": safety.safety_id,
            }
        ),
        trial_id=design.trial_id,
        design_id=design.design_id,
        endpoint_id=endpoint.endpoint_id,
        safety_id=safety.safety_id,
        population_id=endpoint.population_id,
        endpoint_time_frame=endpoint.time_frame,
        safety_time_frame=safety.time_frame,
        endpoint_arm_ids=endpoint.arm_ids,
        safety_arm_ids=safety_arm_ids,
        endpoint_treatment_phase=endpoint.treatment_phase,
        safety_treatment_phase=safety.treatment_phase,
        endpoint_population_alignment_sha256=(endpoint.population_alignment_sha256),
        safety_population_alignment_sha256=safety.population_alignment_sha256,
        alignment_status=alignment_status,
        endpoint_arms_covered_by_safety=set(endpoint.arm_ids).issubset(safety_arm_ids),
        source_content_hashes=tuple(
            sorted(
                set(endpoint.source_content_hashes) | set(safety.source_content_hashes)
            )
        ),
    )


def compile_clinical_endpoint_review_candidate_packet(
    state: ProgramState,
    spec: ClinicalEndpointReviewCandidateSpec,
) -> ClinicalEndpointReviewCandidatePacket:
    """Enumerate every in-scope record and candidate relationship from state."""

    _require_instance(state, ProgramState, "state")
    _require_instance(spec, ClinicalEndpointReviewCandidateSpec, "spec")
    designs = _resolve_designs(state, spec)
    source_registry: dict[str, ClinicalReviewSourceEvidence] = {}
    populations: list[ClinicalPopulationReviewCandidate] = []
    endpoints: list[ClinicalEndpointReviewCandidate] = []
    safety_records: list[ClinicalSafetyReviewCandidate] = []
    pairs: list[ClinicalEndpointPairReviewCandidate] = []
    links: list[ClinicalEndpointSafetyReviewLink] = []

    for design in designs:
        _record_provenance(state, design.supporting_evidence, source_registry)
        for arm in design.arms:
            _record_provenance(state, arm.supporting_evidence, source_registry)
        endpoint_records_by_id = {item.endpoint_id: item for item in design.endpoints}
        safety_records_by_id = {item.safety_id: item for item in design.safety_records}
        posted_endpoint_ids_by_population: dict[str, list[str]] = {
            item.population_id: [] for item in design.populations
        }
        for endpoint in design.endpoints:
            if _normalized(endpoint.reporting_status) == "posted":
                posted_endpoint_ids_by_population[endpoint.population_id].append(
                    endpoint.endpoint_id
                )
        population_candidates_by_id: dict[str, ClinicalPopulationReviewCandidate] = {}
        for population in design.populations:
            candidate = _population_candidate(
                state,
                design,
                population,
                tuple(
                    sorted(posted_endpoint_ids_by_population[population.population_id])
                ),
                source_registry,
            )
            populations.append(candidate)
            population_candidates_by_id[candidate.population_id] = candidate
        endpoint_candidates: list[ClinicalEndpointReviewCandidate] = []
        for endpoint_record in design.endpoints:
            population = population_candidates_by_id.get(endpoint_record.population_id)
            if population is None:
                raise ClinicalEndpointReviewCandidateError(
                    "endpoint population is absent from exhaustive design scope"
                )
            candidate = _endpoint_candidate(
                state,
                design,
                endpoint_record,
                population.record_sha256,
                source_registry,
            )
            endpoints.append(candidate)
            endpoint_candidates.append(candidate)
        safety_candidates: list[ClinicalSafetyReviewCandidate] = []
        for safety_record in design.safety_records:
            for arm_summary in safety_record.arm_summaries:
                _record_provenance(
                    state,
                    arm_summary.supporting_evidence,
                    source_registry,
                )
            candidate = _safety_candidate(
                state,
                design,
                safety_record,
                source_registry,
            )
            safety_records.append(candidate)
            safety_candidates.append(candidate)
        eligible_endpoints = tuple(
            sorted(
                (
                    item
                    for item in endpoint_candidates
                    if item.eligibility_status == REVIEW_CANDIDATE
                ),
                key=lambda item: item.endpoint_id,
            )
        )
        eligible_safety = tuple(
            sorted(
                (
                    item
                    for item in safety_candidates
                    if item.eligibility_status == REVIEW_CANDIDATE
                ),
                key=lambda item: item.safety_id,
            )
        )
        pairs.extend(
            _endpoint_pair(left, right)
            for left, right in combinations(eligible_endpoints, 2)
        )
        links.extend(
            _endpoint_safety_link(
                design,
                endpoint_records_by_id[endpoint.endpoint_id],
                endpoint,
                safety_records_by_id[safety.safety_id],
                safety,
            )
            for endpoint, safety in product(eligible_endpoints, eligible_safety)
        )

    ordered_populations = tuple(
        sorted(
            populations,
            key=lambda item: (item.trial_id, item.design_id, item.population_id),
        )
    )
    ordered_endpoints = tuple(
        sorted(
            endpoints,
            key=lambda item: (item.trial_id, item.design_id, item.endpoint_id),
        )
    )
    ordered_safety = tuple(
        sorted(
            safety_records,
            key=lambda item: (item.trial_id, item.design_id, item.safety_id),
        )
    )
    ordered_pairs = tuple(
        sorted(
            pairs,
            key=lambda item: (
                item.trial_id,
                item.design_id,
                item.left_endpoint_id,
                item.right_endpoint_id,
            ),
        )
    )
    ordered_links = tuple(
        sorted(
            links,
            key=lambda item: (
                item.trial_id,
                item.design_id,
                item.endpoint_id,
                item.safety_id,
            ),
        )
    )
    count_values = {
        "design_count": len(designs),
        "source_evidence_count": len(source_registry),
        "population_record_count": len(ordered_populations),
        "population_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE for item in ordered_populations
        ),
        "population_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED
            for item in ordered_populations
        ),
        "endpoint_record_count": len(ordered_endpoints),
        "endpoint_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE for item in ordered_endpoints
        ),
        "endpoint_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED
            for item in ordered_endpoints
        ),
        "safety_record_count": len(ordered_safety),
        "safety_candidate_count": sum(
            item.eligibility_status == REVIEW_CANDIDATE for item in ordered_safety
        ),
        "safety_excluded_count": sum(
            item.eligibility_status == MECHANICALLY_EXCLUDED for item in ordered_safety
        ),
        "endpoint_pair_count": len(ordered_pairs),
        "endpoint_safety_link_count": len(ordered_links),
    }
    return ClinicalEndpointReviewCandidatePacket(
        packet_id=spec.packet_id,
        program_id=state.program_id,
        candidate_id=spec.candidate_id,
        intervention_id=spec.intervention_id,
        disease_id=spec.disease_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        state_sha256=_sha256(state),
        design_ids=spec.design_ids,
        source_evidence=tuple(
            source_registry[item] for item in sorted(source_registry)
        ),
        populations=ordered_populations,
        endpoints=ordered_endpoints,
        safety_records=ordered_safety,
        endpoint_pairs=ordered_pairs,
        endpoint_safety_links=ordered_links,
        **count_values,
        full_record_enumeration_performed=True,
        full_state_replay_required=True,
        reviewer_approval_performed=False,
        endpoint_family_assigned=False,
        ontology_mapping_approved=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        comparative_safety_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinical_endpoint_review_candidate_packet(
    state: ProgramState,
    spec: ClinicalEndpointReviewCandidateSpec,
    packet: ClinicalEndpointReviewCandidatePacket,
) -> tuple[str, ...]:
    """Recompile a candidate packet and return deterministic failure codes."""

    try:
        rebuilt = compile_clinical_endpoint_review_candidate_packet(state, spec)
    except (ClinicalEndpointReviewCandidateError, TypeError, ValueError):
        return ("clinical_endpoint_review_candidate_recompile_failed",)
    if rebuilt != packet:
        return ("clinical_endpoint_review_candidate_packet_mismatch",)
    return ()


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(
    value: Any,
    path: str,
    expected_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalEndpointReviewCandidateError(f"{path} must be an object")
    if set(value) != expected_fields:
        raise ClinicalEndpointReviewCandidateError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return dict(value)


def _reject_constant(value: str) -> None:
    raise ClinicalEndpointReviewCandidateError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalEndpointReviewCandidateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalEndpointReviewCandidateError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalEndpointReviewCandidateError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ClinicalEndpointReviewCandidateError(
            "endpoint review candidate JSON must be an object"
        )
    return value


def clinical_endpoint_review_candidate_spec_to_dict(
    spec: ClinicalEndpointReviewCandidateSpec,
) -> dict[str, Any]:
    """Return a strict JSON-schema-ready candidate enumeration declaration."""

    _require_instance(spec, ClinicalEndpointReviewCandidateSpec, "spec")
    value = to_primitive(spec)
    if not isinstance(value, dict):
        raise TypeError("serialized candidate spec must be an object")
    return {
        "schema_version": CLINICAL_ENDPOINT_REVIEW_CANDIDATE_SPEC_SCHEMA_VERSION,
        **value,
    }


def clinical_endpoint_review_candidate_spec_from_dict(
    value: Any,
) -> ClinicalEndpointReviewCandidateSpec:
    """Parse a strict candidate enumeration declaration."""

    expected = {"schema_version", *_field_names(ClinicalEndpointReviewCandidateSpec)}
    data = _record(value, "spec", expected)
    if data.pop("schema_version") != (
        CLINICAL_ENDPOINT_REVIEW_CANDIDATE_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalEndpointReviewCandidateError("unsupported spec schema_version")
    return ClinicalEndpointReviewCandidateSpec(**data)


def clinical_endpoint_review_candidate_spec_from_json(
    text: str,
) -> ClinicalEndpointReviewCandidateSpec:
    """Parse strict JSON without duplicate keys or non-finite constants."""

    return clinical_endpoint_review_candidate_spec_from_dict(_load_json(text))


def clinical_endpoint_review_candidate_packet_envelope(
    packet: ClinicalEndpointReviewCandidatePacket,
) -> dict[str, Any]:
    """Return the strict integrity envelope for one candidate packet."""

    _require_instance(packet, ClinicalEndpointReviewCandidatePacket, "packet")
    return {
        "schema_version": CLINICAL_ENDPOINT_REVIEW_CANDIDATE_PACKET_SCHEMA_VERSION,
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _source_from_dict(value: Any, path: str) -> ClinicalReviewSourceEvidence:
    data = _record(value, path, _field_names(ClinicalReviewSourceEvidence))
    return ClinicalReviewSourceEvidence(**data)


def _population_from_dict(
    value: Any,
    path: str,
) -> ClinicalPopulationReviewCandidate:
    data = _record(value, path, _field_names(ClinicalPopulationReviewCandidate))
    return ClinicalPopulationReviewCandidate(**data)


def _endpoint_from_dict(
    value: Any,
    path: str,
) -> ClinicalEndpointReviewCandidate:
    data = _record(value, path, _field_names(ClinicalEndpointReviewCandidate))
    return ClinicalEndpointReviewCandidate(**data)


def _safety_arm_from_dict(
    value: Any,
    path: str,
) -> ClinicalSafetyArmReviewCandidate:
    data = _record(value, path, _field_names(ClinicalSafetyArmReviewCandidate))
    return ClinicalSafetyArmReviewCandidate(**data)


def _safety_from_dict(
    value: Any,
    path: str,
) -> ClinicalSafetyReviewCandidate:
    data = _record(value, path, _field_names(ClinicalSafetyReviewCandidate))
    data["arm_summaries"] = tuple(
        _safety_arm_from_dict(item, f"{path}.arm_summaries[{index}]")
        for index, item in enumerate(_tuple(data["arm_summaries"], "arm_summaries"))
    )
    return ClinicalSafetyReviewCandidate(**data)


def _pair_from_dict(
    value: Any,
    path: str,
) -> ClinicalEndpointPairReviewCandidate:
    data = _record(value, path, _field_names(ClinicalEndpointPairReviewCandidate))
    return ClinicalEndpointPairReviewCandidate(**data)


def _link_from_dict(
    value: Any,
    path: str,
) -> ClinicalEndpointSafetyReviewLink:
    data = _record(value, path, _field_names(ClinicalEndpointSafetyReviewLink))
    return ClinicalEndpointSafetyReviewLink(**data)


def clinical_endpoint_review_candidate_packet_from_dict(
    value: Any,
) -> ClinicalEndpointReviewCandidatePacket:
    """Parse and integrity-check one strict candidate packet envelope."""

    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "packet"},
    )
    if envelope["schema_version"] != (
        CLINICAL_ENDPOINT_REVIEW_CANDIDATE_PACKET_SCHEMA_VERSION
    ):
        raise ClinicalEndpointReviewCandidateError(
            "unsupported candidate packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalEndpointReviewCandidatePacket),
    )
    data["source_evidence"] = tuple(
        _source_from_dict(item, f"packet.source_evidence[{index}]")
        for index, item in enumerate(_tuple(data["source_evidence"], "source_evidence"))
    )
    data["populations"] = tuple(
        _population_from_dict(item, f"packet.populations[{index}]")
        for index, item in enumerate(_tuple(data["populations"], "populations"))
    )
    data["endpoints"] = tuple(
        _endpoint_from_dict(item, f"packet.endpoints[{index}]")
        for index, item in enumerate(_tuple(data["endpoints"], "endpoints"))
    )
    data["safety_records"] = tuple(
        _safety_from_dict(item, f"packet.safety_records[{index}]")
        for index, item in enumerate(_tuple(data["safety_records"], "safety_records"))
    )
    data["endpoint_pairs"] = tuple(
        _pair_from_dict(item, f"packet.endpoint_pairs[{index}]")
        for index, item in enumerate(_tuple(data["endpoint_pairs"], "endpoint_pairs"))
    )
    data["endpoint_safety_links"] = tuple(
        _link_from_dict(item, f"packet.endpoint_safety_links[{index}]")
        for index, item in enumerate(
            _tuple(data["endpoint_safety_links"], "endpoint_safety_links")
        )
    )
    packet = ClinicalEndpointReviewCandidatePacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalEndpointReviewCandidateError("integrity_sha256 mismatch")
    return packet


def clinical_endpoint_review_candidate_packet_from_json(
    text: str,
) -> ClinicalEndpointReviewCandidatePacket:
    """Parse strict candidate packet JSON with duplicate-key rejection."""

    return clinical_endpoint_review_candidate_packet_from_dict(_load_json(text))


def clinical_endpoint_review_candidate_packet_summary(
    packet: ClinicalEndpointReviewCandidatePacket,
) -> dict[str, Any]:
    """Return a compact human- and machine-readable packet summary."""

    _require_instance(packet, ClinicalEndpointReviewCandidatePacket, "packet")
    return {
        "packet_id": packet.packet_id,
        "program_id": packet.program_id,
        "design_count": packet.design_count,
        "population_record_count": packet.population_record_count,
        "population_candidate_count": packet.population_candidate_count,
        "population_excluded_count": packet.population_excluded_count,
        "endpoint_record_count": packet.endpoint_record_count,
        "endpoint_candidate_count": packet.endpoint_candidate_count,
        "endpoint_excluded_count": packet.endpoint_excluded_count,
        "safety_record_count": packet.safety_record_count,
        "safety_candidate_count": packet.safety_candidate_count,
        "safety_excluded_count": packet.safety_excluded_count,
        "endpoint_pair_count": packet.endpoint_pair_count,
        "endpoint_safety_link_count": packet.endpoint_safety_link_count,
        "reviewer_approval_performed": packet.reviewer_approval_performed,
        "endpoint_family_assigned": packet.endpoint_family_assigned,
        "benefit_risk_synthesis_performed": (packet.benefit_risk_synthesis_performed),
        "integrity_sha256": packet.fingerprint,
    }
