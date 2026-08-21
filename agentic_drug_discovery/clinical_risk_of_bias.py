"""Outcome-specific, source-bound clinical risk-of-bias assessments."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from .clinical_population_transport import (
    ClinicalPopulationTransportReport,
    clinical_population_transport_report_integrity_sha256,
)
from .models import (
    SerializableRecord,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError


CLINICAL_RISK_OF_BIAS_SPEC_SCHEMA_VERSION = "adds.clinical-risk-of-bias-spec.v1"
CLINICAL_RISK_OF_BIAS_REPORT_SCHEMA_VERSION = "adds.clinical-risk-of-bias-report.v1"
CLINICAL_RISK_OF_BIAS_METHOD_ID = (
    "adds.project-internal-outcome-specific-risk-of-bias.v1"
)
CLINICAL_RISK_OF_BIAS_STATUS = "project_internal_outcome_specific_assessment_complete"

RISK_OF_BIAS_DOMAIN_IDS = (
    "randomization_process",
    "deviations_from_intended_interventions",
    "missing_outcome_data",
    "measurement_of_the_outcome",
    "selection_of_the_reported_result",
)
RISK_OF_BIAS_JUDGMENTS = (
    "low",
    "some_concerns",
    "high",
    "insufficient_information",
)

_CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_PDF_FORMAT = "application/pdf"
_REGISTRY_FORMAT = "clinicaltrials.gov-study-v2"
_REGISTRY_ROLE = "registry_results"
_PROTOCOL_SAP_ROLE = "protocol_sap"
_RISK_NOT_ASSESSED_BLOCKER = "risk_of_bias_not_assessed"
_REQUIRED_LIMITATIONS = (
    (
        "This is a project-internal, outcome-specific structured judgment based on the "
        "exact public registry and protocol/SAP sources cited; it is not an official "
        "Cochrane RoB 2 assessment."
    ),
    (
        "Public aggregate sources do not establish whether every realized unblinding, "
        "protocol deviation, or analysis decision was completely reported."
    ),
    (
        "A complete assessment resolves only the absence-of-assessment blocker; it does "
        "not make trials exchangeable, justify pooling, or estimate transportability."
    ),
    (
        "The assessment does not establish efficacy, comparative safety, clinical "
        "acceptability, or a treatment recommendation."
    ),
    (
        "Independent external scientific review is not implied by project-internal "
        "approval."
    ),
)


class ClinicalRiskOfBiasError(ValueError):
    """Raised when a risk-of-bias assessment cannot bind safely."""


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


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalRiskOfBiasError(f"{path} must be an object")
    return dict(value)


def _tuple(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ClinicalRiskOfBiasError(f"{path} must be an array")
    return tuple(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClinicalRiskOfBiasError(f"{path} must be non-empty text")
    return value.strip()


def _exact_fields(data: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(data) != expected:
        raise ClinicalRiskOfBiasError(f"{path} must contain exactly {sorted(expected)}")


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _datetime(value: Any, path: str) -> datetime:
    text = _text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClinicalRiskOfBiasError(f"{path} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClinicalRiskOfBiasError(f"{path} must be timezone-aware")
    return parsed


def _parse_iso_date(value: str, path: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ClinicalRiskOfBiasError(f"{path} must be YYYY-MM-DD") from exc


def _date_lower_bound(value: str, path: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return _parse_iso_date(value, path)
    month_match = re.fullmatch(r"([0-9]{4})-([0-9]{2})", value)
    if month_match:
        year, month = (int(item) for item in month_match.groups())
        if not 1 <= month <= 12:
            raise ClinicalRiskOfBiasError(f"{path} has an invalid month")
        return date(year, month, 1)
    if re.fullmatch(r"[0-9]{4}", value):
        return date(int(value), 1, 1)
    raise ClinicalRiskOfBiasError(f"{path} has unsupported date precision")


def _load_registry_document(payload: bytes, path: str) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise ClinicalRiskOfBiasError(f"{path} must be bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ClinicalRiskOfBiasError(
                    f"{path} contains duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is not valid UTF-8 JSON") from exc
    return _mapping(value, path)


def _json_pointer(document: Any, pointer: str, path: str) -> Any:
    if not pointer.startswith("/"):
        raise ClinicalRiskOfBiasError(f"{path} must be an absolute JSON pointer")
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise ClinicalRiskOfBiasError(
                    f"{path} does not resolve in the source document"
                )
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                raise ClinicalRiskOfBiasError(f"{path} contains an invalid array index")
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise ClinicalRiskOfBiasError(
                    f"{path} does not resolve in the source document"
                ) from exc
        else:
            raise ClinicalRiskOfBiasError(
                f"{path} does not resolve in the source document"
            )
    return current


def _overall_judgment(domains: Sequence["ClinicalRiskOfBiasDomainAssessment"]) -> str:
    judgments = {item.judgment for item in domains}
    if "high" in judgments:
        return "high"
    if "insufficient_information" in judgments:
        return "insufficient_information"
    if "some_concerns" in judgments:
        return "some_concerns"
    return "low"


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasSourceCitation(SerializableRecord):
    """Exact public source and locator reviewed for a domain judgment."""

    citation_id: str
    source_role: str
    source_document_format: str
    source_locator: str
    source_content_sha256: str
    source_document_date: str | None = None
    source_field_pointer: str | None = None
    source_field_sha256: str | None = None
    source_page: int | None = None
    source_section: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "citation_id",
            "source_role",
            "source_document_format",
            "source_locator",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        if _CANONICAL_ID.fullmatch(self.citation_id) is None:
            raise ValueError("citation_id must be a canonical snake-case id")
        parsed = urlparse(self.source_locator)
        if parsed.scheme != "https":
            raise ValueError("source_locator must use HTTPS")
        if self.source_role == _REGISTRY_ROLE:
            if self.source_document_format != _REGISTRY_FORMAT:
                raise ValueError("registry citation format is unsupported")
            if parsed.netloc != "clinicaltrials.gov":
                raise ValueError("registry citation must use clinicaltrials.gov")
            if self.source_document_date is not None:
                raise ValueError("registry citation source_document_date must be null")
            if self.source_field_pointer is None or self.source_field_sha256 is None:
                raise ValueError("registry citation requires a field pointer and hash")
            if not self.source_field_pointer.startswith("/"):
                raise ValueError(
                    "source_field_pointer must be an absolute JSON pointer"
                )
            _require_sha256(self.source_field_sha256, "source_field_sha256")
            if self.source_page is not None or self.source_section is not None:
                raise ValueError(
                    "registry citation cannot declare a PDF page or section"
                )
        elif self.source_role == _PROTOCOL_SAP_ROLE:
            if self.source_document_format != _PDF_FORMAT:
                raise ValueError("protocol/SAP citation format is unsupported")
            if parsed.netloc != "cdn.clinicaltrials.gov":
                raise ValueError("protocol/SAP citation must use the registry CDN")
            if self.source_document_date is None:
                raise ValueError("protocol/SAP citation requires source_document_date")
            _parse_iso_date(self.source_document_date, "source_document_date")
            if (
                self.source_field_pointer is not None
                or self.source_field_sha256 is not None
            ):
                raise ValueError("protocol/SAP citation cannot declare a JSON field")
            if (
                not isinstance(self.source_page, int)
                or isinstance(self.source_page, bool)
                or self.source_page < 1
            ):
                raise ValueError(
                    "protocol/SAP citation requires a positive source_page"
                )
            if self.source_section is None:
                raise ValueError("protocol/SAP citation requires source_section")
            _require_text(self.source_section, "source_section")
        else:
            raise ValueError("source_role is unsupported")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasDomainAssessment(SerializableRecord):
    """Reviewer-authored judgment for one required outcome-specific domain."""

    domain_id: str
    judgment: str
    rationale: str
    citation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("domain_id", "judgment", "rationale"):
            _require_text(getattr(self, field_name), field_name)
        if self.domain_id not in RISK_OF_BIAS_DOMAIN_IDS:
            raise ValueError("domain_id is unsupported")
        if self.judgment not in RISK_OF_BIAS_JUDGMENTS:
            raise ValueError("judgment is unsupported")
        citation_ids = tuple(self.citation_ids)
        object.__setattr__(self, "citation_ids", citation_ids)
        if not citation_ids or len(set(citation_ids)) != len(citation_ids):
            raise ValueError("citation_ids must be non-empty and unique")
        for citation_id in citation_ids:
            _require_text(citation_id, "citation_ids item")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasTrialAssessment(SerializableRecord):
    """Reviewed domain judgments and exact arm bindings for one trial outcome."""

    trial_id: str
    design_id: str
    endpoint_id: str
    candidate_result_group_id: str
    comparator_result_group_id: str
    candidate_flow_group_id: str
    comparator_flow_group_id: str
    citations: tuple[ClinicalRiskOfBiasSourceCitation, ...]
    domains: tuple[ClinicalRiskOfBiasDomainAssessment, ...]
    overall_judgment: str
    unresolved_concerns: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "design_id",
            "endpoint_id",
            "candidate_result_group_id",
            "comparator_result_group_id",
            "candidate_flow_group_id",
            "comparator_flow_group_id",
            "overall_judgment",
        ):
            _require_text(getattr(self, field_name), field_name)
        if _NCT_ID.fullmatch(self.trial_id) is None:
            raise ValueError("trial_id must be an NCT identifier")
        if self.overall_judgment not in RISK_OF_BIAS_JUDGMENTS:
            raise ValueError("overall_judgment is unsupported")
        citations = tuple(self.citations)
        domains = tuple(self.domains)
        concerns = tuple(self.unresolved_concerns)
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "domains", domains)
        object.__setattr__(self, "unresolved_concerns", concerns)
        if not citations:
            raise ValueError("citations must not be empty")
        for citation in citations:
            _require_instance(
                citation, ClinicalRiskOfBiasSourceCitation, "citations item"
            )
        citation_ids = tuple(item.citation_id for item in citations)
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("citation ids must be unique within a trial")
        if tuple(item.domain_id for item in domains) != RISK_OF_BIAS_DOMAIN_IDS:
            raise ValueError("domains must use the complete canonical domain order")
        for domain in domains:
            _require_instance(
                domain, ClinicalRiskOfBiasDomainAssessment, "domains item"
            )
            unknown = set(domain.citation_ids).difference(citation_ids)
            if unknown:
                raise ValueError("domain assessment references an unknown citation")
            roles = {
                citation.source_role
                for citation in citations
                if citation.citation_id in domain.citation_ids
            }
            if roles != {_REGISTRY_ROLE, _PROTOCOL_SAP_ROLE}:
                raise ValueError(
                    "each domain must cite both registry results and protocol/SAP"
                )
        referenced = {
            citation_id for domain in domains for citation_id in domain.citation_ids
        }
        if referenced != set(citation_ids):
            raise ValueError("every citation must support at least one domain")
        if self.overall_judgment != _overall_judgment(domains):
            raise ValueError("overall_judgment does not match domain judgments")
        if self.overall_judgment == "low" and concerns:
            raise ValueError("low overall judgment cannot declare unresolved concerns")
        if self.overall_judgment != "low" and not concerns:
            raise ValueError("non-low overall judgment requires unresolved concerns")
        if len(concerns) != len(set(concerns)):
            raise ValueError("unresolved_concerns must be unique")
        for concern in concerns:
            _require_text(concern, "unresolved_concerns item")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasReview(SerializableRecord):
    """Project-internal review scope; independent review cannot be claimed in v1."""

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
        if self.status != "approved_for_project_internal_risk_of_bias":
            raise ValueError("review status is unsupported")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        if self.independent_external_review:
            raise ValueError("v1 cannot attest independent external review")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasSpec(SerializableRecord):
    """Reviewed outcome judgments bound to a prior transport report."""

    analysis_id: str
    transport_analysis_id: str
    transport_report_integrity_sha256: str
    endpoint_family: str
    outcome_time_frame: str
    assessments: tuple[ClinicalRiskOfBiasTrialAssessment, ...]
    review: ClinicalRiskOfBiasReview
    method_id: str = CLINICAL_RISK_OF_BIAS_METHOD_ID

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "transport_analysis_id",
            "endpoint_family",
            "outcome_time_frame",
            "method_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(
            self.transport_report_integrity_sha256,
            "transport_report_integrity_sha256",
        )
        if self.method_id != CLINICAL_RISK_OF_BIAS_METHOD_ID:
            raise ValueError("method_id is unsupported")
        assessments = tuple(self.assessments)
        object.__setattr__(self, "assessments", assessments)
        if len(assessments) < 2:
            raise ValueError("assessments must contain at least two trials")
        for assessment in assessments:
            _require_instance(
                assessment, ClinicalRiskOfBiasTrialAssessment, "assessments item"
            )
        for label, values in (
            ("trial ids", tuple(item.trial_id for item in assessments)),
            ("design ids", tuple(item.design_id for item in assessments)),
            ("endpoint ids", tuple(item.endpoint_id for item in assessments)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"assessments must use unique {label}")
        _require_instance(self.review, ClinicalRiskOfBiasReview, "review")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasTrialRecord(SerializableRecord):
    """Compiled trial judgment with temporal and denominator diagnostics."""

    trial_id: str
    design_id: str
    endpoint_id: str
    candidate_result_group_id: str
    comparator_result_group_id: str
    candidate_flow_group_id: str
    comparator_flow_group_id: str
    candidate_started: int
    comparator_started: int
    candidate_primary_endpoint_denominator: int
    comparator_primary_endpoint_denominator: int
    primary_endpoint_denominator_complete: bool
    protocol_sap_document_date: str
    primary_completion_date: str
    protocol_sap_precedes_primary_completion: bool
    source_content_hashes: tuple[str, ...]
    citations: tuple[ClinicalRiskOfBiasSourceCitation, ...]
    domains: tuple[ClinicalRiskOfBiasDomainAssessment, ...]
    overall_judgment: str
    unresolved_concerns: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "trial_id",
            "design_id",
            "endpoint_id",
            "candidate_result_group_id",
            "comparator_result_group_id",
            "candidate_flow_group_id",
            "comparator_flow_group_id",
            "protocol_sap_document_date",
            "primary_completion_date",
            "overall_judgment",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "candidate_started",
            "comparator_started",
            "candidate_primary_endpoint_denominator",
            "comparator_primary_endpoint_denominator",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        _require_bool(
            self.primary_endpoint_denominator_complete,
            "primary_endpoint_denominator_complete",
        )
        _require_bool(
            self.protocol_sap_precedes_primary_completion,
            "protocol_sap_precedes_primary_completion",
        )
        if self.primary_endpoint_denominator_complete != (
            self.candidate_started == self.candidate_primary_endpoint_denominator
            and self.comparator_started == self.comparator_primary_endpoint_denominator
        ):
            raise ValueError(
                "primary endpoint denominator completeness does not replay"
            )
        _parse_iso_date(self.protocol_sap_document_date, "protocol_sap_document_date")
        _date_lower_bound(self.primary_completion_date, "primary_completion_date")
        if self.protocol_sap_precedes_primary_completion != (
            _parse_iso_date(
                self.protocol_sap_document_date, "protocol_sap_document_date"
            )
            <= _date_lower_bound(
                self.primary_completion_date, "primary_completion_date"
            )
        ):
            raise ValueError("protocol/SAP temporal ordering does not replay")
        source_hashes = tuple(self.source_content_hashes)
        citations = tuple(self.citations)
        domains = tuple(self.domains)
        concerns = tuple(self.unresolved_concerns)
        object.__setattr__(self, "source_content_hashes", source_hashes)
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "domains", domains)
        object.__setattr__(self, "unresolved_concerns", concerns)
        ClinicalRiskOfBiasTrialAssessment(
            trial_id=self.trial_id,
            design_id=self.design_id,
            endpoint_id=self.endpoint_id,
            candidate_result_group_id=self.candidate_result_group_id,
            comparator_result_group_id=self.comparator_result_group_id,
            candidate_flow_group_id=self.candidate_flow_group_id,
            comparator_flow_group_id=self.comparator_flow_group_id,
            citations=citations,
            domains=domains,
            overall_judgment=self.overall_judgment,
            unresolved_concerns=concerns,
        )
        if tuple(sorted(set(source_hashes))) != source_hashes:
            raise ValueError("source_content_hashes must use canonical unique order")
        for digest in source_hashes:
            _require_sha256(digest, "source_content_hashes item")
        if source_hashes != tuple(
            sorted({item.source_content_sha256 for item in citations})
        ):
            raise ValueError(
                "source_content_hashes must equal the citation source union"
            )
        if tuple(item.domain_id for item in domains) != RISK_OF_BIAS_DOMAIN_IDS:
            raise ValueError("domains must use the complete canonical domain order")
        if self.overall_judgment != _overall_judgment(domains):
            raise ValueError("overall_judgment does not match domain judgments")


@dataclass(frozen=True, slots=True)
class ClinicalRiskOfBiasReport(SerializableRecord):
    """Integrity-bound assessment and narrow blocker delta."""

    analysis_id: str
    spec_sha256: str
    method_id: str
    transport_analysis_id: str
    transport_report_integrity_sha256: str
    endpoint_family: str
    outcome_time_frame: str
    review: ClinicalRiskOfBiasReview
    trials: tuple[ClinicalRiskOfBiasTrialRecord, ...]
    status: str
    prior_transportability_blockers: tuple[str, ...]
    resolved_transportability_blockers: tuple[str, ...]
    remaining_transportability_blockers: tuple[str, ...]
    assessment_cautions: tuple[str, ...]
    source_content_hashes: tuple[str, ...]
    risk_of_bias_assessed: bool = True
    pooling_performed: bool = False
    transport_effect_estimated: bool = False
    treatment_recommendation_supported: bool = False
    independent_external_review_completed: bool = False
    limitations: tuple[str, ...] = _REQUIRED_LIMITATIONS

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "method_id",
            "transport_analysis_id",
            "endpoint_family",
            "outcome_time_frame",
            "status",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.spec_sha256, "spec_sha256")
        _require_sha256(
            self.transport_report_integrity_sha256,
            "transport_report_integrity_sha256",
        )
        if self.method_id != CLINICAL_RISK_OF_BIAS_METHOD_ID:
            raise ValueError("method_id is unsupported")
        if self.status != CLINICAL_RISK_OF_BIAS_STATUS:
            raise ValueError("status is unsupported")
        _require_instance(self.review, ClinicalRiskOfBiasReview, "review")
        trials = tuple(self.trials)
        prior = tuple(self.prior_transportability_blockers)
        resolved = tuple(self.resolved_transportability_blockers)
        remaining = tuple(self.remaining_transportability_blockers)
        cautions = tuple(self.assessment_cautions)
        source_hashes = tuple(self.source_content_hashes)
        limitations = tuple(self.limitations)
        object.__setattr__(self, "trials", trials)
        object.__setattr__(self, "prior_transportability_blockers", prior)
        object.__setattr__(self, "resolved_transportability_blockers", resolved)
        object.__setattr__(self, "remaining_transportability_blockers", remaining)
        object.__setattr__(self, "assessment_cautions", cautions)
        object.__setattr__(self, "source_content_hashes", source_hashes)
        object.__setattr__(self, "limitations", limitations)
        if len(trials) < 2:
            raise ValueError("trials must contain at least two assessments")
        for trial in trials:
            _require_instance(trial, ClinicalRiskOfBiasTrialRecord, "trials item")
        if len({item.trial_id for item in trials}) != len(trials):
            raise ValueError("trial ids must be unique")
        if _RISK_NOT_ASSESSED_BLOCKER not in prior:
            raise ValueError("prior blockers must include risk_of_bias_not_assessed")
        if len(prior) != len(set(prior)):
            raise ValueError("prior blockers must be unique")
        if resolved != (_RISK_NOT_ASSESSED_BLOCKER,):
            raise ValueError("v1 resolves only risk_of_bias_not_assessed")
        if remaining != tuple(
            item for item in prior if item != _RISK_NOT_ASSESSED_BLOCKER
        ):
            raise ValueError("remaining blockers must preserve the exact narrow delta")
        if not remaining:
            raise ValueError("v1 cannot resolve all transportability blockers")
        if tuple(sorted(set(cautions))) != cautions:
            raise ValueError("assessment_cautions must use canonical unique order")
        for caution in cautions:
            _require_text(caution, "assessment_cautions item")
        if tuple(sorted(set(source_hashes))) != source_hashes:
            raise ValueError("source_content_hashes must use canonical unique order")
        if source_hashes != tuple(
            sorted(
                {digest for trial in trials for digest in trial.source_content_hashes}
            )
        ):
            raise ValueError("source_content_hashes must equal the trial source union")
        for field_name in (
            "risk_of_bias_assessed",
            "pooling_performed",
            "transport_effect_estimated",
            "treatment_recommendation_supported",
            "independent_external_review_completed",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.risk_of_bias_assessed:
            raise ValueError("risk_of_bias_assessed must be true")
        if any(
            (
                self.pooling_performed,
                self.transport_effect_estimated,
                self.treatment_recommendation_supported,
                self.independent_external_review_completed,
            )
        ):
            raise ValueError(
                "v1 prohibited-inference and external-review flags must be false"
            )
        if self.review.independent_external_review:
            raise ValueError("report review scope conflicts with v1")
        if not set(_REQUIRED_LIMITATIONS).issubset(limitations):
            raise ValueError("report is missing required limitations")


def clinical_risk_of_bias_spec_to_dict(spec: ClinicalRiskOfBiasSpec) -> dict[str, Any]:
    _require_instance(spec, ClinicalRiskOfBiasSpec, "spec")
    value = to_primitive(spec)
    if not isinstance(value, dict):
        raise TypeError("serialized risk-of-bias spec must be an object")
    return {"schema_version": CLINICAL_RISK_OF_BIAS_SPEC_SCHEMA_VERSION, **value}


def clinical_risk_of_bias_spec_integrity_sha256(spec: ClinicalRiskOfBiasSpec) -> str:
    return _sha256(clinical_risk_of_bias_spec_to_dict(spec))


def _parse_citation(value: Any, path: str) -> ClinicalRiskOfBiasSourceCitation:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasSourceCitation.__dataclass_fields__)
    _exact_fields(data, fields, path)
    try:
        return ClinicalRiskOfBiasSourceCitation(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def _parse_domain(value: Any, path: str) -> ClinicalRiskOfBiasDomainAssessment:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasDomainAssessment.__dataclass_fields__)
    _exact_fields(data, fields, path)
    data["citation_ids"] = _tuple(data["citation_ids"], f"{path}.citation_ids")
    try:
        return ClinicalRiskOfBiasDomainAssessment(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def _parse_trial_assessment(value: Any, path: str) -> ClinicalRiskOfBiasTrialAssessment:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasTrialAssessment.__dataclass_fields__)
    _exact_fields(data, fields, path)
    data["citations"] = tuple(
        _parse_citation(item, f"{path}.citations[{index}]")
        for index, item in enumerate(_tuple(data["citations"], f"{path}.citations"))
    )
    data["domains"] = tuple(
        _parse_domain(item, f"{path}.domains[{index}]")
        for index, item in enumerate(_tuple(data["domains"], f"{path}.domains"))
    )
    data["unresolved_concerns"] = _tuple(
        data["unresolved_concerns"], f"{path}.unresolved_concerns"
    )
    try:
        return ClinicalRiskOfBiasTrialAssessment(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def _parse_review(value: Any, path: str) -> ClinicalRiskOfBiasReview:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasReview.__dataclass_fields__)
    _exact_fields(data, fields, path)
    data["reviewed_at"] = _datetime(data["reviewed_at"], f"{path}.reviewed_at")
    try:
        return ClinicalRiskOfBiasReview(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def clinical_risk_of_bias_spec_from_dict(
    value: Any,
    path: str = "clinical_risk_of_bias_spec",
) -> ClinicalRiskOfBiasSpec:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasSpec.__dataclass_fields__)
    _exact_fields(data, {"schema_version", *fields}, path)
    if data.pop("schema_version") != CLINICAL_RISK_OF_BIAS_SPEC_SCHEMA_VERSION:
        raise ClinicalRiskOfBiasError(f"{path}.schema_version is unsupported")
    data["assessments"] = tuple(
        _parse_trial_assessment(item, f"{path}.assessments[{index}]")
        for index, item in enumerate(_tuple(data["assessments"], f"{path}.assessments"))
    )
    data["review"] = _parse_review(data["review"], f"{path}.review")
    try:
        return ClinicalRiskOfBiasSpec(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def clinical_risk_of_bias_spec_from_json(
    payload: str | bytes,
) -> ClinicalRiskOfBiasSpec:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordParseError("risk-of-bias spec is not valid JSON") from exc
    return clinical_risk_of_bias_spec_from_dict(value)


def _measurement_count(outcome: Mapping[str, Any], group_id: str, path: str) -> int:
    for denom in _tuple(outcome.get("denoms"), f"{path}.denoms"):
        denom_data = _mapping(denom, f"{path}.denoms item")
        for count in _tuple(denom_data.get("counts"), f"{path}.denoms.counts"):
            count_data = _mapping(count, f"{path}.denoms.counts item")
            if count_data.get("groupId") == group_id:
                raw = count_data.get("value")
                if not isinstance(raw, str) or not raw.isdigit() or int(raw) < 1:
                    raise ClinicalRiskOfBiasError(
                        f"{path} has an invalid denominator for {group_id}"
                    )
                return int(raw)
    raise ClinicalRiskOfBiasError(f"{path} has no denominator for {group_id}")


def _started_count(document: Mapping[str, Any], group_id: str, path: str) -> int:
    periods = _json_pointer(
        document, "/resultsSection/participantFlowModule/periods", f"{path}.periods"
    )
    for period in _tuple(periods, f"{path}.periods"):
        for milestone in _tuple(
            _mapping(period, f"{path}.period").get("milestones"),
            f"{path}.milestones",
        ):
            milestone_data = _mapping(milestone, f"{path}.milestone")
            if milestone_data.get("type") != "STARTED":
                continue
            for achievement in _tuple(
                milestone_data.get("achievements"), f"{path}.achievements"
            ):
                achievement_data = _mapping(achievement, f"{path}.achievement")
                if achievement_data.get("groupId") == group_id:
                    raw = achievement_data.get("numSubjects")
                    if not isinstance(raw, str) or not raw.isdigit() or int(raw) < 1:
                        raise ClinicalRiskOfBiasError(
                            f"{path} has an invalid STARTED count for {group_id}"
                        )
                    return int(raw)
    raise ClinicalRiskOfBiasError(f"{path} has no STARTED count for {group_id}")


def compile_clinical_risk_of_bias_report(
    transport_report: ClinicalPopulationTransportReport,
    source_documents: Mapping[str, bytes],
    spec: ClinicalRiskOfBiasSpec,
) -> ClinicalRiskOfBiasReport:
    """Compile exact-source domain judgments and a narrow transport blocker delta."""

    _require_instance(
        transport_report, ClinicalPopulationTransportReport, "transport_report"
    )
    _require_instance(spec, ClinicalRiskOfBiasSpec, "spec")
    transport_integrity = clinical_population_transport_report_integrity_sha256(
        transport_report
    )
    if transport_report.analysis_id != spec.transport_analysis_id:
        raise ClinicalRiskOfBiasError("spec is rebound to another transport analysis")
    if transport_integrity != spec.transport_report_integrity_sha256:
        raise ClinicalRiskOfBiasError("linked transport report integrity changed")
    if transport_report.endpoint_family != spec.endpoint_family:
        raise ClinicalRiskOfBiasError("endpoint family changed")
    if _RISK_NOT_ASSESSED_BLOCKER not in transport_report.transportability_blockers:
        raise ClinicalRiskOfBiasError("linked report has no absent-assessment blocker")
    if tuple(item.trial_id for item in spec.assessments) != tuple(
        item.trial_id for item in transport_report.strata
    ):
        raise ClinicalRiskOfBiasError(
            "assessment order must exactly match the transport trial order"
        )

    records: list[ClinicalRiskOfBiasTrialRecord] = []
    for assessment, stratum in zip(
        spec.assessments, transport_report.strata, strict=True
    ):
        if (
            assessment.design_id != stratum.design_id
            or assessment.endpoint_id != stratum.endpoint_id
        ):
            raise ClinicalRiskOfBiasError(
                "assessment identity does not match the transport trial"
            )
        registry_citations = tuple(
            item for item in assessment.citations if item.source_role == _REGISTRY_ROLE
        )
        pdf_citations = tuple(
            item
            for item in assessment.citations
            if item.source_role == _PROTOCOL_SAP_ROLE
        )
        registry_hashes = {item.source_content_sha256 for item in registry_citations}
        pdf_hashes = {item.source_content_sha256 for item in pdf_citations}
        if len(registry_hashes) != 1 or len(pdf_hashes) != 1:
            raise ClinicalRiskOfBiasError(
                "each trial must use one exact registry source and one protocol/SAP source"
            )
        registry_hash = next(iter(registry_hashes))
        pdf_hash = next(iter(pdf_hashes))
        if registry_hash != stratum.source_content_sha256:
            raise ClinicalRiskOfBiasError(
                "registry citation is not bound to the transport trial source"
            )
        registry_payload = source_documents.get(registry_hash)
        pdf_payload = source_documents.get(pdf_hash)
        if registry_payload is None or pdf_payload is None:
            raise ClinicalRiskOfBiasError("a cited source document is missing")
        if hashlib.sha256(registry_payload).hexdigest() != registry_hash:
            raise ClinicalRiskOfBiasError("registry source hash changed")
        if hashlib.sha256(pdf_payload).hexdigest() != pdf_hash:
            raise ClinicalRiskOfBiasError("protocol/SAP source hash changed")
        if not pdf_payload.startswith(b"%PDF-"):
            raise ClinicalRiskOfBiasError("protocol/SAP source is not a PDF")
        registry = _load_registry_document(
            registry_payload, f"source_documents[{assessment.trial_id}]"
        )
        source_trial_id = _json_pointer(
            registry,
            "/protocolSection/identificationModule/nctId",
            f"{assessment.trial_id}.source_trial_id",
        )
        if source_trial_id != assessment.trial_id:
            raise ClinicalRiskOfBiasError("registry source trial identity changed")
        expected_registry_locator = (
            f"https://clinicaltrials.gov/api/v2/studies/{assessment.trial_id}"
        )
        expected_pdf_path_token = f"/{assessment.trial_id}/"
        for citation in registry_citations:
            if citation.source_locator != expected_registry_locator:
                raise ClinicalRiskOfBiasError("registry source locator changed")
            source_field = _json_pointer(
                registry,
                citation.source_field_pointer or "",
                f"{assessment.trial_id}.{citation.citation_id}",
            )
            if _sha256(source_field) != citation.source_field_sha256:
                raise ClinicalRiskOfBiasError("reviewed registry field hash changed")
        for citation in pdf_citations:
            if expected_pdf_path_token not in urlparse(citation.source_locator).path:
                raise ClinicalRiskOfBiasError(
                    "protocol/SAP locator trial identity changed"
                )
        pdf_dates = {item.source_document_date for item in pdf_citations}
        if len(pdf_dates) != 1 or None in pdf_dates:
            raise ClinicalRiskOfBiasError("protocol/SAP document date is ambiguous")
        protocol_date = next(iter(pdf_dates))
        if protocol_date is None:  # narrowed above; retained for type checkers
            raise ClinicalRiskOfBiasError("protocol/SAP document date is missing")
        primary_completion = _json_pointer(
            registry,
            "/protocolSection/statusModule/primaryCompletionDateStruct/date",
            f"{assessment.trial_id}.primary_completion",
        )
        primary_completion = _text(
            primary_completion, f"{assessment.trial_id}.primary_completion"
        )
        protocol_precedes_completion = _parse_iso_date(
            protocol_date, f"{assessment.trial_id}.protocol_date"
        ) <= _date_lower_bound(
            primary_completion, f"{assessment.trial_id}.primary_completion"
        )
        outcome = _mapping(
            _json_pointer(
                registry,
                "/resultsSection/outcomeMeasuresModule/outcomeMeasures/0",
                f"{assessment.trial_id}.primary_outcome",
            ),
            f"{assessment.trial_id}.primary_outcome",
        )
        if (
            outcome.get("type") != "PRIMARY"
            or outcome.get("timeFrame") != spec.outcome_time_frame
        ):
            raise ClinicalRiskOfBiasError(
                "primary outcome identity or time frame changed"
            )
        candidate_started = _started_count(
            registry, assessment.candidate_flow_group_id, assessment.trial_id
        )
        comparator_started = _started_count(
            registry, assessment.comparator_flow_group_id, assessment.trial_id
        )
        candidate_denominator = _measurement_count(
            outcome,
            assessment.candidate_result_group_id,
            f"{assessment.trial_id}.primary_outcome",
        )
        comparator_denominator = _measurement_count(
            outcome,
            assessment.comparator_result_group_id,
            f"{assessment.trial_id}.primary_outcome",
        )
        denominator_complete = (
            candidate_started == candidate_denominator
            and comparator_started == comparator_denominator
        )
        domain_by_id = {item.domain_id: item for item in assessment.domains}
        if not denominator_complete and (
            domain_by_id["missing_outcome_data"].judgment == "low"
        ):
            raise ClinicalRiskOfBiasError(
                "missing-outcome-data judgment cannot be low with incomplete denominators"
            )
        if not protocol_precedes_completion and (
            domain_by_id["selection_of_the_reported_result"].judgment == "low"
        ):
            raise ClinicalRiskOfBiasError(
                "reported-result selection judgment cannot be low with a post-completion SAP"
            )
        records.append(
            ClinicalRiskOfBiasTrialRecord(
                trial_id=assessment.trial_id,
                design_id=assessment.design_id,
                endpoint_id=assessment.endpoint_id,
                candidate_result_group_id=assessment.candidate_result_group_id,
                comparator_result_group_id=assessment.comparator_result_group_id,
                candidate_flow_group_id=assessment.candidate_flow_group_id,
                comparator_flow_group_id=assessment.comparator_flow_group_id,
                candidate_started=candidate_started,
                comparator_started=comparator_started,
                candidate_primary_endpoint_denominator=candidate_denominator,
                comparator_primary_endpoint_denominator=comparator_denominator,
                primary_endpoint_denominator_complete=denominator_complete,
                protocol_sap_document_date=protocol_date,
                primary_completion_date=primary_completion,
                protocol_sap_precedes_primary_completion=protocol_precedes_completion,
                source_content_hashes=tuple(sorted((registry_hash, pdf_hash))),
                citations=assessment.citations,
                domains=assessment.domains,
                overall_judgment=assessment.overall_judgment,
                unresolved_concerns=assessment.unresolved_concerns,
            )
        )

    prior = transport_report.transportability_blockers
    remaining = tuple(item for item in prior if item != _RISK_NOT_ASSESSED_BLOCKER)
    cautions = {
        "aggregate_public_sources_do_not_report_all_realized_protocol_deviations",
        "independent_external_risk_of_bias_review_not_completed",
    }
    if any(item.overall_judgment == "some_concerns" for item in records):
        cautions.add("some_concerns_in_at_least_one_trial")
    if any(item.overall_judgment == "high" for item in records):
        cautions.add("high_risk_in_at_least_one_trial")
    if any(item.overall_judgment == "insufficient_information" for item in records):
        cautions.add("insufficient_information_in_at_least_one_trial")
    return ClinicalRiskOfBiasReport(
        analysis_id=spec.analysis_id,
        spec_sha256=clinical_risk_of_bias_spec_integrity_sha256(spec),
        method_id=spec.method_id,
        transport_analysis_id=transport_report.analysis_id,
        transport_report_integrity_sha256=transport_integrity,
        endpoint_family=spec.endpoint_family,
        outcome_time_frame=spec.outcome_time_frame,
        review=spec.review,
        trials=tuple(records),
        status=CLINICAL_RISK_OF_BIAS_STATUS,
        prior_transportability_blockers=prior,
        resolved_transportability_blockers=(_RISK_NOT_ASSESSED_BLOCKER,),
        remaining_transportability_blockers=remaining,
        assessment_cautions=tuple(sorted(cautions)),
        source_content_hashes=tuple(
            sorted(
                {digest for item in records for digest in item.source_content_hashes}
            )
        ),
    )


def clinical_risk_of_bias_report_integrity_sha256(
    report: ClinicalRiskOfBiasReport,
) -> str:
    _require_instance(report, ClinicalRiskOfBiasReport, "report")
    return _sha256(report)


def clinical_risk_of_bias_report_envelope(
    report: ClinicalRiskOfBiasReport,
) -> dict[str, Any]:
    value = to_primitive(report)
    if not isinstance(value, dict):
        raise TypeError("serialized risk-of-bias report must be an object")
    return {
        "schema_version": CLINICAL_RISK_OF_BIAS_REPORT_SCHEMA_VERSION,
        "integrity_sha256": clinical_risk_of_bias_report_integrity_sha256(report),
        **value,
    }


def _parse_trial_record(value: Any, path: str) -> ClinicalRiskOfBiasTrialRecord:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasTrialRecord.__dataclass_fields__)
    _exact_fields(data, fields, path)
    data["source_content_hashes"] = _tuple(
        data["source_content_hashes"], f"{path}.source_content_hashes"
    )
    data["citations"] = tuple(
        _parse_citation(item, f"{path}.citations[{index}]")
        for index, item in enumerate(_tuple(data["citations"], f"{path}.citations"))
    )
    data["domains"] = tuple(
        _parse_domain(item, f"{path}.domains[{index}]")
        for index, item in enumerate(_tuple(data["domains"], f"{path}.domains"))
    )
    data["unresolved_concerns"] = _tuple(
        data["unresolved_concerns"], f"{path}.unresolved_concerns"
    )
    try:
        return ClinicalRiskOfBiasTrialRecord(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc


def clinical_risk_of_bias_report_from_dict(
    value: Any,
    path: str = "clinical_risk_of_bias_report",
) -> ClinicalRiskOfBiasReport:
    data = _mapping(value, path)
    fields = set(ClinicalRiskOfBiasReport.__dataclass_fields__)
    _exact_fields(data, {"schema_version", "integrity_sha256", *fields}, path)
    if data.pop("schema_version") != CLINICAL_RISK_OF_BIAS_REPORT_SCHEMA_VERSION:
        raise ClinicalRiskOfBiasError(f"{path}.schema_version is unsupported")
    integrity = _text(data.pop("integrity_sha256"), f"{path}.integrity_sha256")
    _require_sha256(integrity, f"{path}.integrity_sha256")
    data["review"] = _parse_review(data["review"], f"{path}.review")
    data["trials"] = tuple(
        _parse_trial_record(item, f"{path}.trials[{index}]")
        for index, item in enumerate(_tuple(data["trials"], f"{path}.trials"))
    )
    for field_name in (
        "prior_transportability_blockers",
        "resolved_transportability_blockers",
        "remaining_transportability_blockers",
        "assessment_cautions",
        "source_content_hashes",
        "limitations",
    ):
        data[field_name] = _tuple(data[field_name], f"{path}.{field_name}")
    try:
        report = ClinicalRiskOfBiasReport(**data)
    except (TypeError, ValueError) as exc:
        raise ClinicalRiskOfBiasError(f"{path} is invalid") from exc
    if clinical_risk_of_bias_report_integrity_sha256(report) != integrity:
        raise ClinicalRiskOfBiasError(f"{path}.integrity_sha256 mismatch")
    return report


def clinical_risk_of_bias_report_from_json(
    payload: str | bytes,
) -> ClinicalRiskOfBiasReport:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordParseError("risk-of-bias report is not valid JSON") from exc
    return clinical_risk_of_bias_report_from_dict(value)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecordParseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
