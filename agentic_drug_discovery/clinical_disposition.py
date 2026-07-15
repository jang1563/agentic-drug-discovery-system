"""Cross-source extraction for one historical negative clinical disposition."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from .ingestion import (
    INGESTION_JOB_SCHEMA_VERSION,
    SourceBundle,
    normalize_pinned_ingestion_job,
    verify_source_payload,
)
from .pinned_evidence import (
    CLINICAL_PRIMARY_ENDPOINT_NOT_MET,
    CLINICAL_TRIAL_TERMINATION,
)


CLINICAL_DISPOSITION_JOB_SCHEMA_VERSION = (
    "adds.clinical-trial-disposition-ingestion-job.v1"
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_PMID = re.compile(r"^[1-9][0-9]{0,15}$")
_DOI = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_JOB_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "source_receipt_ids",
        "identity",
        "registry_review",
        "publication_review",
    }
)
_SOURCE_RECEIPT_FIELDS = frozenset({"registry", "publication"})
_IDENTITY_FIELDS = frozenset(
    {
        "candidate_id",
        "candidate_name",
        "candidate_aliases",
        "intervention_id",
        "disease_id",
        "disease_name",
        "trial_id",
        "protocol_id",
    }
)
_REGISTRY_REVIEW_FIELDS = frozenset(
    {"record_id", "confidence", "why_stopped_code"}
)
_PUBLICATION_REVIEW_FIELDS = frozenset(
    {
        "record_id",
        "confidence",
        "pmid",
        "doi",
        "source_candidate_name",
        "primary_endpoint_met",
        "effect_direction",
        "endpoint_name",
        "candidate_rate",
        "comparator_rate",
        "rate_unit",
        "early_termination_reason",
        "termination_excerpt",
        "endpoint_excerpt",
    }
)
_ENDPOINT_STOPWORDS = frozenset(
    {"a", "an", "and", "at", "in", "of", "on", "the", "to"}
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
        raise ValueError(f"{field_name} must be a safe identifier")
    return text


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _source_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _text_list(value: Any, field_name: str) -> list[str]:
    items = [
        _text(item, f"{field_name}[{index}]")
        for index, item in enumerate(_sequence(value, field_name))
    ]
    if not items or len(items) > 32:
        raise ValueError(f"{field_name} must contain 1-32 strings")
    normalized = [_normalized(item) for item in items]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicate values")
    return items


def _probability(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        raise ValueError(f"{field_name} must be between zero and one")
    return float(value)


def _non_negative_number(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return float(value)


def _iso_date(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _review_hash(value: str) -> str:
    return hashlib.sha256(_source_text(value).encode("utf-8")).hexdigest()


def _endpoint_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", _normalized(value)):
        if token in _ENDPOINT_STOPWORDS:
            continue
        tokens.add(token[:-1] if len(token) > 4 and token.endswith("s") else token)
    return tokens


def normalize_clinical_disposition_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate a reviewer-authored registry/publication disposition job."""

    job = _mapping(value, "job")
    if set(job) != _JOB_FIELDS:
        raise ValueError(f"job must contain exactly {sorted(_JOB_FIELDS)}")
    if job["schema_version"] != CLINICAL_DISPOSITION_JOB_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {CLINICAL_DISPOSITION_JOB_SCHEMA_VERSION}"
        )
    receipts = _mapping(job["source_receipt_ids"], "job.source_receipt_ids")
    if set(receipts) != _SOURCE_RECEIPT_FIELDS:
        raise ValueError(
            "job.source_receipt_ids must contain registry and publication"
        )
    normalized_receipts = {
        role: _safe_id(receipts[role], f"job.source_receipt_ids.{role}")
        for role in sorted(receipts)
    }
    if len(set(normalized_receipts.values())) != 2:
        raise ValueError("clinical disposition source receipt ids must be distinct")

    identity = _mapping(job["identity"], "job.identity")
    if set(identity) != _IDENTITY_FIELDS:
        raise ValueError(
            f"job.identity must contain exactly {sorted(_IDENTITY_FIELDS)}"
        )
    normalized_identity = {
        field_name: _text(identity[field_name], f"job.identity.{field_name}")
        for field_name in _IDENTITY_FIELDS
        if field_name != "candidate_aliases"
    }
    normalized_identity["candidate_aliases"] = _text_list(
        identity["candidate_aliases"], "job.identity.candidate_aliases"
    )
    if _NCT_ID.fullmatch(normalized_identity["trial_id"]) is None:
        raise ValueError("job.identity.trial_id must be an NCT identifier")
    if normalized_identity["intervention_id"] != normalized_identity["candidate_id"]:
        raise ValueError("job.identity.intervention_id must equal candidate_id")
    if _normalized(normalized_identity["candidate_name"]) not in {
        _normalized(item) for item in normalized_identity["candidate_aliases"]
    }:
        raise ValueError("candidate_aliases must include candidate_name")

    registry = _mapping(job["registry_review"], "job.registry_review")
    if set(registry) != _REGISTRY_REVIEW_FIELDS:
        raise ValueError(
            "job.registry_review must contain exactly "
            f"{sorted(_REGISTRY_REVIEW_FIELDS)}"
        )
    normalized_registry = {
        "record_id": _safe_id(
            registry["record_id"], "job.registry_review.record_id"
        ),
        "confidence": _probability(
            registry["confidence"], "job.registry_review.confidence"
        ),
        "why_stopped_code": _text(
            registry["why_stopped_code"],
            "job.registry_review.why_stopped_code",
        ),
    }
    if _normalized(normalized_registry["why_stopped_code"]) != "lack_of_efficacy":
        raise ValueError("registry why_stopped_code must be lack_of_efficacy")

    publication = _mapping(job["publication_review"], "job.publication_review")
    if set(publication) != _PUBLICATION_REVIEW_FIELDS:
        raise ValueError(
            "job.publication_review must contain exactly "
            f"{sorted(_PUBLICATION_REVIEW_FIELDS)}"
        )
    normalized_publication = {
        field_name: _text(
            publication[field_name], f"job.publication_review.{field_name}"
        )
        for field_name in (
            "pmid",
            "doi",
            "source_candidate_name",
            "effect_direction",
            "endpoint_name",
            "rate_unit",
            "early_termination_reason",
            "termination_excerpt",
            "endpoint_excerpt",
        )
    }
    normalized_publication.update(
        {
            "record_id": _safe_id(
                publication["record_id"], "job.publication_review.record_id"
            ),
            "confidence": _probability(
                publication["confidence"], "job.publication_review.confidence"
            ),
            "primary_endpoint_met": publication["primary_endpoint_met"],
            "candidate_rate": _non_negative_number(
                publication["candidate_rate"],
                "job.publication_review.candidate_rate",
            ),
            "comparator_rate": _non_negative_number(
                publication["comparator_rate"],
                "job.publication_review.comparator_rate",
            ),
        }
    )
    if _PMID.fullmatch(normalized_publication["pmid"]) is None:
        raise ValueError("publication pmid is invalid")
    if _DOI.fullmatch(normalized_publication["doi"]) is None:
        raise ValueError("publication doi is invalid")
    if normalized_publication["primary_endpoint_met"] is not False:
        raise ValueError("publication primary_endpoint_met must be false")
    if _normalized(normalized_publication["effect_direction"]) != "no_clinical_benefit":
        raise ValueError("publication effect_direction must be no_clinical_benefit")
    if (
        _normalized(normalized_publication["early_termination_reason"])
        != "lack_of_efficacy"
    ):
        raise ValueError(
            "publication early_termination_reason must be lack_of_efficacy"
        )
    if normalized_registry["record_id"] == normalized_publication["record_id"]:
        raise ValueError("clinical disposition record ids must be distinct")
    return {
        "schema_version": CLINICAL_DISPOSITION_JOB_SCHEMA_VERSION,
        "job_id": _safe_id(job["job_id"], "job.job_id"),
        "source_receipt_ids": normalized_receipts,
        "identity": normalized_identity,
        "registry_review": normalized_registry,
        "publication_review": normalized_publication,
    }


def _json_object(payload: bytes) -> dict[str, Any]:
    try:
        return _mapping(
            json.loads(payload.decode("utf-8")), "ClinicalTrials.gov source"
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ClinicalTrials.gov source is not valid UTF-8 JSON") from exc


def _nested(value: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for field_name in path:
        if not isinstance(current, Mapping) or field_name not in current:
            raise ValueError(
                "ClinicalTrials.gov source is missing " + ".".join(path)
            )
        current = current[field_name]
    return current


def _registry_source(
    job: Mapping[str, Any], bundle: SourceBundle
) -> tuple[dict[str, Any], str, str]:
    verify_source_payload(bundle.receipt, bundle.payload)
    receipt = bundle.receipt
    identity = job["identity"]
    trial_id = identity["trial_id"]
    if receipt.receipt_id != job["source_receipt_ids"]["registry"]:
        raise ValueError("registry source receipt id mismatch")
    if receipt.source_id != f"clinicaltrials-gov-{trial_id}":
        raise ValueError("registry source_id must bind the NCT identifier")
    if receipt.locator != f"https://clinicaltrials.gov/api/v2/studies/{trial_id}":
        raise ValueError("registry locator mismatch")
    if receipt.media_type.casefold() != "application/json":
        raise ValueError("registry source must declare application/json")

    source = _json_object(bundle.payload)
    identification = _mapping(
        _nested(source, ("protocolSection", "identificationModule")),
        "ClinicalTrials.gov identificationModule",
    )
    status = _mapping(
        _nested(source, ("protocolSection", "statusModule")),
        "ClinicalTrials.gov statusModule",
    )
    design = _mapping(
        _nested(source, ("protocolSection", "designModule")),
        "ClinicalTrials.gov designModule",
    )
    intervention_module = _mapping(
        _nested(source, ("protocolSection", "armsInterventionsModule")),
        "ClinicalTrials.gov armsInterventionsModule",
    )
    conditions_module = _mapping(
        _nested(source, ("protocolSection", "conditionsModule")),
        "ClinicalTrials.gov conditionsModule",
    )
    outcomes_module = _mapping(
        _nested(source, ("protocolSection", "outcomesModule")),
        "ClinicalTrials.gov outcomesModule",
    )
    misc = _mapping(
        _nested(source, ("derivedSection", "miscInfoModule")),
        "ClinicalTrials.gov miscInfoModule",
    )
    registry_version = _iso_date(
        misc.get("versionHolder"), "ClinicalTrials.gov versionHolder"
    )
    expected_version = f"clinicaltrials-gov-{trial_id}-version-{registry_version}"
    if receipt.source_version != expected_version:
        raise ValueError("registry source_version mismatch")
    protocol = _mapping(
        identification.get("orgStudyIdInfo"), "ClinicalTrials.gov orgStudyIdInfo"
    )
    phases = _text_list(design.get("phases"), "ClinicalTrials.gov phases")
    interventions = [
        _text(item.get("name"), "ClinicalTrials.gov intervention name")
        for item in _sequence(
            intervention_module.get("interventions"),
            "ClinicalTrials.gov interventions",
        )
        if isinstance(item, Mapping)
    ]
    conditions = _text_list(
        conditions_module.get("conditions"), "ClinicalTrials.gov conditions"
    )
    outcomes = _sequence(
        outcomes_module.get("primaryOutcomes"),
        "ClinicalTrials.gov primaryOutcomes",
    )
    if len(outcomes) != 1 or not isinstance(outcomes[0], Mapping):
        raise ValueError("ClinicalTrials.gov source must have one primary outcome")
    primary_endpoint = _text(
        outcomes[0].get("measure"), "ClinicalTrials.gov primary outcome measure"
    )
    enrollment = _mapping(
        design.get("enrollmentInfo"), "ClinicalTrials.gov enrollmentInfo"
    ).get("count")
    aliases = {_normalized(item) for item in identity["candidate_aliases"]}
    if (
        identification.get("nctId") != trial_id
        or protocol.get("id") != identity["protocol_id"]
        or status.get("overallStatus") != "TERMINATED"
        or _text(status.get("whyStopped"), "ClinicalTrials.gov whyStopped") is None
        or design.get("studyType") != "INTERVENTIONAL"
        or len(phases) != 1
        or not interventions
        or not {_normalized(item) for item in interventions} & aliases
        or not any(
            _normalized(identity["disease_name"]) in _normalized(item)
            or _normalized(item) in _normalized(identity["disease_name"])
            for item in conditions
        )
        or not isinstance(enrollment, int)
        or isinstance(enrollment, bool)
        or enrollment <= 0
    ):
        raise ValueError("ClinicalTrials.gov disposition identities do not match")
    observed_at = _iso_date(
        status.get("lastUpdateSubmitDate"),
        "ClinicalTrials.gov lastUpdateSubmitDate",
    )
    post = _mapping(
        status.get("lastUpdatePostDateStruct"),
        "ClinicalTrials.gov lastUpdatePostDateStruct",
    )
    available_at = _iso_date(
        post.get("date"), "ClinicalTrials.gov lastUpdatePostDateStruct.date"
    )
    if available_at < observed_at:
        raise ValueError("ClinicalTrials.gov posted date precedes submission date")
    return (
        {
            "provider_id": "clinicaltrials_gov",
            "registry": "ClinicalTrials.gov",
            "registry_version": registry_version,
            "study_type": design["studyType"],
            "overall_status": status["overallStatus"],
            "phase": phases[0],
            "why_stopped": status["whyStopped"],
            "why_stopped_code": job["registry_review"]["why_stopped_code"],
            "primary_endpoint": primary_endpoint,
            "enrollment_count": enrollment,
            "source_interventions": interventions,
            "source_conditions": conditions,
        },
        observed_at,
        available_at,
    )


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child) == name]


def _single_child(element: ET.Element, name: str, field_name: str) -> ET.Element:
    values = _children(element, name)
    if len(values) != 1:
        raise ValueError(f"PubMed XML must contain exactly one {field_name}")
    return values[0]


def _element_text(element: ET.Element, field_name: str) -> str:
    return _text("".join(element.itertext()), field_name)


def _xml_date(element: ET.Element, field_name: str) -> str:
    values = {}
    for component in ("Year", "Month", "Day"):
        child = _single_child(element, component, f"{field_name} {component}")
        values[component] = int(_element_text(child, f"{field_name} {component}"))
    return _iso_date(
        f"{values['Year']:04d}-{values['Month']:02d}-{values['Day']:02d}",
        field_name,
    )


def _pubmed_locator_matches(locator: str, pmid: str) -> bool:
    parsed = urllib.parse.urlsplit(locator)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return (
        parsed.scheme.casefold() == "https"
        and parsed.hostname == "eutils.ncbi.nlm.nih.gov"
        and parsed.path == "/entrez/eutils/efetch.fcgi"
        and query.get("db") == ["pubmed"]
        and query.get("id") == [pmid]
        and query.get("retmode") == ["xml"]
    )


def _reported_numbers(value: str) -> set[float]:
    return {
        float(item.replace("·", "."))
        for item in re.findall(r"(?<![0-9])[0-9]+(?:[.·][0-9]+)?", value)
    }


def _publication_source(
    job: Mapping[str, Any], bundle: SourceBundle
) -> tuple[dict[str, Any], str, str, dict[str, str]]:
    verify_source_payload(bundle.receipt, bundle.payload)
    receipt = bundle.receipt
    review = job["publication_review"]
    identity = job["identity"]
    pmid = review["pmid"]
    if receipt.receipt_id != job["source_receipt_ids"]["publication"]:
        raise ValueError("publication source receipt id mismatch")
    if receipt.source_id != f"ncbi-pubmed-{pmid}":
        raise ValueError("publication source_id must bind the PMID")
    if receipt.source_version != (
        f"pmid-{pmid}-pubmed-xml-{receipt.retrieved_at.date().isoformat()}"
    ):
        raise ValueError("publication source_version mismatch")
    if not _pubmed_locator_matches(receipt.locator, pmid):
        raise ValueError("publication source locator mismatch")
    if receipt.media_type.casefold() not in {"text/xml", "application/xml"}:
        raise ValueError("publication source must declare XML")
    try:
        root = ET.fromstring(bundle.payload)
    except ET.ParseError as exc:
        raise ValueError("publication source is not valid PubMed XML") from exc
    articles = [item for item in root if _local_name(item) == "PubmedArticle"]
    if len(articles) != 1:
        raise ValueError("PubMed XML must contain exactly one PubmedArticle")
    pubmed_article = articles[0]
    medline = _single_child(pubmed_article, "MedlineCitation", "MedlineCitation")
    pubmed_data = _single_child(pubmed_article, "PubmedData", "PubmedData")
    article = _single_child(medline, "Article", "Article")
    source_pmid = _element_text(
        _single_child(medline, "PMID", "PMID"), "PubMed PMID"
    )
    title = _element_text(
        _single_child(article, "ArticleTitle", "ArticleTitle"),
        "PubMed article title",
    )
    abstract = _single_child(article, "Abstract", "Abstract")
    abstract_text = _source_text(
        " ".join(
            _element_text(item, "AbstractText")
            for item in _children(abstract, "AbstractText")
        )
    )
    article_id_list = _single_child(pubmed_data, "ArticleIdList", "ArticleIdList")
    article_ids = {
        item.attrib.get("IdType", "").casefold(): _element_text(item, "ArticleId")
        for item in _children(article_id_list, "ArticleId")
    }
    author_list = _single_child(article, "AuthorList", "AuthorList")
    collective_names = [
        _element_text(name, "CollectiveName")
        for author in _children(author_list, "Author")
        for name in _children(author, "CollectiveName")
    ]
    publication_type_list = _single_child(
        article, "PublicationTypeList", "PublicationTypeList"
    )
    if any(
        "retracted publication" in _normalized(_element_text(item, "PublicationType"))
        for item in _children(publication_type_list, "PublicationType")
    ):
        raise ValueError("PubMed XML identifies a retracted publication")
    article_dates = _children(article, "ArticleDate")
    if len(article_dates) != 1:
        raise ValueError("PubMed XML must contain one ArticleDate")
    publication_date = _xml_date(article_dates[0], "PubMed ArticleDate")
    history = _single_child(pubmed_data, "History", "PubMed history")
    public_dates = [
        _xml_date(item, "PubMed public date")
        for item in _children(history, "PubMedPubDate")
        if item.attrib.get("PubStatus", "").casefold() in {"pubmed", "entrez"}
    ]
    if not public_dates:
        raise ValueError("PubMed XML lacks a public availability date")
    available_at = min(public_dates)
    if available_at < publication_date:
        raise ValueError("PubMed public date precedes ArticleDate")

    termination_excerpt = _source_text(review["termination_excerpt"])
    endpoint_excerpt = _source_text(review["endpoint_excerpt"])
    protocol_collective = f"{identity['protocol_id']} Study Investigators"
    aliases = {_normalized(item) for item in identity["candidate_aliases"]}
    source_numbers = _reported_numbers(endpoint_excerpt)
    registry_endpoint = job["_registry_metadata"]["primary_endpoint"]
    endpoint_overlap = _endpoint_tokens(registry_endpoint) & _endpoint_tokens(
        review["endpoint_name"]
    )
    if (
        source_pmid != pmid
        or article_ids.get("pubmed") != pmid
        or _normalized(article_ids.get("doi", "")) != _normalized(review["doi"])
        or protocol_collective not in collective_names
        or _normalized(review["source_candidate_name"]) not in aliases
        or _normalized(review["source_candidate_name"])
        not in _normalized(title + " " + abstract_text)
        or termination_excerpt not in abstract_text
        or endpoint_excerpt not in abstract_text
        or review["candidate_rate"] not in source_numbers
        or review["comparator_rate"] not in source_numbers
        or len(endpoint_overlap) < 2
    ):
        raise ValueError("PubMed disposition declarations do not match")
    if date.fromisoformat(publication_date) > receipt.retrieved_at.date():
        raise ValueError("publication source predates the article")
    return (
        {
            "provider_id": "ncbi_pubmed",
            "pmid": pmid,
            "doi": review["doi"],
            "article_title": title,
            "publication_date": publication_date,
            "source_candidate_name": review["source_candidate_name"],
            "primary_endpoint_met": review["primary_endpoint_met"],
            "effect_direction": review["effect_direction"],
            "endpoint_name": review["endpoint_name"],
            "registry_primary_endpoint": registry_endpoint,
            "candidate_rate": review["candidate_rate"],
            "comparator_rate": review["comparator_rate"],
            "rate_unit": review["rate_unit"],
            "early_termination_reason": review["early_termination_reason"],
        },
        publication_date,
        available_at,
        {
            "termination_excerpt_sha256": _review_hash(termination_excerpt),
            "endpoint_excerpt_sha256": _review_hash(endpoint_excerpt),
        },
    )


def extract_clinical_disposition_ingestion_job(
    value: Any,
    bundles: Mapping[str, SourceBundle],
) -> dict[str, Any]:
    """Verify registry and publication bytes and emit two payload-free records."""

    job = normalize_clinical_disposition_ingestion_job(value)
    if not isinstance(bundles, Mapping) or set(bundles) != _SOURCE_RECEIPT_FIELDS:
        raise ValueError("bundles must contain registry and publication")
    for role, bundle in bundles.items():
        if not isinstance(bundle, SourceBundle):
            raise TypeError(f"bundles.{role} must be a SourceBundle")
    if (
        bundles["registry"].receipt.source_id
        == bundles["publication"].receipt.source_id
        or bundles["registry"].receipt.content_hash
        == bundles["publication"].receipt.content_hash
    ):
        raise ValueError("clinical disposition source bytes must be distinct")

    registry_metadata, registry_observed, registry_available = _registry_source(
        job, bundles["registry"]
    )
    job_with_registry = {**job, "_registry_metadata": registry_metadata}
    (
        publication_metadata,
        publication_observed,
        publication_available,
        publication_hashes,
    ) = _publication_source(job_with_registry, bundles["publication"])
    identity = job["identity"]
    shared_lineage = f"sponsor-protocol:{identity['protocol_id']}"
    context = {
        "candidate_id": identity["candidate_id"],
        "intervention_id": identity["intervention_id"],
        "disease_id": identity["disease_id"],
        "trial_id": identity["trial_id"],
        "protocol_id": identity["protocol_id"],
    }
    common_metadata = {
        "protocol_id": identity["protocol_id"],
        "candidate_aliases": identity["candidate_aliases"],
        "shared_trial_lineage_id": shared_lineage,
    }
    records = [
        {
            "source_receipt_id": job["source_receipt_ids"]["registry"],
            "record_id": job["registry_review"]["record_id"],
            "predicate": CLINICAL_TRIAL_TERMINATION,
            "subject": identity["candidate_name"],
            "object_value": identity["disease_name"],
            "observed_at": registry_observed,
            "available_at": registry_available,
            "confidence": job["registry_review"]["confidence"],
            "biological_context": context,
            "metadata": {
                **common_metadata,
                **registry_metadata,
                "source_lineage_ids": [
                    f"clinicaltrials-gov:{identity['trial_id']}",
                    shared_lineage,
                ],
            },
        },
        {
            "source_receipt_id": job["source_receipt_ids"]["publication"],
            "record_id": job["publication_review"]["record_id"],
            "predicate": CLINICAL_PRIMARY_ENDPOINT_NOT_MET,
            "subject": identity["candidate_name"],
            "object_value": identity["disease_name"],
            "observed_at": publication_observed,
            "available_at": publication_available,
            "confidence": job["publication_review"]["confidence"],
            "biological_context": context,
            "metadata": {
                **common_metadata,
                **publication_metadata,
                **publication_hashes,
                "source_lineage_ids": [
                    f"pubmed:{job['publication_review']['pmid']}",
                    shared_lineage,
                ],
            },
        },
    ]
    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job["job_id"],
            "records": records,
        }
    )
