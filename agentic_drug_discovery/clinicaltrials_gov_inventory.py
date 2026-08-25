"""Registry-record-wide ClinicalTrials.gov outcome and safety inventory.

The inventory is deliberately pre-review. It enumerates bounded public registry
fields and exact lexical link candidates without selecting endpoints or making
clinical, causal, or benefit-risk claims.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

from .ingestion import SourceBundle, verify_source_payload
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_INVENTORY_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-inventory-spec.v1"
)
CLINICALTRIALS_GOV_INVENTORY_PACKET_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-inventory-packet.v1"
)
CLINICALTRIALS_GOV_INVENTORY_POLICY_ID = (
    "adds.clinicaltrials-gov-registry-record-wide-inventory.v1"
)

UNMATCHED = "unmatched"
UNIQUE_EXACT_CANDIDATE = "unique_exact_candidate"
AMBIGUOUS_EXACT_CANDIDATES = "ambiguous_exact_candidates"

_MATCH_STATUSES = frozenset(
    {UNMATCHED, UNIQUE_EXACT_CANDIDATE, AMBIGUOUS_EXACT_CANDIDATES}
)
_PROTOCOL_OUTCOME_FIELDS = (
    ("primaryOutcomes", "PRIMARY", "primary"),
    ("secondaryOutcomes", "SECONDARY", "secondary"),
    ("otherOutcomes", "OTHER", "other"),
)
_REQUIRED_LIMITATIONS = (
    (
        "Completeness is limited to arrays present in one exact ClinicalTrials.gov "
        "API snapshot and does not establish registry, sponsor, or historical "
        "record completeness."
    ),
    (
        "Exact lexical links use normalized title and time-frame text only; they "
        "do not approve endpoint identity, family, ontology, estimand, or semantic "
        "equivalence."
    ),
    (
        "The inventory does not select a primary analysis, arm comparison, "
        "population, effect estimate, or clinically relevant endpoint."
    ),
    (
        "Safety event and group counts are registry fields, not evidence of "
        "causality, common risk windows, comparative safety, or acceptability."
    ),
    (
        "No pooling, utility weighting, regulatory inference, benefit-risk "
        "synthesis, or treatment choice is performed."
    ),
)

_NCT_ID = re.compile(r"^NCT[0-9]{8}$")


class ClinicalTrialsGovInventoryError(ValueError):
    """Raised when a registry inventory cannot be compiled or replayed."""


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


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovInventoryError(f"{path} must be an object")
    return dict(value)


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ClinicalTrialsGovInventoryError(f"{path} must be an array")
    return list(value)


def _optional_array(value: Mapping[str, Any], key: str, path: str) -> list[Any]:
    if key not in value:
        return []
    return _array(value[key], f"{path}.{key}")


def _source_text(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ClinicalTrialsGovInventoryError(f"{path} must be text or null")
    return value


def _source_int(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ClinicalTrialsGovInventoryError(
            f"{path} must be a non-negative integer or null"
        )
    return value


def _description_hash(value: Mapping[str, Any], key: str, path: str) -> str | None:
    if key not in value or value[key] is None:
        return None
    description = _source_text(value[key], f"{path}.{key}")
    assert description is not None
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _lexical_key(title: str | None, time_frame: str | None) -> tuple[str, str] | None:
    if title is None or time_frame is None:
        return None
    normalized = (_normalized(title), _normalized(time_frame))
    if not all(normalized):
        return None
    return normalized


def _match_status(count: int) -> str:
    if count == 0:
        return UNMATCHED
    if count == 1:
        return UNIQUE_EXACT_CANDIDATE
    return AMBIGUOUS_EXACT_CANDIDATES


def _require_optional_text(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be text or null")


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_optional_non_negative_int(value: Any, field_name: str) -> None:
    if value is not None:
        _require_non_negative_int(value, field_name)


def _require_tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def _text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    result = _require_tuple(value, field_name)
    for item in result:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be text")
    return result


def _pointer(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if not value.startswith("/"):
        raise ValueError(f"{field_name} must be an absolute JSON pointer")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovInventorySpec(SerializableRecord):
    """Exact study snapshot scope for one registry-record-wide inventory."""

    inventory_id: str
    source_receipt_id: str
    nct_id: str
    registry_version: str
    policy_id: str = CLINICALTRIALS_GOV_INVENTORY_POLICY_ID

    def __post_init__(self) -> None:
        for field_name in (
            "inventory_id",
            "source_receipt_id",
            "nct_id",
            "registry_version",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        try:
            parsed = date.fromisoformat(self.registry_version)
        except ValueError as exc:
            raise ValueError("registry_version must be an ISO calendar date") from exc
        if parsed.isoformat() != self.registry_version:
            raise ValueError("registry_version must use YYYY-MM-DD")
        if self.policy_id != CLINICALTRIALS_GOV_INVENTORY_POLICY_ID:
            raise ValueError("unsupported ClinicalTrials.gov inventory policy_id")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovInventorySource(SerializableRecord):
    receipt_id: str
    source_id: str
    source_version: str
    locator: str
    content_hash_sha256: str
    byte_size: int
    retrieved_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "receipt_id",
            "source_id",
            "source_version",
            "locator",
            "retrieved_at",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.content_hash_sha256, "content_hash_sha256")
        _require_non_negative_int(self.byte_size, "byte_size")
        if self.byte_size == 0:
            raise ValueError("byte_size must be positive")
        try:
            retrieved_at = datetime.fromisoformat(
                self.retrieved_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("retrieved_at must be an ISO 8601 timestamp") from exc
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")


@dataclass(frozen=True, slots=True)
class ProtocolOutcomeInventoryRecord(SerializableRecord):
    protocol_outcome_id: str
    outcome_type: str
    source_index: int
    source_json_pointer: str
    measure: str | None
    time_frame: str | None
    description_sha256: str | None
    source_record_sha256: str
    exact_candidate_count: int
    reconciliation_status: str
    endpoint_selected: bool = False
    endpoint_family_assigned: bool = False
    semantic_equivalence_approved: bool = False

    def __post_init__(self) -> None:
        _require_text(self.protocol_outcome_id, "protocol_outcome_id")
        if self.outcome_type not in {"PRIMARY", "SECONDARY", "OTHER"}:
            raise ValueError("unsupported protocol outcome_type")
        _require_non_negative_int(self.source_index, "source_index")
        _pointer(self.source_json_pointer, "source_json_pointer")
        _require_optional_text(self.measure, "measure")
        _require_optional_text(self.time_frame, "time_frame")
        if self.description_sha256 is not None:
            _require_sha256(self.description_sha256, "description_sha256")
        _require_sha256(self.source_record_sha256, "source_record_sha256")
        _require_non_negative_int(self.exact_candidate_count, "exact_candidate_count")
        if self.reconciliation_status != _match_status(self.exact_candidate_count):
            raise ValueError("protocol reconciliation status/count mismatch")
        for field_name in (
            "endpoint_selected",
            "endpoint_family_assigned",
            "semantic_equivalence_approved",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class PostedOutcomeInventoryRecord(SerializableRecord):
    posted_outcome_id: str
    source_index: int
    source_json_pointer: str
    outcome_type: str | None
    title: str | None
    time_frame: str | None
    reporting_status: str | None
    parameter_type: str | None
    dispersion_type: str | None
    unit_of_measure: str | None
    description_sha256: str | None
    population_description_sha256: str | None
    group_ids: tuple[str, ...]
    denominator_group_ids: tuple[str, ...]
    measurement_group_ids: tuple[str, ...]
    analysis_group_id_sets: tuple[tuple[str, ...], ...]
    group_count: int
    denominator_count: int
    class_count: int
    category_count: int
    measurement_count: int
    analysis_count: int
    source_record_sha256: str
    exact_candidate_count: int
    reconciliation_status: str
    endpoint_selected: bool = False
    endpoint_family_assigned: bool = False
    semantic_equivalence_approved: bool = False

    def __post_init__(self) -> None:
        _require_text(self.posted_outcome_id, "posted_outcome_id")
        _require_non_negative_int(self.source_index, "source_index")
        _pointer(self.source_json_pointer, "source_json_pointer")
        for field_name in (
            "outcome_type",
            "title",
            "time_frame",
            "reporting_status",
            "parameter_type",
            "dispersion_type",
            "unit_of_measure",
        ):
            _require_optional_text(getattr(self, field_name), field_name)
        for field_name in ("description_sha256", "population_description_sha256"):
            value = getattr(self, field_name)
            if value is not None:
                _require_sha256(value, field_name)
        for field_name in (
            "group_ids",
            "denominator_group_ids",
            "measurement_group_ids",
        ):
            object.__setattr__(
                self, field_name, _text_tuple(getattr(self, field_name), field_name)
            )
        analysis_sets = _require_tuple(
            self.analysis_group_id_sets, "analysis_group_id_sets"
        )
        object.__setattr__(
            self,
            "analysis_group_id_sets",
            tuple(
                _text_tuple(item, f"analysis_group_id_sets[{index}]")
                for index, item in enumerate(analysis_sets)
            ),
        )
        for field_name in (
            "group_count",
            "denominator_count",
            "class_count",
            "category_count",
            "measurement_count",
            "analysis_count",
            "exact_candidate_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.analysis_count != len(self.analysis_group_id_sets):
            raise ValueError("analysis_count does not match analysis_group_id_sets")
        if self.group_count < len(self.group_ids):
            raise ValueError("group_ids exceed source group_count")
        if self.measurement_count < len(self.measurement_group_ids):
            raise ValueError("measurement_group_ids exceed source measurement_count")
        _require_sha256(self.source_record_sha256, "source_record_sha256")
        if self.reconciliation_status != _match_status(self.exact_candidate_count):
            raise ValueError("posted reconciliation status/count mismatch")
        for field_name in (
            "endpoint_selected",
            "endpoint_family_assigned",
            "semantic_equivalence_approved",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class OutcomeLexicalLinkCandidate(SerializableRecord):
    link_id: str
    protocol_outcome_id: str
    posted_outcome_id: str
    lexical_key_sha256: str
    outcome_type_exact_match: bool
    endpoint_identity_approved: bool = False
    semantic_equivalence_approved: bool = False
    clinical_comparability_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in ("link_id", "protocol_outcome_id", "posted_outcome_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.lexical_key_sha256, "lexical_key_sha256")
        for field_name in (
            "outcome_type_exact_match",
            "endpoint_identity_approved",
            "semantic_equivalence_approved",
            "clinical_comparability_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        for field_name in (
            "endpoint_identity_approved",
            "semantic_equivalence_approved",
            "clinical_comparability_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class SafetyGroupInventoryRecord(SerializableRecord):
    safety_group_record_id: str
    source_index: int
    source_json_pointer: str
    source_group_id: str | None
    title: str | None
    description_sha256: str | None
    serious_num_affected: int | None
    serious_num_at_risk: int | None
    other_num_affected: int | None
    other_num_at_risk: int | None
    source_record_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.safety_group_record_id, "safety_group_record_id")
        _require_non_negative_int(self.source_index, "source_index")
        _pointer(self.source_json_pointer, "source_json_pointer")
        _require_optional_text(self.source_group_id, "source_group_id")
        _require_optional_text(self.title, "title")
        if self.description_sha256 is not None:
            _require_sha256(self.description_sha256, "description_sha256")
        for field_name in (
            "serious_num_affected",
            "serious_num_at_risk",
            "other_num_affected",
            "other_num_at_risk",
        ):
            _require_optional_non_negative_int(getattr(self, field_name), field_name)
        _require_sha256(self.source_record_sha256, "source_record_sha256")


@dataclass(frozen=True, slots=True)
class SafetyEventStatInventoryRecord(SerializableRecord):
    stat_id: str
    source_index: int
    source_json_pointer: str
    source_group_id: str | None
    num_affected: int | None
    num_at_risk: int | None
    num_events: int | None
    source_record_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.stat_id, "stat_id")
        _require_non_negative_int(self.source_index, "source_index")
        _pointer(self.source_json_pointer, "source_json_pointer")
        _require_optional_text(self.source_group_id, "source_group_id")
        for field_name in ("num_affected", "num_at_risk", "num_events"):
            _require_optional_non_negative_int(getattr(self, field_name), field_name)
        _require_sha256(self.source_record_sha256, "source_record_sha256")


@dataclass(frozen=True, slots=True)
class SafetyEventInventoryRecord(SerializableRecord):
    safety_event_id: str
    event_category: str
    source_index: int
    source_json_pointer: str
    term: str | None
    organ_system: str | None
    assessment_type: str | None
    notes_sha256: str | None
    stats: tuple[SafetyEventStatInventoryRecord, ...]
    source_record_sha256: str
    causal_relationship_inferred: bool = False
    comparative_safety_inferred: bool = False

    def __post_init__(self) -> None:
        _require_text(self.safety_event_id, "safety_event_id")
        if self.event_category not in {"SERIOUS", "OTHER"}:
            raise ValueError("event_category must be SERIOUS or OTHER")
        _require_non_negative_int(self.source_index, "source_index")
        _pointer(self.source_json_pointer, "source_json_pointer")
        for field_name in ("term", "organ_system", "assessment_type"):
            _require_optional_text(getattr(self, field_name), field_name)
        if self.notes_sha256 is not None:
            _require_sha256(self.notes_sha256, "notes_sha256")
        stats = _require_tuple(self.stats, "stats")
        if any(not isinstance(item, SafetyEventStatInventoryRecord) for item in stats):
            raise TypeError("stats must contain SafetyEventStatInventoryRecord values")
        object.__setattr__(self, "stats", stats)
        _require_sha256(self.source_record_sha256, "source_record_sha256")
        for field_name in (
            "causal_relationship_inferred",
            "comparative_safety_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovInventoryPacket(SerializableRecord):
    inventory_id: str
    policy_id: str
    spec_sha256: str
    source: ClinicalTrialsGovInventorySource
    nct_id: str
    registry_version: str
    source_has_results: bool
    protocol_outcome_module_present: bool
    posted_outcome_module_present: bool
    adverse_event_module_present: bool
    adverse_event_time_frame: str | None
    adverse_event_description_sha256: str | None
    adverse_event_frequency_threshold: str | None
    source_scope_sha256: str
    protocol_outcomes: tuple[ProtocolOutcomeInventoryRecord, ...]
    posted_outcomes: tuple[PostedOutcomeInventoryRecord, ...]
    lexical_link_candidates: tuple[OutcomeLexicalLinkCandidate, ...]
    safety_groups: tuple[SafetyGroupInventoryRecord, ...]
    serious_events: tuple[SafetyEventInventoryRecord, ...]
    other_events: tuple[SafetyEventInventoryRecord, ...]
    protocol_outcome_count: int
    posted_outcome_count: int
    lexical_link_candidate_count: int
    unmatched_protocol_outcome_count: int
    unmatched_posted_outcome_count: int
    ambiguous_protocol_outcome_count: int
    ambiguous_posted_outcome_count: int
    safety_group_count: int
    serious_event_count: int
    other_event_count: int
    safety_event_stat_count: int
    full_source_array_enumeration_performed: bool
    exact_lexical_reconciliation_only: bool
    reviewer_approval_performed: bool
    endpoint_selected: bool
    endpoint_family_assigned: bool
    ontology_mapping_approved: bool
    estimand_equivalence_inferred: bool
    clinical_comparability_inferred: bool
    comparative_safety_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.inventory_id, "inventory_id")
        if self.policy_id != CLINICALTRIALS_GOV_INVENTORY_POLICY_ID:
            raise ValueError("unsupported inventory policy_id")
        _require_sha256(self.spec_sha256, "spec_sha256")
        if not isinstance(self.source, ClinicalTrialsGovInventorySource):
            raise TypeError("source must be a ClinicalTrialsGovInventorySource")
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical form")
        try:
            if (
                date.fromisoformat(self.registry_version).isoformat()
                != self.registry_version
            ):
                raise ValueError
        except ValueError as exc:
            raise ValueError("registry_version must use YYYY-MM-DD") from exc
        for field_name in (
            "source_has_results",
            "protocol_outcome_module_present",
            "posted_outcome_module_present",
            "adverse_event_module_present",
            "full_source_array_enumeration_performed",
            "exact_lexical_reconciliation_only",
            "reviewer_approval_performed",
            "endpoint_selected",
            "endpoint_family_assigned",
            "ontology_mapping_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "comparative_safety_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.full_source_array_enumeration_performed:
            raise ValueError("full_source_array_enumeration_performed must be true")
        if not self.exact_lexical_reconciliation_only:
            raise ValueError("exact_lexical_reconciliation_only must be true")
        for field_name in (
            "reviewer_approval_performed",
            "endpoint_selected",
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
        for field_name in (
            "adverse_event_time_frame",
            "adverse_event_frequency_threshold",
        ):
            _require_optional_text(getattr(self, field_name), field_name)
        if self.adverse_event_description_sha256 is not None:
            _require_sha256(
                self.adverse_event_description_sha256,
                "adverse_event_description_sha256",
            )
        _require_sha256(self.source_scope_sha256, "source_scope_sha256")
        record_types = (
            ("protocol_outcomes", ProtocolOutcomeInventoryRecord),
            ("posted_outcomes", PostedOutcomeInventoryRecord),
            ("lexical_link_candidates", OutcomeLexicalLinkCandidate),
            ("safety_groups", SafetyGroupInventoryRecord),
            ("serious_events", SafetyEventInventoryRecord),
            ("other_events", SafetyEventInventoryRecord),
        )
        for field_name, record_type in record_types:
            values = _require_tuple(getattr(self, field_name), field_name)
            if any(not isinstance(item, record_type) for item in values):
                raise TypeError(f"{field_name} contains an invalid record")
            object.__setattr__(self, field_name, values)
        for item in self.serious_events:
            if item.event_category != "SERIOUS":
                raise ValueError("serious_events contains a non-serious record")
        for item in self.other_events:
            if item.event_category != "OTHER":
                raise ValueError("other_events contains a non-other record")
        counts = {
            "protocol_outcome_count": len(self.protocol_outcomes),
            "posted_outcome_count": len(self.posted_outcomes),
            "lexical_link_candidate_count": len(self.lexical_link_candidates),
            "unmatched_protocol_outcome_count": sum(
                item.reconciliation_status == UNMATCHED
                for item in self.protocol_outcomes
            ),
            "unmatched_posted_outcome_count": sum(
                item.reconciliation_status == UNMATCHED for item in self.posted_outcomes
            ),
            "ambiguous_protocol_outcome_count": sum(
                item.reconciliation_status == AMBIGUOUS_EXACT_CANDIDATES
                for item in self.protocol_outcomes
            ),
            "ambiguous_posted_outcome_count": sum(
                item.reconciliation_status == AMBIGUOUS_EXACT_CANDIDATES
                for item in self.posted_outcomes
            ),
            "safety_group_count": len(self.safety_groups),
            "serious_event_count": len(self.serious_events),
            "other_event_count": len(self.other_events),
            "safety_event_stat_count": sum(
                len(item.stats) for item in (*self.serious_events, *self.other_events)
            ),
        }
        for field_name, expected in counts.items():
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match packet records")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("inventory limitations were rebound")
        object.__setattr__(self, "limitations", limitations)
        protocol_ids = {item.protocol_outcome_id for item in self.protocol_outcomes}
        posted_ids = {item.posted_outcome_id for item in self.posted_outcomes}
        if len(protocol_ids) != len(self.protocol_outcomes):
            raise ValueError("protocol outcome ids must be unique")
        if len(posted_ids) != len(self.posted_outcomes):
            raise ValueError("posted outcome ids must be unique")
        expected_source_id = f"clinicaltrials-gov-{self.nct_id}"
        expected_source_version = (
            f"clinicaltrials-gov-{self.nct_id}-version-{self.registry_version}"
        )
        if (
            self.source.source_id != expected_source_id
            or self.source.source_version != expected_source_version
            or self.source.locator
            != f"https://clinicaltrials.gov/api/v2/studies/{self.nct_id}"
        ):
            raise ValueError("packet source identity is not canonical")
        if not self.protocol_outcome_module_present and self.protocol_outcomes:
            raise ValueError("protocol outcomes exist without a source module")
        if not self.posted_outcome_module_present and self.posted_outcomes:
            raise ValueError("posted outcomes exist without a source module")
        if not self.adverse_event_module_present and (
            self.safety_groups or self.serious_events or self.other_events
        ):
            raise ValueError("safety records exist without an adverse-event module")
        if not self.adverse_event_module_present and any(
            value is not None
            for value in (
                self.adverse_event_time_frame,
                self.adverse_event_description_sha256,
                self.adverse_event_frequency_threshold,
            )
        ):
            raise ValueError("adverse-event metadata exists without a source module")
        protocol_kind = {
            "PRIMARY": ("primary", "primaryOutcomes"),
            "SECONDARY": ("secondary", "secondaryOutcomes"),
            "OTHER": ("other", "otherOutcomes"),
        }
        for item in self.protocol_outcomes:
            id_kind, source_key = protocol_kind[item.outcome_type]
            if (
                item.protocol_outcome_id
                != f"{self.nct_id}:protocol:{id_kind}:{item.source_index}"
                or item.source_json_pointer
                != (f"/protocolSection/outcomesModule/{source_key}/{item.source_index}")
            ):
                raise ValueError("protocol outcome source identity was rebound")
        for expected_index, item in enumerate(self.posted_outcomes):
            if (
                item.source_index != expected_index
                or item.posted_outcome_id != f"{self.nct_id}:posted:{expected_index}"
                or item.source_json_pointer
                != (
                    "/resultsSection/outcomeMeasuresModule/outcomeMeasures/"
                    f"{expected_index}"
                )
            ):
                raise ValueError("posted outcome source identity was rebound")
        link_ids: set[str] = set()
        protocol_link_counts = {item: 0 for item in protocol_ids}
        posted_link_counts = {item: 0 for item in posted_ids}
        for link in self.lexical_link_candidates:
            if (
                link.link_id in link_ids
                or link.protocol_outcome_id not in protocol_ids
                or link.posted_outcome_id not in posted_ids
            ):
                raise ValueError("lexical link identity or reference is invalid")
            protocol_index = next(
                index
                for index, item in enumerate(self.protocol_outcomes)
                if item.protocol_outcome_id == link.protocol_outcome_id
            )
            posted_index = next(
                index
                for index, item in enumerate(self.posted_outcomes)
                if item.posted_outcome_id == link.posted_outcome_id
            )
            if link.link_id != (
                f"{self.nct_id}:lexical-link:{protocol_index}:{posted_index}"
            ):
                raise ValueError("lexical link identity or reference is invalid")
            link_ids.add(link.link_id)
            protocol_link_counts[link.protocol_outcome_id] += 1
            posted_link_counts[link.posted_outcome_id] += 1
        if any(
            item.exact_candidate_count != protocol_link_counts[item.protocol_outcome_id]
            for item in self.protocol_outcomes
        ) or any(
            item.exact_candidate_count != posted_link_counts[item.posted_outcome_id]
            for item in self.posted_outcomes
        ):
            raise ValueError("lexical link counts do not match outcome records")
        safety_ids: set[str] = set()
        for expected_index, item in enumerate(self.safety_groups):
            if (
                item.safety_group_record_id in safety_ids
                or item.source_index != expected_index
                or item.safety_group_record_id
                != f"{self.nct_id}:safety-group:{expected_index}"
                or item.source_json_pointer
                != f"/resultsSection/adverseEventsModule/eventGroups/{expected_index}"
            ):
                raise ValueError("safety group source identity was rebound")
            safety_ids.add(item.safety_group_record_id)
        event_ids: set[str] = set()
        stat_ids: set[str] = set()
        for category, source_key, id_kind, events in (
            ("SERIOUS", "seriousEvents", "serious", self.serious_events),
            ("OTHER", "otherEvents", "other", self.other_events),
        ):
            for expected_index, item in enumerate(events):
                expected_event_id = f"{self.nct_id}:safety:{id_kind}:{expected_index}"
                expected_pointer = (
                    f"/resultsSection/adverseEventsModule/{source_key}/{expected_index}"
                )
                if (
                    item.safety_event_id in event_ids
                    or item.event_category != category
                    or item.source_index != expected_index
                    or item.safety_event_id != expected_event_id
                    or item.source_json_pointer != expected_pointer
                ):
                    raise ValueError("safety event source identity was rebound")
                event_ids.add(item.safety_event_id)
                for expected_stat_index, stat in enumerate(item.stats):
                    if (
                        stat.stat_id in stat_ids
                        or stat.source_index != expected_stat_index
                        or stat.stat_id
                        != f"{expected_event_id}:stat:{expected_stat_index}"
                        or stat.source_json_pointer
                        != f"{expected_pointer}/stats/{expected_stat_index}"
                    ):
                        raise ValueError("safety stat source identity was rebound")
                    stat_ids.add(stat.stat_id)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovInventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovInventoryError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovInventoryError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovInventoryError(f"invalid {label} JSON: {exc}") from exc
    return _mapping(value, label)


def _validate_bundle(
    spec: ClinicalTrialsGovInventorySpec, bundle: SourceBundle
) -> None:
    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    verify_source_payload(bundle.receipt, bundle.payload)
    receipt = bundle.receipt
    if receipt.receipt_id != spec.source_receipt_id:
        raise ClinicalTrialsGovInventoryError("source receipt_id does not match spec")
    if receipt.media_type.casefold() not in {
        "application/json",
        "application/json; charset=utf-8",
    }:
        raise ClinicalTrialsGovInventoryError("source must use application/json")
    parsed = urllib.parse.urlsplit(receipt.locator)
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "clinicaltrials.gov"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != f"/api/v2/studies/{spec.nct_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise ClinicalTrialsGovInventoryError(
            "locator must be the exact ClinicalTrials.gov study API URL"
        )
    if receipt.source_id != f"clinicaltrials-gov-{spec.nct_id}":
        raise ClinicalTrialsGovInventoryError("source_id is not canonical")
    expected_version = (
        f"clinicaltrials-gov-{spec.nct_id}-version-{spec.registry_version}"
    )
    if receipt.source_version != expected_version:
        raise ClinicalTrialsGovInventoryError(
            "source_version does not bind the declared registry version"
        )
    if receipt.retrieved_at.date() < date.fromisoformat(spec.registry_version):
        raise ClinicalTrialsGovInventoryError(
            "source snapshot predates registry version"
        )


def _source_identity(
    spec: ClinicalTrialsGovInventorySpec,
    source: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    protocol = _mapping(source.get("protocolSection"), "protocolSection")
    identification = _mapping(
        protocol.get("identificationModule"), "protocolSection.identificationModule"
    )
    if identification.get("nctId") != spec.nct_id:
        raise ClinicalTrialsGovInventoryError("source nctId does not match spec")
    derived = _mapping(source.get("derivedSection"), "derivedSection")
    misc = _mapping(derived.get("miscInfoModule"), "derivedSection.miscInfoModule")
    if misc.get("versionHolder") != spec.registry_version:
        raise ClinicalTrialsGovInventoryError(
            "source versionHolder does not match spec"
        )
    has_results = source.get("hasResults")
    if not isinstance(has_results, bool):
        raise ClinicalTrialsGovInventoryError("source hasResults must be boolean")
    results_value = source.get("resultsSection")
    if results_value is None:
        results: dict[str, Any] = {}
    else:
        results = _mapping(results_value, "resultsSection")
    return protocol, results, has_results


def _protocol_source_records(
    nct_id: str,
    module: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source_key, outcome_type, id_kind in _PROTOCOL_OUTCOME_FIELDS:
        for index, raw in enumerate(
            _optional_array(module, source_key, "outcomesModule")
        ):
            record = _mapping(raw, f"outcomesModule.{source_key}[{index}]")
            result.append(
                {
                    "protocol_outcome_id": f"{nct_id}:protocol:{id_kind}:{index}",
                    "outcome_type": outcome_type,
                    "source_index": index,
                    "source_json_pointer": (
                        f"/protocolSection/outcomesModule/{source_key}/{index}"
                    ),
                    "measure": _source_text(
                        record.get("measure"), f"{source_key}[{index}].measure"
                    ),
                    "time_frame": _source_text(
                        record.get("timeFrame"), f"{source_key}[{index}].timeFrame"
                    ),
                    "description_sha256": _description_hash(
                        record, "description", f"{source_key}[{index}]"
                    ),
                    "source_record_sha256": _sha256(record),
                }
            )
    return result


def _ids_from_objects(
    values: list[Any],
    *,
    id_key: str,
    path: str,
) -> tuple[str, ...]:
    result: list[str] = []
    for index, raw in enumerate(values):
        record = _mapping(raw, f"{path}[{index}]")
        value = _source_text(record.get(id_key), f"{path}[{index}].{id_key}")
        if value is not None:
            result.append(value)
    return tuple(result)


def _posted_source_records(
    nct_id: str,
    module: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(
        _optional_array(module, "outcomeMeasures", "outcomeMeasuresModule")
    ):
        record = _mapping(raw, f"outcomeMeasures[{index}]")
        groups = _optional_array(record, "groups", f"outcomeMeasures[{index}]")
        denoms = _optional_array(record, "denoms", f"outcomeMeasures[{index}]")
        classes = _optional_array(record, "classes", f"outcomeMeasures[{index}]")
        analyses = _optional_array(record, "analyses", f"outcomeMeasures[{index}]")
        denominator_group_ids: list[str] = []
        for denom_index, raw_denom in enumerate(denoms):
            denom = _mapping(
                raw_denom, f"outcomeMeasures[{index}].denoms[{denom_index}]"
            )
            denominator_group_ids.extend(
                _ids_from_objects(
                    _optional_array(
                        denom,
                        "counts",
                        f"outcomeMeasures[{index}].denoms[{denom_index}]",
                    ),
                    id_key="groupId",
                    path=f"outcomeMeasures[{index}].denoms[{denom_index}].counts",
                )
            )
        category_count = 0
        measurement_count = 0
        measurement_group_ids: list[str] = []
        for class_index, raw_class in enumerate(classes):
            class_record = _mapping(
                raw_class, f"outcomeMeasures[{index}].classes[{class_index}]"
            )
            class_denoms = _optional_array(
                class_record,
                "denoms",
                f"outcomeMeasures[{index}].classes[{class_index}]",
            )
            for denom_index, raw_denom in enumerate(class_denoms):
                denom = _mapping(
                    raw_denom,
                    f"outcomeMeasures[{index}].classes[{class_index}].denoms[{denom_index}]",
                )
                denominator_group_ids.extend(
                    _ids_from_objects(
                        _optional_array(denom, "counts", "class denom"),
                        id_key="groupId",
                        path="class denom.counts",
                    )
                )
            categories = _optional_array(
                class_record,
                "categories",
                f"outcomeMeasures[{index}].classes[{class_index}]",
            )
            category_count += len(categories)
            for category_index, raw_category in enumerate(categories):
                category = _mapping(
                    raw_category,
                    (
                        f"outcomeMeasures[{index}].classes[{class_index}]"
                        f".categories[{category_index}]"
                    ),
                )
                measurements = _optional_array(
                    category, "measurements", "outcome category"
                )
                measurement_count += len(measurements)
                measurement_group_ids.extend(
                    _ids_from_objects(
                        measurements,
                        id_key="groupId",
                        path="outcome category.measurements",
                    )
                )
        analysis_group_id_sets: list[tuple[str, ...]] = []
        for analysis_index, raw_analysis in enumerate(analyses):
            analysis = _mapping(
                raw_analysis, f"outcomeMeasures[{index}].analyses[{analysis_index}]"
            )
            group_ids = analysis.get("groupIds")
            if group_ids is None:
                analysis_group_id_sets.append(())
            else:
                analysis_group_id_sets.append(
                    tuple(
                        value
                        for group_index, raw_group_id in enumerate(
                            _array(group_ids, "analysis.groupIds")
                        )
                        if (
                            value := _source_text(
                                raw_group_id,
                                f"analysis.groupIds[{group_index}]",
                            )
                        )
                        is not None
                    )
                )
        result.append(
            {
                "posted_outcome_id": f"{nct_id}:posted:{index}",
                "source_index": index,
                "source_json_pointer": (
                    f"/resultsSection/outcomeMeasuresModule/outcomeMeasures/{index}"
                ),
                "outcome_type": _source_text(record.get("type"), "outcome.type"),
                "title": _source_text(record.get("title"), "outcome.title"),
                "time_frame": _source_text(
                    record.get("timeFrame"), "outcome.timeFrame"
                ),
                "reporting_status": _source_text(
                    record.get("reportingStatus"), "outcome.reportingStatus"
                ),
                "parameter_type": _source_text(
                    record.get("paramType"), "outcome.paramType"
                ),
                "dispersion_type": _source_text(
                    record.get("dispersionType"), "outcome.dispersionType"
                ),
                "unit_of_measure": _source_text(
                    record.get("unitOfMeasure"), "outcome.unitOfMeasure"
                ),
                "description_sha256": _description_hash(
                    record, "description", f"outcomeMeasures[{index}]"
                ),
                "population_description_sha256": _description_hash(
                    record, "populationDescription", f"outcomeMeasures[{index}]"
                ),
                "group_ids": _ids_from_objects(
                    groups,
                    id_key="id",
                    path=f"outcomeMeasures[{index}].groups",
                ),
                "denominator_group_ids": tuple(denominator_group_ids),
                "measurement_group_ids": tuple(measurement_group_ids),
                "analysis_group_id_sets": tuple(analysis_group_id_sets),
                "group_count": len(groups),
                "denominator_count": len(denoms)
                + sum(
                    len(
                        _optional_array(
                            _mapping(item, "outcome class"),
                            "denoms",
                            "outcome class",
                        )
                    )
                    for item in classes
                ),
                "class_count": len(classes),
                "category_count": category_count,
                "measurement_count": measurement_count,
                "analysis_count": len(analyses),
                "source_record_sha256": _sha256(record),
            }
        )
    return result


def _safety_group_records(
    nct_id: str,
    module: Mapping[str, Any],
) -> tuple[SafetyGroupInventoryRecord, ...]:
    result: list[SafetyGroupInventoryRecord] = []
    for index, raw in enumerate(
        _optional_array(module, "eventGroups", "adverseEventsModule")
    ):
        record = _mapping(raw, f"adverseEventsModule.eventGroups[{index}]")
        result.append(
            SafetyGroupInventoryRecord(
                safety_group_record_id=f"{nct_id}:safety-group:{index}",
                source_index=index,
                source_json_pointer=(
                    f"/resultsSection/adverseEventsModule/eventGroups/{index}"
                ),
                source_group_id=_source_text(record.get("id"), "eventGroup.id"),
                title=_source_text(record.get("title"), "eventGroup.title"),
                description_sha256=_description_hash(
                    record, "description", "eventGroup"
                ),
                serious_num_affected=_source_int(
                    record.get("seriousNumAffected"), "eventGroup.seriousNumAffected"
                ),
                serious_num_at_risk=_source_int(
                    record.get("seriousNumAtRisk"), "eventGroup.seriousNumAtRisk"
                ),
                other_num_affected=_source_int(
                    record.get("otherNumAffected"), "eventGroup.otherNumAffected"
                ),
                other_num_at_risk=_source_int(
                    record.get("otherNumAtRisk"), "eventGroup.otherNumAtRisk"
                ),
                source_record_sha256=_sha256(record),
            )
        )
    return tuple(result)


def _safety_event_records(
    nct_id: str,
    module: Mapping[str, Any],
    *,
    source_key: str,
    category: str,
) -> tuple[SafetyEventInventoryRecord, ...]:
    result: list[SafetyEventInventoryRecord] = []
    id_kind = "serious" if category == "SERIOUS" else "other"
    for index, raw in enumerate(
        _optional_array(module, source_key, "adverseEventsModule")
    ):
        record = _mapping(raw, f"adverseEventsModule.{source_key}[{index}]")
        stats: list[SafetyEventStatInventoryRecord] = []
        for stat_index, raw_stat in enumerate(
            _optional_array(record, "stats", f"{source_key}[{index}]")
        ):
            stat = _mapping(raw_stat, f"{source_key}[{index}].stats[{stat_index}]")
            stats.append(
                SafetyEventStatInventoryRecord(
                    stat_id=f"{nct_id}:safety:{id_kind}:{index}:stat:{stat_index}",
                    source_index=stat_index,
                    source_json_pointer=(
                        f"/resultsSection/adverseEventsModule/{source_key}/{index}"
                        f"/stats/{stat_index}"
                    ),
                    source_group_id=_source_text(
                        stat.get("groupId"), "event stat.groupId"
                    ),
                    num_affected=_source_int(
                        stat.get("numAffected"), "event stat.numAffected"
                    ),
                    num_at_risk=_source_int(
                        stat.get("numAtRisk"), "event stat.numAtRisk"
                    ),
                    num_events=_source_int(
                        stat.get("numEvents"), "event stat.numEvents"
                    ),
                    source_record_sha256=_sha256(stat),
                )
            )
        result.append(
            SafetyEventInventoryRecord(
                safety_event_id=f"{nct_id}:safety:{id_kind}:{index}",
                event_category=category,
                source_index=index,
                source_json_pointer=(
                    f"/resultsSection/adverseEventsModule/{source_key}/{index}"
                ),
                term=_source_text(record.get("term"), "safety event.term"),
                organ_system=_source_text(
                    record.get("organSystem"), "safety event.organSystem"
                ),
                assessment_type=_source_text(
                    record.get("assessmentType"), "safety event.assessmentType"
                ),
                notes_sha256=_description_hash(record, "notes", "safety event"),
                stats=tuple(stats),
                source_record_sha256=_sha256(record),
            )
        )
    return tuple(result)


def compile_clinicaltrials_gov_inventory(
    spec: ClinicalTrialsGovInventorySpec,
    bundle: SourceBundle,
) -> ClinicalTrialsGovInventoryPacket:
    """Enumerate all bounded outcome and safety arrays in one exact snapshot."""

    if not isinstance(spec, ClinicalTrialsGovInventorySpec):
        raise TypeError("spec must be a ClinicalTrialsGovInventorySpec")
    _validate_bundle(spec, bundle)
    try:
        payload = bundle.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClinicalTrialsGovInventoryError("source must be UTF-8 JSON") from exc
    source = _load_json(payload, "ClinicalTrials.gov source")
    protocol, results, has_results = _source_identity(spec, source)
    protocol_module_value = protocol.get("outcomesModule")
    protocol_module_present = protocol_module_value is not None
    protocol_module = (
        _mapping(protocol_module_value, "protocolSection.outcomesModule")
        if protocol_module_present
        else {}
    )
    posted_module_value = results.get("outcomeMeasuresModule")
    posted_module_present = posted_module_value is not None
    posted_module = (
        _mapping(posted_module_value, "resultsSection.outcomeMeasuresModule")
        if posted_module_present
        else {}
    )
    safety_module_value = results.get("adverseEventsModule")
    safety_module_present = safety_module_value is not None
    safety_module = (
        _mapping(safety_module_value, "resultsSection.adverseEventsModule")
        if safety_module_present
        else {}
    )

    protocol_raw = _protocol_source_records(spec.nct_id, protocol_module)
    posted_raw = _posted_source_records(spec.nct_id, posted_module)
    link_pairs: list[tuple[int, int, tuple[str, str]]] = []
    protocol_link_counts = [0] * len(protocol_raw)
    posted_link_counts = [0] * len(posted_raw)
    for protocol_index, protocol_record in enumerate(protocol_raw):
        protocol_key = _lexical_key(
            protocol_record["measure"], protocol_record["time_frame"]
        )
        if protocol_key is None:
            continue
        for posted_index, posted_record in enumerate(posted_raw):
            posted_key = _lexical_key(
                posted_record["title"], posted_record["time_frame"]
            )
            if posted_key == protocol_key:
                link_pairs.append((protocol_index, posted_index, protocol_key))
                protocol_link_counts[protocol_index] += 1
                posted_link_counts[posted_index] += 1

    protocol_outcomes = tuple(
        ProtocolOutcomeInventoryRecord(
            **record,
            exact_candidate_count=protocol_link_counts[index],
            reconciliation_status=_match_status(protocol_link_counts[index]),
        )
        for index, record in enumerate(protocol_raw)
    )
    posted_outcomes = tuple(
        PostedOutcomeInventoryRecord(
            **record,
            exact_candidate_count=posted_link_counts[index],
            reconciliation_status=_match_status(posted_link_counts[index]),
        )
        for index, record in enumerate(posted_raw)
    )
    lexical_links = tuple(
        OutcomeLexicalLinkCandidate(
            link_id=(f"{spec.nct_id}:lexical-link:{protocol_index}:{posted_index}"),
            protocol_outcome_id=protocol_outcomes[protocol_index].protocol_outcome_id,
            posted_outcome_id=posted_outcomes[posted_index].posted_outcome_id,
            lexical_key_sha256=_sha256(key),
            outcome_type_exact_match=(
                _normalized(protocol_outcomes[protocol_index].outcome_type)
                == _normalized(posted_outcomes[posted_index].outcome_type or "")
            ),
        )
        for protocol_index, posted_index, key in link_pairs
    )
    safety_groups = _safety_group_records(spec.nct_id, safety_module)
    serious_events = _safety_event_records(
        spec.nct_id,
        safety_module,
        source_key="seriousEvents",
        category="SERIOUS",
    )
    other_events = _safety_event_records(
        spec.nct_id,
        safety_module,
        source_key="otherEvents",
        category="OTHER",
    )
    source_scope = {
        "protocol_outcomes_module_present": protocol_module_present,
        "protocol_outcomes_module": protocol_module
        if protocol_module_present
        else None,
        "posted_outcomes_module_present": posted_module_present,
        "posted_outcomes_module": posted_module if posted_module_present else None,
        "adverse_event_module_present": safety_module_present,
        "adverse_event_module": safety_module if safety_module_present else None,
    }
    receipt = bundle.receipt
    counts = {
        "protocol_outcome_count": len(protocol_outcomes),
        "posted_outcome_count": len(posted_outcomes),
        "lexical_link_candidate_count": len(lexical_links),
        "unmatched_protocol_outcome_count": sum(
            item.reconciliation_status == UNMATCHED for item in protocol_outcomes
        ),
        "unmatched_posted_outcome_count": sum(
            item.reconciliation_status == UNMATCHED for item in posted_outcomes
        ),
        "ambiguous_protocol_outcome_count": sum(
            item.reconciliation_status == AMBIGUOUS_EXACT_CANDIDATES
            for item in protocol_outcomes
        ),
        "ambiguous_posted_outcome_count": sum(
            item.reconciliation_status == AMBIGUOUS_EXACT_CANDIDATES
            for item in posted_outcomes
        ),
        "safety_group_count": len(safety_groups),
        "serious_event_count": len(serious_events),
        "other_event_count": len(other_events),
        "safety_event_stat_count": sum(
            len(item.stats) for item in (*serious_events, *other_events)
        ),
    }
    return ClinicalTrialsGovInventoryPacket(
        inventory_id=spec.inventory_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        source=ClinicalTrialsGovInventorySource(
            receipt_id=receipt.receipt_id,
            source_id=receipt.source_id,
            source_version=receipt.source_version,
            locator=receipt.locator,
            content_hash_sha256=receipt.content_hash,
            byte_size=receipt.byte_size,
            retrieved_at=receipt.retrieved_at.isoformat().replace("+00:00", "Z"),
        ),
        nct_id=spec.nct_id,
        registry_version=spec.registry_version,
        source_has_results=has_results,
        protocol_outcome_module_present=protocol_module_present,
        posted_outcome_module_present=posted_module_present,
        adverse_event_module_present=safety_module_present,
        adverse_event_time_frame=_source_text(
            safety_module.get("timeFrame"), "adverseEventsModule.timeFrame"
        ),
        adverse_event_description_sha256=_description_hash(
            safety_module, "description", "adverseEventsModule"
        ),
        adverse_event_frequency_threshold=_source_text(
            safety_module.get("frequencyThreshold"),
            "adverseEventsModule.frequencyThreshold",
        ),
        source_scope_sha256=_sha256(source_scope),
        protocol_outcomes=protocol_outcomes,
        posted_outcomes=posted_outcomes,
        lexical_link_candidates=lexical_links,
        safety_groups=safety_groups,
        serious_events=serious_events,
        other_events=other_events,
        **counts,
        full_source_array_enumeration_performed=True,
        exact_lexical_reconciliation_only=True,
        reviewer_approval_performed=False,
        endpoint_selected=False,
        endpoint_family_assigned=False,
        ontology_mapping_approved=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        comparative_safety_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_inventory(
    spec: ClinicalTrialsGovInventorySpec,
    bundle: SourceBundle,
    packet: ClinicalTrialsGovInventoryPacket,
) -> tuple[str, ...]:
    """Recompile the full source scope and return deterministic failure codes."""

    try:
        rebuilt = compile_clinicaltrials_gov_inventory(spec, bundle)
    except (ClinicalTrialsGovInventoryError, TypeError, ValueError):
        return ("clinicaltrials_gov_inventory_recompile_failed",)
    if rebuilt != packet:
        return ("clinicaltrials_gov_inventory_packet_mismatch",)
    return ()


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    data = _mapping(value, path)
    if set(data) != expected_fields:
        raise ClinicalTrialsGovInventoryError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return data


def clinicaltrials_gov_inventory_spec_to_dict(
    spec: ClinicalTrialsGovInventorySpec,
) -> dict[str, Any]:
    if not isinstance(spec, ClinicalTrialsGovInventorySpec):
        raise TypeError("spec must be a ClinicalTrialsGovInventorySpec")
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": CLINICALTRIALS_GOV_INVENTORY_SPEC_SCHEMA_VERSION,
        **value,
    }


def clinicaltrials_gov_inventory_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovInventorySpec:
    data = _record(
        value,
        "spec",
        {"schema_version", *_field_names(ClinicalTrialsGovInventorySpec)},
    )
    if data.pop("schema_version") != CLINICALTRIALS_GOV_INVENTORY_SPEC_SCHEMA_VERSION:
        raise ClinicalTrialsGovInventoryError(
            "unsupported inventory spec schema_version"
        )
    return ClinicalTrialsGovInventorySpec(**data)


def clinicaltrials_gov_inventory_spec_from_json(
    text: str,
) -> ClinicalTrialsGovInventorySpec:
    return clinicaltrials_gov_inventory_spec_from_dict(
        _load_json(text, "inventory spec")
    )


def clinicaltrials_gov_inventory_packet_envelope(
    packet: ClinicalTrialsGovInventoryPacket,
) -> dict[str, Any]:
    if not isinstance(packet, ClinicalTrialsGovInventoryPacket):
        raise TypeError("packet must be a ClinicalTrialsGovInventoryPacket")
    return {
        "schema_version": CLINICALTRIALS_GOV_INVENTORY_PACKET_SCHEMA_VERSION,
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _source_from_dict(value: Any, path: str) -> ClinicalTrialsGovInventorySource:
    return ClinicalTrialsGovInventorySource(
        **_record(value, path, _field_names(ClinicalTrialsGovInventorySource))
    )


def _protocol_from_dict(value: Any, path: str) -> ProtocolOutcomeInventoryRecord:
    return ProtocolOutcomeInventoryRecord(
        **_record(value, path, _field_names(ProtocolOutcomeInventoryRecord))
    )


def _posted_from_dict(value: Any, path: str) -> PostedOutcomeInventoryRecord:
    data = _record(value, path, _field_names(PostedOutcomeInventoryRecord))
    data["analysis_group_id_sets"] = tuple(
        _require_tuple(item, f"{path}.analysis_group_id_sets[{index}]")
        for index, item in enumerate(
            _require_tuple(data["analysis_group_id_sets"], "analysis_group_id_sets")
        )
    )
    return PostedOutcomeInventoryRecord(**data)


def _link_from_dict(value: Any, path: str) -> OutcomeLexicalLinkCandidate:
    return OutcomeLexicalLinkCandidate(
        **_record(value, path, _field_names(OutcomeLexicalLinkCandidate))
    )


def _group_from_dict(value: Any, path: str) -> SafetyGroupInventoryRecord:
    return SafetyGroupInventoryRecord(
        **_record(value, path, _field_names(SafetyGroupInventoryRecord))
    )


def _stat_from_dict(value: Any, path: str) -> SafetyEventStatInventoryRecord:
    return SafetyEventStatInventoryRecord(
        **_record(value, path, _field_names(SafetyEventStatInventoryRecord))
    )


def _event_from_dict(value: Any, path: str) -> SafetyEventInventoryRecord:
    data = _record(value, path, _field_names(SafetyEventInventoryRecord))
    data["stats"] = tuple(
        _stat_from_dict(item, f"{path}.stats[{index}]")
        for index, item in enumerate(_require_tuple(data["stats"], "stats"))
    )
    return SafetyEventInventoryRecord(**data)


def clinicaltrials_gov_inventory_packet_from_dict(
    value: Any,
) -> ClinicalTrialsGovInventoryPacket:
    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "packet"},
    )
    if envelope["schema_version"] != CLINICALTRIALS_GOV_INVENTORY_PACKET_SCHEMA_VERSION:
        raise ClinicalTrialsGovInventoryError(
            "unsupported inventory packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalTrialsGovInventoryPacket),
    )
    data["source"] = _source_from_dict(data["source"], "packet.source")
    data["protocol_outcomes"] = tuple(
        _protocol_from_dict(item, f"packet.protocol_outcomes[{index}]")
        for index, item in enumerate(
            _require_tuple(data["protocol_outcomes"], "protocol_outcomes")
        )
    )
    data["posted_outcomes"] = tuple(
        _posted_from_dict(item, f"packet.posted_outcomes[{index}]")
        for index, item in enumerate(
            _require_tuple(data["posted_outcomes"], "posted_outcomes")
        )
    )
    data["lexical_link_candidates"] = tuple(
        _link_from_dict(item, f"packet.lexical_link_candidates[{index}]")
        for index, item in enumerate(
            _require_tuple(data["lexical_link_candidates"], "lexical_link_candidates")
        )
    )
    data["safety_groups"] = tuple(
        _group_from_dict(item, f"packet.safety_groups[{index}]")
        for index, item in enumerate(
            _require_tuple(data["safety_groups"], "safety_groups")
        )
    )
    data["serious_events"] = tuple(
        _event_from_dict(item, f"packet.serious_events[{index}]")
        for index, item in enumerate(
            _require_tuple(data["serious_events"], "serious_events")
        )
    )
    data["other_events"] = tuple(
        _event_from_dict(item, f"packet.other_events[{index}]")
        for index, item in enumerate(
            _require_tuple(data["other_events"], "other_events")
        )
    )
    packet = ClinicalTrialsGovInventoryPacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovInventoryError("inventory integrity_sha256 mismatch")
    return packet


def clinicaltrials_gov_inventory_packet_from_json(
    text: str,
) -> ClinicalTrialsGovInventoryPacket:
    return clinicaltrials_gov_inventory_packet_from_dict(
        _load_json(text, "inventory packet")
    )


def clinicaltrials_gov_inventory_summary(
    packet: ClinicalTrialsGovInventoryPacket,
) -> dict[str, Any]:
    if not isinstance(packet, ClinicalTrialsGovInventoryPacket):
        raise TypeError("packet must be a ClinicalTrialsGovInventoryPacket")
    return {
        "inventory_id": packet.inventory_id,
        "nct_id": packet.nct_id,
        "registry_version": packet.registry_version,
        "source_receipt_id": packet.source.receipt_id,
        "protocol_outcome_count": packet.protocol_outcome_count,
        "posted_outcome_count": packet.posted_outcome_count,
        "lexical_link_candidate_count": packet.lexical_link_candidate_count,
        "unmatched_protocol_outcome_count": packet.unmatched_protocol_outcome_count,
        "unmatched_posted_outcome_count": packet.unmatched_posted_outcome_count,
        "ambiguous_protocol_outcome_count": packet.ambiguous_protocol_outcome_count,
        "ambiguous_posted_outcome_count": packet.ambiguous_posted_outcome_count,
        "safety_group_count": packet.safety_group_count,
        "serious_event_count": packet.serious_event_count,
        "other_event_count": packet.other_event_count,
        "reviewer_approval_performed": packet.reviewer_approval_performed,
        "benefit_risk_synthesis_performed": packet.benefit_risk_synthesis_performed,
        "integrity_sha256": packet.fingerprint,
    }
