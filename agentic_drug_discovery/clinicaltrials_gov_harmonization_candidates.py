"""Cross-trial endpoint harmonization candidates with source provenance.

This layer converts exact registry-record inventories into an exhaustive,
bounded reviewer universe. Mechanical field equality is diagnostic only: no
endpoint identity, comparability, safety, synthesis, or treatment claim is
approved here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime
from itertools import combinations, product
from typing import Any

from .clinicaltrials_gov_inventory import ClinicalTrialsGovInventoryPacket
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_HARMONIZATION_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-candidate-spec.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_PACKET_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-candidate-packet.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_POLICY_ID = (
    "adds.clinicaltrials-gov-cross-trial-harmonization-candidates.v1"
)
MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT = 100_000
MAX_CROSS_TRIAL_INVENTORY_COUNT = 256
MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT = 100_000

INCOMPLETE_SOURCE_FIELDS = "incomplete_source_fields"
ALL_MECHANICAL_FIELDS_EQUAL = "all_mechanical_fields_equal"
MIXED_MECHANICAL_FIELDS = "mixed_mechanical_fields"

_PAIR_STATUSES = frozenset(
    {
        INCOMPLETE_SOURCE_FIELDS,
        ALL_MECHANICAL_FIELDS_EQUAL,
        MIXED_MECHANICAL_FIELDS,
    }
)
_ENDPOINT_FIELD_NAMES = (
    "title",
    "time_frame",
    "outcome_type",
    "reporting_status",
    "parameter_type",
    "dispersion_type",
    "unit_of_measure",
    "population_description_sha256",
)
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_REQUIRED_LIMITATIONS = (
    (
        "Completeness is limited to the exact input inventory packets and their "
        "upstream ClinicalTrials.gov snapshots; registry omissions and historical "
        "changes cannot be recovered here."
    ),
    (
        "Normalized field equality is a mechanical reviewer diagnostic and does "
        "not establish endpoint identity, family, ontology, estimand, or semantic "
        "equivalence."
    ),
    (
        "Safety context is retained at the trial level and is not linked causally "
        "to an endpoint, harmonized risk window, intervention, or comparison."
    ),
    (
        "Input inventory integrity is checked, but source-bundle replay remains an "
        "upstream requirement and is not performed by this packet compiler."
    ),
    (
        "No endpoint selection, pooling, utility weighting, benefit-risk synthesis, "
        "regulatory inference, or treatment choice is performed."
    ),
)


class ClinicalTrialsGovHarmonizationError(ValueError):
    """Raised when a cross-trial candidate graph cannot be compiled or replayed."""


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


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_optional_text(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be text or null")


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


def _source_text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    values = _tuple(value, field_name)
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"{field_name} items must be text")
    return values


def _sorted_unique_text(value: Any, field_name: str) -> tuple[str, ...]:
    values = _text_tuple(value, field_name)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must use canonical unique sorted order")
    return values


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().split())
    return normalized or None


def _observed_equal(left: str | None, right: str | None) -> bool:
    left_value = _normalized_optional(left)
    right_value = _normalized_optional(right)
    return left_value is not None and left_value == right_value


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationInventoryBinding(SerializableRecord):
    inventory_id: str
    nct_id: str
    inventory_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.inventory_id, "inventory_id")
        _require_text(self.nct_id, "nct_id")
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        _require_sha256(self.inventory_sha256, "inventory_sha256")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationCandidateSpec(SerializableRecord):
    packet_id: str
    inventory_bindings: tuple[ClinicalTrialsGovHarmonizationInventoryBinding, ...]
    max_endpoint_candidate_count: int
    max_pair_count: int
    policy_id: str = CLINICALTRIALS_GOV_HARMONIZATION_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.packet_id, "packet_id")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_POLICY_ID:
            raise ValueError("unsupported harmonization policy_id")
        bindings = _tuple(self.inventory_bindings, "inventory_bindings")
        if any(
            not isinstance(item, ClinicalTrialsGovHarmonizationInventoryBinding)
            for item in bindings
        ):
            raise TypeError("inventory_bindings contains an invalid binding")
        if len(bindings) < 2:
            raise ValueError("inventory_bindings must contain at least two trials")
        if len(bindings) > MAX_CROSS_TRIAL_INVENTORY_COUNT:
            raise ValueError(
                "inventory_bindings exceeds MAX_CROSS_TRIAL_INVENTORY_COUNT"
            )
        if bindings != tuple(sorted(bindings, key=lambda item: item.nct_id)):
            raise ValueError("inventory_bindings must use canonical nct_id order")
        for field_name, values in (
            ("inventory_id", [item.inventory_id for item in bindings]),
            ("nct_id", [item.nct_id for item in bindings]),
            ("inventory_sha256", [item.inventory_sha256 for item in bindings]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"inventory binding {field_name} values must be unique"
                )
        for field_name in (
            "max_endpoint_candidate_count",
            "max_pair_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) == 0:
                raise ValueError(f"{field_name} must be positive")
        if self.max_endpoint_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT:
            raise ValueError(
                "max_endpoint_candidate_count exceeds "
                "MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT"
            )
        if self.max_pair_count > MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError(
                "max_pair_count exceeds MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT"
            )
        object.__setattr__(self, "inventory_bindings", bindings)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class CrossTrialSafetyRecordReference(SerializableRecord):
    record_id: str
    record_type: str
    source_json_pointer: str
    source_record_sha256: str
    stat_count: int

    def __post_init__(self) -> None:
        _require_text(self.record_id, "record_id")
        if self.record_type not in {"GROUP", "SERIOUS_EVENT", "OTHER_EVENT"}:
            raise ValueError("unsupported safety record_type")
        _require_text(self.source_json_pointer, "source_json_pointer")
        if not self.source_json_pointer.startswith("/"):
            raise ValueError("source_json_pointer must be absolute")
        _require_sha256(self.source_record_sha256, "source_record_sha256")
        _require_non_negative_int(self.stat_count, "stat_count")
        if self.record_type == "GROUP" and self.stat_count != 0:
            raise ValueError("safety group stat_count must be zero")


@dataclass(frozen=True, slots=True)
class CrossTrialSafetyContext(SerializableRecord):
    safety_context_id: str
    inventory_id: str
    nct_id: str
    inventory_sha256: str
    source_receipt_id: str
    source_id: str
    source_version: str
    source_locator: str
    source_content_hash_sha256: str
    source_retrieved_at: str
    registry_version: str
    source_scope_sha256: str
    source_has_results: bool
    protocol_outcome_module_present: bool
    posted_outcome_module_present: bool
    adverse_event_module_present: bool
    adverse_event_time_frame: str | None
    adverse_event_description_sha256: str | None
    adverse_event_frequency_threshold: str | None
    safety_records: tuple[CrossTrialSafetyRecordReference, ...]
    protocol_outcome_count: int
    posted_outcome_count: int
    lexical_link_candidate_count: int
    safety_group_count: int
    serious_event_count: int
    other_event_count: int
    safety_event_stat_count: int
    endpoint_causal_link_inferred: bool = False
    comparative_safety_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "safety_context_id",
            "inventory_id",
            "nct_id",
            "source_receipt_id",
            "source_id",
            "source_version",
            "source_locator",
            "source_retrieved_at",
            "registry_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        try:
            if (
                date.fromisoformat(self.registry_version).isoformat()
                != self.registry_version
            ):
                raise ValueError
        except ValueError as exc:
            raise ValueError("registry_version must use YYYY-MM-DD") from exc
        try:
            retrieved_at = datetime.fromisoformat(
                self.source_retrieved_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("source_retrieved_at must be ISO 8601") from exc
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("source_retrieved_at must include a timezone")
        if (
            self.source_id != f"clinicaltrials-gov-{self.nct_id}"
            or self.source_version
            != f"clinicaltrials-gov-{self.nct_id}-version-{self.registry_version}"
            or self.source_locator
            != f"https://clinicaltrials.gov/api/v2/studies/{self.nct_id}"
        ):
            raise ValueError("safety context source identity is not canonical")
        for field_name in (
            "inventory_sha256",
            "source_content_hash_sha256",
            "source_scope_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        for field_name in (
            "source_has_results",
            "protocol_outcome_module_present",
            "posted_outcome_module_present",
            "adverse_event_module_present",
        ):
            _require_bool(getattr(self, field_name), field_name)
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
        records = _tuple(self.safety_records, "safety_records")
        if any(
            not isinstance(item, CrossTrialSafetyRecordReference) for item in records
        ):
            raise TypeError("safety_records contains an invalid reference")
        if len({item.record_id for item in records}) != len(records):
            raise ValueError("safety record ids must be unique")
        expected_records: list[tuple[str, str, str]] = []
        for record_type, count, id_kind, source_key in (
            (
                "GROUP",
                sum(item.record_type == "GROUP" for item in records),
                "safety-group",
                "eventGroups",
            ),
            (
                "SERIOUS_EVENT",
                sum(item.record_type == "SERIOUS_EVENT" for item in records),
                "safety:serious",
                "seriousEvents",
            ),
            (
                "OTHER_EVENT",
                sum(item.record_type == "OTHER_EVENT" for item in records),
                "safety:other",
                "otherEvents",
            ),
        ):
            for index in range(count):
                expected_records.append(
                    (
                        record_type,
                        f"{self.nct_id}:{id_kind}:{index}",
                        (f"/resultsSection/adverseEventsModule/{source_key}/{index}"),
                    )
                )
        if tuple(
            (item.record_type, item.record_id, item.source_json_pointer)
            for item in records
        ) != tuple(expected_records):
            raise ValueError("safety record source identities are not canonical")
        object.__setattr__(self, "safety_records", records)
        counts = {
            "safety_group_count": sum(item.record_type == "GROUP" for item in records),
            "serious_event_count": sum(
                item.record_type == "SERIOUS_EVENT" for item in records
            ),
            "other_event_count": sum(
                item.record_type == "OTHER_EVENT" for item in records
            ),
            "safety_event_stat_count": sum(item.stat_count for item in records),
        }
        for field_name in (
            "protocol_outcome_count",
            "posted_outcome_count",
            "lexical_link_candidate_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if not self.protocol_outcome_module_present and self.protocol_outcome_count:
            raise ValueError("protocol outcomes exist without a source module")
        if not self.posted_outcome_module_present and self.posted_outcome_count:
            raise ValueError("posted outcomes exist without a source module")
        for field_name, expected in counts.items():
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match safety records")
        if not self.adverse_event_module_present and records:
            raise ValueError("safety records exist without an adverse-event module")
        if not self.adverse_event_module_present and any(
            value is not None
            for value in (
                self.adverse_event_time_frame,
                self.adverse_event_description_sha256,
                self.adverse_event_frequency_threshold,
            )
        ):
            raise ValueError("safety metadata exists without an adverse-event module")
        for field_name in (
            "endpoint_causal_link_inferred",
            "comparative_safety_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class CrossTrialEndpointCandidate(SerializableRecord):
    endpoint_candidate_id: str
    inventory_id: str
    nct_id: str
    inventory_sha256: str
    source_receipt_id: str
    source_content_hash_sha256: str
    posted_outcome_id: str
    source_index: int
    source_json_pointer: str
    source_record_sha256: str
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
    within_trial_protocol_outcome_ids: tuple[str, ...]
    within_trial_lexical_link_ids: tuple[str, ...]
    within_trial_exact_candidate_count: int
    within_trial_reconciliation_status: str
    safety_context_id: str
    endpoint_selected: bool = False
    endpoint_family_assigned: bool = False
    semantic_equivalence_approved: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "endpoint_candidate_id",
            "inventory_id",
            "nct_id",
            "source_receipt_id",
            "posted_outcome_id",
            "source_json_pointer",
            "within_trial_reconciliation_status",
            "safety_context_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "inventory_sha256",
            "source_content_hash_sha256",
            "source_record_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_non_negative_int(self.source_index, "source_index")
        if not self.source_json_pointer.startswith("/"):
            raise ValueError("source_json_pointer must be absolute")
        for field_name in _ENDPOINT_FIELD_NAMES[:-1]:
            _require_optional_text(getattr(self, field_name), field_name)
        for field_name in (
            "description_sha256",
            "population_description_sha256",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_sha256(value, field_name)
        for field_name in (
            "group_ids",
            "denominator_group_ids",
            "measurement_group_ids",
        ):
            values = _source_text_tuple(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, values)
        for field_name in (
            "within_trial_protocol_outcome_ids",
            "within_trial_lexical_link_ids",
        ):
            values = _text_tuple(getattr(self, field_name), field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
            object.__setattr__(self, field_name, values)
        analysis_sets = _tuple(self.analysis_group_id_sets, "analysis_group_id_sets")
        canonical_analysis_sets = tuple(
            _source_text_tuple(item, f"analysis_group_id_sets[{index}]")
            for index, item in enumerate(analysis_sets)
        )
        object.__setattr__(self, "analysis_group_id_sets", canonical_analysis_sets)
        for field_name in (
            "group_count",
            "denominator_count",
            "class_count",
            "category_count",
            "measurement_count",
            "analysis_count",
            "within_trial_exact_candidate_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if len(self.within_trial_protocol_outcome_ids) != len(
            self.within_trial_lexical_link_ids
        ):
            raise ValueError("within-trial protocol and lexical link counts differ")
        if self.analysis_count != len(self.analysis_group_id_sets):
            raise ValueError("analysis_count does not match analysis_group_id_sets")
        if self.within_trial_exact_candidate_count != len(
            self.within_trial_lexical_link_ids
        ):
            raise ValueError("within-trial exact candidate count differs from links")
        for field_name in (
            "endpoint_selected",
            "endpoint_family_assigned",
            "semantic_equivalence_approved",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class CrossTrialEndpointPairCandidate(SerializableRecord):
    pair_id: str
    left_endpoint_candidate_id: str
    right_endpoint_candidate_id: str
    left_nct_id: str
    right_nct_id: str
    left_inventory_sha256: str
    right_inventory_sha256: str
    left_source_record_sha256: str
    right_source_record_sha256: str
    left_safety_context_id: str
    right_safety_context_id: str
    title_exact: bool
    time_frame_exact: bool
    outcome_type_exact: bool
    reporting_status_exact: bool
    parameter_type_exact: bool
    dispersion_type_exact: bool
    unit_of_measure_exact: bool
    population_description_sha256_exact: bool
    safety_time_frame_exact: bool
    missing_field_codes: tuple[str, ...]
    mechanical_status: str
    endpoint_identity_approved: bool = False
    endpoint_family_assigned: bool = False
    estimand_equivalence_inferred: bool = False
    clinical_comparability_inferred: bool = False
    safety_comparability_inferred: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "pair_id",
            "left_endpoint_candidate_id",
            "right_endpoint_candidate_id",
            "left_nct_id",
            "right_nct_id",
            "left_safety_context_id",
            "right_safety_context_id",
            "mechanical_status",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.left_nct_id >= self.right_nct_id:
            raise ValueError("pair sides must use canonical nct_id order")
        for field_name in (
            "left_inventory_sha256",
            "right_inventory_sha256",
            "left_source_record_sha256",
            "right_source_record_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        diagnostic_fields = (
            "title_exact",
            "time_frame_exact",
            "outcome_type_exact",
            "reporting_status_exact",
            "parameter_type_exact",
            "dispersion_type_exact",
            "unit_of_measure_exact",
            "population_description_sha256_exact",
            "safety_time_frame_exact",
        )
        for field_name in diagnostic_fields:
            _require_bool(getattr(self, field_name), field_name)
        missing = _sorted_unique_text(self.missing_field_codes, "missing_field_codes")
        allowed_missing = {
            f"{side}.{field_name}"
            for side in ("left", "right")
            for field_name in _ENDPOINT_FIELD_NAMES
        }
        if not set(missing).issubset(allowed_missing):
            raise ValueError("missing_field_codes contains an unsupported code")
        if self.mechanical_status not in _PAIR_STATUSES:
            raise ValueError("unsupported mechanical_status")
        endpoint_equal = tuple(getattr(self, name) for name in diagnostic_fields[:-1])
        expected_status = (
            INCOMPLETE_SOURCE_FIELDS
            if missing
            else ALL_MECHANICAL_FIELDS_EQUAL
            if all(endpoint_equal)
            else MIXED_MECHANICAL_FIELDS
        )
        if self.mechanical_status != expected_status:
            raise ValueError("mechanical_status does not match pair diagnostics")
        object.__setattr__(self, "missing_field_codes", missing)
        for field_name in (
            "endpoint_identity_approved",
            "endpoint_family_assigned",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "safety_comparability_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationCandidatePacket(SerializableRecord):
    packet_id: str
    policy_id: str
    spec_sha256: str
    max_endpoint_candidate_count: int
    max_pair_count: int
    inventory_bindings: tuple[ClinicalTrialsGovHarmonizationInventoryBinding, ...]
    safety_contexts: tuple[CrossTrialSafetyContext, ...]
    endpoint_candidates: tuple[CrossTrialEndpointCandidate, ...]
    pair_candidates: tuple[CrossTrialEndpointPairCandidate, ...]
    inventory_count: int
    endpoint_candidate_count: int
    pair_candidate_count: int
    zero_posted_outcome_inventory_count: int
    full_cross_trial_cartesian_enumeration_performed: bool
    bounded_work_preflight_performed: bool
    source_inventory_integrity_verified: bool
    source_bundle_replay_performed: bool
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
        _require_text(self.packet_id, "packet_id")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_POLICY_ID:
            raise ValueError("unsupported harmonization packet policy_id")
        _require_sha256(self.spec_sha256, "spec_sha256")
        _require_non_negative_int(
            self.max_endpoint_candidate_count,
            "max_endpoint_candidate_count",
        )
        if not (
            0
            < self.max_endpoint_candidate_count
            <= MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT
        ):
            raise ValueError(
                "max_endpoint_candidate_count is outside the supported bound"
            )
        _require_non_negative_int(self.max_pair_count, "max_pair_count")
        if not 0 < self.max_pair_count <= MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError("max_pair_count is outside the supported bound")
        typed_arrays = (
            (
                "inventory_bindings",
                ClinicalTrialsGovHarmonizationInventoryBinding,
            ),
            ("safety_contexts", CrossTrialSafetyContext),
            ("endpoint_candidates", CrossTrialEndpointCandidate),
            ("pair_candidates", CrossTrialEndpointPairCandidate),
        )
        for field_name, record_type in typed_arrays:
            values = _tuple(getattr(self, field_name), field_name)
            if any(not isinstance(item, record_type) for item in values):
                raise TypeError(f"{field_name} contains an invalid record")
            object.__setattr__(self, field_name, values)
        bindings = self.inventory_bindings
        if len(bindings) < 2 or bindings != tuple(
            sorted(bindings, key=lambda item: item.nct_id)
        ):
            raise ValueError("inventory bindings are not canonical")
        if len(bindings) > MAX_CROSS_TRIAL_INVENTORY_COUNT:
            raise ValueError("inventory bindings exceed the supported count")
        contexts = self.safety_contexts
        if tuple(item.nct_id for item in contexts) != tuple(
            item.nct_id for item in bindings
        ):
            raise ValueError("safety contexts do not cover canonical inventory order")
        binding_by_nct = {item.nct_id: item for item in bindings}
        context_by_id = {item.safety_context_id: item for item in contexts}
        if len(binding_by_nct) != len(bindings) or len(context_by_id) != len(contexts):
            raise ValueError("inventory or safety context identities are duplicated")
        if len({item.source_receipt_id for item in contexts}) != len(contexts):
            raise ValueError("source receipt identities must be cross-trial distinct")
        if len({item.source_content_hash_sha256 for item in contexts}) != len(contexts):
            raise ValueError("source content hashes must be cross-trial distinct")
        for context in contexts:
            binding = binding_by_nct[context.nct_id]
            if (
                context.inventory_id != binding.inventory_id
                or context.inventory_sha256 != binding.inventory_sha256
                or context.safety_context_id != f"{context.nct_id}:safety-context"
            ):
                raise ValueError("safety context was rebound")
        endpoints = self.endpoint_candidates
        endpoint_by_id = {item.endpoint_candidate_id: item for item in endpoints}
        if len(endpoint_by_id) != len(endpoints):
            raise ValueError("endpoint candidate ids must be unique")
        endpoint_ids_by_nct: dict[str, list[str]] = {
            item.nct_id: [] for item in bindings
        }
        for endpoint in endpoints:
            binding = binding_by_nct.get(endpoint.nct_id)
            context = context_by_id.get(endpoint.safety_context_id)
            if binding is None or context is None:
                raise ValueError("endpoint references an unknown inventory or context")
            if (
                endpoint.inventory_id != binding.inventory_id
                or endpoint.inventory_sha256 != binding.inventory_sha256
                or endpoint.source_receipt_id != context.source_receipt_id
                or endpoint.source_content_hash_sha256
                != context.source_content_hash_sha256
                or endpoint.endpoint_candidate_id
                != f"{endpoint.nct_id}:cross-trial-endpoint:{endpoint.source_index}"
            ):
                raise ValueError("endpoint candidate provenance was rebound")
            endpoint_ids_by_nct[endpoint.nct_id].append(endpoint.endpoint_candidate_id)
        for binding in bindings:
            trial_endpoints = [
                item for item in endpoints if item.nct_id == binding.nct_id
            ]
            context = next(item for item in contexts if item.nct_id == binding.nct_id)
            if len(trial_endpoints) != context.posted_outcome_count:
                raise ValueError(
                    "endpoint candidates do not cover posted outcome count"
                )
            for expected_index, endpoint in enumerate(trial_endpoints):
                if (
                    endpoint.source_index != expected_index
                    or endpoint.posted_outcome_id
                    != f"{binding.nct_id}:posted:{expected_index}"
                    or endpoint.source_json_pointer
                    != (
                        "/resultsSection/outcomeMeasuresModule/outcomeMeasures/"
                        f"{expected_index}"
                    )
                ):
                    raise ValueError("endpoint source identity was rebound")
        expected_endpoint_order = tuple(
            endpoint_id
            for binding in bindings
            for endpoint_id in endpoint_ids_by_nct[binding.nct_id]
        )
        if (
            tuple(item.endpoint_candidate_id for item in endpoints)
            != expected_endpoint_order
        ):
            raise ValueError("endpoint candidates do not use canonical inventory order")
        expected_pair_index = 0
        for left_binding, right_binding in combinations(bindings, 2):
            for left_id, right_id in product(
                endpoint_ids_by_nct[left_binding.nct_id],
                endpoint_ids_by_nct[right_binding.nct_id],
            ):
                expected_pair_id = f"pair:{left_id}::{right_id}"
                if (
                    expected_pair_index >= len(self.pair_candidates)
                    or self.pair_candidates[expected_pair_index].pair_id
                    != expected_pair_id
                ):
                    raise ValueError(
                        "pair candidates are not the full canonical Cartesian set"
                    )
                expected_pair_index += 1
        if expected_pair_index != len(self.pair_candidates):
            raise ValueError("pair candidates are not the full canonical Cartesian set")
        for pair in self.pair_candidates:
            left = endpoint_by_id.get(pair.left_endpoint_candidate_id)
            right = endpoint_by_id.get(pair.right_endpoint_candidate_id)
            if left is None or right is None:
                raise ValueError("pair references an unknown endpoint candidate")
            if (
                pair.left_nct_id != left.nct_id
                or pair.right_nct_id != right.nct_id
                or pair.left_inventory_sha256 != left.inventory_sha256
                or pair.right_inventory_sha256 != right.inventory_sha256
                or pair.left_source_record_sha256 != left.source_record_sha256
                or pair.right_source_record_sha256 != right.source_record_sha256
                or pair.left_safety_context_id != left.safety_context_id
                or pair.right_safety_context_id != right.safety_context_id
            ):
                raise ValueError("pair candidate provenance was rebound")
            expected_pair = _pair_candidate(left, right, context_by_id)
            if pair != expected_pair:
                raise ValueError("pair candidate diagnostics were rebound")
        counts = {
            "inventory_count": len(bindings),
            "endpoint_candidate_count": len(endpoints),
            "pair_candidate_count": len(self.pair_candidates),
            "zero_posted_outcome_inventory_count": sum(
                not endpoint_ids_by_nct[item.nct_id] for item in bindings
            ),
        }
        for field_name, expected in counts.items():
            _require_non_negative_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match packet records")
        if self.pair_candidate_count > self.max_pair_count:
            raise ValueError("pair candidates exceed max_pair_count")
        if self.endpoint_candidate_count > self.max_endpoint_candidate_count:
            raise ValueError("endpoint candidates exceed max_endpoint_candidate_count")
        true_fields = (
            "full_cross_trial_cartesian_enumeration_performed",
            "bounded_work_preflight_performed",
            "source_inventory_integrity_verified",
        )
        false_fields = (
            "source_bundle_replay_performed",
            "reviewer_approval_performed",
            "endpoint_selected",
            "endpoint_family_assigned",
            "ontology_mapping_approved",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "comparative_safety_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, item) for item in true_fields):
            raise ValueError("required enumeration or integrity flag is false")
        if any(getattr(self, item) for item in false_fields):
            raise ValueError("an approval, inference, or synthesis flag was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("harmonization limitations were rebound")
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _safety_context(
    packet: ClinicalTrialsGovInventoryPacket,
) -> CrossTrialSafetyContext:
    references = tuple(
        CrossTrialSafetyRecordReference(
            record_id=item.safety_group_record_id,
            record_type="GROUP",
            source_json_pointer=item.source_json_pointer,
            source_record_sha256=item.source_record_sha256,
            stat_count=0,
        )
        for item in packet.safety_groups
    ) + tuple(
        CrossTrialSafetyRecordReference(
            record_id=item.safety_event_id,
            record_type=(
                "SERIOUS_EVENT" if item.event_category == "SERIOUS" else "OTHER_EVENT"
            ),
            source_json_pointer=item.source_json_pointer,
            source_record_sha256=item.source_record_sha256,
            stat_count=len(item.stats),
        )
        for item in (*packet.serious_events, *packet.other_events)
    )
    return CrossTrialSafetyContext(
        safety_context_id=f"{packet.nct_id}:safety-context",
        inventory_id=packet.inventory_id,
        nct_id=packet.nct_id,
        inventory_sha256=packet.fingerprint,
        source_receipt_id=packet.source.receipt_id,
        source_id=packet.source.source_id,
        source_version=packet.source.source_version,
        source_locator=packet.source.locator,
        source_content_hash_sha256=packet.source.content_hash_sha256,
        source_retrieved_at=packet.source.retrieved_at,
        registry_version=packet.registry_version,
        source_scope_sha256=packet.source_scope_sha256,
        source_has_results=packet.source_has_results,
        protocol_outcome_module_present=packet.protocol_outcome_module_present,
        posted_outcome_module_present=packet.posted_outcome_module_present,
        adverse_event_module_present=packet.adverse_event_module_present,
        adverse_event_time_frame=packet.adverse_event_time_frame,
        adverse_event_description_sha256=packet.adverse_event_description_sha256,
        adverse_event_frequency_threshold=packet.adverse_event_frequency_threshold,
        safety_records=references,
        protocol_outcome_count=packet.protocol_outcome_count,
        posted_outcome_count=packet.posted_outcome_count,
        lexical_link_candidate_count=packet.lexical_link_candidate_count,
        safety_group_count=packet.safety_group_count,
        serious_event_count=packet.serious_event_count,
        other_event_count=packet.other_event_count,
        safety_event_stat_count=packet.safety_event_stat_count,
    )


def _endpoint_candidates(
    packet: ClinicalTrialsGovInventoryPacket,
) -> tuple[CrossTrialEndpointCandidate, ...]:
    result: list[CrossTrialEndpointCandidate] = []
    for outcome in packet.posted_outcomes:
        links = tuple(
            item
            for item in packet.lexical_link_candidates
            if item.posted_outcome_id == outcome.posted_outcome_id
        )
        result.append(
            CrossTrialEndpointCandidate(
                endpoint_candidate_id=(
                    f"{packet.nct_id}:cross-trial-endpoint:{outcome.source_index}"
                ),
                inventory_id=packet.inventory_id,
                nct_id=packet.nct_id,
                inventory_sha256=packet.fingerprint,
                source_receipt_id=packet.source.receipt_id,
                source_content_hash_sha256=packet.source.content_hash_sha256,
                posted_outcome_id=outcome.posted_outcome_id,
                source_index=outcome.source_index,
                source_json_pointer=outcome.source_json_pointer,
                source_record_sha256=outcome.source_record_sha256,
                outcome_type=outcome.outcome_type,
                title=outcome.title,
                time_frame=outcome.time_frame,
                reporting_status=outcome.reporting_status,
                parameter_type=outcome.parameter_type,
                dispersion_type=outcome.dispersion_type,
                unit_of_measure=outcome.unit_of_measure,
                description_sha256=outcome.description_sha256,
                population_description_sha256=outcome.population_description_sha256,
                group_ids=outcome.group_ids,
                denominator_group_ids=outcome.denominator_group_ids,
                measurement_group_ids=outcome.measurement_group_ids,
                analysis_group_id_sets=outcome.analysis_group_id_sets,
                group_count=outcome.group_count,
                denominator_count=outcome.denominator_count,
                class_count=outcome.class_count,
                category_count=outcome.category_count,
                measurement_count=outcome.measurement_count,
                analysis_count=outcome.analysis_count,
                within_trial_protocol_outcome_ids=tuple(
                    item.protocol_outcome_id for item in links
                ),
                within_trial_lexical_link_ids=tuple(item.link_id for item in links),
                within_trial_exact_candidate_count=outcome.exact_candidate_count,
                within_trial_reconciliation_status=outcome.reconciliation_status,
                safety_context_id=f"{packet.nct_id}:safety-context",
            )
        )
    return tuple(result)


def _missing_codes(
    left: CrossTrialEndpointCandidate,
    right: CrossTrialEndpointCandidate,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{side}.{field_name}"
            for side, endpoint in (("left", left), ("right", right))
            for field_name in _ENDPOINT_FIELD_NAMES
            if _normalized_optional(getattr(endpoint, field_name)) is None
        )
    )


def _pair_candidate(
    left: CrossTrialEndpointCandidate,
    right: CrossTrialEndpointCandidate,
    safety_by_id: Mapping[str, CrossTrialSafetyContext],
) -> CrossTrialEndpointPairCandidate:
    diagnostics = {
        f"{field_name}_exact": _observed_equal(
            getattr(left, field_name), getattr(right, field_name)
        )
        for field_name in _ENDPOINT_FIELD_NAMES
    }
    missing = _missing_codes(left, right)
    status = (
        INCOMPLETE_SOURCE_FIELDS
        if missing
        else ALL_MECHANICAL_FIELDS_EQUAL
        if all(diagnostics.values())
        else MIXED_MECHANICAL_FIELDS
    )
    left_safety = safety_by_id[left.safety_context_id]
    right_safety = safety_by_id[right.safety_context_id]
    return CrossTrialEndpointPairCandidate(
        pair_id=f"pair:{left.endpoint_candidate_id}::{right.endpoint_candidate_id}",
        left_endpoint_candidate_id=left.endpoint_candidate_id,
        right_endpoint_candidate_id=right.endpoint_candidate_id,
        left_nct_id=left.nct_id,
        right_nct_id=right.nct_id,
        left_inventory_sha256=left.inventory_sha256,
        right_inventory_sha256=right.inventory_sha256,
        left_source_record_sha256=left.source_record_sha256,
        right_source_record_sha256=right.source_record_sha256,
        left_safety_context_id=left.safety_context_id,
        right_safety_context_id=right.safety_context_id,
        safety_time_frame_exact=_observed_equal(
            left_safety.adverse_event_time_frame,
            right_safety.adverse_event_time_frame,
        ),
        missing_field_codes=missing,
        mechanical_status=status,
        **diagnostics,
    )


def compile_clinicaltrials_gov_harmonization_candidates(
    spec: ClinicalTrialsGovHarmonizationCandidateSpec,
    inventory_packets: Sequence[ClinicalTrialsGovInventoryPacket],
) -> ClinicalTrialsGovHarmonizationCandidatePacket:
    """Enumerate every posted-outcome pair across distinct exact trial inventories."""

    if not isinstance(spec, ClinicalTrialsGovHarmonizationCandidateSpec):
        raise TypeError("spec must be a ClinicalTrialsGovHarmonizationCandidateSpec")
    if isinstance(inventory_packets, (str, bytes)):
        raise TypeError("inventory_packets must be an array")
    packets = tuple(inventory_packets)
    if any(not isinstance(item, ClinicalTrialsGovInventoryPacket) for item in packets):
        raise TypeError("inventory_packets contains an invalid packet")
    packets = tuple(sorted(packets, key=lambda item: item.nct_id))
    actual_bindings = tuple(
        ClinicalTrialsGovHarmonizationInventoryBinding(
            inventory_id=item.inventory_id,
            nct_id=item.nct_id,
            inventory_sha256=item.fingerprint,
        )
        for item in packets
    )
    if actual_bindings != spec.inventory_bindings:
        raise ClinicalTrialsGovHarmonizationError(
            "input inventory packets do not match the exact spec bindings"
        )
    for field_name, values in (
        ("source receipt", [item.source.receipt_id for item in packets]),
        (
            "source content hash",
            [item.source.content_hash_sha256 for item in packets],
        ),
    ):
        if len(values) != len(set(values)):
            raise ClinicalTrialsGovHarmonizationError(
                f"cross-trial inventories must use distinct {field_name} values"
            )
    expected_endpoint_count = sum(item.posted_outcome_count for item in packets)
    if expected_endpoint_count > spec.max_endpoint_candidate_count:
        raise ClinicalTrialsGovHarmonizationError(
            f"expected endpoint count {expected_endpoint_count} exceeds "
            "max_endpoint_candidate_count "
            f"{spec.max_endpoint_candidate_count}"
        )
    expected_pair_count = 0
    prior_endpoint_count = 0
    for packet in packets:
        expected_pair_count += prior_endpoint_count * packet.posted_outcome_count
        prior_endpoint_count += packet.posted_outcome_count
    if expected_pair_count > spec.max_pair_count:
        raise ClinicalTrialsGovHarmonizationError(
            f"expected pair count {expected_pair_count} exceeds max_pair_count "
            f"{spec.max_pair_count}"
        )
    safety_contexts = tuple(_safety_context(item) for item in packets)
    safety_by_id = {item.safety_context_id: item for item in safety_contexts}
    endpoint_groups = tuple(_endpoint_candidates(item) for item in packets)
    endpoints = tuple(item for group in endpoint_groups for item in group)
    pairs = tuple(
        _pair_candidate(left_endpoint, right_endpoint, safety_by_id)
        for left_group, right_group in combinations(endpoint_groups, 2)
        for left_endpoint, right_endpoint in product(left_group, right_group)
    )
    return ClinicalTrialsGovHarmonizationCandidatePacket(
        packet_id=spec.packet_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        max_endpoint_candidate_count=spec.max_endpoint_candidate_count,
        max_pair_count=spec.max_pair_count,
        inventory_bindings=actual_bindings,
        safety_contexts=safety_contexts,
        endpoint_candidates=endpoints,
        pair_candidates=pairs,
        inventory_count=len(packets),
        endpoint_candidate_count=len(endpoints),
        pair_candidate_count=len(pairs),
        zero_posted_outcome_inventory_count=sum(
            item.posted_outcome_count == 0 for item in packets
        ),
        full_cross_trial_cartesian_enumeration_performed=True,
        bounded_work_preflight_performed=True,
        source_inventory_integrity_verified=True,
        source_bundle_replay_performed=False,
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


def validate_clinicaltrials_gov_harmonization_candidates(
    spec: ClinicalTrialsGovHarmonizationCandidateSpec,
    inventory_packets: Sequence[ClinicalTrialsGovInventoryPacket],
    packet: ClinicalTrialsGovHarmonizationCandidatePacket,
) -> tuple[str, ...]:
    """Recompile the complete candidate universe and return deterministic failures."""

    try:
        rebuilt = compile_clinicaltrials_gov_harmonization_candidates(
            spec, inventory_packets
        )
    except (ClinicalTrialsGovHarmonizationError, TypeError, ValueError):
        return ("clinicaltrials_gov_harmonization_recompile_failed",)
    if rebuilt != packet:
        return ("clinicaltrials_gov_harmonization_packet_mismatch",)
    return ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovHarmonizationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovHarmonizationError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovHarmonizationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovHarmonizationError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationError(f"{label} must be an object")
    return dict(value)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationError(f"{path} must be an object")
    data = dict(value)
    if set(data) != expected_fields:
        raise ClinicalTrialsGovHarmonizationError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return data


def clinicaltrials_gov_harmonization_spec_to_dict(
    spec: ClinicalTrialsGovHarmonizationCandidateSpec,
) -> dict[str, Any]:
    if not isinstance(spec, ClinicalTrialsGovHarmonizationCandidateSpec):
        raise TypeError("spec must be a ClinicalTrialsGovHarmonizationCandidateSpec")
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": CLINICALTRIALS_GOV_HARMONIZATION_SPEC_SCHEMA_VERSION,
        **value,
    }


def _binding_from_dict(
    value: Any, path: str
) -> ClinicalTrialsGovHarmonizationInventoryBinding:
    return ClinicalTrialsGovHarmonizationInventoryBinding(
        **_record(
            value,
            path,
            _field_names(ClinicalTrialsGovHarmonizationInventoryBinding),
        )
    )


def clinicaltrials_gov_harmonization_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationCandidateSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovHarmonizationCandidateSpec),
        },
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_HARMONIZATION_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationError(
            "unsupported harmonization spec schema_version"
        )
    data["inventory_bindings"] = tuple(
        _binding_from_dict(item, f"spec.inventory_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["inventory_bindings"], "inventory_bindings")
        )
    )
    return ClinicalTrialsGovHarmonizationCandidateSpec(**data)


def clinicaltrials_gov_harmonization_spec_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationCandidateSpec:
    return clinicaltrials_gov_harmonization_spec_from_dict(
        _load_json(text, "harmonization spec")
    )


def clinicaltrials_gov_harmonization_packet_envelope(
    packet: ClinicalTrialsGovHarmonizationCandidatePacket,
) -> dict[str, Any]:
    if not isinstance(packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError(
            "packet must be a ClinicalTrialsGovHarmonizationCandidatePacket"
        )
    return {
        "schema_version": CLINICALTRIALS_GOV_HARMONIZATION_PACKET_SCHEMA_VERSION,
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _safety_reference_from_dict(
    value: Any, path: str
) -> CrossTrialSafetyRecordReference:
    return CrossTrialSafetyRecordReference(
        **_record(value, path, _field_names(CrossTrialSafetyRecordReference))
    )


def _safety_context_from_dict(value: Any, path: str) -> CrossTrialSafetyContext:
    data = _record(value, path, _field_names(CrossTrialSafetyContext))
    data["safety_records"] = tuple(
        _safety_reference_from_dict(item, f"{path}.safety_records[{index}]")
        for index, item in enumerate(_tuple(data["safety_records"], "safety_records"))
    )
    return CrossTrialSafetyContext(**data)


def _endpoint_from_dict(value: Any, path: str) -> CrossTrialEndpointCandidate:
    return CrossTrialEndpointCandidate(
        **_record(value, path, _field_names(CrossTrialEndpointCandidate))
    )


def _pair_from_dict(value: Any, path: str) -> CrossTrialEndpointPairCandidate:
    return CrossTrialEndpointPairCandidate(
        **_record(value, path, _field_names(CrossTrialEndpointPairCandidate))
    )


def clinicaltrials_gov_harmonization_packet_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationCandidatePacket:
    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "packet"},
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_HARMONIZATION_PACKET_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationError(
            "unsupported harmonization packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalTrialsGovHarmonizationCandidatePacket),
    )
    data["inventory_bindings"] = tuple(
        _binding_from_dict(item, f"packet.inventory_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["inventory_bindings"], "inventory_bindings")
        )
    )
    data["safety_contexts"] = tuple(
        _safety_context_from_dict(item, f"packet.safety_contexts[{index}]")
        for index, item in enumerate(_tuple(data["safety_contexts"], "safety_contexts"))
    )
    data["endpoint_candidates"] = tuple(
        _endpoint_from_dict(item, f"packet.endpoint_candidates[{index}]")
        for index, item in enumerate(
            _tuple(data["endpoint_candidates"], "endpoint_candidates")
        )
    )
    data["pair_candidates"] = tuple(
        _pair_from_dict(item, f"packet.pair_candidates[{index}]")
        for index, item in enumerate(_tuple(data["pair_candidates"], "pair_candidates"))
    )
    packet = ClinicalTrialsGovHarmonizationCandidatePacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovHarmonizationError(
            "harmonization integrity_sha256 mismatch"
        )
    return packet


def clinicaltrials_gov_harmonization_packet_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationCandidatePacket:
    return clinicaltrials_gov_harmonization_packet_from_dict(
        _load_json(text, "harmonization packet")
    )


def clinicaltrials_gov_harmonization_summary(
    packet: ClinicalTrialsGovHarmonizationCandidatePacket,
) -> dict[str, Any]:
    if not isinstance(packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError(
            "packet must be a ClinicalTrialsGovHarmonizationCandidatePacket"
        )
    return {
        "packet_id": packet.packet_id,
        "inventory_count": packet.inventory_count,
        "endpoint_candidate_count": packet.endpoint_candidate_count,
        "pair_candidate_count": packet.pair_candidate_count,
        "zero_posted_outcome_inventory_count": (
            packet.zero_posted_outcome_inventory_count
        ),
        "max_endpoint_candidate_count": packet.max_endpoint_candidate_count,
        "max_pair_count": packet.max_pair_count,
        "reviewer_approval_performed": packet.reviewer_approval_performed,
        "clinical_comparability_inferred": packet.clinical_comparability_inferred,
        "benefit_risk_synthesis_performed": (packet.benefit_risk_synthesis_performed),
        "integrity_sha256": packet.fingerprint,
    }
