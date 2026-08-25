"""Payload-free decomposition of cross-trial structural disagreement."""

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
from .clinicaltrials_gov_harmonization_diagnostics import (
    ClinicalTrialsGovHarmonizationDiagnosticReport,
)
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-structure-spec.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_REPORT_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-structure-report.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_POLICY_ID = (
    "adds.payload-free-structural-disagreement-decomposition.v1"
)

ALL_STRUCTURAL_FIELDS_EXACT = "all_structural_fields_exact"
TRIAL_GLOBAL_DISAGREEMENT_ONLY = "trial_global_disagreement_only"
ENDPOINT_LOCAL_DISAGREEMENT_PRESENT = "endpoint_local_disagreement_present"

_PAIR_CATEGORY_CODES = (
    ALL_STRUCTURAL_FIELDS_EXACT,
    TRIAL_GLOBAL_DISAGREEMENT_ONLY,
    ENDPOINT_LOCAL_DISAGREEMENT_PRESENT,
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
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_REQUIRED_LIMITATIONS = (
    (
        "The decomposition is complete only for the exact candidate packet and "
        "diagnostic report bound by hash in the spec."
    ),
    (
        "Trial-global and endpoint-local labels are roster-relative mechanical "
        "classifications and can change when the endpoint universe changes."
    ),
    (
        "Endpoint-local disagreement means structural values vary within at least "
        "one trial; it does not establish semantic or estimand nonequivalence."
    ),
    (
        "Upstream optional-array presence provenance is not retained; positive "
        "values establish present nonempty arrays mechanically, while zero or "
        "empty values remain absent-versus-empty non-identifiable."
    ),
    (
        "No structural disagreement is discounted, and no endpoint approval, "
        "clinical comparability, synthesis, regulatory inference, or treatment "
        "choice is performed."
    ),
)


class ClinicalTrialsGovHarmonizationStructureError(ValueError):
    """Raised when a structural decomposition cannot be compiled or replayed."""


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


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationStructureSpec(SerializableRecord):
    report_id: str
    candidate_packet_sha256: str
    diagnostic_report_sha256: str
    policy_id: str = CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.report_id, "report_id")
        _require_sha256(self.candidate_packet_sha256, "candidate_packet_sha256")
        _require_sha256(self.diagnostic_report_sha256, "diagnostic_report_sha256")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_POLICY_ID:
            raise ValueError("unsupported harmonization structure policy_id")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class TrialStructuralFieldProfile(SerializableRecord):
    field_name: str
    endpoint_count: int
    unique_value_count: int
    zero_or_empty_value_count: int
    within_trial_constant: bool
    source_presence_identifiable: bool

    def __post_init__(self) -> None:
        if self.field_name not in _STRUCTURAL_FIELDS:
            raise ValueError("unsupported structural field_name")
        _require_bool(self.within_trial_constant, "within_trial_constant")
        _require_bool(self.source_presence_identifiable, "source_presence_identifiable")
        for field_name in (
            "endpoint_count",
            "unique_value_count",
            "zero_or_empty_value_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.unique_value_count > self.endpoint_count:
            raise ValueError("unique values exceed endpoint_count")
        if self.zero_or_empty_value_count > self.endpoint_count:
            raise ValueError("zero or empty values exceed endpoint_count")
        if self.endpoint_count == 0:
            if self.unique_value_count != 0 or self.within_trial_constant:
                raise ValueError("empty trial structural profile is inconsistent")
        elif self.unique_value_count == 0:
            raise ValueError("nonempty trial structural profile has no values")
        elif self.within_trial_constant != (self.unique_value_count == 1):
            raise ValueError("within_trial_constant does not match unique values")
        if self.source_presence_identifiable:
            if self.endpoint_count == 0 or self.zero_or_empty_value_count != 0:
                raise ValueError(
                    "source presence cannot be fully identified for empty or "
                    "zero-containing profiles"
                )
        elif self.endpoint_count > 0 and self.zero_or_empty_value_count == 0:
            raise ValueError(
                "positive structural values identify present nonempty source arrays"
            )


@dataclass(frozen=True, slots=True)
class TrialStructuralProfile(SerializableRecord):
    nct_id: str
    inventory_sha256: str
    source_content_hash_sha256: str
    endpoint_count: int
    field_profiles: tuple[TrialStructuralFieldProfile, ...]

    def __post_init__(self) -> None:
        _require_text(self.nct_id, "nct_id")
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        _require_sha256(self.inventory_sha256, "inventory_sha256")
        _require_sha256(self.source_content_hash_sha256, "source_content_hash_sha256")
        _require_non_negative_int(self.endpoint_count, "endpoint_count")
        profiles = _tuple(self.field_profiles, "field_profiles")
        if any(not isinstance(item, TrialStructuralFieldProfile) for item in profiles):
            raise TypeError("field_profiles contains an invalid profile")
        if tuple(item.field_name for item in profiles) != _STRUCTURAL_FIELDS:
            raise ValueError("field_profiles were reordered or omitted")
        if any(item.endpoint_count != self.endpoint_count for item in profiles):
            raise ValueError("field profile endpoint_count does not match trial")
        object.__setattr__(self, "field_profiles", profiles)


@dataclass(frozen=True, slots=True)
class StructuralFieldDecomposition(SerializableRecord):
    field_name: str
    pair_count: int
    exact_count: int
    trial_global_disagreement_count: int
    endpoint_local_disagreement_count: int
    source_presence_non_identifiable_pair_count: int

    def __post_init__(self) -> None:
        if self.field_name not in _STRUCTURAL_FIELDS:
            raise ValueError("unsupported structural field_name")
        for field_name in (
            "pair_count",
            "exact_count",
            "trial_global_disagreement_count",
            "endpoint_local_disagreement_count",
            "source_presence_non_identifiable_pair_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if (
            self.exact_count
            + self.trial_global_disagreement_count
            + self.endpoint_local_disagreement_count
            != self.pair_count
        ):
            raise ValueError("structural decomposition does not partition pairs")
        if self.source_presence_non_identifiable_pair_count > self.pair_count:
            raise ValueError("source-presence non-identifiability exceeds pairs")


@dataclass(frozen=True, slots=True)
class PairStructuralCategoryCount(SerializableRecord):
    code: str
    count: int

    def __post_init__(self) -> None:
        if self.code not in _PAIR_CATEGORY_CODES:
            raise ValueError("unsupported pair structural category code")
        _require_non_negative_int(self.count, "count")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationStructureReport(SerializableRecord):
    report_id: str
    policy_id: str
    spec_sha256: str
    candidate_packet_id: str
    candidate_packet_sha256: str
    diagnostic_report_id: str
    diagnostic_report_sha256: str
    trial_profiles: tuple[TrialStructuralProfile, ...]
    field_decompositions: tuple[StructuralFieldDecomposition, ...]
    pair_category_counts: tuple[PairStructuralCategoryCount, ...]
    trial_count: int
    endpoint_candidate_count: int
    pair_candidate_count: int
    trial_global_saturated_field_count: int
    endpoint_local_present_field_count: int
    payload_free_aggregate_only: bool
    structural_value_payloads_retained: bool
    source_presence_identifiable: bool
    source_presence_provenance_retained: bool
    trial_global_disagreement_discounted: bool
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
            "diagnostic_report_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_POLICY_ID:
            raise ValueError("unsupported harmonization structure policy_id")
        for field_name in (
            "spec_sha256",
            "candidate_packet_sha256",
            "diagnostic_report_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        profiles = _tuple(self.trial_profiles, "trial_profiles")
        if any(not isinstance(item, TrialStructuralProfile) for item in profiles):
            raise TypeError("trial_profiles contains an invalid profile")
        if profiles != tuple(sorted(profiles, key=lambda item: item.nct_id)):
            raise ValueError("trial_profiles must use canonical nct_id order")
        if len({item.nct_id for item in profiles}) != len(profiles):
            raise ValueError("trial profile nct_id values must be unique")
        if len({item.inventory_sha256 for item in profiles}) != len(profiles):
            raise ValueError("trial profile inventory hashes must be unique")
        decompositions = _tuple(self.field_decompositions, "field_decompositions")
        if any(
            not isinstance(item, StructuralFieldDecomposition)
            for item in decompositions
        ):
            raise TypeError("field_decompositions contains an invalid decomposition")
        if tuple(item.field_name for item in decompositions) != _STRUCTURAL_FIELDS:
            raise ValueError("field_decompositions were reordered or omitted")
        categories = _tuple(self.pair_category_counts, "pair_category_counts")
        if any(
            not isinstance(item, PairStructuralCategoryCount) for item in categories
        ):
            raise TypeError("pair_category_counts contains an invalid count")
        if tuple(item.code for item in categories) != _PAIR_CATEGORY_CODES:
            raise ValueError("pair_category_counts were reordered or omitted")
        for field_name in (
            "trial_count",
            "endpoint_candidate_count",
            "pair_candidate_count",
            "trial_global_saturated_field_count",
            "endpoint_local_present_field_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.trial_count != len(profiles) or not (
            2 <= self.trial_count <= MAX_CROSS_TRIAL_INVENTORY_COUNT
        ):
            raise ValueError("trial_count does not match supported profiles")
        if self.endpoint_candidate_count != sum(
            item.endpoint_count for item in profiles
        ):
            raise ValueError("endpoint count does not match trial profiles")
        if self.endpoint_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_CANDIDATE_COUNT:
            raise ValueError("endpoint count exceeds the supported bound")
        endpoint_counts = [item.endpoint_count for item in profiles]
        expected_pairs = sum(
            left * right
            for index, left in enumerate(endpoint_counts)
            for right in endpoint_counts[index + 1 :]
        )
        if self.pair_candidate_count != expected_pairs:
            raise ValueError("pair count is not the complete cross-trial Cartesian set")
        if self.pair_candidate_count > MAX_CROSS_TRIAL_ENDPOINT_PAIR_COUNT:
            raise ValueError("pair count exceeds the supported bound")
        if any(item.pair_count != self.pair_candidate_count for item in decompositions):
            raise ValueError("field decomposition denominator does not match pairs")
        if sum(item.count for item in categories) != self.pair_candidate_count:
            raise ValueError("pair structural categories do not partition pairs")
        if self.trial_global_saturated_field_count != sum(
            item.trial_global_disagreement_count == self.pair_candidate_count
            and self.pair_candidate_count > 0
            for item in decompositions
        ):
            raise ValueError("trial-global saturated field count is inconsistent")
        if self.endpoint_local_present_field_count != sum(
            item.endpoint_local_disagreement_count > 0 for item in decompositions
        ):
            raise ValueError("endpoint-local field count is inconsistent")
        true_fields = ("payload_free_aggregate_only",)
        false_fields = (
            "structural_value_payloads_retained",
            "source_presence_provenance_retained",
            "trial_global_disagreement_discounted",
            "endpoint_semantic_equivalence_inferred",
            "estimand_equivalence_inferred",
            "clinical_comparability_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, field_name) for field_name in true_fields):
            raise ValueError("required payload-free flag is false")
        if any(getattr(self, field_name) for field_name in false_fields):
            raise ValueError("a forbidden payload, discount, or inference was enabled")
        _require_bool(self.source_presence_identifiable, "source_presence_identifiable")
        expected_presence_identifiable = all(
            item.source_presence_non_identifiable_pair_count == 0
            for item in decompositions
        )
        if self.source_presence_identifiable != expected_presence_identifiable:
            raise ValueError("source-presence identifiability is inconsistent")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("structural decomposition limitations were rebound")
        object.__setattr__(self, "trial_profiles", profiles)
        object.__setattr__(self, "field_decompositions", decompositions)
        object.__setattr__(self, "pair_category_counts", categories)
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _zero_or_empty(value: Any) -> bool:
    if value == 0:
        return True
    if isinstance(value, tuple):
        return not value or all(_zero_or_empty(item) for item in value)
    return False


def _field_profile(
    field_name: str,
    endpoints: Sequence[CrossTrialEndpointCandidate],
) -> TrialStructuralFieldProfile:
    values = tuple(getattr(item, field_name) for item in endpoints)
    unique_count = len(set(values))
    zero_or_empty_count = sum(_zero_or_empty(item) for item in values)
    return TrialStructuralFieldProfile(
        field_name=field_name,
        endpoint_count=len(endpoints),
        unique_value_count=unique_count,
        zero_or_empty_value_count=zero_or_empty_count,
        within_trial_constant=bool(values) and unique_count == 1,
        source_presence_identifiable=bool(values) and zero_or_empty_count == 0,
    )


def compile_clinicaltrials_gov_harmonization_structure(
    spec: ClinicalTrialsGovHarmonizationStructureSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    diagnostic_report: ClinicalTrialsGovHarmonizationDiagnosticReport,
) -> ClinicalTrialsGovHarmonizationStructureReport:
    """Partition structural disagreement into trial-global and endpoint-local causes."""

    if not isinstance(spec, ClinicalTrialsGovHarmonizationStructureSpec):
        raise TypeError("spec must be a harmonization structure spec")
    if not isinstance(candidate_packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError("candidate_packet must be a harmonization candidate packet")
    if not isinstance(
        diagnostic_report, ClinicalTrialsGovHarmonizationDiagnosticReport
    ):
        raise TypeError("diagnostic_report must be a harmonization diagnostic report")
    if spec.candidate_packet_sha256 != candidate_packet.fingerprint:
        raise ClinicalTrialsGovHarmonizationStructureError(
            "candidate packet fingerprint does not match structure spec"
        )
    if spec.diagnostic_report_sha256 != diagnostic_report.fingerprint:
        raise ClinicalTrialsGovHarmonizationStructureError(
            "diagnostic report fingerprint does not match structure spec"
        )
    if (
        diagnostic_report.candidate_packet_id != candidate_packet.packet_id
        or diagnostic_report.candidate_packet_sha256 != candidate_packet.fingerprint
    ):
        raise ClinicalTrialsGovHarmonizationStructureError(
            "diagnostic report does not bind the candidate packet"
        )
    contexts = {item.nct_id: item for item in candidate_packet.safety_contexts}
    endpoints_by_nct: dict[str, list[CrossTrialEndpointCandidate]] = defaultdict(list)
    endpoints_by_id = {
        item.endpoint_candidate_id: item
        for item in candidate_packet.endpoint_candidates
    }
    for endpoint in candidate_packet.endpoint_candidates:
        endpoints_by_nct[endpoint.nct_id].append(endpoint)
    diagnostic_trials = {
        item.nct_id: item for item in diagnostic_report.trial_diagnostics
    }
    if set(diagnostic_trials) != set(contexts):
        raise ClinicalTrialsGovHarmonizationStructureError(
            "diagnostic trial set does not match candidate packet"
        )
    trial_profiles = []
    constant: dict[tuple[str, str], bool] = {}
    for nct_id in sorted(contexts):
        context = contexts[nct_id]
        diagnostic_trial = diagnostic_trials[nct_id]
        if (
            diagnostic_trial.inventory_sha256 != context.inventory_sha256
            or diagnostic_trial.source_content_hash_sha256
            != context.source_content_hash_sha256
        ):
            raise ClinicalTrialsGovHarmonizationStructureError(
                f"diagnostic provenance does not match {nct_id}"
            )
        endpoints = endpoints_by_nct[nct_id]
        field_profiles = tuple(
            _field_profile(field_name, endpoints) for field_name in _STRUCTURAL_FIELDS
        )
        for item in field_profiles:
            constant[(nct_id, item.field_name)] = item.within_trial_constant
        trial_profiles.append(
            TrialStructuralProfile(
                nct_id=nct_id,
                inventory_sha256=context.inventory_sha256,
                source_content_hash_sha256=context.source_content_hash_sha256,
                endpoint_count=len(endpoints),
                field_profiles=field_profiles,
            )
        )

    field_counts: dict[str, Counter[str]] = {
        field_name: Counter() for field_name in _STRUCTURAL_FIELDS
    }
    pair_categories = Counter()
    for pair in candidate_packet.pair_candidates:
        left = endpoints_by_id[pair.left_endpoint_candidate_id]
        right = endpoints_by_id[pair.right_endpoint_candidate_id]
        local_present = False
        disagreement_present = False
        for field_name in _STRUCTURAL_FIELDS:
            left_value = getattr(left, field_name)
            right_value = getattr(right, field_name)
            if left_value == right_value:
                category = "exact"
            elif (
                constant[(left.nct_id, field_name)]
                and constant[(right.nct_id, field_name)]
            ):
                category = "trial_global"
                disagreement_present = True
            else:
                category = "endpoint_local"
                local_present = True
                disagreement_present = True
            field_counts[field_name][category] += 1
            if _zero_or_empty(left_value) or _zero_or_empty(right_value):
                field_counts[field_name]["source_presence_non_identifiable"] += 1
        if local_present:
            pair_categories[ENDPOINT_LOCAL_DISAGREEMENT_PRESENT] += 1
        elif disagreement_present:
            pair_categories[TRIAL_GLOBAL_DISAGREEMENT_ONLY] += 1
        else:
            pair_categories[ALL_STRUCTURAL_FIELDS_EXACT] += 1

    pair_count = candidate_packet.pair_candidate_count
    decompositions = tuple(
        StructuralFieldDecomposition(
            field_name=field_name,
            pair_count=pair_count,
            exact_count=field_counts[field_name]["exact"],
            trial_global_disagreement_count=(field_counts[field_name]["trial_global"]),
            endpoint_local_disagreement_count=(
                field_counts[field_name]["endpoint_local"]
            ),
            source_presence_non_identifiable_pair_count=(
                field_counts[field_name]["source_presence_non_identifiable"]
            ),
        )
        for field_name in _STRUCTURAL_FIELDS
    )
    diagnostic_structures = {
        item.field_name: item for item in diagnostic_report.structural_diagnostics
    }
    for item in decompositions:
        diagnostic = diagnostic_structures.get(item.field_name)
        if diagnostic is None or (
            diagnostic.pair_count != item.pair_count
            or diagnostic.exact_count != item.exact_count
            or diagnostic.disagreement_count
            != item.trial_global_disagreement_count
            + item.endpoint_local_disagreement_count
        ):
            raise ClinicalTrialsGovHarmonizationStructureError(
                f"structural decomposition does not refine {item.field_name}"
            )
    return ClinicalTrialsGovHarmonizationStructureReport(
        report_id=spec.report_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        candidate_packet_id=candidate_packet.packet_id,
        candidate_packet_sha256=candidate_packet.fingerprint,
        diagnostic_report_id=diagnostic_report.report_id,
        diagnostic_report_sha256=diagnostic_report.fingerprint,
        trial_profiles=tuple(trial_profiles),
        field_decompositions=decompositions,
        pair_category_counts=tuple(
            PairStructuralCategoryCount(code=code, count=pair_categories[code])
            for code in _PAIR_CATEGORY_CODES
        ),
        trial_count=candidate_packet.inventory_count,
        endpoint_candidate_count=candidate_packet.endpoint_candidate_count,
        pair_candidate_count=pair_count,
        trial_global_saturated_field_count=sum(
            item.trial_global_disagreement_count == pair_count and pair_count > 0
            for item in decompositions
        ),
        endpoint_local_present_field_count=sum(
            item.endpoint_local_disagreement_count > 0 for item in decompositions
        ),
        payload_free_aggregate_only=True,
        structural_value_payloads_retained=False,
        source_presence_identifiable=all(
            item.source_presence_non_identifiable_pair_count == 0
            for item in decompositions
        ),
        source_presence_provenance_retained=False,
        trial_global_disagreement_discounted=False,
        endpoint_semantic_equivalence_inferred=False,
        estimand_equivalence_inferred=False,
        clinical_comparability_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_harmonization_structure(
    spec: ClinicalTrialsGovHarmonizationStructureSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    diagnostic_report: ClinicalTrialsGovHarmonizationDiagnosticReport,
    report: ClinicalTrialsGovHarmonizationStructureReport,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_harmonization_structure(
            spec, candidate_packet, diagnostic_report
        )
    except (ClinicalTrialsGovHarmonizationStructureError, TypeError, ValueError):
        return ("clinicaltrials_gov_harmonization_structure_recompile_failed",)
    if rebuilt != report:
        return ("clinicaltrials_gov_harmonization_structure_report_mismatch",)
    return ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovHarmonizationStructureError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovHarmonizationStructureError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovHarmonizationStructureError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovHarmonizationStructureError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationStructureError(f"{label} must be an object")
    return dict(value)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationStructureError(f"{path} must be an object")
    data = dict(value)
    if set(data) != expected_fields:
        raise ClinicalTrialsGovHarmonizationStructureError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return data


def clinicaltrials_gov_harmonization_structure_spec_to_dict(
    spec: ClinicalTrialsGovHarmonizationStructureSpec,
) -> dict[str, Any]:
    if not isinstance(spec, ClinicalTrialsGovHarmonizationStructureSpec):
        raise TypeError("spec must be a harmonization structure spec")
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_SPEC_SCHEMA_VERSION
        ),
        **value,
    }


def clinicaltrials_gov_harmonization_structure_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationStructureSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovHarmonizationStructureSpec),
        },
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationStructureError(
            "unsupported harmonization structure spec schema_version"
        )
    return ClinicalTrialsGovHarmonizationStructureSpec(**data)


def clinicaltrials_gov_harmonization_structure_spec_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationStructureSpec:
    return clinicaltrials_gov_harmonization_structure_spec_from_dict(
        _load_json(text, "harmonization structure spec")
    )


def clinicaltrials_gov_harmonization_structure_report_envelope(
    report: ClinicalTrialsGovHarmonizationStructureReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationStructureReport):
        raise TypeError("report must be a harmonization structure report")
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def _field_profile_from_dict(value: Any, path: str) -> TrialStructuralFieldProfile:
    return TrialStructuralFieldProfile(
        **_record(value, path, _field_names(TrialStructuralFieldProfile))
    )


def _trial_profile_from_dict(value: Any, path: str) -> TrialStructuralProfile:
    data = _record(value, path, _field_names(TrialStructuralProfile))
    data["field_profiles"] = tuple(
        _field_profile_from_dict(item, f"{path}.field_profiles[{index}]")
        for index, item in enumerate(_tuple(data["field_profiles"], "field_profiles"))
    )
    return TrialStructuralProfile(**data)


def _decomposition_from_dict(value: Any, path: str) -> StructuralFieldDecomposition:
    return StructuralFieldDecomposition(
        **_record(value, path, _field_names(StructuralFieldDecomposition))
    )


def _category_from_dict(value: Any, path: str) -> PairStructuralCategoryCount:
    return PairStructuralCategoryCount(
        **_record(value, path, _field_names(PairStructuralCategoryCount))
    )


def clinicaltrials_gov_harmonization_structure_report_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationStructureReport:
    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "report"},
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_HARMONIZATION_STRUCTURE_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationStructureError(
            "unsupported harmonization structure report schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "report",
        _field_names(ClinicalTrialsGovHarmonizationStructureReport),
    )
    data["trial_profiles"] = tuple(
        _trial_profile_from_dict(item, f"report.trial_profiles[{index}]")
        for index, item in enumerate(_tuple(data["trial_profiles"], "trial_profiles"))
    )
    data["field_decompositions"] = tuple(
        _decomposition_from_dict(item, f"report.field_decompositions[{index}]")
        for index, item in enumerate(
            _tuple(data["field_decompositions"], "field_decompositions")
        )
    )
    data["pair_category_counts"] = tuple(
        _category_from_dict(item, f"report.pair_category_counts[{index}]")
        for index, item in enumerate(
            _tuple(data["pair_category_counts"], "pair_category_counts")
        )
    )
    report = ClinicalTrialsGovHarmonizationStructureReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovHarmonizationStructureError(
            "harmonization structure integrity_sha256 mismatch"
        )
    return report


def clinicaltrials_gov_harmonization_structure_report_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationStructureReport:
    return clinicaltrials_gov_harmonization_structure_report_from_dict(
        _load_json(text, "harmonization structure report")
    )


def clinicaltrials_gov_harmonization_structure_summary(
    report: ClinicalTrialsGovHarmonizationStructureReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationStructureReport):
        raise TypeError("report must be a harmonization structure report")
    categories = {item.code: item.count for item in report.pair_category_counts}
    return {
        "report_id": report.report_id,
        "trial_count": report.trial_count,
        "endpoint_candidate_count": report.endpoint_candidate_count,
        "pair_candidate_count": report.pair_candidate_count,
        "trial_global_saturated_field_count": (
            report.trial_global_saturated_field_count
        ),
        "endpoint_local_present_field_count": (
            report.endpoint_local_present_field_count
        ),
        "trial_global_only_pair_count": categories[TRIAL_GLOBAL_DISAGREEMENT_ONLY],
        "endpoint_local_present_pair_count": categories[
            ENDPOINT_LOCAL_DISAGREEMENT_PRESENT
        ],
        "source_presence_identifiable": report.source_presence_identifiable,
        "integrity_sha256": report.fingerprint,
    }
