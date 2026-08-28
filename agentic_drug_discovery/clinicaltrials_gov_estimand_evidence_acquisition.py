"""Source-bound estimand evidence acquisition for review-ready endpoint pairs.

This module acquires protocol/SAP page cues for the five preregistered estimand
dimensions. It deliberately stops before evidence interpretation, endpoint
equivalence, or any clinical decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from .clinicaltrials_gov_endpoint_estimand_preflight import (
    ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
    READY_FOR_ENDPOINT_ESTIMAND_REVIEW,
    REQUIRED_ESTIMAND_DIMENSIONS,
    SOURCE_COMPLETION_REQUIRED,
    ClinicalTrialsGovEndpointEstimandPreflightPacket,
)
from .clinicaltrials_gov_harmonization_candidates import (
    ClinicalTrialsGovHarmonizationCandidatePacket,
    CrossTrialEndpointCandidate,
)
from .models import SerializableRecord, _require_sha256, _require_text, to_primitive


CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_SPEC_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-estimand-evidence-acquisition-spec.v1"
)
CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_PACKET_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-estimand-evidence-acquisition-packet.v1"
)
CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_POLICY_ID = (
    "adds.source-bound-estimand-evidence-acquisition.v1"
)
CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ANCHOR_POLICY_ID = (
    "adds.estimand-page-cue-anchors.v1"
)

CANDIDATE_PAGES_FOUND = "candidate_pages_found"
NO_CANDIDATE_PAGES_FOUND = "no_candidate_pages_found"
EVIDENCE_CUES_ACQUIRED = "evidence_cues_acquired"
PREFLIGHT_BLOCKED = "preflight_blocked"
_DOCUMENT_ROLES = ("protocol", "sap")
_CUE_STATES = (CANDIDATE_PAGES_FOUND, NO_CANDIDATE_PAGES_FOUND)
_PAIR_ACQUISITION_STATES = (EVIDENCE_CUES_ACQUIRED, PREFLIGHT_BLOCKED)
_PREFLIGHT_ROUTES = (
    SOURCE_COMPLETION_REQUIRED,
    ENDPOINT_IDENTITY_RECONCILIATION_REQUIRED,
    READY_FOR_ENDPOINT_ESTIMAND_REVIEW,
)

_DIMENSION_ANCHORS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "treatment_condition": (
        ("allocation_randomized", re.compile(r"\brandomi[sz](?:ed|ation)\b", re.I)),
        ("comparator_placebo", re.compile(r"\b(?:comparator|placebo)\b", re.I)),
        ("dose_regimen", re.compile(r"\b(?:dose|dosing|regimen)\b", re.I)),
        ("treatment_group", re.compile(r"\btreatment (?:arm|group)\b", re.I)),
    ),
    "population": (
        ("analysis_population", re.compile(r"\banalysis (?:population|set)\b", re.I)),
        ("eligibility", re.compile(r"\b(?:eligibility|inclusion|exclusion)\b", re.I)),
        (
            "intent_to_treat",
            re.compile(r"\b(?:intent(?:ion)?[- ]to[- ]treat|itt|mitt)\b", re.I),
        ),
        ("per_protocol", re.compile(r"\bper[- ]protocol\b", re.I)),
    ),
    "variable": (
        ("change_from_baseline", re.compile(r"\bchange from baseline\b", re.I)),
        ("clinical_endpoint", re.compile(r"\bclinical endpoint\b", re.I)),
        ("efficacy_endpoint", re.compile(r"\befficacy endpoint\b", re.I)),
        ("outcome_measure", re.compile(r"\boutcome measure\b", re.I)),
        ("primary_endpoint", re.compile(r"\bprimary endpoint\b", re.I)),
        ("secondary_endpoint", re.compile(r"\bsecondary endpoint\b", re.I)),
    ),
    "intercurrent_event_strategy": (
        ("discontinuation", re.compile(r"\bdiscontinu(?:ation|ed|ing)\b", re.I)),
        ("intercurrent_event", re.compile(r"\bintercurrent event\b", re.I)),
        ("missing_data", re.compile(r"\bmissing data\b", re.I)),
        ("multiple_imputation", re.compile(r"\bmultiple imputation\b", re.I)),
        ("non_responder", re.compile(r"\bnon[- ]responder\b", re.I)),
        ("observed_cases", re.compile(r"\bobserved cases?\b", re.I)),
        ("rescue_medication", re.compile(r"\brescue medication\b", re.I)),
        ("treatment_failure", re.compile(r"\btreatment failure\b", re.I)),
    ),
    "population_level_summary": (
        ("ancova", re.compile(r"\bancova\b", re.I)),
        ("confidence_interval", re.compile(r"\bconfidence interval\b", re.I)),
        ("hazard_ratio", re.compile(r"\bhazard ratio\b", re.I)),
        ("logistic_regression", re.compile(r"\blogistic regression\b", re.I)),
        ("mean_change", re.compile(r"\bmean change\b", re.I)),
        ("mixed_model", re.compile(r"\b(?:mixed model|mmrm)\b", re.I)),
        ("odds_ratio", re.compile(r"\bodds ratio\b", re.I)),
        ("proportion", re.compile(r"\bproportion\b", re.I)),
        ("risk_ratio", re.compile(r"\brisk ratio\b", re.I)),
    ),
}

_VARIABLE_EXTRA_ANCHORS = (
    "endpoint_title_exact",
    "endpoint_title_token_set",
    "endpoint_time_frame_exact",
)
_ANCHOR_IDS_BY_DIMENSION = {
    dimension: frozenset(anchor_id for anchor_id, _pattern in anchors)
    | (frozenset(_VARIABLE_EXTRA_ANCHORS) if dimension == "variable" else frozenset())
    for dimension, anchors in _DIMENSION_ANCHORS.items()
}
_STOPWORDS = frozenset(
    {
        "and",
        "assessment",
        "baseline",
        "change",
        "clinical",
        "day",
        "days",
        "during",
        "endpoint",
        "from",
        "measure",
        "number",
        "participants",
        "percentage",
        "period",
        "score",
        "study",
        "the",
        "time",
        "week",
        "weeks",
        "with",
    }
)

_REQUIRED_LIMITATIONS = (
    (
        "The packet is valid only for the exact candidate graph, endpoint/estimand "
        "preflight, registry records, and protocol/SAP bytes identified by SHA-256."
    ),
    (
        "Candidate pages are lexical retrieval cues, not verified evidence, semantic "
        "interpretations, or determinations that an estimand dimension is resolved."
    ),
    (
        "PDF text and excerpts are intentionally absent; page hashes support local "
        "replay without redistributing source-document payloads."
    ),
    (
        "Preflight-blocked pairs remain blocked and are not automatically excluded, "
        "repaired, or promoted by document acquisition."
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


class ClinicalTrialsGovEstimandEvidenceAcquisitionError(ValueError):
    """Raised when evidence acquisition cannot compile or replay exactly."""


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


def _require_positive_int(value: Any, field_name: str) -> None:
    _require_non_negative_int(value, field_name)
    if value == 0:
        raise ValueError(f"{field_name} must be positive")


def _require_nct_id(value: Any, field_name: str = "nct_id") -> None:
    if not isinstance(value, str) or re.fullmatch(r"NCT[0-9]{8}", value) is None:
        raise ValueError(f"{field_name} must use canonical NCT######## form")


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _document_locator(nct_id: str, filename: str) -> str:
    return (
        f"https://cdn.clinicaltrials.gov/large-docs/{nct_id[-2:]}/"
        f"{nct_id}/{filename}"
    )


@dataclass(frozen=True, slots=True)
class EstimandEvidenceDocumentBinding(SerializableRecord):
    document_id: str
    nct_id: str
    filename: str
    document_roles: tuple[str, ...]
    source_label: str
    source_locator: str
    source_document_date: str
    source_upload_date: str
    expected_size_bytes: int
    source_content_sha256: str

    def __post_init__(self) -> None:
        _require_nct_id(self.nct_id)
        for field_name in (
            "document_id",
            "filename",
            "source_label",
            "source_locator",
            "source_document_date",
            "source_upload_date",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.document_id != f"{self.nct_id}:{self.filename}":
            raise ValueError("document_id must bind nct_id and filename")
        if not self.filename.endswith(".pdf") or "/" in self.filename:
            raise ValueError("filename must be a basename ending in .pdf")
        roles = _sorted_unique_text(self.document_roles, "document_roles")
        if not roles or any(item not in _DOCUMENT_ROLES for item in roles):
            raise ValueError("document_roles contains an unsupported role")
        if self.source_locator != _document_locator(self.nct_id, self.filename):
            raise ValueError("source_locator is not the canonical ClinicalTrials.gov URL")
        if urlparse(self.source_locator).scheme != "https":
            raise ValueError("source_locator must use HTTPS")
        try:
            if date.fromisoformat(self.source_document_date).isoformat() != (
                self.source_document_date
            ):
                raise ValueError
        except ValueError as exc:
            raise ValueError("source_document_date must use YYYY-MM-DD") from exc
        try:
            datetime.strptime(self.source_upload_date, "%Y-%m-%dT%H:%M")
        except ValueError as exc:
            raise ValueError("source_upload_date must use YYYY-MM-DDTHH:MM") from exc
        _require_positive_int(self.expected_size_bytes, "expected_size_bytes")
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        object.__setattr__(self, "document_roles", roles)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovEstimandEvidenceAcquisitionSpec(SerializableRecord):
    packet_id: str
    candidate_packet_sha256: str
    preflight_packet_sha256: str
    document_bindings: tuple[EstimandEvidenceDocumentBinding, ...]
    max_document_bytes: int
    max_candidate_pages_per_dimension: int
    required_estimand_dimensions: tuple[str, ...] = REQUIRED_ESTIMAND_DIMENSIONS
    anchor_policy_id: str = CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ANCHOR_POLICY_ID
    policy_id: str = CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_POLICY_ID

    def __post_init__(self) -> None:
        _require_text(self.packet_id, "packet_id")
        _require_sha256(self.candidate_packet_sha256, "candidate_packet_sha256")
        _require_sha256(self.preflight_packet_sha256, "preflight_packet_sha256")
        bindings = _tuple(self.document_bindings, "document_bindings")
        if any(not isinstance(item, EstimandEvidenceDocumentBinding) for item in bindings):
            raise TypeError("document_bindings contains an invalid binding")
        if bindings != tuple(sorted(bindings, key=lambda item: item.document_id)):
            raise ValueError("document_bindings must use canonical document_id order")
        if not bindings or len({item.document_id for item in bindings}) != len(bindings):
            raise ValueError("document_bindings must contain unique documents")
        _require_positive_int(self.max_document_bytes, "max_document_bytes")
        if any(item.expected_size_bytes > self.max_document_bytes for item in bindings):
            raise ValueError("a document exceeds max_document_bytes")
        _require_positive_int(
            self.max_candidate_pages_per_dimension,
            "max_candidate_pages_per_dimension",
        )
        if self.max_candidate_pages_per_dimension > 20:
            raise ValueError("max_candidate_pages_per_dimension exceeds 20")
        dimensions = _text_tuple(
            self.required_estimand_dimensions, "required_estimand_dimensions"
        )
        if dimensions != REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("required estimand dimensions were rebound")
        if self.anchor_policy_id != CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ANCHOR_POLICY_ID:
            raise ValueError("unsupported anchor_policy_id")
        if self.policy_id != CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_POLICY_ID:
            raise ValueError("unsupported evidence-acquisition policy_id")
        object.__setattr__(self, "document_bindings", bindings)
        object.__setattr__(self, "required_estimand_dimensions", dimensions)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class AcquiredEstimandSourceDocument(SerializableRecord):
    document_id: str
    nct_id: str
    filename: str
    document_roles: tuple[str, ...]
    source_label: str
    source_locator: str
    source_document_date: str
    source_upload_date: str
    source_content_sha256: str
    size_bytes: int
    page_count: int
    text_bearing_page_count: int
    registry_inventory_verified: bool
    exact_bytes_verified: bool
    pdf_parse_verified: bool

    def __post_init__(self) -> None:
        for field_name in ("size_bytes", "page_count", "text_bearing_page_count"):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.size_bytes == 0 or self.page_count == 0:
            raise ValueError("acquired document must contain bytes and pages")
        validated_binding = EstimandEvidenceDocumentBinding(
            document_id=self.document_id,
            nct_id=self.nct_id,
            filename=self.filename,
            document_roles=self.document_roles,
            source_label=self.source_label,
            source_locator=self.source_locator,
            source_document_date=self.source_document_date,
            source_upload_date=self.source_upload_date,
            expected_size_bytes=self.size_bytes,
            source_content_sha256=self.source_content_sha256,
        )
        if self.text_bearing_page_count > self.page_count:
            raise ValueError("text_bearing_page_count exceeds page_count")
        for field_name in (
            "registry_inventory_verified",
            "exact_bytes_verified",
            "pdf_parse_verified",
        ):
            _require_bool(getattr(self, field_name), field_name)
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be true")
        object.__setattr__(self, "document_roles", validated_binding.document_roles)


@dataclass(frozen=True, slots=True)
class EstimandEvidencePageCue(SerializableRecord):
    retrieval_rank: int
    document_id: str
    source_content_sha256: str
    page_number: int
    normalized_page_text_sha256: str
    matched_anchor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_positive_int(self.retrieval_rank, "retrieval_rank")
        _require_text(self.document_id, "document_id")
        _require_sha256(self.source_content_sha256, "source_content_sha256")
        _require_positive_int(self.page_number, "page_number")
        _require_sha256(
            self.normalized_page_text_sha256, "normalized_page_text_sha256"
        )
        anchors = _sorted_unique_text(self.matched_anchor_ids, "matched_anchor_ids")
        if not anchors:
            raise ValueError("matched_anchor_ids must not be empty")
        object.__setattr__(self, "matched_anchor_ids", anchors)


@dataclass(frozen=True, slots=True)
class EndpointEstimandEvidenceCue(SerializableRecord):
    evidence_id: str
    endpoint_candidate_id: str
    nct_id: str
    source_record_sha256: str
    estimand_dimension: str
    cue_state: str
    candidate_pages: tuple[EstimandEvidencePageCue, ...]
    source_excerpt_included: bool
    semantic_sufficiency_assessed: bool
    human_review_required: bool

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "endpoint_candidate_id", "estimand_dimension"):
            _require_text(getattr(self, field_name), field_name)
        _require_nct_id(self.nct_id)
        _require_sha256(self.source_record_sha256, "source_record_sha256")
        if self.estimand_dimension not in REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("unsupported estimand_dimension")
        if self.evidence_id != (
            f"{self.endpoint_candidate_id}:estimand-evidence:{self.estimand_dimension}"
        ):
            raise ValueError("evidence_id does not bind endpoint and dimension")
        if self.cue_state not in _CUE_STATES:
            raise ValueError("unsupported cue_state")
        pages = _tuple(self.candidate_pages, "candidate_pages")
        if any(not isinstance(item, EstimandEvidencePageCue) for item in pages):
            raise TypeError("candidate_pages contains an invalid cue")
        if tuple(item.retrieval_rank for item in pages) != tuple(
            range(1, len(pages) + 1)
        ):
            raise ValueError("candidate page ranks must be contiguous")
        identities = [(item.document_id, item.page_number) for item in pages]
        if len(identities) != len(set(identities)):
            raise ValueError("candidate page identities must be unique")
        if (self.cue_state == CANDIDATE_PAGES_FOUND) != bool(pages):
            raise ValueError("cue_state does not match candidate pages")
        allowed_anchors = _ANCHOR_IDS_BY_DIMENSION[self.estimand_dimension]
        if any(
            not set(page.matched_anchor_ids) <= allowed_anchors for page in pages
        ):
            raise ValueError("candidate page contains an unsupported dimension anchor")
        for field_name in (
            "source_excerpt_included",
            "semantic_sufficiency_assessed",
            "human_review_required",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if self.source_excerpt_included or self.semantic_sufficiency_assessed:
            raise ValueError("payload or semantic sufficiency must remain absent")
        if not self.human_review_required:
            raise ValueError("human_review_required must remain true")
        object.__setattr__(self, "candidate_pages", pages)


@dataclass(frozen=True, slots=True)
class PairEstimandEvidenceAcquisition(SerializableRecord):
    pair_id: str
    left_endpoint_candidate_id: str
    right_endpoint_candidate_id: str
    preflight_review_route: str
    acquisition_state: str
    evidence_ids: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    human_review_required: bool
    reviewer_approval_performed: bool
    estimand_equivalence_approved: bool

    def __post_init__(self) -> None:
        for field_name in (
            "pair_id",
            "left_endpoint_candidate_id",
            "right_endpoint_candidate_id",
            "preflight_review_route",
            "acquisition_state",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.acquisition_state not in _PAIR_ACQUISITION_STATES:
            raise ValueError("unsupported acquisition_state")
        if self.preflight_review_route not in _PREFLIGHT_ROUTES:
            raise ValueError("unsupported preflight_review_route")
        evidence_ids = _sorted_unique_text(self.evidence_ids, "evidence_ids")
        blocker_codes = _sorted_unique_text(self.blocker_codes, "blocker_codes")
        is_ready = self.preflight_review_route == READY_FOR_ENDPOINT_ESTIMAND_REVIEW
        if is_ready:
            if self.acquisition_state != EVIDENCE_CUES_ACQUIRED:
                raise ValueError("review-ready pair must acquire evidence cues")
            if blocker_codes or len(evidence_ids) != 2 * len(REQUIRED_ESTIMAND_DIMENSIONS):
                raise ValueError("review-ready pair evidence coverage is incomplete")
            expected_evidence_ids = tuple(
                sorted(
                    f"{endpoint_id}:estimand-evidence:{dimension}"
                    for endpoint_id in (
                        self.left_endpoint_candidate_id,
                        self.right_endpoint_candidate_id,
                    )
                    for dimension in REQUIRED_ESTIMAND_DIMENSIONS
                )
            )
            if evidence_ids != expected_evidence_ids:
                raise ValueError("pair evidence ids do not bind both endpoint candidates")
        elif (
            self.acquisition_state != PREFLIGHT_BLOCKED
            or evidence_ids
            or not blocker_codes
        ):
            raise ValueError(
                "preflight-blocked pair must retain blockers and cannot acquire cues"
            )
        _require_bool(self.human_review_required, "human_review_required")
        _require_bool(self.reviewer_approval_performed, "reviewer_approval_performed")
        _require_bool(self.estimand_equivalence_approved, "estimand_equivalence_approved")
        if not self.human_review_required:
            raise ValueError("human_review_required must remain true")
        if self.reviewer_approval_performed or self.estimand_equivalence_approved:
            raise ValueError("review approval must remain false")
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(self, "blocker_codes", blocker_codes)


@dataclass(frozen=True, slots=True)
class EstimandDimensionCueCount(SerializableRecord):
    estimand_dimension: str
    evidence_record_count: int
    candidate_pages_found_count: int
    no_candidate_pages_found_count: int

    def __post_init__(self) -> None:
        if self.estimand_dimension not in REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("unsupported estimand_dimension")
        for field_name in (
            "evidence_record_count",
            "candidate_pages_found_count",
            "no_candidate_pages_found_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.evidence_record_count != (
            self.candidate_pages_found_count + self.no_candidate_pages_found_count
        ):
            raise ValueError("dimension cue counts do not partition evidence records")


@dataclass(frozen=True, slots=True)
class ClinicalTrialsGovEstimandEvidenceAcquisitionPacket(SerializableRecord):
    packet_id: str
    policy_id: str
    anchor_policy_id: str
    spec_sha256: str
    candidate_packet_id: str
    candidate_packet_sha256: str
    preflight_packet_id: str
    preflight_packet_sha256: str
    required_estimand_dimensions: tuple[str, ...]
    source_documents: tuple[AcquiredEstimandSourceDocument, ...]
    evidence_cues: tuple[EndpointEstimandEvidenceCue, ...]
    pair_acquisitions: tuple[PairEstimandEvidenceAcquisition, ...]
    dimension_counts: tuple[EstimandDimensionCueCount, ...]
    source_document_count: int
    source_document_page_count: int
    source_document_text_bearing_page_count: int
    pair_count: int
    review_ready_pair_count: int
    preflight_blocked_pair_count: int
    unique_review_ready_endpoint_count: int
    evidence_record_count: int
    candidate_page_cue_count: int
    exact_registry_inventory_verified: bool
    exact_document_bytes_verified: bool
    source_payload_included: bool
    source_excerpt_included: bool
    semantic_sufficiency_assessed: bool
    reviewer_approval_performed: bool
    endpoint_equivalence_approved: bool
    estimand_equivalence_approved: bool
    benefit_risk_synthesis_performed: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "packet_id",
            "candidate_packet_id",
            "preflight_packet_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_POLICY_ID:
            raise ValueError("unsupported evidence-acquisition policy_id")
        if self.anchor_policy_id != CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ANCHOR_POLICY_ID:
            raise ValueError("unsupported anchor_policy_id")
        for field_name in (
            "spec_sha256",
            "candidate_packet_sha256",
            "preflight_packet_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        dimensions = _text_tuple(
            self.required_estimand_dimensions, "required_estimand_dimensions"
        )
        if dimensions != REQUIRED_ESTIMAND_DIMENSIONS:
            raise ValueError("required estimand dimensions were rebound")
        documents = _tuple(self.source_documents, "source_documents")
        if any(not isinstance(item, AcquiredEstimandSourceDocument) for item in documents):
            raise TypeError("source_documents contains an invalid document")
        if documents != tuple(sorted(documents, key=lambda item: item.document_id)):
            raise ValueError("source_documents must use canonical order")
        if len({item.document_id for item in documents}) != len(documents):
            raise ValueError("source document ids must be unique")
        cues = _tuple(self.evidence_cues, "evidence_cues")
        if any(not isinstance(item, EndpointEstimandEvidenceCue) for item in cues):
            raise TypeError("evidence_cues contains an invalid cue")
        if cues != tuple(sorted(cues, key=lambda item: item.evidence_id)):
            raise ValueError("evidence_cues must use canonical order")
        if len({item.evidence_id for item in cues}) != len(cues):
            raise ValueError("evidence cue ids must be unique")
        pairs = _tuple(self.pair_acquisitions, "pair_acquisitions")
        if any(not isinstance(item, PairEstimandEvidenceAcquisition) for item in pairs):
            raise TypeError("pair_acquisitions contains an invalid record")
        if pairs != tuple(sorted(pairs, key=lambda item: item.pair_id)):
            raise ValueError("pair_acquisitions must use canonical order")
        if len({item.pair_id for item in pairs}) != len(pairs):
            raise ValueError("pair acquisition ids must be unique")
        counts = _tuple(self.dimension_counts, "dimension_counts")
        if any(not isinstance(item, EstimandDimensionCueCount) for item in counts):
            raise TypeError("dimension_counts contains an invalid count")
        if tuple(item.estimand_dimension for item in counts) != dimensions:
            raise ValueError("dimension_counts must follow preregistered dimension order")
        integer_fields = (
            "source_document_count",
            "source_document_page_count",
            "source_document_text_bearing_page_count",
            "pair_count",
            "review_ready_pair_count",
            "preflight_blocked_pair_count",
            "unique_review_ready_endpoint_count",
            "evidence_record_count",
            "candidate_page_cue_count",
        )
        for field_name in integer_fields:
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.source_document_count != len(documents):
            raise ValueError("source_document_count mismatch")
        if self.source_document_page_count != sum(item.page_count for item in documents):
            raise ValueError("source_document_page_count mismatch")
        if self.source_document_text_bearing_page_count != sum(
            item.text_bearing_page_count for item in documents
        ):
            raise ValueError("source_document_text_bearing_page_count mismatch")
        if self.pair_count != len(pairs):
            raise ValueError("pair_count mismatch")
        if self.review_ready_pair_count != sum(
            item.acquisition_state == EVIDENCE_CUES_ACQUIRED for item in pairs
        ):
            raise ValueError("review_ready_pair_count mismatch")
        if self.preflight_blocked_pair_count != sum(
            item.acquisition_state == PREFLIGHT_BLOCKED for item in pairs
        ):
            raise ValueError("preflight_blocked_pair_count mismatch")
        if self.pair_count != self.review_ready_pair_count + self.preflight_blocked_pair_count:
            raise ValueError("pair acquisition states do not partition pairs")
        endpoint_ids = {item.endpoint_candidate_id for item in cues}
        if self.unique_review_ready_endpoint_count != len(endpoint_ids):
            raise ValueError("unique_review_ready_endpoint_count mismatch")
        if self.evidence_record_count != len(cues):
            raise ValueError("evidence_record_count mismatch")
        if len(cues) != len(endpoint_ids) * len(dimensions):
            raise ValueError("endpoint evidence dimension coverage is incomplete")
        if self.candidate_page_cue_count != sum(
            len(item.candidate_pages) for item in cues
        ):
            raise ValueError("candidate_page_cue_count mismatch")
        count_by_dimension = Counter(item.estimand_dimension for item in cues)
        found_by_dimension = Counter(
            item.estimand_dimension
            for item in cues
            if item.cue_state == CANDIDATE_PAGES_FOUND
        )
        for item in counts:
            if (
                item.evidence_record_count != count_by_dimension[item.estimand_dimension]
                or item.candidate_pages_found_count
                != found_by_dimension[item.estimand_dimension]
            ):
                raise ValueError("dimension_counts mismatch")
        evidence_ids = {item.evidence_id for item in cues}
        if any(not set(item.evidence_ids) <= evidence_ids for item in pairs):
            raise ValueError("pair acquisition references unknown evidence")
        document_by_id = {item.document_id: item for item in documents}
        for cue in cues:
            for page in cue.candidate_pages:
                document = document_by_id.get(page.document_id)
                if document is None:
                    raise ValueError("evidence page references an unknown document")
                if (
                    document.nct_id != cue.nct_id
                    or document.source_content_sha256 != page.source_content_sha256
                    or page.page_number > document.page_count
                ):
                    raise ValueError("evidence page does not match its source document")
        endpoint_bindings = {
            (
                item.endpoint_candidate_id,
                item.nct_id,
                item.source_record_sha256,
            )
            for item in cues
        }
        if len(endpoint_bindings) != len(endpoint_ids):
            raise ValueError("endpoint evidence identity changed across dimensions")
        true_fields = (
            "exact_registry_inventory_verified",
            "exact_document_bytes_verified",
        )
        false_fields = (
            "source_payload_included",
            "source_excerpt_included",
            "semantic_sufficiency_assessed",
            "reviewer_approval_performed",
            "endpoint_equivalence_approved",
            "estimand_equivalence_approved",
            "benefit_risk_synthesis_performed",
            "treatment_choice_inferred",
        )
        for field_name in (*true_fields, *false_fields):
            _require_bool(getattr(self, field_name), field_name)
        if any(not getattr(self, item) for item in true_fields):
            raise ValueError("required acquisition assurance is false")
        if any(getattr(self, item) for item in false_fields):
            raise ValueError("a forbidden payload, approval, or inference was enabled")
        limitations = _text_tuple(self.limitations, "limitations")
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("evidence-acquisition limitations were rebound")
        object.__setattr__(self, "required_estimand_dimensions", dimensions)
        object.__setattr__(self, "source_documents", documents)
        object.__setattr__(self, "evidence_cues", cues)
        object.__setattr__(self, "pair_acquisitions", pairs)
        object.__setattr__(self, "dimension_counts", counts)
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class _ParsedDocument:
    binding: EstimandEvidenceDocumentBinding
    page_texts: tuple[str, ...]
    public_record: AcquiredEstimandSourceDocument


def _load_registry_json(payload: bytes, nct_id: str) -> dict[str, Any]:
    try:
        value = _load_json(payload.decode("utf-8"), f"{nct_id} registry source")
    except (UnicodeDecodeError, ClinicalTrialsGovEstimandEvidenceAcquisitionError) as exc:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{nct_id} registry source is invalid JSON"
        ) from exc
    observed = (
        value.get("protocolSection", {})
        .get("identificationModule", {})
        .get("nctId")
    )
    if observed != nct_id:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{nct_id} registry source identity mismatch"
        )
    return value


def _registry_document_inventory(value: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    documents = (
        value.get("documentSection", {})
        .get("largeDocumentModule", {})
        .get("largeDocs", [])
    )
    if not isinstance(documents, list) or any(not isinstance(item, dict) for item in documents):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "registry large-document inventory is malformed"
        )
    relevant = tuple(
        item for item in documents if item.get("hasProtocol") or item.get("hasSap")
    )
    return relevant


def _inventory_identity(nct_id: str, item: Mapping[str, Any]) -> tuple[Any, ...]:
    roles = tuple(
        role
        for role, field_name in (("protocol", "hasProtocol"), ("sap", "hasSap"))
        if item.get(field_name) is True
    )
    return (
        f"{nct_id}:{item.get('filename')}",
        roles,
        item.get("label"),
        item.get("date"),
        item.get("uploadDate"),
        item.get("size"),
    )


def _binding_inventory_identity(
    binding: EstimandEvidenceDocumentBinding,
) -> tuple[Any, ...]:
    return (
        binding.document_id,
        binding.document_roles,
        binding.source_label,
        binding.source_document_date,
        binding.source_upload_date,
        binding.expected_size_bytes,
    )


def _parse_document(
    binding: EstimandEvidenceDocumentBinding,
    payload: bytes,
    max_document_bytes: int,
) -> _ParsedDocument:
    if len(payload) > max_document_bytes:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} exceeds max_document_bytes"
        )
    if len(payload) != binding.expected_size_bytes:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} byte size mismatch"
        )
    observed_hash = hashlib.sha256(payload).hexdigest()
    if observed_hash != binding.source_content_sha256:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} SHA-256 mismatch"
        )
    if not payload.startswith(b"%PDF-"):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} is not a PDF"
        )
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(payload), strict=True)
        page_texts = tuple(
            _normalize_text(page.extract_text() or "") for page in reader.pages
        )
    except Exception as exc:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} PDF parse failed"
        ) from exc
    if not page_texts:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{binding.document_id} has no pages"
        )
    return _ParsedDocument(
        binding=binding,
        page_texts=page_texts,
        public_record=AcquiredEstimandSourceDocument(
            document_id=binding.document_id,
            nct_id=binding.nct_id,
            filename=binding.filename,
            document_roles=binding.document_roles,
            source_label=binding.source_label,
            source_locator=binding.source_locator,
            source_document_date=binding.source_document_date,
            source_upload_date=binding.source_upload_date,
            source_content_sha256=binding.source_content_sha256,
            size_bytes=len(payload),
            page_count=len(page_texts),
            text_bearing_page_count=sum(bool(item) for item in page_texts),
            registry_inventory_verified=True,
            exact_bytes_verified=True,
            pdf_parse_verified=True,
        ),
    )


def _endpoint_title_tokens(endpoint: CrossTrialEndpointCandidate) -> tuple[str, ...]:
    if not endpoint.title:
        return ()
    tokens = {
        item
        for item in re.findall(r"[a-z0-9]+", endpoint.title.casefold())
        if len(item) >= 4 and item not in _STOPWORDS and not item.isdigit()
    }
    return tuple(sorted(tokens))


def _page_anchors(
    endpoint: CrossTrialEndpointCandidate,
    dimension: str,
    text: str,
) -> tuple[str, ...]:
    anchors = {
        anchor_id
        for anchor_id, pattern in _DIMENSION_ANCHORS[dimension]
        if pattern.search(text)
    }
    if dimension == "variable":
        normalized_title = _normalize_text(endpoint.title or "")
        if len(normalized_title) >= 8 and normalized_title in text:
            anchors.add("endpoint_title_exact")
        title_tokens = _endpoint_title_tokens(endpoint)
        if len(title_tokens) >= 2 and sum(token in text for token in title_tokens) >= 2:
            anchors.add("endpoint_title_token_set")
        normalized_time_frame = _normalize_text(endpoint.time_frame or "")
        if len(normalized_time_frame) >= 4 and normalized_time_frame in text:
            anchors.add("endpoint_time_frame_exact")
    return tuple(sorted(anchors))


def _evidence_cue(
    endpoint: CrossTrialEndpointCandidate,
    dimension: str,
    documents: Sequence[_ParsedDocument],
    max_pages: int,
) -> EndpointEstimandEvidenceCue:
    scored: list[tuple[int, int, str, int, str, tuple[str, ...]]] = []
    for document in documents:
        for page_number, text in enumerate(document.page_texts, start=1):
            anchors = _page_anchors(endpoint, dimension, text)
            if not anchors:
                continue
            endpoint_specific = sum(item in _VARIABLE_EXTRA_ANCHORS for item in anchors)
            scored.append(
                (
                    endpoint_specific,
                    len(anchors),
                    document.binding.document_id,
                    page_number,
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    anchors,
                )
            )
    selected = sorted(
        scored,
        key=lambda item: (-item[0], -item[1], item[2], item[3]),
    )[:max_pages]
    pages = tuple(
        EstimandEvidencePageCue(
            retrieval_rank=rank,
            document_id=item[2],
            source_content_sha256=next(
                document.binding.source_content_sha256
                for document in documents
                if document.binding.document_id == item[2]
            ),
            page_number=item[3],
            normalized_page_text_sha256=item[4],
            matched_anchor_ids=item[5],
        )
        for rank, item in enumerate(selected, start=1)
    )
    return EndpointEstimandEvidenceCue(
        evidence_id=(
            f"{endpoint.endpoint_candidate_id}:estimand-evidence:{dimension}"
        ),
        endpoint_candidate_id=endpoint.endpoint_candidate_id,
        nct_id=endpoint.nct_id,
        source_record_sha256=endpoint.source_record_sha256,
        estimand_dimension=dimension,
        cue_state=CANDIDATE_PAGES_FOUND if pages else NO_CANDIDATE_PAGES_FOUND,
        candidate_pages=pages,
        source_excerpt_included=False,
        semantic_sufficiency_assessed=False,
        human_review_required=True,
    )


def compile_clinicaltrials_gov_estimand_evidence_acquisition(
    spec: ClinicalTrialsGovEstimandEvidenceAcquisitionSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    preflight_packet: ClinicalTrialsGovEndpointEstimandPreflightPacket,
    registry_sources: Mapping[str, bytes],
    source_documents: Mapping[str, bytes],
) -> ClinicalTrialsGovEstimandEvidenceAcquisitionPacket:
    """Acquire bounded page cues while preserving every human review gate."""

    if not isinstance(spec, ClinicalTrialsGovEstimandEvidenceAcquisitionSpec):
        raise TypeError("spec must be an evidence-acquisition spec")
    if not isinstance(candidate_packet, ClinicalTrialsGovHarmonizationCandidatePacket):
        raise TypeError("candidate_packet must be a harmonization candidate packet")
    if not isinstance(preflight_packet, ClinicalTrialsGovEndpointEstimandPreflightPacket):
        raise TypeError("preflight_packet must be an endpoint/estimand preflight packet")
    if spec.candidate_packet_sha256 != candidate_packet.fingerprint:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "candidate packet fingerprint does not match spec"
        )
    if spec.preflight_packet_sha256 != preflight_packet.fingerprint:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "preflight packet fingerprint does not match spec"
        )
    if (
        preflight_packet.candidate_packet_id != candidate_packet.packet_id
        or preflight_packet.candidate_packet_sha256 != candidate_packet.fingerprint
    ):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "preflight packet was rebound to a different candidate graph"
        )
    binding_nct_ids = {item.nct_id for item in spec.document_bindings}
    expected_nct_ids = {item.nct_id for item in preflight_packet.source_bindings}
    if binding_nct_ids != expected_nct_ids or set(registry_sources) != expected_nct_ids:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "registry/document NCT coverage does not match preflight"
        )
    if set(source_documents) != {item.document_id for item in spec.document_bindings}:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "source document identities do not match spec"
        )
    source_binding_by_nct = {
        item.nct_id: item for item in preflight_packet.source_bindings
    }
    bindings_by_nct: dict[str, list[EstimandEvidenceDocumentBinding]] = {
        nct_id: [] for nct_id in expected_nct_ids
    }
    for binding in spec.document_bindings:
        bindings_by_nct[binding.nct_id].append(binding)
    for nct_id in sorted(expected_nct_ids):
        payload = registry_sources[nct_id]
        expected_hash = source_binding_by_nct[nct_id].source_content_hash_sha256
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
                f"{nct_id} registry source SHA-256 mismatch"
            )
        registry = _load_registry_json(payload, nct_id)
        observed = tuple(
            sorted(
                (_inventory_identity(nct_id, item) for item in _registry_document_inventory(registry)),
                key=lambda item: item[0],
            )
        )
        expected = tuple(
            sorted(
                (_binding_inventory_identity(item) for item in bindings_by_nct[nct_id]),
                key=lambda item: item[0],
            )
        )
        if observed != expected:
            raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
                f"{nct_id} protocol/SAP inventory does not match spec"
            )
    parsed_documents = tuple(
        _parse_document(
            binding,
            source_documents[binding.document_id],
            spec.max_document_bytes,
        )
        for binding in spec.document_bindings
    )
    parsed_by_nct: dict[str, tuple[_ParsedDocument, ...]] = {
        nct_id: tuple(item for item in parsed_documents if item.binding.nct_id == nct_id)
        for nct_id in expected_nct_ids
    }
    endpoint_by_id = {
        item.endpoint_candidate_id: item for item in candidate_packet.endpoint_candidates
    }
    ready_endpoint_ids = tuple(
        sorted(
            {
                endpoint_id
                for pair in preflight_packet.pair_preflights
                if pair.review_route == READY_FOR_ENDPOINT_ESTIMAND_REVIEW
                for endpoint_id in (
                    pair.left_endpoint_candidate_id,
                    pair.right_endpoint_candidate_id,
                )
            }
        )
    )
    try:
        ready_endpoints = tuple(endpoint_by_id[item] for item in ready_endpoint_ids)
    except KeyError as exc:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "preflight references an unknown endpoint candidate"
        ) from exc
    evidence_cues = tuple(
        sorted(
            (
                _evidence_cue(
                    endpoint,
                    dimension,
                    parsed_by_nct[endpoint.nct_id],
                    spec.max_candidate_pages_per_dimension,
                )
                for endpoint in ready_endpoints
                for dimension in REQUIRED_ESTIMAND_DIMENSIONS
            ),
            key=lambda item: item.evidence_id,
        )
    )
    evidence_id_by_endpoint_dimension = {
        (item.endpoint_candidate_id, item.estimand_dimension): item.evidence_id
        for item in evidence_cues
    }
    pair_acquisitions = tuple(
        PairEstimandEvidenceAcquisition(
            pair_id=pair.pair_id,
            left_endpoint_candidate_id=pair.left_endpoint_candidate_id,
            right_endpoint_candidate_id=pair.right_endpoint_candidate_id,
            preflight_review_route=pair.review_route,
            acquisition_state=(
                EVIDENCE_CUES_ACQUIRED
                if pair.review_route == READY_FOR_ENDPOINT_ESTIMAND_REVIEW
                else PREFLIGHT_BLOCKED
            ),
            evidence_ids=(
                tuple(
                    sorted(
                        evidence_id_by_endpoint_dimension[(endpoint_id, dimension)]
                        for endpoint_id in (
                            pair.left_endpoint_candidate_id,
                            pair.right_endpoint_candidate_id,
                        )
                        for dimension in REQUIRED_ESTIMAND_DIMENSIONS
                    )
                )
                if pair.review_route == READY_FOR_ENDPOINT_ESTIMAND_REVIEW
                else ()
            ),
            blocker_codes=pair.blocker_codes,
            human_review_required=True,
            reviewer_approval_performed=False,
            estimand_equivalence_approved=False,
        )
        for pair in preflight_packet.pair_preflights
    )
    dimension_counts = tuple(
        EstimandDimensionCueCount(
            estimand_dimension=dimension,
            evidence_record_count=sum(
                item.estimand_dimension == dimension for item in evidence_cues
            ),
            candidate_pages_found_count=sum(
                item.estimand_dimension == dimension
                and item.cue_state == CANDIDATE_PAGES_FOUND
                for item in evidence_cues
            ),
            no_candidate_pages_found_count=sum(
                item.estimand_dimension == dimension
                and item.cue_state == NO_CANDIDATE_PAGES_FOUND
                for item in evidence_cues
            ),
        )
        for dimension in REQUIRED_ESTIMAND_DIMENSIONS
    )
    documents = tuple(item.public_record for item in parsed_documents)
    return ClinicalTrialsGovEstimandEvidenceAcquisitionPacket(
        packet_id=spec.packet_id,
        policy_id=spec.policy_id,
        anchor_policy_id=spec.anchor_policy_id,
        spec_sha256=spec.fingerprint,
        candidate_packet_id=candidate_packet.packet_id,
        candidate_packet_sha256=candidate_packet.fingerprint,
        preflight_packet_id=preflight_packet.packet_id,
        preflight_packet_sha256=preflight_packet.fingerprint,
        required_estimand_dimensions=REQUIRED_ESTIMAND_DIMENSIONS,
        source_documents=documents,
        evidence_cues=evidence_cues,
        pair_acquisitions=pair_acquisitions,
        dimension_counts=dimension_counts,
        source_document_count=len(documents),
        source_document_page_count=sum(item.page_count for item in documents),
        source_document_text_bearing_page_count=sum(
            item.text_bearing_page_count for item in documents
        ),
        pair_count=len(pair_acquisitions),
        review_ready_pair_count=sum(
            item.acquisition_state == EVIDENCE_CUES_ACQUIRED
            for item in pair_acquisitions
        ),
        preflight_blocked_pair_count=sum(
            item.acquisition_state == PREFLIGHT_BLOCKED for item in pair_acquisitions
        ),
        unique_review_ready_endpoint_count=len(ready_endpoint_ids),
        evidence_record_count=len(evidence_cues),
        candidate_page_cue_count=sum(
            len(item.candidate_pages) for item in evidence_cues
        ),
        exact_registry_inventory_verified=True,
        exact_document_bytes_verified=True,
        source_payload_included=False,
        source_excerpt_included=False,
        semantic_sufficiency_assessed=False,
        reviewer_approval_performed=False,
        endpoint_equivalence_approved=False,
        estimand_equivalence_approved=False,
        benefit_risk_synthesis_performed=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinicaltrials_gov_estimand_evidence_acquisition(
    spec: ClinicalTrialsGovEstimandEvidenceAcquisitionSpec,
    candidate_packet: ClinicalTrialsGovHarmonizationCandidatePacket,
    preflight_packet: ClinicalTrialsGovEndpointEstimandPreflightPacket,
    registry_sources: Mapping[str, bytes],
    source_documents: Mapping[str, bytes],
    packet: ClinicalTrialsGovEstimandEvidenceAcquisitionPacket,
) -> tuple[str, ...]:
    try:
        rebuilt = compile_clinicaltrials_gov_estimand_evidence_acquisition(
            spec,
            candidate_packet,
            preflight_packet,
            registry_sources,
            source_documents,
        )
    except (ClinicalTrialsGovEstimandEvidenceAcquisitionError, TypeError, ValueError):
        return ("clinicaltrials_gov_estimand_evidence_acquisition_recompile_failed",)
    if rebuilt != packet:
        return ("clinicaltrials_gov_estimand_evidence_acquisition_packet_mismatch",)
    return ()


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{path} must be an object"
        )
    return dict(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalTrialsGovEstimandEvidenceAcquisitionError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"invalid {label} JSON: {exc}"
        ) from exc
    return _mapping(value, label)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected: set[str]) -> dict[str, Any]:
    data = _mapping(value, path)
    if set(data) != expected:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            f"{path} must contain exactly {sorted(expected)}"
        )
    return data


def _document_binding_from_dict(
    value: Any, path: str
) -> EstimandEvidenceDocumentBinding:
    data = _record(value, path, _field_names(EstimandEvidenceDocumentBinding))
    data["document_roles"] = tuple(_tuple(data["document_roles"], "document_roles"))
    return EstimandEvidenceDocumentBinding(**data)


def clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict(
    spec: ClinicalTrialsGovEstimandEvidenceAcquisitionSpec,
) -> dict[str, Any]:
    value = to_primitive(spec)
    assert isinstance(value, dict)
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_SPEC_SCHEMA_VERSION
        ),
        **value,
    }


def clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict(
    value: Any,
) -> ClinicalTrialsGovEstimandEvidenceAcquisitionSpec:
    data = _record(
        value,
        "spec",
        {
            "schema_version",
            *_field_names(ClinicalTrialsGovEstimandEvidenceAcquisitionSpec),
        },
    )
    if data.pop("schema_version") != (
        CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "unsupported evidence-acquisition spec schema_version"
        )
    data["document_bindings"] = tuple(
        _document_binding_from_dict(item, f"spec.document_bindings[{index}]")
        for index, item in enumerate(_tuple(data["document_bindings"], "document_bindings"))
    )
    data["required_estimand_dimensions"] = tuple(
        _tuple(data["required_estimand_dimensions"], "required_estimand_dimensions")
    )
    return ClinicalTrialsGovEstimandEvidenceAcquisitionSpec(**data)


def clinicaltrials_gov_estimand_evidence_acquisition_spec_from_json(
    text: str,
) -> ClinicalTrialsGovEstimandEvidenceAcquisitionSpec:
    return clinicaltrials_gov_estimand_evidence_acquisition_spec_from_dict(
        _load_json(text, "estimand evidence-acquisition spec")
    )


def clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope(
    packet: ClinicalTrialsGovEstimandEvidenceAcquisitionPacket,
) -> dict[str, Any]:
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_PACKET_SCHEMA_VERSION
        ),
        "integrity_sha256": packet.fingerprint,
        "packet": to_primitive(packet),
    }


def _source_document_from_dict(
    value: Any, path: str
) -> AcquiredEstimandSourceDocument:
    data = _record(value, path, _field_names(AcquiredEstimandSourceDocument))
    data["document_roles"] = tuple(_tuple(data["document_roles"], "document_roles"))
    return AcquiredEstimandSourceDocument(**data)


def _page_cue_from_dict(value: Any, path: str) -> EstimandEvidencePageCue:
    data = _record(value, path, _field_names(EstimandEvidencePageCue))
    data["matched_anchor_ids"] = tuple(
        _tuple(data["matched_anchor_ids"], "matched_anchor_ids")
    )
    return EstimandEvidencePageCue(**data)


def _evidence_cue_from_dict(value: Any, path: str) -> EndpointEstimandEvidenceCue:
    data = _record(value, path, _field_names(EndpointEstimandEvidenceCue))
    data["candidate_pages"] = tuple(
        _page_cue_from_dict(item, f"{path}.candidate_pages[{index}]")
        for index, item in enumerate(_tuple(data["candidate_pages"], "candidate_pages"))
    )
    return EndpointEstimandEvidenceCue(**data)


def _pair_acquisition_from_dict(
    value: Any, path: str
) -> PairEstimandEvidenceAcquisition:
    data = _record(value, path, _field_names(PairEstimandEvidenceAcquisition))
    data["evidence_ids"] = tuple(_tuple(data["evidence_ids"], "evidence_ids"))
    data["blocker_codes"] = tuple(_tuple(data["blocker_codes"], "blocker_codes"))
    return PairEstimandEvidenceAcquisition(**data)


def _dimension_count_from_dict(value: Any, path: str) -> EstimandDimensionCueCount:
    return EstimandDimensionCueCount(
        **_record(value, path, _field_names(EstimandDimensionCueCount))
    )


def clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(
    value: Any,
) -> ClinicalTrialsGovEstimandEvidenceAcquisitionPacket:
    envelope = _record(
        value, "envelope", {"schema_version", "integrity_sha256", "packet"}
    )
    if envelope["schema_version"] != (
        CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_PACKET_SCHEMA_VERSION
    ):
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "unsupported evidence-acquisition packet schema_version"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["packet"],
        "packet",
        _field_names(ClinicalTrialsGovEstimandEvidenceAcquisitionPacket),
    )
    data["required_estimand_dimensions"] = tuple(
        _tuple(data["required_estimand_dimensions"], "required_estimand_dimensions")
    )
    data["source_documents"] = tuple(
        _source_document_from_dict(item, f"packet.source_documents[{index}]")
        for index, item in enumerate(_tuple(data["source_documents"], "source_documents"))
    )
    data["evidence_cues"] = tuple(
        _evidence_cue_from_dict(item, f"packet.evidence_cues[{index}]")
        for index, item in enumerate(_tuple(data["evidence_cues"], "evidence_cues"))
    )
    data["pair_acquisitions"] = tuple(
        _pair_acquisition_from_dict(item, f"packet.pair_acquisitions[{index}]")
        for index, item in enumerate(
            _tuple(data["pair_acquisitions"], "pair_acquisitions")
        )
    )
    data["dimension_counts"] = tuple(
        _dimension_count_from_dict(item, f"packet.dimension_counts[{index}]")
        for index, item in enumerate(_tuple(data["dimension_counts"], "dimension_counts"))
    )
    data["limitations"] = tuple(_tuple(data["limitations"], "limitations"))
    packet = ClinicalTrialsGovEstimandEvidenceAcquisitionPacket(**data)
    if packet.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalTrialsGovEstimandEvidenceAcquisitionError(
            "evidence-acquisition packet integrity mismatch"
        )
    return packet


def clinicaltrials_gov_estimand_evidence_acquisition_packet_from_json(
    text: str,
) -> ClinicalTrialsGovEstimandEvidenceAcquisitionPacket:
    return clinicaltrials_gov_estimand_evidence_acquisition_packet_from_dict(
        _load_json(text, "estimand evidence-acquisition packet")
    )


def clinicaltrials_gov_estimand_evidence_acquisition_summary(
    packet: ClinicalTrialsGovEstimandEvidenceAcquisitionPacket,
) -> dict[str, Any]:
    return {
        "schema_version": (
            CLINICALTRIALS_GOV_ESTIMAND_EVIDENCE_ACQUISITION_PACKET_SCHEMA_VERSION
        ),
        "packet_id": packet.packet_id,
        "integrity_sha256": packet.fingerprint,
        "source_document_count": packet.source_document_count,
        "source_document_page_count": packet.source_document_page_count,
        "pair_count": packet.pair_count,
        "review_ready_pair_count": packet.review_ready_pair_count,
        "preflight_blocked_pair_count": packet.preflight_blocked_pair_count,
        "unique_review_ready_endpoint_count": packet.unique_review_ready_endpoint_count,
        "evidence_record_count": packet.evidence_record_count,
        "candidate_page_cue_count": packet.candidate_page_cue_count,
        "dimension_counts": to_primitive(packet.dimension_counts),
        "semantic_sufficiency_assessed": packet.semantic_sufficiency_assessed,
        "reviewer_approval_performed": packet.reviewer_approval_performed,
        "estimand_equivalence_approved": packet.estimand_equivalence_approved,
    }
