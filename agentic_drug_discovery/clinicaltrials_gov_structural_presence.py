"""Presence-preserving structural-array sidecars and harmonization resolution."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

from .clinicaltrials_gov_harmonization_candidates import (
    MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT,
    MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT,
    MAX_CROSS_TRIAL_INVENTORY_COUNT,
    ClinicalTrialsGovHarmonizationCandidatePacket,
    CrossTrialEndpointCandidate,
)
from .clinicaltrials_gov_harmonization_structure import (
    ClinicalTrialsGovHarmonizationStructureReport,
)
from .clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventoryPacket,
    ClinicalTrialsGovInventorySpec,
    compile_clinicaltrials_gov_inventory,
)
from .ingestion import SourceBundle, verify_source_payload
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-structural-presence-spec.v1"
)
CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_PACKET_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-structural-presence-packet.v1"
)
CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_POLICY_ID = (
    "adds.source-bound-structural-array-presence.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-presence-spec.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_REPORT_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-presence-report.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_POLICY_ID = (
    "adds.payload-free-source-presence-resolution.v1"
)

ABSENT = "absent"
PRESENT_NULL = "present_null"
PRESENT_EMPTY = "present_empty"
PRESENT_NONEMPTY = "present_nonempty"
_PRESENCE_STATES = (ABSENT, PRESENT_NULL, PRESENT_EMPTY, PRESENT_NONEMPTY)

OUTCOME_GROUPS = "outcome_groups"
OUTCOME_DENOMINATORS = "outcome_denominators"
OUTCOME_DENOMINATOR_COUNTS = "outcome_denominator_counts"
OUTCOME_CLASSES = "outcome_classes"
CLASS_DENOMINATORS = "class_denominators"
CLASS_DENOMINATOR_COUNTS = "class_denominator_counts"
CLASS_CATEGORIES = "class_categories"
CATEGORY_MEASUREMENTS = "category_measurements"
OUTCOME_ANALYSES = "outcome_analyses"
ANALYSIS_GROUP_IDS = "analysis_group_ids"
_ARRAY_ROLES = (
    OUTCOME_GROUPS,
    OUTCOME_DENOMINATORS,
    OUTCOME_DENOMINATOR_COUNTS,
    OUTCOME_CLASSES,
    CLASS_DENOMINATORS,
    CLASS_DENOMINATOR_COUNTS,
    CLASS_CATEGORIES,
    CATEGORY_MEASUREMENTS,
    OUTCOME_ANALYSES,
    ANALYSIS_GROUP_IDS,
)
_ROLE_FIELD = {
    OUTCOME_GROUPS: "group_count",
    OUTCOME_DENOMINATORS: "denominator_count",
    OUTCOME_DENOMINATOR_COUNTS: "denominator_count",
    OUTCOME_CLASSES: "class_count",
    CLASS_DENOMINATORS: "denominator_count",
    CLASS_DENOMINATOR_COUNTS: "denominator_count",
    CLASS_CATEGORIES: "category_count",
    CATEGORY_MEASUREMENTS: "measurement_count",
    OUTCOME_ANALYSES: "analysis_count",
    ANALYSIS_GROUP_IDS: "analysis_group_id_sets",
}
_STRUCTURAL_FIELDS = (
    "group_count",
    "denominator_count",
    "class_count",
    "category_count",
    "measurement_count",
    "analysis_count",
    "analysis_group_id_sets",
)
_FIELD_ZERO_CAUSE_ROLES = {
    "group_count": (OUTCOME_GROUPS,),
    "denominator_count": (
        OUTCOME_DENOMINATORS,
        OUTCOME_CLASSES,
        CLASS_DENOMINATORS,
    ),
    "class_count": (OUTCOME_CLASSES,),
    "category_count": (OUTCOME_CLASSES, CLASS_CATEGORIES),
    "measurement_count": (
        OUTCOME_CLASSES,
        CLASS_CATEGORIES,
        CATEGORY_MEASUREMENTS,
    ),
    "analysis_count": (OUTCOME_ANALYSES,),
    "analysis_group_id_sets": (OUTCOME_ANALYSES, ANALYSIS_GROUP_IDS),
}
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
MAX_STRUCTURAL_ARRAY_RECORD_COUNT = 1_000_000

_SIDECAR_LIMITATIONS = (
    (
        "The sidecar is valid only for the exact source bundle and immutable v1 "
        "inventory bound by SHA-256."
    ),
    (
        "Presence states distinguish absent, present-null, present-empty, and "
        "present-nonempty arrays for the ten structural roles parsed by v1."
    ),
    (
        "Pointers, counts, and hashes are provenance metadata; source array values, "
        "endpoint titles, and clinical interpretations are not retained."
    ),
    (
        "No endpoint identity, estimand equivalence, clinical comparability, safety "
        "inference, benefit-risk synthesis, or treatment choice is performed."
    ),
)
_REPORT_LIMITATIONS = (
    (
        "The report resolves source presence only for the exact candidate packet, "
        "structure report, and sidecars bound by SHA-256."
    ),
    (
        "Absent, null, and empty involvement counts may overlap when an endpoint "
        "contains multiple relevant nested arrays."
    ),
    (
        "Presence signatures describe registry representation, not semantic or "
        "estimand equivalence and not whether a difference matters clinically."
    ),
    (
        "No endpoint approval, exclusion, pooling, ranking, efficacy or safety "
        "inference, benefit-risk synthesis, or treatment choice is performed."
    ),
)


class ClinicalTrialsGovStructuralPresenceError(ValueError):
    """Raised when structural-array presence cannot be compiled or replayed."""


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


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def _text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    values = _tuple(value, field_name)
    for item in values:
        _require_text(item, field_name)
    return values


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _pointer(value: Any, field_name: str) -> None:
    _require_text(value, field_name)
    if not value.startswith("/"):
        raise ValueError(f"{field_name} must be an absolute JSON pointer")


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovStructuralPresenceError(f"{path} must be an object")
    return dict(value)


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ClinicalTrialsGovStructuralPresenceError(f"{path} must be an array")
    return list(value)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovStructuralPresenceSpec(SerializableRecord):
    sidecar_id: str
    inventory_sha256: str
    source_content_hash_sha256: str
    max_structural_array_record_count: int
    policy_id: str = CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.sidecar_id, "sidecar_id")
        _require_sha256(self.inventory_sha256, "inventory_sha256")
        _require_sha256(self.source_content_hash_sha256, "source_content_hash_sha256")
        _require_non_negative_int(
            self.max_structural_array_record_count,
            "max_structural_array_record_count",
        )
        if not (
            1
            <= self.max_structural_array_record_count
            <= MAX_STRUCTURAL_ARRAY_RECORD_COUNT
        ):
            raise ValueError("max_structural_array_record_count is outside bounds")
        if self.policy_id != CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_POLICY_ID:
            raise ValueError("unsupported structural presence policy_id")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class StructuralArrayPresenceRecord(SerializableRecord):
    record_id: str
    posted_outcome_id: str
    posted_outcome_source_index: int
    posted_outcome_source_record_sha256: str
    field_name: str
    array_role: str
    parent_source_json_pointer: str
    parent_source_record_sha256: str
    source_json_pointer: str
    presence_state: str
    item_count: int
    source_value_sha256: str | None

    def __post_init__(self) -> None:
        for field_name in ("record_id", "posted_outcome_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_non_negative_int(
            self.posted_outcome_source_index, "posted_outcome_source_index"
        )
        _require_sha256(
            self.posted_outcome_source_record_sha256,
            "posted_outcome_source_record_sha256",
        )
        if self.array_role not in _ARRAY_ROLES:
            raise ValueError("unsupported structural array_role")
        if self.field_name != _ROLE_FIELD[self.array_role]:
            raise ValueError("array role and structural field do not match")
        _pointer(self.parent_source_json_pointer, "parent_source_json_pointer")
        _pointer(self.source_json_pointer, "source_json_pointer")
        if not self.source_json_pointer.startswith(
            f"{self.parent_source_json_pointer}/"
        ):
            raise ValueError("source pointer is outside its parent")
        _require_sha256(self.parent_source_record_sha256, "parent_source_record_sha256")
        if self.presence_state not in _PRESENCE_STATES:
            raise ValueError("unsupported presence_state")
        _require_non_negative_int(self.item_count, "item_count")
        if self.source_value_sha256 is not None:
            _require_sha256(self.source_value_sha256, "source_value_sha256")
        if self.presence_state == ABSENT:
            if self.item_count != 0 or self.source_value_sha256 is not None:
                raise ValueError("absent array has value metadata")
        elif self.presence_state == PRESENT_NULL:
            if self.item_count != 0 or self.source_value_sha256 != _sha256(None):
                raise ValueError("present-null array metadata is inconsistent")
        elif self.presence_state == PRESENT_EMPTY:
            if self.item_count != 0 or self.source_value_sha256 != _sha256([]):
                raise ValueError("present-empty array metadata is inconsistent")
        elif self.item_count == 0 or self.source_value_sha256 is None:
            raise ValueError("present-nonempty array metadata is inconsistent")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovStructuralPresencePacket(SerializableRecord):
    sidecar_id: str
    policy_id: str
    spec_sha256: str
    inventory_id: str
    inventory_sha256: str
    source_receipt_id: str
    source_content_hash_sha256: str
    source_scope_sha256: str
    nct_id: str
    registry_version: str
    array_records: tuple[StructuralArrayPresenceRecord, ...]
    posted_outcome_count: int
    structural_array_record_count: int
    absent_count: int
    present_null_count: int
    present_empty_count: int
    present_nonempty_count: int
    bounded_work_preflight_performed: bool
    v1_inventory_replay_verified: bool
    source_presence_provenance_retained: bool
    structural_array_values_retained: bool
    endpoint_semantic_equivalence_inferred: bool
    estimand_equivalence_inferred: bool
    clinical_comparability_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "sidecar_id",
            "inventory_id",
            "source_receipt_id",
            "nct_id",
            "registry_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_POLICY_ID:
            raise ValueError("unsupported structural presence policy_id")
        for field_name in (
            "spec_sha256",
            "inventory_sha256",
            "source_content_hash_sha256",
            "source_scope_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        records = _tuple(self.array_records, "array_records")
        if any(not isinstance(item, StructuralArrayPresenceRecord) for item in records):
            raise TypeError("array_records contains an invalid record")
        if len({item.source_json_pointer for item in records}) != len(records):
            raise ValueError("structural array source pointers must be unique")
        for index, item in enumerate(records):
            if item.record_id != f"{self.nct_id}:structural-array:{index}":
                raise ValueError("structural array record identity was rebound")
            if item.posted_outcome_id != (
                f"{self.nct_id}:posted:{item.posted_outcome_source_index}"
            ):
                raise ValueError("structural array posted outcome was rebound")
        counts = {
            "structural_array_record_count": len(records),
            "absent_count": sum(item.presence_state == ABSENT for item in records),
            "present_null_count": sum(
                item.presence_state == PRESENT_NULL for item in records
            ),
            "present_empty_count": sum(
                item.presence_state == PRESENT_EMPTY for item in records
            ),
            "present_nonempty_count": sum(
                item.presence_state == PRESENT_NONEMPTY for item in records
            ),
        }
        _require_non_negative_int(self.posted_outcome_count, "posted_outcome_count")
        expected_outcome_ids = {
            f"{self.nct_id}:posted:{index}"
            for index in range(self.posted_outcome_count)
        }
        if {item.posted_outcome_id for item in records} != expected_outcome_ids:
            raise ValueError("array records do not cover every posted outcome")
        top_level_roles = {
            OUTCOME_GROUPS,
            OUTCOME_DENOMINATORS,
            OUTCOME_CLASSES,
            OUTCOME_ANALYSES,
        }
        for outcome_id in expected_outcome_ids:
            outcome_records = tuple(
                item for item in records if item.posted_outcome_id == outcome_id
            )
            if (
                len(
                    {
                        item.posted_outcome_source_record_sha256
                        for item in outcome_records
                    }
                )
                != 1
            ):
                raise ValueError("posted outcome source hashes are inconsistent")
            if Counter(
                item.array_role
                for item in outcome_records
                if item.array_role in top_level_roles
            ) != Counter(top_level_roles):
                raise ValueError("posted outcome top-level array roles are incomplete")
        for field_name, expected in counts.items():
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match array records")
        if sum(
            counts[name] for name in counts if name != "structural_array_record_count"
        ) != len(records):
            raise ValueError("presence state counts do not partition records")
        true_fields = (
            "bounded_work_preflight_performed",
            "v1_inventory_replay_verified",
            "source_presence_provenance_retained",
        )
        false_fields = (
            "structural_array_values_retained",
            "endpoint_semantic_equivalence_inferred",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, field_name) for field_name in true_fields):
            raise ValueError("required presence provenance flag is false")
        if any(getattr(self, field_name) for field_name in false_fields):
            raise ValueError("a forbidden value payload or inference was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _SIDECAR_LIMITATIONS:
            raise ValueError("structural presence limitations were rebound")
        object.__setattr__(self, "array_records", records)
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class StructuralPresenceSidecarBinding(SerializableRecord):
    nct_id: str
    inventory_sha256: str
    sidecar_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.nct_id, str) or _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        _require_sha256(self.inventory_sha256, "inventory_sha256")
        _require_sha256(self.sidecar_sha256, "sidecar_sha256")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationPresenceSpec(SerializableRecord):
    report_id: str
    candidate_packet_sha256: str
    structure_report_sha256: str
    sidecar_bindings: tuple[StructuralPresenceSidecarBinding, ...]
    policy_id: str = CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.report_id, "report_id")
        _require_sha256(self.candidate_packet_sha256, "candidate_packet_sha256")
        _require_sha256(self.structure_report_sha256, "structure_report_sha256")
        bindings = _tuple(self.sidecar_bindings, "sidecar_bindings")
        if any(
            not isinstance(item, StructuralPresenceSidecarBinding) for item in bindings
        ):
            raise TypeError("sidecar_bindings contains an invalid binding")
        if not (2 <= len(bindings) <= MAX_CROSS_TRIAL_INVENTORY_COUNT):
            raise ValueError("sidecar binding count is outside bounds")
        if bindings != tuple(sorted(bindings, key=lambda item: item.nct_id)):
            raise ValueError("sidecar_bindings must use canonical nct_id order")
        if len({item.nct_id for item in bindings}) != len(bindings):
            raise ValueError("sidecar nct_id values must be unique")
        if len({item.inventory_sha256 for item in bindings}) != len(bindings):
            raise ValueError("sidecar inventory hashes must be unique")
        if len({item.sidecar_sha256 for item in bindings}) != len(bindings):
            raise ValueError("sidecar hashes must be unique")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_POLICY_ID:
            raise ValueError("unsupported harmonization presence policy_id")
        object.__setattr__(self, "sidecar_bindings", bindings)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ArrayRolePresenceCount(SerializableRecord):
    array_role: str
    record_count: int
    absent_count: int
    present_null_count: int
    present_empty_count: int
    present_nonempty_count: int

    def __post_init__(self) -> None:
        if self.array_role not in _ARRAY_ROLES:
            raise ValueError("unsupported structural array_role")
        for field_name in (
            "record_count",
            "absent_count",
            "present_null_count",
            "present_empty_count",
            "present_nonempty_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if (
            self.absent_count
            + self.present_null_count
            + self.present_empty_count
            + self.present_nonempty_count
            != self.record_count
        ):
            raise ValueError("role presence counts do not partition records")


@dataclass(frozen=True, slots=True)
class StructuralFieldZeroCauseProfile(SerializableRecord):
    field_name: str
    endpoint_count: int
    positive_value_endpoint_count: int
    zero_or_empty_value_endpoint_count: int
    zero_with_absent_array_count: int
    zero_with_present_null_array_count: int
    zero_with_present_empty_array_count: int

    def __post_init__(self) -> None:
        if self.field_name not in _STRUCTURAL_FIELDS:
            raise ValueError("unsupported structural field_name")
        for field_name in (
            "endpoint_count",
            "positive_value_endpoint_count",
            "zero_or_empty_value_endpoint_count",
            "zero_with_absent_array_count",
            "zero_with_present_null_array_count",
            "zero_with_present_empty_array_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if (
            self.positive_value_endpoint_count + self.zero_or_empty_value_endpoint_count
            != self.endpoint_count
        ):
            raise ValueError("field endpoint counts do not partition endpoints")
        for field_name in (
            "zero_with_absent_array_count",
            "zero_with_present_null_array_count",
            "zero_with_present_empty_array_count",
        ):
            if getattr(self, field_name) > self.zero_or_empty_value_endpoint_count:
                raise ValueError("zero cause count exceeds zero endpoints")


@dataclass(frozen=True, slots=True)
class TrialStructuralPresenceProfile(SerializableRecord):
    nct_id: str
    inventory_sha256: str
    source_content_hash_sha256: str
    sidecar_sha256: str
    endpoint_count: int
    structural_array_record_count: int
    role_counts: tuple[ArrayRolePresenceCount, ...]
    zero_cause_profiles: tuple[StructuralFieldZeroCauseProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.nct_id, str) or _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        for field_name in (
            "inventory_sha256",
            "source_content_hash_sha256",
            "sidecar_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_non_negative_int(self.endpoint_count, "endpoint_count")
        _require_non_negative_int(
            self.structural_array_record_count, "structural_array_record_count"
        )
        roles = _tuple(self.role_counts, "role_counts")
        if any(not isinstance(item, ArrayRolePresenceCount) for item in roles):
            raise TypeError("role_counts contains an invalid count")
        if tuple(item.array_role for item in roles) != _ARRAY_ROLES:
            raise ValueError("role_counts were reordered or omitted")
        if (
            sum(item.record_count for item in roles)
            != self.structural_array_record_count
        ):
            raise ValueError("role counts do not match structural array records")
        causes = _tuple(self.zero_cause_profiles, "zero_cause_profiles")
        if any(
            not isinstance(item, StructuralFieldZeroCauseProfile) for item in causes
        ):
            raise TypeError("zero_cause_profiles contains an invalid profile")
        if tuple(item.field_name for item in causes) != _STRUCTURAL_FIELDS:
            raise ValueError("zero_cause_profiles were reordered or omitted")
        if any(item.endpoint_count != self.endpoint_count for item in causes):
            raise ValueError("zero cause endpoint count does not match trial")
        object.__setattr__(self, "role_counts", roles)
        object.__setattr__(self, "zero_cause_profiles", causes)


@dataclass(frozen=True, slots=True)
class StructuralFieldPresenceResolution(SerializableRecord):
    field_name: str
    pair_count: int
    legacy_non_identifiable_pair_count: int
    resolved_pair_count: int
    absent_array_involved_pair_count: int
    present_null_array_involved_pair_count: int
    present_empty_array_involved_pair_count: int
    zero_cause_signature_exact_count: int
    zero_cause_signature_disagreement_count: int

    def __post_init__(self) -> None:
        if self.field_name not in _STRUCTURAL_FIELDS:
            raise ValueError("unsupported structural field_name")
        for field_name in (
            "pair_count",
            "legacy_non_identifiable_pair_count",
            "resolved_pair_count",
            "absent_array_involved_pair_count",
            "present_null_array_involved_pair_count",
            "present_empty_array_involved_pair_count",
            "zero_cause_signature_exact_count",
            "zero_cause_signature_disagreement_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.legacy_non_identifiable_pair_count > self.pair_count:
            raise ValueError("legacy non-identifiable count exceeds pairs")
        if self.resolved_pair_count != self.legacy_non_identifiable_pair_count:
            raise ValueError("legacy source presence was not fully resolved")
        if (
            self.zero_cause_signature_exact_count
            + self.zero_cause_signature_disagreement_count
            != self.resolved_pair_count
        ):
            raise ValueError("zero cause signatures do not partition resolved pairs")
        for field_name in (
            "absent_array_involved_pair_count",
            "present_null_array_involved_pair_count",
            "present_empty_array_involved_pair_count",
        ):
            if getattr(self, field_name) > self.resolved_pair_count:
                raise ValueError("source-state involvement exceeds resolved pairs")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationPresenceReport(SerializableRecord):
    report_id: str
    policy_id: str
    spec_sha256: str
    candidate_packet_id: str
    candidate_packet_sha256: str
    structure_report_id: str
    structure_report_sha256: str
    sidecar_bindings: tuple[StructuralPresenceSidecarBinding, ...]
    trial_profiles: tuple[TrialStructuralPresenceProfile, ...]
    field_resolutions: tuple[StructuralFieldPresenceResolution, ...]
    trial_count: int
    endpoint_candidate_count: int
    pair_candidate_count: int
    legacy_non_identifiable_field_pair_count: int
    resolved_field_pair_count: int
    source_presence_provenance_retained: bool
    v1_artifacts_mutated: bool
    structural_array_values_retained: bool
    endpoint_semantic_equivalence_inferred: bool
    estimand_equivalence_inferred: bool
    clinical_comparability_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "report_id",
            "candidate_packet_id",
            "structure_report_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_POLICY_ID:
            raise ValueError("unsupported harmonization presence policy_id")
        for field_name in (
            "spec_sha256",
            "candidate_packet_sha256",
            "structure_report_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        bindings = _tuple(self.sidecar_bindings, "sidecar_bindings")
        if any(
            not isinstance(item, StructuralPresenceSidecarBinding) for item in bindings
        ):
            raise TypeError("sidecar_bindings contains an invalid binding")
        if not (2 <= len(bindings) <= MAX_CROSS_TRIAL_INVENTORY_COUNT):
            raise ValueError("sidecar binding count is outside bounds")
        if bindings != tuple(sorted(bindings, key=lambda item: item.nct_id)):
            raise ValueError("sidecar_bindings must use canonical nct_id order")
        if len({item.nct_id for item in bindings}) != len(bindings):
            raise ValueError("sidecar nct_id values must be unique")
        if len({item.inventory_sha256 for item in bindings}) != len(bindings):
            raise ValueError("sidecar inventory hashes must be unique")
        if len({item.sidecar_sha256 for item in bindings}) != len(bindings):
            raise ValueError("sidecar hashes must be unique")
        profiles = _tuple(self.trial_profiles, "trial_profiles")
        if any(
            not isinstance(item, TrialStructuralPresenceProfile) for item in profiles
        ):
            raise TypeError("trial_profiles contains an invalid profile")
        if tuple(item.nct_id for item in profiles) != tuple(
            item.nct_id for item in bindings
        ):
            raise ValueError("trial profiles do not match sidecar bindings")
        if any(
            profile.inventory_sha256 != binding.inventory_sha256
            or profile.sidecar_sha256 != binding.sidecar_sha256
            for profile, binding in zip(profiles, bindings, strict=True)
        ):
            raise ValueError("trial profile hashes do not match sidecar bindings")
        resolutions = _tuple(self.field_resolutions, "field_resolutions")
        if any(
            not isinstance(item, StructuralFieldPresenceResolution)
            for item in resolutions
        ):
            raise TypeError("field_resolutions contains an invalid resolution")
        if tuple(item.field_name for item in resolutions) != _STRUCTURAL_FIELDS:
            raise ValueError("field_resolutions were reordered or omitted")
        for field_name in (
            "trial_count",
            "endpoint_candidate_count",
            "pair_candidate_count",
            "legacy_non_identifiable_field_pair_count",
            "resolved_field_pair_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.trial_count != len(bindings) or self.trial_count != len(profiles):
            raise ValueError("trial_count does not match bound profiles")
        if self.endpoint_candidate_count != sum(
            item.endpoint_count for item in profiles
        ):
            raise ValueError("endpoint count does not match trial profiles")
        if self.endpoint_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT:
            raise ValueError("endpoint count exceeds supported bound")
        endpoint_counts = [item.endpoint_count for item in profiles]
        expected_pairs = sum(
            left * right
            for index, left in enumerate(endpoint_counts)
            for right in endpoint_counts[index + 1 :]
        )
        if self.pair_candidate_count != expected_pairs:
            raise ValueError("pair count is not the complete cross-trial Cartesian set")
        if self.pair_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError("pair count exceeds supported bound")
        if any(item.pair_count != self.pair_candidate_count for item in resolutions):
            raise ValueError("field resolution denominator does not match pairs")
        if self.legacy_non_identifiable_field_pair_count != sum(
            item.legacy_non_identifiable_pair_count for item in resolutions
        ):
            raise ValueError("legacy non-identifiable total is inconsistent")
        if self.resolved_field_pair_count != sum(
            item.resolved_pair_count for item in resolutions
        ):
            raise ValueError("resolved field-pair total is inconsistent")
        true_fields = ("source_presence_provenance_retained",)
        false_fields = (
            "v1_artifacts_mutated",
            "structural_array_values_retained",
            "endpoint_semantic_equivalence_inferred",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, field_name) for field_name in true_fields):
            raise ValueError("source presence provenance was not retained")
        if any(getattr(self, field_name) for field_name in false_fields):
            raise ValueError("a mutation, payload, or forbidden inference was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REPORT_LIMITATIONS:
            raise ValueError("harmonization presence limitations were rebound")
        object.__setattr__(self, "sidecar_bindings", bindings)
        object.__setattr__(self, "trial_profiles", profiles)
        object.__setattr__(self, "field_resolutions", resolutions)
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _presence(
    parent: Mapping[str, Any], key: str, path: str
) -> tuple[str, int, str | None, list[Any]]:
    if key not in parent:
        return ABSENT, 0, None, []
    value = parent[key]
    if value is None:
        return PRESENT_NULL, 0, _sha256(None), []
    values = _array(value, path)
    state = PRESENT_EMPTY if not values else PRESENT_NONEMPTY
    return state, len(values), _sha256(values), values


def _source_record(
    *,
    nct_id: str,
    sequence: int,
    outcome_id: str,
    outcome_index: int,
    outcome_hash: str,
    role: str,
    parent_pointer: str,
    parent: Mapping[str, Any],
    key: str,
) -> tuple[StructuralArrayPresenceRecord, list[Any]]:
    pointer = f"{parent_pointer}/{key}"
    state, count, value_hash, values = _presence(parent, key, pointer)
    return (
        StructuralArrayPresenceRecord(
            record_id=f"{nct_id}:structural-array:{sequence}",
            posted_outcome_id=outcome_id,
            posted_outcome_source_index=outcome_index,
            posted_outcome_source_record_sha256=outcome_hash,
            field_name=_ROLE_FIELD[role],
            array_role=role,
            parent_source_json_pointer=parent_pointer,
            parent_source_record_sha256=_sha256(parent),
            source_json_pointer=pointer,
            presence_state=state,
            item_count=count,
            source_value_sha256=value_hash,
        ),
        values,
    )


def _expected_record_count(outcomes: Sequence[Any]) -> int:
    count = 0
    for outcome_index, raw_outcome in enumerate(outcomes):
        outcome = _mapping(raw_outcome, f"outcomeMeasures[{outcome_index}]")
        count += 4
        denoms = outcome.get("denoms") or []
        classes = outcome.get("classes") or []
        analyses = outcome.get("analyses") or []
        count += len(denoms) + len(classes) * 2 + len(analyses)
        for class_index, raw_class in enumerate(classes):
            class_record = _mapping(
                raw_class, f"outcomeMeasures[{outcome_index}].classes[{class_index}]"
            )
            class_denoms = class_record.get("denoms") or []
            categories = class_record.get("categories") or []
            count += len(class_denoms) + len(categories)
    return count


def _compile_array_records(
    nct_id: str,
    outcomes: Sequence[Any],
    inventory: ClinicalTrialsGovInventoryPacket,
) -> tuple[StructuralArrayPresenceRecord, ...]:
    result: list[StructuralArrayPresenceRecord] = []

    def add(
        *,
        outcome_id: str,
        outcome_index: int,
        outcome_hash: str,
        role: str,
        parent_pointer: str,
        parent: Mapping[str, Any],
        key: str,
    ) -> list[Any]:
        record, values = _source_record(
            nct_id=nct_id,
            sequence=len(result),
            outcome_id=outcome_id,
            outcome_index=outcome_index,
            outcome_hash=outcome_hash,
            role=role,
            parent_pointer=parent_pointer,
            parent=parent,
            key=key,
        )
        result.append(record)
        return values

    for outcome_index, raw_outcome in enumerate(outcomes):
        outcome = _mapping(raw_outcome, f"outcomeMeasures[{outcome_index}]")
        legacy = inventory.posted_outcomes[outcome_index]
        if legacy.source_record_sha256 != _sha256(outcome):
            raise ClinicalTrialsGovStructuralPresenceError(
                "posted outcome source hash does not match v1 inventory"
            )
        pointer = legacy.source_json_pointer
        kwargs = {
            "outcome_id": legacy.posted_outcome_id,
            "outcome_index": outcome_index,
            "outcome_hash": legacy.source_record_sha256,
        }
        add(
            role=OUTCOME_GROUPS,
            parent_pointer=pointer,
            parent=outcome,
            key="groups",
            **kwargs,
        )
        denoms = add(
            role=OUTCOME_DENOMINATORS,
            parent_pointer=pointer,
            parent=outcome,
            key="denoms",
            **kwargs,
        )
        for denom_index, raw_denom in enumerate(denoms):
            denom = _mapping(
                raw_denom, f"outcomeMeasures[{outcome_index}].denoms[{denom_index}]"
            )
            add(
                role=OUTCOME_DENOMINATOR_COUNTS,
                parent_pointer=f"{pointer}/denoms/{denom_index}",
                parent=denom,
                key="counts",
                **kwargs,
            )
        classes = add(
            role=OUTCOME_CLASSES,
            parent_pointer=pointer,
            parent=outcome,
            key="classes",
            **kwargs,
        )
        for class_index, raw_class in enumerate(classes):
            class_record = _mapping(
                raw_class, f"outcomeMeasures[{outcome_index}].classes[{class_index}]"
            )
            class_pointer = f"{pointer}/classes/{class_index}"
            class_denoms = add(
                role=CLASS_DENOMINATORS,
                parent_pointer=class_pointer,
                parent=class_record,
                key="denoms",
                **kwargs,
            )
            for denom_index, raw_denom in enumerate(class_denoms):
                denom = _mapping(raw_denom, "outcome class denominator")
                add(
                    role=CLASS_DENOMINATOR_COUNTS,
                    parent_pointer=f"{class_pointer}/denoms/{denom_index}",
                    parent=denom,
                    key="counts",
                    **kwargs,
                )
            categories = add(
                role=CLASS_CATEGORIES,
                parent_pointer=class_pointer,
                parent=class_record,
                key="categories",
                **kwargs,
            )
            for category_index, raw_category in enumerate(categories):
                category = _mapping(raw_category, "outcome class category")
                add(
                    role=CATEGORY_MEASUREMENTS,
                    parent_pointer=f"{class_pointer}/categories/{category_index}",
                    parent=category,
                    key="measurements",
                    **kwargs,
                )
        analyses = add(
            role=OUTCOME_ANALYSES,
            parent_pointer=pointer,
            parent=outcome,
            key="analyses",
            **kwargs,
        )
        for analysis_index, raw_analysis in enumerate(analyses):
            analysis = _mapping(raw_analysis, "outcome analysis")
            add(
                role=ANALYSIS_GROUP_IDS,
                parent_pointer=f"{pointer}/analyses/{analysis_index}",
                parent=analysis,
                key="groupIds",
                **kwargs,
            )
    return tuple(result)


def compile_clinicaltrials_gov_structural_presence(
    spec: ClinicalTrialsGovStructuralPresenceSpec,
    bundle: SourceBundle,
    inventory: ClinicalTrialsGovInventoryPacket,
) -> ClinicalTrialsGovStructuralPresencePacket:
    """Replay v1 and preserve every structural-array presence state."""

    if not isinstance(spec, ClinicalTrialsGovStructuralPresenceSpec):
        raise TypeError("spec must be a structural presence spec")
    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    if not isinstance(inventory, ClinicalTrialsGovInventoryPacket):
        raise TypeError("inventory must be a ClinicalTrialsGovInventoryPacket")
    verify_source_payload(bundle.receipt, bundle.payload)
    if spec.inventory_sha256 != inventory.fingerprint:
        raise ClinicalTrialsGovStructuralPresenceError(
            "inventory fingerprint does not match structural presence spec"
        )
    if (
        spec.source_content_hash_sha256 != bundle.receipt.content_hash
        or inventory.source.content_hash_sha256 != bundle.receipt.content_hash
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "source content hash does not match structural presence bindings"
        )
    legacy_spec = ClinicalTrialsGovInventorySpec(
        inventory_id=inventory.inventory_id,
        source_receipt_id=inventory.source.receipt_id,
        nct_id=inventory.nct_id,
        registry_version=inventory.registry_version,
    )
    if legacy_spec.fingerprint != inventory.spec_sha256:
        raise ClinicalTrialsGovStructuralPresenceError(
            "v1 inventory spec identity cannot be reconstructed"
        )
    if compile_clinicaltrials_gov_inventory(legacy_spec, bundle) != inventory:
        raise ClinicalTrialsGovStructuralPresenceError(
            "v1 inventory does not replay from the exact source bundle"
        )
    try:
        source = _load_json(bundle.payload.decode("utf-8"), "ClinicalTrials.gov source")
    except UnicodeDecodeError as exc:
        raise ClinicalTrialsGovStructuralPresenceError(
            "source must be UTF-8 JSON"
        ) from exc
    results_value = source.get("resultsSection")
    results = {} if results_value is None else _mapping(results_value, "resultsSection")
    module_value = results.get("outcomeMeasuresModule")
    module = (
        {}
        if module_value is None
        else _mapping(module_value, "resultsSection.outcomeMeasuresModule")
    )
    _, _, _, outcomes = _presence(
        module,
        "outcomeMeasures",
        "/resultsSection/outcomeMeasuresModule/outcomeMeasures",
    )
    if len(outcomes) != inventory.posted_outcome_count:
        raise ClinicalTrialsGovStructuralPresenceError(
            "posted outcome count differs from v1 inventory"
        )
    expected_count = _expected_record_count(outcomes)
    if expected_count > spec.max_structural_array_record_count:
        raise ClinicalTrialsGovStructuralPresenceError(
            "structural array record count exceeds preregistered bound"
        )
    records = _compile_array_records(inventory.nct_id, outcomes, inventory)
    if len(records) != expected_count:
        raise ClinicalTrialsGovStructuralPresenceError(
            "structural array preflight count changed during compilation"
        )
    states = Counter(item.presence_state for item in records)
    return ClinicalTrialsGovStructuralPresencePacket(
        sidecar_id=spec.sidecar_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        inventory_id=inventory.inventory_id,
        inventory_sha256=inventory.fingerprint,
        source_receipt_id=inventory.source.receipt_id,
        source_content_hash_sha256=inventory.source.content_hash_sha256,
        source_scope_sha256=inventory.source_scope_sha256,
        nct_id=inventory.nct_id,
        registry_version=inventory.registry_version,
        array_records=records,
        posted_outcome_count=inventory.posted_outcome_count,
        structural_array_record_count=len(records),
        absent_count=states[ABSENT],
        present_null_count=states[PRESENT_NULL],
        present_empty_count=states[PRESENT_EMPTY],
        present_nonempty_count=states[PRESENT_NONEMPTY],
        bounded_work_preflight_performed=True,
        v1_inventory_replay_verified=True,
        source_presence_provenance_retained=True,
        structural_array_values_retained=False,
        endpoint_semantic_equivalence_inferred=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_SIDECAR_LIMITATIONS,
    )


def _zero_or_empty(value: Any) -> bool:
    if value == 0:
        return True
    if isinstance(value, tuple):
        return not value or all(_zero_or_empty(item) for item in value)
    return False


def _endpoint_cause_states(
    endpoint: CrossTrialEndpointCandidate,
    field_name: str,
    records_by_outcome_role: Mapping[
        tuple[str, str], tuple[StructuralArrayPresenceRecord, ...]
    ],
) -> tuple[str, ...]:
    if not _zero_or_empty(getattr(endpoint, field_name)):
        return ("positive",)
    states = {
        item.presence_state
        for role in _FIELD_ZERO_CAUSE_ROLES[field_name]
        for item in records_by_outcome_role.get((endpoint.posted_outcome_id, role), ())
        if item.presence_state in {ABSENT, PRESENT_NULL, PRESENT_EMPTY}
    }
    if not states:
        raise ClinicalTrialsGovStructuralPresenceError(
            f"zero or empty {field_name} has no source-presence cause"
        )
    return tuple(state for state in _PRESENCE_STATES[:-1] if state in states)


def compile_clinicaltrials_gov_harmonization_presence(
    spec: ClinicalTrialsGovHarmonizationPresenceSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    structure_report: ClinicalTrialsGovHarmonizationStructureReport,
    sidecars: Sequence[ClinicalTrialsGovStructuralPresencePacket],
) -> ClinicalTrialsGovHarmonizationPresenceReport:
    """Resolve v1 zero/empty ambiguity with exact source-presence sidecars."""

    if not isinstance(spec, ClinicalTrialsGovHarmonizationPresenceSpec):
        raise TypeError("spec must be a harmonization presence spec")
    if not isinstance(candidate_packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError("candidate_packet must be a harmonization candidate packet")
    if not isinstance(structure_report, ClinicalTrialsGovHarmonizationStructureReport):
        raise TypeError("structure_report must be a harmonization structure report")
    packets = _tuple(sidecars, "sidecars")
    if any(
        not isinstance(item, ClinicalTrialsGovStructuralPresencePacket)
        for item in packets
    ):
        raise TypeError("sidecars contains an invalid packet")
    if len(packets) != len(spec.sidecar_bindings):
        raise ClinicalTrialsGovStructuralPresenceError(
            "sidecar count does not match presence spec"
        )
    if spec.candidate_packet_sha256 != candidate_packet.fingerprint:
        raise ClinicalTrialsGovStructuralPresenceError(
            "candidate packet fingerprint does not match presence spec"
        )
    if spec.structure_report_sha256 != structure_report.fingerprint:
        raise ClinicalTrialsGovStructuralPresenceError(
            "structure report fingerprint does not match presence spec"
        )
    if (
        structure_report.candidate_packet_id != candidate_packet.packet_id
        or structure_report.candidate_packet_sha256 != candidate_packet.fingerprint
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "structure report does not bind the candidate packet"
        )
    packet_by_nct = {item.nct_id: item for item in packets}
    if len(packet_by_nct) != len(packets):
        raise ClinicalTrialsGovStructuralPresenceError(
            "sidecar nct_id values must be unique"
        )
    binding_by_nct = {item.nct_id: item for item in spec.sidecar_bindings}
    contexts = {item.nct_id: item for item in candidate_packet.safety_contexts}
    if set(packet_by_nct) != set(binding_by_nct) or set(packet_by_nct) != set(contexts):
        raise ClinicalTrialsGovStructuralPresenceError(
            "sidecar trial set does not match candidate packet and spec"
        )
    for nct_id, packet in packet_by_nct.items():
        binding = binding_by_nct[nct_id]
        context = contexts[nct_id]
        if (
            binding.sidecar_sha256 != packet.fingerprint
            or binding.inventory_sha256 != packet.inventory_sha256
            or packet.inventory_sha256 != context.inventory_sha256
            or packet.source_content_hash_sha256 != context.source_content_hash_sha256
        ):
            raise ClinicalTrialsGovStructuralPresenceError(
                f"sidecar provenance does not match {nct_id}"
            )

    endpoints_by_nct: dict[str, list[CrossTrialEndpointCandidate]] = defaultdict(list)
    endpoints_by_id = {
        item.endpoint_candidate_id: item
        for item in candidate_packet.endpoint_candidates
    }
    for endpoint in candidate_packet.endpoint_candidates:
        endpoints_by_nct[endpoint.nct_id].append(endpoint)
    records_by_outcome_role: dict[
        tuple[str, str], tuple[StructuralArrayPresenceRecord, ...]
    ] = {}
    mutable_records: dict[tuple[str, str], list[StructuralArrayPresenceRecord]] = (
        defaultdict(list)
    )
    for packet in packets:
        for record in packet.array_records:
            mutable_records[(record.posted_outcome_id, record.array_role)].append(
                record
            )
    records_by_outcome_role = {
        key: tuple(values) for key, values in mutable_records.items()
    }

    endpoint_causes: dict[tuple[str, str], tuple[str, ...]] = {}
    trial_profiles = []
    for binding in spec.sidecar_bindings:
        packet = packet_by_nct[binding.nct_id]
        endpoints = endpoints_by_nct[binding.nct_id]
        role_counts = []
        for role in _ARRAY_ROLES:
            role_records = tuple(
                item for item in packet.array_records if item.array_role == role
            )
            states = Counter(item.presence_state for item in role_records)
            role_counts.append(
                ArrayRolePresenceCount(
                    array_role=role,
                    record_count=len(role_records),
                    absent_count=states[ABSENT],
                    present_null_count=states[PRESENT_NULL],
                    present_empty_count=states[PRESENT_EMPTY],
                    present_nonempty_count=states[PRESENT_NONEMPTY],
                )
            )
        cause_profiles = []
        for field_name in _STRUCTURAL_FIELDS:
            causes = []
            for endpoint in endpoints:
                cause = _endpoint_cause_states(
                    endpoint, field_name, records_by_outcome_role
                )
                endpoint_causes[(endpoint.endpoint_candidate_id, field_name)] = cause
                causes.append(cause)
            zero_causes = tuple(item for item in causes if item != ("positive",))
            cause_profiles.append(
                StructuralFieldZeroCauseProfile(
                    field_name=field_name,
                    endpoint_count=len(endpoints),
                    positive_value_endpoint_count=len(causes) - len(zero_causes),
                    zero_or_empty_value_endpoint_count=len(zero_causes),
                    zero_with_absent_array_count=sum(
                        ABSENT in item for item in zero_causes
                    ),
                    zero_with_present_null_array_count=sum(
                        PRESENT_NULL in item for item in zero_causes
                    ),
                    zero_with_present_empty_array_count=sum(
                        PRESENT_EMPTY in item for item in zero_causes
                    ),
                )
            )
        trial_profiles.append(
            TrialStructuralPresenceProfile(
                nct_id=packet.nct_id,
                inventory_sha256=packet.inventory_sha256,
                source_content_hash_sha256=packet.source_content_hash_sha256,
                sidecar_sha256=packet.fingerprint,
                endpoint_count=len(endpoints),
                structural_array_record_count=packet.structural_array_record_count,
                role_counts=tuple(role_counts),
                zero_cause_profiles=tuple(cause_profiles),
            )
        )

    structure_by_field = {
        item.field_name: item for item in structure_report.field_decompositions
    }
    counters = {field_name: Counter() for field_name in _STRUCTURAL_FIELDS}
    for pair in candidate_packet.pair_candidates:
        left = endpoints_by_id[pair.left_endpoint_candidate_id]
        right = endpoints_by_id[pair.right_endpoint_candidate_id]
        for field_name in _STRUCTURAL_FIELDS:
            left_cause = endpoint_causes[(left.endpoint_candidate_id, field_name)]
            right_cause = endpoint_causes[(right.endpoint_candidate_id, field_name)]
            if left_cause == ("positive",) and right_cause == ("positive",):
                continue
            counter = counters[field_name]
            counter["resolved"] += 1
            involved = set(left_cause) | set(right_cause)
            for state in (ABSENT, PRESENT_NULL, PRESENT_EMPTY):
                if state in involved:
                    counter[state] += 1
            counter["exact" if left_cause == right_cause else "disagreement"] += 1
    resolutions = []
    for field_name in _STRUCTURAL_FIELDS:
        prior = structure_by_field[field_name]
        counter = counters[field_name]
        if counter["resolved"] != prior.source_presence_non_identifiable_pair_count:
            raise ClinicalTrialsGovStructuralPresenceError(
                f"presence resolution does not refine {field_name}"
            )
        resolutions.append(
            StructuralFieldPresenceResolution(
                field_name=field_name,
                pair_count=candidate_packet.pair_candidate_count,
                legacy_non_identifiable_pair_count=(
                    prior.source_presence_non_identifiable_pair_count
                ),
                resolved_pair_count=counter["resolved"],
                absent_array_involved_pair_count=counter[ABSENT],
                present_null_array_involved_pair_count=counter[PRESENT_NULL],
                present_empty_array_involved_pair_count=counter[PRESENT_EMPTY],
                zero_cause_signature_exact_count=counter["exact"],
                zero_cause_signature_disagreement_count=counter["disagreement"],
            )
        )
    legacy_total = sum(item.legacy_non_identifiable_pair_count for item in resolutions)
    return ClinicalTrialsGovHarmonizationPresenceReport(
        report_id=spec.report_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        candidate_packet_id=candidate_packet.packet_id,
        candidate_packet_sha256=candidate_packet.fingerprint,
        structure_report_id=structure_report.report_id,
        structure_report_sha256=structure_report.fingerprint,
        sidecar_bindings=spec.sidecar_bindings,
        trial_profiles=tuple(trial_profiles),
        field_resolutions=tuple(resolutions),
        trial_count=candidate_packet.inventory_count,
        endpoint_candidate_count=candidate_packet.endpoint_candidate_count,
        pair_candidate_count=candidate_packet.pair_candidate_count,
        legacy_non_identifiable_field_pair_count=legacy_total,
        resolved_field_pair_count=legacy_total,
        source_presence_provenance_retained=True,
        v1_artifacts_mutated=False,
        structural_array_values_retained=False,
        endpoint_semantic_equivalence_inferred=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REPORT_LIMITATIONS,
    )


def validate_clinicaltrials_gov_structural_presence(
    spec: ClinicalTrialsGovStructuralPresenceSpec,
    bundle: SourceBundle,
    inventory: ClinicalTrialsGovInventoryPacket,
    packet: ClinicalTrialsGovStructuralPresencePacket,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_structural_presence(
            spec, bundle, inventory
        )
    except (ClinicalTrialsGovStructuralPresenceError, TypeError, ValueError):
        return ("clinicaltrials_gov_structural_presence_recompile_failed",)
    if rebuilt != packet:
        return ("clinicaltrials_gov_structural_presence_packet_mismatch",)
    return ()


def validate_clinicaltrials_gov_harmonization_presence(
    spec: ClinicalTrialsGovHarmonizationPresenceSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    structure_report: ClinicalTrialsGovHarmonizationStructureReport,
    sidecars: Sequence[ClinicalTrialsGovStructuralPresencePacket],
    report: ClinicalTrialsGovHarmonizationPresenceReport,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_harmonization_presence(
            spec, candidate_packet, structure_report, sidecars
        )
    except (ClinicalTrialsGovStructuralPresenceError, TypeError, ValueError):
        return ("clinicaltrials_gov_harmonization_presence_recompile_failed",)
    if rebuilt != report:
        return ("clinicaltrials_gov_harmonization_presence_report_mismatch",)
    return ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovStructuralPresenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovStructuralPresenceError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovStructuralPresenceError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovStructuralPresenceError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    return _mapping(value, label)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected: set[str]) -> dict[str, Any]:
    data = _mapping(value, path)
    if set(data) != expected:
        raise ClinicalTrialsGovStructuralPresenceError(
            f"{path} must contain exactly {sorted(expected)}"
        )
    return data


def clinicaltrials_gov_structural_presence_spec_to_dict(
    spec: ClinicalTrialsGovStructuralPresenceSpec,
) -> dict[str, Any]:
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_SPEC_SCHEMA_VERSION,
        **value,
    }


def clinicaltrials_gov_structural_presence_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovStructuralPresenceSpec:
    data = _record(
        value,
        "spec",
        {"schema_version", *_field_names(ClinicalTrialsGovStructuralPresenceSpec)},
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "unsupported structural presence spec schema_version"
        )
    return ClinicalTrialsGovStructuralPresenceSpec(**data)


def clinicaltrials_gov_structural_presence_spec_from_json(
    text: str,
) -> ClinicalTrialsGovStructuralPresenceSpec:
    return clinicaltrials_gov_structural_presence_spec_from_dict(
        _load_json(text, "structural presence spec")
    )


def clinicaltrials_gov_structural_presence_packet_envelope(
    packet: ClinicalTrialsGovStructuralPresencePacket,
) -> dict[str, Any]:
    return {
        "schema_version": CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_PACKET_SCHEMA_VERSION,
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _array_record_from_dict(value: Any, path: str) -> StructuralArrayPresenceRecord:
    return StructuralArrayPresenceRecord(
        **_record(value, path, _field_names(StructuralArrayPresenceRecord))
    )


def clinicaltrials_gov_structural_presence_packet_from_dict(
    value: Any,
) -> ClinicalTrialsGovStructuralPresencePacket:
    envelope = _record(
        value, "envelope", {"schema_version", "integrity_sha256", "packet"}
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_STRUCTURAL_PRESENCE_PACKET_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "unsupported structural presence packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalTrialsGovStructuralPresencePacket),
    )
    data["array_records"] = tuple(
        _array_record_from_dict(item, f"packet.array_records[{index}]")
        for index, item in enumerate(_tuple(data["array_records"], "array_records"))
    )
    packet = ClinicalTrialsGovStructuralPresencePacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovStructuralPresenceError(
            "structural presence integrity_sha256 mismatch"
        )
    return packet


def clinicaltrials_gov_structural_presence_packet_from_json(
    text: str,
) -> ClinicalTrialsGovStructuralPresencePacket:
    return clinicaltrials_gov_structural_presence_packet_from_dict(
        _load_json(text, "structural presence packet")
    )


def clinicaltrials_gov_harmonization_presence_spec_to_dict(
    spec: ClinicalTrialsGovHarmonizationPresenceSpec,
) -> dict[str, Any]:
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_SPEC_SCHEMA_VERSION,
        **value,
    }


def _binding_from_dict(value: Any, path: str) -> StructuralPresenceSidecarBinding:
    return StructuralPresenceSidecarBinding(
        **_record(value, path, _field_names(StructuralPresenceSidecarBinding))
    )


def clinicaltrials_gov_harmonization_presence_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationPresenceSpec:
    data = _record(
        value,
        "spec",
        {"schema_version", *_field_names(ClinicalTrialsGovHarmonizationPresenceSpec)},
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "unsupported harmonization presence spec schema_version"
        )
    data["sidecar_bindings"] = tuple(
        _binding_from_dict(item, f"spec.sidecar_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["sidecar_bindings"], "sidecar_bindings")
        )
    )
    return ClinicalTrialsGovHarmonizationPresenceSpec(**data)


def clinicaltrials_gov_harmonization_presence_spec_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationPresenceSpec:
    return clinicaltrials_gov_harmonization_presence_spec_from_dict(
        _load_json(text, "harmonization presence spec")
    )


def clinicaltrials_gov_harmonization_presence_report_envelope(
    report: ClinicalTrialsGovHarmonizationPresenceReport,
) -> dict[str, Any]:
    return {
        "schema_version": CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def _role_count_from_dict(value: Any, path: str) -> ArrayRolePresenceCount:
    return ArrayRolePresenceCount(
        **_record(value, path, _field_names(ArrayRolePresenceCount))
    )


def _cause_profile_from_dict(value: Any, path: str) -> StructuralFieldZeroCauseProfile:
    return StructuralFieldZeroCauseProfile(
        **_record(value, path, _field_names(StructuralFieldZeroCauseProfile))
    )


def _trial_profile_from_dict(value: Any, path: str) -> TrialStructuralPresenceProfile:
    data = _record(value, path, _field_names(TrialStructuralPresenceProfile))
    data["role_counts"] = tuple(
        _role_count_from_dict(item, f"{path}.role_counts[{index}]")
        for index, item in enumerate(_tuple(data["role_counts"], "role_counts"))
    )
    data["zero_cause_profiles"] = tuple(
        _cause_profile_from_dict(item, f"{path}.zero_cause_profiles[{index}]")
        for index, item in enumerate(
            _tuple(data["zero_cause_profiles"], "zero_cause_profiles")
        )
    )
    return TrialStructuralPresenceProfile(**data)


def _resolution_from_dict(value: Any, path: str) -> StructuralFieldPresenceResolution:
    return StructuralFieldPresenceResolution(
        **_record(value, path, _field_names(StructuralFieldPresenceResolution))
    )


def clinicaltrials_gov_harmonization_presence_report_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationPresenceReport:
    envelope = _record(
        value, "envelope", {"schema_version", "integrity_sha256", "report"}
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_HARMONIZATION_PRESENCE_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovStructuralPresenceError(
            "unsupported harmonization presence report schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "report",
        _field_names(ClinicalTrialsGovHarmonizationPresenceReport),
    )
    data["sidecar_bindings"] = tuple(
        _binding_from_dict(item, f"report.sidecar_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["sidecar_bindings"], "sidecar_bindings")
        )
    )
    data["trial_profiles"] = tuple(
        _trial_profile_from_dict(item, f"report.trial_profiles[{index}]")
        for index, item in enumerate(_tuple(data["trial_profiles"], "trial_profiles"))
    )
    data["field_resolutions"] = tuple(
        _resolution_from_dict(item, f"report.field_resolutions[{index}]")
        for index, item in enumerate(
            _tuple(data["field_resolutions"], "field_resolutions")
        )
    )
    report = ClinicalTrialsGovHarmonizationPresenceReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovStructuralPresenceError(
            "harmonization presence integrity_sha256 mismatch"
        )
    return report


def clinicaltrials_gov_harmonization_presence_report_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationPresenceReport:
    return clinicaltrials_gov_harmonization_presence_report_from_dict(
        _load_json(text, "harmonization presence report")
    )


def clinicaltrials_gov_structural_presence_summary(
    packet: ClinicalTrialsGovStructuralPresencePacket,
) -> dict[str, Any]:
    return {
        "sidecar_id": packet.sidecar_id,
        "nct_id": packet.nct_id,
        "posted_outcome_count": packet.posted_outcome_count,
        "structural_array_record_count": packet.structural_array_record_count,
        "absent_count": packet.absent_count,
        "present_null_count": packet.present_null_count,
        "present_empty_count": packet.present_empty_count,
        "present_nonempty_count": packet.present_nonempty_count,
        "integrity_sha256": packet.fingerprint,
    }


def clinicaltrials_gov_harmonization_presence_summary(
    report: ClinicalTrialsGovHarmonizationPresenceReport,
) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "trial_count": report.trial_count,
        "endpoint_candidate_count": report.endpoint_candidate_count,
        "pair_candidate_count": report.pair_candidate_count,
        "legacy_non_identifiable_field_pair_count": (
            report.legacy_non_identifiable_field_pair_count
        ),
        "resolved_field_pair_count": report.resolved_field_pair_count,
        "source_presence_provenance_retained": (
            report.source_presence_provenance_retained
        ),
        "integrity_sha256": report.fingerprint,
    }
