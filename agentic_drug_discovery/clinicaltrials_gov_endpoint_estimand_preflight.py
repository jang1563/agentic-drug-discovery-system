"""Preregistered endpoint/estimand review preflight for registry pairs.

The preflight consumes the complete cross-trial candidate graph plus exact
structural-presence sidecars. It routes source and identity blockers before
semantic review without excluding pairs or approving endpoint or estimand
equivalence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

from .clinicaltrials_gov_harmonization_candidates import (
    MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT,
    ClinicalTrialsGovHarmonizationCandidatePacket,
    CrossTrialEndpointCandidate,
    CrossTrialEndpointPairCandidate,
)
from .clinicaltrials_gov_inventory import (
    AMBIGUOUS_EXACT_CANDIDATES,
    UNIQUE_EXACT_CANDIDATE,
    UNMATCHED,
)
from .clinicaltrials_gov_structural_presence import (
    ANALYSIS_GROUP_IDS,
    OUTCOME_ANALYSES,
    PRESENT_NONEMPTY,
    ClinicalTrialsGovHarmonizationPresenceReport,
    ClinicalTrialsGovStructuralPresencePacket,
    StructuralPresenceSidecarBinding,
)
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-endpoint-estimand-preflight-spec.v1"
)
CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_PACKET_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-endpoint-estimand-preflight-packet.v1"
)
CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_POLICY_ID = (
    "adds.preregistered-endpoint-estimand-review-preflight.v1"
)

SOURCE_COMPLETION_REQUIRED = "source_completion_required"
ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED = (
    "endpoint_identity_reconciliation_required"
)
READY_FOR_ENDPOINT_ESTIMAND_REVIEW = "ready_for_endpoint_estimand_review"
_REVIEW_ROUTES = (
    SOURCE_COMPLETION_REQUIRED,
    ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
    READY_FOR_ENDPOINT_ESTIMAND_REVIEW,
)

PENDING_SOURCE_COMPLETION = "pending_source_completion"
PENDING_IDENTITY_RECONCILIATION = "pending_identity_reconciliation"
PENDING_HUMAN_REVIEW = "pending_human_review"

REQUIRED_ESTIMAND_DIMENSIONS = (
    "treatment_condition",
    "population",
    "variable",
    "intercurrent_event_strategy",
    "population_level_summary",
)

_ENDPOINT_FIELDS = (
    "title",
    "time_frame",
    "outcome_type",
    "reporting_status",
    "parameter_type",
    "dispersion_type",
    "unit_of_measure",
    "population_description_sha256",
)
_NONBLOCKING_ENDPOINT_FIELDS = ("dispersion_type",)
_BLOCKING_ENDPOINT_FIELDS = tuple(
    item for item in _ENDPOINT_FIELDS if item not in _NONBLOCKING_ENDPOINT_FIELDS
)
_PRESENCE_BLOCKING_STATES = ("absent", "present_null", "present_empty")
_BLOCKER_PATTERN = re.compile(
    r"^(left|right)\.((endpoint_field\."
    + "(?:"
    + "|".join(_BLOCKING_ENDPOINT_FIELDS)
    + r")\.missing)|(outcome_analyses\."
    + "(?:"
    + "|".join(_PRESENCE_BLOCKING_STATES)
    + r"))|(analysis_group_ids\."
    + "(?:"
    + "|".join(_PRESENCE_BLOCKING_STATES)
    + r"))|(protocol_link\.(?:unmatched|ambiguous_exact_candidates)))$"
)
_CONTEXT_GAP_PATTERN = re.compile(
    r"^(left|right)\.endpoint_field\."
    + "(?:"
    + "|".join(_NONBLOCKING_ENDPOINT_FIELDS)
    + r")\.missing$"
)

_REQUIRED_LIMITATIONS = (
    (
        "The preflight is valid only for the exact candidate packet, aggregate "
        "presence report, and source-bound sidecars identified by SHA-256."
    ),
    (
        "Source-completion and identity-reconciliation routes are typed review "
        "blockers, not automatic endpoint-pair exclusion rules."
    ),
    (
        "A ready route means only that fixed preflight prerequisites were observed; "
        "all five estimand dimensions still require independent human review."
    ),
    (
        "No endpoint identity, family, ontology, estimand, population, analysis, "
        "risk-window, safety, or clinical comparability decision is approved."
    ),
    (
        "No pooling, ranking, efficacy or safety inference, benefit-risk synthesis, "
        "regulatory conclusion, or treatment choice is performed."
    ),
)


class ClinicalTrialsGovEndpointEstimandPreflightError(ValueError):
    """Raised when endpoint/estimand preflight cannot compile or replay."""


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


def _sorted_unique_text(value: Any, field_name: str) -> tuple[str, ...]:
    values = _text_tuple(value, field_name)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must use canonical unique sorted order")
    return values


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _is_source_blocker(code: str) -> bool:
    return any(
        marker in code
        for marker in (
            ".endpoint_field.",
            ".outcome_analyses.",
            ".analysis_group_ids.",
        )
    )


def _is_identity_blocker(code: str) -> bool:
    return ".protocol_link." in code


def _route(blocker_codes: tuple[str, ...]) -> tuple[str, str]:
    if any(_is_source_blocker(code) for code in blocker_codes):
        return SOURCE_COMPLETION_REQUIRED, PENDING_SOURCE_COMPLETION
    if any(_is_identity_blocker(code) for code in blocker_codes):
        return (
            ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
            PENDING_IDENTITY_RECONCILIATION,
        )
    return READY_FOR_ENDPOINT_ESTIMAND_REVIEW, PENDING_HUMAN_REVIEW


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovEndpointEstimandPreflightSpec(SerializableRecord):
    packet_id: str
    candidate_packet_sha256: str
    presence_report_sha256: str
    sidecar_bindings: tuple[StructuralPresenceSidecarBinding, ...]
    max_pair_count: int
    required_estimand_dimensions: tuple[str, ...] = REQUIRED_ESTIMAND_DIMENSIONS
    policy_id: str = CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.packet_id, "packet_id")
        _require_sha256(self.candidate_packet_sha256, "candidate_packet_sha256")
        _require_sha256(self.presence_report_sha256, "presence_report_sha256")
        bindings = _tuple(self.sidecar_bindings, "sidecar_bindings")
        if any(
            not isinstance(item, StructuralPresenceSidecarBinding) for item in bindings
        ):
            raise TypeError("sidecar_bindings contains an invalid binding")
        if len(bindings) < 2:
            raise ValueError("sidecar_bindings must contain at least two trials")
        if bindings != tuple(sorted(bindings, key=lambda item: item.nct_id)):
            raise ValueError("sidecar_bindings must use canonical nct_id order")
        for values in (
            [item.nct_id for item in bindings],
            [item.inventory_sha256 for item in bindings],
            [item.sidecar_sha256 for item in bindings],
        ):
            if len(values) != len(set(values)):
                raise ValueError("sidecar binding identities must be unique")
        _require_non_negative_int(self.max_pair_count, "max_pair_count")
        if not 1 <= self.max_pair_count <= MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError("max_pair_count is outside supported bounds")
        dimensions = _text_tuple(
            self.required_estimand_dimensions, "required_estimand_dimensions"
        )
        if dimensions != REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("required estimand dimensions were rebound")
        if self.policy_id != CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_POLICY_ID:
            raise ValueError("unsupported endpoint/estimand preflight policy_id")
        object.__setattr__(self, "sidecar_bindings", bindings)
        object.__setattr__(self, "required_estimand_dimensions", dimensions)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class EndpointEstimandPairPreflight(SerializableRecord):
    pair_id: str
    left_endpoint_candidate_id: str
    right_endpoint_candidate_id: str
    left_nct_id: str
    right_nct_id: str
    left_source_record_sha256: str
    right_source_record_sha256: str
    mechanical_status: str
    blocker_codes: tuple[str, ...]
    context_gap_codes: tuple[str, ...]
    review_route: str
    review_state: str
    required_estimand_dimensions: tuple[str, ...]
    unresolved_estimand_dimensions: tuple[str, ...]
    automatic_exclusion_performed: bool = False
    reviewer_approval_performed: bool = False
    endpoint_identity_approved: bool = False
    endpoint_family_assigned: bool = False
    estimand_equivalence_approved: bool = False
    clinical_comparability_approved: bool = False
    safety_comparability_approved: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "pair_id",
            "left_endpoint_candidate_id",
            "right_endpoint_candidate_id",
            "left_nct_id",
            "right_nct_id",
            "mechanical_status",
            "review_route",
            "review_state",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "left_source_record_sha256",
            "right_source_record_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        codes = _sorted_unique_text(self.blocker_codes, "blocker_codes")
        if any(_BLOCKER_PATTERN.fullmatch(code) is None for code in codes):
            raise ValueError("blocker_codes contains an unsupported code")
        context_gaps = _sorted_unique_text(
            self.context_gap_codes, "context_gap_codes"
        )
        if any(
            _CONTEXT_GAP_PATTERN.fullmatch(code) is None for code in context_gaps
        ):
            raise ValueError("context_gap_codes contains an unsupported code")
        expected_route, expected_state = _route(codes)
        if self.review_route != expected_route or self.review_state != expected_state:
            raise ValueError("review route/state does not match blocker codes")
        dimensions = _text_tuple(
            self.required_estimand_dimensions, "required_estimand_dimensions"
        )
        unresolved = _text_tuple(
            self.unresolved_estimand_dimensions, "unresolved_estimand_dimensions"
        )
        if dimensions != REQUIRED_ESTIMAND_DIMENSIONS or unresolved != dimensions:
            raise ValueError("estimand dimensions must remain fixed and unresolved")
        for field_name in (
            "automatic_exclusion_performed",
            "reviewer_approval_performed",
            "endpoint_identity_approved",
            "endpoint_family_assigned",
            "estimand_equivalence_approved",
            "clinical_comparability_approved",
            "safety_comparability_approved",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")
        object.__setattr__(self, "blocker_codes", codes)
        object.__setattr__(self, "context_gap_codes", context_gaps)
        object.__setattr__(self, "required_estimand_dimensions", dimensions)
        object.__setattr__(self, "unresolved_estimand_dimensions", unresolved)


@dataclass(frozen=True, slots=True)
class EndpointEstimandBlockerCount(SerializableRecord):
    blocker_code: str
    pair_count: int

    def __post_init__(self) -> None:
        _require_text(self.blocker_code, "blocker_code")
        if _BLOCKER_PATTERN.fullmatch(self.blocker_code) is None:
            raise ValueError("unsupported blocker_code")
        _require_non_negative_int(self.pair_count, "pair_count")
        if self.pair_count == 0:
            raise ValueError("blocker pair_count must be positive")


@dataclass(frozen=True, slots=True)
class EndpointEstimandContextGapCount(SerializableRecord):
    context_gap_code: str
    pair_count: int

    def __post_init__(self) -> None:
        _require_text(self.context_gap_code, "context_gap_code")
        if _CONTEXT_GAP_PATTERN.fullmatch(self.context_gap_code) is None:
            raise ValueError("unsupported context_gap_code")
        _require_non_negative_int(self.pair_count, "pair_count")
        if self.pair_count == 0:
            raise ValueError("context-gap pair_count must be positive")


@dataclass(frozen=True, slots=True)
class EndpointEstimandSourceBinding(SerializableRecord):
    nct_id: str
    source_receipt_id: str
    source_version: str
    source_locator: str
    source_retrieved_at: str
    registry_version: str
    inventory_sha256: str
    sidecar_sha256: str
    source_content_hash_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.nct_id, str) or re.fullmatch(
            r"NCT[0-9]{8}", self.nct_id
        ) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        for field_name in (
            "source_receipt_id",
            "source_version",
            "source_locator",
            "source_retrieved_at",
            "registry_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if (
            self.source_version
            != f"clinicaltrials-gov-{self.nct_id}-version-{self.registry_version}"
            or self.source_locator
            != f"https://clinicaltrials.gov/api/v2/studies/{self.nct_id}"
        ):
            raise ValueError("source identity is not canonical")
        try:
            if date.fromisoformat(self.registry_version).isoformat() != self.registry_version:
                raise ValueError
        except ValueError as exc:
            raise ValueError("registry_version must use YYYY-MM-DD") from exc
        try:
            retrieved_at = datetime.fromisoformat(
                self.source_retrieved_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("source_retrieved_at must use ISO 8601") from exc
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("source_retrieved_at must include a timezone")
        for field_name in (
            "inventory_sha256",
            "sidecar_sha256",
            "source_content_hash_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovEndpointEstimandPreflightPacket(SerializableRecord):
    packet_id: str
    policy_id: str
    spec_sha256: str
    candidate_packet_id: str
    candidate_packet_sha256: str
    presence_report_id: str
    presence_report_sha256: str
    source_bindings: tuple[EndpointEstimandSourceBinding, ...]
    required_estimand_dimensions: tuple[str, ...]
    pair_preflights: tuple[EndpointEstimandPairPreflight, ...]
    blocker_counts: tuple[EndpointEstimandBlockerCount, ...]
    context_gap_counts: tuple[EndpointEstimandContextGapCount, ...]
    pair_count: int
    source_completion_required_pair_count: int
    identity_reconciliation_required_pair_count: int
    ready_for_endpoint_estimand_review_pair_count: int
    missing_analysis_pair_count: int
    incomplete_analysis_group_ids_pair_count: int
    blocking_endpoint_field_pair_count: int
    nonblocking_context_gap_pair_count: int
    unresolved_protocol_link_pair_count: int
    exact_input_bindings_verified: bool
    source_presence_provenance_retained: bool
    preregistered_dimensions_fixed: bool
    automatic_exclusion_performed: bool
    reviewer_approval_performed: bool
    endpoint_equivalence_approved: bool
    estimand_equivalence_approved: bool
    clinical_comparability_approved: bool
    safety_comparability_approved: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "packet_id",
            "candidate_packet_id",
            "presence_report_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_POLICY_ID:
            raise ValueError("unsupported endpoint/estimand preflight policy_id")
        for field_name in (
            "spec_sha256",
            "candidate_packet_sha256",
            "presence_report_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        bindings = _tuple(self.source_bindings, "source_bindings")
        if any(
            not isinstance(item, EndpointEstimandSourceBinding) for item in bindings
        ):
            raise TypeError("source_bindings contains an invalid binding")
        if bindings != tuple(sorted(bindings, key=lambda item: item.nct_id)):
            raise ValueError("source_bindings must use canonical nct_id order")
        for values in (
            [item.nct_id for item in bindings],
            [item.source_receipt_id for item in bindings],
            [item.source_version for item in bindings],
            [item.inventory_sha256 for item in bindings],
            [item.sidecar_sha256 for item in bindings],
            [item.source_content_hash_sha256 for item in bindings],
        ):
            if len(values) != len(set(values)):
                raise ValueError("source binding identities must be unique")
        dimensions = _text_tuple(
            self.required_estimand_dimensions, "required_estimand_dimensions"
        )
        if dimensions != REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("required estimand dimensions were rebound")
        pair_preflights = _tuple(self.pair_preflights, "pair_preflights")
        if any(
            not isinstance(item, EndpointEstimandPairPreflight)
            for item in pair_preflights
        ):
            raise TypeError("pair_preflights contains an invalid record")
        if pair_preflights != tuple(
            sorted(pair_preflights, key=lambda item: item.pair_id)
        ):
            raise ValueError("pair_preflights must use canonical pair_id order")
        if len({item.pair_id for item in pair_preflights}) != len(pair_preflights):
            raise ValueError("pair_preflight ids must be unique")
        blocker_counts = _tuple(self.blocker_counts, "blocker_counts")
        if any(
            not isinstance(item, EndpointEstimandBlockerCount)
            for item in blocker_counts
        ):
            raise TypeError("blocker_counts contains an invalid count")
        if blocker_counts != tuple(
            sorted(blocker_counts, key=lambda item: item.blocker_code)
        ):
            raise ValueError("blocker_counts must use canonical blocker-code order")
        expected_blockers = Counter(
            code for pair in pair_preflights for code in pair.blocker_codes
        )
        if expected_blockers != Counter(
            {item.blocker_code: item.pair_count for item in blocker_counts}
        ):
            raise ValueError("blocker counts do not match pair preflights")
        context_gap_counts = _tuple(self.context_gap_counts, "context_gap_counts")
        if any(
            not isinstance(item, EndpointEstimandContextGapCount)
            for item in context_gap_counts
        ):
            raise TypeError("context_gap_counts contains an invalid count")
        if context_gap_counts != tuple(
            sorted(context_gap_counts, key=lambda item: item.context_gap_code)
        ):
            raise ValueError(
                "context_gap_counts must use canonical context-gap-code order"
            )
        expected_context_gaps = Counter(
            code for pair in pair_preflights for code in pair.context_gap_codes
        )
        if expected_context_gaps != Counter(
            {item.context_gap_code: item.pair_count for item in context_gap_counts}
        ):
            raise ValueError("context-gap counts do not match pair preflights")
        for field_name in (
            "pair_count",
            "source_completion_required_pair_count",
            "identity_reconciliation_required_pair_count",
            "ready_for_endpoint_estimand_review_pair_count",
            "missing_analysis_pair_count",
            "incomplete_analysis_group_ids_pair_count",
            "blocking_endpoint_field_pair_count",
            "nonblocking_context_gap_pair_count",
            "unresolved_protocol_link_pair_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.pair_count != len(pair_preflights):
            raise ValueError("pair_count does not match pair_preflights")
        route_counts = Counter(item.review_route for item in pair_preflights)
        expected_route_counts = {
            SOURCE_COMPLETION_REQUIRED: self.source_completion_required_pair_count,
            ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED: (
                self.identity_reconciliation_required_pair_count
            ),
            READY_FOR_ENDPOINT_ESTIMAND_REVIEW: (
                self.ready_for_endpoint_estimand_review_pair_count
            ),
        }
        if any(route_counts[route] != count for route, count in expected_route_counts.items()):
            raise ValueError("review route counts do not match pair preflights")
        if sum(expected_route_counts.values()) != self.pair_count:
            raise ValueError("review routes do not partition pairs")
        observed_categories = {
            "missing_analysis_pair_count": sum(
                any(".outcome_analyses." in code for code in item.blocker_codes)
                for item in pair_preflights
            ),
            "incomplete_analysis_group_ids_pair_count": sum(
                any(".analysis_group_ids." in code for code in item.blocker_codes)
                for item in pair_preflights
            ),
            "blocking_endpoint_field_pair_count": sum(
                any(".endpoint_field." in code for code in item.blocker_codes)
                for item in pair_preflights
            ),
            "nonblocking_context_gap_pair_count": sum(
                bool(item.context_gap_codes) for item in pair_preflights
            ),
            "unresolved_protocol_link_pair_count": sum(
                any(".protocol_link." in code for code in item.blocker_codes)
                for item in pair_preflights
            ),
        }
        for field_name, expected in observed_categories.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match pair preflights")
        true_fields = (
            "exact_input_bindings_verified",
            "source_presence_provenance_retained",
            "preregistered_dimensions_fixed",
        )
        false_fields = (
            "automatic_exclusion_performed",
            "reviewer_approval_performed",
            "endpoint_equivalence_approved",
            "estimand_equivalence_approved",
            "clinical_comparability_approved",
            "safety_comparability_approved",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, field_name) for field_name in true_fields):
            raise ValueError("required preflight assurance is false")
        if any(getattr(self, field_name) for field_name in false_fields):
            raise ValueError("a forbidden approval or inference was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("endpoint/estimand preflight limitations were rebound")
        object.__setattr__(self, "source_bindings", bindings)
        object.__setattr__(self, "required_estimand_dimensions", dimensions)
        object.__setattr__(self, "pair_preflights", pair_preflights)
        object.__setattr__(self, "blocker_counts", blocker_counts)
        object.__setattr__(self, "context_gap_counts", context_gap_counts)
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _canonical_sidecars(
    sidecars: Sequence[ClinicalTrialsGovStructuralPresencePacket],
) -> tuple[ClinicalTrialsGovStructuralPresencePacket, ...]:
    values = _tuple(sidecars, "sidecars")
    if any(
        not isinstance(item, ClinicalTrialsGovStructuralPresencePacket)
        for item in values
    ):
        raise TypeError("sidecars contains an invalid packet")
    result = tuple(sorted(values, key=lambda item: item.nct_id))
    if len({item.nct_id for item in result}) != len(result):
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "sidecar nct_id values must be unique"
        )
    return result


def _side_presence_codes(
    side: str,
    endpoint: CrossTrialEndpointCandidate,
    sidecar: ClinicalTrialsGovStructuralPresencePacket,
) -> tuple[str, ...]:
    records = tuple(
        item
        for item in sidecar.array_records
        if item.posted_outcome_id == endpoint.posted_outcome_id
    )
    if not records:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "sidecar does not cover an endpoint candidate"
        )
    source_hashes = {item.posted_outcome_source_record_sha256 for item in records}
    if source_hashes != {endpoint.source_record_sha256}:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "endpoint source record hash does not match sidecar"
        )
    analyses = tuple(item for item in records if item.array_role == OUTCOME_ANALYSES)
    if len(analyses) != 1:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "endpoint must have exactly one outcome-analyses presence record"
        )
    analysis = analyses[0]
    if analysis.item_count != endpoint.analysis_count:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "endpoint analysis count does not match presence sidecar"
        )
    codes: list[str] = []
    if analysis.presence_state != PRESENT_NONEMPTY:
        codes.append(f"{side}.outcome_analyses.{analysis.presence_state}")
        if any(item.array_role == ANALYSIS_GROUP_IDS for item in records):
            raise ClinicalTrialsGovEndpointEstimandPreflightError(
                "empty analyses unexpectedly contain group-id presence records"
            )
    else:
        group_records = tuple(
            item for item in records if item.array_role == ANALYSIS_GROUP_IDS
        )
        if len(group_records) != analysis.item_count:
            raise ClinicalTrialsGovEndpointEstimandPreflightError(
                "analysis group-id presence coverage is incomplete"
            )
        codes.extend(
            f"{side}.analysis_group_ids.{state}"
            for state in sorted(
                {
                    item.presence_state
                    for item in group_records
                    if item.presence_state != PRESENT_NONEMPTY
                }
            )
        )
    return tuple(codes)


def _side_protocol_code(
    side: str, endpoint: CrossTrialEndpointCandidate
) -> str | None:
    status = endpoint.within_trial_reconciliation_status
    if status == UNIQUE_EXACT_CANDIDATE:
        return None
    if status not in {UNMATCHED, AMBIGUOUS_EXACT_CANDIDATES}:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "unsupported within-trial reconciliation status"
        )
    return f"{side}.protocol_link.{status}"


def _pair_preflight(
    pair: CrossTrialEndpointPairCandidate,
    endpoint_by_id: Mapping[str, CrossTrialEndpointCandidate],
    sidecar_by_nct: Mapping[str, ClinicalTrialsGovStructuralPresencePacket],
) -> EndpointEstimandPairPreflight:
    try:
        left = endpoint_by_id[pair.left_endpoint_candidate_id]
        right = endpoint_by_id[pair.right_endpoint_candidate_id]
        left_sidecar = sidecar_by_nct[left.nct_id]
        right_sidecar = sidecar_by_nct[right.nct_id]
    except KeyError as exc:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "pair references an unknown endpoint or sidecar"
        ) from exc
    codes: list[str] = []
    context_gap_codes: list[str] = []
    for missing in pair.missing_field_codes:
        side, field_name = missing.split(".", maxsplit=1)
        code = f"{side}.endpoint_field.{field_name}.missing"
        if field_name in _NONBLOCKING_ENDPOINT_FIELDS:
            context_gap_codes.append(code)
        else:
            codes.append(code)
    codes.extend(_side_presence_codes("left", left, left_sidecar))
    codes.extend(_side_presence_codes("right", right, right_sidecar))
    for side, endpoint in (("left", left), ("right", right)):
        protocol_code = _side_protocol_code(side, endpoint)
        if protocol_code is not None:
            codes.append(protocol_code)
    blocker_codes = tuple(sorted(set(codes)))
    route, state = _route(blocker_codes)
    return EndpointEstimandPairPreflight(
        pair_id=pair.pair_id,
        left_endpoint_candidate_id=pair.left_endpoint_candidate_id,
        right_endpoint_candidate_id=pair.right_endpoint_candidate_id,
        left_nct_id=pair.left_nct_id,
        right_nct_id=pair.right_nct_id,
        left_source_record_sha256=pair.left_source_record_sha256,
        right_source_record_sha256=pair.right_source_record_sha256,
        mechanical_status=pair.mechanical_status,
        blocker_codes=blocker_codes,
        context_gap_codes=tuple(sorted(set(context_gap_codes))),
        review_route=route,
        review_state=state,
        required_estimand_dimensions=REQUIRED_ESTIMAND_DIMENSIONS,
        unresolved_estimand_dimensions=REQUIRED_ESTIMAND_DIMENSIONS,
    )


def compile_clinicaltrials_gov_endpoint_estimand_preflight(
    spec: ClinicalTrialsGovEndpointEstimandPreflightSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    presence_report: ClinicalTrialsGovHarmonizationPresenceReport,
    sidecars: Sequence[ClinicalTrialsGovStructuralPresencePacket],
) -> ClinicalTrialsGovEndpointEstimandPreflightPacket:
    """Compile a bounded pairwise review preflight without semantic approval."""

    if not isinstance(spec, ClinicalTrialsGovEndpointEstimandPreflightSpec):
        raise TypeError("spec must be a preflight spec")
    if not isinstance(candidate_packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError("candidate_packet must be a harmonization candidate packet")
    if not isinstance(presence_report, ClinicalTrialsGovHarmonizationPresenceReport):
        raise TypeError("presence_report must be a harmonization presence report")
    if spec.candidate_packet_sha256 != candidate_packet.fingerprint:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "candidate packet fingerprint does not match preflight spec"
        )
    if spec.presence_report_sha256 != presence_report.fingerprint:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "presence report fingerprint does not match preflight spec"
        )
    if (
        presence_report.candidate_packet_id != candidate_packet.packet_id
        or presence_report.candidate_packet_sha256 != candidate_packet.fingerprint
    ):
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "presence report was rebound to a different candidate packet"
        )
    if spec.sidecar_bindings != presence_report.sidecar_bindings:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "preflight sidecar bindings do not match presence report"
        )
    canonical_sidecars = _canonical_sidecars(sidecars)
    observed_bindings = tuple(
        StructuralPresenceSidecarBinding(
            nct_id=item.nct_id,
            inventory_sha256=item.inventory_sha256,
            sidecar_sha256=item.fingerprint,
        )
        for item in canonical_sidecars
    )
    if observed_bindings != spec.sidecar_bindings:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "exact sidecars do not match preflight bindings"
        )
    if candidate_packet.pair_candidate_count > spec.max_pair_count:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "candidate pairs exceed preregistered max_pair_count"
        )
    context_by_nct = {
        item.nct_id: item for item in candidate_packet.safety_contexts
    }
    for sidecar in canonical_sidecars:
        context = context_by_nct.get(sidecar.nct_id)
        if context is None or (
            context.source_receipt_id != sidecar.source_receipt_id
            or context.source_content_hash_sha256
            != sidecar.source_content_hash_sha256
            or context.inventory_sha256 != sidecar.inventory_sha256
            or context.registry_version != sidecar.registry_version
        ):
            raise ClinicalTrialsGovEndpointEstimandPreflightError(
                "candidate source context does not match presence sidecar"
            )
    endpoint_by_id = {
        item.endpoint_candidate_id: item
        for item in candidate_packet.endpoint_candidates
    }
    sidecar_by_nct = {item.nct_id: item for item in canonical_sidecars}
    pair_preflights = tuple(
        sorted(
            (
                _pair_preflight(pair, endpoint_by_id, sidecar_by_nct)
                for pair in candidate_packet.pair_candidates
            ),
            key=lambda item: item.pair_id,
        )
    )
    blocker_counter = Counter(
        code for pair in pair_preflights for code in pair.blocker_codes
    )
    blocker_counts = tuple(
        EndpointEstimandBlockerCount(blocker_code=code, pair_count=count)
        for code, count in sorted(blocker_counter.items())
    )
    context_gap_counter = Counter(
        code for pair in pair_preflights for code in pair.context_gap_codes
    )
    context_gap_counts = tuple(
        EndpointEstimandContextGapCount(context_gap_code=code, pair_count=count)
        for code, count in sorted(context_gap_counter.items())
    )
    routes = Counter(item.review_route for item in pair_preflights)
    return ClinicalTrialsGovEndpointEstimandPreflightPacket(
        packet_id=spec.packet_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        candidate_packet_id=candidate_packet.packet_id,
        candidate_packet_sha256=candidate_packet.fingerprint,
        presence_report_id=presence_report.report_id,
        presence_report_sha256=presence_report.fingerprint,
        source_bindings=tuple(
            EndpointEstimandSourceBinding(
                nct_id=item.nct_id,
                source_receipt_id=item.source_receipt_id,
                source_version=context_by_nct[item.nct_id].source_version,
                source_locator=context_by_nct[item.nct_id].source_locator,
                source_retrieved_at=context_by_nct[item.nct_id].source_retrieved_at,
                registry_version=item.registry_version,
                inventory_sha256=item.inventory_sha256,
                sidecar_sha256=item.fingerprint,
                source_content_hash_sha256=item.source_content_hash_sha256,
            )
            for item in canonical_sidecars
        ),
        required_estimand_dimensions=spec.required_estimand_dimensions,
        pair_preflights=pair_preflights,
        blocker_counts=blocker_counts,
        context_gap_counts=context_gap_counts,
        pair_count=len(pair_preflights),
        source_completion_required_pair_count=routes[SOURCE_COMPLETION_REQUIRED],
        identity_reconciliation_required_pair_count=routes[
            ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED
        ],
        ready_for_endpoint_estimand_review_pair_count=routes[
            READY_FOR_ENDPOINT_ESTIMAND_REVIEW
        ],
        missing_analysis_pair_count=sum(
            any(".outcome_analyses." in code for code in item.blocker_codes)
            for item in pair_preflights
        ),
        incomplete_analysis_group_ids_pair_count=sum(
            any(".analysis_group_ids." in code for code in item.blocker_codes)
            for item in pair_preflights
        ),
        blocking_endpoint_field_pair_count=sum(
            any(".endpoint_field." in code for code in item.blocker_codes)
            for item in pair_preflights
        ),
        nonblocking_context_gap_pair_count=sum(
            bool(item.context_gap_codes) for item in pair_preflights
        ),
        unresolved_protocol_link_pair_count=sum(
            any(".protocol_link." in code for code in item.blocker_codes)
            for item in pair_preflights
        ),
        exact_input_bindings_verified=True,
        source_presence_provenance_retained=True,
        preregistered_dimensions_fixed=True,
        automatic_exclusion_performed=False,
        reviewer_approval_performed=False,
        endpoint_equivalence_approved=False,
        estimand_equivalence_approved=False,
        clinical_comparability_approved=False,
        safety_comparability_approved=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_endpoint_estimand_preflight(
    spec: ClinicalTrialsGovEndpointEstimandPreflightSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    presence_report: ClinicalTrialsGovHarmonizationPresenceReport,
    sidecars: Sequence[ClinicalTrialsGovStructuralPresencePacket],
    packet: ClinicalTrialsGovEndpointEstimandPreflightPacket,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_endpoint_estimand_preflight(
            spec, candidate_packet, presence_report, sidecars
        )
    except (ClinicalTrialsGovEndpointEstimandPreflightError, TypeError, ValueError):
        return ("clinicaltrials_gov_endpoint_estimand_preflight_recompile_failed",)
    if rebuilt != packet:
        return ("clinicaltrials_gov_endpoint_estimand_preflight_packet_mismatch",)
    return ()


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            f"{path} must be an object"
        )
    return dict(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovEndpointEstimandPreflightError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovEndpointEstimandPreflightError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovEndpointEstimandPreflightError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    return _mapping(value, label)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected: set[str]) -> dict[str, Any]:
    data = _mapping(value, path)
    if set(data) != expected:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            f"{path} must contain exactly {sorted(expected)}"
        )
    return data


def _binding_from_dict(value: Any, path: str) -> StructuralPresenceSidecarBinding:
    return StructuralPresenceSidecarBinding(
        **_record(value, path, _field_names(StructuralPresenceSidecarBinding))
    )


def _source_binding_from_dict(
    value: Any, path: str
) -> EndpointEstimandSourceBinding:
    return EndpointEstimandSourceBinding(
        **_record(value, path, _field_names(EndpointEstimandSourceBinding))
    )


def clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict(
    spec: ClinicalTrialsGovEndpointEstimandPreflightSpec,
) -> dict[str, Any]:
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_SPEC_SCHEMA_VERSION
        ),
        **value,
    }


def clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovEndpointEstimandPreflightSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovEndpointEstimandPreflightSpec),
        },
    )
    if data.pop("schema_version") != (
        CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "unsupported endpoint/estimand preflight spec schema_version"
        )
    data["sidecar_bindings"] = tuple(
        _binding_from_dict(item, f"spec.sidecar_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["sidecar_bindings"], "sidecar_bindings")
        )
    )
    data["required_estimand_dimensions"] = tuple(
        _tuple(data["required_estimand_dimensions"], "required_estimand_dimensions")
    )
    return ClinicalTrialsGovEndpointEstimandPreflightSpec(**data)


def clinicaltrials_gov_endpoint_estimand_preflight_spec_from_json(
    text: str,
) -> ClinicalTrialsGovEndpointEstimandPreflightSpec:
    return clinicaltrials_gov_endpoint_estimand_preflight_spec_from_dict(
        _load_json(text, "endpoint/estimand preflight spec")
    )


def clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope(
    packet: ClinicalTrialsGovEndpointEstimandPreflightPacket,
) -> dict[str, Any]:
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_PACKET_SCHEMA_VERSION
        ),
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _pair_from_dict(value: Any, path: str) -> EndpointEstimandPairPreflight:
    data = _record(value, path, _field_names(EndpointEstimandPairPreflight))
    for field_name in (
        "blocker_codes",
        "context_gap_codes",
        "required_estimand_dimensions",
        "unresolved_estimand_dimensions",
    ):
        data[field_name] = tuple(_tuple(data[field_name], field_name))
    return EndpointEstimandPairPreflight(**data)


def _blocker_count_from_dict(value: Any, path: str) -> EndpointEstimandBlockerCount:
    return EndpointEstimandBlockerCount(
        **_record(value, path, _field_names(EndpointEstimandBlockerCount))
    )


def _context_gap_count_from_dict(
    value: Any, path: str
) -> EndpointEstimandContextGapCount:
    return EndpointEstimandContextGapCount(
        **_record(value, path, _field_names(EndpointEstimandContextGapCount))
    )


def clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(
    value: Any,
) -> ClinicalTrialsGovEndpointEstimandPreflightPacket:
    envelope = _record(
        value, "envelope", {"schema_version", "integrity_sha256", "packet"}
    )
    if envelope["schema_version"] != (
        CLINICALTRIALS_GOV_ENDPOINT_ESTIMAND_PREFLIGHT_PACKET_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "unsupported endpoint/estimand preflight packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalTrialsGovEndpointEstimandPreflightPacket),
    )
    data["source_bindings"] = tuple(
        _source_binding_from_dict(item, f"packet.source_bindings[{index}]")
        for index, item in enumerate(
            _tuple(data["source_bindings"], "source_bindings")
        )
    )
    data["required_estimand_dimensions"] = tuple(
        _tuple(data["required_estimand_dimensions"], "required_estimand_dimensions")
    )
    data["pair_preflights"] = tuple(
        _pair_from_dict(item, f"packet.pair_preflights[{index}]")
        for index, item in enumerate(
            _tuple(data["pair_preflights"], "pair_preflights")
        )
    )
    data["blocker_counts"] = tuple(
        _blocker_count_from_dict(item, f"packet.blocker_counts[{index}]")
        for index, item in enumerate(
            _tuple(data["blocker_counts"], "blocker_counts")
        )
    )
    data["context_gap_counts"] = tuple(
        _context_gap_count_from_dict(item, f"packet.context_gap_counts[{index}]")
        for index, item in enumerate(
            _tuple(data["context_gap_counts"], "context_gap_counts")
        )
    )
    data["limitations"] = tuple(_tuple(data["limitations"], "limitations"))
    packet = ClinicalTrialsGovEndpointEstimandPreflightPacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovEndpointEstimandPreflightError(
            "endpoint/estimand preflight integrity_sha256 mismatch"
        )
    return packet


def clinicaltrials_gov_endpoint_estimand_preflight_packet_from_json(
    text: str,
) -> ClinicalTrialsGovEndpointEstimandPreflightPacket:
    return clinicaltrials_gov_endpoint_estimand_preflight_packet_from_dict(
        _load_json(text, "endpoint/estimand preflight packet")
    )


def clinicaltrials_gov_endpoint_estimand_preflight_summary(
    packet: ClinicalTrialsGovEndpointEstimandPreflightPacket,
) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "pair_count": packet.pair_count,
        "source_completion_required_pair_count": (
            packet.source_completion_required_pair_count
        ),
        "identity_reconciliation_required_pair_count": (
            packet.identity_reconciliation_required_pair_count
        ),
        "ready_for_endpoint_estimand_review_pair_count": (
            packet.ready_for_endpoint_estimand_review_pair_count
        ),
        "missing_analysis_pair_count": packet.missing_analysis_pair_count,
        "incomplete_analysis_group_ids_pair_count": (
            packet.incomplete_analysis_group_ids_pair_count
        ),
        "blocking_endpoint_field_pair_count": (
            packet.blocking_endpoint_field_pair_count
        ),
        "nonblocking_context_gap_pair_count": (
            packet.nonblocking_context_gap_pair_count
        ),
        "unresolved_protocol_link_pair_count": (
            packet.unresolved_protocol_link_pair_count
        ),
        "automatic_exclusion_performed": packet.automatic_exclusion_performed,
        "reviewer_approval_performed": packet.reviewer_approval_performed,
        "integrity_sha256": packet.fingerprint,
    }
