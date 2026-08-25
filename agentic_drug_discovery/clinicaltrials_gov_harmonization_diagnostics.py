"""Payload-free diagnostics for cross-trial harmonization review workload."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date
from typing import Any

from .clinicaltrials_gov_harmonization_candidates import (
    ALL_MECHANICAL_FIELDS_EQUAL,
    INCOMPLETE_SOURCE_FIELDS,
    MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT,
    MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT,
    MAX_CROSS_TRIAL_INVENTORY_COUNT,
    MIXED_MECHANICAL_FIELDS,
    ClinicalTrialsGovHarmonizationCandidatePacket,
    CrossTrialEndpointCandidate,
)
from .clinicaltrials_gov_inventory import (
    AMBIGUOUS_EXACT_CANDIDATES,
    UNIQUE_EXACT_CANDIDATE,
    UNMATCHED,
)
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-diagnostic-spec.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_REPORT_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-diagnostic-report.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_POLICY_ID = (
    "adds.payload-free-harmonization-difficulty-diagnostics.v1"
)

SEMANTIC_ENDPOINT_REVIEW_REQUIRED = "semantic_endpoint_review_required"
SOURCE_FIELD_COMPLETION_REQUIRED = "source_field_completion_required"
WITHIN_TRIAL_RECONCILIATION_REVIEW_REQUIRED = (
    "within_trial_reconciliation_review_required"
)
TITLE_IDENTITY_REVIEW_REQUIRED = "title_identity_review_required"
TIME_FRAME_REVIEW_REQUIRED = "time_frame_review_required"
OUTCOME_TYPE_REVIEW_REQUIRED = "outcome_type_review_required"
REPORTING_STATUS_REVIEW_REQUIRED = "reporting_status_review_required"
ESTIMAND_STRUCTURE_REVIEW_REQUIRED = "estimand_structure_review_required"
POPULATION_REVIEW_REQUIRED = "population_review_required"
SAFETY_WINDOW_REVIEW_REQUIRED = "safety_window_review_required"

_ROUTE_CODES = (
    SEMANTIC_ENDPOINT_REVIEW_REQUIRED,
    SOURCE_FIELD_COMPLETION_REQUIRED,
    WITHIN_TRIAL_RECONCILIATION_REVIEW_REQUIRED,
    TITLE_IDENTITY_REVIEW_REQUIRED,
    TIME_FRAME_REVIEW_REQUIRED,
    OUTCOME_TYPE_REVIEW_REQUIRED,
    REPORTING_STATUS_REVIEW_REQUIRED,
    ESTIMAND_STRUCTURE_REVIEW_REQUIRED,
    POPULATION_REVIEW_REQUIRED,
    SAFETY_WINDOW_REVIEW_REQUIRED,
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
_PAIR_FIELD_FLAGS = (
    ("title", "title_exact"),
    ("time_frame", "time_frame_exact"),
    ("outcome_type", "outcome_type_exact"),
    ("reporting_status", "reporting_status_exact"),
    ("parameter_type", "parameter_type_exact"),
    ("dispersion_type", "dispersion_type_exact"),
    ("unit_of_measure", "unit_of_measure_exact"),
    (
        "population_description_sha256",
        "population_description_sha256_exact",
    ),
    ("safety_time_frame", "safety_time_frame_exact"),
)
_STRUCTURAL_FIELDS = (
    "group_count",
    "denominator_count",
    "class_count",
    "category_count",
    "measurement_count",
    "analysis_count",
    "analysis_group_id_sets",
)
_RECONCILIATION_STATUSES = (
    UNMATCHED,
    UNIQUE_EXACT_CANDIDATE,
    AMBIGUOUS_EXACT_CANDIDATES,
)
_MECHANICAL_STATUSES = (
    INCOMPLETE_SOURCE_FIELDS,
    ALL_MECHANICAL_FIELDS_EQUAL,
    MIXED_MECHANICAL_FIELDS,
)
_REQUIRED_LIMITATIONS = (
    (
        "Diagnostics are complete only for the exact input candidate packet and "
        "cannot recover registry fields or trials absent upstream."
    ),
    (
        "Counts describe mechanical disagreement and review workload; they do not "
        "measure semantic endpoint equivalence or model accuracy."
    ),
    (
        "Difficulty signatures are overlapping blocker routes, not independent "
        "errors, clinical outcomes, or validated adjudication labels."
    ),
    (
        "Safety-window diagnostics do not establish common risk windows, event "
        "causality, comparative safety, or acceptability."
    ),
    (
        "No pair is automatically approved or excluded, and no pooling, synthesis, "
        "regulatory inference, or treatment choice is performed."
    ),
)
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")


class ClinicalTrialsGovHarmonizationDiagnosticError(ValueError):
    """Raised when a harmonization diagnostic cannot be compiled or replayed."""


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


def _observed(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationDiagnosticSpec(SerializableRecord):
    report_id: str
    candidate_packet_sha256: str
    policy_id: str = CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.report_id, "report_id")
        _require_sha256(self.candidate_packet_sha256, "candidate_packet_sha256")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_POLICY_ID:
            raise ValueError("unsupported harmonization diagnostic policy_id")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class DiagnosticCount(SerializableRecord):
    code: str
    count: int

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_non_negative_int(self.count, "count")


@dataclass(frozen=True, slots=True)
class TrialHarmonizationDiagnostic(SerializableRecord):
    nct_id: str
    inventory_sha256: str
    source_content_hash_sha256: str
    registry_version: str
    source_has_results: bool
    protocol_outcome_module_present: bool
    posted_outcome_module_present: bool
    adverse_event_module_present: bool
    protocol_outcome_count: int
    posted_outcome_count: int
    lexical_link_candidate_count: int
    safety_group_count: int
    serious_event_count: int
    other_event_count: int
    safety_event_stat_count: int
    endpoint_field_missing_counts: tuple[DiagnosticCount, ...]
    reconciliation_status_counts: tuple[DiagnosticCount, ...]

    def __post_init__(self) -> None:
        _require_text(self.nct_id, "nct_id")
        _require_text(self.registry_version, "registry_version")
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        try:
            if (
                date.fromisoformat(self.registry_version).isoformat()
                != self.registry_version
            ):
                raise ValueError("registry_version must use YYYY-MM-DD")
        except ValueError as exc:
            raise ValueError("registry_version must use YYYY-MM-DD") from exc
        for field_name in (
            "inventory_sha256",
            "source_content_hash_sha256",
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
            "protocol_outcome_count",
            "posted_outcome_count",
            "lexical_link_candidate_count",
            "safety_group_count",
            "serious_event_count",
            "other_event_count",
            "safety_event_stat_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        missing = _diagnostic_counts(
            self.endpoint_field_missing_counts,
            "endpoint_field_missing_counts",
            _ENDPOINT_FIELDS,
            self.posted_outcome_count,
        )
        reconciliation = _diagnostic_counts(
            self.reconciliation_status_counts,
            "reconciliation_status_counts",
            _RECONCILIATION_STATUSES,
            self.posted_outcome_count,
            partition=True,
        )
        if not self.protocol_outcome_module_present and self.protocol_outcome_count:
            raise ValueError("absent protocol outcome module has nonzero records")
        if not self.posted_outcome_module_present and self.posted_outcome_count:
            raise ValueError("absent posted outcome module has nonzero records")
        if not self.adverse_event_module_present and any(
            (
                self.safety_group_count,
                self.serious_event_count,
                self.other_event_count,
                self.safety_event_stat_count,
            )
        ):
            raise ValueError("absent adverse-event module has nonzero records")
        if not self.source_has_results and (
            self.posted_outcome_module_present or self.adverse_event_module_present
        ):
            raise ValueError(
                "result modules are present when source_has_results is false"
            )
        if self.lexical_link_candidate_count > (
            self.protocol_outcome_count * self.posted_outcome_count
        ):
            raise ValueError("lexical link count exceeds the outcome Cartesian set")
        if self.safety_event_stat_count > self.safety_group_count * (
            self.serious_event_count + self.other_event_count
        ):
            raise ValueError("safety statistic count exceeds event-by-group support")
        object.__setattr__(self, "endpoint_field_missing_counts", missing)
        object.__setattr__(self, "reconciliation_status_counts", reconciliation)


@dataclass(frozen=True, slots=True)
class PairFieldDiagnostic(SerializableRecord):
    field_name: str
    pair_count: int
    observed_both_count: int
    missing_pair_count: int
    exact_count: int
    disagreement_count: int

    def __post_init__(self) -> None:
        _require_text(self.field_name, "field_name")
        for field_name in (
            "pair_count",
            "observed_both_count",
            "missing_pair_count",
            "exact_count",
            "disagreement_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.observed_both_count + self.missing_pair_count != self.pair_count:
            raise ValueError("observed and missing field counts do not partition pairs")
        if self.exact_count + self.disagreement_count != self.observed_both_count:
            raise ValueError(
                "exact and disagreement counts do not partition observations"
            )


@dataclass(frozen=True, slots=True)
class StructuralDiagnostic(SerializableRecord):
    field_name: str
    pair_count: int
    exact_count: int
    disagreement_count: int

    def __post_init__(self) -> None:
        _require_text(self.field_name, "field_name")
        for field_name in ("pair_count", "exact_count", "disagreement_count"):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.exact_count + self.disagreement_count != self.pair_count:
            raise ValueError("structural counts do not partition pairs")


@dataclass(frozen=True, slots=True)
class DifficultySignature(SerializableRecord):
    signature_sha256: str
    route_codes: tuple[str, ...]
    pair_count: int

    def __post_init__(self) -> None:
        _require_sha256(self.signature_sha256, "signature_sha256")
        routes = _text_tuple(self.route_codes, "route_codes")
        expected = tuple(code for code in _ROUTE_CODES if code in set(routes))
        if routes != expected or len(routes) != len(set(routes)):
            raise ValueError("route_codes must use canonical policy order")
        if not routes or routes[0] != SEMANTIC_ENDPOINT_REVIEW_REQUIRED:
            raise ValueError("every difficulty signature requires semantic review")
        if self.signature_sha256 != _sha256(routes):
            raise ValueError("signature_sha256 does not match route_codes")
        _require_non_negative_int(self.pair_count, "pair_count")
        if self.pair_count == 0:
            raise ValueError("difficulty signature pair_count must be positive")
        object.__setattr__(self, "route_codes", routes)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationDiagnosticReport(SerializableRecord):
    report_id: str
    policy_id: str
    spec_sha256: str
    candidate_packet_id: str
    candidate_packet_sha256: str
    trial_diagnostics: tuple[TrialHarmonizationDiagnostic, ...]
    pair_field_diagnostics: tuple[PairFieldDiagnostic, ...]
    structural_diagnostics: tuple[StructuralDiagnostic, ...]
    mechanical_status_counts: tuple[DiagnosticCount, ...]
    review_route_counts: tuple[DiagnosticCount, ...]
    difficulty_signatures: tuple[DifficultySignature, ...]
    trial_count: int
    endpoint_candidate_count: int
    pair_candidate_count: int
    unique_difficulty_signature_count: int
    pairs_with_multiple_additional_blockers_count: int
    pairs_with_no_additional_mechanical_blocker_count: int
    payload_free_aggregate_only: bool
    every_pair_requires_semantic_review: bool
    automatic_pair_approval_performed: bool
    automatic_pair_exclusion_performed: bool
    endpoint_family_assigned: bool
    estimand_equivalence_inferred: bool
    clinical_comparability_inferred: bool
    comparative_safety_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "report_id",
            "candidate_packet_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_POLICY_ID:
            raise ValueError("unsupported diagnostic report policy_id")
        for field_name in ("spec_sha256", "candidate_packet_sha256"):
            _require_sha256(getattr(self, field_name), field_name)
        for field_name in (
            "trial_count",
            "endpoint_candidate_count",
            "pair_candidate_count",
            "unique_difficulty_signature_count",
            "pairs_with_multiple_additional_blockers_count",
            "pairs_with_no_additional_mechanical_blocker_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        typed_arrays = (
            ("trial_diagnostics", TrialHarmonizationDiagnostic),
            ("pair_field_diagnostics", PairFieldDiagnostic),
            ("structural_diagnostics", StructuralDiagnostic),
            ("mechanical_status_counts", DiagnosticCount),
            ("review_route_counts", DiagnosticCount),
            ("difficulty_signatures", DifficultySignature),
        )
        for field_name, record_type in typed_arrays:
            values = _tuple(getattr(self, field_name), field_name)
            if any(not isinstance(item, record_type) for item in values):
                raise TypeError(f"{field_name} contains an invalid record")
            object.__setattr__(self, field_name, values)
        if tuple(item.nct_id for item in self.trial_diagnostics) != tuple(
            sorted(item.nct_id for item in self.trial_diagnostics)
        ):
            raise ValueError("trial diagnostics must use canonical nct_id order")
        if len({item.nct_id for item in self.trial_diagnostics}) != len(
            self.trial_diagnostics
        ):
            raise ValueError("trial diagnostic nct_id values must be unique")
        if len({item.inventory_sha256 for item in self.trial_diagnostics}) != len(
            self.trial_diagnostics
        ):
            raise ValueError("trial inventory hashes must be unique")
        if len(
            {item.source_content_hash_sha256 for item in self.trial_diagnostics}
        ) != len(self.trial_diagnostics):
            raise ValueError("trial source content hashes must be unique")
        if tuple(item.field_name for item in self.pair_field_diagnostics) != tuple(
            item[0] for item in _PAIR_FIELD_FLAGS
        ):
            raise ValueError("pair field diagnostics were reordered or omitted")
        if tuple(item.field_name for item in self.structural_diagnostics) != (
            _STRUCTURAL_FIELDS
        ):
            raise ValueError("structural diagnostics were reordered or omitted")
        mechanical = _diagnostic_counts(
            self.mechanical_status_counts,
            "mechanical_status_counts",
            _MECHANICAL_STATUSES,
            self.pair_candidate_count,
            partition=True,
        )
        routes = _diagnostic_counts(
            self.review_route_counts,
            "review_route_counts",
            _ROUTE_CODES,
            self.pair_candidate_count,
        )
        if routes[0].count != self.pair_candidate_count:
            raise ValueError("semantic review route must include every pair")
        object.__setattr__(self, "mechanical_status_counts", mechanical)
        object.__setattr__(self, "review_route_counts", routes)
        signatures = self.difficulty_signatures
        if signatures != tuple(sorted(signatures, key=lambda item: item.route_codes)):
            raise ValueError("difficulty signatures must use canonical route order")
        if len({item.route_codes for item in signatures}) != len(signatures):
            raise ValueError("difficulty signatures must be unique")
        if sum(item.pair_count for item in signatures) != self.pair_candidate_count:
            raise ValueError("difficulty signatures do not partition candidate pairs")
        expected_routes = Counter()
        for signature in signatures:
            for code in signature.route_codes:
                expected_routes[code] += signature.pair_count
        if tuple(item.count for item in routes) != tuple(
            expected_routes[code] for code in _ROUTE_CODES
        ):
            raise ValueError("route counts do not match difficulty signatures")
        if self.trial_count != len(self.trial_diagnostics):
            raise ValueError("trial_count does not match trial diagnostics")
        if not 2 <= self.trial_count <= MAX_CROSS_TRIAL_INVENTORY_COUNT:
            raise ValueError("trial_count is outside the supported bound")
        if self.endpoint_candidate_count != sum(
            item.posted_outcome_count for item in self.trial_diagnostics
        ):
            raise ValueError("endpoint count does not match trial diagnostics")
        if self.endpoint_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT:
            raise ValueError("endpoint count exceeds the supported bound")
        posted_counts = [item.posted_outcome_count for item in self.trial_diagnostics]
        expected_pair_count = sum(
            left_count * right_count
            for left_index, left_count in enumerate(posted_counts)
            for right_count in posted_counts[left_index + 1 :]
        )
        if self.pair_candidate_count != expected_pair_count:
            raise ValueError("pair count is not the complete cross-trial Cartesian set")
        if self.pair_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError("pair count exceeds the supported bound")
        if self.unique_difficulty_signature_count != len(signatures):
            raise ValueError("signature count does not match signatures")
        expected_no_additional = sum(
            item.pair_count for item in signatures if len(item.route_codes) == 1
        )
        expected_multiple = sum(
            item.pair_count for item in signatures if len(item.route_codes) >= 3
        )
        if (
            self.pairs_with_no_additional_mechanical_blocker_count
            != expected_no_additional
            or self.pairs_with_multiple_additional_blockers_count != expected_multiple
        ):
            raise ValueError("difficulty summary counts do not match signatures")
        for item in (*self.pair_field_diagnostics, *self.structural_diagnostics):
            if item.pair_count != self.pair_candidate_count:
                raise ValueError("diagnostic denominator does not match pair count")
        true_fields = (
            "payload_free_aggregate_only",
            "every_pair_requires_semantic_review",
        )
        false_fields = (
            "automatic_pair_approval_performed",
            "automatic_pair_exclusion_performed",
            "endpoint_family_assigned",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "comparative_safety_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, item) for item in true_fields):
            raise ValueError("required aggregate or semantic-review flag is false")
        if any(getattr(self, item) for item in false_fields):
            raise ValueError(
                "an approval, exclusion, inference, or synthesis was enabled"
            )
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("diagnostic limitations were rebound")
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _diagnostic_counts(
    value: Any,
    field_name: str,
    expected_codes: tuple[str, ...],
    upper_bound: int,
    *,
    partition: bool = False,
) -> tuple[DiagnosticCount, ...]:
    values = _tuple(value, field_name)
    if any(not isinstance(item, DiagnosticCount) for item in values):
        raise TypeError(f"{field_name} contains an invalid count")
    if tuple(item.code for item in values) != expected_codes:
        raise ValueError(f"{field_name} codes were reordered or omitted")
    if any(item.count > upper_bound for item in values):
        raise ValueError(f"{field_name} count exceeds its denominator")
    if partition and sum(item.count for item in values) != upper_bound:
        raise ValueError(f"{field_name} does not partition its denominator")
    return values


def _route_codes(
    pair: Any,
    left: CrossTrialEndpointCandidate,
    right: CrossTrialEndpointCandidate,
    structural_equal: Mapping[str, bool],
    safety_observed_both: bool,
) -> tuple[str, ...]:
    routes = {SEMANTIC_ENDPOINT_REVIEW_REQUIRED}
    if pair.missing_field_codes:
        routes.add(SOURCE_FIELD_COMPLETION_REQUIRED)
    if any(
        item.within_trial_reconciliation_status != UNIQUE_EXACT_CANDIDATE
        for item in (left, right)
    ):
        routes.add(WITHIN_TRIAL_RECONCILIATION_REVIEW_REQUIRED)
    if not pair.title_exact:
        routes.add(TITLE_IDENTITY_REVIEW_REQUIRED)
    if not pair.time_frame_exact:
        routes.add(TIME_FRAME_REVIEW_REQUIRED)
    if not pair.outcome_type_exact:
        routes.add(OUTCOME_TYPE_REVIEW_REQUIRED)
    if not pair.reporting_status_exact:
        routes.add(REPORTING_STATUS_REVIEW_REQUIRED)
    if (
        not pair.parameter_type_exact
        or not pair.dispersion_type_exact
        or not pair.unit_of_measure_exact
        or not all(structural_equal.values())
    ):
        routes.add(ESTIMAND_STRUCTURE_REVIEW_REQUIRED)
    if not pair.population_description_sha256_exact:
        routes.add(POPULATION_REVIEW_REQUIRED)
    if not safety_observed_both or not pair.safety_time_frame_exact:
        routes.add(SAFETY_WINDOW_REVIEW_REQUIRED)
    return tuple(code for code in _ROUTE_CODES if code in routes)


def compile_clinicaltrials_gov_harmonization_diagnostic(
    spec: ClinicalTrialsGovHarmonizationDiagnosticSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
) -> ClinicalTrialsGovHarmonizationDiagnosticReport:
    """Aggregate a complete candidate graph without retaining pair-level content."""

    if not isinstance(spec, ClinicalTrialsGovHarmonizationDiagnosticSpec):
        raise TypeError("spec must be a harmonization diagnostic spec")
    if not isinstance(candidate_packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError("candidate_packet must be a harmonization candidate packet")
    if spec.candidate_packet_sha256 != candidate_packet.fingerprint:
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            "candidate packet fingerprint does not match diagnostic spec"
        )
    endpoints_by_id = {
        item.endpoint_candidate_id: item
        for item in candidate_packet.endpoint_candidates
    }
    contexts_by_id = {
        item.safety_context_id: item for item in candidate_packet.safety_contexts
    }
    endpoints_by_nct: dict[str, list[CrossTrialEndpointCandidate]] = {
        item.nct_id: [] for item in candidate_packet.safety_contexts
    }
    for endpoint in candidate_packet.endpoint_candidates:
        endpoints_by_nct[endpoint.nct_id].append(endpoint)
    trial_diagnostics = []
    for context in candidate_packet.safety_contexts:
        endpoints = endpoints_by_nct[context.nct_id]
        missing = Counter(
            field_name
            for endpoint in endpoints
            for field_name in _ENDPOINT_FIELDS
            if not _observed(getattr(endpoint, field_name))
        )
        reconciliation = Counter(
            item.within_trial_reconciliation_status for item in endpoints
        )
        trial_diagnostics.append(
            TrialHarmonizationDiagnostic(
                nct_id=context.nct_id,
                inventory_sha256=context.inventory_sha256,
                source_content_hash_sha256=context.source_content_hash_sha256,
                registry_version=context.registry_version,
                source_has_results=context.source_has_results,
                protocol_outcome_module_present=(
                    context.protocol_outcome_module_present
                ),
                posted_outcome_module_present=context.posted_outcome_module_present,
                adverse_event_module_present=context.adverse_event_module_present,
                protocol_outcome_count=context.protocol_outcome_count,
                posted_outcome_count=context.posted_outcome_count,
                lexical_link_candidate_count=context.lexical_link_candidate_count,
                safety_group_count=context.safety_group_count,
                serious_event_count=context.serious_event_count,
                other_event_count=context.other_event_count,
                safety_event_stat_count=context.safety_event_stat_count,
                endpoint_field_missing_counts=tuple(
                    DiagnosticCount(code=code, count=missing[code])
                    for code in _ENDPOINT_FIELDS
                ),
                reconciliation_status_counts=tuple(
                    DiagnosticCount(code=code, count=reconciliation[code])
                    for code in _RECONCILIATION_STATUSES
                ),
            )
        )

    field_observed = Counter()
    field_exact = Counter()
    structural_exact = Counter()
    mechanical = Counter()
    route_counts = Counter()
    signatures = Counter()
    for pair in candidate_packet.pair_candidates:
        left = endpoints_by_id[pair.left_endpoint_candidate_id]
        right = endpoints_by_id[pair.right_endpoint_candidate_id]
        left_context = contexts_by_id[pair.left_safety_context_id]
        right_context = contexts_by_id[pair.right_safety_context_id]
        for field_name, flag_name in _PAIR_FIELD_FLAGS[:-1]:
            if _observed(getattr(left, field_name)) and _observed(
                getattr(right, field_name)
            ):
                field_observed[field_name] += 1
            if getattr(pair, flag_name):
                field_exact[field_name] += 1
        safety_observed = _observed(
            left_context.adverse_event_time_frame
        ) and _observed(right_context.adverse_event_time_frame)
        if safety_observed:
            field_observed["safety_time_frame"] += 1
        if pair.safety_time_frame_exact:
            field_exact["safety_time_frame"] += 1
        structural_equal = {
            field_name: getattr(left, field_name) == getattr(right, field_name)
            for field_name in _STRUCTURAL_FIELDS
        }
        for field_name, is_equal in structural_equal.items():
            if is_equal:
                structural_exact[field_name] += 1
        routes = _route_codes(
            pair,
            left,
            right,
            structural_equal,
            safety_observed,
        )
        for code in routes:
            route_counts[code] += 1
        signatures[routes] += 1
        mechanical[pair.mechanical_status] += 1

    pair_count = candidate_packet.pair_candidate_count
    pair_fields = tuple(
        PairFieldDiagnostic(
            field_name=field_name,
            pair_count=pair_count,
            observed_both_count=field_observed[field_name],
            missing_pair_count=pair_count - field_observed[field_name],
            exact_count=field_exact[field_name],
            disagreement_count=(field_observed[field_name] - field_exact[field_name]),
        )
        for field_name, _ in _PAIR_FIELD_FLAGS
    )
    structural = tuple(
        StructuralDiagnostic(
            field_name=field_name,
            pair_count=pair_count,
            exact_count=structural_exact[field_name],
            disagreement_count=pair_count - structural_exact[field_name],
        )
        for field_name in _STRUCTURAL_FIELDS
    )
    difficulty_signatures = tuple(
        DifficultySignature(
            signature_sha256=_sha256(route_codes),
            route_codes=route_codes,
            pair_count=count,
        )
        for route_codes, count in sorted(signatures.items())
    )
    return ClinicalTrialsGovHarmonizationDiagnosticReport(
        report_id=spec.report_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        candidate_packet_id=candidate_packet.packet_id,
        candidate_packet_sha256=candidate_packet.fingerprint,
        trial_diagnostics=tuple(trial_diagnostics),
        pair_field_diagnostics=pair_fields,
        structural_diagnostics=structural,
        mechanical_status_counts=tuple(
            DiagnosticCount(code=code, count=mechanical[code])
            for code in _MECHANICAL_STATUSES
        ),
        review_route_counts=tuple(
            DiagnosticCount(code=code, count=route_counts[code])
            for code in _ROUTE_CODES
        ),
        difficulty_signatures=difficulty_signatures,
        trial_count=candidate_packet.inventory_count,
        endpoint_candidate_count=candidate_packet.endpoint_candidate_count,
        pair_candidate_count=pair_count,
        unique_difficulty_signature_count=len(difficulty_signatures),
        pairs_with_multiple_additional_blockers_count=sum(
            count for routes, count in signatures.items() if len(routes) >= 3
        ),
        pairs_with_no_additional_mechanical_blocker_count=signatures[
            (SEMANTIC_ENDPOINT_REVIEW_REQUIRED,)
        ],
        payload_free_aggregate_only=True,
        every_pair_requires_semantic_review=True,
        automatic_pair_approval_performed=False,
        automatic_pair_exclusion_performed=False,
        endpoint_family_assigned=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        comparative_safety_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_harmonization_diagnostic(
    spec: ClinicalTrialsGovHarmonizationDiagnosticSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    report: ClinicalTrialsGovHarmonizationDiagnosticReport,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_harmonization_diagnostic(
            spec, candidate_packet
        )
    except (ClinicalTrialsGovHarmonizationDiagnosticError, TypeError, ValueError):
        return ("clinicaltrials_gov_harmonization_diagnostic_recompile_failed",)
    if rebuilt != report:
        return ("clinicaltrials_gov_harmonization_diagnostic_report_mismatch",)
    return ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovHarmonizationDiagnosticError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovHarmonizationDiagnosticError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovHarmonizationDiagnosticError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            f"{label} must be an object"
        )
    return dict(value)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationDiagnosticError(f"{path} must be an object")
    data = dict(value)
    if set(data) != expected_fields:
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return data


def clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(
    spec: ClinicalTrialsGovHarmonizationDiagnosticSpec,
) -> dict[str, Any]:
    if not isinstance(spec, ClinicalTrialsGovHarmonizationDiagnosticSpec):
        raise TypeError("spec must be a harmonization diagnostic spec")
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_SPEC_SCHEMA_VERSION
        ),
        **value,
    }


def clinicaltrials_gov_harmonization_diagnostic_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationDiagnosticSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovHarmonizationDiagnosticSpec),
        },
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            "unsupported harmonization diagnostic spec schema_version"
        )
    return ClinicalTrialsGovHarmonizationDiagnosticSpec(**data)


def clinicaltrials_gov_harmonization_diagnostic_spec_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationDiagnosticSpec:
    return clinicaltrials_gov_harmonization_diagnostic_spec_from_dict(
        _load_json(text, "harmonization diagnostic spec")
    )


def clinicaltrials_gov_harmonization_diagnostic_report_envelope(
    report: ClinicalTrialsGovHarmonizationDiagnosticReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationDiagnosticReport):
        raise TypeError("report must be a harmonization diagnostic report")
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def _count_from_dict(value: Any, path: str) -> DiagnosticCount:
    return DiagnosticCount(**_record(value, path, _field_names(DiagnosticCount)))


def _trial_from_dict(value: Any, path: str) -> TrialHarmonizationDiagnostic:
    data = _record(value, path, _field_names(TrialHarmonizationDiagnostic))
    for field_name in (
        "endpoint_field_missing_counts",
        "reconciliation_status_counts",
    ):
        data[field_name] = tuple(
            _count_from_dict(item, f"{path}.{field_name}[{index}]")
            for index, item in enumerate(_tuple(data[field_name], field_name))
        )
    return TrialHarmonizationDiagnostic(**data)


def _pair_field_from_dict(value: Any, path: str) -> PairFieldDiagnostic:
    return PairFieldDiagnostic(
        **_record(value, path, _field_names(PairFieldDiagnostic))
    )


def _structural_from_dict(value: Any, path: str) -> StructuralDiagnostic:
    return StructuralDiagnostic(
        **_record(value, path, _field_names(StructuralDiagnostic))
    )


def _signature_from_dict(value: Any, path: str) -> DifficultySignature:
    return DifficultySignature(
        **_record(value, path, _field_names(DifficultySignature))
    )


def clinicaltrials_gov_harmonization_diagnostic_report_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationDiagnosticReport:
    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "report"},
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_HARMONIZATION_DIAGNOSTIC_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            "unsupported harmonization diagnostic report schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "report",
        _field_names(ClinicalTrialsGovHarmonizationDiagnosticReport),
    )
    data["trial_diagnostics"] = tuple(
        _trial_from_dict(item, f"report.trial_diagnostics[{index}]")
        for index, item in enumerate(
            _tuple(data["trial_diagnostics"], "trial_diagnostics")
        )
    )
    data["pair_field_diagnostics"] = tuple(
        _pair_field_from_dict(item, f"report.pair_field_diagnostics[{index}]")
        for index, item in enumerate(
            _tuple(data["pair_field_diagnostics"], "pair_field_diagnostics")
        )
    )
    data["structural_diagnostics"] = tuple(
        _structural_from_dict(item, f"report.structural_diagnostics[{index}]")
        for index, item in enumerate(
            _tuple(data["structural_diagnostics"], "structural_diagnostics")
        )
    )
    for field_name in ("mechanical_status_counts", "review_route_counts"):
        data[field_name] = tuple(
            _count_from_dict(item, f"report.{field_name}[{index}]")
            for index, item in enumerate(_tuple(data[field_name], field_name))
        )
    data["difficulty_signatures"] = tuple(
        _signature_from_dict(item, f"report.difficulty_signatures[{index}]")
        for index, item in enumerate(
            _tuple(data["difficulty_signatures"], "difficulty_signatures")
        )
    )
    report = ClinicalTrialsGovHarmonizationDiagnosticReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovHarmonizationDiagnosticError(
            "harmonization diagnostic integrity_sha256 mismatch"
        )
    return report


def clinicaltrials_gov_harmonization_diagnostic_report_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationDiagnosticReport:
    return clinicaltrials_gov_harmonization_diagnostic_report_from_dict(
        _load_json(text, "harmonization diagnostic report")
    )


def clinicaltrials_gov_harmonization_diagnostic_summary(
    report: ClinicalTrialsGovHarmonizationDiagnosticReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationDiagnosticReport):
        raise TypeError("report must be a harmonization diagnostic report")
    route_counts = {item.code: item.count for item in report.review_route_counts}
    return {
        "report_id": report.report_id,
        "trial_count": report.trial_count,
        "endpoint_candidate_count": report.endpoint_candidate_count,
        "pair_candidate_count": report.pair_candidate_count,
        "unique_difficulty_signature_count": (report.unique_difficulty_signature_count),
        "source_field_completion_required_count": route_counts[
            SOURCE_FIELD_COMPLETION_REQUIRED
        ],
        "estimand_structure_review_required_count": route_counts[
            ESTIMAND_STRUCTURE_REVIEW_REQUIRED
        ],
        "population_review_required_count": route_counts[POPULATION_REVIEW_REQUIRED],
        "safety_window_review_required_count": route_counts[
            SAFETY_WINDOW_REVIEW_REQUIRED
        ],
        "every_pair_requires_semantic_review": (
            report.every_pair_requires_semantic_review
        ),
        "integrity_sha256": report.fingerprint,
    }
