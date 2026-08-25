"""Source-disjoint robustness profiles for payload-free harmonization reports."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

from .clinicaltrials_gov_harmonization_diagnostics import (
    ESTIMAND_STRUCTURE_REVIEW_REQUIRED,
    OUTCOME_TYPE_REVIEW_REQUIRED,
    POPULATION_REVIEW_REQUIRED,
    REPORTING_STATUS_REVIEW_REQUIRED,
    SAFETY_WINDOW_REVIEW_REQUIRED,
    SEMANTIC_ENDPOINT_REVIEW_REQUIRED,
    SOURCE_FIELD_COMPLETION_REQUIRED,
    TIME_FRAME_REVIEW_REQUIRED,
    TITLE_IDENTITY_REVIEW_REQUIRED,
    WITHIN_TRIAL_RECONCILIATION_REVIEW_REQUIRED,
    ClinicalTrialsGovHarmonizationDiagnosticReport,
)
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-robustness-spec.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_REPORT_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-harmonization-robustness-report.v1"
)
CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_POLICY_ID = (
    "adds.source-disjoint-harmonization-robustness.v1"
)
MAX_HARMONIZATION_ROBUSTNESS_COHORT_COUNT = 64

SATURATED_ALL = "saturated_all"
ABSENT_ALL = "absent_all"
STABLE_NON_BOUNDARY = "stable_non_boundary"
HETEROGENEOUS = "heterogeneous"

_STABILITY_STATUSES = (
    SATURATED_ALL,
    ABSENT_ALL,
    STABLE_NON_BOUNDARY,
    HETEROGENEOUS,
)
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
_PAIR_FIELD_NAMES = (
    "title",
    "time_frame",
    "outcome_type",
    "reporting_status",
    "parameter_type",
    "dispersion_type",
    "unit_of_measure",
    "population_description_sha256",
    "safety_time_frame",
)
_STRUCTURAL_FIELD_NAMES = (
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
        "The profile is complete only for the exact source-disjoint diagnostic "
        "reports bound by hash in the benchmark spec."
    ),
    (
        "Every rate retains its report-specific numerator and denominator; counts "
        "are not pooled, weighted, averaged, or converted into a difficulty rank."
    ),
    (
        "Stability labels describe mechanical prevalence across the supplied "
        "cohorts and do not establish disease-level or out-of-sample generalization."
    ),
    (
        "Saturation can reflect policy invariants, source missingness, or "
        "trial-global structure and is not evidence of semantic task accuracy."
    ),
    (
        "No endpoint equivalence, clinical comparability, comparative safety, "
        "benefit-risk synthesis, regulatory inference, or treatment choice is made."
    ),
)


class ClinicalTrialsGovHarmonizationRobustnessError(ValueError):
    """Raised when a harmonization robustness profile is invalid."""


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
class HarmonizationRobustnessReportBinding(SerializableRecord):
    cohort_id: str
    diagnostic_report_id: str
    diagnostic_report_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.cohort_id, "cohort_id")
        _require_text(self.diagnostic_report_id, "diagnostic_report_id")
        _require_sha256(self.diagnostic_report_sha256, "diagnostic_report_sha256")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationRobustnessSpec(SerializableRecord):
    benchmark_id: str
    report_bindings: tuple[HarmonizationRobustnessReportBinding, ...]
    policy_id: str = CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.benchmark_id, "benchmark_id")
        bindings = _tuple(self.report_bindings, "report_bindings")
        if any(
            not isinstance(item, HarmonizationRobustnessReportBinding)
            for item in bindings
        ):
            raise TypeError("report_bindings contains an invalid binding")
        if not 2 <= len(bindings) <= MAX_HARMONIZATION_ROBUSTNESS_COHORT_COUNT:
            raise ValueError("report_bindings count is outside the supported bound")
        if bindings != tuple(sorted(bindings, key=lambda item: item.cohort_id)):
            raise ValueError("report_bindings must use canonical cohort_id order")
        if len({item.cohort_id for item in bindings}) != len(bindings):
            raise ValueError("report binding cohort_id values must be unique")
        if len({item.diagnostic_report_id for item in bindings}) != len(bindings):
            raise ValueError("diagnostic report ids must be unique")
        if len({item.diagnostic_report_sha256 for item in bindings}) != len(bindings):
            raise ValueError("diagnostic report hashes must be unique")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_POLICY_ID:
            raise ValueError("unsupported harmonization robustness policy_id")
        object.__setattr__(self, "report_bindings", bindings)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ExactRate(SerializableRecord):
    code: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_non_negative_int(self.numerator, "numerator")
        _require_non_negative_int(self.denominator, "denominator")
        if self.denominator == 0:
            raise ValueError("rate denominator must be positive")
        if self.numerator > self.denominator:
            raise ValueError("rate numerator exceeds denominator")


@dataclass(frozen=True, slots=True)
class HarmonizationTrialSource(SerializableRecord):
    nct_id: str
    source_content_hash_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.nct_id, "nct_id")
        if _NCT_ID.fullmatch(self.nct_id) is None:
            raise ValueError("nct_id must use canonical NCT######## form")
        _require_sha256(
            self.source_content_hash_sha256, "source_content_hash_sha256"
        )


def _rates(
    value: Any,
    field_name: str,
    expected_codes: tuple[str, ...],
    denominator: int,
) -> tuple[ExactRate, ...]:
    values = _tuple(value, field_name)
    if any(not isinstance(item, ExactRate) for item in values):
        raise TypeError(f"{field_name} contains an invalid rate")
    if tuple(item.code for item in values) != expected_codes:
        raise ValueError(f"{field_name} codes were reordered or omitted")
    if any(item.denominator != denominator for item in values):
        raise ValueError(f"{field_name} denominator does not match pair_count")
    return values


@dataclass(frozen=True, slots=True)
class HarmonizationCohortProfile(SerializableRecord):
    cohort_id: str
    diagnostic_report_id: str
    diagnostic_report_sha256: str
    trial_sources: tuple[HarmonizationTrialSource, ...]
    trial_count: int
    endpoint_candidate_count: int
    pair_candidate_count: int
    unique_difficulty_signature_count: int
    review_route_rates: tuple[ExactRate, ...]
    pair_field_missing_rates: tuple[ExactRate, ...]
    structural_disagreement_rates: tuple[ExactRate, ...]

    def __post_init__(self) -> None:
        _require_text(self.cohort_id, "cohort_id")
        _require_text(self.diagnostic_report_id, "diagnostic_report_id")
        _require_sha256(self.diagnostic_report_sha256, "diagnostic_report_sha256")
        trial_sources = _tuple(self.trial_sources, "trial_sources")
        if any(
            not isinstance(item, HarmonizationTrialSource)
            for item in trial_sources
        ):
            raise TypeError("trial_sources contains an invalid binding")
        if trial_sources != tuple(
            sorted(trial_sources, key=lambda item: item.nct_id)
        ):
            raise ValueError("trial_sources must use canonical nct_id order")
        if len({item.nct_id for item in trial_sources}) != len(trial_sources):
            raise ValueError("trial source nct_id values must be unique")
        if len(
            {item.source_content_hash_sha256 for item in trial_sources}
        ) != len(trial_sources):
            raise ValueError("trial source content hashes must be unique")
        for field_name in (
            "trial_count",
            "endpoint_candidate_count",
            "pair_candidate_count",
            "unique_difficulty_signature_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.trial_count != len(trial_sources):
            raise ValueError("trial_count does not match trial_sources")
        if self.pair_candidate_count == 0:
            raise ValueError("robustness profiles require a positive pair count")
        object.__setattr__(self, "trial_sources", trial_sources)
        object.__setattr__(
            self,
            "review_route_rates",
            _rates(
                self.review_route_rates,
                "review_route_rates",
                _ROUTE_CODES,
                self.pair_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "pair_field_missing_rates",
            _rates(
                self.pair_field_missing_rates,
                "pair_field_missing_rates",
                _PAIR_FIELD_NAMES,
                self.pair_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "structural_disagreement_rates",
            _rates(
                self.structural_disagreement_rates,
                "structural_disagreement_rates",
                _STRUCTURAL_FIELD_NAMES,
                self.pair_candidate_count,
            ),
        )


@dataclass(frozen=True, slots=True)
class CrossCohortRateStability(SerializableRecord):
    code: str
    status: str

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        if self.status not in _STABILITY_STATUSES:
            raise ValueError("unsupported cross-cohort stability status")


def _stabilities(
    value: Any,
    field_name: str,
    expected_codes: tuple[str, ...],
) -> tuple[CrossCohortRateStability, ...]:
    values = _tuple(value, field_name)
    if any(not isinstance(item, CrossCohortRateStability) for item in values):
        raise TypeError(f"{field_name} contains an invalid stability record")
    if tuple(item.code for item in values) != expected_codes:
        raise ValueError(f"{field_name} codes were reordered or omitted")
    return values


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovHarmonizationRobustnessReport(SerializableRecord):
    benchmark_id: str
    policy_id: str
    spec_sha256: str
    cohort_profiles: tuple[HarmonizationCohortProfile, ...]
    review_route_stability: tuple[CrossCohortRateStability, ...]
    pair_field_missing_stability: tuple[CrossCohortRateStability, ...]
    structural_disagreement_stability: tuple[CrossCohortRateStability, ...]
    cohort_count: int
    source_disjoint: bool
    payload_free_aggregate_only: bool
    count_pooling_performed: bool
    cohort_weighting_performed: bool
    difficulty_ranking_performed: bool
    disease_generalization_inferred: bool
    semantic_accuracy_inferred: bool
    clinical_comparability_inferred: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.benchmark_id, "benchmark_id")
        if self.policy_id != CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_POLICY_ID:
            raise ValueError("unsupported harmonization robustness policy_id")
        _require_sha256(self.spec_sha256, "spec_sha256")
        profiles = _tuple(self.cohort_profiles, "cohort_profiles")
        if any(not isinstance(item, HarmonizationCohortProfile) for item in profiles):
            raise TypeError("cohort_profiles contains an invalid profile")
        if profiles != tuple(sorted(profiles, key=lambda item: item.cohort_id)):
            raise ValueError("cohort_profiles must use canonical cohort_id order")
        if len({item.cohort_id for item in profiles}) != len(profiles):
            raise ValueError("cohort profile ids must be unique")
        if len({item.diagnostic_report_id for item in profiles}) != len(profiles):
            raise ValueError("cohort diagnostic report ids must be unique")
        if len({item.diagnostic_report_sha256 for item in profiles}) != len(
            profiles
        ):
            raise ValueError("cohort diagnostic report hashes must be unique")
        if self.cohort_count != len(profiles) or not (
            2 <= self.cohort_count <= MAX_HARMONIZATION_ROBUSTNESS_COHORT_COUNT
        ):
            raise ValueError("cohort_count does not match the supported profiles")
        all_trial_sources = [
            source for item in profiles for source in item.trial_sources
        ]
        all_nct_ids = [item.nct_id for item in all_trial_sources]
        if len(all_nct_ids) != len(set(all_nct_ids)):
            raise ValueError("cohort profiles are not source-disjoint by NCT id")
        all_source_hashes = [
            item.source_content_hash_sha256 for item in all_trial_sources
        ]
        if len(all_source_hashes) != len(set(all_source_hashes)):
            raise ValueError(
                "cohort profiles are not source-disjoint by content hash"
            )
        object.__setattr__(self, "cohort_profiles", profiles)
        object.__setattr__(
            self,
            "review_route_stability",
            _stabilities(
                self.review_route_stability,
                "review_route_stability",
                _ROUTE_CODES,
            ),
        )
        object.__setattr__(
            self,
            "pair_field_missing_stability",
            _stabilities(
                self.pair_field_missing_stability,
                "pair_field_missing_stability",
                _PAIR_FIELD_NAMES,
            ),
        )
        object.__setattr__(
            self,
            "structural_disagreement_stability",
            _stabilities(
                self.structural_disagreement_stability,
                "structural_disagreement_stability",
                _STRUCTURAL_FIELD_NAMES,
            ),
        )
        expected_stabilities = (
            (
                "review_route_stability",
                _cross_cohort_stability(
                    profiles, "review_route_rates", _ROUTE_CODES
                ),
            ),
            (
                "pair_field_missing_stability",
                _cross_cohort_stability(
                    profiles, "pair_field_missing_rates", _PAIR_FIELD_NAMES
                ),
            ),
            (
                "structural_disagreement_stability",
                _cross_cohort_stability(
                    profiles,
                    "structural_disagreement_rates",
                    _STRUCTURAL_FIELD_NAMES,
                ),
            ),
        )
        for field_name, expected in expected_stabilities:
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match cohort rates")
        true_fields = ("source_disjoint", "payload_free_aggregate_only")
        false_fields = (
            "count_pooling_performed",
            "cohort_weighting_performed",
            "difficulty_ranking_performed",
            "disease_generalization_inferred",
            "semantic_accuracy_inferred",
            "clinical_comparability_inferred",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, field_name) for field_name in true_fields):
            raise ValueError("required source-disjoint or aggregate flag is false")
        if any(getattr(self, field_name) for field_name in false_fields):
            raise ValueError("a forbidden pooling, ranking, or inference was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("robustness limitations were rebound")
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def classify_harmonization_rate_stability(rates: Sequence[ExactRate]) -> str:
    """Classify exact cohort rates without floating-point conversion."""

    rates = tuple(rates)
    if len(rates) < 2:
        raise ValueError("cross-cohort rate classification requires two rates")
    if any(not isinstance(item, ExactRate) for item in rates):
        raise TypeError("rates contains an invalid exact rate")
    if len({item.code for item in rates}) != 1:
        raise ValueError("cross-cohort rates must use one diagnostic code")
    if all(item.numerator == item.denominator for item in rates):
        return SATURATED_ALL
    if all(item.numerator == 0 for item in rates):
        return ABSENT_ALL
    first = rates[0]
    if all(
        item.numerator * first.denominator
        == first.numerator * item.denominator
        for item in rates[1:]
    ):
        return STABLE_NON_BOUNDARY
    return HETEROGENEOUS


def _cross_cohort_stability(
    profiles: Sequence[HarmonizationCohortProfile],
    field_name: str,
    codes: tuple[str, ...],
) -> tuple[CrossCohortRateStability, ...]:
    return tuple(
        CrossCohortRateStability(
            code=code,
            status=classify_harmonization_rate_stability(
                [
                    next(
                        item
                        for item in getattr(profile, field_name)
                        if item.code == code
                    )
                    for profile in profiles
                ]
            ),
        )
        for code in codes
    )


def _profile(
    binding: HarmonizationRobustnessReportBinding,
    report: ClinicalTrialsGovHarmonizationDiagnosticReport,
) -> HarmonizationCohortProfile:
    return HarmonizationCohortProfile(
        cohort_id=binding.cohort_id,
        diagnostic_report_id=report.report_id,
        diagnostic_report_sha256=report.fingerprint,
        trial_sources=tuple(
            HarmonizationTrialSource(
                nct_id=item.nct_id,
                source_content_hash_sha256=item.source_content_hash_sha256,
            )
            for item in report.trial_diagnostics
        ),
        trial_count=report.trial_count,
        endpoint_candidate_count=report.endpoint_candidate_count,
        pair_candidate_count=report.pair_candidate_count,
        unique_difficulty_signature_count=report.unique_difficulty_signature_count,
        review_route_rates=tuple(
            ExactRate(
                code=item.code,
                numerator=item.count,
                denominator=report.pair_candidate_count,
            )
            for item in report.review_route_counts
        ),
        pair_field_missing_rates=tuple(
            ExactRate(
                code=item.field_name,
                numerator=item.missing_pair_count,
                denominator=report.pair_candidate_count,
            )
            for item in report.pair_field_diagnostics
        ),
        structural_disagreement_rates=tuple(
            ExactRate(
                code=item.field_name,
                numerator=item.disagreement_count,
                denominator=report.pair_candidate_count,
            )
            for item in report.structural_diagnostics
        ),
    )


def compile_clinicaltrials_gov_harmonization_robustness(
    spec: ClinicalTrialsGovHarmonizationRobustnessSpec,
    reports: Sequence[ClinicalTrialsGovHarmonizationDiagnosticReport],
) -> ClinicalTrialsGovHarmonizationRobustnessReport:
    """Compile exact per-cohort rates without pooling their denominators."""

    if not isinstance(spec, ClinicalTrialsGovHarmonizationRobustnessSpec):
        raise TypeError("spec must be a harmonization robustness spec")
    reports = tuple(reports)
    if any(
        not isinstance(item, ClinicalTrialsGovHarmonizationDiagnosticReport)
        for item in reports
    ):
        raise TypeError("reports contains an invalid diagnostic report")
    reports_by_id = {item.report_id: item for item in reports}
    if len(reports_by_id) != len(reports):
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            "diagnostic report ids must be unique"
        )
    if set(reports_by_id) != {
        item.diagnostic_report_id for item in spec.report_bindings
    }:
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            "diagnostic reports do not exactly match spec bindings"
        )
    profiles = []
    for binding in spec.report_bindings:
        report = reports_by_id[binding.diagnostic_report_id]
        if report.fingerprint != binding.diagnostic_report_sha256:
            raise ClinicalTrialsGovHarmonizationRobustnessError(
                f"diagnostic report hash mismatch for {binding.cohort_id}"
            )
        profiles.append(_profile(binding, report))
    typed_profiles = tuple(profiles)
    return ClinicalTrialsGovHarmonizationRobustnessReport(
        benchmark_id=spec.benchmark_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        cohort_profiles=typed_profiles,
        review_route_stability=_cross_cohort_stability(
            typed_profiles, "review_route_rates", _ROUTE_CODES
        ),
        pair_field_missing_stability=_cross_cohort_stability(
            typed_profiles, "pair_field_missing_rates", _PAIR_FIELD_NAMES
        ),
        structural_disagreement_stability=_cross_cohort_stability(
            typed_profiles,
            "structural_disagreement_rates",
            _STRUCTURAL_FIELD_NAMES,
        ),
        cohort_count=len(typed_profiles),
        source_disjoint=True,
        payload_free_aggregate_only=True,
        count_pooling_performed=False,
        cohort_weighting_performed=False,
        difficulty_ranking_performed=False,
        disease_generalization_inferred=False,
        semantic_accuracy_inferred=False,
        clinical_comparability_inferred=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_harmonization_robustness(
    spec: ClinicalTrialsGovHarmonizationRobustnessSpec,
    reports: Sequence[ClinicalTrialsGovHarmonizationDiagnosticReport],
    benchmark: ClinicalTrialsGovHarmonizationRobustnessReport,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_harmonization_robustness(spec, reports)
    except (ClinicalTrialsGovHarmonizationRobustnessError, TypeError, ValueError):
        return ("clinicaltrials_gov_harmonization_robustness_recompile_failed",)
    if rebuilt != benchmark:
        return ("clinicaltrials_gov_harmonization_robustness_report_mismatch",)
    return ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovHarmonizationRobustnessError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovHarmonizationRobustnessError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovHarmonizationRobustnessError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            f"{label} must be an object"
        )
    return dict(value)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            f"{path} must be an object"
        )
    data = dict(value)
    if set(data) != expected_fields:
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return data


def clinicaltrials_gov_harmonization_robustness_spec_to_dict(
    spec: ClinicalTrialsGovHarmonizationRobustnessSpec,
) -> dict[str, Any]:
    if not isinstance(spec, ClinicalTrialsGovHarmonizationRobustnessSpec):
        raise TypeError("spec must be a harmonization robustness spec")
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_SPEC_SCHEMA_VERSION
        ),
        **value,
    }


def _binding_from_dict(
    value: Any, path: str
) -> HarmonizationRobustnessReportBinding:
    return HarmonizationRobustnessReportBinding(
        **_record(value, path, _field_names(HarmonizationRobustnessReportBinding))
    )


def clinicaltrials_gov_harmonization_robustness_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationRobustnessSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovHarmonizationRobustnessSpec),
        },
    )
    if (
        data.pop("schema_version")
        != CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            "unsupported harmonization robustness spec schema_version"
        )
    data["report_bindings"] = tuple(
        _binding_from_dict(item, f"spec.report_bindings[{index}]")
        for index, item in enumerate(_tuple(data["report_bindings"], "report_bindings"))
    )
    return ClinicalTrialsGovHarmonizationRobustnessSpec(**data)


def clinicaltrials_gov_harmonization_robustness_spec_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationRobustnessSpec:
    return clinicaltrials_gov_harmonization_robustness_spec_from_dict(
        _load_json(text, "harmonization robustness spec")
    )


def clinicaltrials_gov_harmonization_robustness_report_envelope(
    report: ClinicalTrialsGovHarmonizationRobustnessReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationRobustnessReport):
        raise TypeError("report must be a harmonization robustness report")
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def _rate_from_dict(value: Any, path: str) -> ExactRate:
    return ExactRate(**_record(value, path, _field_names(ExactRate)))


def _profile_from_dict(value: Any, path: str) -> HarmonizationCohortProfile:
    data = _record(value, path, _field_names(HarmonizationCohortProfile))
    data["trial_sources"] = tuple(
        HarmonizationTrialSource(
            **_record(
                item,
                f"{path}.trial_sources[{index}]",
                _field_names(HarmonizationTrialSource),
            )
        )
        for index, item in enumerate(_tuple(data["trial_sources"], "trial_sources"))
    )
    for field_name in (
        "review_route_rates",
        "pair_field_missing_rates",
        "structural_disagreement_rates",
    ):
        data[field_name] = tuple(
            _rate_from_dict(item, f"{path}.{field_name}[{index}]")
            for index, item in enumerate(_tuple(data[field_name], field_name))
        )
    return HarmonizationCohortProfile(**data)


def _stability_from_dict(value: Any, path: str) -> CrossCohortRateStability:
    return CrossCohortRateStability(
        **_record(value, path, _field_names(CrossCohortRateStability))
    )


def clinicaltrials_gov_harmonization_robustness_report_from_dict(
    value: Any,
) -> ClinicalTrialsGovHarmonizationRobustnessReport:
    envelope = _record(
        value,
        "envelope",
        {"schema_version", "integrity_sha256", "report"},
    )
    if (
        envelope["schema_version"]
        != CLINICALTRIALS_GOV_HARMONIZATION_ROBUSTNESS_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            "unsupported harmonization robustness report schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "report",
        _field_names(ClinicalTrialsGovHarmonizationRobustnessReport),
    )
    data["cohort_profiles"] = tuple(
        _profile_from_dict(item, f"report.cohort_profiles[{index}]")
        for index, item in enumerate(_tuple(data["cohort_profiles"], "cohort_profiles"))
    )
    for field_name in (
        "review_route_stability",
        "pair_field_missing_stability",
        "structural_disagreement_stability",
    ):
        data[field_name] = tuple(
            _stability_from_dict(item, f"report.{field_name}[{index}]")
            for index, item in enumerate(_tuple(data[field_name], field_name))
        )
    report = ClinicalTrialsGovHarmonizationRobustnessReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovHarmonizationRobustnessError(
            "harmonization robustness integrity_sha256 mismatch"
        )
    return report


def clinicaltrials_gov_harmonization_robustness_report_from_json(
    text: str,
) -> ClinicalTrialsGovHarmonizationRobustnessReport:
    return clinicaltrials_gov_harmonization_robustness_report_from_dict(
        _load_json(text, "harmonization robustness report")
    )


def clinicaltrials_gov_harmonization_robustness_summary(
    report: ClinicalTrialsGovHarmonizationRobustnessReport,
) -> dict[str, Any]:
    if not isinstance(report, ClinicalTrialsGovHarmonizationRobustnessReport):
        raise TypeError("report must be a harmonization robustness report")
    route_statuses = {item.code: item.status for item in report.review_route_stability}
    status_counts = Counter(route_statuses.values())
    return {
        "benchmark_id": report.benchmark_id,
        "cohort_count": report.cohort_count,
        "source_disjoint": report.source_disjoint,
        "saturated_review_route_count": status_counts[SATURATED_ALL],
        "absent_review_route_count": status_counts[ABSENT_ALL],
        "heterogeneous_review_route_count": status_counts[HETEROGENEOUS],
        "semantic_review_stability": route_statuses[
            SEMANTIC_ENDPOINT_REVIEW_REQUIRED
        ],
        "integrity_sha256": report.fingerprint,
    }
