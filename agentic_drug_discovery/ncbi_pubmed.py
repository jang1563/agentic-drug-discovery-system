"""Reviewer-controlled treatment-gap extraction from NCBI PubMed XML."""

from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .ingestion import (
    INGESTION_JOB_SCHEMA_VERSION,
    SourceBundle,
    normalize_pinned_ingestion_job,
    verify_source_payload,
)


NCBI_PUBMED_JOB_SCHEMA_VERSION = "adds.ncbi-pubmed-ingestion-job.v1"
NCBI_PUBMED_DISEASE_MODEL_JOB_SCHEMA_VERSION = (
    "adds.ncbi-pubmed-disease-model-ingestion-job.v1"
)
NCBI_PUBMED_PROVIDER_ID = "ncbi_pubmed"

_JOB_FIELDS = frozenset(
    {"schema_version", "job_id", "source_receipt_id", "article", "records"}
)
_ARTICLE_FIELDS = frozenset(
    {"title", "pmid", "pmcid", "doi", "publication_date", "canonical_url"}
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
_EVIDENCE_FIELDS = frozenset(
    {
        "result_label",
        "result_excerpt",
        "context_label",
        "context_excerpt",
        "value_text",
        "population_anchor",
        "geography_anchor",
        "reference_period_anchor",
        "treatment_anchor",
    }
)
_PROVIDER_METADATA_FIELDS = frozenset(
    {
        "provider_id",
        "article_pmid",
        "article_pmcid",
        "article_doi",
        "article_title",
        "article_publication_date",
        "article_canonical_url",
        "result_location",
        "context_location",
        "result_excerpt_sha256",
        "context_excerpt_sha256",
        "evidence_value_text",
        "population_anchor_sha256",
        "geography_anchor_sha256",
        "reference_period_anchor_sha256",
        "treatment_anchor_sha256",
    }
)
_REQUIRED_METADATA_FIELDS = frozenset(
    {
        "treatment_context",
        "gap_summary",
        "gap_measure_operator",
        "gap_measure_value",
        "gap_measure_unit",
        "population",
        "geography",
        "reference_period",
    }
)
_GAP_OPERATORS = frozenset({"lt", "le", "eq", "ge", "gt"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PMID = re.compile(r"^[1-9][0-9]{0,15}$")
_PMCID = re.compile(r"^PMC[1-9][0-9]{0,15}$")
_DOI = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_REFERENCE_PERIOD = re.compile(r"^([12][0-9]{3})-([12][0-9]{3})$")
_VALUE_TEXT = re.compile(
    r"^(?P<comparison><=|>=|<|>)?(?P<value>[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)(?P<percent>%)?$"
)
_COMPARISON_TO_OPERATOR = {"<": "lt", "<=": "le", "": "eq", ">=": "ge", ">": "gt"}
_DISEASE_MODEL_JOB_FIELDS = _JOB_FIELDS
_DISEASE_MODEL_ARTICLE_FIELDS = _ARTICLE_FIELDS
_DISEASE_MODEL_CONTEXT_FIELDS = frozenset(
    {"candidate_id", "disease_id", "organism", "model_system_id"}
)
_DISEASE_MODEL_METADATA_FIELDS = frozenset(
    {
        "model_system",
        "model_type",
        "endpoint",
        "endpoint_relation",
        "endpoint_value",
        "endpoint_unit",
        "endpoint_variation_value",
        "endpoint_variation_unit",
        "effect_direction",
        "disease_relevance",
        "source_candidate_name",
        "dose_value",
        "dose_unit",
        "route",
        "frequency",
        "duration_value",
        "duration_unit",
        "p_value_relation",
        "p_value",
    }
)
_DISEASE_MODEL_EVIDENCE_FIELDS = frozenset(
    {
        "result_excerpt",
        "conclusion_excerpt",
        "candidate_anchor",
        "model_anchor",
        "dose_text",
        "route_anchor",
        "frequency_anchor",
        "duration_text",
        "endpoint_value_text",
        "endpoint_variation_text",
        "p_value_text",
        "conclusion_anchor",
    }
)
_DISEASE_MODEL_PROVIDER_METADATA_FIELDS = frozenset(
    {
        "provider_id",
        "article_pmid",
        "article_pmcid",
        "article_doi",
        "article_title",
        "article_publication_date",
        "article_canonical_url",
        "result_excerpt_sha256",
        "conclusion_excerpt_sha256",
        "candidate_anchor_sha256",
        "model_anchor_sha256",
        "dose_text_sha256",
        "route_anchor_sha256",
        "frequency_anchor_sha256",
        "duration_text_sha256",
        "endpoint_value_text_sha256",
        "endpoint_variation_text_sha256",
        "p_value_text_sha256",
        "conclusion_anchor_sha256",
        "source_lineage_ids",
    }
)
_TYPED_VALUE_TEXT = re.compile(
    r"^(?P<comparison><=|>=|<|>)?"
    r"(?P<value>(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))"
    r"(?P<percent>%)?$"
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


def _finite_decimal(value: Any, field_name: str) -> Decimal:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field_name} must be a finite number")
    return Decimal(str(value))


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
                "\u2264": "<=",
                "\u2265": ">=",
            }
        )
    )
    return " ".join(translated.split())


def _comparison_text(value: str) -> str:
    return _normalized_text(value).casefold()


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _contains_term(value: str, term: str) -> bool:
    return (
        re.search(
            rf"(?<!\w){re.escape(_comparison_text(term))}(?!\w)",
            _comparison_text(value),
        )
        is not None
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _element_text(element: ET.Element, field_name: str) -> str:
    text = _normalized_text("".join(element.itertext()))
    if not text:
        raise ValueError(f"NCBI PubMed XML has an empty {field_name}")
    return text


def _direct_children(parent: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in parent if child.tag == tag]


def _single_child(parent: ET.Element, tag: str, field_name: str) -> ET.Element:
    values = _direct_children(parent, tag)
    if len(values) != 1:
        raise ValueError(f"NCBI PubMed XML must contain exactly one {field_name}")
    return values[0]


def _canonical_pubmed_url(value: Any, pmid: str, field_name: str) -> str:
    url = _text(value, field_name)
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} has an invalid port") from exc
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "pubmed.ncbi.nlm.nih.gov"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != f"/{pmid}/"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{field_name} must be the canonical PubMed URL for PMID {pmid}"
        )
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def _validate_efetch_locator(value: str, pmid: str) -> None:
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "receipt.locator is not a valid NCBI PubMed EFetch URL"
        ) from exc
    query_parts = parsed.query.split("&")
    expected_parts = {"db=pubmed", f"id={pmid}", "retmode=xml"}
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "eutils.ncbi.nlm.nih.gov"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/entrez/eutils/efetch.fcgi"
        or parsed.fragment
        or len(query_parts) != len(expected_parts)
        or set(query_parts) != expected_parts
    ):
        raise ValueError(
            "receipt.locator must be the exact NCBI PubMed EFetch XML request"
        )


def _normalize_article(value: Any) -> tuple[dict[str, str], date]:
    article = _mapping(value, "job.article")
    if set(article) != _ARTICLE_FIELDS:
        raise ValueError(f"job.article must contain exactly {sorted(_ARTICLE_FIELDS)}")
    pmid = _text(article["pmid"], "job.article.pmid")
    if _PMID.fullmatch(pmid) is None:
        raise ValueError("job.article.pmid must be a positive PubMed identifier")
    pmcid = _text(article["pmcid"], "job.article.pmcid").upper()
    if _PMCID.fullmatch(pmcid) is None:
        raise ValueError("job.article.pmcid must be a positive PMC identifier")
    doi = _text(article["doi"], "job.article.doi").casefold()
    if _DOI.fullmatch(doi) is None:
        raise ValueError("job.article.doi must be a DOI")
    publication_date = _iso_date(
        article["publication_date"], "job.article.publication_date"
    )
    title = _normalized_text(_text(article["title"], "job.article.title"))
    if len(title) > 4096:
        raise ValueError("job.article.title must contain at most 4096 characters")
    if len(doi) > 255:
        raise ValueError("job.article.doi must contain at most 255 characters")
    return (
        {
            "title": title,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "publication_date": publication_date.isoformat(),
            "canonical_url": _canonical_pubmed_url(
                article["canonical_url"], pmid, "job.article.canonical_url"
            ),
        },
        publication_date,
    )


def _normalize_record(
    value: Any,
    *,
    index: int,
    source_receipt_id: str,
    publication_date: date,
) -> tuple[dict[str, Any], dict[str, str]]:
    label = f"job.records[{index}]"
    record = _mapping(value, label)
    if set(record) != _RECORD_FIELDS:
        raise ValueError(f"{label} must contain exactly {sorted(_RECORD_FIELDS)}")
    if record["predicate"] != "treatment_gap_supported":
        raise ValueError(f"{label}.predicate must be treatment_gap_supported")
    observed_at = _iso_date(record["observed_at"], f"{label}.observed_at")
    available_at = _iso_date(record["available_at"], f"{label}.available_at")
    if observed_at > available_at:
        raise ValueError(f"{label}.observed_at cannot follow available_at")
    if available_at != publication_date:
        raise ValueError(
            f"{label}.available_at must equal the article publication date"
        )

    context = _mapping(record["biological_context"], f"{label}.biological_context")
    for key in ("disease_id", "evidence_context_id"):
        _text(context.get(key), f"{label}.biological_context.{key}")

    metadata = _mapping(record["metadata"], f"{label}.metadata")
    if any(not isinstance(key, str) for key in metadata):
        raise ValueError(f"{label}.metadata keys must be strings")
    missing = sorted(_REQUIRED_METADATA_FIELDS - set(metadata))
    if missing:
        raise ValueError(f"{label}.metadata is missing required fields: {missing}")
    provider_fields = {_normalized_field_name(key) for key in _PROVIDER_METADATA_FIELDS}
    overlap = sorted(
        key for key in metadata if _normalized_field_name(key) in provider_fields
    )
    if overlap:
        raise ValueError(f"{label}.metadata contains provider-owned fields: {overlap}")
    for key in (
        "treatment_context",
        "gap_summary",
        "gap_measure_unit",
        "population",
        "geography",
        "reference_period",
    ):
        _text(metadata[key], f"{label}.metadata.{key}")
    operator = _text(
        metadata["gap_measure_operator"],
        f"{label}.metadata.gap_measure_operator",
    ).casefold()
    if operator not in _GAP_OPERATORS:
        raise ValueError(f"{label}.metadata.gap_measure_operator is unsupported")
    metadata["gap_measure_operator"] = operator
    _finite_decimal(
        metadata["gap_measure_value"], f"{label}.metadata.gap_measure_value"
    )
    period = _text(metadata["reference_period"], f"{label}.metadata.reference_period")
    match = _REFERENCE_PERIOD.fullmatch(period)
    if match is None or int(match.group(1)) > int(match.group(2)):
        raise ValueError(
            f"{label}.metadata.reference_period must be canonical YYYY-YYYY"
        )

    evidence = _mapping(record["evidence"], f"{label}.evidence")
    if set(evidence) != _EVIDENCE_FIELDS:
        raise ValueError(
            f"{label}.evidence must contain exactly {sorted(_EVIDENCE_FIELDS)}"
        )
    normalized_evidence = {
        key: _normalized_text(_text(evidence[key], f"{label}.evidence.{key}"))
        for key in _EVIDENCE_FIELDS
    }
    if normalized_evidence["result_label"] != "RESULTS":
        raise ValueError(f"{label}.evidence.result_label must be RESULTS")
    if normalized_evidence["context_label"] != "METHODS":
        raise ValueError(f"{label}.evidence.context_label must be METHODS")
    for key, text in normalized_evidence.items():
        if len(text) > 4096:
            raise ValueError(
                f"{label}.evidence.{key} must contain at most 4096 characters"
            )
    for key in ("result_excerpt", "context_excerpt"):
        if not 20 <= len(normalized_evidence[key]) <= 4096:
            raise ValueError(f"{label}.evidence.{key} must contain 20-4096 characters")
    if len(normalized_evidence["population_anchor"]) < 20:
        raise ValueError(
            f"{label}.evidence.population_anchor must contain at least 20 characters"
        )

    value_match = _VALUE_TEXT.fullmatch(normalized_evidence["value_text"])
    if value_match is None:
        raise ValueError(f"{label}.evidence.value_text must be one typed numeric value")
    value_operator = _COMPARISON_TO_OPERATOR[value_match.group("comparison") or ""]
    if value_operator != operator:
        raise ValueError(
            f"{label} comparator does not match metadata.gap_measure_operator"
        )
    try:
        observed_value = Decimal(value_match.group("value").replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(
            f"{label}.evidence.value_text has an invalid numeric value"
        ) from exc
    if observed_value != Decimal(str(metadata["gap_measure_value"])):
        raise ValueError(f"{label} numeric value does not match evidence.value_text")
    unit = _comparison_text(str(metadata["gap_measure_unit"]))
    if unit == "percent" and value_match.group("percent") != "%":
        raise ValueError(f"{label} percent evidence must use an explicit % sign")
    if unit != "percent" and not _contains_term(
        normalized_evidence["result_excerpt"], unit
    ):
        raise ValueError(f"{label} declared unit is absent from the result excerpt")

    generic_record = {
        "source_receipt_id": source_receipt_id,
        "record_id": _safe_id(record["record_id"], f"{label}.record_id"),
        "predicate": "treatment_gap_supported",
        "subject": _text(record["subject"], f"{label}.subject"),
        "object_value": _text(record["object_value"], f"{label}.object_value"),
        "observed_at": observed_at.isoformat(),
        "available_at": available_at.isoformat(),
        "confidence": _probability(record["confidence"], f"{label}.confidence"),
        "biological_context": context,
        "metadata": metadata,
    }
    return generic_record, normalized_evidence


def normalize_ncbi_pubmed_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate a reviewer-authored PubMed extraction job without source bytes."""

    job = _mapping(value, "job")
    if set(job) != _JOB_FIELDS:
        raise ValueError(f"job must contain exactly {sorted(_JOB_FIELDS)}")
    if job["schema_version"] != NCBI_PUBMED_JOB_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {NCBI_PUBMED_JOB_SCHEMA_VERSION}")
    job_id = _safe_id(job["job_id"], "job.job_id")
    source_receipt_id = _safe_id(job["source_receipt_id"], "job.source_receipt_id")
    article, publication_date = _normalize_article(job["article"])
    raw_records = _sequence(job["records"], "job.records")
    if not raw_records:
        raise ValueError("job.records must contain at least one record")
    records: list[dict[str, Any]] = []
    generic_records: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records):
        generic, evidence = _normalize_record(
            raw,
            index=index,
            source_receipt_id=source_receipt_id,
            publication_date=publication_date,
        )
        generic_records.append(generic)
        records.append(
            {
                **{
                    key: item
                    for key, item in generic.items()
                    if key != "source_receipt_id"
                },
                "evidence": evidence,
            }
        )
    normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "records": generic_records,
        }
    )
    return {
        "schema_version": NCBI_PUBMED_JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "source_receipt_id": source_receipt_id,
        "article": article,
        "records": records,
    }


def _parse_pubmed_xml(payload: bytes) -> ET.Element:
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("NCBI PubMed payload must be UTF-8 XML") from exc
    if re.search(r"<!\s*ENTITY\b", source, re.IGNORECASE):
        raise ValueError("NCBI PubMed XML must not contain entity declarations")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ValueError("NCBI PubMed payload could not be parsed as XML") from exc
    if root.tag != "PubmedArticleSet":
        raise ValueError("NCBI PubMed XML root must be PubmedArticleSet")
    if any(child.tag != "PubmedArticle" for child in root):
        raise ValueError("NCBI PubMed XML must contain only PubmedArticle records")
    if len(_direct_children(root, "PubmedArticle")) != 1:
        raise ValueError("NCBI PubMed XML must contain exactly one PubmedArticle")
    return root


def _article_date(article: ET.Element) -> date:
    electronic = [
        item
        for item in _direct_children(article, "ArticleDate")
        if item.attrib.get("DateType", "").casefold() == "electronic"
    ]
    if len(electronic) != 1:
        raise ValueError(
            "NCBI PubMed XML must contain exactly one electronic ArticleDate"
        )
    year = _element_text(
        _single_child(electronic[0], "Year", "electronic publication year"),
        "electronic publication year",
    )
    month = _element_text(
        _single_child(electronic[0], "Month", "electronic publication month"),
        "electronic publication month",
    )
    day = _element_text(
        _single_child(electronic[0], "Day", "electronic publication day"),
        "electronic publication day",
    )
    try:
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError(
            "NCBI PubMed XML has an invalid electronic publication date"
        ) from exc


def _article_identifier(
    article_id_list: ET.Element,
    id_type: str,
    field_name: str,
) -> str:
    matches = [
        item
        for item in _direct_children(article_id_list, "ArticleId")
        if item.attrib.get("IdType", "").casefold() == id_type.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(f"NCBI PubMed XML must contain exactly one {field_name}")
    return _element_text(matches[0], field_name)


def _reject_retracted(medline: ET.Element, article: ET.Element) -> None:
    publication_types = _direct_children(article, "PublicationTypeList")
    if len(publication_types) > 1:
        raise ValueError("NCBI PubMed XML has conflicting PublicationTypeList elements")
    if publication_types:
        values = (
            _comparison_text(_element_text(item, "publication type"))
            for item in _direct_children(publication_types[0], "PublicationType")
        )
        if any("retracted publication" in value for value in values):
            raise ValueError("NCBI PubMed XML identifies a retracted publication")
    correction_lists = _direct_children(medline, "CommentsCorrectionsList")
    if len(correction_lists) > 1:
        raise ValueError(
            "NCBI PubMed XML has conflicting CommentsCorrectionsList elements"
        )
    if correction_lists and any(
        "retract" in item.attrib.get("RefType", "").casefold()
        for item in _direct_children(correction_lists[0], "CommentsCorrections")
    ):
        raise ValueError("NCBI PubMed XML contains a retraction relationship")


def _validate_article_source(
    job: Mapping[str, Any],
    bundle: SourceBundle,
    root: ET.Element,
) -> dict[str, str]:
    declared = job["article"]
    receipt = bundle.receipt
    if receipt.receipt_id != job["source_receipt_id"]:
        raise ValueError("NCBI PubMed job source_receipt_id does not match the bundle")
    if receipt.media_type.casefold() not in {"text/xml", "application/xml"}:
        raise ValueError("NCBI PubMed source must declare an XML media type")
    _validate_efetch_locator(receipt.locator, declared["pmid"])
    expected_version = (
        f"pmid-{declared['pmid']}-pubmed-xml-{receipt.retrieved_at.date().isoformat()}"
    )
    if receipt.source_version != expected_version:
        raise ValueError(
            "NCBI PubMed source_version must exactly bind PMID and retrieval date"
        )
    if date.fromisoformat(declared["publication_date"]) > receipt.retrieved_at.date():
        raise ValueError(
            "NCBI PubMed source cannot be retrieved before article publication"
        )

    pubmed_article = _single_child(root, "PubmedArticle", "PubmedArticle")
    medline = _single_child(pubmed_article, "MedlineCitation", "MedlineCitation")
    pubmed_data = _single_child(pubmed_article, "PubmedData", "PubmedData")
    article = _single_child(medline, "Article", "Article")
    _reject_retracted(medline, article)

    pmid = _element_text(_single_child(medline, "PMID", "MedlineCitation PMID"), "PMID")
    title = _element_text(
        _single_child(article, "ArticleTitle", "ArticleTitle"), "title"
    )
    doi_locations = [
        item
        for item in _direct_children(article, "ELocationID")
        if item.attrib.get("EIdType", "").casefold() == "doi"
    ]
    if len(doi_locations) != 1:
        raise ValueError(
            "NCBI PubMed XML must contain exactly one article DOI ELocationID"
        )
    location_doi = _element_text(doi_locations[0], "article DOI").casefold()
    publication_date = _article_date(article)

    article_id_list = _single_child(pubmed_data, "ArticleIdList", "ArticleIdList")
    data_pmid = _article_identifier(article_id_list, "pubmed", "PubMed ArticleId")
    pmcid = _article_identifier(article_id_list, "pmc", "PMC ArticleId").upper()
    data_doi = _article_identifier(article_id_list, "doi", "DOI ArticleId").casefold()

    if pmid != declared["pmid"] or data_pmid != declared["pmid"]:
        raise ValueError("NCBI PubMed source PMID does not match the provider job")
    if pmcid != declared["pmcid"]:
        raise ValueError("NCBI PubMed source PMCID does not match the provider job")
    if location_doi != declared["doi"] or data_doi != declared["doi"]:
        raise ValueError("NCBI PubMed source DOI does not match the provider job")
    if _comparison_text(title) != _comparison_text(declared["title"]):
        raise ValueError("NCBI PubMed source title does not match the provider job")
    if publication_date.isoformat() != declared["publication_date"]:
        raise ValueError(
            "NCBI PubMed electronic publication date does not match the provider job"
        )
    return {"title": title, "pmid": pmid, "pmcid": pmcid, "doi": location_doi}


def _abstract_sections(root: ET.Element) -> dict[str, list[str]]:
    pubmed_article = _single_child(root, "PubmedArticle", "PubmedArticle")
    medline = _single_child(pubmed_article, "MedlineCitation", "MedlineCitation")
    article = _single_child(medline, "Article", "Article")
    abstract = _single_child(article, "Abstract", "Abstract")
    sections: dict[str, list[str]] = {}
    for item in _direct_children(abstract, "AbstractText"):
        label = _normalized_text(item.attrib.get("Label", ""))
        if not label:
            continue
        sections.setdefault(label.casefold(), []).append(
            _element_text(item, f"{label} AbstractText")
        )
    return sections


def _exactly_once(container: str, value: str, field_name: str) -> None:
    if _normalized_text(container).count(_normalized_text(value)) != 1:
        raise ValueError(
            f"{field_name} must occur exactly once in its selected abstract section"
        )


def _validate_record_evidence(
    record: Mapping[str, Any],
    sections: Mapping[str, Sequence[str]],
    *,
    index: int,
) -> dict[str, str]:
    label = f"records[{index}]"
    evidence = record["evidence"]
    result_key = evidence["result_label"].casefold()
    context_key = evidence["context_label"].casefold()
    result_sections = list(sections.get(result_key, ()))
    context_sections = list(sections.get(context_key, ()))
    if len(result_sections) != 1:
        raise ValueError(f"{label}.evidence.result_label must resolve exactly once")
    if len(context_sections) != 1:
        raise ValueError(f"{label}.evidence.context_label must resolve exactly once")
    result_source = result_sections[0]
    context_source = context_sections[0]
    _exactly_once(
        result_source, evidence["result_excerpt"], f"{label}.evidence.result_excerpt"
    )
    _exactly_once(
        context_source, evidence["context_excerpt"], f"{label}.evidence.context_excerpt"
    )
    _exactly_once(
        evidence["result_excerpt"],
        evidence["value_text"],
        f"{label}.evidence.value_text",
    )
    _exactly_once(
        evidence["context_excerpt"],
        evidence["population_anchor"],
        f"{label}.evidence.population_anchor",
    )
    _exactly_once(
        evidence["context_excerpt"],
        evidence["geography_anchor"],
        f"{label}.evidence.geography_anchor",
    )
    _exactly_once(
        evidence["context_excerpt"],
        evidence["reference_period_anchor"],
        f"{label}.evidence.reference_period_anchor",
    )
    _exactly_once(
        evidence["result_excerpt"],
        evidence["treatment_anchor"],
        f"{label}.evidence.treatment_anchor",
    )

    metadata = record["metadata"]
    if _comparison_text(str(metadata["geography"])) != _comparison_text(
        evidence["geography_anchor"]
    ):
        raise ValueError(f"{label} geography does not match its evidence anchor")
    if _comparison_text(str(metadata["treatment_context"])) != _comparison_text(
        evidence["treatment_anchor"]
    ):
        raise ValueError(
            f"{label} treatment context does not match its evidence anchor"
        )
    period_match = _REFERENCE_PERIOD.fullmatch(str(metadata["reference_period"]))
    assert period_match is not None
    anchor_years = re.findall(
        r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", evidence["reference_period_anchor"]
    )
    expected_years = [period_match.group(1), period_match.group(2)]
    if anchor_years != expected_years:
        raise ValueError(f"{label} reference period does not match its evidence anchor")

    return {
        "result_excerpt_sha256": _sha256(evidence["result_excerpt"]),
        "context_excerpt_sha256": _sha256(evidence["context_excerpt"]),
        "population_anchor_sha256": _sha256(evidence["population_anchor"]),
        "geography_anchor_sha256": _sha256(evidence["geography_anchor"]),
        "reference_period_anchor_sha256": _sha256(evidence["reference_period_anchor"]),
        "treatment_anchor_sha256": _sha256(evidence["treatment_anchor"]),
    }


def extract_ncbi_pubmed_ingestion_job(
    value: Any,
    bundle: SourceBundle,
) -> dict[str, Any]:
    """Verify one PubMed XML snapshot and emit a sanitized generic ingestion job."""

    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    verify_source_payload(bundle.receipt, bundle.payload)
    job = normalize_ncbi_pubmed_ingestion_job(value)
    root = _parse_pubmed_xml(bundle.payload)
    _validate_article_source(job, bundle, root)
    sections = _abstract_sections(root)

    records: list[dict[str, Any]] = []
    for index, record in enumerate(job["records"]):
        hashes = _validate_record_evidence(record, sections, index=index)
        evidence = record["evidence"]
        records.append(
            {
                "source_receipt_id": job["source_receipt_id"],
                **{key: item for key, item in record.items() if key != "evidence"},
                "metadata": {
                    **record["metadata"],
                    "provider_id": NCBI_PUBMED_PROVIDER_ID,
                    "article_pmid": job["article"]["pmid"],
                    "article_pmcid": job["article"]["pmcid"],
                    "article_doi": job["article"]["doi"],
                    "article_title": job["article"]["title"],
                    "article_publication_date": job["article"]["publication_date"],
                    "article_canonical_url": job["article"]["canonical_url"],
                    "result_location": evidence["result_label"],
                    "context_location": evidence["context_label"],
                    "evidence_value_text": evidence["value_text"],
                    **hashes,
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


def _normalize_optional_pmcid(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    pmcid = _text(value, field_name).upper()
    if _PMCID.fullmatch(pmcid) is None:
        raise ValueError(f"{field_name} must be null or a positive PMC identifier")
    return pmcid


def _normalize_disease_model_article(value: Any) -> tuple[dict[str, Any], date]:
    article = _mapping(value, "job.article")
    if set(article) != _DISEASE_MODEL_ARTICLE_FIELDS:
        raise ValueError(
            f"job.article must contain exactly {sorted(_DISEASE_MODEL_ARTICLE_FIELDS)}"
        )
    pmid = _text(article["pmid"], "job.article.pmid")
    if _PMID.fullmatch(pmid) is None:
        raise ValueError("job.article.pmid must be a positive PubMed identifier")
    doi = _text(article["doi"], "job.article.doi").casefold()
    if _DOI.fullmatch(doi) is None:
        raise ValueError("job.article.doi must be a DOI")
    publication_date = _iso_date(
        article["publication_date"], "job.article.publication_date"
    )
    title = _normalized_text(_text(article["title"], "job.article.title"))
    if len(title) > 4096:
        raise ValueError("job.article.title must contain at most 4096 characters")
    return (
        {
            "title": title,
            "pmid": pmid,
            "pmcid": _normalize_optional_pmcid(article["pmcid"], "job.article.pmcid"),
            "doi": doi,
            "publication_date": publication_date.isoformat(),
            "canonical_url": _canonical_pubmed_url(
                article["canonical_url"], pmid, "job.article.canonical_url"
            ),
        },
        publication_date,
    )


def _normalize_relation(value: Any, field_name: str) -> str:
    relation = _text(value, field_name).casefold()
    if relation not in _GAP_OPERATORS:
        raise ValueError(f"{field_name} is unsupported")
    return relation


def _typed_value_text(
    value: str,
    *,
    field_name: str,
) -> tuple[str, Decimal, bool]:
    match = _TYPED_VALUE_TEXT.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must contain one typed numeric value")
    operator = _COMPARISON_TO_OPERATOR[match.group("comparison") or ""]
    try:
        number = Decimal(match.group("value"))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} has an invalid numeric value") from exc
    return operator, number, match.group("percent") == "%"


def _normalize_disease_model_record(
    value: Any,
    *,
    index: int,
    source_receipt_id: str,
    article: Mapping[str, Any],
    publication_date: date,
) -> tuple[dict[str, Any], dict[str, str]]:
    label = f"job.records[{index}]"
    record = _mapping(value, label)
    if set(record) != _RECORD_FIELDS:
        raise ValueError(f"{label} must contain exactly {sorted(_RECORD_FIELDS)}")
    if record["predicate"] != "disease_model_effect_supported":
        raise ValueError(f"{label}.predicate must be disease_model_effect_supported")
    observed_at = _iso_date(record["observed_at"], f"{label}.observed_at")
    available_at = _iso_date(record["available_at"], f"{label}.available_at")
    if observed_at > available_at:
        raise ValueError(f"{label}.observed_at cannot follow available_at")
    if available_at != publication_date:
        raise ValueError(f"{label}.available_at must equal article publication_date")

    context = _mapping(record["biological_context"], f"{label}.biological_context")
    if set(context) != _DISEASE_MODEL_CONTEXT_FIELDS:
        raise ValueError(
            f"{label}.biological_context must contain exactly "
            f"{sorted(_DISEASE_MODEL_CONTEXT_FIELDS)}"
        )
    context = {
        key: _text(item, f"{label}.biological_context.{key}")
        for key, item in context.items()
    }

    metadata = _mapping(record["metadata"], f"{label}.metadata")
    if set(metadata) != _DISEASE_MODEL_METADATA_FIELDS:
        raise ValueError(
            f"{label}.metadata must contain exactly "
            f"{sorted(_DISEASE_MODEL_METADATA_FIELDS)}"
        )
    provider_fields = {
        _normalized_field_name(key) for key in _DISEASE_MODEL_PROVIDER_METADATA_FIELDS
    }
    overlap = sorted(
        key for key in metadata if _normalized_field_name(key) in provider_fields
    )
    if overlap:
        raise ValueError(f"{label}.metadata contains provider-owned fields: {overlap}")
    text_fields = (
        "model_system",
        "model_type",
        "endpoint",
        "endpoint_unit",
        "endpoint_variation_unit",
        "effect_direction",
        "disease_relevance",
        "source_candidate_name",
        "dose_unit",
        "route",
        "frequency",
        "duration_unit",
    )
    normalized_metadata = dict(metadata)
    for key in text_fields:
        normalized_metadata[key] = _text(metadata[key], f"{label}.metadata.{key}")
    for key in (
        "endpoint_value",
        "endpoint_variation_value",
        "dose_value",
        "duration_value",
        "p_value",
    ):
        _finite_decimal(metadata[key], f"{label}.metadata.{key}")
    for key in ("endpoint_relation", "p_value_relation"):
        normalized_metadata[key] = _normalize_relation(
            metadata[key], f"{label}.metadata.{key}"
        )
    if _comparison_text(normalized_metadata["endpoint_unit"]) != "percent":
        raise ValueError(f"{label}.metadata.endpoint_unit must be percent")
    if _comparison_text(normalized_metadata["endpoint_variation_unit"]) != "percent":
        raise ValueError(f"{label}.metadata.endpoint_variation_unit must be percent")
    if _comparison_text(normalized_metadata["route"]) != "oral":
        raise ValueError(f"{label}.metadata.route must be oral")

    evidence = _mapping(record["evidence"], f"{label}.evidence")
    if set(evidence) != _DISEASE_MODEL_EVIDENCE_FIELDS:
        raise ValueError(
            f"{label}.evidence must contain exactly "
            f"{sorted(_DISEASE_MODEL_EVIDENCE_FIELDS)}"
        )
    normalized_evidence = {
        key: _normalized_text(_text(item, f"{label}.evidence.{key}"))
        for key, item in evidence.items()
    }
    for key in ("result_excerpt", "conclusion_excerpt"):
        if not 20 <= len(normalized_evidence[key]) <= 4096:
            raise ValueError(f"{label}.evidence.{key} must contain 20-4096 characters")
    if _comparison_text(normalized_evidence["candidate_anchor"]) != _comparison_text(
        normalized_metadata["source_candidate_name"]
    ):
        raise ValueError(f"{label} source candidate does not match its evidence anchor")
    if (
        _comparison_text(normalized_evidence["route_anchor"]) != "orally"
        or _comparison_text(normalized_metadata["route"]) != "oral"
    ):
        raise ValueError(f"{label} route does not match its evidence anchor")
    if _comparison_text(normalized_evidence["frequency_anchor"]) != _comparison_text(
        normalized_metadata["frequency"]
    ):
        raise ValueError(f"{label} frequency does not match its evidence anchor")

    endpoint_relation, endpoint_value, endpoint_percent = _typed_value_text(
        normalized_evidence["endpoint_value_text"],
        field_name=f"{label}.evidence.endpoint_value_text",
    )
    if (
        endpoint_relation != normalized_metadata["endpoint_relation"]
        or endpoint_value != Decimal(str(normalized_metadata["endpoint_value"]))
        or not endpoint_percent
    ):
        raise ValueError(f"{label} endpoint value does not match typed metadata")
    variation_relation, variation_value, variation_percent = _typed_value_text(
        normalized_evidence["endpoint_variation_text"],
        field_name=f"{label}.evidence.endpoint_variation_text",
    )
    if (
        variation_relation != "eq"
        or variation_value
        != Decimal(str(normalized_metadata["endpoint_variation_value"]))
        or not variation_percent
    ):
        raise ValueError(f"{label} endpoint variation does not match typed metadata")
    p_relation, p_value, p_percent = _typed_value_text(
        normalized_evidence["p_value_text"],
        field_name=f"{label}.evidence.p_value_text",
    )
    if (
        p_relation != normalized_metadata["p_value_relation"]
        or p_value != Decimal(str(normalized_metadata["p_value"]))
        or p_percent
    ):
        raise ValueError(f"{label} p-value does not match typed metadata")

    dose_match = re.fullmatch(
        r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s+(?P<unit>\S+)",
        normalized_evidence["dose_text"],
    )
    if (
        dose_match is None
        or Decimal(dose_match.group("value"))
        != Decimal(str(normalized_metadata["dose_value"]))
        or _comparison_text(dose_match.group("unit"))
        != _comparison_text(normalized_metadata["dose_unit"])
    ):
        raise ValueError(f"{label} dose does not match typed metadata")
    duration_match = re.fullmatch(
        r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s+(?P<unit>\S+)",
        normalized_evidence["duration_text"],
    )
    if (
        duration_match is None
        or Decimal(duration_match.group("value"))
        != Decimal(str(normalized_metadata["duration_value"]))
        or _comparison_text(duration_match.group("unit"))
        != _comparison_text(normalized_metadata["duration_unit"])
    ):
        raise ValueError(f"{label} duration does not match typed metadata")

    generic_record = {
        "source_receipt_id": source_receipt_id,
        "record_id": _safe_id(record["record_id"], f"{label}.record_id"),
        "predicate": "disease_model_effect_supported",
        "subject": _text(record["subject"], f"{label}.subject"),
        "object_value": _text(record["object_value"], f"{label}.object_value"),
        "observed_at": observed_at.isoformat(),
        "available_at": available_at.isoformat(),
        "confidence": _probability(record["confidence"], f"{label}.confidence"),
        "biological_context": context,
        "metadata": {
            **normalized_metadata,
            "source_lineage_ids": [
                f"pubmed:{article['pmid']}",
                f"doi:{article['doi']}",
            ],
        },
    }
    return generic_record, normalized_evidence


def normalize_ncbi_pubmed_disease_model_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate one reviewer-authored PubMed disease-model extraction job."""

    job = _mapping(value, "job")
    if set(job) != _DISEASE_MODEL_JOB_FIELDS:
        raise ValueError(
            f"job must contain exactly {sorted(_DISEASE_MODEL_JOB_FIELDS)}"
        )
    if job["schema_version"] != NCBI_PUBMED_DISEASE_MODEL_JOB_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {NCBI_PUBMED_DISEASE_MODEL_JOB_SCHEMA_VERSION}"
        )
    job_id = _safe_id(job["job_id"], "job.job_id")
    source_receipt_id = _safe_id(job["source_receipt_id"], "job.source_receipt_id")
    article, publication_date = _normalize_disease_model_article(job["article"])
    raw_records = _sequence(job["records"], "job.records")
    if len(raw_records) != 1:
        raise ValueError("job.records must contain exactly one disease-model record")
    generic, evidence = _normalize_disease_model_record(
        raw_records[0],
        index=0,
        source_receipt_id=source_receipt_id,
        article=article,
        publication_date=publication_date,
    )
    normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "records": [generic],
        }
    )
    return {
        "schema_version": NCBI_PUBMED_DISEASE_MODEL_JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "source_receipt_id": source_receipt_id,
        "article": article,
        "records": [
            {
                **{
                    key: item
                    for key, item in generic.items()
                    if key != "source_receipt_id"
                },
                "metadata": {
                    key: generic["metadata"][key]
                    for key in _DISEASE_MODEL_METADATA_FIELDS
                },
                "evidence": evidence,
            }
        ],
    }


def _optional_article_identifier(
    article_id_list: ET.Element,
    id_type: str,
    field_name: str,
) -> str | None:
    matches = [
        item
        for item in _direct_children(article_id_list, "ArticleId")
        if item.attrib.get("IdType", "").casefold() == id_type.casefold()
    ]
    if len(matches) > 1:
        raise ValueError(f"NCBI PubMed XML must contain at most one {field_name}")
    return _element_text(matches[0], field_name) if matches else None


def _validate_disease_model_article_source(
    job: Mapping[str, Any],
    bundle: SourceBundle,
    root: ET.Element,
) -> None:
    declared = job["article"]
    receipt = bundle.receipt
    if receipt.receipt_id != job["source_receipt_id"]:
        raise ValueError("NCBI PubMed disease-model source_receipt_id mismatch")
    if receipt.media_type.casefold() not in {"text/xml", "application/xml"}:
        raise ValueError("NCBI PubMed disease-model source must declare XML")
    _validate_efetch_locator(receipt.locator, declared["pmid"])
    expected_version = (
        f"pmid-{declared['pmid']}-pubmed-xml-{receipt.retrieved_at.date().isoformat()}"
    )
    if receipt.source_version != expected_version:
        raise ValueError("NCBI PubMed disease-model source_version mismatch")
    if date.fromisoformat(declared["publication_date"]) > receipt.retrieved_at.date():
        raise ValueError("NCBI PubMed disease-model source predates publication")

    pubmed_article = _single_child(root, "PubmedArticle", "PubmedArticle")
    medline = _single_child(pubmed_article, "MedlineCitation", "MedlineCitation")
    pubmed_data = _single_child(pubmed_article, "PubmedData", "PubmedData")
    article = _single_child(medline, "Article", "Article")
    _reject_retracted(medline, article)
    pmid = _element_text(_single_child(medline, "PMID", "MedlineCitation PMID"), "PMID")
    title = _element_text(
        _single_child(article, "ArticleTitle", "ArticleTitle"), "title"
    )
    doi_locations = [
        item
        for item in _direct_children(article, "ELocationID")
        if item.attrib.get("EIdType", "").casefold() == "doi"
    ]
    if len(doi_locations) > 1:
        raise ValueError("NCBI PubMed XML must contain at most one article DOI")
    location_doi = (
        _element_text(doi_locations[0], "article DOI").casefold()
        if doi_locations
        else None
    )
    publication_date = _article_date(article)

    article_id_list = _single_child(pubmed_data, "ArticleIdList", "ArticleIdList")
    data_pmid = _article_identifier(article_id_list, "pubmed", "PubMed ArticleId")
    data_doi = _article_identifier(article_id_list, "doi", "DOI ArticleId").casefold()
    pmcid = _optional_article_identifier(article_id_list, "pmc", "PMC ArticleId")
    if pmid != declared["pmid"] or data_pmid != declared["pmid"]:
        raise ValueError("NCBI PubMed disease-model source PMID mismatch")
    if (pmcid.upper() if pmcid is not None else None) != declared["pmcid"]:
        raise ValueError("NCBI PubMed disease-model source PMCID mismatch")
    if data_doi != declared["doi"] or (
        location_doi is not None and location_doi != declared["doi"]
    ):
        raise ValueError("NCBI PubMed disease-model source DOI mismatch")
    if _comparison_text(title) != _comparison_text(declared["title"]):
        raise ValueError("NCBI PubMed disease-model source title mismatch")
    if publication_date.isoformat() != declared["publication_date"]:
        raise ValueError("NCBI PubMed disease-model publication date mismatch")


def _unstructured_abstract(root: ET.Element) -> str:
    pubmed_article = _single_child(root, "PubmedArticle", "PubmedArticle")
    medline = _single_child(pubmed_article, "MedlineCitation", "MedlineCitation")
    article = _single_child(medline, "Article", "Article")
    abstract = _single_child(article, "Abstract", "Abstract")
    values = _direct_children(abstract, "AbstractText")
    if len(values) != 1 or _normalized_text(values[0].attrib.get("Label", "")):
        raise ValueError(
            "NCBI PubMed disease-model source must have one unstructured abstract"
        )
    return _element_text(values[0], "unstructured AbstractText")


def _validate_disease_model_evidence(
    record: Mapping[str, Any],
    abstract: str,
) -> dict[str, str]:
    evidence = record["evidence"]
    result = evidence["result_excerpt"]
    conclusion = evidence["conclusion_excerpt"]
    _exactly_once(abstract, result, "records[0].evidence.result_excerpt")
    _exactly_once(abstract, conclusion, "records[0].evidence.conclusion_excerpt")
    for key in (
        "candidate_anchor",
        "model_anchor",
        "dose_text",
        "route_anchor",
        "frequency_anchor",
        "duration_text",
        "endpoint_value_text",
        "endpoint_variation_text",
        "p_value_text",
    ):
        _exactly_once(result, evidence[key], f"records[0].evidence.{key}")
    _exactly_once(
        conclusion,
        evidence["conclusion_anchor"],
        "records[0].evidence.conclusion_anchor",
    )
    return {
        f"{key}_sha256": _sha256(evidence[key])
        for key in _DISEASE_MODEL_EVIDENCE_FIELDS
    }


def extract_ncbi_pubmed_disease_model_ingestion_job(
    value: Any,
    bundle: SourceBundle,
) -> dict[str, Any]:
    """Verify one PubMed in-vivo result and emit a payload-free generic job."""

    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    verify_source_payload(bundle.receipt, bundle.payload)
    job = normalize_ncbi_pubmed_disease_model_ingestion_job(value)
    root = _parse_pubmed_xml(bundle.payload)
    _validate_disease_model_article_source(job, bundle, root)
    abstract = _unstructured_abstract(root)
    record = job["records"][0]
    hashes = _validate_disease_model_evidence(record, abstract)
    metadata = {
        **record["metadata"],
        "source_lineage_ids": [
            f"pubmed:{job['article']['pmid']}",
            f"doi:{job['article']['doi']}",
        ],
        "provider_id": NCBI_PUBMED_PROVIDER_ID,
        "article_pmid": job["article"]["pmid"],
        "article_pmcid": job["article"]["pmcid"],
        "article_doi": job["article"]["doi"],
        "article_title": job["article"]["title"],
        "article_publication_date": job["article"]["publication_date"],
        "article_canonical_url": job["article"]["canonical_url"],
        **hashes,
    }
    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job["job_id"],
            "records": [
                {
                    "source_receipt_id": job["source_receipt_id"],
                    **{
                        key: item
                        for key, item in record.items()
                        if key not in {"metadata", "evidence"}
                    },
                    "metadata": metadata,
                }
            ],
        }
    )
