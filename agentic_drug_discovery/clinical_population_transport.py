"""Reviewed, provenance-bound clinical population stratification diagnostics."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import (
    BenefitRiskSynthesisRecord,
    SerializableRecord,
    TrialDesignRecord,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_POPULATION_TRANSPORT_SPEC_SCHEMA_VERSION = (
    "adds.clinical-population-transport-spec.v1"
)
CLINICAL_POPULATION_TRANSPORT_REPORT_SCHEMA_VERSION = (
    "adds.clinical-population-transport-report.v1"
)
CLINICAL_POPULATION_TRANSPORT_METHOD_ID = (
    "adds.descriptive-population-stratified-transport-diagnostic.v1"
)
CLINICAL_POPULATION_TRANSPORT_ANALYSIS_MODE = "descriptive_population_stratification"
CLINICAL_POPULATION_TRANSPORT_STATUS = (
    "descriptive_stratification_complete_transport_not_estimable"
)

_SOURCE_DOCUMENT_FORMAT = "clinicaltrials.gov-study-v2"
_CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_REQUIRED_LIMITATIONS = (
    (
        "Population strata are reviewer-declared and hash-bound to exact registry "
        "fields; no free-text similarity model or automatic eligibility inference is used."
    ),
    (
        "Trial-level effects and serious-event aggregates are displayed side by side "
        "without pooling or a cross-stratum effect contrast."
    ),
    (
        "Distinct source strata are not treated as homogeneous, exchangeable, or "
        "representative of an undeclared target population."
    ),
    (
        "Aggregate registry results do not provide individual-level covariates, overlap, "
        "positivity, conditional exchangeability, or risk-of-bias adjustment."
    ),
    (
        "Completing this diagnostic does not establish efficacy, comparative safety, "
        "clinical acceptability, transportability, or a treatment recommendation."
    ),
    (
        "Independent external scientific review is not implied by project-internal approval."
    ),
)


class ClinicalPopulationTransportError(ValueError):
    """Raised when population transport diagnostics cannot bind safely."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _tuple(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClinicalPopulationTransportError(f"{path} must be an array")
    return tuple(value)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalPopulationTransportError(f"{path} must be an object")
    return dict(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClinicalPopulationTransportError(f"{path} must be non-empty text")
    return value.strip()


def _exact_fields(data: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(data) != expected:
        raise ClinicalPopulationTransportError(
            f"{path} must contain exactly {sorted(expected)}"
        )


def _datetime(value: Any, path: str) -> datetime:
    text = _text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClinicalPopulationTransportError(f"{path} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClinicalPopulationTransportError(f"{path} must be timezone-aware")
    return parsed


def _load_source_document(payload: bytes, path: str) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise ClinicalPopulationTransportError(f"{path} must be bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ClinicalPopulationTransportError(
                    f"{path} contains duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClinicalPopulationTransportError(
            f"{path} is not valid UTF-8 JSON"
        ) from exc
    return _mapping(value, path)


def _json_pointer(document: Any, pointer: str, path: str) -> Any:
    if not pointer.startswith("/"):
        raise ClinicalPopulationTransportError(
            f"{path} must be an absolute JSON pointer"
        )
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise ClinicalPopulationTransportError(
                    f"{path} does not resolve in the source document"
                )
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                index = int(token)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise ClinicalPopulationTransportError(
                    f"{path} does not resolve in the source document"
                ) from exc
        else:
            raise ClinicalPopulationTransportError(
                f"{path} does not resolve in the source document"
            )
    return current


@dataclass(frozen=True, slots=True)
class ClinicalPopulationSourceCitation(SerializableRecord):
    """Exact registry document and field reviewed for one stratum declaration."""

    source_document_format: str
    source_content_sha256: str
    source_field_pointer: str
    source_field_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_document_format",
            "source_field_pointer",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        _require_sha256(self.source_field_sha256, "source_field_sha256")
        if self.source_document_format != _SOURCE_DOCUMENT_FORMAT:
            raise ValueError("source_document_format is unsupported")
        if not self.source_field_pointer.startswith("/"):
            raise ValueError("source_field_pointer must be an absolute JSON pointer")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationStratumBinding(SerializableRecord):
    """Reviewer declaration for one exact study population and source field."""

    trial_id: str
    design_id: str
    endpoint_id: str
    population_id: str
    stratum_id: str
    stratum_label: str
    population_context: str
    citation: ClinicalPopulationSourceCitation

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "design_id",
            "endpoint_id",
            "population_id",
            "stratum_id",
            "stratum_label",
            "population_context",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.citation, ClinicalPopulationSourceCitation, "citation")
        if _CANONICAL_ID.fullmatch(self.stratum_id) is None:
            raise ValueError("stratum_id must be a canonical snake-case id")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationTransportReview(SerializableRecord):
    """Approval scope for descriptive stratification, not an external validation."""

    status: str
    reviewer_id: str
    reviewer_role: str
    reviewed_at: datetime
    independent_external_review: bool = False

    def __post_init__(self) -> None:
        for field_name in ("status", "reviewer_id", "reviewer_role"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.reviewed_at, datetime, "reviewed_at")
        _require_bool(self.independent_external_review, "independent_external_review")
        if self.status != "approved_for_descriptive_stratification":
            raise ValueError("review status is unsupported")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        if self.independent_external_review:
            raise ValueError("v1 cannot attest independent external review")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationTransportSpec(SerializableRecord):
    """Preregistered, reviewer-declared population stratification contract."""

    analysis_id: str
    synthesis_id: str
    stratification_axis_id: str
    stratification_axis_label: str
    bindings: tuple[ClinicalPopulationStratumBinding, ...]
    review: ClinicalPopulationTransportReview
    analysis_mode: str = CLINICAL_POPULATION_TRANSPORT_ANALYSIS_MODE
    target_population_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "synthesis_id",
            "stratification_axis_id",
            "stratification_axis_label",
            "analysis_mode",
        ):
            _require_text(getattr(self, field_name), field_name)
        if _CANONICAL_ID.fullmatch(self.stratification_axis_id) is None:
            raise ValueError("stratification_axis_id must be canonical snake case")
        if self.analysis_mode != CLINICAL_POPULATION_TRANSPORT_ANALYSIS_MODE:
            raise ValueError("analysis_mode is unsupported")
        if self.target_population_id is not None:
            _require_text(self.target_population_id, "target_population_id")
            raise ValueError("v1 requires target_population_id to remain null")
        bindings = tuple(self.bindings)
        object.__setattr__(self, "bindings", bindings)
        if len(bindings) < 2:
            raise ValueError("bindings must contain at least two studies")
        for item in bindings:
            _require_instance(item, ClinicalPopulationStratumBinding, "bindings item")
        for field_name, values in (
            ("trial ids", tuple(item.trial_id for item in bindings)),
            ("design ids", tuple(item.design_id for item in bindings)),
            ("endpoint ids", tuple(item.endpoint_id for item in bindings)),
            ("population ids", tuple(item.population_id for item in bindings)),
            (
                "source content hashes",
                tuple(item.citation.source_content_sha256 for item in bindings),
            ),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"bindings must use unique {field_name}")
        _require_instance(self.review, ClinicalPopulationTransportReview, "review")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationStratumRecord(SerializableRecord):
    """One non-pooled trial cell with exact analysis-population provenance."""

    trial_id: str
    study_record_id: str
    design_id: str
    endpoint_id: str
    population_id: str
    population_description_sha256: str
    stratum_id: str
    stratum_label: str
    population_context: str
    source_content_sha256: str
    source_field_pointer: str
    source_field_sha256: str
    effect_estimate: float
    confidence_interval_percent: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    measurement_unit: str
    endpoint_time_frame: str
    safety_time_frame: str
    candidate_serious_num_affected: int
    candidate_serious_num_at_risk: int
    comparator_serious_num_affected: int
    comparator_serious_num_at_risk: int
    serious_event_risk_difference: float
    benefit_direction: str
    safety_direction: str

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "study_record_id",
            "design_id",
            "endpoint_id",
            "population_id",
            "stratum_id",
            "stratum_label",
            "population_context",
            "source_field_pointer",
            "measurement_unit",
            "endpoint_time_frame",
            "safety_time_frame",
            "benefit_direction",
            "safety_direction",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "population_description_sha256",
            "source_content_sha256",
            "source_field_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if _CANONICAL_ID.fullmatch(self.stratum_id) is None:
            raise ValueError("stratum_id must be a canonical snake-case id")
        if not self.source_field_pointer.startswith("/"):
            raise ValueError("source_field_pointer must be an absolute JSON pointer")
        for field_name in (
            "effect_estimate",
            "confidence_interval_percent",
            "confidence_interval_lower",
            "confidence_interval_upper",
            "serious_event_risk_difference",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
        if not 0 < self.confidence_interval_percent <= 100:
            raise ValueError("confidence_interval_percent must be in (0, 100]")
        if not (
            self.confidence_interval_lower
            <= self.effect_estimate
            <= self.confidence_interval_upper
        ):
            raise ValueError("effect estimate must lie within its confidence interval")
        for field_name in (
            "candidate_serious_num_affected",
            "candidate_serious_num_at_risk",
            "comparator_serious_num_affected",
            "comparator_serious_num_at_risk",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if (
            self.candidate_serious_num_at_risk < 1
            or self.comparator_serious_num_at_risk < 1
        ):
            raise ValueError("serious-event numbers at risk must be positive")
        if (
            self.candidate_serious_num_affected > self.candidate_serious_num_at_risk
            or self.comparator_serious_num_affected
            > self.comparator_serious_num_at_risk
        ):
            raise ValueError("serious-event affected count exceeds number at risk")
        expected_risk_difference = (
            self.candidate_serious_num_affected / self.candidate_serious_num_at_risk
            - self.comparator_serious_num_affected / self.comparator_serious_num_at_risk
        )
        if not math.isclose(
            self.serious_event_risk_difference,
            expected_risk_difference,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("serious_event_risk_difference does not match counts")
        if self.benefit_direction not in {"benefit", "harm", "null_or_uncertain"}:
            raise ValueError("benefit_direction is unsupported")
        if self.safety_direction not in {
            "lower_observed_serious_event_risk",
            "higher_observed_serious_event_risk",
            "equal_observed_serious_event_risk",
        }:
            raise ValueError("safety_direction is unsupported")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationStratumSupport(SerializableRecord):
    stratum_id: str
    trial_count: int

    def __post_init__(self) -> None:
        _require_text(self.stratum_id, "stratum_id")
        if not isinstance(self.trial_count, int) or isinstance(self.trial_count, bool):
            raise TypeError("trial_count must be an integer")
        if self.trial_count < 1:
            raise ValueError("trial_count must be positive")


@dataclass(frozen=True, slots=True)
class ClinicalPopulationTransportReport(SerializableRecord):
    """Fail-closed result separating completed stratification from transport inference."""

    analysis_id: str
    spec_sha256: str
    method_id: str
    synthesis_id: str
    synthesis_sha256: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    endpoint_mapping_id: str
    endpoint_family: str
    effect_measure: str
    safety_measure: str
    stratification_axis_id: str
    stratification_axis_label: str
    analysis_mode: str
    review: ClinicalPopulationTransportReview
    strata: tuple[ClinicalPopulationStratumRecord, ...]
    stratum_support: tuple[ClinicalPopulationStratumSupport, ...]
    status: str
    transportability_blockers: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    target_population_defined: bool = False
    population_homogeneity_inferred: bool = False
    population_exchangeability_inferred: bool = False
    pooling_performed: bool = False
    cross_stratum_effect_contrast_computed: bool = False
    transport_effect_estimated: bool = False
    risk_of_bias_assessed: bool = False
    independent_external_review_completed: bool = False
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "method_id",
            "synthesis_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "safety_measure",
            "stratification_axis_id",
            "stratification_axis_label",
            "analysis_mode",
            "status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.spec_sha256, "spec_sha256")
        _require_sha256(self.synthesis_sha256, "synthesis_sha256")
        if self.method_id != CLINICAL_POPULATION_TRANSPORT_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.analysis_mode != CLINICAL_POPULATION_TRANSPORT_ANALYSIS_MODE:
            raise ValueError("analysis_mode is unsupported")
        if self.status != CLINICAL_POPULATION_TRANSPORT_STATUS:
            raise ValueError("status is unsupported")
        _require_instance(self.review, ClinicalPopulationTransportReview, "review")
        strata = tuple(self.strata)
        support = tuple(self.stratum_support)
        blockers = tuple(self.transportability_blockers)
        source_evidence_ids = tuple(self.source_evidence_ids)
        source_content_hashes = tuple(self.source_content_hashes)
        limitations = tuple(self.limitations)
        object.__setattr__(self, "strata", strata)
        object.__setattr__(self, "stratum_support", support)
        object.__setattr__(self, "transportability_blockers", blockers)
        object.__setattr__(self, "source_evidence_ids", source_evidence_ids)
        object.__setattr__(self, "source_content_hashes", source_content_hashes)
        object.__setattr__(self, "limitations", limitations)
        if len(strata) < 2:
            raise ValueError("strata must contain at least two trial records")
        for item in strata:
            _require_instance(item, ClinicalPopulationStratumRecord, "strata item")
        for item in support:
            _require_instance(item, ClinicalPopulationStratumSupport, "support item")
        if tuple(item.stratum_id for item in support) != tuple(
            sorted({item.stratum_id for item in strata})
        ):
            raise ValueError(
                "stratum_support must use canonical observed-stratum order"
            )
        expected_support = {
            stratum_id: sum(item.stratum_id == stratum_id for item in strata)
            for stratum_id in {item.stratum_id for item in strata}
        }
        if any(
            expected_support[item.stratum_id] != item.trial_count for item in support
        ):
            raise ValueError("stratum_support does not match trial records")
        for label, values in (
            ("trial ids", tuple(item.trial_id for item in strata)),
            ("study record ids", tuple(item.study_record_id for item in strata)),
            ("design ids", tuple(item.design_id for item in strata)),
            ("endpoint ids", tuple(item.endpoint_id for item in strata)),
            ("population ids", tuple(item.population_id for item in strata)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"strata must use unique {label}")
        if not blockers:
            raise ValueError("transportability_blockers must not be empty")
        if (
            not source_evidence_ids
            or tuple(sorted(set(source_evidence_ids))) != source_evidence_ids
        ):
            raise ValueError("source_evidence_ids must use canonical unique order")
        if tuple(sorted(set(source_content_hashes))) != source_content_hashes:
            raise ValueError("source_content_hashes must use canonical unique order")
        for digest in source_content_hashes:
            _require_sha256(digest, "source_content_hashes item")
        if source_content_hashes != tuple(
            sorted({item.source_content_sha256 for item in strata})
        ):
            raise ValueError(
                "source_content_hashes must equal the stratum source union"
            )
        required_blockers = {
            "target_population_not_declared",
            "aggregate_registry_results_only",
            "individual_level_covariates_unavailable",
            "transport_model_not_preregistered",
            "risk_of_bias_not_assessed",
        }
        if len({item.stratum_id for item in strata}) > 1:
            required_blockers.add("distinct_reviewed_population_strata")
        if any(item.trial_count < 2 for item in support):
            required_blockers.add("no_within_stratum_replication")
        if not required_blockers.issubset(blockers):
            raise ValueError("report is missing required transportability blockers")
        for field_name in (
            "target_population_defined",
            "population_homogeneity_inferred",
            "population_exchangeability_inferred",
            "pooling_performed",
            "cross_stratum_effect_contrast_computed",
            "transport_effect_estimated",
            "risk_of_bias_assessed",
            "independent_external_review_completed",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false in v1")
        if self.independent_external_review_completed != (
            self.review.independent_external_review
        ):
            raise ValueError("report external-review status conflicts with review")
        if not set(_REQUIRED_LIMITATIONS).issubset(limitations):
            raise ValueError("report is missing required limitations")


def clinical_population_transport_spec_to_dict(
    spec: ClinicalPopulationTransportSpec,
) -> dict[str, Any]:
    _require_instance(spec, ClinicalPopulationTransportSpec, "spec")
    value = to_primitive(spec)
    if not isinstance(value, dict):
        raise TypeError("serialized population transport spec must be an object")
    return {
        "schema_version": CLINICAL_POPULATION_TRANSPORT_SPEC_SCHEMA_VERSION,
        **value,
    }


def clinical_population_transport_spec_from_dict(
    value: Any,
    path: str = "clinical_population_transport_spec",
) -> ClinicalPopulationTransportSpec:
    data = _mapping(value, path)
    expected = {
        "schema_version",
        "analysis_id",
        "synthesis_id",
        "stratification_axis_id",
        "stratification_axis_label",
        "bindings",
        "review",
        "analysis_mode",
        "target_population_id",
    }
    _exact_fields(data, expected, path)
    if data["schema_version"] != CLINICAL_POPULATION_TRANSPORT_SPEC_SCHEMA_VERSION:
        raise ClinicalPopulationTransportError(f"{path}.schema_version is unsupported")
    review = _parse_review(data["review"], f"{path}.review")
    bindings: list[ClinicalPopulationStratumBinding] = []
    for index, raw in enumerate(_tuple(data["bindings"], f"{path}.bindings")):
        item_path = f"{path}.bindings[{index}]"
        item = _mapping(raw, item_path)
        _exact_fields(
            item,
            {
                "trial_id",
                "design_id",
                "endpoint_id",
                "population_id",
                "stratum_id",
                "stratum_label",
                "population_context",
                "citation",
            },
            item_path,
        )
        citation_path = f"{item_path}.citation"
        citation = _mapping(item["citation"], citation_path)
        _exact_fields(
            citation,
            {
                "source_document_format",
                "source_content_sha256",
                "source_field_pointer",
                "source_field_sha256",
            },
            citation_path,
        )
        bindings.append(
            ClinicalPopulationStratumBinding(
                trial_id=_text(item["trial_id"], f"{item_path}.trial_id"),
                design_id=_text(item["design_id"], f"{item_path}.design_id"),
                endpoint_id=_text(item["endpoint_id"], f"{item_path}.endpoint_id"),
                population_id=_text(
                    item["population_id"], f"{item_path}.population_id"
                ),
                stratum_id=_text(item["stratum_id"], f"{item_path}.stratum_id"),
                stratum_label=_text(
                    item["stratum_label"], f"{item_path}.stratum_label"
                ),
                population_context=_text(
                    item["population_context"], f"{item_path}.population_context"
                ),
                citation=ClinicalPopulationSourceCitation(
                    source_document_format=_text(
                        citation["source_document_format"],
                        f"{citation_path}.source_document_format",
                    ),
                    source_content_sha256=_text(
                        citation["source_content_sha256"],
                        f"{citation_path}.source_content_sha256",
                    ),
                    source_field_pointer=_text(
                        citation["source_field_pointer"],
                        f"{citation_path}.source_field_pointer",
                    ),
                    source_field_sha256=_text(
                        citation["source_field_sha256"],
                        f"{citation_path}.source_field_sha256",
                    ),
                ),
            )
        )
    target = data["target_population_id"]
    if target is not None:
        target = _text(target, f"{path}.target_population_id")
    return ClinicalPopulationTransportSpec(
        analysis_id=_text(data["analysis_id"], f"{path}.analysis_id"),
        synthesis_id=_text(data["synthesis_id"], f"{path}.synthesis_id"),
        stratification_axis_id=_text(
            data["stratification_axis_id"], f"{path}.stratification_axis_id"
        ),
        stratification_axis_label=_text(
            data["stratification_axis_label"], f"{path}.stratification_axis_label"
        ),
        bindings=tuple(bindings),
        review=review,
        analysis_mode=_text(data["analysis_mode"], f"{path}.analysis_mode"),
        target_population_id=target,
    )


def clinical_population_transport_spec_from_json(
    payload: str | bytes,
) -> ClinicalPopulationTransportSpec:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordParseError("population transport spec is not valid JSON") from exc
    return clinical_population_transport_spec_from_dict(value)


def clinical_population_transport_spec_integrity_sha256(
    spec: ClinicalPopulationTransportSpec,
) -> str:
    _require_instance(spec, ClinicalPopulationTransportSpec, "spec")
    return _sha256(spec)


def _parse_review(value: Any, path: str) -> ClinicalPopulationTransportReview:
    data = _mapping(value, path)
    _exact_fields(
        data,
        {
            "status",
            "reviewer_id",
            "reviewer_role",
            "reviewed_at",
            "independent_external_review",
        },
        path,
    )
    independent = data["independent_external_review"]
    _require_bool(independent, f"{path}.independent_external_review")
    return ClinicalPopulationTransportReview(
        status=_text(data["status"], f"{path}.status"),
        reviewer_id=_text(data["reviewer_id"], f"{path}.reviewer_id"),
        reviewer_role=_text(data["reviewer_role"], f"{path}.reviewer_role"),
        reviewed_at=_datetime(data["reviewed_at"], f"{path}.reviewed_at"),
        independent_external_review=independent,
    )


def compile_clinical_population_transport_report(
    synthesis: BenefitRiskSynthesisRecord,
    designs: Sequence[TrialDesignRecord],
    source_documents: Mapping[str, bytes],
    spec: ClinicalPopulationTransportSpec,
) -> ClinicalPopulationTransportReport:
    """Compile a side-by-side population diagnostic without a transport estimate."""

    _require_instance(synthesis, BenefitRiskSynthesisRecord, "synthesis")
    _require_instance(spec, ClinicalPopulationTransportSpec, "spec")
    if synthesis.synthesis_id != spec.synthesis_id:
        raise ClinicalPopulationTransportError("spec is rebound to another synthesis")
    if synthesis.pooling_method != "none" or synthesis.pooling_performed:
        raise ClinicalPopulationTransportError(
            "population diagnostic requires non-pooled synthesis"
        )
    design_tuple = tuple(designs)
    design_by_id: dict[str, TrialDesignRecord] = {}
    for design in design_tuple:
        _require_instance(design, TrialDesignRecord, "designs item")
        if design.design_id in design_by_id:
            raise ClinicalPopulationTransportError("design ids must be unique")
        design_by_id[design.design_id] = design
    studies = tuple(synthesis.studies)
    if tuple(item.trial_id for item in spec.bindings) != tuple(
        item.trial_id for item in studies
    ):
        raise ClinicalPopulationTransportError(
            "spec binding order must exactly match synthesis study order"
        )
    records: list[ClinicalPopulationStratumRecord] = []
    for study, binding in zip(studies, spec.bindings, strict=True):
        if (
            binding.design_id != study.design_id
            or binding.endpoint_id != study.endpoint_id
        ):
            raise ClinicalPopulationTransportError(
                "stratum binding does not match the synthesis study identity"
            )
        design = design_by_id.get(binding.design_id)
        if design is None or design.trial_id != binding.trial_id:
            raise ClinicalPopulationTransportError(
                "bound trial design is missing or rebound"
            )
        endpoints = tuple(
            item for item in design.endpoints if item.endpoint_id == binding.endpoint_id
        )
        populations = tuple(
            item
            for item in design.populations
            if item.population_id == binding.population_id
        )
        if len(endpoints) != 1 or len(populations) != 1:
            raise ClinicalPopulationTransportError(
                "bound endpoint or analysis population is missing or ambiguous"
            )
        endpoint = endpoints[0]
        population = populations[0]
        if endpoint.population_id != population.population_id:
            raise ClinicalPopulationTransportError(
                "endpoint does not reference the reviewed analysis population"
            )
        description_sha256 = _text_sha256(population.description)
        declared_description_sha256 = population.attributes.get(
            "source_description_sha256"
        )
        if declared_description_sha256 is not None and (
            declared_description_sha256 != description_sha256
        ):
            raise ClinicalPopulationTransportError(
                "analysis population description hash does not replay"
            )
        citation = binding.citation
        if citation.source_content_sha256 not in study.source_content_hashes:
            raise ClinicalPopulationTransportError(
                "population citation is not source-bound to the synthesis study"
            )
        payload = source_documents.get(citation.source_content_sha256)
        if payload is None:
            raise ClinicalPopulationTransportError(
                "reviewed source document is missing"
            )
        if hashlib.sha256(payload).hexdigest() != citation.source_content_sha256:
            raise ClinicalPopulationTransportError(
                "reviewed source document hash changed"
            )
        document = _load_source_document(
            payload, f"source_documents[{binding.trial_id}]"
        )
        source_trial_id = _json_pointer(
            document,
            "/protocolSection/identificationModule/nctId",
            f"{binding.trial_id}.source_trial_id",
        )
        if source_trial_id != binding.trial_id:
            raise ClinicalPopulationTransportError(
                "source document trial identity changed"
            )
        source_field = _json_pointer(
            document,
            citation.source_field_pointer,
            f"{binding.trial_id}.source_field_pointer",
        )
        if not isinstance(source_field, str) or not source_field.strip():
            raise ClinicalPopulationTransportError("reviewed source field is not text")
        if _text_sha256(source_field) != citation.source_field_sha256:
            raise ClinicalPopulationTransportError("reviewed source field hash changed")
        records.append(
            ClinicalPopulationStratumRecord(
                trial_id=study.trial_id,
                study_record_id=study.study_record_id,
                design_id=study.design_id,
                endpoint_id=study.endpoint_id,
                population_id=population.population_id,
                population_description_sha256=description_sha256,
                stratum_id=binding.stratum_id,
                stratum_label=binding.stratum_label,
                population_context=binding.population_context,
                source_content_sha256=citation.source_content_sha256,
                source_field_pointer=citation.source_field_pointer,
                source_field_sha256=citation.source_field_sha256,
                effect_estimate=study.effect_estimate,
                confidence_interval_percent=study.confidence_interval_percent,
                confidence_interval_lower=study.confidence_interval_lower,
                confidence_interval_upper=study.confidence_interval_upper,
                measurement_unit=study.measurement_unit,
                endpoint_time_frame=study.endpoint_time_frame,
                safety_time_frame=study.safety_time_frame,
                candidate_serious_num_affected=study.candidate_serious_num_affected,
                candidate_serious_num_at_risk=study.candidate_serious_num_at_risk,
                comparator_serious_num_affected=study.comparator_serious_num_affected,
                comparator_serious_num_at_risk=study.comparator_serious_num_at_risk,
                serious_event_risk_difference=study.serious_event_risk_difference,
                benefit_direction=study.benefit_direction,
                safety_direction=study.safety_direction,
            )
        )
    stratum_ids = sorted({item.stratum_id for item in records})
    support = tuple(
        ClinicalPopulationStratumSupport(
            stratum_id=stratum_id,
            trial_count=sum(item.stratum_id == stratum_id for item in records),
        )
        for stratum_id in stratum_ids
    )
    blockers = ["target_population_not_declared"]
    if len(stratum_ids) > 1:
        blockers.append("distinct_reviewed_population_strata")
    if any(item.trial_count < 2 for item in support):
        blockers.append("no_within_stratum_replication")
    blockers.extend(
        (
            "aggregate_registry_results_only",
            "individual_level_covariates_unavailable",
            "transport_model_not_preregistered",
            "risk_of_bias_not_assessed",
        )
    )
    return ClinicalPopulationTransportReport(
        analysis_id=spec.analysis_id,
        spec_sha256=clinical_population_transport_spec_integrity_sha256(spec),
        method_id=CLINICAL_POPULATION_TRANSPORT_METHOD_ID,
        synthesis_id=synthesis.synthesis_id,
        synthesis_sha256=_sha256(synthesis),
        candidate_id=synthesis.candidate_id,
        intervention_id=synthesis.intervention_id,
        disease_id=synthesis.disease_id,
        endpoint_mapping_id=synthesis.endpoint_mapping_id,
        endpoint_family=synthesis.endpoint_family,
        effect_measure=synthesis.effect_measure,
        safety_measure=synthesis.safety_measure,
        stratification_axis_id=spec.stratification_axis_id,
        stratification_axis_label=spec.stratification_axis_label,
        analysis_mode=spec.analysis_mode,
        review=spec.review,
        strata=tuple(records),
        stratum_support=support,
        status=CLINICAL_POPULATION_TRANSPORT_STATUS,
        transportability_blockers=tuple(blockers),
        source_evidence_ids=synthesis.source_evidence_ids,
        source_content_hashes=synthesis.source_content_hashes,
    )


def clinical_population_transport_report_integrity_sha256(
    report: ClinicalPopulationTransportReport,
) -> str:
    _require_instance(report, ClinicalPopulationTransportReport, "report")
    return _sha256(report)


def clinical_population_transport_report_envelope(
    report: ClinicalPopulationTransportReport,
) -> dict[str, Any]:
    value = to_primitive(report)
    if not isinstance(value, dict):
        raise TypeError("serialized population transport report must be an object")
    return {
        "schema_version": CLINICAL_POPULATION_TRANSPORT_REPORT_SCHEMA_VERSION,
        "integrity_sha256": clinical_population_transport_report_integrity_sha256(
            report
        ),
        **value,
    }


def _parse_stratum(value: Any, path: str) -> ClinicalPopulationStratumRecord:
    data = _mapping(value, path)
    fields = set(ClinicalPopulationStratumRecord.__dataclass_fields__)
    _exact_fields(data, fields, path)
    return ClinicalPopulationStratumRecord(**data)


def clinical_population_transport_report_from_dict(
    value: Any,
    path: str = "clinical_population_transport_report",
) -> ClinicalPopulationTransportReport:
    data = _mapping(value, path)
    report_fields = set(ClinicalPopulationTransportReport.__dataclass_fields__)
    _exact_fields(data, {"schema_version", "integrity_sha256", *report_fields}, path)
    if data["schema_version"] != CLINICAL_POPULATION_TRANSPORT_REPORT_SCHEMA_VERSION:
        raise ClinicalPopulationTransportError(f"{path}.schema_version is unsupported")
    integrity_sha256 = _text(data.pop("integrity_sha256"), f"{path}.integrity_sha256")
    data.pop("schema_version")
    _require_sha256(integrity_sha256, f"{path}.integrity_sha256")
    data["review"] = _parse_review(data["review"], f"{path}.review")
    data["strata"] = tuple(
        _parse_stratum(item, f"{path}.strata[{index}]")
        for index, item in enumerate(_tuple(data["strata"], f"{path}.strata"))
    )
    support: list[ClinicalPopulationStratumSupport] = []
    for index, raw in enumerate(
        _tuple(data["stratum_support"], f"{path}.stratum_support")
    ):
        item_path = f"{path}.stratum_support[{index}]"
        item = _mapping(raw, item_path)
        _exact_fields(item, {"stratum_id", "trial_count"}, item_path)
        support.append(ClinicalPopulationStratumSupport(**item))
    data["stratum_support"] = tuple(support)
    for field_name in (
        "transportability_blockers",
        "source_evidence_ids",
        "source_content_hashes",
        "limitations",
    ):
        data[field_name] = _tuple(data[field_name], f"{path}.{field_name}")
    try:
        report = ClinicalPopulationTransportReport(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalPopulationTransportError(f"{path} is invalid") from exc
    if (
        clinical_population_transport_report_integrity_sha256(report)
        != integrity_sha256
    ):
        raise ClinicalPopulationTransportError(f"{path}.integrity_sha256 mismatch")
    return report


def clinical_population_transport_report_from_json(
    payload: str | bytes,
) -> ClinicalPopulationTransportReport:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordParseError("population transport report is not valid JSON") from exc
    return clinical_population_transport_report_from_dict(value)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecordParseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
