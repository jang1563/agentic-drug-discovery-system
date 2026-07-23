"""Reviewer-controlled extraction from captured CDC MMWR HTML snapshots."""

from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

from .ingestion import (
    INGESTION_JOB_SCHEMA_VERSION,
    SourceBundle,
    normalize_pinned_ingestion_job,
    verify_source_payload,
)


CDC_MMWR_JOB_SCHEMA_VERSION = "adds.cdc-mmwr-ingestion-job.v1"
CDC_MMWR_PROVIDER_ID = "cdc_mmwr"

_JOB_FIELDS = frozenset(
    {"schema_version", "job_id", "source_receipt_id", "article", "records"}
)
_ARTICLE_FIELDS = frozenset(
    {"title", "doi", "publication_date", "canonical_url"}
)
_RECORD_FIELDS = frozenset(
    {
        "record_id",
        "predicate",
        "subject",
        "object_value",
        "observed_at",
        "available_at",
        "confidence",
        "biological_context",
        "metadata",
        "evidence",
    }
)
_EVIDENCE_FIELDS = frozenset({"location_id", "excerpt", "value_text"})
_PROVIDER_METADATA_FIELDS = frozenset(
    {
        "provider_id",
        "article_doi",
        "article_title",
        "article_publication_date",
        "evidence_location",
        "evidence_excerpt_sha256",
        "evidence_value_text",
    }
)
_SUPPORTED_PREDICATES = frozenset(
    {"disease_burden_supported", "treatment_gap_supported"}
)
_BLOCK_TAGS = frozenset({"p", "li", "td", "th", "caption", "h1", "h2", "h3", "h4", "h5", "h6"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "noscript"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_LOCATION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_DOI = re.compile(
    r"^10\.15585/mmwr\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*$",
    re.IGNORECASE,
)
_NUMBER_TEXT = re.compile(
    r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$"
)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _sequence(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    return list(value)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _safe_id(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    if _SAFE_ID.fullmatch(text) is None:
        raise ValueError(f"{field_name} contains unsupported characters")
    return text


def _iso_date(value: Any, field_name: str) -> date:
    text = _text(value, field_name)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _probability(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{field_name} must be between zero and one")
    return float(value)


def _finite_number(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field_name} must be a finite number")
    return float(value)


def _normalized_text(value: str) -> str:
    translated = unicodedata.normalize("NFKC", html.unescape(value)).translate(
        str.maketrans(
            {
                "\u2010": "-",
                "\u2011": "-",
                "\u2012": "-",
                "\u2013": "-",
                "\u2014": "-",
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u00a0": " ",
            }
        )
    )
    return " ".join(translated.split())


def _comparison_text(value: str) -> str:
    return _normalized_text(value).casefold()


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _contains_term(value: str, term: str) -> bool:
    normalized_value = _comparison_text(value)
    normalized_term = _comparison_text(term)
    return (
        re.search(
            rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
            normalized_value,
        )
        is not None
    )


def _single(values: Sequence[str], field_name: str) -> str:
    normalized = tuple(dict.fromkeys(_normalized_text(value) for value in values))
    if len(normalized) != 1:
        raise ValueError(f"CDC MMWR source has missing or conflicting {field_name}")
    return normalized[0]


def _canonical_cdc_url(value: Any, field_name: str) -> str:
    url = _text(value, field_name)
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} has an invalid port") from exc
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() not in {"cdc.gov", "www.cdc.gov"}
        or port not in {None, 443}
        or not parsed.path.casefold().startswith("/mmwr/volumes/")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{field_name} must be a canonical public CDC MMWR URL")
    return urllib.parse.urlunsplit(
        ("https", "www.cdc.gov", parsed.path.rstrip("/"), "", "")
    )


def _decimal_from_value_text(value: str, field_name: str) -> Decimal:
    normalized = _text(value, field_name).replace(" ", "")
    if _NUMBER_TEXT.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must contain one explicit numeric value")
    try:
        return Decimal(normalized.rstrip("%").replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must contain one explicit numeric value") from exc


class _MmwrHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.canonical_urls: list[str] = []
        self.section_blocks: dict[str, list[str]] = {}
        self.all_blocks: list[str] = []
        self._blocks: list[tuple[str, str | None, list[str]]] = []
        self._current_section: str | None = None
        self._heading_depth = 0
        self._pending_section: str | None = None
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.casefold()
        attributes = {key.casefold(): value for key, value in attrs if value is not None}
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta":
            key = attributes.get("name") or attributes.get("property")
            content = attributes.get("content")
            if key and content:
                self.meta.setdefault(key.casefold(), []).append(content)
        elif tag == "link" and attributes.get("rel", "").casefold() == "canonical":
            href = attributes.get("href")
            if href:
                self.canonical_urls.append(href)
        if tag in _HEADING_TAGS:
            self._heading_depth += 1
            self._pending_section = None
        element_id = attributes.get("id")
        if element_id and self._heading_depth:
            self._pending_section = element_id
        if tag in _BLOCK_TAGS:
            self._blocks.append((tag, self._current_section, []))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS and self._blocks and self._blocks[-1][0] == tag:
            _, section, fragments = self._blocks.pop()
            block = _normalized_text(" ".join(fragments))
            if block:
                self.all_blocks.append(block)
                if section is not None:
                    self.section_blocks.setdefault(section, []).append(block)
        if tag in _HEADING_TAGS:
            if self._pending_section is not None:
                self._current_section = self._pending_section
            self._pending_section = None
            self._heading_depth = max(0, self._heading_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and self._blocks:
            self._blocks[-1][2].append(data)


def _parse_mmwr_html(payload: bytes) -> _MmwrHtmlParser:
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("CDC MMWR payload must be UTF-8 HTML") from exc
    parser = _MmwrHtmlParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        raise ValueError("CDC MMWR payload could not be parsed as HTML") from exc
    return parser


def _validate_common_record(
    record: Mapping[str, Any],
    *,
    index: int,
    publication_date: date,
) -> tuple[dict[str, Any], dict[str, str]]:
    label = f"records[{index}]"
    if set(record) != _RECORD_FIELDS:
        raise ValueError(f"{label} must contain exactly {sorted(_RECORD_FIELDS)}")
    predicate = _text(record["predicate"], f"{label}.predicate")
    if predicate not in _SUPPORTED_PREDICATES:
        raise ValueError(f"{label}.predicate is not supported by CDC MMWR extraction")
    observed_at = _iso_date(record["observed_at"], f"{label}.observed_at")
    available_at = _iso_date(record["available_at"], f"{label}.available_at")
    if observed_at > available_at:
        raise ValueError(f"{label}.observed_at cannot follow available_at")
    if available_at != publication_date:
        raise ValueError(f"{label}.available_at must equal the article publication date")
    context = _mapping(record["biological_context"], f"{label}.biological_context")
    for key in ("disease_id", "evidence_context_id"):
        _text(context.get(key), f"{label}.biological_context.{key}")
    metadata = _mapping(record["metadata"], f"{label}.metadata")
    if any(not isinstance(key, str) for key in metadata):
        raise ValueError(f"{label}.metadata keys must be strings")
    provider_field_names = {
        _normalized_field_name(key) for key in _PROVIDER_METADATA_FIELDS
    }
    overlap = sorted(
        key
        for key in metadata
        if _normalized_field_name(key) in provider_field_names
    )
    if overlap:
        raise ValueError(f"{label}.metadata contains provider-owned fields: {overlap}")
    common_metadata = ("population", "geography", "reference_period")
    for key in common_metadata:
        _text(metadata.get(key), f"{label}.metadata.{key}")
    if predicate == "disease_burden_supported":
        for key in ("measure_type", "measure_unit"):
            _text(metadata.get(key), f"{label}.metadata.{key}")
        _finite_number(metadata.get("measure_value"), f"{label}.metadata.measure_value")
    else:
        for key in ("treatment_context", "gap_summary", "gap_measure_unit"):
            _text(metadata.get(key), f"{label}.metadata.{key}")
        _finite_number(
            metadata.get("gap_measure_value"),
            f"{label}.metadata.gap_measure_value",
        )
    evidence = _mapping(record["evidence"], f"{label}.evidence")
    if set(evidence) != _EVIDENCE_FIELDS:
        raise ValueError(
            f"{label}.evidence must contain exactly {sorted(_EVIDENCE_FIELDS)}"
        )
    location_id = _text(evidence["location_id"], f"{label}.evidence.location_id")
    if _SAFE_LOCATION_ID.fullmatch(location_id) is None:
        raise ValueError(f"{label}.evidence.location_id is invalid")
    excerpt = _normalized_text(
        _text(evidence["excerpt"], f"{label}.evidence.excerpt")
    )
    if len(excerpt) < 20 or len(excerpt) > 4096:
        raise ValueError(f"{label}.evidence.excerpt must contain 20-4096 characters")
    value_text = _text(evidence["value_text"], f"{label}.evidence.value_text")
    _decimal_from_value_text(value_text, f"{label}.evidence.value_text")
    generic_record = {
        "record_id": _safe_id(record["record_id"], f"{label}.record_id"),
        "predicate": predicate,
        "subject": _text(record["subject"], f"{label}.subject"),
        "object_value": _text(record["object_value"], f"{label}.object_value"),
        "observed_at": observed_at.isoformat(),
        "available_at": available_at.isoformat(),
        "confidence": _probability(record["confidence"], f"{label}.confidence"),
        "biological_context": context,
        "metadata": metadata,
    }
    return generic_record, {
        "location_id": location_id,
        "excerpt": excerpt,
        "value_text": value_text,
    }


def normalize_cdc_mmwr_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate a reviewer-authored CDC MMWR extraction job without source bytes."""

    job = _mapping(value, "job")
    if set(job) != _JOB_FIELDS:
        raise ValueError(f"job must contain exactly {sorted(_JOB_FIELDS)}")
    if job["schema_version"] != CDC_MMWR_JOB_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {CDC_MMWR_JOB_SCHEMA_VERSION}")
    job_id = _safe_id(job["job_id"], "job.job_id")
    source_receipt_id = _safe_id(
        job["source_receipt_id"], "job.source_receipt_id"
    )
    article = _mapping(job["article"], "job.article")
    if set(article) != _ARTICLE_FIELDS:
        raise ValueError(f"job.article must contain exactly {sorted(_ARTICLE_FIELDS)}")
    doi = _text(article["doi"], "job.article.doi").casefold()
    if _DOI.fullmatch(doi) is None:
        raise ValueError("job.article.doi must identify a CDC MMWR DOI")
    publication_date = _iso_date(
        article["publication_date"], "job.article.publication_date"
    )
    normalized_article = {
        "title": _normalized_text(_text(article["title"], "job.article.title")),
        "doi": doi,
        "publication_date": publication_date.isoformat(),
        "canonical_url": _canonical_cdc_url(
            article["canonical_url"], "job.article.canonical_url"
        ),
    }
    raw_records = _sequence(job["records"], "job.records")
    if not raw_records:
        raise ValueError("job.records must contain at least one record")
    records: list[dict[str, Any]] = []
    generic_records: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records):
        record = _mapping(raw, f"job.records[{index}]")
        generic, evidence = _validate_common_record(
            record,
            index=index,
            publication_date=publication_date,
        )
        generic_records.append(
            {"source_receipt_id": source_receipt_id, **generic}
        )
        records.append({**generic, "evidence": evidence})
    normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "records": generic_records,
        }
    )
    return {
        "schema_version": CDC_MMWR_JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "source_receipt_id": source_receipt_id,
        "article": normalized_article,
        "records": records,
    }


def _validate_article_source(
    job: Mapping[str, Any],
    bundle: SourceBundle,
    page: _MmwrHtmlParser,
) -> None:
    article = job["article"]
    receipt = bundle.receipt
    if receipt.receipt_id != job["source_receipt_id"]:
        raise ValueError("CDC MMWR job source_receipt_id does not match the bundle")
    if receipt.media_type.casefold() not in {"text/html", "application/xhtml+xml"}:
        raise ValueError("CDC MMWR source must declare an HTML media type")
    if _canonical_cdc_url(receipt.locator, "receipt.locator") != article[
        "canonical_url"
    ]:
        raise ValueError("CDC MMWR receipt locator does not match the article canonical URL")
    source_version_token = re.sub(
        r"[^a-z0-9.]+", "-", article["doi"].casefold()
    ).strip("-")
    normalized_version = re.sub(
        r"[^a-z0-9.]+", "-", receipt.source_version.casefold()
    ).strip("-")
    if normalized_version != f"doi-{source_version_token}":
        raise ValueError("CDC MMWR source_version must exactly bind the declared DOI")
    if date.fromisoformat(article["publication_date"]) > receipt.retrieved_at.date():
        raise ValueError("CDC MMWR source cannot be retrieved before article publication")

    source_title = _single(page.meta.get("citation_title", ()), "citation_title")
    source_doi = _single(page.meta.get("citation_doi", ()), "citation_doi").casefold()
    source_year = _single(
        page.meta.get("citation_publication_date", ()),
        "citation_publication_date",
    )
    source_canonical = _canonical_cdc_url(
        _single(page.canonical_urls, "canonical URL"),
        "source canonical URL",
    )
    if _comparison_text(source_title) != _comparison_text(article["title"]):
        raise ValueError("CDC MMWR source title does not match the provider job")
    if source_doi != article["doi"]:
        raise ValueError("CDC MMWR source DOI does not match the provider job")
    if source_year != article["publication_date"][:4]:
        raise ValueError("CDC MMWR source publication year does not match the provider job")
    if source_canonical != article["canonical_url"]:
        raise ValueError("CDC MMWR source canonical URL does not match the provider job")
    published = date.fromisoformat(article["publication_date"])
    human_date = f"{_MONTHS[published.month - 1]} {published.day}, {published.year}"
    if not any(
        _comparison_text(human_date) in _comparison_text(block)
        for block in page.all_blocks[:20]
    ):
        raise ValueError("CDC MMWR source does not contain the declared publication date")


def _validate_evidence_block(
    record: Mapping[str, Any],
    page: _MmwrHtmlParser,
    *,
    index: int,
) -> str:
    label = f"records[{index}]"
    evidence = record["evidence"]
    location_id = evidence["location_id"]
    excerpt = evidence["excerpt"]
    blocks = page.section_blocks.get(location_id, ())
    matches = [
        block
        for block in blocks
        if _normalized_text(block).count(excerpt) == 1
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{label}.evidence.excerpt must match exactly one block in section "
            f"{location_id}"
        )
    if excerpt.count(_normalized_text(evidence["value_text"])) != 1:
        raise ValueError(
            f"{label}.evidence.value_text must occur exactly once in the excerpt"
        )
    observed_value = _decimal_from_value_text(
        evidence["value_text"], f"{label}.evidence.value_text"
    )
    metadata = record["metadata"]
    if record["predicate"] == "disease_burden_supported":
        declared_value = Decimal(str(metadata["measure_value"]))
        unit = _comparison_text(metadata["measure_unit"])
    else:
        declared_value = Decimal(str(metadata["gap_measure_value"]))
        unit = _comparison_text(metadata["gap_measure_unit"])
    if observed_value != declared_value:
        raise ValueError(f"{label} numeric value does not match evidence.value_text")
    if unit == "percent":
        unit_present = "%" in evidence["value_text"] or _contains_term(
            excerpt, "percent"
        )
    else:
        unit_present = _contains_term(excerpt, unit)
    if not unit_present:
        raise ValueError(f"{label} declared unit is absent from the evidence excerpt")
    for field_name in ("geography", "reference_period"):
        if not _contains_term(excerpt, str(metadata[field_name])):
            raise ValueError(
                f"{label} metadata.{field_name} is absent from the evidence excerpt"
            )
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def extract_cdc_mmwr_ingestion_job(
    value: Any,
    bundle: SourceBundle,
) -> dict[str, Any]:
    """Verify one CDC MMWR snapshot and emit a sanitized generic ingestion job."""

    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    verify_source_payload(bundle.receipt, bundle.payload)
    job = normalize_cdc_mmwr_ingestion_job(value)
    page = _parse_mmwr_html(bundle.payload)
    _validate_article_source(job, bundle, page)

    records: list[dict[str, Any]] = []
    for index, record in enumerate(job["records"]):
        excerpt_hash = _validate_evidence_block(record, page, index=index)
        evidence = record["evidence"]
        records.append(
            {
                "source_receipt_id": job["source_receipt_id"],
                **{key: value for key, value in record.items() if key != "evidence"},
                "metadata": {
                    **record["metadata"],
                    "provider_id": CDC_MMWR_PROVIDER_ID,
                    "article_doi": job["article"]["doi"],
                    "article_title": job["article"]["title"],
                    "article_publication_date": job["article"]["publication_date"],
                    "evidence_location": evidence["location_id"],
                    "evidence_excerpt_sha256": excerpt_hash,
                    "evidence_value_text": evidence["value_text"],
                },
            }
        )
    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job["job_id"],
            "records": records,
        }
    )
